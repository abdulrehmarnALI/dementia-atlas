"""Derived rows: computed at silver build, never stored from the publication.

Era A publishes an ``ALL_AGED_<band>`` row alongside ``FEMALE_AGED_<band>`` and
``MALE_AGED_<band>``; it is exactly Female + Male in 100% of cells (QA notebook
§7.1, re-proved in ``tests/test_derived_rows.py``). Era B publishes no all-sex row.
Keeping the published Era-A row would double-count any naive sum over gender, so
silver drops it and recomputes the all-sex row for both eras from the same rule.

The same summing rule carries value state: a total built over a suppressed cell is
itself suppressed (context.md, done-criterion 7), never a silently smaller number.
"""

import pandas as pd

from .silver_schema import BLANK, NUMERIC, SILVER_COLUMNS, SUPPRESSED

ALL = "ALL"
AGE_GENDER = "AGE_GENDER"

# Columns that vary between the members of a derived group, or describe the value.
_NON_GROUPING = {"gender", "value_raw", "value_num", "value_state", "dq_flag", "is_derived",
                 "ingested_at"}
GROUP_COLUMNS = [c for c in SILVER_COLUMNS if c not in _NON_GROUPING]


def sum_with_state(value_num: pd.Series, value_state: pd.Series) -> tuple[float, str]:
    """Sum a set of silver values, propagating state.

    All numeric -> numeric sum. Any suppressed input -> the total is suppressed (the
    true total is the partial sum plus 0-4 per suppressed cell, and we do not guess).
    Otherwise any blank input -> blank.
    """
    states = set(value_state)
    if states == {NUMERIC}:
        return float(value_num.sum()), NUMERIC
    if SUPPRESSED in states:
        return float("nan"), SUPPRESSED
    return float("nan"), BLANK


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

    rows = []
    for key, group in sexed.groupby(GROUP_COLUMNS, sort=False, dropna=False):
        if set(group["gender"]) != {"Female", "Male"} or len(group) != 2:
            continue
        num, state = sum_with_state(group["value_num"], group["value_state"])
        row = dict(zip(GROUP_COLUMNS, key))
        row.update({
            "gender": ALL,
            "value_raw": pd.NA,
            "value_num": num,
            "value_state": state,
            "dq_flag": False,
            "is_derived": True,
            "ingested_at": group["ingested_at"].iloc[0],
        })
        rows.append(row)

    out = pd.DataFrame(rows, columns=list(SILVER_COLUMNS))
    for col, dt in SILVER_COLUMNS.items():
        out[col] = out[col].astype(dt)
    return out
