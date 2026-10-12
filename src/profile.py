"""Profile a Statistics Canada CSV before loading it (run this first on the real file).

    python -m src.profile --csv data/raw/real/32100359_YYYY-MM-DD.csv
"""
import argparse
import sys
from pathlib import Path

import pandas as pd

from . import config
from .standardize import SchemaError, clean_label, detect_columns, geo_level, parse_measure


def profile(csv_path):
    raw = pd.read_csv(csv_path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    lines = [f"File: {csv_path}", f"Rows: {len(raw):,}   Columns: {list(raw.columns)}"]
    try:
        cols = detect_columns(raw.columns)
    except SchemaError as exc:
        lines.append(f"SCHEMA PROBLEM: {exc}")
        return "\n".join(lines)
    years = pd.to_numeric(raw[cols["year"]].str.slice(0, 4), errors="coerce")
    lines.append(f"Reference years: {int(years.min())} to {int(years.max())}")
    lines.append("")
    lines.append(f"MEASURES  (column '{cols['measure']}' + UOM)  -> how the pipeline reads them")
    pairs = raw[[cols["measure"], cols["uom"]]].drop_duplicates().sort_values([cols["measure"], cols["uom"]])
    for m, u in pairs.itertuples(index=False):
        code, unit, system = parse_measure(clean_label(m), clean_label(u))
        if code is None:
            verdict = "UNMAPPED  (will be rejected)"
        elif (code, unit) in config.FACT_UNITS:
            verdict = f"{code} / {unit}  -> LOADED to warehouse"
        else:
            verdict = f"{code} / {unit} ({system})  -> reference only"
        lines.append(f"  {m!r:60} | {u!r:28} -> {verdict}")
    crops = sorted(raw[cols["crop"]].unique())
    lines += ["", f"CROPS ({len(crops)}):"] + [f"  {c!r}" for c in crops]
    geos = sorted(raw[cols["geo"]].unique())
    lines += ["", f"GEOGRAPHIES ({len(geos)}):"] + [f"  {g!r:45} -> {geo_level(clean_label(g))}" for g in geos]
    for key in ("status", "symbol", "scalar_id"):
        if cols.get(key):
            counts = raw[cols[key]].value_counts().head(12)
            lines += ["", f"{cols[key]} values:"] + [f"  {v!r}: {n:,}" for v, n in counts.items()]
    blank = int((raw[cols["value"]].str.strip() == "").sum())
    lines += ["", f"Rows with blank VALUE: {blank:,}"]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True)
    parser.add_argument("--out", default=str(config.ROOT / "reports" / "profile.txt"))
    args = parser.parse_args(argv)
    text = profile(args.csv)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    print(f"\n(Saved to {args.out})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
