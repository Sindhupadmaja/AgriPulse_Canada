"""Download Statistics Canada table 32-10-0359-01 (full table, CSV) as a dated snapshot.

    python scripts/download_data.py

If the download is blocked, open the table page, choose Download options > "Download entire
table (CSV)", unzip it, and save the CSV into data/raw/real/ .
"""
import datetime
import hashlib
import io
import json
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src import config  # noqa: E402


def main():
    out_dir = ROOT / "data" / "raw" / "real"
    out_dir.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(
        config.SOURCE_URL, headers={"User-Agent": "AgriPulse-Canada portfolio project"})
    print(f"Downloading {config.SOURCE_URL} ...")
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            blob = response.read()
    except Exception as exc:
        sys.exit(f"Download failed: {exc}\nUse the manual steps in this file's docstring.")
    archive = zipfile.ZipFile(io.BytesIO(blob))
    names = [n for n in archive.namelist() if n.lower().endswith(".csv") and "metadata" not in n.lower()]
    if not names:
        sys.exit(f"No data CSV found in the zip. Files: {archive.namelist()}")
    data = archive.read(names[0])
    stamp = datetime.date.today().isoformat()
    path = out_dir / f"{config.TABLE_ID}_{stamp}.csv"
    path.write_bytes(data)
    sha = hashlib.sha256(data).hexdigest()
    manifest = out_dir / "manifest.json"
    entries = json.loads(manifest.read_text()) if manifest.exists() else []
    entries.append({"file": path.name, "sha256": sha, "bytes": len(data), "url": config.SOURCE_URL,
                    "downloaded_on": stamp})
    manifest.write_text(json.dumps(entries, indent=2))
    print(f"Saved {path}  ({len(data):,} bytes)\nSHA-256: {sha}")


if __name__ == "__main__":
    main()
