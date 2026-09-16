"""Gold tables: integrity between them, and against silver and the raw files.

These tests build gold from the silver Parquet on disk, so run ``python -m src.build``
first (the fixture skips if it hasn't been run). The PostGIS load is exercised only
when DATABASE_URL is set.
"""

import os
import sys
from pathlib import Path

import pandas as pd
import pytest

PIPELINE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPELINE_DIR))

from src.gold import (  # noqa: E402
    GOLD_TABLES, RATE_MEASURES, SILVER_DIR, build_gold, measure_key, organisation_names,
)
from src.silver_loader import read_silver  # noqa: E402

RAW = PIPELINE_DIR / "data" / "raw" / "pcdd"


@pytest.fixture(scope="module")
def gold():
    if not (SILVER_DIR / "pcdd_observations.parquet").exists():
        pytest.skip("silver Parquet not built - run python -m src.build")
    try:
        return build_gold(fetch=False)   # cached boundaries and geocodes only; no network in tests
    except FileNotFoundError as e:
        pytest.skip(f"boundary / geocode cache not fetched yet: {e}")


@pytest.fixture(scope="module")
def latest():
    return read_silver(SILVER_DIR / "pcdd_latest.parquet")


def test_every_table_is_present_and_keyed(gold):
    assert set(gold) == set(GOLD_TABLES)
    assert not gold["organisation"].duplicated(["org_level", "org_code"]).any()
    assert not gold["measure"].duplicated("measure_key").any()
    assert not gold["period"].duplicated("period_end").any()
    assert not gold["observation"].duplicated(["period_end", "org_level", "org_code", "measure_key"]).any()
    assert not gold["diagnosis_rate"].duplicated(["period_end", "org_level", "org_code"]).any()


def test_referential_integrity(gold):
    obs, orgs, measures, periods = gold["observation"], gold["organisation"], gold["measure"], gold["period"]
    org_keys = set(zip(orgs["org_level"], orgs["org_code"]))
    assert set(zip(obs["org_level"], obs["org_code"])) <= org_keys
    assert set(obs["measure_key"]) <= set(measures["measure_key"])
    assert set(obs["period_end"]) <= set(periods["period_end"])
    rate = gold["diagnosis_rate"]
    assert set(zip(rate["org_level"], rate["org_code"])) <= org_keys
    parents = orgs.dropna(subset=["parent_org_code"])
    assert set(zip(parents["parent_org_level"], parents["parent_org_code"])) <= org_keys


def test_observation_is_latest_silver_with_one_england(gold, latest):
    obs = gold["observation"]
    # la_rate's England rows duplicate nhs_rate's (same five measures, same values), so
    # gold has exactly those rows fewer.
    la_england = latest[(latest["org_level"] == "country") & (latest["org_code"] == "E92000001")]
    assert len(obs) == len(latest) - len(la_england) and len(la_england) > 0
    assert obs["value"].sum() == pytest.approx(latest["value_num"].sum() - la_england["value_num"].sum())
    assert (obs["value_state"] == "minimum").sum() > 0
    assert obs["is_derived"].sum() == latest["is_derived"].sum()
    assert set(obs.loc[obs["org_level"] == "country", "org_code"]) == {"ENG"}
    assert (gold["organisation"]["org_level"] == "country").sum() == 1


def test_measure_keys_and_descriptions(gold):
    m = gold["measure"].set_index("measure_key")
    assert "DEMENTIA_REGISTER:AGE_GENDER:age=65_69:gender=Female" in m.index
    assert "DIAG_RATE_65_PLUS:N/A" in m.index and m.loc["DIAG_RATE_65_PLUS:N/A", "unit"] == "percent"
    assert m.loc["DEMENTIA_ESTIMATE_65_PLUS:N/A", "unit"] == "estimate"
    assert m.loc["INCIDENCE:N/A", "comparability"] == "not_comparable"
    assert m.loc["DEMENTIA_REGISTER:ETHNICITY:ethnicity=WHITE", "description"].startswith("Number of patients recorded on the QOF Dementia Register")
    assert "White" in m.loc["DEMENTIA_REGISTER:ETHNICITY:ethnicity=WHITE", "description"]
    assert m.loc["REVIEWS:DIAG_RECEIVED_CARE_PLAN", "description"].startswith("Number of patients")
    assert m.loc["PAT_LIST:PAT_LIST_65_PLUS:age=65_PLUS", "description"].startswith("Registered patients aged 65")
    assert m["description"].notna().all() and (m["is_additive"] == (m["unit"] == "count")).all()
    assert measure_key({"measure": "MCI", "breakdown": "AGE_GENDER", "age": "40_44", "gender": "Male",
                        "ethnicity": "ALL", "dementia_type": "ALL", "residential_type": "ALL"}) == "MCI:AGE_GENDER:age=40_44:gender=Male"


def test_organisations_have_names_parents_and_breaks(gold):
    orgs = gold["organisation"].set_index(["org_level", "org_code"])
    assert orgs.loc[("sub_icb", "00L"), "parent_org_code"] == "QHM"
    assert orgs.loc[("icb", "QHM"), "parent_org_level"] == "nhs_region"
    assert orgs.loc[("nhs_region", "Y63"), "parent_org_code"] == "ENG"
    assert orgs.loc[("sub_icb", "D4U1Y"), "series_break_from"] == "2026-04"
    assert orgs.loc[("sub_icb", "D9Y0V"), "series_break_from"] == "2026-04"
    assert not orgs.loc[("sub_icb", "D4U1Y"), "is_current"] and orgs.loc[("sub_icb", "U2G6B"), "is_current"]
    assert orgs.loc[("country", "ENG"), "name"] == "England"
    assert "Frimley" in orgs.loc[("sub_icb", "D4U1Y"), "name"]
    nhs = orgs[orgs.index.get_level_values("org_level").isin(["sub_icb", "icb", "nhs_region", "practice"])]
    assert nhs["name"].notna().all()
    la = orgs[orgs.index.get_level_values("org_level").isin(["ltla", "utla", "gor"])]
    assert la["name"].notna().all()
    # The reissued LTLA codes are canonical here too, so no pre-reissue code has a row.
    assert ("ltla", "E08000016") not in orgs.index and ("utla", "E08000016") not in orgs.index


def test_diagnosis_rate_matches_the_raw_june_file(gold):
    rate = gold["diagnosis_rate"]
    assert list(rate.columns) == ["period_end", "org_level", "org_code", *RATE_MEASURES.values(), "dq_flag"]
    raw = pd.read_csv(RAW / "2026-06" / "pcdem-nhs-rate-jun-2026.csv", dtype=str, keep_default_na=False)
    eng = raw[(raw["ORG_TYPE"] == "COUNTRY_RESPONSIBILITY")].set_index("MEASURE")["VALUE"].astype(float)
    row = rate[(rate["period_end"] == pd.Timestamp("2026-06-30")) & (rate["org_level"] == "country") & (rate["org_code"] == "ENG")].iloc[0]
    assert row["register_65_plus"] == eng["DEMENTIA_REGISTER_65_PLUS"]
    assert row["diag_rate"] == eng["DIAG_RATE_65_PLUS"]
    june = rate[rate["period_end"] == pd.Timestamp("2026-06-30")]
    assert june.groupby("org_level").size().to_dict() == {"country": 1, "gor": 9, "icb": 36, "ltla": 296, "nhs_region": 7, "sub_icb": 106, "utla": 153}
    assert june["dq_flag"].sum() > 0 and set(june.loc[june["dq_flag"], "org_level"]) <= {"ltla", "utla"}


def test_geometry_covers_every_level_and_every_current_organisation(gold):
    geo, orgs, periods = gold["geometry"], gold["organisation"], gold["period"]
    assert geo["org_code"].notna().all() and geo["geometry_geojson"].str.startswith('{"type":"').all()
    assert set(zip(geo["org_level"], geo["org_code"])) <= set(zip(orgs["org_level"], orgs["org_code"]))
    current = orgs[orgs["is_current"] & orgs["org_level"].isin(["sub_icb", "icb", "nhs_region", "ltla", "utla", "gor"])]
    latest_version = {"sub_icb": "2026-04", "icb": "2026-04"}
    for level, group in current.groupby("org_level"):
        polys = geo[(geo["org_level"] == level)]
        if level in latest_version:
            polys = polys[polys["boundary_version"] == latest_version[level]]
        assert set(group["org_code"]) <= set(polys["org_code"]), level
    # The period table says which NHS boundary set to draw each period on.
    assert set(periods.loc[periods["period"] <= "2026-03", "boundary_version_nhs"]) == {"2023-04"}
    assert set(periods.loc[periods["period"] >= "2026-04", "boundary_version_nhs"]) == {"2026-04"}
    assert set(periods["boundary_version_nhs"]) <= set(geo.loc[geo["org_level"] == "icb", "boundary_version"])


def test_practice_locations_line_up_with_practice_observations(gold):
    loc = gold["practice_location"]
    practices = gold["organisation"][gold["organisation"]["org_level"] == "practice"]
    assert set(practices["org_code"]) <= set(loc["practice_code"])
    june = loc[loc["source_release"] == "2026-06"]
    assert june["lat"].notna().mean() > 0.999
    assert not loc["practice_code"].duplicated().any()


@pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set")
def test_postgis_load_round_trip(gold, tmp_path):
    from src.gold import write_gold
    from src.load_postgis import load
    import psycopg
    write_gold(gold, tmp_path)
    counts = load(os.environ["DATABASE_URL"], tmp_path)
    assert counts["observation"] == len(gold["observation"])
    by_lv = counts["geometry_by_level_version"]
    assert by_lv["sub_icb@2026-04"] == 106 and by_lv["sub_icb@2023-04"] == 106
    assert by_lv["icb@2026-04"] == 36 and by_lv["icb@2023-04"] == 42
    assert by_lv["ltla@2026-05"] == 296 and by_lv["utla@2025-12"] == 153 and by_lv["gor@2025-12"] == 9
    assert counts["practice_points"] > 0.999 * (gold["practice_location"]["lat"].notna().sum())
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        invalid = conn.execute("SELECT count(*) FROM gold.geometry WHERE NOT ST_IsValid(geom) OR geom_web IS NULL").fetchone()[0]
        assert invalid == 0
        shrink = conn.execute("SELECT sum(ST_NPoints(geom_web))::float / sum(ST_NPoints(geom)) FROM gold.geometry").fetchone()[0]
        assert shrink < 0.5
        n = conn.execute("SELECT count(*) FROM gold.observation o JOIN gold.geometry g "
                         "ON g.org_level = o.org_level AND g.org_code = o.org_code WHERE o.value_state = 'minimum'").fetchone()[0]
        assert n > 0
        # A period-aware join: Era-A ICB rows land on the 2023 outlines, Era-B on 2026.
        rows = conn.execute("""
            SELECT p.boundary_version_nhs, count(DISTINCT r.org_code)
            FROM gold.diagnosis_rate r JOIN gold.period p USING (period_end)
            JOIN gold.geometry g ON g.org_level = r.org_level AND g.org_code = r.org_code
                                 AND g.boundary_version = p.boundary_version_nhs
            WHERE r.org_level = 'icb' GROUP BY 1 ORDER BY 1""").fetchall()
        assert dict(rows) == {"2023-04": 42, "2026-04": 36}
        eng = conn.execute("SELECT diag_rate FROM gold.diagnosis_rate WHERE org_level='country' AND org_code='ENG' "
                           "ORDER BY period_end DESC LIMIT 1").fetchone()[0]
        assert 60 < eng < 80
