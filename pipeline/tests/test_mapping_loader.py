"""Check the mapping-snapshot loader against the raw files with plain pandas."""

import sys
from pathlib import Path

import pandas as pd
import pytest

PIPELINE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPELINE_DIR))

from src.mapping_loader import MAPPING_COLUMNS, hierarchy, load_mapping  # noqa: E402

RAW = PIPELINE_DIR / "data" / "raw" / "pcdd"
FILES = {
    "2025-05": "gp-reg-pat-prac-map-06-2025.csv",
    "2026-03": "gp-reg-pat-prac-map-03-2026.csv",
    "2026-06": "mapping-file-july-dementia-2026.csv",
}


def read_raw(release):
    return pd.read_csv(RAW / release / FILES[release], dtype=str, keep_default_na=False, encoding="utf-8-sig")


@pytest.fixture(scope="module")
def snapshots():
    return {rel: load_mapping(RAW / rel / f, rel) for rel, f in FILES.items()}


@pytest.mark.parametrize("release", list(FILES))
def test_rows_and_practices_are_conserved(snapshots, release):
    raw = read_raw(release)
    out = snapshots[release]
    assert len(out) == len(raw)
    assert set(out["practice_code"]) == set(raw["PRACTICE_CODE"])
    assert list(out.columns) == list(MAPPING_COLUMNS)
    assert out.dtypes.astype(str).to_dict() == MAPPING_COLUMNS


def test_snapshot_sizes_and_extract_dates_match_the_notebook(snapshots):
    expected = {"2025-05": (6215, "2025-06-01"), "2026-03": (6169, "2026-03-01"), "2026-06": (6182, "2026-07-01")}
    for rel, (n, date) in expected.items():
        assert len(snapshots[rel]) == n
        assert set(snapshots[rel]["extract_date"]) == {pd.Timestamp(date)}


def test_june_null_sentinel_becomes_unmapped_not_nan(snapshots):
    raw = read_raw("2026-06")
    null_rows = raw[(raw[["SUB_ICB_LOCATION_CODE", "ICB_CODE", "COMM_REGION_CODE"]] == "NULL").all(axis=1)]
    assert len(null_rows) == 1
    out = snapshots["2026-06"]
    unmapped = out[out["unmapped"]]
    assert set(unmapped["practice_code"]) == set(null_rows["PRACTICE_CODE"])
    assert unmapped[["sub_icb_code", "icb_code", "region_code"]].isna().all().all()
    assert not out.loc[~out["unmapped"], ["sub_icb_code", "icb_code", "region_code"]].isna().any().any()
    for rel in ("2025-05", "2026-03"):
        assert not snapshots[rel]["unmapped"].any()


def test_era_only_columns_are_null_where_not_published(snapshots):
    assert snapshots["2026-06"][["pcn_code", "pcn_name", "supplier_name"]].isna().all().all()
    for rel in ("2025-05", "2026-03"):
        assert snapshots[rel]["pcn_code"].notna().all()
        assert snapshots[rel]["supplier_name"].notna().all()


def test_names_are_stripped_and_codes_are_not_touched(snapshots):
    raw = read_raw("2025-05")
    assert (raw["ICB_NAME"] != raw["ICB_NAME"].str.strip()).any()   # the defect the strip exists for
    out = snapshots["2025-05"]
    assert (out["icb_name"] == out["icb_name"].str.strip()).all()
    assert (out["icb_code"].to_numpy() == raw["ICB_CODE"].to_numpy()).all()


def test_hierarchy_counts_either_side_of_the_reorganisation(snapshots):
    for rel, (subs, icbs, regions) in {"2025-05": (106, 42, 7), "2026-03": (106, 42, 7), "2026-06": (106, 36, 7)}.items():
        h = hierarchy(snapshots[rel])
        assert h["sub_icb_code"].nunique() == subs
        assert h["icb_code"].nunique() == icbs
        assert h["region_code"].nunique() == regions
        assert len(h) == subs   # one parent chain per Sub-ICB


def test_hierarchy_rejects_an_inconsistent_snapshot(snapshots):
    bad = snapshots["2026-06"].copy()
    idx = bad.index[bad["sub_icb_code"] == "00L"][0]
    bad.loc[idx, "icb_code"] = "QHM_OTHER"
    with pytest.raises(ValueError, match="more than one parent"):
        hierarchy(bad)
