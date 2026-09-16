"""Build the silver Parquet from every raw release on disk.

    python -m src.build            # from pipeline/

Writes to ``data/processed/silver/``:

- ``pcdd_observations.parquet`` - every release, every row, ``source_release`` kept;
                                  includes the computed ICB / region / England
                                  aggregates for levels the publisher did not publish
                                  (``is_derived = True``, no ``source_file``)
- ``pcdd_latest.parquet``       - one row per observation, latest release wins
- ``pcdd_mapping.parquet``      - the practice mapping snapshot of every release
- ``pcdd_hierarchy.parquet``    - distinct Sub-ICB -> ICB -> region per release
- ``pcdd_series_breaks.parquet`` - where a series on an organisation or a measure is
                                  not comparable with its own past

Fails if any overlapping observation differs between releases.
"""

import sys
from pathlib import Path

import pandas as pd

from .aggregation import fill_missing_aggregates
from .mapping_loader import hierarchy, load_mapping
from .series_breaks import build_series_breaks
from .silver_loader import _assert_unique_key, build_silver, classify_file, resolve_latest_release, write_silver

PIPELINE_DIR = Path(__file__).resolve().parents[1]
RAW_ROOT = PIPELINE_DIR / "data" / "raw" / "pcdd"
SILVER_DIR = PIPELINE_DIR / "data" / "processed" / "silver"


def release_dirs(raw_root: Path, releases: list[str] | None) -> list[Path]:
    dirs = sorted(p for p in raw_root.iterdir() if p.is_dir())
    if releases is not None:
        missing = set(releases) - {p.name for p in dirs}
        if missing:
            raise ValueError(f"No raw folder for release(s) {sorted(missing)} under {raw_root}")
        dirs = [p for p in dirs if p.name in releases]
    return dirs


def build_mapping(raw_root: Path, releases: list[str] | None) -> pd.DataFrame:
    frames = []
    for release_dir in release_dirs(raw_root, releases):
        files = [p for p in release_dir.glob("*.csv") if classify_file(p.name) == "practice_mapping"]
        if len(files) != 1:
            raise ValueError(f"{release_dir.name}: expected one mapping file, found {[f.name for f in files]}")
        frames.append(load_mapping(files[0], release_dir.name))
    return pd.concat(frames, ignore_index=True)


def main(argv: list[str] | None = None, raw_root: Path = RAW_ROOT, out_dir: Path = SILVER_DIR) -> int:
    releases = (sys.argv[1:] if argv is None else argv) or None
    release_dirs(raw_root, releases)   # fail early on a mistyped release name
    ingested_at = pd.Timestamp.now()

    published = build_silver(raw_root, releases, ingested_at=ingested_at)
    mapping = build_mapping(raw_root, releases)
    hier = hierarchy(mapping)
    aggregates = fill_missing_aggregates(published, hier)
    silver = pd.concat([published, aggregates], ignore_index=True)
    _assert_unique_key(silver, "observations + aggregates")
    latest = resolve_latest_release(silver)
    breaks = build_series_breaks(published)

    out_dir.mkdir(parents=True, exist_ok=True)
    write_silver(silver, out_dir / "pcdd_observations.parquet")
    write_silver(latest, out_dir / "pcdd_latest.parquet")
    mapping.to_parquet(out_dir / "pcdd_mapping.parquet", index=False)
    hier.to_parquet(out_dir / "pcdd_hierarchy.parquet", index=False)
    breaks.to_parquet(out_dir / "pcdd_series_breaks.parquet", index=False)

    by_release = published.groupby("source_release").size().to_dict()
    print(f"silver: {len(published):,} loaded rows from {by_release} + {len(aggregates):,} computed "
          f"aggregates; latest-wins: {len(latest):,} rows; {len(breaks)} series breaks")
    print(f"mapping: {len(mapping):,} practice rows across {mapping['source_release'].nunique()} snapshots")
    print(f"written to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
