"""Series breaks: where a series is not comparable with its own past.

A break is a property of an organisation or of a measure, not of an observation
(docs/context.md decision), so breaks live in their own table keyed on
``(org_level, org_code)`` or ``(measure, breakdown)`` with an ``effective_from``
period. The app reads this table and never re-derives breaks from the rows.

Two sources:

- **Known breaks** from the crosswalks: the 2026-04 ICB reorganisation (codes
  closed, opened, and Sub-ICBs whose geography changed under a stable code), and
  the measures whose definition, suppression or existence changed at the era
  boundary.
- **Breaks read off the data**: organisations and measures whose series start
  after, or end before, the rest of their level - the 2025-07 UTLA expansion, the
  2024-06 start of MCI, the 2025-04 start of delirium.
"""

import pandas as pd

from .measure_crosswalk import (
    COMPARABLE,
    COMPARABLE_LABELS_ONLY,
    CROSS_ERA_COMPARABILITY,
    ERA_A_ONLY,
    ERA_B_ONLY,
    NOT_COMPARABLE,
)
from .org_crosswalk import (
    ICB_CODES_INTRODUCED_2026_04,
    ICB_CODES_RETIRED_2026_04,
    ICB_REORG_EFFECTIVE,
    ICB_REORG_SOURCE,
    SUB_ICB_BOUNDARY_BREAKS_2026_04,
    SUB_ICB_CODES_INTRODUCED_2026_04,
    SUB_ICB_CODES_RETIRED_2026_04,
)

BREAK_COLUMNS: dict[str, str] = {
    "scope": "string",             # "org" or "measure"
    "org_level": "string",         # org scope
    "org_code": "string",          # org scope
    "measure": "string",           # measure scope
    "breakdown": "string",         # measure scope; "*" = every breakdown of the measure
    "effective_from": "string",    # first period (YYYY-MM) the new state applies to
    "kind": "string",
    "note": "string",
    "source": "string",
}

# kinds
CLOSED = "closed"                        # series ends; the code is retired
OPENED = "opened"                        # series starts; nothing before this period
BOUNDARY_CHANGE = "boundary_change"      # same code, different geography either side
DEFINITION_CHANGE = "definition_change"  # same name, different measurement
SUPPRESSION_REMOVED = "suppression_removed"  # values incomparable because Era A hid 0-4
DISCONTINUED = "discontinued"            # measure no longer published
INTRODUCED = "introduced"                # measure first published

# ICB QRL is the parent of D9Y0V, which absorbed 14 Frimley practices; S9B9J (92A's
# new parent) is itself new. So QRL is the one continuing ICB whose geography moved.
ICB_BOUNDARY_CHANGES_2026_04 = {"QRL": "NHS Hampshire and Isle of Wight ICB expanded via D9Y0V (14 D4U1Y practices)"}

_ODS = "NHS England ODS: " + ICB_REORG_SOURCE
_QA = "notebooks/03_cross_release_qa.ipynb"


def _rows(scope, kind, effective_from, note, source, orgs=(), measures=()):
    for level, code in orgs:
        yield {"scope": scope, "org_level": level, "org_code": code, "measure": pd.NA, "breakdown": pd.NA,
               "effective_from": effective_from, "kind": kind, "note": note, "source": source}
    for measure, breakdown in measures:
        yield {"scope": scope, "org_level": pd.NA, "org_code": pd.NA, "measure": measure, "breakdown": breakdown,
               "effective_from": effective_from, "kind": kind, "note": note, "source": source}


def known_org_breaks() -> pd.DataFrame:
    """The 2026-04 reorganisation, from the org crosswalk."""
    rows = []
    rows += _rows("org", CLOSED, ICB_REORG_EFFECTIVE, "ICB closed at the 2026 reorganisation", _ODS,
                  orgs=[("icb", c) for c in sorted(ICB_CODES_RETIRED_2026_04)])
    rows += _rows("org", OPENED, ICB_REORG_EFFECTIVE, "ICB created at the 2026 reorganisation", _ODS,
                  orgs=[("icb", c) for c in sorted(ICB_CODES_INTRODUCED_2026_04)])
    for code, note in ICB_BOUNDARY_CHANGES_2026_04.items():
        rows += _rows("org", BOUNDARY_CHANGE, ICB_REORG_EFFECTIVE, note, _ODS, orgs=[("icb", code)])
    rows += _rows("org", CLOSED, ICB_REORG_EFFECTIVE, "Sub-ICB closed; practices split across successors", _ODS,
                  orgs=[("sub_icb", c) for c in sorted(SUB_ICB_CODES_RETIRED_2026_04)])
    for code, note in SUB_ICB_BOUNDARY_BREAKS_2026_04.items():
        kind = OPENED if code in SUB_ICB_CODES_INTRODUCED_2026_04 else BOUNDARY_CHANGE
        rows += _rows("org", kind, ICB_REORG_EFFECTIVE, note, _ODS, orgs=[("sub_icb", code)])
    return pd.DataFrame(rows)


_MEASURE_KIND = {
    NOT_COMPARABLE: (DEFINITION_CHANGE, "measure redefined at the 2026/27 boundary"),
    COMPARABLE_LABELS_ONLY: (SUPPRESSION_REMOVED, "Era A suppressed counts of 0-4; Era B publishes them"),
    ERA_A_ONLY: (DISCONTINUED, "not published from 2026/27"),
    ERA_B_ONLY: (INTRODUCED, "first published in 2026/27"),
}


def known_measure_breaks() -> pd.DataFrame:
    """Measures whose meaning, suppression or existence changes at the era boundary,
    from the measure crosswalk's comparability table."""
    rows = []
    for (measure, breakdown), comparability in CROSS_ERA_COMPARABILITY.items():
        if comparability == COMPARABLE:
            continue
        kind, note = _MEASURE_KIND[comparability]
        rows += _rows("measure", kind, ICB_REORG_EFFECTIVE, note, _QA + " §7.2", measures=[(measure, breakdown)])
    return pd.DataFrame(rows)


def breaks_from_data(silver: pd.DataFrame, org_levels=("utla", "ltla", "gor")) -> pd.DataFrame:
    """Series that start late or end early relative to their level or family, read
    off the loaded rows. Restricted to the local-authority levels for organisations
    (NHS levels are covered by the known breaks) and to published measures."""
    published = silver[~silver["is_derived"].astype(bool)].copy()
    published["period"] = published["period_end"].dt.strftime("%Y-%m")
    rows = []

    # Organisations, within a level: first/last period per code vs the level's span.
    for level in org_levels:
        at_level = published[published["org_level"] == level]
        if at_level.empty:
            continue
        span = at_level.groupby("org_code")["period"].agg(["min", "max"])
        level_min, level_max = at_level["period"].min(), at_level["period"].max()
        for code, first in span[span["min"] > level_min]["min"].items():
            rows += _rows("org", OPENED, first, f"{level.upper()} first published at {first}", _QA + " §8",
                          orgs=[(level, code)])
        for code, last in span[span["max"] < level_max]["max"].items():
            rows += _rows("org", CLOSED, _next_period(last), f"{level.upper()} last published at {last}", _QA + " §8",
                          orgs=[(level, code)])

    # Measures: first period per (measure, breakdown) vs the earliest period held.
    earliest = published["period"].min()
    first_seen = published.groupby(["measure", "breakdown"])["period"].min()
    for (measure, breakdown), first in first_seen[first_seen > earliest].items():
        if (measure, breakdown) in CROSS_ERA_COMPARABILITY and CROSS_ERA_COMPARABILITY[(measure, breakdown)] == ERA_B_ONLY:
            continue   # already an "introduced" row at the era boundary
        if (measure, "*") in CROSS_ERA_COMPARABILITY and CROSS_ERA_COMPARABILITY[(measure, "*")] == ERA_B_ONLY:
            continue
        rows += _rows("measure", INTRODUCED, first, f"first period with data: {first}", _QA + " §7",
                      measures=[(measure, breakdown)])
    return pd.DataFrame(rows, columns=list(BREAK_COLUMNS))


def _next_period(period: str) -> str:
    return (pd.Period(period, freq="M") + 1).strftime("%Y-%m")


def build_series_breaks(silver: pd.DataFrame) -> pd.DataFrame:
    """Every known and data-derived break, one row each, in a fixed shape."""
    out = pd.concat([known_org_breaks(), known_measure_breaks(), breaks_from_data(silver)], ignore_index=True)
    out = out[list(BREAK_COLUMNS)]
    for col, dt in BREAK_COLUMNS.items():
        out[col] = out[col].astype(dt)
    key = ["scope", "org_level", "org_code", "measure", "breakdown", "effective_from", "kind"]
    if out.duplicated(key).any():
        raise ValueError(f"duplicate series breaks: {out[out.duplicated(key, keep=False)].to_dict('records')[:5]}")
    return out.sort_values(["scope", "org_level", "org_code", "measure", "breakdown", "effective_from"]).reset_index(drop=True)
