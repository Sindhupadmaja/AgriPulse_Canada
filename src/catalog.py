"""Crop-name catalog and aliases (reference data kept in config/)."""
from pathlib import Path

import pandas as pd

from .standardize import clean_label, name_key


def load_aliases(config_dir):
    """alias -> canonical name (optional file config/crop_aliases.csv)."""
    path = Path(config_dir) / "crop_aliases.csv"
    if not path.exists():
        return {}
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    if not {"alias", "canonical"} <= set(df.columns):
        return {}
    return {a: c for a, c in zip(df["alias"], df["canonical"]) if a and c}


def load_or_bootstrap_catalog(config_dir, raw_crop):
    """Return (key -> canonical name, bootstrapped?).

    The first run creates config/crop_catalog.csv from the names found in the data
    (most frequent spelling per key). Later runs compare against it, so new or
    variant crop names are detected instead of silently accepted.
    """
    path = Path(config_dir) / "crop_catalog.csv"
    if path.exists():
        df = pd.read_csv(path, dtype=str, keep_default_na=False)
        return dict(zip(df["key"], df["canonical_name"])), False
    uniq = raw_crop.unique()
    table = pd.DataFrame({"raw": uniq})
    table["key"] = [name_key(u) for u in uniq]
    table["name"] = [clean_label(u) for u in uniq]
    counts = raw_crop.value_counts()
    table["n"] = table["raw"].map(counts)
    table = table[table["key"] != ""]
    top = (table.sort_values(["key", "n", "name"], ascending=[True, False, True])
           .drop_duplicates("key"))
    out = top[["name", "key"]].rename(columns={"name": "canonical_name"})
    Path(config_dir).mkdir(parents=True, exist_ok=True)
    out.to_csv(path, index=False)
    return dict(zip(out["key"], out["canonical_name"])), True
