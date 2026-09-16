"""Re-derive the derived-row claims from the raw March 2026 age/sex file with plain pandas.

The module under test drops Era A's published ``ALL_AGED_*`` rows and recomputes
them as Female + Male. The evidence that this loses nothing is re-established here
directly from the raw file - the decode is done with a regex in this test, not via
the crosswalk, and the published totals are compared cell by cell.
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

PIPELINE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPELINE_DIR))

from src.derived_rows import (  # noqa: E402
    derive_all_sex_rows,
    drop_published_all_sex_rows,
    sum_with_state,
)
from src.silver_schema import BLANK, NUMERIC, SILVER_COLUMNS, SUPPRESSED, conform  # noqa: E402

RAW = PIPELINE_DIR / "data" / "raw" / "pcdd"


def silver_like(rows: pd.DataFrame, **fixed) -> pd.DataFrame:
    """Fill a partial frame out to the full silver shape with constant provenance."""
    defaults = {
        "source_release": "2026-03", "source_file": "test", "publication_era": "A",
        "dictionary_version": "PCDD-2526", "ingested_at": pd.Timestamp("2026-09-16"),
        "org_level": "sub_icb", "ons_code": pd.NA, "measure": "DEMENTIA_REGISTER",
        "breakdown": "AGE_GENDER", "ethnicity": "ALL", "dementia_type": "ALL",
        "residential_type": "ALL", "value_raw": pd.NA, "dq_flag": False,
        "is_derived": False, "comparability": "comparable",
    }
    defaults.update(fixed)
    out = rows.copy()
    for col in SILVER_COLUMNS:
        if col not in out.columns:
            out[col] = defaults[col]
    return conform(out)


@pytest.fixture(scope="module")
def age_sex_march():
    """Raw March 2026 age/sex file decoded into a silver-shaped frame with pandas only."""
    raw = pd.read_csv(RAW / "2026-03" / "pcdem-sicbl-age-sex-mar-2026.csv", dtype=str,
                      keep_default_na=False, encoding="utf-8-sig")
    parts = raw["Measure"].str.extract(r"^(?P<sex>ALL|FEMALE|MALE)_AGED_(?P<band>.+)$")
    frame = pd.DataFrame({
        "period_end": pd.to_datetime(raw["ACH_DATE"], format="%d-%b-%y"),
        "org_code": raw["SUB_ICB_ODS_CODE"],
        "age": parts["band"],
        "gender": parts["sex"].map({"ALL": "ALL", "FEMALE": "Female", "MALE": "Male"}),
        "value_raw": raw["Value"],
        "value_num": pd.to_numeric(raw["Value"]),
        "value_state": NUMERIC,
    })
    return silver_like(frame)


def test_published_all_sex_rows_are_exactly_female_plus_male(age_sex_march):
    published = age_sex_march[age_sex_march["gender"] == "ALL"]
    assert len(published) == 8268    # 13 periods x 106 Sub-ICBs x 6 bands

    derived = derive_all_sex_rows(age_sex_march)
    key = ["period_end", "org_code", "age"]
    joined = published.set_index(key)["value_num"].to_frame("published").join(
        derived.set_index(key)["value_num"].rename("derived"), how="outer")
    assert joined.notna().all().all(), "every published total has a derived partner and vice versa"
    assert (joined["published"] == joined["derived"]).all()
    assert derived["is_derived"].all() and (derived["value_state"] == NUMERIC).all()
    assert derived["value_raw"].isna().all()


def test_drop_removes_only_the_published_totals(age_sex_march):
    kept = drop_published_all_sex_rows(age_sex_march)
    assert len(age_sex_march) - len(kept) == 8268
    assert not (kept["gender"] == "ALL").any()
    # A derived ALL row is not a published one and survives a second drop.
    rebuilt = pd.concat([kept, derive_all_sex_rows(kept)], ignore_index=True)
    assert len(drop_published_all_sex_rows(rebuilt)) == len(rebuilt)


def test_derivation_needs_both_sexes():
    only_female = silver_like(pd.DataFrame({
        "period_end": [pd.Timestamp("2026-03-31")], "org_code": ["00L"], "age": ["65_69"],
        "gender": ["Female"], "value_num": [10.0], "value_state": [NUMERIC],
    }))
    assert derive_all_sex_rows(only_female).empty


def test_suppression_propagates_into_the_derived_total():
    frame = silver_like(pd.DataFrame({
        "period_end": [pd.Timestamp("2026-03-31")] * 4,
        "org_code": ["00L", "00L", "00N", "00N"],
        "age": ["65_69"] * 4,
        "gender": ["Female", "Male", "Female", "Male"],
        "value_raw": ["*", "10", "7", "8"],
        "value_num": [float("nan"), 10.0, 7.0, 8.0],
        "value_state": [SUPPRESSED, NUMERIC, NUMERIC, NUMERIC],
    }))
    derived = derive_all_sex_rows(frame).set_index("org_code")
    assert derived.loc["00L", "value_state"] == SUPPRESSED and pd.isna(derived.loc["00L", "value_num"])
    assert derived.loc["00N", "value_state"] == NUMERIC and derived.loc["00N", "value_num"] == 15.0


def test_sum_with_state_priority():
    assert sum_with_state(pd.Series([1.0, 2.0]), pd.Series([NUMERIC, NUMERIC])) == (3.0, NUMERIC)
    num, state = sum_with_state(pd.Series([1.0, float("nan")]), pd.Series([NUMERIC, BLANK]))
    assert pd.isna(num) and state == BLANK
    num, state = sum_with_state(pd.Series([float("nan"), float("nan")]), pd.Series([BLANK, SUPPRESSED]))
    assert pd.isna(num) and state == SUPPRESSED
