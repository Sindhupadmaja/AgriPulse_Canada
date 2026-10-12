-- Persistent tables: raw snapshots and the audit trail. Warehouse tables are rebuilt each run.
CREATE TABLE IF NOT EXISTS raw_observation (
    snapshot_id VARCHAR, source_row BIGINT, ref_date VARCHAR, geo VARCHAR, crop VARCHAR,
    measure VARCHAR, uom VARCHAR, value VARCHAR, status VARCHAR, symbol VARCHAR, scalar_id VARCHAR
);
CREATE TABLE IF NOT EXISTS audit_load_log (
    run_seq INTEGER, run_id VARCHAR, label VARCHAR, snapshot_id VARCHAR, source_file VARCHAR,
    source_sha256 VARCHAR, started_at TIMESTAMP, finished_at TIMESTAMP, status VARCHAR,
    published BOOLEAN, rows_source BIGINT, rows_loaded BIGINT, rows_reference_only BIGINT,
    rows_rejected BIGINT, rows_flagged BIGINT, checks_passed INTEGER, checks_warned INTEGER,
    checks_failed INTEGER, message VARCHAR
);
CREATE TABLE IF NOT EXISTS audit_dq_results (
    run_id VARCHAR, rule_id VARCHAR, rule_name VARCHAR, severity VARCHAR, status VARCHAR,
    metric DOUBLE, threshold DOUBLE, details VARCHAR
);
CREATE TABLE IF NOT EXISTS audit_rejected_records (
    run_id VARCHAR, source_row BIGINT, reason VARCHAR, detail VARCHAR, ref_date VARCHAR,
    geo VARCHAR, crop VARCHAR, measure VARCHAR, uom VARCHAR, value_raw VARCHAR
)
