"""Create a deliberately corrupted copy of a CSV for the 'simulated failure test'.

    python scripts/make_defect_copy.py --input data/raw/real/FILE.csv --mode rows
    python scripts/make_defect_copy.py --input data/raw/real/FILE.csv --mode schema
"""
import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.demo_data import break_schema, inject_row_defects  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("--input", required=True)
parser.add_argument("--mode", choices=["rows", "schema"], required=True)
args = parser.parse_args()

df = pd.read_csv(args.input, dtype=str, keep_default_na=False, encoding="utf-8-sig")
out_dir = ROOT / "data" / "raw" / "simulated"
out_dir.mkdir(parents=True, exist_ok=True)
out = out_dir / f"simulated_{args.mode}_defects.csv"
(inject_row_defects(df) if args.mode == "rows" else break_schema(df)).to_csv(out, index=False)
print(f"Wrote {out}  (simulated test file, NOT real data)")
