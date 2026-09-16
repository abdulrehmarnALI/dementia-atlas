"""Hierarchy aggregation: Sub-ICB observations -> ICB, NHS region, England.

Era B publishes its Sub-ICB measures at Sub-ICB level only, so the higher levels
have to be computed. Era A published all four levels, which is where the rule was
checked (``tests/test_aggregation_evidence.py``, ``docs/aggregation_error_era_a.md``):
summing Sub-ICBs reproduces the published figure exactly for register / list-size
measures and to within small publisher-side noise for the rest.

Every aggregate uses the one summing rule in ``derived_rows`` (``sum_groups``): a
group with no suppressed inputs is exact; a group with suppressed inputs is
published as its lower bound with state ``minimum`` and the upper bound carried
(each suppressed cell hides 0..4, so the bounds are exact, not estimates); a group
with a blank input is blank. Aggregates are silver rows with ``is_derived = True``
and no ``source_file`` - the app should treat them as computed, never as published.
"""

import pandas as pd

from .derived_rows import GROUP_COLUMNS, sum_groups
from .org_crosswalk import ENGLAND_ODS_CODE, ENGLAND_ONS_CODE
from .silver_loader import OBSERVATION_KEY
from .silver_schema import SILVER_COLUMNS, conform

SOURCE_LEVEL = "sub_icb"

# Ratios cannot be summed. The diagnosis rate and its confidence limits are published
# at every level in every release anyway; if they ever need computing it is
# register / estimate * 100, not a sum, and belongs in a separate step.
NON_ADDITIVE_MEASURES = frozenset({"DIAG_RATE_65_PLUS", "DIAG_RATE_65_PLUS_LL", "DIAG_RATE_65_PLUS_UL"})

# target org_level -> (hierarchy code column, hierarchy ONS-code column)
AGGREGATE_LEVELS: dict[str, tuple[str, str]] = {
    "icb": ("icb_code", "icb_ons_code"),
    "nhs_region": ("region_code", "region_ons_code"),
    "country": ("country_code", "country_ons_code"),
}

# What identifies an aggregate: the derived-row grouping minus the organisation
# columns (which the aggregate replaces) and source_file (many files feed one
# aggregate), plus gender (a grain column here, unlike in all-sex derivation).
AGGREGATE_GROUP = [c for c in GROUP_COLUMNS if c not in ("org_level", "org_code", "ons_code", "source_file")] + ["gender"]


def _hierarchy_with_country(hierarchy: pd.DataFrame) -> pd.DataFrame:
    h = hierarchy.copy()
    h["country_code"] = ENGLAND_ODS_CODE
    h["country_ons_code"] = ENGLAND_ONS_CODE
    for col in ("icb_ons_code", "region_ons_code"):
        if col not in h.columns:
            h[col] = pd.NA
    return h


def aggregate_sub_icbs(df: pd.DataFrame, hierarchy: pd.DataFrame,
                       levels: tuple[str, ...] = tuple(AGGREGATE_LEVELS)) -> pd.DataFrame:
    """Compute every ICB / region / England aggregate the Sub-ICB rows in ``df``
    support, whether or not the publisher also published it.

    ``hierarchy`` is one row per (source_release, sub_icb_code) with icb_code and
    region_code (from ``mapping_loader.hierarchy``). Every Sub-ICB in ``df`` must be
    in it for its release - an unmapped Sub-ICB would silently shrink a total.
    """
    subs = df[(df["org_level"] == SOURCE_LEVEL) & ~df["measure"].isin(NON_ADDITIVE_MEASURES)]
    if subs.empty:
        return df.iloc[0:0].copy()
    h = _hierarchy_with_country(hierarchy)
    joined = subs.merge(h, left_on=["source_release", "org_code"],
                        right_on=["source_release", "sub_icb_code"], how="left", indicator=True)
    unmapped = joined.loc[joined["_merge"] == "left_only", ["source_release", "org_code"]].drop_duplicates()
    if not unmapped.empty:
        raise ValueError(f"Sub-ICBs with no hierarchy entry for their release: {unmapped.to_dict('records')[:5]}")

    frames = []
    for level in levels:
        code_col, ons_col = AGGREGATE_LEVELS[level]
        agg = sum_groups(joined, AGGREGATE_GROUP + [code_col], extra={
            "ons_code": (ons_col, "first"), "ingested_at": ("ingested_at", "first")})
        agg = agg.rename(columns={code_col: "org_code"})
        agg["org_level"] = level
        frames.append(agg)
    out = pd.concat(frames, ignore_index=True)
    out["source_file"] = pd.NA
    out["value_raw"] = pd.NA
    out["dq_flag"] = False
    out["is_derived"] = True
    out = out.drop(columns=["n"])
    return conform(out[list(SILVER_COLUMNS)])


def fill_missing_aggregates(df: pd.DataFrame, hierarchy: pd.DataFrame) -> pd.DataFrame:
    """The aggregates NHS England did *not* publish: computed rows whose observation
    key (release, period, organisation, measure, breakdown, dimensions) has no
    published row in ``df``."""
    computed = aggregate_sub_icbs(df, hierarchy)
    key = ["source_release", *OBSERVATION_KEY]
    published = df.loc[~df["is_derived"].astype(bool), key].drop_duplicates()
    merged = computed.merge(published, on=key, how="left", indicator=True)
    return conform(merged[merged["_merge"] == "left_only"].drop(columns=["_merge"]).reset_index(drop=True))


def compare_to_published(df: pd.DataFrame, hierarchy: pd.DataFrame) -> pd.DataFrame:
    """For validation: every computed aggregate that has a published counterpart,
    side by side. Columns: the observation key, ``published`` (value_num),
    ``published_state``, ``computed``, ``computed_state``, ``lower``, ``upper``."""
    computed = aggregate_sub_icbs(df, hierarchy)
    key = ["source_release", *OBSERVATION_KEY]
    published = df[~df["is_derived"].astype(bool)][key + ["value_num", "value_state"]].rename(
        columns={"value_num": "published", "value_state": "published_state"})
    both = computed[key + ["value_num", "value_state", "value_num_lower", "value_num_upper"]].rename(
        columns={"value_num": "computed", "value_state": "computed_state",
                 "value_num_lower": "lower", "value_num_upper": "upper"})
    return both.merge(published, on=key, how="inner")
