"""Re-derive the value/metadata schema claims from the raw CSVs with plain pandas.

The schema module hard-codes a small vocabulary of publisher sentinels, date
spellings and DQ tokens. These tests census the raw files of both held releases
independently and check that vocabulary is complete - nothing appears in the
data that the parsers would not recognise - and that the parsers classify each
observed token the way the evidence says they should.
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

PIPELINE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPELINE_DIR))

from src.silver_schema import (  # noqa: E402
    BLANK,
    ERA_A,
    ERA_B,
    NOT_APPLICABLE,
    NUMERIC,
    SILVER_COLUMNS,
    SILVER_KEY,
    SUPPRESSED,
    VALUE_STATES,
    classify_values,
    conform,
    dictionary_version,
    empty_silver_frame,
    parse_dates,
    parse_dq_flag,
    parse_period_end,
    publication_era,
)

RAW = PIPELINE_DIR / "data" / "raw" / "pcdd"


def header(path: Path) -> list[str]:
    return pd.read_csv(path, nrows=0, encoding="utf-8-sig").columns.tolist()


def read_cols(path: Path, cols: list[str]) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig", usecols=cols)


def all_csvs():
    return sorted(p for rel in ("2026-03", "2026-06") for p in (RAW / rel).glob("*.csv"))


@pytest.fixture(scope="module")
def value_columns():
    """{file: raw value Series} for every CSV that has a VALUE/Value column."""
    out = {}
    for path in all_csvs():
        col = next((c for c in header(path) if c.upper() == "VALUE"), None)
        if col:
            out[path.name] = read_cols(path, [col])[col]
    return out


# --------------------------------------------------------------------------------------
# Value tokens
# --------------------------------------------------------------------------------------

def test_value_token_universe_is_exactly_numeric_star_and_dot(value_columns):
    seen = set()
    for series in value_columns.values():
        seen |= set(series[pd.to_numeric(series, errors="coerce").isna()].unique())
    assert seen == {"*", "."}, f"value tokens in the corpus: {seen}"


def test_classify_values_recognises_every_observed_token(value_columns):
    for name, series in value_columns.items():
        out = classify_values(series)
        assert set(out["value_state"].unique()) <= set(VALUE_STATES), name
        # numeric rows parse, non-numeric rows do not, one-to-one
        assert (out["value_num"].notna() == (out["value_state"] == NUMERIC)).all(), name
        assert ((series == "*") == (out["value_state"] == SUPPRESSED)).all(), name
        assert ((series == ".") == (out["value_state"] == BLANK)).all(), name


def test_star_means_zero_to_four_in_sub_icb_files_but_not_in_practice_files(value_columns):
    """In the Sub-ICB files that contain '*', no count below 5 is ever published - so
    '*' hides 0-4 and is not null. The practice-level files are different: they
    publish zeros and 1-4 freely alongside '*', so whatever their suppression rule
    is, it is not small-number suppression (recorded in NOW.md, not resolved here)."""
    for name, series in value_columns.items():
        num = pd.to_numeric(series, errors="coerce")
        if not (series == "*").any():
            continue
        if "sicbl" in name:
            assert num.min() >= 5, f"{name}: min published value {num.min()} alongside '*'"
        else:
            assert name.startswith("pcdem-prac-"), name
            assert (num == 0).any() and ((num >= 1) & (num <= 4)).any(), name
    # Era B publishes everything, including small counts, unsuppressed.
    era_b = value_columns["pcdem-sub-icb-jun-2026.csv"]
    assert not (era_b == "*").any()
    assert (pd.to_numeric(era_b) == 0).any()


def test_dot_is_confined_to_pat_list_in_the_practice_care_plans_file():
    path = RAW / "2026-03" / "pcdem-prac-ass-plans-mar-2026.csv"
    df = read_cols(path, ["Measure", "Value", "PRACTICE_CODE"])
    dots = df[df["Value"] == "."]
    assert len(dots) == 12
    assert set(dots["Measure"]) == {"PAT_LIST_0_64", "PAT_LIST_65_PLUS"}
    assert dots["PRACTICE_CODE"].nunique() == 5


def test_blank_and_n_a_never_appear_in_a_value_column_but_are_still_classified(value_columns):
    for name, series in value_columns.items():
        assert not (series == "").any(), name
        assert not (series == "N/A").any(), name
    out = classify_values(pd.Series(["12", "*", "", ".", "N/A", "3.5"]))
    assert list(out["value_state"]) == [NUMERIC, SUPPRESSED, BLANK, BLANK, NOT_APPLICABLE, NUMERIC]
    assert out["value_num"].tolist()[:1] == [12.0]
    # Bounds: numeric is its own bounds, suppressed is 0..4, blank / N/A have none.
    assert out["value_num_lower"].tolist()[:2] == [12.0, 0.0]
    assert out["value_num_upper"].tolist()[:2] == [12.0, 4.0]
    assert out.loc[2:4, ["value_num_lower", "value_num_upper"]].isna().all().all()
    assert out.loc[5, "value_num_lower"] == out.loc[5, "value_num_upper"] == 3.5


def test_unknown_value_token_raises():
    with pytest.raises(ValueError, match="Unrecognised value tokens"):
        classify_values(pd.Series(["1", "-", "2"]))


# --------------------------------------------------------------------------------------
# DQ flag
# --------------------------------------------------------------------------------------

def test_dq_tokens_and_where_they_are_set():
    for rel, la, nhs in [("2026-03", "pcdem-la-rate-mar-2026.csv", "pcdem-nhs-rate-mar-2026.csv"),
                         ("2026-06", "pcdem-la-rate-jun-2026.csv", "pcdem-nhs-rate-jun-2026.csv")]:
        la_df = read_cols(RAW / rel / la, ["ORG_TYPE", "DQ"])
        nhs_df = read_cols(RAW / rel / nhs, ["ORG_TYPE", "DQ"])
        assert set(la_df["DQ"]) == {"", "1.0"}, rel
        assert set(nhs_df["DQ"]) == {""}, rel
        flagged = la_df[parse_dq_flag(la_df["DQ"])]
        assert len(flagged) > 0
        assert set(flagged["ORG_TYPE"]) <= {"LTLA", "UTLA"}, rel
    with pytest.raises(ValueError):
        parse_dq_flag(pd.Series(["", "2"]))


# --------------------------------------------------------------------------------------
# Dates
# --------------------------------------------------------------------------------------

def test_every_date_column_in_the_corpus_parses_and_ach_dates_are_month_ends():
    spellings = set()
    for path in all_csvs():
        for col in header(path):
            if col in ("ACH_DATE", "EXTRACT_DATE", "LATEST_DATA_SUBMISSION"):
                raw = read_cols(path, [col])[col]
                spellings |= {("%d-%b-%y" if "-" in v and len(v) == 9 else
                               "%Y-%m-%d" if len(v) == 10 else "%d%b%Y") for v in raw.unique()}
                parsed = parse_period_end(raw) if col == "ACH_DATE" else parse_dates(raw)
                assert parsed.notna().all(), (path.name, col)
    assert spellings == {"%d-%b-%y", "%Y-%m-%d", "%d%b%Y"}


def test_march_2026_release_covers_13_month_ends_and_june_covers_one():
    mar = parse_period_end(read_cols(RAW / "2026-03" / "pcdem-nhs-rate-mar-2026.csv", ["ACH_DATE"])["ACH_DATE"])
    assert mar.nunique() == 13
    assert mar.min() == pd.Timestamp("2025-03-31") and mar.max() == pd.Timestamp("2026-03-31")
    jun = parse_period_end(read_cols(RAW / "2026-06" / "pcdem-nhs-rate-jun-2026.csv", ["ACH_DATE"])["ACH_DATE"])
    assert set(jun) == {pd.Timestamp("2026-06-30")}


def test_unknown_date_spelling_and_non_month_end_raise():
    with pytest.raises(ValueError, match="date spellings"):
        parse_dates(pd.Series(["31/03/2026"]))
    with pytest.raises(ValueError, match="month-ends"):
        parse_period_end(pd.Series(["2026-03-15"]))


# --------------------------------------------------------------------------------------
# Release metadata
# --------------------------------------------------------------------------------------

def test_era_and_dictionary_for_the_held_releases():
    assert publication_era("2025-05") == ERA_A and dictionary_version("2025-05") == "PCDD-2526"
    assert publication_era("2026-03") == ERA_A and dictionary_version("2026-03") == "PCDD-2526"
    assert publication_era("2026-06") == ERA_B and dictionary_version("2026-06") == "PCDD-2627"
    # The dictionaries actually shipped with the releases on disk agree.
    assert (RAW / "2026-03" / "PCDD-2526-data-dictionary.xlsx").exists()
    assert (RAW / "2026-06" / "PCDD-2627-data-dictionary.xlsx").exists()


def test_unobserved_boundary_months_are_refused_not_guessed():
    for release in ("2026-04", "2026-05"):
        with pytest.raises(ValueError, match="unobserved gap"):
            publication_era(release)
    with pytest.raises(ValueError):
        publication_era("June 2026")


# --------------------------------------------------------------------------------------
# Frame shape
# --------------------------------------------------------------------------------------

def test_silver_shape_and_conform():
    assert set(SILVER_KEY) <= set(SILVER_COLUMNS)
    for required in ("value_raw", "value_num", "value_state", "value_num_lower", "value_num_upper",
                     "dq_flag", "source_release", "source_file", "publication_era", "ingested_at",
                     "dictionary_version"):
        assert required in SILVER_COLUMNS
    empty = empty_silver_frame()
    assert list(empty.columns) == list(SILVER_COLUMNS)
    assert conform(empty).dtypes.astype(str).to_dict() == SILVER_COLUMNS
    with pytest.raises(ValueError, match="missing columns"):
        conform(empty.drop(columns=["value_state"]))
