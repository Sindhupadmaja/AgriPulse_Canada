"""Central settings for the AgriPulse Canada pipeline."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "db" / "agripulse.duckdb"
REPORTS_DIR = ROOT / "reports" / "powerbi"

TABLE_ID = "32100359"
TABLE_PAGE = "https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=3210035901"
SOURCE_URL = f"https://www150.statcan.gc.ca/n1/tbl/csv/{TABLE_ID}-eng.zip"

# Gate and rule thresholds (all documented in docs/DQ_RULES.md)
MAX_REJECT_RATE = 0.20               # more rejected rows than this blocks publishing
ARITHMETIC_TOLERANCE = 0.03          # production vs harvested area x yield
ARITHMETIC_ABS_FLOOR_TONNES = 500    # ignore tiny rounding differences
AREA_TOLERANCE = 0.005               # hectares vs acres
AREA_ABS_FLOOR_ACRES = 1000
HIERARCHY_TOLERANCE = 0.01           # sum of provinces vs Canada total
HIERARCHY_ABS_FLOOR = 1000
ACRES_PER_HECTARE = 2.471053814671653
YIELD_LIMITS = {"kg_ha": 25000, "bu_ac": 400}  # plausibility ceilings

# Metric measures loaded into the warehouse: (code, name, unit_code, unit_label)
MEASURES = [
    ("seeded_area", "Seeded area", "hectares", "ha"),
    ("harvested_area", "Harvested area", "hectares", "ha"),
    ("yield", "Average yield", "kg_ha", "kg/ha"),
    ("production", "Production", "tonnes", "metric tonnes"),
    ("farm_price", "Average farm price", "dollars_per_tonne", "$/tonne"),
    ("farm_value", "Total farm value", "dollars", "$"),
]
FACT_UNITS = {(m[0], m[2]) for m in MEASURES}
ADDITIVE_MEASURES = ("seeded_area", "harvested_area", "production", "farm_value")
REPORT_COLUMNS = {
    "seeded_area": "seeded_area_ha",
    "harvested_area": "harvested_area_ha",
    "yield": "yield_kg_ha",
    "production": "production_t",
    "farm_price": "farm_price_per_t",
    "farm_value": "farm_value_dollars",
}

PROVINCES = {
    "newfoundland and labrador", "prince edward island", "nova scotia", "new brunswick",
    "quebec", "québec", "ontario", "manitoba", "saskatchewan", "alberta",
    "british columbia", "yukon", "northwest territories", "nunavut",
}
