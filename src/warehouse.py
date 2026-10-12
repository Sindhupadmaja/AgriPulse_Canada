"""Build the star schema in *_new tables, then publish them atomically if checks pass."""
import pandas as pd

from . import config
from .db import insert_df

TABLES = ["dim_geography", "dim_crop", "dim_year", "dim_measure", "fact_observation", "rpt_crop_year"]


def discard_new(con):
    for table in TABLES:
        con.execute(f"DROP TABLE IF EXISTS {table}_new")


def build_new(con, snapshot_id):
    discard_new(con)
    con.execute("""
        CREATE TABLE dim_geography_new AS
        SELECT DENSE_RANK() OVER (ORDER BY lvl, geo) AS geo_key, geo AS geo_name, geo_level
        FROM (SELECT DISTINCT geo, geo_level,
                     CASE geo_level WHEN 'Canada' THEN 0 WHEN 'Province/Territory' THEN 1 ELSE 2 END AS lvl
              FROM stg_fact)""")
    con.execute("""
        CREATE TABLE dim_crop_new AS
        SELECT DENSE_RANK() OVER (ORDER BY crop) AS crop_key, crop AS crop_name,
               BOOL_OR(quality_flags LIKE '%new_crop%') AS needs_review
        FROM stg_fact GROUP BY crop""")
    con.execute("""
        CREATE TABLE dim_year_new AS
        SELECT DISTINCT year, (year // 10) * 10 AS decade FROM stg_fact""")
    con.execute("""CREATE TABLE dim_measure_new (measure_key INTEGER, measure_code VARCHAR,
                   measure_name VARCHAR, unit_code VARCHAR, unit_label VARCHAR)""")
    measures = pd.DataFrame(
        [(i + 1, m[0], m[1], m[2], m[3]) for i, m in enumerate(config.MEASURES)],
        columns=["measure_key", "measure_code", "measure_name", "unit_code", "unit_label"])
    insert_df(con, "dim_measure_new", measures)
    con.execute(f"""
        CREATE TABLE fact_observation_new AS
        SELECT f.year, g.geo_key, c.crop_key, m.measure_key, f.value, f.status_flag,
               f.quality_flags, f.source_row, '{snapshot_id}' AS snapshot_id
        FROM stg_fact f
        JOIN dim_geography_new g ON g.geo_name = f.geo
        JOIN dim_crop_new c ON c.crop_name = f.crop
        JOIN dim_measure_new m ON m.measure_code = f.measure""")
    cols = ",\n".join(
        f"MAX(CASE WHEN m.measure_code = '{code}' THEN f.value END) AS {col}"
        for code, col in config.REPORT_COLUMNS.items())
    con.execute(f"""
        CREATE TABLE rpt_crop_year_new AS
        WITH w AS (
            SELECT f.year, g.geo_name AS geography, g.geo_level, c.crop_name AS crop,
                   {cols},
                   STRING_AGG(DISTINCT NULLIF(f.quality_flags, ''), ';') AS quality_flags
            FROM fact_observation_new f
            JOIN dim_geography_new g USING (geo_key)
            JOIN dim_crop_new c USING (crop_key)
            JOIN dim_measure_new m USING (measure_key)
            GROUP BY f.year, g.geo_name, g.geo_level, c.crop_name)
        SELECT w.*, p.production_t AS production_prev_year_t,
               CASE WHEN p.production_t > 0 THEN (w.production_t - p.production_t) / p.production_t END
                   AS production_yoy_pct,
               '{snapshot_id}' AS snapshot_id
        FROM w LEFT JOIN w p ON p.geography = w.geography AND p.crop = w.crop AND p.year = w.year - 1""")


def publish(con):
    con.execute("BEGIN TRANSACTION")
    try:
        for table in TABLES:
            con.execute(f"CREATE OR REPLACE TABLE {table} AS SELECT * FROM {table}_new")
            con.execute(f"DROP TABLE {table}_new")
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
