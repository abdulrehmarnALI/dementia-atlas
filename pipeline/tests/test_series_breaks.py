"""The series-breaks table against the loaded rows and the raw la_rate file."""

import sys
from pathlib import Path

import pandas as pd
import pytest

PIPELINE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPELINE_DIR))

from src.series_breaks import (  # noqa: E402
    BOUNDARY_CHANGE, BREAK_COLUMNS, CLOSED, INTRODUCED, OPENED,
    breaks_from_data, build_series_breaks, known_measure_breaks, known_org_breaks,
)
from src.measure_crosswalk import COMPARABLE, CROSS_ERA_COMPARABILITY  # noqa: E402
from src.silver_loader import build_silver  # noqa: E402

RAW = PIPELINE_DIR / "data" / "raw" / "pcdd"


@pytest.fixture(scope="module")
def silver():
    return build_silver(RAW, None, ingested_at=pd.Timestamp("2026-09-16"))


@pytest.fixture(scope="module")
def breaks(silver):
    return build_series_breaks(silver)


def test_shape_and_uniqueness(breaks):
    assert list(breaks.columns) == list(BREAK_COLUMNS)
    assert breaks["effective_from"].str.fullmatch(r"\d{4}-\d{2}").all()
    assert set(breaks["scope"]) == {"org", "measure"}
    org = breaks[breaks["scope"] == "org"]
    assert org[["org_level", "org_code"]].notna().all().all() and org[["measure", "breakdown"]].isna().all().all()


def test_reorganisation_breaks_match_the_loaded_organisations(silver, breaks):
    org = breaks[breaks["scope"] == "org"].set_index(["org_level", "org_code"])
    era_a = silver[silver["publication_era"] == "A"]
    era_b = silver[silver["publication_era"] == "B"]
    closed = org[org["kind"] == CLOSED]
    opened = org[(org["kind"] == OPENED) & (org.index.get_level_values("org_level").isin(["icb", "sub_icb"]))]
    for level, code in closed.index:
        assert code in set(era_a.loc[era_a["org_level"] == level, "org_code"]), (level, code)
        assert code not in set(era_b.loc[era_b["org_level"] == level, "org_code"]), (level, code)
    for level, code in opened.index:
        assert code not in set(era_a.loc[era_a["org_level"] == level, "org_code"]), (level, code)
        assert code in set(era_b.loc[era_b["org_level"] == level, "org_code"]), (level, code)
    boundary = org[org["kind"] == BOUNDARY_CHANGE]
    assert set(boundary.index) == {("sub_icb", "D9Y0V"), ("sub_icb", "92A"), ("icb", "QRL")}
    assert (org["effective_from"].loc[org["kind"].isin([CLOSED, OPENED, BOUNDARY_CHANGE])]
            .loc[lambda s: s.index.get_level_values("org_level").isin(["icb", "sub_icb"])] == "2026-04").all()
    assert len(known_org_breaks()) == 12 + 6 + 1 + 1 + 3


def test_utla_expansion_is_read_off_the_data(silver, breaks):
    """UTLAs jump from 132 to 153 at 2025-07 (QA notebook §8): every code that
    appears then and not before gets an 'opened' row, and nothing else at UTLA."""
    la = pd.read_csv(RAW / "2026-03" / "pcdem-la-rate-mar-2026.csv", dtype=str, keep_default_na=False)
    la["period"] = pd.to_datetime(la["ACH_DATE"], format="%d-%b-%y").dt.strftime("%Y-%m")
    utla = la[la["ORG_TYPE"] == "UTLA"]
    before = set(utla.loc[utla["period"] < "2025-07", "ONS_CODE"])
    after = set(utla.loc[utla["period"] == "2025-07", "ONS_CODE"])
    new_codes = after - before
    assert len(before) == 132 and len(after) == 153

    utla_breaks = breaks[(breaks["scope"] == "org") & (breaks["org_level"] == "utla")]
    assert set(utla_breaks["org_code"]) == new_codes
    assert set(utla_breaks["kind"]) == {OPENED} and set(utla_breaks["effective_from"]) == {"2025-07"}
    # The LTLA reissue is handled by canonicalising org_code, so it is not a break.
    assert breaks[(breaks["org_level"] == "ltla")].empty


def test_measure_breaks_cover_every_non_comparable_pair_and_late_starts(breaks):
    measure = breaks[breaks["scope"] == "measure"]
    # A measure can carry more than one break (MCI: introduced 2024-06 AND
    # suppression removed 2026-04), so key on kind as well.
    by_kind = {(m, b, k): e for m, b, k, e in
               zip(measure["measure"], measure["breakdown"], measure["kind"], measure["effective_from"])}
    assert by_kind[("INCIDENCE", "N/A", "definition_change")] == "2026-04"
    assert by_kind[("COMORBIDITIES", "N/A", "discontinued")] == "2026-04"
    assert by_kind[("REFERRALS", "*", "introduced")] == "2026-04"
    assert by_kind[("DEMENTIA_REGISTER", "RESIDENCE_TYPE", "suppression_removed")] == "2026-04"
    # Read off the data: MCI starts 2024-06, delirium 2025-04 (QA notebook §7).
    assert by_kind[("MCI", "AGE_GENDER", INTRODUCED)] == "2024-06"
    assert by_kind[("DELIRIUM_12M", "N/A", INTRODUCED)] == "2025-04"
    assert len(known_measure_breaks()) == sum(1 for v in CROSS_ERA_COMPARABILITY.values() if v != COMPARABLE)


def test_breaks_from_data_is_empty_when_nothing_starts_late(silver):
    june = silver[silver["source_release"] == "2026-06"]
    assert breaks_from_data(june).empty
