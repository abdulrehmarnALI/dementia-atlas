"""Derived rows: computed at silver build, never stored from the publication.

Era A publishes an ``ALL_AGED_<band>`` row alongside ``FEMALE_AGED_<band>`` and
``MALE_AGED_<band>``; it is exactly Female + Male in 100% of cells (QA notebook
§7.1, re-proved in ``tests/test_derived_rows.py``). Era B publishes no all-sex row.
Keeping the published Era-A row would double-count any naive sum over gender, so
silver drops it and recomputes the all-sex row for both eras from the same rule.

That rule - ``sum_with_state`` - is the one every computed total in silver uses
(derived all-sex rows here, hierarchy aggregates in ``aggregation``). Because a
suppressed cell hides an integer in 0..4, a sum over suppressed inputs has exact
bounds: the total is published as its lower bound with state ``minimum`` and the
upper bound carried alongside (docs/context.md decision).
"""

import pandas as pd

from .measure_crosswalk import ALL, BREAKDOWN_AGE_GENDER as AGE_GENDER
from .silver_schema import BLANK, MINIMUM, NOT_APPLICABLE, NUMERIC, SILVER_COLUMNS

# --------------------------------------------------------------------------------------
# The summing rule
# --------------------------------------------------------------------------------------

def sum_with_state(values: pd.DataFrame) -> dict:
    """Sum a set of silver values, propagating state and bounds.

    This is the specification; ``sum_groups`` is the vectorised form used in
    practice, and the tests assert the two agree.

    - any blank / not-applicable input  -> blank, no bounds (nothing can be said)
    - all numeric                       -> numeric sum; bounds equal the sum
    - otherwise (some suppressed, or    -> ``minimum``: value_num is the sum of lower
      inputs that are themselves minima)   bounds, value_num_upper the sum of uppers
    """
    states = set(values["value_state"])
    if states & {BLANK, NOT_APPLICABLE}:
        return {"value_num": float("nan"), "value_state": BLANK,
                "value_num_lower": float("nan"), "value_num_upper": float("nan")}
    lower = float(values["value_num_lower"].sum())
    upper = float(values["value_num_upper"].sum())
    if states == {NUMERIC}:
        return {"value_num": lower, "value_state": NUMERIC,
                "value_num_lower": lower, "value_num_upper": upper}
    return {"value_num": lower, "value_state": MINIMUM,
            "value_num_lower": lower, "value_num_upper": upper}


def sum_groups(df: pd.DataFrame, group_columns: list[str], extra: dict | None = None) -> pd.DataFrame:
    """``sum_with_state`` applied per group, without a Python loop.

    Returns one row per group with the group columns, ``n`` (members), the four
    value columns, and any ``extra`` named aggregations (pandas ``agg`` syntax).

    How it works: the facts the rule needs are turned into 0/1 columns first
    (``_blank``, ``_numeric``), so that summing them inside a group is the same as
    counting; the bounds are summed directly; then the rule's three cases become
    three masks applied in priority order.
    """
    flagged = df.assign(
        _blank=df["value_state"].isin([BLANK, NOT_APPLICABLE]).astype(int),
        _numeric=(df["value_state"] == NUMERIC).astype(int),
    )
    aggs = {
        "n": ("_blank", "size"),
        "n_blank": ("_blank", "sum"),
        "n_numeric": ("_numeric", "sum"),
        "value_num_lower": ("value_num_lower", "sum"),
        "value_num_upper": ("value_num_upper", "sum"),
        **(extra or {}),
    }
    # dropna=False: ons_code can be NA and pandas would otherwise drop those groups.
    out = flagged.groupby(group_columns, sort=False, dropna=False).agg(**aggs).reset_index()

    any_blank = out["n_blank"] > 0
    all_numeric = out["n_numeric"] == out["n"]
    out["value_state"] = MINIMUM
    out.loc[all_numeric, "value_state"] = NUMERIC
    out.loc[any_blank, "value_state"] = BLANK
    out["value_num"] = out["value_num_lower"]
    out.loc[any_blank, ["value_num", "value_num_lower", "value_num_upper"]] = float("nan")
    return out.drop(columns=["n_blank", "n_numeric"])


# --------------------------------------------------------------------------------------
# All-sex rows
# --------------------------------------------------------------------------------------

# The columns that identify a derived all-sex group: everything that is the same for
# the Female row, the Male row and the ALL row they produce. Listed explicitly so that
# adding a silver column is a deliberate choice here too - the assertion below fails
# the import if a column is neither grouped on nor accounted for.
GROUP_COLUMNS: list[str] = [
    "source_release", "source_file", "publication_era", "dictionary_version",
    "period_end", "org_level", "org_code", "ons_code",
    "measure", "breakdown", "age", "ethnicity", "dementia_type", "residential_type",
    "comparability",
]
_PER_ROW_COLUMNS = {
    "gender",                                                       # what the group varies over
    "value_raw", "value_num", "value_state", "value_num_lower", "value_num_upper",
    "dq_flag", "is_derived", "ingested_at",
}
assert set(GROUP_COLUMNS) | _PER_ROW_COLUMNS == set(SILVER_COLUMNS), (
    "SILVER_COLUMNS changed: decide whether the new column groups or is per-row")


def is_published_all_sex_row(df: pd.DataFrame) -> pd.Series:
    """Era-A ``ALL_AGED_<band>`` rows after decoding: an AGE_GENDER breakdown with
    gender ALL that was *published*, not derived."""
    return (df["breakdown"] == AGE_GENDER) & (df["gender"] == ALL) & ~df["is_derived"].fillna(False).astype(bool)


def drop_published_all_sex_rows(df: pd.DataFrame) -> pd.DataFrame:
    return df[~is_published_all_sex_row(df)]


def derive_all_sex_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Build gender=ALL rows for every AGE_GENDER observation that has both a Female
    and a Male row. Groups missing either sex produce nothing - absence of a row is
    not a zero.

    Returns only the new rows, in silver column order, with ``is_derived=True`` and
    no ``value_raw`` (there is no published token to keep).
    """
    sexed = df[(df["breakdown"] == AGE_GENDER) & df["gender"].isin(["Female", "Male"])]
    if sexed.empty:
        return df.iloc[0:0].copy()

    flagged = sexed.assign(_female=(sexed["gender"] == "Female").astype(int),
                           _male=(sexed["gender"] == "Male").astype(int))
    agg = sum_groups(flagged, GROUP_COLUMNS, extra={
        "female": ("_female", "sum"), "male": ("_male", "sum"), "ingested_at": ("ingested_at", "first")})
    agg = agg[(agg["n"] == 2) & (agg["female"] == 1) & (agg["male"] == 1)]

    out = agg.drop(columns=["n", "female", "male"]).copy()
    out["gender"] = ALL
    out["value_raw"] = pd.NA
    out["dq_flag"] = False
    out["is_derived"] = True

    out = out[list(SILVER_COLUMNS)].reset_index(drop=True)
    for col, dt in SILVER_COLUMNS.items():
        out[col] = out[col].astype(dt)
    return out
