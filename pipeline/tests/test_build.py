"""The build command end to end, into a temporary folder."""

import sys
from pathlib import Path

import pandas as pd
import pytest

PIPELINE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPELINE_DIR))

from src.build import RAW_ROOT, build_mapping, main, release_dirs  # noqa: E402
from src.mapping_loader import MAPPING_COLUMNS  # noqa: E402
from src.silver_loader import read_silver  # noqa: E402


def test_release_dirs_refuses_a_mistyped_release():
    assert [p.name for p in release_dirs(RAW_ROOT, None)] == ["2025-05", "2026-03", "2026-06"]
    assert [p.name for p in release_dirs(RAW_ROOT, ["2026-06"])] == ["2026-06"]
    with pytest.raises(ValueError, match="No raw folder"):
        release_dirs(RAW_ROOT, ["2026-6"])


def test_build_writes_the_four_parquet_files(tmp_path):
    assert main(["2026-06"], out_dir=tmp_path) == 0
    names = sorted(p.name for p in tmp_path.glob("*.parquet"))
    assert names == ["pcdd_hierarchy.parquet", "pcdd_latest.parquet", "pcdd_mapping.parquet",
                     "pcdd_observations.parquet"]
    observations = read_silver(tmp_path / "pcdd_observations.parquet")
    assert set(observations["source_release"]) == {"2026-06"}
    computed = observations[observations["source_file"].isna()]
    assert computed["is_derived"].all() and set(computed["org_level"]) == {"icb", "nhs_region", "country"}
    assert len(computed) > 1000
    mapping = pd.read_parquet(tmp_path / "pcdd_mapping.parquet")
    assert list(mapping.columns) == list(MAPPING_COLUMNS) and len(mapping) == 6182
    hier = pd.read_parquet(tmp_path / "pcdd_hierarchy.parquet")
    assert len(hier) == 106 and hier["icb_code"].nunique() == 36


def test_mapping_covers_every_release():
    mapping = build_mapping(RAW_ROOT, None)
    assert mapping.groupby("source_release").size().to_dict() == {"2025-05": 6215, "2026-03": 6169, "2026-06": 6182}
