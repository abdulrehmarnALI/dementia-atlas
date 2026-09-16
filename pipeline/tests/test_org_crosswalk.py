"""Re-derive the organisation-crosswalk claims from the raw data with plain pandas.

Each test independently re-checks a claim that ``src/org_crosswalk.py`` hard-codes,
against the raw June 2026 release files - no pipeline code in the loop, just
``pd.read_csv`` and set logic. If NHS England ever republishes these files
differently, these tests fail before the crosswalk quietly lies.

Two releases are on disk and both are used: June 2026 (Era B) for the *new* side
of every boundary, March 2026 (Era A, 13 monthly periods) for the *old* side - the
``COUNTRY``/``REGION`` ORG_TYPE tokens, the retired ICB codes, the pre-reissue LTLA
codes. May 2025 is not held locally.
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

PIPELINE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPELINE_DIR))

from src.org_crosswalk import (  # noqa: E402
    ENGLAND_ODS_CODE,
    ENGLAND_ONS_CODE,
    ICB_CODES_INTRODUCED_2026_06,
    ICB_CODES_RETIRED_2026_06,
    LTLA_ONS_CODE_REISSUES,
    ORG_LEVEL_BY_ORG_TYPE,
    SUB_ICB_CODES_INTRODUCED_2026_06,
    SUB_ICB_CODES_RETIRED_2026_06,
    SUB_ICB_ICB_REASSIGNMENTS_2026_06,
    canonical_ltla_ons_code,
    icb_successors,
    is_england,
    new_icb_for_sub_icb,
    normalise_ons_code,
    to_org_level,
)

RAW = PIPELINE_DIR / "data" / "raw" / "pcdd"
RAW_2026_06 = RAW / "2026-06"
RAW_2026_03 = RAW / "2026-03"


def read_raw(filename: str, release_dir: Path = RAW_2026_06) -> pd.DataFrame:
    """Lossless read: everything as strings, no NA coercion, BOM-tolerant.

    ``keep_default_na=False`` matters because the files use ``N/A`` and the literal
    string ``NULL`` as meaningful tokens; ``utf-8-sig`` because the mapping file
    carries a BOM that would otherwise corrupt its first column name.
    """
    return pd.read_csv(release_dir / filename, dtype=str, keep_default_na=False,
                       encoding="utf-8-sig")


def period(ach_date: pd.Series) -> pd.Series:
    """Era-A ACH_DATE (``31-Mar-26``) -> ``YYYY-MM``."""
    return pd.to_datetime(ach_date, format="%d-%b-%y").dt.strftime("%Y-%m")


@pytest.fixture(scope="module")
def nhs_rate():
    return read_raw("pcdem-nhs-rate-jun-2026.csv")


@pytest.fixture(scope="module")
def la_rate():
    return read_raw("pcdem-la-rate-jun-2026.csv")


@pytest.fixture(scope="module")
def sub_icb():
    return read_raw("pcdem-sub-icb-jun-2026.csv")


@pytest.fixture(scope="module")
def practice():
    return read_raw("pcdem-practice-jun-2026.csv")


@pytest.fixture(scope="module")
def mapping():
    return read_raw("mapping-file-july-dementia-2026.csv")


@pytest.fixture(scope="module")
def nhs_rate_mar():
    return read_raw("pcdem-nhs-rate-mar-2026.csv", RAW_2026_03)


@pytest.fixture(scope="module")
def la_rate_mar():
    return read_raw("pcdem-la-rate-mar-2026.csv", RAW_2026_03)


@pytest.fixture(scope="module")
def cog_imp_mar():
    return read_raw("pcdem_sicbl-cog-imp-mar-2026.csv", RAW_2026_03)


@pytest.fixture(scope="module")
def mapping_mar():
    return read_raw("gp-reg-pat-prac-map-03-2026.csv", RAW_2026_03)


# --------------------------------------------------------------------------------------
# ORG_TYPE -> org_level
# --------------------------------------------------------------------------------------

def test_org_type_vocabulary_covers_every_june_2026_token(nhs_rate, la_rate, sub_icb, practice):
    seen = set()
    for df in (nhs_rate, la_rate, sub_icb, practice):
        seen |= set(df["ORG_TYPE"].unique())
    unmapped = seen - set(ORG_LEVEL_BY_ORG_TYPE)
    assert not unmapped, f"ORG_TYPE tokens in the raw data with no org_level mapping: {unmapped}"


def test_org_type_maps_to_expected_level_per_file(nhs_rate, la_rate, sub_icb, practice):
    # nhs_rate carries the four NHS levels under its own vocabulary.
    nhs_levels = {to_org_level(t) for t in nhs_rate["ORG_TYPE"].unique()}
    assert nhs_levels == {"country", "nhs_region", "icb", "sub_icb"}
    # la_rate carries local-government geography plus England.
    la_levels = {to_org_level(t) for t in la_rate["ORG_TYPE"].unique()}
    assert la_levels == {"country", "gor", "utla", "ltla"}
    # The consolidated and practice files are single-level.
    assert {to_org_level(t) for t in sub_icb["ORG_TYPE"].unique()} == {"sub_icb"}
    assert {to_org_level(t) for t in practice["ORG_TYPE"].unique()} == {"practice"}


def test_gor_and_nhs_region_are_genuinely_different_entity_sets(nhs_rate, la_rate):
    # The reason GOR is not collapsed into nhs_region: 9 GORs vs 7 NHS regions.
    gors = la_rate.loc[la_rate["ORG_TYPE"] == "GOR", "ONS_CODE"].nunique()
    nhs_regions = nhs_rate.loc[nhs_rate["ORG_TYPE"] == "NHS_REGION", "ORG_CODE"].nunique()
    assert gors == 9
    assert nhs_regions == 7


def test_unknown_org_type_raises_instead_of_passing_through():
    with pytest.raises(KeyError):
        to_org_level("PCN")


# --------------------------------------------------------------------------------------
# England alias
# --------------------------------------------------------------------------------------

def test_england_is_coded_inconsistently_across_the_rate_files(nhs_rate, la_rate):
    nhs_eng = nhs_rate[nhs_rate["ORG_TYPE"] == "COUNTRY_RESPONSIBILITY"]
    assert set(nhs_eng["ORG_CODE"]) == {ENGLAND_ODS_CODE}
    # The defect the alias exists for: nhs_rate's ONS_CODE for England is not an ONS code.
    assert set(nhs_eng["ONS_CODE"]) == {ENGLAND_ODS_CODE}
    la_eng = la_rate[la_rate["ORG_TYPE"] == "COUNTRY_GEOGRAPHICAL"]
    assert set(la_eng["ONS_CODE"]) == {ENGLAND_ONS_CODE}


def test_normalise_ons_code_unifies_england_and_touches_nothing_else(la_rate):
    assert normalise_ons_code("ENG") == ENGLAND_ONS_CODE
    assert is_england("ENG") and is_england(ENGLAND_ONS_CODE)
    # Every real ONS code in la_rate passes through unchanged.
    codes = la_rate["ONS_CODE"].unique()
    assert all(normalise_ons_code(c) == c for c in codes)


# --------------------------------------------------------------------------------------
# LTLA ONS code reissue (2025-08)
# --------------------------------------------------------------------------------------

def test_june_2026_ltlas_use_the_reissued_codes(la_rate):
    ltla_codes = set(la_rate.loc[la_rate["ORG_TYPE"] == "LTLA", "ONS_CODE"])
    assert len(ltla_codes) == 296
    assert set(LTLA_ONS_CODE_REISSUES.values()) <= ltla_codes, "reissued codes missing"
    assert not (set(LTLA_ONS_CODE_REISSUES) & ltla_codes), "pre-reissue codes still present"


def test_canonical_ltla_ons_code_is_identity_except_for_the_reissued_pair(la_rate):
    assert canonical_ltla_ons_code("E08000016") == "E08000038"
    assert canonical_ltla_ons_code("E08000019") == "E08000039"
    ltla_codes = la_rate.loc[la_rate["ORG_TYPE"] == "LTLA", "ONS_CODE"].unique()
    assert all(canonical_ltla_ons_code(c) == c for c in ltla_codes)


# --------------------------------------------------------------------------------------
# ICB reorganisation (2026-06)
# --------------------------------------------------------------------------------------

def test_june_2026_icb_set_reflects_the_reorganisation(nhs_rate, mapping):
    icbs = set(nhs_rate.loc[nhs_rate["ORG_TYPE"] == "ICB", "ORG_CODE"])
    assert len(icbs) == 36
    assert ICB_CODES_INTRODUCED_2026_06 <= icbs, "new ICB codes missing from June release"
    assert not (ICB_CODES_RETIRED_2026_06 & icbs), "retired ICB codes still in June release"
    # The mapping file agrees with the rate file on the ICB universe.
    assert set(mapping["ICB_CODE"]) - {"NULL"} == icbs


def test_sub_icb_reassignments_match_the_june_mapping_file(mapping):
    # For every reassigned Sub-ICB, the June mapping must place it under the NEW ICB.
    pairs = (mapping[["SUB_ICB_LOCATION_CODE", "ICB_CODE"]]
             .drop_duplicates()
             .set_index("SUB_ICB_LOCATION_CODE")["ICB_CODE"])
    for sub, (_, new) in SUB_ICB_ICB_REASSIGNMENTS_2026_06.items():
        assert pairs.get(sub) == new, f"Sub-ICB {sub}: mapping says {pairs.get(sub)}, crosswalk says {new}"


def test_sub_icb_code_churn_at_the_boundary(sub_icb):
    codes = set(sub_icb["ODS_CODE"])
    assert len(codes) == 106
    assert SUB_ICB_CODES_INTRODUCED_2026_06 <= codes
    assert not (SUB_ICB_CODES_RETIRED_2026_06 & codes)


def test_every_reassignment_lands_on_a_new_icb_and_leaves_a_retired_one():
    for sub, (old, new) in SUB_ICB_ICB_REASSIGNMENTS_2026_06.items():
        assert old in ICB_CODES_RETIRED_2026_06, f"{sub}: old parent {old} not marked retired"
        assert new in ICB_CODES_INTRODUCED_2026_06, f"{sub}: new parent {new} not a new code"


def test_icb_successor_lookups():
    # Splits are real: these two retired ICBs each feed two new ICBs, which is why
    # the crosswalk is keyed on Sub-ICB rather than being an ICB-to-ICB rename table.
    assert icb_successors("QJG") == {"D7T5G", "T6Y0W"}
    assert icb_successors("QM7") == {"D7T5G", "S1Y5D"}
    # QNQ is retired but none of its Sub-ICBs survive the boundary in the local data.
    assert icb_successors("QNQ") == frozenset()


def test_new_icb_for_sub_icb_handles_moved_and_unmoved_practices():
    assert new_icb_for_sub_icb("06Q", "QH8") == "D7T5G"
    # Unreassigned Sub-ICBs keep their parent.
    assert new_icb_for_sub_icb("16C", "QHM") == "QHM"
    # Disagreement between caller and crosswalk is an error, not a guess.
    with pytest.raises(ValueError):
        new_icb_for_sub_icb("06Q", "QHM")


# --------------------------------------------------------------------------------------
# Era-A side of every boundary, re-derived from the March 2026 release
# --------------------------------------------------------------------------------------

def test_era_a_org_type_vocabulary_is_covered(cog_imp_mar, nhs_rate_mar, la_rate_mar):
    # The Era-A multi-level measure files use a third vocabulary for the same levels.
    assert set(cog_imp_mar["ORG_TYPE"]) == {"COUNTRY", "REGION", "ICB", "SUB_ICB"}
    assert ({to_org_level(t) for t in cog_imp_mar["ORG_TYPE"].unique()}
            == {to_org_level(t) for t in nhs_rate_mar["ORG_TYPE"].unique()}
            == {"country", "nhs_region", "icb", "sub_icb"})
    seen = set(nhs_rate_mar["ORG_TYPE"]) | set(la_rate_mar["ORG_TYPE"]) | set(cog_imp_mar["ORG_TYPE"])
    assert not (seen - set(ORG_LEVEL_BY_ORG_TYPE))


def test_england_alias_holds_in_era_a(cog_imp_mar, nhs_rate_mar):
    eng = cog_imp_mar[cog_imp_mar["ORG_TYPE"] == "COUNTRY"]
    assert set(eng["ORG_CODE"]) == {ENGLAND_ODS_CODE}
    assert set(eng["ONS_CODE"]) == {ENGLAND_ONS_CODE}   # the Era-A measure files get it right
    nhs_eng = nhs_rate_mar[nhs_rate_mar["ORG_TYPE"] == "COUNTRY_RESPONSIBILITY"]
    assert set(nhs_eng["ONS_CODE"]) == {ENGLAND_ODS_CODE}   # nhs_rate gets it wrong in Era A too


def test_march_2026_icb_set_is_the_pre_reorg_universe(nhs_rate_mar, mapping_mar):
    latest = nhs_rate_mar[nhs_rate_mar["ACH_DATE"] == "31-Mar-26"]
    icbs = set(latest.loc[latest["ORG_TYPE"] == "ICB", "ORG_CODE"])
    assert len(icbs) == 42
    assert ICB_CODES_RETIRED_2026_06 <= icbs, "codes marked retired were not in March"
    assert not (ICB_CODES_INTRODUCED_2026_06 & icbs), "codes marked new already existed in March"
    assert set(mapping_mar["ICB_CODE"]) == icbs
    # The ICB set is stable across all 13 Era-A periods - the churn is at the boundary only.
    per_period = nhs_rate_mar[nhs_rate_mar["ORG_TYPE"] == "ICB"].groupby("ACH_DATE")["ORG_CODE"].agg(set)
    assert all(codes == icbs for codes in per_period)


def test_sub_icb_reassignments_match_the_march_mapping_file(mapping_mar, mapping):
    old_parent = (mapping_mar[["SUB_ICB_LOCATION_CODE", "ICB_CODE"]].drop_duplicates()
                  .set_index("SUB_ICB_LOCATION_CODE")["ICB_CODE"])
    new_parent = (mapping[["SUB_ICB_LOCATION_CODE", "ICB_CODE"]].drop_duplicates()
                  .set_index("SUB_ICB_LOCATION_CODE")["ICB_CODE"])
    for sub, (old, _) in SUB_ICB_ICB_REASSIGNMENTS_2026_06.items():
        assert old_parent.get(sub) == old, f"Sub-ICB {sub}: March mapping says {old_parent.get(sub)}"
    # Completeness: every Sub-ICB in BOTH releases whose parent changed is in the table,
    # and nothing that kept its parent is.
    both = old_parent.index.intersection(new_parent.index)
    changed = {s for s in both if old_parent[s] != new_parent[s]}
    assert changed == set(SUB_ICB_ICB_REASSIGNMENTS_2026_06)
    for s in set(both) - changed:
        assert new_icb_for_sub_icb(s, old_parent[s]) == new_parent[s]


def test_sub_icb_churn_old_side(nhs_rate_mar, mapping_mar):
    latest = nhs_rate_mar[nhs_rate_mar["ACH_DATE"] == "31-Mar-26"]
    subs = set(latest.loc[latest["ORG_TYPE"] == "SUB_ICB_LOC", "ORG_CODE"])
    assert len(subs) == 106
    assert SUB_ICB_CODES_RETIRED_2026_06 <= subs
    assert not (SUB_ICB_CODES_INTRODUCED_2026_06 & subs)
    # The retired Sub-ICB's parent was itself retired - which is why that ICB has no
    # observable successor in icb_successors().
    parent = mapping_mar.loc[mapping_mar["SUB_ICB_LOCATION_CODE"] == "D4U1Y", "ICB_CODE"].unique()
    assert len(parent) == 1 and parent[0] in ICB_CODES_RETIRED_2026_06


def test_ltla_reissue_happens_at_2025_08_inside_the_march_release(la_rate_mar):
    ltla = la_rate_mar[la_rate_mar["ORG_TYPE"] == "LTLA"].copy()
    ltla["period"] = period(ltla["ACH_DATE"])
    by_period = ltla.groupby("period")["ONS_CODE"].agg(set).sort_index()
    assert len(by_period) == 13
    assert all(len(codes) == 296 for codes in by_period)
    old, new = set(LTLA_ONS_CODE_REISSUES), set(LTLA_ONS_CODE_REISSUES.values())
    for p, codes in by_period.items():
        if p < "2025-08":
            assert old <= codes and not (new & codes), p
        else:
            assert new <= codes and not (old & codes), p
    # After canonicalising, the LTLA set is identical in every period.
    canonical = {frozenset(canonical_ltla_ons_code(c) for c in codes) for codes in by_period}
    assert len(canonical) == 1
