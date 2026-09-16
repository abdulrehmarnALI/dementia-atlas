"""Value and metadata schema for silver rows.

Defines the one observation shape both publication eras are loaded into, and the
small parsers that turn published tokens into typed columns without losing the
original. Evidence: ``notebooks/03_cross_release_qa.ipynb`` sections 2, 3 and 10,
plus the value-token census re-run in ``tests/test_silver_schema.py``.

The rules that matter:

- ``value_raw`` is kept verbatim. ``value_num`` and ``value_state`` are derived from
  it, never the other way round.
- ``*`` is disclosure control. In the Sub-ICB files the minimum published count
  alongside it is 5, so there ``*`` means "an integer in 0-4", not "missing". The
  Era-A practice-level files publish 0-4 freely next to ``*``, so their rule is
  different and undocumented. Either way ``*`` is never coerced to 0 or to null
  without the state travelling alongside.
- Unknown tokens raise. A new sentinel in a future release is a decision, not a NaN.
"""

import re

import pandas as pd

# --------------------------------------------------------------------------------------
# Value states
# --------------------------------------------------------------------------------------

NUMERIC = "numeric"
SUPPRESSED = "suppressed"            # '*' - disclosure control, true value in 0..4
BLANK = "blank"                      # unavailable / not published
NOT_APPLICABLE = "not_applicable"    # 'N/A' - breakdown does not apply to this measure
MINIMUM = "minimum"                  # computed over suppressed inputs: value_num is the
                                     # lower bound, value_num_upper the upper bound

VALUE_STATES = (NUMERIC, SUPPRESSED, BLANK, NOT_APPLICABLE, MINIMUM)
PUBLISHED_VALUE_STATES = (NUMERIC, SUPPRESSED, BLANK, NOT_APPLICABLE)   # never MINIMUM

# What '*' hides. Holds for every file silver loads (the Sub-ICB files never publish a
# count below 5 next to '*'). It does NOT hold for the Era-A practice-level files, which
# is one reason they are not loaded.
SUPPRESSED_LOWER = 0.0
SUPPRESSED_UPPER = 4.0

SUPPRESSED_TOKEN = "*"
# '' is the dictionary's "cell left blank where unavailable". '.' is undocumented: it
# occurs in 12 PAT_LIST cells of the March 2026 practice care-plans file, for five
# practices in Apr-Sep 2025 (one of them the practice that closed mid-window), and
# is the SAS convention for a missing numeric. Treated as blank; see NOW.md.
BLANK_TOKENS = frozenset({"", "."})
NOT_APPLICABLE_TOKEN = "N/A"


def classify_values(raw: pd.Series) -> pd.DataFrame:
    """Split a published value column into ``value_num`` (float, NaN unless numeric),
    ``value_state``, and the bounds ``value_num_lower`` / ``value_num_upper``.

    Bounds: a numeric value is its own bounds; a suppressed cell is 0..4; blank and
    not-applicable have none. Raises ValueError listing any token that is neither
    numeric nor a known sentinel, so a new publisher convention cannot slip through
    as NaN.
    """
    raw = raw.astype("string").fillna("")
    value_num = pd.to_numeric(raw, errors="coerce").astype("float64")
    value_state = pd.Series(pd.NA, index=raw.index, dtype="string")
    value_state[value_num.notna()] = NUMERIC
    value_state[raw == SUPPRESSED_TOKEN] = SUPPRESSED
    value_state[raw.isin(BLANK_TOKENS)] = BLANK
    value_state[raw == NOT_APPLICABLE_TOKEN] = NOT_APPLICABLE
    unknown = raw[value_state.isna()].unique()
    if len(unknown):
        raise ValueError(f"Unrecognised value tokens: {sorted(map(str, unknown))!r}")
    suppressed = value_state == SUPPRESSED
    lower = value_num.where(~suppressed, SUPPRESSED_LOWER)
    upper = value_num.where(~suppressed, SUPPRESSED_UPPER)
    return pd.DataFrame({"value_num": value_num, "value_state": value_state,
                         "value_num_lower": lower, "value_num_upper": upper})


def parse_dq_flag(raw: pd.Series) -> pd.Series:
    """The rate files' DQ column: blank, or a '1' (published as ``1.0``) marking a
    denominator population smaller than the CFAS II reference population."""
    raw = raw.astype("string").fillna("")
    flag = raw.isin({"1", "1.0"})
    bad = raw[~flag & (raw != "")].unique()
    if len(bad):
        raise ValueError(f"Unrecognised DQ tokens: {sorted(map(str, bad))!r}")
    return flag.astype("boolean")


# --------------------------------------------------------------------------------------
# Dates
# --------------------------------------------------------------------------------------

# Three spellings across the corpus: 31-Mar-26 (most files), 2025-03-31 (practice
# antipsychotic file and latest-submission file), 01Mar2026 (Era-A mapping extract).
_DATE_FORMATS = (
    (re.compile(r"^\d{2}-[A-Za-z]{3}-\d{2}$"), "%d-%b-%y"),
    (re.compile(r"^\d{4}-\d{2}-\d{2}$"), "%Y-%m-%d"),
    (re.compile(r"^\d{2}[A-Za-z]{3}\d{4}$"), "%d%b%Y"),
)


def parse_dates(raw: pd.Series) -> pd.Series:
    """Parse any of the publisher's date spellings into datetime64. Raises on a
    spelling not seen before."""
    raw = raw.astype("string").fillna("")
    out = pd.Series(pd.NaT, index=raw.index, dtype="datetime64[ns]")
    for pattern, fmt in _DATE_FORMATS:
        mask = raw.str.match(pattern).fillna(False)
        if mask.any():
            out[mask] = pd.to_datetime(raw[mask], format=fmt)
    unparsed = raw[out.isna()].unique()
    if len(unparsed):
        raise ValueError(f"Unrecognised date spellings: {sorted(map(str, unparsed))!r}")
    return out


def parse_period_end(raw: pd.Series) -> pd.Series:
    """ACH_DATE -> period_end. Every reporting period ends on a month-end; anything
    else means the column was misread."""
    dates = parse_dates(raw)
    not_month_end = dates[~dates.dt.is_month_end].unique()
    if len(not_month_end):
        raise ValueError(f"ACH_DATE values that are not month-ends: {list(not_month_end)!r}")
    return dates


# --------------------------------------------------------------------------------------
# Release metadata
# --------------------------------------------------------------------------------------

ERA_A = "A"   # split files, rolling 13-month window, categories inside `Measure`
ERA_B = "B"   # consolidated files, single period, explicit dimension columns

LAST_OBSERVED_ERA_A_RELEASE = "2026-03"
FIRST_OBSERVED_ERA_B_RELEASE = "2026-06"

_RELEASE = re.compile(r"^\d{4}-\d{2}$")


def publication_era(release: str) -> str:
    """Which schema era a release (``YYYY-MM``) belongs to.

    The boundary is attributed to the 2026/27 financial year but has only been
    *observed* at March -> June 2026. April and May 2026 are deliberately
    unclassified until a file is seen (NOW.md, open question).
    """
    if not _RELEASE.match(release):
        raise ValueError(f"release must be YYYY-MM, got {release!r}")
    if release <= LAST_OBSERVED_ERA_A_RELEASE:
        return ERA_A
    if release >= FIRST_OBSERVED_ERA_B_RELEASE:
        return ERA_B
    raise ValueError(
        f"Release {release} falls in the unobserved gap between the last Era-A release "
        f"({LAST_OBSERVED_ERA_A_RELEASE}) and the first Era-B release "
        f"({FIRST_OBSERVED_ERA_B_RELEASE}); classify it deliberately once a file is held."
    )


def dictionary_version(release: str) -> str:
    """The data dictionary that governs a release: one per financial year, named
    ``PCDD-YYyy`` (``PCDD-2526`` for anything published Apr 2025 - Mar 2026)."""
    if not _RELEASE.match(release):
        raise ValueError(f"release must be YYYY-MM, got {release!r}")
    year, month = int(release[:4]), int(release[5:])
    fy_start = year if month >= 4 else year - 1
    return f"PCDD-{fy_start % 100:02d}{(fy_start + 1) % 100:02d}"


# --------------------------------------------------------------------------------------
# The silver observation shape
# --------------------------------------------------------------------------------------

# The five breakdown dimensions, in canonical order. This is the single definition:
# measure_crosswalk.MeasureKey's fields and the loader's column handling are checked
# against it rather than repeating the list.
DIMENSION_COLUMNS: tuple[str, ...] = ("age", "gender", "ethnicity", "dementia_type", "residential_type")

# Column -> pandas dtype. Order is the canonical column order.
#
# Identity note: ``org_code`` is the ODS code for every NHS level (practice, Sub-ICB,
# ICB, region, England = "ENG") but the *ONS* code for local-government levels
# (LTLA, UTLA, GOR, and England = "E92000001" in la_rate), because la_rate publishes
# no ODS code. Join on (org_level, org_code), never on org_code alone.
SILVER_COLUMNS: dict[str, str] = {
    # provenance
    "source_release": "string",         # YYYY-MM of the publication the row came from
    "source_file": "string",            # raw file name within that release
    "publication_era": "string",        # ERA_A / ERA_B
    "dictionary_version": "string",     # PCDD-2526 / PCDD-2627 / ...
    "ingested_at": "datetime64[ns]",
    # grain
    "period_end": "datetime64[ns]",
    "org_level": "string",              # org_crosswalk.ORG_LEVELS
    "org_code": "string",               # ODS code where one exists, else ONS code - see note above
    "ons_code": "string",               # secondary identifier; England normalised
    "measure": "string",
    "breakdown": "string",
    **{dimension: "string" for dimension in DIMENSION_COLUMNS},
    # value
    "value_raw": "string",
    "value_num": "float64",
    "value_state": "string",
    "value_num_lower": "float64",       # exact bounds on the true value; equal to value_num
    "value_num_upper": "float64",       #   when numeric, 0..4 when suppressed, NaN when blank
    "dq_flag": "boolean",               # rate files only; False elsewhere
    "is_derived": "boolean",            # computed at silver build (e.g. all-sex rows), not published
    "comparability": "string",          # measure_crosswalk cross-era class
}

# The columns that identify one observation. Everything else is provenance or value.
SILVER_KEY: tuple[str, ...] = (
    "source_release", "period_end", "org_level", "org_code", "measure", "breakdown",
    "age", "gender", "ethnicity", "dementia_type", "residential_type",
)


def empty_silver_frame() -> pd.DataFrame:
    return pd.DataFrame({col: pd.Series(dtype=dt) for col, dt in SILVER_COLUMNS.items()})


def conform(df: pd.DataFrame) -> pd.DataFrame:
    """Coerce a frame to the silver column order and dtypes; missing columns are an
    error rather than silently added."""
    missing = [c for c in SILVER_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"silver frame is missing columns: {missing}")
    out = df[list(SILVER_COLUMNS)].copy()
    for col, dt in SILVER_COLUMNS.items():
        out[col] = out[col].astype(dt)
    return out
