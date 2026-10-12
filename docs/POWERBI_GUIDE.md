# Power BI build guide

Power BI Desktop is free and runs on Windows. Build from the **real** run's exports, never from
synthetic data.

## 1. Get the files onto your computer

After you push the repository, open it on GitHub, choose **Code > Download ZIP**, unzip it, and note the
folder `reports/powerbi`. It contains the CSVs below.

## 2. Load the data

**Home > Get data > Text/CSV**, then load each file: `rpt_crop_year`, `dim_geography`, `dim_crop`,
`dim_year`, `audit_load_log`, `audit_dq_results`, `audit_reject_summary`. Check the data types in
Power Query: `year` and `run_seq` whole numbers, measures decimal numbers, timestamps date/time.

## 3. Model (Model view)

| From (one side) | To (many side) |
|---|---|
| dim_geography[geo_name] | rpt_crop_year[geography] |
| dim_crop[crop_name] | rpt_crop_year[crop] |
| dim_year[year] | rpt_crop_year[year] |
| audit_load_log[run_id] | audit_dq_results[run_id] |
| audit_load_log[run_id] | audit_reject_summary[run_id] |

Use single-direction filters. Hide the key columns you do not need in report view.

## 4. DAX measures

```DAX
Selected Year = MAX ( dim_year[year] )
Production (t) = SUM ( rpt_crop_year[production_t] )
Harvested Area (ha) = SUM ( rpt_crop_year[harvested_area_ha] )
Seeded Area (ha) = SUM ( rpt_crop_year[seeded_area_ha] )
Farm Value ($) = SUM ( rpt_crop_year[farm_value_dollars] )
Yield (kg/ha) = DIVIDE ( [Production (t)] * 1000, [Harvested Area (ha)] )

Production Prior Year (t) =
    CALCULATE ( [Production (t)], dim_year[year] = [Selected Year] - 1 )
Production YoY % =
    DIVIDE ( [Production (t)] - [Production Prior Year (t)], [Production Prior Year (t)] )

Production Canada (t) =
    CALCULATE ( [Production (t)], dim_geography[geo_level] = "Canada" )
Production Provinces (t) =
    CALCULATE ( [Production (t)], dim_geography[geo_level] = "Province/Territory" )

Snapshot = MAX ( rpt_crop_year[snapshot_id] )
```

Never add Canada, regional and provincial rows together: that double counts. Always filter on
`geo_level`. Yield is only meaningful for one crop at a time, so use a single-select crop slicer.

## 5. Page 1: Executive overview

- Page filter: `dim_geography[geo_level]` = Canada.
- Slicers: **Crop** (dropdown, single select) and **Year**.
- Cards: Production (t), Harvested Area (ha), Yield (kg/ha), Production YoY %.
- Line chart: `year` on the axis, Production (t) as the value, for the selected crop.
- Footer text: "Source: Statistics Canada Table 32-10-0359-01. Snapshot:" plus a card showing `[Snapshot]`.
- Label units on every visual, and keep one consistent colour for production.

## 6. Page 2: Provincial and crop analysis

- Page filter: `geo_level` = Province/Territory.
- Bar chart: provinces by Production (t) for the selected crop and year.
- Bar chart: provinces by Yield (kg/ha).
- Matrix: crops as rows, provinces as columns, Production (t) as values, with background colour scale.
- Line chart: Production by province over time (legend = geography).

## 7. Page 3: Climate context

Build this in Phase 2 (Canadian Drought Monitor). Until then, leave the page out rather than showing
an empty one. When you add it: label the time period and geographic resolution on every visual, and
describe patterns only. Do not state that drought caused a production change.

## 8. Page 4: Data quality and pipeline monitoring

```DAX
Latest Real Run Seq =
    CALCULATE ( MAX ( audit_load_log[run_seq] ), audit_load_log[label] = "real" )
Source Rows =
    CALCULATE ( SUM ( audit_load_log[rows_source] ), audit_load_log[run_seq] = [Latest Real Run Seq] )
Loaded Rows =
    CALCULATE ( SUM ( audit_load_log[rows_loaded] ), audit_load_log[run_seq] = [Latest Real Run Seq] )
Rejected Rows =
    CALCULATE ( SUM ( audit_load_log[rows_rejected] ), audit_load_log[run_seq] = [Latest Real Run Seq] )
Latest Status =
    LOOKUPVALUE ( audit_load_log[status], audit_load_log[run_seq], [Latest Real Run Seq] )
Last Load Time =
    CALCULATE ( MAX ( audit_load_log[finished_at] ), audit_load_log[run_seq] = [Latest Real Run Seq] )
Failed Runs =
    CALCULATE ( COUNTROWS ( audit_load_log ),
                FILTER ( audit_load_log, LEFT ( audit_load_log[status], 6 ) = "FAILED" ) )
Reconciliation Status =
    IF (
        CALCULATE ( COUNTROWS ( audit_dq_results ),
                    audit_dq_results[run_seq] = [Latest Real Run Seq],
                    audit_dq_results[rule_id] IN { "DQ-C01", "DQ-K01", "DQ-K02" },
                    audit_dq_results[status] = "FAIL" ) = 0,
        "Balanced", "Out of balance" )
```

Visuals:

- Cards: Source Rows, Loaded Rows, Rejected Rows, Latest Status, Last Load Time, Failed Runs,
  Reconciliation Status.
- Table: run history from `audit_load_log` (run_seq, label, status, published, row counts, message).
- Bar chart: `audit_reject_summary[reason]` by rows, with a **label** slicer so you can switch between
  real runs and simulated tests.
- Table: `audit_dq_results` (rule_id, rule_name, status, metric, details) for the selected run, with
  conditional formatting on status: PASS green, WARN amber, FAIL red, INFO grey.
- Add a text note: "Runs labelled *simulated* are deliberate failure tests on corrupted copies of the
  data, not defects in the official data."

## 9. Finish and share

1. Save as `powerbi/AgriPulse_Canada.pbix`.
2. Take one screenshot per page and save them in `powerbi/` (for example `page1.png`), then link them
   from the README.
3. Record a 60 to 90 second screen recording that walks through the four pages.
4. **Publish to web** is optional. It needs a work or school email, and an administrator can turn it
   off, so the .pbix, screenshots and recording are the reliable way to share your work.

## Definition of done

- [ ] Four pages (or three, with the climate page added in Phase 2)
- [ ] Every number traceable to the pipeline run it came from (snapshot shown)
- [ ] Units labelled, no summing across geography levels
- [ ] Data-quality page shows a real run and the simulated tests
- [ ] .pbix, screenshots and README results table committed
