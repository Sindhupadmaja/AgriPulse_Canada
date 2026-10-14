"""AgriPulse Canada pipeline: ingest -> standardize -> quality gate -> warehouse -> export.

Usage (from the repository root):
    python -m src.pipeline --csv data/raw/real/32100359_YYYY-MM-DD.csv --label real
"""
import argparse
import hashlib
import sys
import traceback
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from . import config, export, quality, warehouse
from .catalog import load_aliases, load_or_bootstrap_catalog
from .db import connect, init_schema, insert_df, load_staging, load_unavailable
from .standardize import SchemaError, detect_columns, standardize


class PipelineFailure(Exception):
    pass


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(csv_path, label="real", db_path=None, config_dir=None, reports_dir=None,
        publish=None, now=None):
    now = now or datetime.now()
    csv_path = Path(csv_path)
    db_path = db_path or config.DB_PATH
    config_dir = config_dir or config.CONFIG_DIR
    reports_dir = reports_dir or config.REPORTS_DIR
    publish = (label == "real") if publish is None else publish

    con = connect(db_path)
    init_schema(con)
    run_seq = con.execute("SELECT COALESCE(MAX(run_seq), 0) + 1 FROM audit_load_log").fetchone()[0]
    run_id = f"run{run_seq:03d}-{label}"
    baseline = con.execute(
        "SELECT snapshot_id FROM audit_load_log WHERE published ORDER BY run_seq DESC LIMIT 1").fetchone()
    baseline = baseline[0] if baseline else None

    info = {"run_seq": run_seq, "run_id": run_id, "label": label, "snapshot_id": None,
            "source_file": csv_path.name, "source_sha256": None, "started_at": now,
            "status": "FAILED", "published": False, "message": "",
            "rows_source": 0, "rows_loaded": 0, "rows_reference_only": 0,
            "rows_rejected": 0, "rows_unavailable": 0, "rows_flagged": 0}
    results, rejected = [], None

    try:
        raw = pd.read_csv(csv_path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
        raw["_source_row"] = np.arange(1, len(raw) + 1)
        info["rows_source"] = len(raw)
        try:
            cols = detect_columns([c for c in raw.columns if c != "_source_row"])
        except SchemaError as exc:
            results.append(quality.result("DQ-S01", "Schema contract: required columns present",
                                          "blocking", "FAIL", None, None, str(exc)))
            raise PipelineFailure(str(exc))
        results.append(quality.result("DQ-S01", "Schema contract: required columns present",
                                      "blocking", "PASS", None, None,
                                      f"measure column='{cols['measure']}', crop column='{cols['crop']}'"))

        sha = _sha256(csv_path)
        info["source_sha256"], info["snapshot_id"] = sha, sha[:12]
        known = con.execute("SELECT COUNT(*) FROM raw_observation WHERE snapshot_id = ?",
                            [info["snapshot_id"]]).fetchone()[0]
        if not known:
            snap = pd.DataFrame({
                "snapshot_id": info["snapshot_id"], "source_row": raw["_source_row"].to_numpy(),
                "ref_date": raw[cols["year"]].to_numpy(), "geo": raw[cols["geo"]].to_numpy(),
                "crop": raw[cols["crop"]].to_numpy(), "measure": raw[cols["measure"]].to_numpy(),
                "uom": raw[cols["uom"]].to_numpy(), "value": raw[cols["value"]].to_numpy(),
                "status": raw[cols["status"]].to_numpy() if cols["status"] else "",
                "symbol": raw[cols["symbol"]].to_numpy() if cols["symbol"] else "",
                "scalar_id": raw[cols["scalar_id"]].to_numpy() if cols["scalar_id"] else "",
            })
            insert_df(con, "raw_observation", snap)

        catalog, bootstrapped = load_or_bootstrap_catalog(config_dir, raw[cols["crop"]])
        aliases = load_aliases(config_dir)
        std = standardize(raw, cols, catalog, aliases)
        fact, reference, rejected = std["fact"], std["reference"], std["rejected"]
        rejected.insert(0, "run_id", run_id)

        load_staging(con, "stg_fact", fact)
        load_staging(con, "stg_reference", reference)
        load_unavailable(con, std["unavailable"])
        insert_df(con, "audit_rejected_records", rejected,
                  ["run_id", "source_row", "reason", "detail", "ref_date", "geo", "crop",
                   "measure", "uom", "value_raw"])

        info.update(rows_loaded=len(fact), rows_reference_only=len(reference),
                    rows_rejected=len(rejected),
                    rows_unavailable=int((rejected["reason"] == "unavailable_value").sum()),
                    rows_flagged=int((fact["quality_flags"] != "").sum()))
        warehouse.build_new(con, info["snapshot_id"])
        ctx = {"run_id": run_id, "snapshot_id": info["snapshot_id"], "baseline_snapshot": baseline,
               "now": now, "rows_source": info["rows_source"], "rows_fact": len(fact),
               "rows_reference": len(reference), "rows_rejected": len(rejected),
               "rows_unavailable": info["rows_unavailable"]}
        results += quality.run_checks(con, ctx)

        statuses = [r["status"] for r in results]
        if "FAIL" in statuses:
            info["status"] = "FAILED_GATE"
            failing = [r["rule_id"] for r in results if r["status"] == "FAIL"]
            info["message"] = "Publishing blocked by: " + ", ".join(failing)
        else:
            info["status"] = "SUCCESS_WITH_WARNINGS" if "WARN" in statuses else "SUCCESS"
            if publish:
                warehouse.publish(con)
                info["published"] = True
                info["message"] = "Warehouse published"
            else:
                info["message"] = f"Checks passed; not published (label='{label}')"
        if bootstrapped:
            info["message"] += "; created config/crop_catalog.csv from this file"
    except PipelineFailure as exc:
        info["status"], info["message"] = "FAILED", str(exc)
    except Exception as exc:  # unexpected error: record it, never lose the audit trail
        traceback.print_exc()
        info["status"], info["message"] = "FAILED", f"{type(exc).__name__}: {exc}"
    finally:
        try:
            warehouse.discard_new(con)
        except Exception:
            pass
        info["finished_at"] = datetime.now()
        statuses = [r["status"] for r in results]
        info.update(checks_passed=statuses.count("PASS"), checks_warned=statuses.count("WARN"),
                    checks_failed=statuses.count("FAIL"))
        dq = pd.DataFrame(results)
        if len(dq):
            dq.insert(0, "run_id", run_id)
            insert_df(con, "audit_dq_results", dq,
                      ["run_id", "rule_id", "rule_name", "severity", "status", "metric",
                       "threshold", "details"])
        log = pd.DataFrame([info])
        insert_df(con, "audit_load_log", log,
                  ["run_seq", "run_id", "label", "snapshot_id", "source_file", "source_sha256",
                   "started_at", "finished_at", "status", "published", "rows_source", "rows_loaded",
                   "rows_reference_only", "rows_rejected", "rows_unavailable", "rows_flagged", "checks_passed",
                   "checks_warned", "checks_failed", "message"])
        export.export_group(con, reports_dir, export.AUDIT)
        if info["published"]:
            export.export_group(con, reports_dir, export.REPORTING)
        con.close()
    info["results"] = results
    return info


def print_summary(info):
    print(f"\nRun {info['run_id']}  |  status: {info['status']}  |  published: {info['published']}")
    print(f"  source rows {info['rows_source']:,}  loaded {info['rows_loaded']:,}  "
          f"reference-only {info['rows_reference_only']:,}  rejected {info['rows_rejected']:,} "
          f"(of which official unavailable/suppressed {info['rows_unavailable']:,})  "
          f"flagged {info['rows_flagged']:,}")
    for r in info["results"]:
        print(f"  [{r['status']:<4}] {r['rule_id']}  {r['rule_name']}")
        if r["details"] and r["status"] in ("WARN", "FAIL"):
            print(f"         {r['details']}")
    if info["message"]:
        print(f"  {info['message']}")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run the AgriPulse Canada pipeline")
    parser.add_argument("--csv", required=True, help="Path to the Statistics Canada CSV")
    parser.add_argument("--label", default="real", choices=["real", "simulated", "demo"])
    parser.add_argument("--db", default=None)
    args = parser.parse_args(argv)
    info = run(args.csv, label=args.label, db_path=args.db)
    print_summary(info)
    return 1 if info["status"].startswith("FAILED") else 0


if __name__ == "__main__":
    sys.exit(main())
