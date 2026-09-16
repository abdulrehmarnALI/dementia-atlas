"""Practice geocoding: cache behaviour without the network, coverage with the cache."""

import sys
from pathlib import Path

import pandas as pd
import pytest

PIPELINE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPELINE_DIR))

from src.geocode import CACHE, geocode_postcodes, normalise_postcode, practice_locations  # noqa: E402

MAPPING = PIPELINE_DIR / "data" / "processed" / "silver" / "pcdd_mapping.parquet"


def test_normalise_postcode():
    assert normalise_postcode(" ts18  1hu ") == "TS18 1HU"
    assert normalise_postcode("SE152UA") == "SE152UA"      # no reformatting, only case and spacing


def test_uncached_postcode_without_network_is_absent_not_fabricated(tmp_path):
    empty_cache = tmp_path / "postcodes.parquet"
    out = geocode_postcodes(["TS18 1HU"], cache_path=empty_cache, fetch=False)
    assert out.empty and not empty_cache.exists()


def test_cache_is_used_and_covers_the_practices():
    if not (CACHE.exists() and MAPPING.exists()):
        pytest.skip("geocode cache or mapping not built")
    mapping = pd.read_parquet(MAPPING)
    coords = geocode_postcodes(mapping["practice_postcode"], fetch=False)   # no network
    assert len(coords) == mapping["practice_postcode"].map(normalise_postcode).nunique()
    assert coords["lat"].notna().mean() > 0.995
    located = coords.dropna(subset=["lat"])
    assert located["lat"].between(49.8, 56).all() and located["lon"].between(-6.5, 2).all()

    loc = practice_locations(mapping, fetch=False)
    assert not loc["practice_code"].duplicated().any()
    assert len(loc) == mapping["practice_code"].nunique()
    june = loc[loc["source_release"] == "2026-06"]
    assert len(june) == 6182 and june["lat"].notna().mean() > 0.999
    assert loc.loc[loc["practice_code"] == "A81001", "postcode"].iloc[0] == "TS18 1HU"
