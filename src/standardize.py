"""Row-level standardization: parse measures, clean names, apply rejection rules."""
import re

import numpy as np
import pandas as pd

from . import config


class SchemaError(Exception):
    """The input file does not match the expected Statistics Canada layout."""


_FOOTNOTE = re.compile(r"\[\d+\]")


def clean_label(value):
    text = _FOOTNOTE.sub(" ", str(value))
    return re.sub(r"\s+", " ", text).strip()


def name_key(value):
    return re.sub(r"[^a-z0-9]", "", clean_label(value).lower())


def detect_columns(columns):
    """Schema contract: find the columns the pipeline needs, or raise SchemaError."""
    cols = list(columns)
    missing = [c for c in ("REF_DATE", "GEO", "UOM", "VALUE") if c not in cols]
    measure = next((c for c in cols if "disposition" in c.lower() or "measure" in c.lower()), None)
    crop = next((c for c in cols if "crop" in c.lower()), None)
    if measure is None:
        missing.append("<measure column such as 'Harvest disposition'>")
    if crop is None:
        missing.append("<crop column such as 'Type of crop'>")
    if missing:
        raise SchemaError("Missing required columns: " + ", ".join(missing))
    return {
        "year": "REF_DATE", "geo": "GEO", "measure": measure, "crop": crop,
        "uom": "UOM", "value": "VALUE",
        "status": "STATUS" if "STATUS" in cols else None,
        "symbol": "SYMBOL" if "SYMBOL" in cols else None,
        "scalar_id": "SCALAR_ID" if "SCALAR_ID" in cols else None,
    }


def _slug(text):
    return re.sub(r"[^a-z0-9]+", "_", str(text).lower()).strip("_")


def parse_measure(label, uom):
    """Return (measure_code, unit_code, unit_system) or (None, None, None).

    The six metric units used by the warehouse get fixed codes; every other unit (imperial
    or otherwise) gets its own code so different imperial units never collide.
    """
    text = f"{label} {uom}".lower()
    if "harvested" in text and "area" in text:
        measure = "harvested_area"
    elif ("seeded" in text or "planted" in text) and "area" in text:
        measure = "seeded_area"
    elif "yield" in text:
        measure = "yield"
    elif "production" in text:
        measure = "production"
    elif "farm price" in text:
        measure = "farm_price"
    elif "farm value" in text:
        measure = "farm_value"
    else:
        return (None, None, None)
    unit_text = str(uom).strip().lower()
    if not unit_text:
        found = re.search(r"\(([^)]*)\)", str(label))
        unit_text = found.group(1).strip().lower() if found else ""
    if "kilogram" in unit_text and "hectare" in unit_text and "per" in unit_text:
        return (measure, "kg_ha", "metric")
    if "tonne" in unit_text and "dollar" in unit_text:
        return (measure, "dollars_per_tonne", "metric")
    if unit_text in ("hectares", "hectare"):
        return (measure, "hectares", "metric")
    if unit_text in ("metric tonnes", "tonnes", "tonne", "metric tonne"):
        return (measure, "tonnes", "metric")
    if unit_text == "dollars":
        return (measure, "dollars", "neutral")
    system = "imperial" if any(w in unit_text for w in ("acre", "pound", "ton", "bushel", "hundredweight")) \
        else "other"
    return (measure, _slug(unit_text) or "unknown", system)


def geo_level(name):
    lower = str(name).lower()
    if lower == "canada":
        return "Canada"
    if lower in config.PROVINCES:
        return "Province/Territory"
    return "Region"


def _map_unique(series, fn):
    mapping = {u: fn(u) for u in series.unique()}
    return series.map(mapping)


def standardize(raw, cols, catalog, aliases):
    """Apply cleaning and rejection rules. Returns dict of DataFrames."""
    df = pd.DataFrame({
        "source_row": raw["_source_row"].to_numpy(),
        "year_raw": raw[cols["year"]].to_numpy(),
        "geo_raw": raw[cols["geo"]].to_numpy(),
        "crop_raw": raw[cols["crop"]].to_numpy(),
        "measure_raw": raw[cols["measure"]].to_numpy(),
        "uom_raw": raw[cols["uom"]].to_numpy(),
        "value_raw": raw[cols["value"]].to_numpy(),
    })
    df["status_raw"] = raw[cols["status"]].to_numpy() if cols.get("status") else ""
    df["symbol_raw"] = raw[cols["symbol"]].to_numpy() if cols.get("symbol") else ""
    df["scalar_raw"] = raw[cols["scalar_id"]].to_numpy() if cols.get("scalar_id") else "0"

    df["year"] = pd.to_numeric(df["year_raw"].str.slice(0, 4), errors="coerce")
    df["geo"] = _map_unique(df["geo_raw"], clean_label)
    df["crop_clean"] = _map_unique(df["crop_raw"], clean_label)
    key = _map_unique(df["crop_raw"], name_key)

    alias_by_key = {name_key(k): v for k, v in aliases.items()}
    in_alias = key.isin(list(alias_by_key.keys()))
    in_catalog = key.isin(list(catalog.keys()))
    canon = key.map(alias_by_key)
    canon = canon.fillna(key.map(catalog))
    canon = canon.fillna(df["crop_clean"])
    df["crop"] = canon
    df["new_crop"] = ~(in_alias | in_catalog)
    df["standardized_name"] = (~df["new_crop"]) & (df["crop_raw"] != df["crop"])

    pairs = df[["measure_raw", "uom_raw"]].drop_duplicates().reset_index(drop=True)
    parsed = [parse_measure(clean_label(m), clean_label(u))
              for m, u in zip(pairs["measure_raw"], pairs["uom_raw"])]
    pairs["measure"] = [p[0] for p in parsed]
    pairs["unit"] = [p[1] for p in parsed]
    pairs["unit_system"] = [p[2] for p in parsed]
    df = df.merge(pairs, on=["measure_raw", "uom_raw"], how="left")

    cleaned = df["value_raw"].str.replace(",", "", regex=False).str.strip()
    blank = cleaned.eq("")
    number = pd.to_numeric(cleaned.mask(blank), errors="coerce")
    invalid = (~blank) & number.isna()
    scalar = pd.to_numeric(df["scalar_raw"], errors="coerce").fillna(0)
    df["value"] = number * np.power(10.0, scalar)

    reason = pd.Series("", index=df.index, dtype="object")

    def assign(mask, name):
        selected = (reason == "") & mask.fillna(False).astype(bool)
        reason.loc[selected] = name

    assign(df["year"].isna(), "invalid_year")
    assign((df["geo"] == "") | (df["crop_clean"] == ""), "missing_dimension")
    assign(df["measure"].isna(), "unmapped_measure")
    has_symbol = (df["symbol_raw"].astype(str).str.strip() != "") | (df["status_raw"].astype(str).str.strip() != "")
    assign(blank & has_symbol, "unavailable_value")   # official StatCan marker: suppressed / not available
    assign(blank, "missing_value")                    # blank with no explanation: a real defect
    assign(invalid, "invalid_number")
    assign(df["value"] < 0, "negative_value")

    ok = reason == ""
    dup = pd.Series(False, index=df.index)
    dup.loc[ok] = df.loc[ok, ["year", "geo", "crop", "measure", "unit"]].duplicated(keep="first").to_numpy()
    assign(dup, "duplicate_key")

    bad = reason != ""
    detail = pd.Series("", index=df.index, dtype="object")
    missing = reason.isin(["missing_value", "unavailable_value"])
    detail.loc[missing] = ("symbol=" + df.loc[missing, "symbol_raw"].astype(str)
                           + " status=" + df.loc[missing, "status_raw"].astype(str))
    rejected = df.loc[bad, ["source_row", "year_raw", "geo_raw", "crop_raw", "measure_raw",
                            "uom_raw", "value_raw"]].copy()
    rejected.columns = ["source_row", "ref_date", "geo", "crop", "measure", "uom", "value_raw"]
    rejected["reason"] = reason.loc[bad].to_numpy()
    rejected["detail"] = detail.loc[bad].to_numpy()

    acc = df.loc[reason == ""].copy()
    acc["year"] = acc["year"].astype("int64")
    acc["geo_level"] = _map_unique(acc["geo"], geo_level) if len(acc) else ""
    status = acc["status_raw"].astype(str).str.strip()

    def flag(mask, text):
        return pd.Series(np.where(mask, text, ""), index=acc.index, dtype="object")

    flags = (flag(acc["standardized_name"], "standardized_name;")
             + flag(acc["new_crop"], "new_crop;")
             + flag(status.eq("E"), "use_with_caution;"))
    acc["quality_flags"] = flags.str.rstrip(";")
    acc["status_flag"] = status

    pair = pd.Series([(m, u) in config.FACT_UNITS for m, u in zip(acc["measure"], acc["unit"])],
                     index=acc.index, dtype=bool)
    unavailable = df.loc[reason == "unavailable_value", ["year", "geo", "crop", "measure", "unit"]].copy()
    unavailable["year"] = unavailable["year"].astype("int64")
    keep = ["source_row", "year", "geo", "geo_level", "crop", "crop_raw", "measure", "unit",
            "unit_system", "value", "status_flag", "quality_flags"]
    return {
        "fact": acc.loc[pair, keep].reset_index(drop=True),
        "reference": acc.loc[~pair, keep].reset_index(drop=True),
        "rejected": rejected.reset_index(drop=True),
        "unavailable": unavailable.reset_index(drop=True),
    }
