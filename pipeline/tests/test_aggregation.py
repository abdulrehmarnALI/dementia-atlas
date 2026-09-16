"""Hierarchy aggregation, validated against what Era A published.

``tests/test_aggregation_evidence.py`` established the rule with plain pandas; this
file checks that the aggregation module reproduces it, that bounds behave, and
that only the missing levels get filled.
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

PIPELINE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPELINE_DIR))

from src.aggregation import aggregate_sub_icbs, compare_to_published, fill_missing_aggregates  # noqa: E402
from src.build import build_mapping  # noqa: E402
from src.mapping_loader import hierarchy  # noqa: E402
from src.silver_loader import OBSERVATION_KEY, build_silver  # noqa: E402
from src.silver_schema import MINIMUM, NUMERIC, SILVER_COLUMNS  # noqa: E402

RAW = PIPELINE_DIR / "data" / "raw" / "pcdd"
INGESTED = pd.Timestamp("2026-09-16")
REGISTER_MEASURES = {"DEMENTIA_REGISTER", "PAT_LIST", "DEMENTIA_REGISTER_65_PLUS", "DEMENTIA_ESTIMATE_65_PLUS"}


@pytest.fixture(scope="module")
def silver():
    return build_silver(RAW, ["2025-05", "2026-03", "2026-06"], ingested_at=INGESTED)


@pytest.fixture(scope="module")
def hier():
    return hierarchy(build_mapping(RAW, None))


@pytest.fixture(scope="module")
def comparison(silver, hier):
    return compare_to_published(silver, hier)


def test_register_measures_reproduce_published_aggregates_exactly(comparison):
    reg = comparison[comparison["measure"].isin(REGISTER_MEASURES) & (comparison["computed_state"] == NUMERIC)]
    assert len(reg) > 1000
    assert set(reg["org_level"]) == {"icb", "nhs_region", "country"}
    counts = reg[reg["measure"] != "DEMENTIA_ESTIMATE_65_PLUS"]
    assert (counts["computed"] == counts["published"]).all()
    # Estimates are published to 1 dp, so summing up to 106 of them can drift by a
    # few tenths (observed max 0.7 at England level).
    estimates = reg[reg["measure"] == "DEMENTIA_ESTIMATE_65_PLUS"]
    assert ((estimates["computed"] - estimates["published"]).abs() <= 1.0).all()


def test_other_measures_stay_within_the_pinned_noise(comparison):
    other = comparison[~comparison["measure"].isin(REGISTER_MEASURES) & (comparison["computed_state"] == NUMERIC)
                       & (comparison["published_state"] == NUMERIC)]
    gap = other["published"] - other["computed"]
    assert gap.abs().max() <= 41           # England-level MCI, the worst case in the evidence tests
    assert abs(gap.mean()) < 0.5


def test_bounds_arithmetic_against_published_where_inputs_were_suppressed(comparison):
    """Only MCI has suppressed Sub-ICB inputs in Era A, so it is the only place the
    bounds can be held up against a published figure. The arithmetic holds
    (lower = sum of numerics, upper = lower + 4 per suppressed cell, computed =
    lower), but containment is only ~49%: MCI's published aggregates carry the
    same +/- publisher noise as its suppression-free groups (see
    test_aggregation_evidence), and that noise (up to 41 at England level) is
    wider than the bounds themselves (typically 4-8). So the check is: published
    never sits further outside [lower, upper] than that noise."""
    mins = comparison[comparison["computed_state"] == MINIMUM]
    assert len(mins) > 1000 and set(mins["measure"]) == {"MCI"}
    assert (mins["lower"] <= mins["upper"]).all()
    assert (mins["computed"] == mins["lower"]).all()
    assert ((mins["upper"] - mins["lower"]) % 4 == 0).all()   # 4 x number of suppressed inputs
    inside = (mins["published"] >= mins["lower"]) & (mins["published"] <= mins["upper"])
    excursion = pd.concat([mins["lower"] - mins["published"], mins["published"] - mins["upper"]], axis=1).max(axis=1).clip(lower=0)
    assert 0.4 < inside.mean() < 0.6
    assert excursion.max() <= 41 and excursion.quantile(0.95) <= 11


def test_fill_missing_only_adds_what_was_not_published(silver, hier):
    filled = fill_missing_aggregates(silver, hier)
    key = ["source_release", *OBSERVATION_KEY]
    published = silver.loc[~silver["is_derived"], key]
    assert filled.merge(published, on=key).empty
    assert filled["is_derived"].all() and filled["source_file"].isna().all()
    assert list(filled.columns) == list(SILVER_COLUMNS)
    # Era B: everything but the rate file needs computing; Era A: the four
    # Sub-ICB-only category files (ethnicity, dementia type, residence, age/sex).
    era_b = filled[filled["source_release"] == "2026-06"]
    assert set(era_b["measure"]) >= {"DEMENTIA_REGISTER", "MCI", "INCIDENCE", "FRAILTY", "PRESCRIBING"}
    assert "DEMENTIA_ESTIMATE_65_PLUS" not in set(era_b["measure"])
    era_a = filled[filled["source_release"] == "2026-03"]
    assert set(era_a["breakdown"]) == {"AGE_GENDER", "ETHNICITY", "DEMENTIA_TYPE", "RESIDENCE_TYPE"}
    # Every derived all-sex row at Sub-ICB level has its aggregate too.
    assert (era_b[(era_b["breakdown"] == "AGE_GENDER")]["gender"] == "ALL").any()
    # No duplicate keys inside the computed set.
    assert not filled.duplicated(key).any()


def test_unmapped_sub_icb_is_an_error(silver, hier):
    broken = hier[~((hier["source_release"] == "2026-06") & (hier["sub_icb_code"] == "00L"))]
    with pytest.raises(ValueError, match="no hierarchy entry"):
        aggregate_sub_icbs(silver[silver["source_release"] == "2026-06"], broken)
