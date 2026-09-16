"""Boundaries from the ONS Open Geography Portal, checked against silver.

Uses the cached GeoJSON under data/raw/boundaries/ (fetched once by src.gold); skips
if a layer has not been fetched, so the suite never needs the network.
"""

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

PIPELINE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPELINE_DIR))

from src.boundaries import (  # noqa: E402
    BOUNDARY_LAYERS, cache_path, coverage, load_boundaries, nhs_boundary_version, ons_to_org_code,
)
from src.silver_loader import read_silver  # noqa: E402

SILVER = PIPELINE_DIR / "data" / "processed" / "silver" / "pcdd_observations.parquet"

EXPECTED = {   # (org_level, boundary_version) -> polygons == organisations
    ("sub_icb", "2026-04"): 106, ("sub_icb", "2023-04"): 106,
    ("icb", "2026-04"): 36, ("icb", "2023-04"): 42,
    ("nhs_region", "2024-01"): 7, ("ltla", "2026-05"): 296, ("utla", "2025-12"): 153, ("gor", "2025-12"): 9,
}


@pytest.fixture(scope="module")
def silver():
    if not SILVER.exists():
        pytest.skip("silver not built")
    return read_silver(SILVER)


@pytest.fixture(scope="module")
def boundaries(silver):
    missing = [s.layer for s in BOUNDARY_LAYERS if not cache_path(s.layer).exists()]
    if missing:
        pytest.skip(f"boundary layers not fetched: {missing}")
    return load_boundaries(silver, fetch=False)


def test_every_layer_resolves_completely_and_covers_its_organisations(boundaries, silver):
    counts = boundaries.groupby(["org_level", "boundary_version"]).size().to_dict()
    assert counts == EXPECTED
    cov = coverage(boundaries, silver).set_index(["org_level", "boundary_version"])
    assert (cov["covered"] == cov["organisations"]).all()
    assert (cov["polygons"] == cov["organisations"]).all()
    assert cov["missing"].map(len).sum() == 0


def test_era_a_icbs_and_frimley_are_in_the_2023_set_only(boundaries):
    icb = boundaries[boundaries["org_level"] == "icb"]
    assert "QNQ" in set(icb.loc[icb["boundary_version"] == "2023-04", "org_code"])
    assert "QNQ" not in set(icb.loc[icb["boundary_version"] == "2026-04", "org_code"])
    assert "S0E4D" in set(icb.loc[icb["boundary_version"] == "2026-04", "org_code"])
    sub = boundaries[boundaries["org_level"] == "sub_icb"]
    assert "D4U1Y" in set(sub.loc[sub["boundary_version"] == "2023-04", "org_code"])
    assert "U2G6B" in set(sub.loc[sub["boundary_version"] == "2026-04", "org_code"])
    # D9Y0V exists in both worlds under different ONS codes - the point of resolving via silver.
    d9 = sub[sub["org_code"] == "D9Y0V"].set_index("boundary_version")["ons_code"]
    assert len(d9) == 2 and d9["2023-04"] != d9["2026-04"]


def test_local_authority_codes_are_the_canonical_post_reissue_ones(boundaries):
    la = boundaries[boundaries["org_level"].isin(["ltla", "utla"])]
    assert {"E08000038", "E08000039"} <= set(la["org_code"])
    assert not ({"E08000016", "E08000019"} & set(la["org_code"]))
    assert la["ons_code"].str.startswith("E").all()          # UK layers filtered to England


def test_geometries_are_valid_geojson_in_wgs84(boundaries):
    sample = boundaries.groupby(["org_level", "boundary_version"]).head(2)
    for geojson in sample["geometry_geojson"]:
        g = json.loads(geojson)
        assert g["type"] in ("Polygon", "MultiPolygon")
        ring = g["coordinates"][0] if g["type"] == "Polygon" else g["coordinates"][0][0]
        lon, lat = ring[0]
        assert -7 < lon < 2.5 and 49.5 < lat < 56


def test_nhs_boundary_version_rule():
    assert nhs_boundary_version("2026-03") == "2023-04"
    assert nhs_boundary_version("2026-04") == "2026-04"
    assert nhs_boundary_version("2024-05") == "2023-04"


def test_ons_lookup_prefers_the_latest_release(silver):
    lookup = ons_to_org_code(silver)
    assert lookup[("country", "E92000001")] == "ENG"
    assert lookup[("sub_icb", "E38000247")] == "16C"
