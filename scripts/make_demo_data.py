"""Write SYNTHETIC demo data (for a dry run only; not real agricultural data)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.demo_data import make_demo_frame  # noqa: E402

out = ROOT / "data" / "raw" / "demo"
out.mkdir(parents=True, exist_ok=True)
path = out / "synthetic_32100359.csv"
make_demo_frame().to_csv(path, index=False)
print(f"Wrote synthetic demo file: {path}")
