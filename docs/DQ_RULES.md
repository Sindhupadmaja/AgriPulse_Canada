# Data quality rules

Statuses: **PASS**, **WARN** (advisory finding), **FAIL** (blocking, stops publishing), **INFO**, **SKIP**.
Thresholds live in `src/config.py`.

## Row-level rules (rows are rejected and written to `audit_rejected_records`)

| Reason | Meaning |
|---|---|
| `invalid_year` | REF_DATE cannot be read as a year |
| `missing_dimension` | geography or crop is blank |
| `unmapped_measure` | the measure and unit label is not recognized |
| `missing_value` | VALUE is blank (the StatCan symbol and status are kept in `detail`) |
| `invalid_number` | VALUE is not numeric |
| `negative_value` | VALUE is below zero |
| `duplicate_key` | same year, geography, crop, measure and unit already loaded (first row kept) |

Rows in imperial units are not rejected: they are held as **reference-only** and used for DQ-A02.

## Row flags (rows are loaded, with a flag in `quality_flags`)

`standardized_name` (crop spelling mapped to the catalog name), `new_crop` (not in
`config/crop_catalog.csv`), `use_with_caution` (StatCan status E), `out_of_range` (yield outside limits).

## Dataset-level checks

| ID | Check | Type | Threshold |
|---|---|---|---|
| DQ-S01 | Schema contract: required columns present | blocking | all present |
| DQ-C01 | Row conservation: source = loaded + reference-only + rejected | blocking | exact |
| DQ-C02 | Warehouse load is not empty | blocking | at least 1 row |
| DQ-R01 | Rejected-row rate | blocking / warn | FAIL above 20%; WARN if any |
| DQ-N01 | Crop names not in the catalog | advisory | none |
| DQ-N02 | Crop spellings standardized | info | count only |
| DQ-M01 | No missing years inside each series | advisory | none |
| DQ-A01 | Production = harvested area x yield / 1000 | advisory | 3% or 500 t |
| DQ-A02 | Hectares agree with acres (x 2.47105) | advisory | 0.5% or 1,000 acres |
| DQ-H01 | Provinces and territories add up to Canada (additive measures) | advisory | 1% or 1,000 units |
| DQ-O01 | Yields inside plausibility limits | advisory | none |
| DQ-F01 | Latest reference year is current | advisory | at least last calendar year |
| DQ-V01 | Release-to-release revisions vs the published baseline | advisory / info | WARN if rows were dropped |
| DQ-K01 | Source-to-target: staging equals warehouse (counts and sums per measure) | blocking | exact |
| DQ-K02 | Published report table equals warehouse (per measure column) | blocking | exact |

## Why these thresholds

StatCan publishes rounded values, so small differences between area x yield and production, or
between hectares and acres, are expected. The relative tolerance and absolute floor keep the checks
from flagging rounding noise while still catching real discrepancies. Tune them in `src/config.py`.
