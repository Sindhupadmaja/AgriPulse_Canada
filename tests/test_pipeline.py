import duckdb
import pandas as pd

from src.demo_data import break_schema, inject_row_defects, make_demo_frame
from tests.conftest import by_rule, run


def counts(env):
    con = duckdb.connect(str(env["db_path"]))
    try:
        return con.execute("SELECT COUNT(*) FROM fact_observation").fetchone()[0]
    finally:
        con.close()


def test_clean_run_publishes_and_reconciles(clean_csv, env):
    info = run(clean_csv, env)
    rules = by_rule(info)
    assert info["status"] == "SUCCESS", info["message"]
    assert info["published"] is True
    assert info["rows_source"] == info["rows_loaded"] + info["rows_reference_only"] + info["rows_rejected"]
    assert info["rows_rejected"] == 0
    for rule_id in ("DQ-C01", "DQ-K01", "DQ-K02", "DQ-A01", "DQ-A02", "DQ-H01", "DQ-M01", "DQ-F01"):
        assert rules[rule_id]["status"] == "PASS", (rule_id, rules[rule_id]["details"])
    assert (env["reports_dir"] / "rpt_crop_year.csv").exists()
    assert (env["config_dir"] / "crop_catalog.csv").exists()
    report = pd.read_csv(env["reports_dir"] / "rpt_crop_year.csv")
    assert {"production_t", "yield_kg_ha", "production_yoy_pct"} <= set(report.columns)


def test_row_defects_are_detected_and_not_published(clean_csv, env):
    base = run(clean_csv, env)
    published_rows = counts(env)
    dirty = env["tmp"] / "dirty.csv"
    inject_row_defects(make_demo_frame()).to_csv(dirty, index=False)
    info = run(dirty, env, label="simulated")
    rules = by_rule(info)
    assert info["status"] == "SUCCESS_WITH_WARNINGS", info["message"]
    assert info["published"] is False
    assert counts(env) == published_rows                      # warehouse untouched
    con = duckdb.connect(str(env["db_path"]))
    reasons = {r[0] for r in con.execute(
        "SELECT DISTINCT reason FROM audit_rejected_records WHERE run_id = ?", [info["run_id"]]).fetchall()}
    con.close()
    assert {"duplicate_key", "missing_value", "negative_value", "invalid_number"} <= reasons
    for rule_id in ("DQ-A01", "DQ-A02", "DQ-H01", "DQ-N01"):
        assert rules[rule_id]["status"] == "WARN", (rule_id, rules[rule_id]["details"])
    assert rules["DQ-N02"]["metric"] >= 5                     # spelling variants standardized
    assert rules["DQ-C01"]["status"] == "PASS"                # every row still accounted for
    assert base["snapshot_id"] != info["snapshot_id"]


def test_schema_break_fails_the_run(clean_csv, env):
    run(clean_csv, env)
    broken = env["tmp"] / "broken.csv"
    break_schema(make_demo_frame()).to_csv(broken, index=False)
    info = run(broken, env, label="simulated")
    assert info["status"] == "FAILED"
    assert "Missing required columns" in info["message"]
    assert by_rule(info)["DQ-S01"]["status"] == "FAIL"
    con = duckdb.connect(str(env["db_path"]))
    statuses = [r[0] for r in con.execute("SELECT status FROM audit_load_log ORDER BY run_seq").fetchall()]
    con.close()
    assert statuses == ["SUCCESS", "FAILED"]


def test_quality_gate_blocks_bad_file_and_keeps_old_data(clean_csv, env):
    run(clean_csv, env)
    before = counts(env)
    bad = make_demo_frame()
    bad["Harvest disposition"] = "Unknown measure"
    path = env["tmp"] / "bad.csv"
    bad.to_csv(path, index=False)
    info = run(path, env, label="real")
    assert info["status"] == "FAILED_GATE"
    assert info["published"] is False
    assert counts(env) == before
    assert {"DQ-C02", "DQ-R01"} <= {r["rule_id"] for r in info["results"] if r["status"] == "FAIL"}


def test_revision_check_reports_changes_between_releases(clean_csv, env):
    run(clean_csv, env)
    revised = make_demo_frame()
    mask = revised["Harvest disposition"].eq("Total farm value (dollars)")
    idx = revised.index[mask][:3]
    revised.loc[idx, "VALUE"] = revised.loc[idx, "VALUE"].astype(float).mul(1.01).round().astype(int).astype(str)
    path = env["tmp"] / "revised.csv"
    revised.to_csv(path, index=False)
    info = run(path, env, label="real")
    rule = by_rule(info)["DQ-V01"]
    assert rule["status"] == "INFO" and rule["metric"] == 3
    assert rule["details"].startswith("vs snapshot")


def test_rerunning_same_file_is_idempotent(clean_csv, env):
    first = run(clean_csv, env)
    second = run(clean_csv, env)
    assert first["snapshot_id"] == second["snapshot_id"]
    assert by_rule(second)["DQ-V01"]["status"] == "SKIP"
    con = duckdb.connect(str(env["db_path"]))
    n = con.execute("SELECT COUNT(*) FROM raw_observation").fetchone()[0]
    con.close()
    assert n == first["rows_source"]                          # raw rows stored only once
