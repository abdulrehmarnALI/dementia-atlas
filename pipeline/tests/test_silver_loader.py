"""Check the silver loader against the raw CSVs with plain pandas.

The loader is the first piece that composes everything else, so the checks here are
conservation checks - nothing lost, nothing invented - plus the cross-release
revision claim re-derived on the actual overlap between May 2025 and March 2026.
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

PIPELINE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPELINE_DIR))

from src.silver_loader import (  # noqa: E402
    LOADED_FAMILIES,
    OBSERVATION_KEY,
    build_silver,
    classify_file,
    find_revisions,
    load_file,
    load_release,
    overlapping_observations,
    read_silver,
    release_files,
    resolve_latest_release,
    write_silver,
)
from src.silver_schema import SILVER_COLUMNS, SILVER_KEY  # noqa: E402

RAW = PIPELINE_DIR / "data" / "raw" / "pcdd"
RELEASES = ["2025-05", "2026-03", "2026-06"]
INGESTED = pd.Timestamp("2026-09-16")


def read_raw(path: Path, **kw) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig", **kw)


@pytest.fixture(scope="module")
def silver():
    return build_silver(RAW, RELEASES, ingested_at=INGESTED)


# --------------------------------------------------------------------------------------
# Classification
# --------------------------------------------------------------------------------------

def test_every_raw_csv_is_classified_and_the_loaded_set_is_the_nine_analytical_families():
    for release in RELEASES:
        names = [p.name for p in (RAW / release).glob("*.csv")]
        assert all(classify_file(n) is not None for n in names), names
        loaded = {classify_file(p.name) for p in release_files(RAW / release)}
        assert loaded <= LOADED_FAMILIES
        if release == "2026-06":
            assert loaded == {"nhs_rate", "la_rate", "sub_icb_consolidated", "practice_measures"}
        else:
            assert len(loaded) == 9   # the Era-A practice files are classified but not loaded
            assert {classify_file(n) for n in names} >= {"practice_anti_psy", "practice_ass_plans", "practice_data_date"}
    assert classify_file("something-else.csv") is None


# --------------------------------------------------------------------------------------
# Conservation: raw rows in, silver rows out
# --------------------------------------------------------------------------------------

@pytest.mark.parametrize("release", RELEASES)
def test_published_rows_are_conserved_and_all_sex_rows_replaced_one_for_one(release):
    files = release_files(RAW / release)
    raw_rows = sum(len(read_raw(p, usecols=[0])) for p in files)
    published_all_sex = 0
    for p in files:
        if "age-sex" in p.name:
            published_all_sex = int(read_raw(p, usecols=["Measure"])["Measure"].str.startswith("ALL_AGED_").sum())
    out = load_release(RAW / release, release, INGESTED)
    published = out[~out["is_derived"]]
    derived = out[out["is_derived"]]
    assert len(published) == raw_rows - published_all_sex
    # Every published Female/Male pair yields exactly one derived row.
    pairs = published[(published["breakdown"] == "AGE_GENDER") & published["gender"].isin(["Female", "Male"])]
    assert len(derived) == len(pairs) // 2
    assert not out.duplicated(list(SILVER_KEY)).any()
    assert list(out.columns) == list(SILVER_COLUMNS)


def test_values_and_states_survive_the_load_untouched():
    path = RAW / "2026-03" / "pcdem-sicbl-res-type-mar-2026.csv"
    raw = read_raw(path)
    out = load_file(path, "2026-03", INGESTED)
    assert (out["value_raw"].to_numpy() == raw["Value"].to_numpy()).all()
    assert out["value_num"].sum() == pd.to_numeric(raw["Value"], errors="coerce").sum()
    assert (out["value_state"] == "suppressed").sum() == (raw["Value"] == "*").sum()
    assert set(out["residential_type"]) == set(raw["Measure"])
    assert (out["comparability"] == "labels_only").all()


def test_era_b_practice_file_loads_with_age_decoded_and_every_practice_mappable(silver):
    raw = read_raw(RAW / "2026-06" / "pcdem-practice-jun-2026.csv")
    rows = silver[silver["org_level"] == "practice"]
    assert len(rows) == len(raw) == 42616
    assert rows["org_code"].nunique() == raw["ODS_CODE"].nunique() == 6088
    assert rows["ons_code"].isna().all() and not rows["is_derived"].any()
    assert set(rows["measure"]) == {"DEMENTIA_REGISTER", "PAT_LIST", "REVIEWS"}
    def ages(breakdown):
        return set(rows.loc[rows["breakdown"] == breakdown, "age"])
    assert ages("DEMENTIA_REGISTER_0_64") == {"0_64"}
    assert ages("PAT_LIST_65_PLUS") == {"65_PLUS"}
    assert ages("DIAG_RECEIVED_CARE_PLAN") == {"ALL"}
    assert (rows["comparability"] == "era_b_only").all()
    # Practice history starts here: no practice rows from the Era-A releases.
    assert set(rows["source_release"]) == {"2026-06"}
    # Every measured practice is in the June mapping snapshot (the closed-practice
    # case the notebook found is in May 2025, which is out of scope).
    mapping = read_raw(RAW / "2026-06" / "mapping-file-july-dementia-2026.csv")
    assert set(rows["org_code"]) <= set(mapping["PRACTICE_CODE"])


def test_identity_normalisation_in_the_loaded_rows(silver):
    england = silver[silver["org_level"] == "country"]
    assert set(england["ons_code"]) == {"E92000001"}
    assert set(england["org_code"]) == {"ENG", "E92000001"}   # nhs/measure files vs la_rate
    # LTLA org_code is canonical across the reissue; ons_code keeps what was published.
    ltla = silver[(silver["org_level"] == "ltla") & (silver["source_release"] == "2026-03")]
    by_period = ltla.groupby("period_end")["org_code"].agg(set)
    assert len({frozenset(s) for s in by_period}) == 1
    assert ltla["ons_code"].nunique() == 298 and ltla["org_code"].nunique() == 296
    # Era B's PAT_LIST gender casing is gone.
    assert set(silver["gender"]) == {"Female", "Male", "ALL"}
    assert silver["comparability"].notna().all()


# --------------------------------------------------------------------------------------
# Across releases
# --------------------------------------------------------------------------------------

def test_may_2025_and_march_2026_overlap_and_never_disagree(silver):
    """The QA notebook's headline: 35,302 observations in the 3 overlapping months,
    100% identical. Re-derived here on the loaded frame, published rows only: the
    notebook's count includes the ALL_AGED rows silver drops (3 months x 106
    Sub-ICBs x 6 bands = 1,908), so the published overlap is 33,394."""
    published = silver[~silver["is_derived"]]
    dropped_all_sex = 3 * 106 * 6
    assert overlapping_observations(published) == 35302 - dropped_all_sex == 33394
    assert set(published[published.duplicated(list(OBSERVATION_KEY), keep=False)]["period_end"].dt.strftime("%Y-%m")) == {"2025-03", "2025-04", "2025-05"}
    assert find_revisions(silver).empty


def test_latest_release_wins_leaves_one_row_per_observation(silver):
    resolved = resolve_latest_release(silver)
    assert not resolved.duplicated(list(OBSERVATION_KEY)).any()
    assert len(resolved) == len(silver) - overlapping_observations(silver)
    overlap_keys = silver[silver.duplicated(list(OBSERVATION_KEY), keep=False)]
    winners = resolved.merge(overlap_keys[list(OBSERVATION_KEY)].drop_duplicates(), on=list(OBSERVATION_KEY))
    assert set(winners["source_release"]) == {"2026-03"}


def test_a_revision_is_detected():
    a = load_file(RAW / "2025-05" / "pcdem-nhs-rate-may-2025.csv", "2025-05", INGESTED)
    b = load_file(RAW / "2026-03" / "pcdem-nhs-rate-mar-2026.csv", "2026-03", INGESTED)
    assert find_revisions(pd.concat([a, b])).empty
    tampered = b.copy()
    idx = tampered.index[tampered["period_end"] == pd.Timestamp("2025-05-31")][0]
    tampered.loc[idx, "value_raw"] = "999999"
    revs = find_revisions(pd.concat([a, tampered]))
    assert len(revs) == 2 and set(revs["source_release"]) == {"2025-05", "2026-03"}


# --------------------------------------------------------------------------------------
# Storage
# --------------------------------------------------------------------------------------

def test_parquet_round_trip(silver, tmp_path):
    path = write_silver(silver, tmp_path / "silver" / "pcdd.parquet")
    back = read_silver(path)
    assert back.dtypes.astype(str).to_dict() == SILVER_COLUMNS
    assert len(back) == len(silver)
    pd.testing.assert_frame_equal(back, silver.reset_index(drop=True))
