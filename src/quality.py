"""Dataset-level data quality, reconciliation and gate checks.

Statuses: PASS, WARN, FAIL, INFO, SKIP. Blocking rules produce FAIL and stop publishing;
advisory rules produce WARN and are reported on the dashboard.
"""
from . import config


def result(rule_id, name, severity, status, metric=None, threshold=None, details=""):
    return {"rule_id": rule_id, "rule_name": name, "severity": severity, "status": status,
            "metric": None if metric is None else float(metric),
            "threshold": None if threshold is None else float(threshold), "details": details}


def _one(con, sql, params=None):
    return con.execute(sql, params or []).fetchone()


def run_checks(con, ctx):
    out = []
    total = ctx["rows_fact"] + ctx["rows_reference"] + ctx["rows_rejected"]

    out.append(result(
        "DQ-C01", "Row conservation: source = loaded + reference-only + rejected", "blocking",
        "PASS" if total == ctx["rows_source"] else "FAIL", total, ctx["rows_source"],
        f"loaded={ctx['rows_fact']}, reference_only={ctx['rows_reference']}, "
        f"rejected={ctx['rows_rejected']}, source={ctx['rows_source']}"))

    out.append(result(
        "DQ-C02", "Warehouse load is not empty", "blocking",
        "PASS" if ctx["rows_fact"] > 0 else "FAIL", ctx["rows_fact"], 1,
        "No rows matched the expected metric measures; run the profile step and check measure labels"
        if ctx["rows_fact"] == 0 else ""))

    rate = ctx["rows_rejected"] / ctx["rows_source"] if ctx["rows_source"] else 0
    reasons = con.execute(
        "SELECT reason, COUNT(*) FROM audit_rejected_records WHERE run_id = ? GROUP BY 1 ORDER BY 2 DESC",
        [ctx["run_id"]]).fetchall()
    detail = ", ".join(f"{r}={n}" for r, n in reasons) or "no rejected rows"
    if rate > config.MAX_REJECT_RATE:
        status = "FAIL"
    elif ctx["rows_rejected"] > 0:
        status = "WARN"
    else:
        status = "PASS"
    out.append(result("DQ-R01", "Rejected-row rate within limit", "blocking", status,
                      rate, config.MAX_REJECT_RATE, detail))

    new_crops = con.execute(
        "SELECT DISTINCT crop FROM stg_fact WHERE quality_flags LIKE '%new_crop%' ORDER BY 1").fetchall()
    out.append(result(
        "DQ-N01", "Crop names not in the reference catalog", "advisory",
        "WARN" if new_crops else "PASS", len(new_crops), 0,
        ("Review and add to config/crop_catalog.csv or crop_aliases.csv: "
         + ", ".join(c[0] for c in new_crops[:10])) if new_crops else ""))

    std_rows, std_variants = _one(
        con, "SELECT COUNT(*), COUNT(DISTINCT crop_raw) FROM stg_fact WHERE quality_flags LIKE '%standardized_name%'")
    out.append(result(
        "DQ-N02", "Inconsistent crop-name spellings standardized", "advisory",
        "INFO", std_rows, None,
        f"{std_rows} rows across {std_variants} spelling variants mapped to canonical names"))

    gaps, series = _one(con, """
        WITH s AS (SELECT geo, crop, measure, MIN(year) AS lo, MAX(year) AS hi, COUNT(DISTINCT year) AS n
                   FROM stg_fact GROUP BY geo, crop, measure)
        SELECT COALESCE(SUM((hi - lo + 1) - n), 0), COUNT(*) FROM s""")
    examples = con.execute("""
        WITH s AS (SELECT geo, crop, measure, (MAX(year) - MIN(year) + 1) - COUNT(DISTINCT year) AS g
                   FROM stg_fact GROUP BY geo, crop, measure)
        SELECT geo, crop, measure, g FROM s WHERE g > 0 ORDER BY g DESC LIMIT 3""").fetchall()
    out.append(result(
        "DQ-M01", "Completeness: no missing years inside each series", "advisory",
        "WARN" if gaps else "PASS", gaps, 0,
        f"{series} series checked" + ("; e.g. " + "; ".join(f"{g}/{c}/{m} missing {n}" for g, c, m, n in examples)
                                       if examples else "")))

    tol, floor = config.ARITHMETIC_TOLERANCE, config.ARITHMETIC_ABS_FLOOR_TONNES
    checked, bad = _one(con, f"""
        WITH p AS (SELECT year, geo, crop, value AS prod FROM stg_fact WHERE measure = 'production'),
             a AS (SELECT year, geo, crop, value AS area FROM stg_fact WHERE measure = 'harvested_area'),
             y AS (SELECT year, geo, crop, value AS yld FROM stg_fact WHERE measure = 'yield')
        SELECT COUNT(*),
               COALESCE(SUM(CASE WHEN ABS(p.prod - a.area * y.yld / 1000.0) >
                                      GREATEST({tol} * p.prod, {floor}) THEN 1 ELSE 0 END), 0)
        FROM p JOIN a USING (year, geo, crop) JOIN y USING (year, geo, crop)""")
    out.append(result(
        "DQ-A01", "Production equals harvested area x yield (within tolerance)", "advisory",
        "WARN" if bad else "PASS", bad, 0, f"{checked} series-years checked, tolerance {tol:.0%}"))

    atol, afloor, k = config.AREA_TOLERANCE, config.AREA_ABS_FLOOR_ACRES, config.ACRES_PER_HECTARE
    checked, bad = _one(con, f"""
        WITH ha AS (SELECT year, geo, crop, measure, value AS ha FROM stg_fact WHERE unit = 'hectares'),
             ac AS (SELECT year, geo, crop, measure, value AS ac FROM stg_reference WHERE unit = 'acres')
        SELECT COUNT(*),
               COALESCE(SUM(CASE WHEN ABS(ac.ac - ha.ha * {k}) >
                                      GREATEST({atol} * ha.ha * {k}, {afloor}) THEN 1 ELSE 0 END), 0)
        FROM ha JOIN ac USING (year, geo, crop, measure)""")
    out.append(result(
        "DQ-A02", "Metric area agrees with imperial area (hectares vs acres)", "advisory",
        "WARN" if bad else ("PASS" if checked else "SKIP"), bad, 0,
        f"{checked} area pairs compared" if checked else "No imperial area rows found"))

    htol, hfloor = config.HIERARCHY_TOLERANCE, config.HIERARCHY_ABS_FLOOR
    measures = ",".join(f"'{m}'" for m in config.ADDITIVE_MEASURES)
    checked, bad = _one(con, f"""
        WITH prov AS (SELECT year, crop, measure, SUM(value) AS s FROM stg_fact
                      WHERE geo_level = 'Province/Territory' AND measure IN ({measures}) GROUP BY 1, 2, 3),
             can AS (SELECT year, crop, measure, value AS c FROM stg_fact
                     WHERE geo_level = 'Canada' AND measure IN ({measures}))
        SELECT COUNT(*),
               COALESCE(SUM(CASE WHEN ABS(prov.s - can.c) > GREATEST({htol} * can.c, {hfloor}) THEN 1 ELSE 0 END), 0)
        FROM prov JOIN can USING (year, crop, measure)""")
    out.append(result(
        "DQ-H01", "Provinces add up to the Canada total", "advisory",
        "WARN" if bad else ("PASS" if checked else "SKIP"), bad, 0,
        f"{checked} crop-year-measure totals compared, tolerance {htol:.0%} "
        "(suppressed provincial values can explain gaps)" if checked else "No Canada rows to compare"))

    flagged = _one(con, "SELECT COUNT(*) FROM stg_fact WHERE quality_flags LIKE '%out_of_range%'")[0]
    caution = _one(con, "SELECT COUNT(*) FROM stg_fact WHERE quality_flags LIKE '%use_with_caution%'")[0]
    out.append(result(
        "DQ-O01", "Plausibility: yields inside expected range", "advisory",
        "WARN" if flagged else "PASS", flagged, 0,
        f"{caution} rows carry the StatCan 'use with caution' (E) flag"))

    max_year = _one(con, "SELECT MAX(year) FROM stg_fact")[0]
    needed = ctx["now"].year - 1
    out.append(result(
        "DQ-F01", "Freshness: latest reference year is current", "advisory",
        "PASS" if (max_year is not None and max_year >= needed) else "WARN",
        max_year, needed, f"latest year loaded = {max_year}; expected at least {needed}"))

    out.append(_revision_check(con, ctx))

    a_cnt, b_cnt, bad_measures = _compare_stage_to_fact(con)
    out.append(result(
        "DQ-K01", "Source-to-target: staging equals warehouse (counts and sums)", "blocking",
        "PASS" if bad_measures == 0 and a_cnt == b_cnt else "FAIL", bad_measures, 0,
        f"staging_rows={a_cnt}, warehouse_rows={b_cnt}, measures_out_of_balance={bad_measures}"))

    bad_cols = _compare_report_to_fact(con)
    out.append(result(
        "DQ-K02", "Published report table equals warehouse (KPI reconciliation)", "blocking",
        "PASS" if bad_cols == 0 else "FAIL", bad_cols, 0,
        f"measure columns out of balance={bad_cols}"))
    return out


def _compare_stage_to_fact(con):
    a_cnt = _one(con, "SELECT COUNT(*) FROM stg_fact")[0]
    b_cnt = _one(con, "SELECT COUNT(*) FROM fact_observation_new")[0]
    bad = _one(con, """
        WITH a AS (SELECT measure, SUM(value) AS s, COUNT(*) AS n FROM stg_fact GROUP BY 1),
             b AS (SELECT m.measure_code AS measure, SUM(f.value) AS s, COUNT(*) AS n
                   FROM fact_observation_new f JOIN dim_measure_new m USING (measure_key) GROUP BY 1)
        SELECT COUNT(*) FROM a FULL OUTER JOIN b ON a.measure = b.measure
        WHERE a.n IS DISTINCT FROM b.n
           OR ABS(COALESCE(a.s, 0) - COALESCE(b.s, 0)) > 1e-6 * GREATEST(ABS(COALESCE(a.s, 0)), 1)""")[0]
    return a_cnt, b_cnt, bad


def _compare_report_to_fact(con):
    bad = 0
    for code, column in config.REPORT_COLUMNS.items():
        fact_sum = _one(con, """SELECT COALESCE(SUM(f.value), 0) FROM fact_observation_new f
                                JOIN dim_measure_new m USING (measure_key) WHERE m.measure_code = ?""", [code])[0]
        rpt_sum = _one(con, f"SELECT COALESCE(SUM({column}), 0) FROM rpt_crop_year_new")[0]
        if abs(fact_sum - rpt_sum) > 1e-6 * max(abs(fact_sum), 1):
            bad += 1
    return bad


def _revision_check(con, ctx):
    base, cur = ctx.get("baseline_snapshot"), ctx["snapshot_id"]
    if not base:
        return result("DQ-V01", "Release-to-release revisions vs published baseline", "advisory",
                      "SKIP", None, None, "No published baseline yet (first load)")
    if base == cur:
        return result("DQ-V01", "Release-to-release revisions vs published baseline", "advisory",
                      "SKIP", None, None, "Same file as the published baseline")
    removed, added, changed = _one(con, """
        WITH a AS (SELECT ref_date, geo, crop, measure, uom, MAX(TRY_CAST(value AS DOUBLE)) AS v
                   FROM raw_observation WHERE snapshot_id = ? GROUP BY 1, 2, 3, 4, 5),
             b AS (SELECT ref_date, geo, crop, measure, uom, MAX(TRY_CAST(value AS DOUBLE)) AS v
                   FROM raw_observation WHERE snapshot_id = ? GROUP BY 1, 2, 3, 4, 5)
        SELECT COUNT(*) FILTER (WHERE b.ref_date IS NULL),
               COUNT(*) FILTER (WHERE a.ref_date IS NULL),
               COUNT(*) FILTER (WHERE a.ref_date IS NOT NULL AND b.ref_date IS NOT NULL
                                  AND a.v IS DISTINCT FROM b.v)
        FROM a FULL OUTER JOIN b ON a.ref_date = b.ref_date AND a.geo = b.geo AND a.crop = b.crop
                                 AND a.measure = b.measure AND a.uom = b.uom""", [base, cur])
    return result("DQ-V01", "Release-to-release revisions vs published baseline", "advisory",
                  "WARN" if removed else "INFO", changed, None,
                  f"vs snapshot {base}: values changed={changed}, rows added={added}, rows dropped={removed}")
