"""Synthetic data in the Statistics Canada layout, used ONLY for tests and dry runs.

Nothing generated here is real agricultural data.
"""
import numpy as np
import pandas as pd

from . import config
from .standardize import detect_columns

CROPS = ["Wheat, all", "Barley", "Oats", "Canola (rapeseed)", "Corn for grain", "Soybeans"]
PROVINCES = ["Prince Edward Island", "Nova Scotia", "New Brunswick", "Quebec", "Ontario",
             "Manitoba", "Saskatchewan", "Alberta", "British Columbia"]
YEARS = list(range(2015, 2026))
COLUMNS = ["REF_DATE", "GEO", "DGUID", "Harvest disposition", "Type of crop", "UOM", "UOM_ID",
           "SCALAR_FACTOR", "SCALAR_ID", "VECTOR", "COORDINATE", "VALUE", "STATUS", "SYMBOL",
           "TERMINATED", "DECIMALS"]


def make_demo_frame(seed=42):
    rng = np.random.default_rng(seed)
    rows = []

    def add(year, geo, crop, label, uom, value):
        rows.append([str(year), geo, "2016A000011124", label, crop, uom, "100", "units", "0",
                     "v0", "1.1.1", str(value), "", "", "", "0"])

    for crop in CROPS:
        for year in YEARS:
            totals = {"seeded": 0, "harvested": 0, "production": 0, "value": 0}
            for prov in PROVINCES:
                harvested = int(rng.uniform(5_000, 2_000_000))
                seeded = int(harvested * rng.uniform(1.0, 1.05))
                yld = int(round(rng.uniform(1500, 6000) / 10.0) * 10)
                production = int(round(harvested * yld / 1000.0))
                price = int(rng.uniform(150, 600))
                farm_value = production * price
                for k, v in (("seeded", seeded), ("harvested", harvested),
                             ("production", production), ("value", farm_value)):
                    totals[k] += v
                _emit(add, year, prov, crop, seeded, harvested, yld, production, price, farm_value)
            yld_c = int(round(totals["production"] * 1000.0 / totals["harvested"] / 10.0) * 10)
            price_c = int(round(totals["value"] / totals["production"]))
            _emit(add, year, "Canada", crop, totals["seeded"], totals["harvested"], yld_c,
                  totals["production"], price_c, totals["value"])
    return pd.DataFrame(rows, columns=COLUMNS)


def _emit(add, year, geo, crop, seeded, harvested, yld, production, price, farm_value):
    k = config.ACRES_PER_HECTARE
    add(year, geo, crop, "Seeded area (hectares)", "Hectares", seeded)
    add(year, geo, crop, "Seeded area (acres)", "Acres", int(round(seeded * k)))
    add(year, geo, crop, "Harvested area (hectares)", "Hectares", harvested)
    add(year, geo, crop, "Harvested area (acres)", "Acres", int(round(harvested * k)))
    add(year, geo, crop, "Average yield (kilograms per hectare)", "Kilograms per hectare", yld)
    add(year, geo, crop, "Average yield (bushels per acre)", "Bushels per acre", round(yld / 67.25, 1))
    add(year, geo, crop, "Production (metric tonnes)", "Metric tonnes", production)
    add(year, geo, crop, "Average farm price (dollars per tonne)", "Dollars per tonne", price)
    add(year, geo, crop, "Total farm value (dollars)", "Dollars", farm_value)


def inject_row_defects(df, seed=7):
    """Return a corrupted copy for the 'simulated failure test' (row-level defects)."""
    rng = np.random.default_rng(seed)
    df = df.copy().reset_index(drop=True)
    cols = detect_columns(df.columns)
    measure, crop, geo = df[cols["measure"]].str.lower(), df[cols["crop"]], df[cols["geo"]]
    used = set()

    def pick(mask, n):
        pool = [i for i in df.index[mask] if i not in used]
        chosen = list(rng.choice(pool, size=min(n, len(pool)), replace=False)) if pool else []
        used.update(chosen)
        return chosen

    prod = measure.str.contains("production") & ~geo.str.lower().eq("canada") & df["VALUE"].str.strip().ne("")
    for i in pick(prod, 1):                       # breaks hierarchy and arithmetic checks
        df.loc[i, "VALUE"] = str(round(float(df.loc[i, "VALUE"]) * 1.4))
    acres = measure.str.contains("harvested area") & measure.str.contains("acre")
    for i in pick(acres, 1):                      # breaks hectares-vs-acres check
        df.loc[i, "VALUE"] = str(round(float(df.loc[i, "VALUE"]) * 1.2))
    for n, i in enumerate(pick(prod, 8)):         # 4 official "not available", 4 unexplained blanks
        df.loc[i, ["VALUE", "SYMBOL"]] = ["", ".." if n < 4 else ""]
    for i in pick(prod, 2):                       # negative values
        df.loc[i, "VALUE"] = "-" + df.loc[i, "VALUE"]
    for i in pick(prod, 2):                       # non-numeric values
        df.loc[i, "VALUE"] = "abc"
    first_crop = crop.value_counts().index[0]
    for i in pick(crop.eq(first_crop), 10):       # inconsistent crop spellings
        df.loc[i, cols["crop"]] = first_crop.lower() + "  "
    new_rows = df.loc[pick(prod, 3)].copy()       # a crop the catalog has never seen
    new_rows[cols["crop"]] = "Quinoa"
    dups = df.loc[pick(prod, 5)].copy()           # exact duplicate rows
    return pd.concat([df, new_rows, dups], ignore_index=True)


def break_schema(df):
    """Drop the crop column so the schema contract fails (simulated failed run)."""
    cols = detect_columns(df.columns)
    return df.drop(columns=[cols["crop"]])
