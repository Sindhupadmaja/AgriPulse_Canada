"""DuckDB helpers."""
from pathlib import Path

import duckdb

SCHEMA_FILE = Path(__file__).resolve().parents[1] / "sql" / "01_schema.sql"


def connect(db_path):
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(db_path))


def init_schema(con):
    for statement in SCHEMA_FILE.read_text().split(";"):
        if statement.strip():
            con.execute(statement)


def insert_df(con, table, df, columns=None):
    if df is None or len(df) == 0:
        return
    con.register("_tmp_df", df)
    cols = ", ".join(columns) if columns else ", ".join(df.columns)
    con.execute(f"INSERT INTO {table} ({cols}) SELECT {cols} FROM _tmp_df")
    con.unregister("_tmp_df")


STAGING_DDL = """
CREATE TABLE {name} (
    source_row BIGINT, year INTEGER, geo VARCHAR, geo_level VARCHAR, crop VARCHAR, crop_raw VARCHAR,
    measure VARCHAR, unit VARCHAR, unit_system VARCHAR, value DOUBLE, status_flag VARCHAR,
    quality_flags VARCHAR
)"""


def load_staging(con, name, df):
    """Recreate a staging table with an explicit schema (safe even when df is empty)."""
    con.execute(f"DROP TABLE IF EXISTS {name}")
    con.execute(STAGING_DDL.format(name=name))
    insert_df(con, name, df)
