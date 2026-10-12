# Data dictionary

## Reporting tables (exported to `reports/powerbi/`)

**rpt_crop_year** (one row per year, geography and crop; used by Power BI)

| Column | Description |
|---|---|
| year | Reference year |
| geography, geo_level | Geography name and level: `Canada`, `Province/Territory` or `Region` |
| crop | Canonical crop name |
| seeded_area_ha, harvested_area_ha | Area in hectares |
| yield_kg_ha | Average yield, kilograms per hectare |
| production_t | Production, metric tonnes |
| farm_price_per_t | Average farm price, dollars per tonne |
| farm_value_dollars | Total farm value, dollars |
| quality_flags | Row flags (see DQ_RULES.md) |
| production_prev_year_t, production_yoy_pct | Prior-year production and year-over-year change |
| snapshot_id | First 12 characters of the source file SHA-256 |

**dim_geography** (geo_key, geo_name, geo_level) · **dim_crop** (crop_key, crop_name, needs_review) ·
**dim_year** (year, decade) · **dim_measure** (measure_key, measure_code, measure_name, unit_code, unit_label)

## Warehouse

**fact_observation** (long form): year, geo_key, crop_key, measure_key, value, status_flag,
quality_flags, source_row, snapshot_id.

## Audit tables (exported to `reports/powerbi/`)

| Table | Contents |
|---|---|
| audit_load_log | One row per run: label, snapshot, status, published, row counts, check counts, message |
| audit_dq_results | One row per check per run: rule, severity, status, metric, threshold, details |
| audit_reject_summary | Rejected rows by reason per run |
| audit_rejected_records | Every rejected row with its reason |

Run statuses: `SUCCESS`, `SUCCESS_WITH_WARNINGS`, `FAILED_GATE` (blocking check failed),
`FAILED` (schema contract or unexpected error). Labels: `real`, `simulated`, `demo`.
