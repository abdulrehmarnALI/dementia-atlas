"""Re-derive the derived-row claims from the raw March 2026 age/sex file with plain pandas.

The module under test drops Era A's published ``ALL_AGED_*`` rows and recomputes
them as Female + Male. The evidence that this loses nothing is re-established here
directly from the raw file - the decode is done with a regex in this test, not via
the crosswalk, and the published totals are compared cell by cell. The vectorised
``sum_groups`` is also checked against the scalar ``sum_with_state`` specification.
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

PIPELINE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPELINE_DIR))

from src.derived_rows import (  # noqa: E402
    GROUP_COLUMNS,
    derive_all_sex_rows,
    drop_published_all_sex_rows,
    sum_groups,
    sum_with_state,
)
from src.silver_schema import (  # noqa: E402
    BLANK, MINIMUM, NOT_APPLICABLE, NUMERIC, SILVER_COLUMNS, SUPPRESSED, conform,
)

RAW = PIPELINE_DIR / "data" / "raw" / "pcdd"


def silver_like(rows: pd.DataFrame, **fixed) -> pd.DataFrame:
    """Fill a partial frame out to the full silver shape with constant provenance and
    bounds derived from value_num / value_state the way classify_values does."""
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
        if col not in out.columns and col in defaults:
            out[col] = defaults[col]
    if "value_num_lower" not in out.columns:
        suppressed = out["value_state"] == SUPPRESSED
        out["value_num_lower"] = out["value_num"].where(~suppressed, 0.0)
        out["value_num_upper"] = out["value_num"].where(~suppressed, 4.0)
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
    assert (derived["value_num_lower"] == derived["value_num"]).all()
    assert (derived["value_num_upper"] == derived["value_num"]).all()
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


def test_suppressed_input_gives_a_minimum_with_exact_bounds():
    frame = silver_like(pd.DataFrame({
        "period_end": [pd.Timestamp("2026-03-31")] * 6,
        "org_code": ["00L", "00L", "00N", "00N", "00P", "00P"],
        "age": ["65_69"] * 6,
        "gender": ["Female", "Male"] * 3,
        "value_raw": ["*", "10", "7", "8", "", "9"],
        "value_num": [float("nan"), 10.0, 7.0, 8.0, float("nan"), 9.0],
        "value_state": [SUPPRESSED, NUMERIC, NUMERIC, NUMERIC, BLANK, NUMERIC],
    }))
    derived = derive_all_sex_rows(frame).set_index("org_code")
    # * + 10: the true total is 10..14, published as a minimum of 10.
    assert derived.loc["00L", "value_state"] == MINIMUM
    assert derived.loc["00L", "value_num"] == 10.0
    assert (derived.loc["00L", "value_num_lower"], derived.loc["00L", "value_num_upper"]) == (10.0, 14.0)
    # 7 + 8: exact.
    assert derived.loc["00N", "value_state"] == NUMERIC and derived.loc["00N", "value_num"] == 15.0
    # blank + 9: nothing can be said.
    assert derived.loc["00P", "value_state"] == BLANK
    assert derived.loc["00P", ["value_num", "value_num_lower", "value_num_upper"]].isna().all()


def test_sum_with_state_specification():
    def values(*pairs):
        num = [v for v, _ in pairs]
        state = [s for _, s in pairs]
        return silver_like(pd.DataFrame({
            "period_end": pd.Timestamp("2026-03-31"), "org_code": "X", "age": "65_69",
            "gender": ["Female"] * len(pairs), "value_num": num, "value_state": state,
        }))[["value_num", "value_state", "value_num_lower", "value_num_upper"]]

    assert sum_with_state(values((1.0, NUMERIC), (2.0, NUMERIC))) == {
        "value_num": 3.0, "value_state": NUMERIC, "value_num_lower": 3.0, "value_num_upper": 3.0}
    r = sum_with_state(values((1.0, NUMERIC), (float("nan"), SUPPRESSED), (float("nan"), SUPPRESSED)))
    assert r == {"value_num": 1.0, "value_state": MINIMUM, "value_num_lower": 1.0, "value_num_upper": 9.0}
    for state in (BLANK, NOT_APPLICABLE):
        r = sum_with_state(values((1.0, NUMERIC), (float("nan"), state)))
        assert r["value_state"] == BLANK and pd.isna(r["value_num"]) and pd.isna(r["value_num_upper"])
    # A minimum feeding a further sum carries its bounds, not its lower bound twice.
    minimum = values((5.0, MINIMUM))
    minimum["value_num_upper"] = 9.0
    r = sum_with_state(pd.concat([minimum, values((1.0, NUMERIC))]))
    assert r == {"value_num": 6.0, "value_state": MINIMUM, "value_num_lower": 6.0, "value_num_upper": 10.0}


def test_vectorised_sum_groups_matches_sum_with_state_group_by_group(age_sex_march):
    """The scalar rule is the spec; the vectorised form must agree with it on real
    data plus injected suppressed and blank cells."""
    frame = age_sex_march[age_sex_march["gender"] != "ALL"].head(4000).copy()
    frame.loc[frame.index[::7], ["value_num", "value_state", "value_num_lower", "value_num_upper"]] = \
        [float("nan"), SUPPRESSED, 0.0, 4.0]
    frame.loc[frame.index[::23], ["value_num", "value_state", "value_num_lower", "value_num_upper"]] = \
        [float("nan"), BLANK, float("nan"), float("nan")]

    vectorised = sum_groups(frame, GROUP_COLUMNS).set_index(GROUP_COLUMNS)
    checked = 0
    for key, group in frame.groupby(GROUP_COLUMNS, dropna=False, sort=False):
        expected = sum_with_state(group)
        got = vectorised.loc[key]
        assert got["value_state"] == expected["value_state"], key
        for col in ("value_num", "value_num_lower", "value_num_upper"):
            assert (pd.isna(got[col]) and pd.isna(expected[col])) or got[col] == expected[col], (key, col)
        checked += 1
    assert checked == len(vectorised) > 1000
