"""Export CSVs for Power BI."""
from pathlib import Path

REPORTING = {
    "dim_geography": "SELECT * FROM dim_geography ORDER BY geo_key",
    "dim_crop": "SELECT * FROM dim_crop ORDER BY crop_key",
    "dim_year": "SELECT * FROM dim_year ORDER BY year",
    "dim_measure": "SELECT * FROM dim_measure ORDER BY measure_key",
    "rpt_crop_year": "SELECT * FROM rpt_crop_year ORDER BY crop, geography, year",
}
AUDIT = {
    "audit_load_log": "SELECT * FROM audit_load_log ORDER BY run_seq",
    "audit_dq_results": """SELECT l.run_seq, l.label, d.* FROM audit_dq_results d
                           JOIN audit_load_log l USING (run_id) ORDER BY l.run_seq, d.rule_id""",
    "audit_reject_summary": """SELECT l.run_seq, l.label, r.run_id, r.reason, COUNT(*) AS rows
                               FROM audit_rejected_records r JOIN audit_load_log l USING (run_id)
                               GROUP BY ALL ORDER BY l.run_seq, rows DESC""",
    "audit_rejected_records": """SELECT l.run_seq, l.label, r.* FROM audit_rejected_records r
                                 JOIN audit_load_log l USING (run_id) WHERE r.reason <> 'unavailable_value'
                                 ORDER BY l.run_seq, r.source_row""",
}


def _copy(con, sql, path):
    con.execute(f"COPY ({sql}) TO '{Path(path).as_posix()}' (HEADER, DELIMITER ',')")


def export_group(con, reports_dir, group):
    Path(reports_dir).mkdir(parents=True, exist_ok=True)
    for name, sql in group.items():
        _copy(con, sql, Path(reports_dir) / f"{name}.csv")
