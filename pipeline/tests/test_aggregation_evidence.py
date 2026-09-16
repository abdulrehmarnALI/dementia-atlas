"""Evidence for the aggregation rule, re-derived from the March 2026 release.

Era B publishes Sub-ICB measures at Sub-ICB level only, so ICB / Region / England
figures for those measures have to be computed. Era A published all four levels,
which makes it the only place the "sum the Sub-ICBs" rule can be checked against
what NHS England itself published. These tests pin what that check found, so the
aggregation module can rely on it and so a future release that behaves differently
fails loudly.

Findings (all at the release's own 13 periods, plain pandas):
- England == sum of published Regions EXACTLY, for every measure in every
  multi-level file.
- Region == sum of published ICBs EXACTLY for the incidence/onset/delirium and
  comorbidity/palliative files - but NOT for MCI (cognitive impairment), where only
  ~11% of groups match and the rest differ by up to 13 patients in both directions.
- ICB == sum of published Sub-ICBs EXACTLY for the register-type measures
  (DEMENTIA_REGISTER, DEMENTIA_REGISTER_65_PLUS, PAT_LIST_ALL, and nhs_rate's
  DEMENTIA_REGISTER_65_PLUS).
- ICB != sum of published Sub-ICBs for the other measures (INCIDENCE, DELIRIUM_12M,
  YOUNG_ONSET, PALLIATIVE_CARE, COMORBIDITIES, MCI): between half and 85% of the
  groups match, the rest differ by small amounts in both directions (|gap| <= 15
  patients, <= 5.3% of the published figure for the non-MCI measures, mean ~0).
  Cause not determinable from the data.

Rule the aggregation module may rely on: summing Sub-ICBs reproduces published
figures exactly for register/list-size measures and only approximately for the
rest - computed aggregates for those must be marked as computed.
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

PIPELINE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPELINE_DIR))

RAW = PIPELINE_DIR / "data" / "raw" / "pcdd" / "2026-03"

REGISTER_MEASURES = {"DEMENTIA_REGISTER", "DEMENTIA_REGISTER_65_PLUS", "PAT_LIST_ALL"}
MAX_RELATIVE_GAP_NON_REGISTER = 0.06


def read_raw(filename: str) -> pd.DataFrame:
    return pd.read_csv(RAW / filename, dtype=str, keep_default_na=False, encoding="utf-8-sig")


@pytest.fixture(scope="module")
def hierarchy():
    """Sub-ICB -> ICB -> Region per period, from the age/sex file's own columns."""
    h = read_raw("pcdem-sicbl-age-sex-mar-2026.csv")[
        ["ACH_DATE", "REGION_ODS_CODE", "ICB_ODS_CODE", "SUB_ICB_ODS_CODE"]].drop_duplicates()
    assert h.groupby(["ACH_DATE", "SUB_ICB_ODS_CODE"]).size().max() == 1
    assert h.groupby(["ACH_DATE", "ICB_ODS_CODE"])["REGION_ODS_CODE"].nunique().max() == 1
    return h


def multi_level(filename, value_col="Value", measure_col="Measure"):
    df = read_raw(filename).rename(columns={value_col: "value", measure_col: "measure"})
    df["num"] = pd.to_numeric(df["value"], errors="coerce")
    df["suppressed"] = df["value"] == "*"
    return df


def compare(children: pd.DataFrame, parent_col: str, parents: pd.DataFrame) -> pd.DataFrame:
    """Sum children per (period, measure, parent) and join to the published parent row."""
    summed = children.groupby(["ACH_DATE", "measure", parent_col]).agg(
        partial=("num", "sum"), n_suppressed=("suppressed", "sum")).reset_index()
    parents = parents[parents["measure"].isin(children["measure"].unique())]
    pub = parents[["ACH_DATE", "measure", "ORG_CODE", "num"]].rename(
        columns={"ORG_CODE": parent_col, "num": "published"})
    m = summed.merge(pub, on=["ACH_DATE", "measure", parent_col], how="outer", indicator=True)
    assert (m["_merge"] == "both").all(), "published parent set and child-derived parent set differ"
    m["gap"] = m["published"] - m["partial"]
    return m


INCIDENCE_FILE = "pcdem-sicbl-incidence-onset-delirium-mar-2026.csv"
COMOR_FILE = "pcdem-sicbl-comor-pall-care-mar-2026.csv"
MCI_FILE = "pcdem_sicbl-cog-imp-mar-2026.csv"
FILES = [INCIDENCE_FILE, COMOR_FILE, MCI_FILE]


def icbs_with_region(df, hierarchy):
    icb2reg = hierarchy[["ACH_DATE", "ICB_ODS_CODE", "REGION_ODS_CODE"]].drop_duplicates()
    icbs = df[df["ORG_TYPE"] == "ICB"].merge(icb2reg, left_on=["ACH_DATE", "ORG_CODE"],
                                             right_on=["ACH_DATE", "ICB_ODS_CODE"])
    assert not icbs["suppressed"].any()
    return icbs


@pytest.mark.parametrize("filename", [INCIDENCE_FILE, COMOR_FILE])
def test_region_is_exactly_the_sum_of_published_icbs(hierarchy, filename):
    df = multi_level(filename)
    m = compare(icbs_with_region(df, hierarchy), "REGION_ODS_CODE", df[df["ORG_TYPE"] == "REGION"])
    assert (m["gap"] == 0).all()


def test_mci_region_is_only_approximately_the_sum_of_published_icbs(hierarchy):
    df = multi_level(MCI_FILE)
    m = compare(icbs_with_region(df, hierarchy), "REGION_ODS_CODE", df[df["ORG_TYPE"] == "REGION"])
    assert (m["gap"] != 0).any()
    assert m["gap"].abs().max() <= 15
    assert (m["gap"].abs() / m["published"]).max() <= MAX_RELATIVE_GAP_NON_REGISTER
    assert abs(m["gap"].mean()) < 0.5


@pytest.mark.parametrize("filename", FILES)
def test_england_is_exactly_the_sum_of_published_regions(filename):
    df = multi_level(filename)
    regions = df[df["ORG_TYPE"] == "REGION"].assign(ENG="ENG")
    m = compare(regions, "ENG", df[df["ORG_TYPE"] == "COUNTRY"])
    assert (m["gap"] == 0).all()


def test_icb_is_exactly_the_sum_of_sub_icbs_for_register_measures(hierarchy):
    for filename in FILES[:2]:
        df = multi_level(filename)
        subs = df[(df["ORG_TYPE"] == "SUB_ICB") & df["measure"].isin(REGISTER_MEASURES)].merge(
            hierarchy, left_on=["ACH_DATE", "ORG_CODE"], right_on=["ACH_DATE", "SUB_ICB_ODS_CODE"])
        m = compare(subs, "ICB_ODS_CODE", df[df["ORG_TYPE"] == "ICB"])
        assert len(m) > 0 and (m["gap"] == 0).all(), filename
    # nhs_rate's headline register, too.
    nhs = multi_level("pcdem-nhs-rate-mar-2026.csv", value_col="VALUE", measure_col="MEASURE")
    nhs = nhs[nhs["measure"] == "DEMENTIA_REGISTER_65_PLUS"]
    subs = nhs[nhs["ORG_TYPE"] == "SUB_ICB_LOC"].merge(
        hierarchy, left_on=["ACH_DATE", "ORG_CODE"], right_on=["ACH_DATE", "SUB_ICB_ODS_CODE"])
    m = compare(subs, "ICB_ODS_CODE", nhs[nhs["ORG_TYPE"] == "ICB"])
    assert len(m) == 13 * 42 and (m["gap"] == 0).all()


def test_icb_is_only_approximately_the_sum_of_sub_icbs_for_other_measures(hierarchy):
    """Pins the tolerance. If a release ever makes these exact, this test should be
    revisited - it would mean the publisher's method changed."""
    seen_inexact = False
    for filename in FILES[:2]:
        df = multi_level(filename)
        subs = df[(df["ORG_TYPE"] == "SUB_ICB") & ~df["measure"].isin(REGISTER_MEASURES)].merge(
            hierarchy, left_on=["ACH_DATE", "ORG_CODE"], right_on=["ACH_DATE", "SUB_ICB_ODS_CODE"])
        m = compare(subs, "ICB_ODS_CODE", df[df["ORG_TYPE"] == "ICB"])
        assert (m["n_suppressed"] == 0).all()   # no suppression to explain the gaps away
        rel = (m["gap"].abs() / m["published"])
        assert rel.max() <= MAX_RELATIVE_GAP_NON_REGISTER, filename
        assert m["gap"].abs().max() <= 11, filename
        assert abs(m["gap"].mean()) < 0.5, filename      # noise, not bias
        seen_inexact |= (m["gap"] != 0).any()
    assert seen_inexact
    # MCI: same picture at ICB level, on the groups with no suppressed inputs.
    df = multi_level(MCI_FILE)
    subs = df[df["ORG_TYPE"] == "SUB_ICB"].merge(
        hierarchy, left_on=["ACH_DATE", "ORG_CODE"], right_on=["ACH_DATE", "SUB_ICB_ODS_CODE"])
    m = compare(subs, "ICB_ODS_CODE", df[df["ORG_TYPE"] == "ICB"])
    clean = m[m["n_suppressed"] == 0]
    assert 0.8 <= (clean["gap"] == 0).mean() < 1.0
    assert clean["gap"].abs().max() <= 15 and abs(clean["gap"].mean()) < 0.5


def test_nhs_rate_estimate_sums_within_rounding_and_rate_is_register_over_estimate(hierarchy):
    nhs = multi_level("pcdem-nhs-rate-mar-2026.csv", value_col="VALUE", measure_col="MEASURE")
    est = nhs[nhs["measure"] == "DEMENTIA_ESTIMATE_65_PLUS"]
    subs = est[est["ORG_TYPE"] == "SUB_ICB_LOC"].merge(
        hierarchy, left_on=["ACH_DATE", "ORG_CODE"], right_on=["ACH_DATE", "SUB_ICB_ODS_CODE"])
    m = compare(subs, "ICB_ODS_CODE", est[est["ORG_TYPE"] == "ICB"])
    assert m["gap"].abs().max() < 0.5            # estimates are published to 1 dp

    wide = nhs.pivot_table(index=["ACH_DATE", "ORG_TYPE", "ORG_CODE"], columns="measure",
                           values="num", aggfunc="first")
    calc = wide["DEMENTIA_REGISTER_65_PLUS"] / wide["DEMENTIA_ESTIMATE_65_PLUS"] * 100
    diff = (calc - wide["DIAG_RATE_65_PLUS"]).abs()
    assert (diff <= 0.06).all()                   # rate published to 1 dp
