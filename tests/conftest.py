import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import pipeline  # noqa: E402
from src.demo_data import make_demo_frame  # noqa: E402

NOW = datetime(2026, 10, 12)


@pytest.fixture
def env(tmp_path):
    """Isolated database, config, and report folders for each test."""
    return {"db_path": tmp_path / "t.duckdb", "config_dir": tmp_path / "config",
            "reports_dir": tmp_path / "reports", "now": NOW, "tmp": tmp_path}


@pytest.fixture
def clean_csv(tmp_path):
    path = tmp_path / "clean.csv"
    make_demo_frame().to_csv(path, index=False)
    return path


def run(csv, env, label="real"):
    return pipeline.run(csv, label=label, db_path=env["db_path"], config_dir=env["config_dir"],
                        reports_dir=env["reports_dir"], now=env["now"])


def by_rule(info):
    return {r["rule_id"]: r for r in info["results"]}
