"""Build the silver Parquet from every raw release on disk.

    python -m src.build            # from pipeline/

Writes ``data/processed/silver/pcdd_observations.parquet`` (every release, every
row, ``source_release`` kept) and ``pcdd_latest.parquet`` (one row per observation,
latest release wins). Fails if any overlapping observation differs between releases.
"""

import sys
from pathlib import Path

import pandas as pd

from .silver_loader import build_silver, resolve_latest_release, write_silver

PIPELINE_DIR = Path(__file__).resolve().parents[1]
RAW_ROOT = PIPELINE_DIR / "data" / "raw" / "pcdd"
SILVER_DIR = PIPELINE_DIR / "data" / "processed" / "silver"


def main(argv: list[str] | None = None) -> int:
    releases = (argv or sys.argv[1:]) or None
    silver = build_silver(RAW_ROOT, releases, ingested_at=pd.Timestamp.now())
    latest = resolve_latest_release(silver)
    write_silver(silver, SILVER_DIR / "pcdd_observations.parquet")
    write_silver(latest, SILVER_DIR / "pcdd_latest.parquet")
    by_release = silver.groupby("source_release").size().to_dict()
    print(f"silver: {len(silver):,} rows from {by_release}; latest-wins: {len(latest):,} rows")
    print(f"written to {SILVER_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
