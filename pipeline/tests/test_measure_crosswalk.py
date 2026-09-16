"""Re-derive the Era-A measure-crosswalk claims from the raw CSVs with plain pandas.

The crosswalk decodes Era-A ``Measure`` strings into Era B's explicit
``MEASURE / BREAKDOWN / AGE / GENDER / ...`` shape. These tests check, independently
of the module, that (a) every Measure string in the March 2026 release is decodable,
(b) the decoded keys land on combinations Era B actually publishes, and (c) the
arithmetic identities that justify treating the two encodings as the same concept
hold in the raw data.
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

PIPELINE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPELINE_DIR))

from src.measure_crosswalk import (  # noqa: E402
    AGE_BANDS,
    ALL,
    CROSS_ERA_COMPARABILITY,
    DEMENTIA_TYPE_CATEGORIES,
    ERA_A_FAMILIES,
    ETHNICITY_CATEGORIES,
    NOT_APPLICABLE,
    RESIDENTIAL_TYPE_CATEGORIES,
    MeasureKey,
    cross_era_comparability,
    decode_era_a_measure,
    era_a_family_for_filename,
    is_derived_all_sex_row,
    normalise_gender,
)

RAW = PIPELINE_DIR / "data" / "raw" / "pcdd"
DIMENSIONS = ["AGE", "GENDER", "ETHNICITY", "DEMENTIA_TYPE", "RESIDENTIAL_TYPE"]


def read_raw(release: str, filename: str, **kw) -> pd.DataFrame:
    return pd.read_csv(RAW / release / filename, dtype=str, keep_default_na=False,
                       encoding="utf-8-sig", **kw)


ERA_A_FILES = {
    "sicbl_age_sex": "pcdem-sicbl-age-sex-mar-2026.csv",
    "sicbl_cog_imp": "pcdem_sicbl-cog-imp-mar-2026.csv",
    "sicbl_ethnicity": "pcdem-sicbl-ethnicity-mar-2026.csv",
    "sicbl_dem_type": "pcdem-sicbl-dem-type-mar-2026.csv",
    "sicbl_res_type": "pcdem-sicbl-res-type-mar-2026.csv",
    "sicbl_incidence_onset_delirium": "pcdem-sicbl-incidence-onset-delirium-mar-2026.csv",
    "sicbl_comor_pall_care": "pcdem-sicbl-comor-pall-care-mar-2026.csv",
}


@pytest.fixture(scope="module")
def era_a():
    return {fam: read_raw("2026-03", f) for fam, f in ERA_A_FILES.items()}


@pytest.fixture(scope="module")
def era_b_sub_icb():
    return read_raw("2026-06", "pcdem-sub-icb-jun-2026.csv")


@pytest.fixture(scope="module")
def era_b_combos(era_b_sub_icb):
    """Every (MEASURE, BREAKDOWN, dims...) Era B publishes, as MeasureKeys, with the
    PAT_LIST gender-casing defect normalised so keys are comparable."""
    cols = ["MEASURE", "BREAKDOWN"] + DIMENSIONS
    rows = era_b_sub_icb[cols].drop_duplicates()
    return {
        MeasureKey(r.MEASURE, r.BREAKDOWN, r.AGE, normalise_gender(r.GENDER),
                   r.ETHNICITY, r.DEMENTIA_TYPE, r.RESIDENTIAL_TYPE)
        for r in rows.itertuples(index=False)
    }


# --------------------------------------------------------------------------------------
# Family detection
# --------------------------------------------------------------------------------------

def test_every_march_2026_csv_is_classified_correctly():
    for fam, filename in ERA_A_FILES.items():
        assert era_a_family_for_filename(filename) == fam
    # Files that are NOT Era-A measure families must come back as None, not mis-filed.
    for other in ("pcdem-nhs-rate-mar-2026.csv", "pcdem-la-rate-mar-2026.csv",
                  "gp-reg-pat-prac-map-03-2026.csv", "pcdem-prac-anti-psy-mar-2026.csv",
                  "pcdem-prac-ass-plans-mar-2026.csv", "pcdem-prac-data-date-mar-2026.csv"):
        assert era_a_family_for_filename(other) is None
    assert set(ERA_A_FILES) == ERA_A_FAMILIES


# --------------------------------------------------------------------------------------
# Decoding coverage
# --------------------------------------------------------------------------------------

def test_every_era_a_measure_string_decodes(era_a):
    for fam, df in era_a.items():
        for measure in df["Measure"].unique():
            decode_era_a_measure(fam, measure)   # raises on anything unknown


def test_measure_key_dimensions_are_the_silver_dimension_columns():
    from dataclasses import fields
    from src.silver_schema import DIMENSION_COLUMNS, SILVER_COLUMNS
    assert tuple(f.name for f in fields(MeasureKey)) == ("measure", "breakdown", *DIMENSION_COLUMNS)
    assert [c for c in SILVER_COLUMNS if c in DIMENSION_COLUMNS] == list(DIMENSION_COLUMNS)


def test_unknown_measure_or_family_raises():
    with pytest.raises(ValueError):
        decode_era_a_measure("sicbl_age_sex", "WHITE")
    with pytest.raises(ValueError):
        decode_era_a_measure("sicbl_ethnicity", "FEMALE_AGED_65_69")
    with pytest.raises(ValueError):
        decode_era_a_measure("practice_anti_psy", "DEM_REGISTER")


def test_decoded_keys_land_on_era_b_published_combinations(era_a, era_b_combos):
    """Every decoded Era-A key either exists in Era B verbatim, or is one of the
    known Era-A-only totals. Nothing else."""
    era_a_only = set()
    for fam, df in era_a.items():
        for measure in df["Measure"].unique():
            if is_derived_all_sex_row(fam, measure):
                continue   # dropped at silver build, never compared to Era B
            key = decode_era_a_measure(fam, measure)
            if key not in era_b_combos:
                era_a_only.add(key)
    assert era_a_only == {
        MeasureKey("DEMENTIA_REGISTER", NOT_APPLICABLE),               # all-age total
        MeasureKey("DEMENTIA_REGISTER", NOT_APPLICABLE, age="65_PLUS"),  # 65+ total
        MeasureKey("PAT_LIST", NOT_APPLICABLE),                        # all-age list size
        MeasureKey("COMORBIDITIES", NOT_APPLICABLE),                   # discontinued
    }


def test_era_a_age_sex_is_65_plus_only_and_era_b_is_all_ages(era_a, era_b_sub_icb):
    bands_a = {decode_era_a_measure("sicbl_age_sex", m).age
               for m in era_a["sicbl_age_sex"]["Measure"].unique()}
    assert bands_a == set(AGE_BANDS[6:])   # 65_69 .. 90_PLUS
    reg_b = era_b_sub_icb[(era_b_sub_icb["MEASURE"] == "DEMENTIA_REGISTER")
                          & (era_b_sub_icb["BREAKDOWN"] == "AGE_GENDER")]
    assert set(reg_b["AGE"]) == set(AGE_BANDS)


# --------------------------------------------------------------------------------------
# Category vocabularies are byte-identical across eras
# --------------------------------------------------------------------------------------

@pytest.mark.parametrize("family, column, expected", [
    ("sicbl_ethnicity", "ETHNICITY", ETHNICITY_CATEGORIES),
    ("sicbl_dem_type", "DEMENTIA_TYPE", DEMENTIA_TYPE_CATEGORIES),
    ("sicbl_res_type", "RESIDENTIAL_TYPE", RESIDENTIAL_TYPE_CATEGORIES),
])
def test_category_vocabulary_identical_in_both_eras(era_a, era_b_sub_icb, family, column, expected):
    a = set(era_a[family]["Measure"])
    b = set(era_b_sub_icb[column]) - {ALL}
    assert a == b == expected


# --------------------------------------------------------------------------------------
# Gender casing
# --------------------------------------------------------------------------------------

def test_era_b_gender_casing_defect_is_confined_to_pat_list_and_normalises(era_b_sub_icb):
    age_gender = era_b_sub_icb[era_b_sub_icb["BREAKDOWN"] == "AGE_GENDER"]
    by_measure = age_gender.groupby("MEASURE")["GENDER"].agg(lambda s: set(s))
    assert by_measure["PAT_LIST"] == {"FEMALE", "MALE"}
    assert by_measure["DEMENTIA_REGISTER"] == {"Female", "Male"}
    assert by_measure["MCI"] == {"Female", "Male"}
    assert set(era_b_sub_icb["GENDER"].map(normalise_gender)) == {"Female", "Male", ALL}
    with pytest.raises(ValueError):
        normalise_gender("Unknown")


# --------------------------------------------------------------------------------------
# Arithmetic evidence that the decoded keys mean the same thing in both eras
# --------------------------------------------------------------------------------------

def test_decoded_65_plus_register_reconciles_to_published_headline_in_both_eras(era_a, era_b_sub_icb):
    """Sum Female + Male over the 65+ bands per Sub-ICB and compare to nhs_rate's
    DEMENTIA_REGISTER_65_PLUS. Exact in 106/106 Sub-ICBs in each era."""
    bands_65 = set(AGE_BANDS[6:])

    # Era A, latest period, via the crosswalk's decoding.
    a = era_a["sicbl_age_sex"]
    a = a[a["ACH_DATE"] == "31-Mar-26"].copy()
    keys = a["Measure"].map(lambda m: decode_era_a_measure("sicbl_age_sex", m))
    a = a[[k.gender != ALL and k.age in bands_65 for k in keys]]
    sum_a = pd.to_numeric(a["Value"]).groupby(a["SUB_ICB_ODS_CODE"]).sum()
    nhs_a = read_raw("2026-03", "pcdem-nhs-rate-mar-2026.csv")
    nhs_a = nhs_a[(nhs_a["ACH_DATE"] == "31-Mar-26") & (nhs_a["ORG_TYPE"] == "SUB_ICB_LOC")
                  & (nhs_a["MEASURE"] == "DEMENTIA_REGISTER_65_PLUS")]
    headline_a = pd.to_numeric(nhs_a["VALUE"]).groupby(nhs_a["ORG_CODE"]).sum()
    joined = pd.concat([sum_a.rename("sum"), headline_a.rename("headline")], axis=1)
    assert len(joined) == 106 and joined.notna().all().all()
    assert (joined["sum"] == joined["headline"]).all()

    # Era B, straight from the dimension columns.
    b = era_b_sub_icb
    b = b[(b["MEASURE"] == "DEMENTIA_REGISTER") & (b["BREAKDOWN"] == "AGE_GENDER") & b["AGE"].isin(bands_65)]
    sum_b = pd.to_numeric(b["VALUE"]).groupby(b["ODS_CODE"]).sum()
    nhs_b = read_raw("2026-06", "pcdem-nhs-rate-jun-2026.csv")
    nhs_b = nhs_b[(nhs_b["ORG_TYPE"] == "SUB_ICB_LOC") & (nhs_b["MEASURE"] == "DEMENTIA_REGISTER_65_PLUS")]
    headline_b = pd.to_numeric(nhs_b["VALUE"]).groupby(nhs_b["ORG_CODE"]).sum()
    joined = pd.concat([sum_b.rename("sum"), headline_b.rename("headline")], axis=1)
    assert len(joined) == 106 and joined.notna().all().all()
    assert (joined["sum"] == joined["headline"]).all()


def test_era_a_65_plus_total_equals_sum_of_65_plus_age_sex_rows(era_a):
    """DEMENTIA_REGISTER_65_PLUS in the comorbidity/palliative file is the same
    quantity as the age/sex file's 65+ sum - which is why it decodes to
    (DEMENTIA_REGISTER, N/A, age=65_PLUS) rather than to a measure of its own."""
    a = era_a["sicbl_age_sex"]
    a = a[(a["ACH_DATE"] == "31-Mar-26") & a["Measure"].str.startswith("ALL_AGED_")]
    from_bands = pd.to_numeric(a["Value"]).groupby(a["SUB_ICB_ODS_CODE"]).sum()
    c = era_a["sicbl_comor_pall_care"]
    c = c[(c["ACH_DATE"] == "31-Mar-26") & (c["ORG_TYPE"] == "SUB_ICB")
          & (c["Measure"] == "DEMENTIA_REGISTER_65_PLUS")]
    total = pd.to_numeric(c["Value"]).groupby(c["ORG_CODE"]).sum()
    joined = pd.concat([from_bands.rename("bands"), total.rename("total")], axis=1)
    assert len(joined) == 106 and joined.notna().all().all()
    assert (joined["bands"] == joined["total"]).all()


# --------------------------------------------------------------------------------------
# Comparability table
# --------------------------------------------------------------------------------------

def test_comparability_covers_every_decoded_and_era_b_measure(era_a, era_b_sub_icb):
    for fam, df in era_a.items():
        for measure in df["Measure"].unique():
            key = decode_era_a_measure(fam, measure)
            cross_era_comparability(key.measure, key.breakdown)
    for measure, breakdown in era_b_sub_icb[["MEASURE", "BREAKDOWN"]].drop_duplicates().itertuples(index=False):
        cross_era_comparability(measure, breakdown)
    with pytest.raises(KeyError):
        cross_era_comparability("DEMENTIA_REGISTER", "POSTCODE")


def test_comparability_classes_match_the_evidence():
    assert cross_era_comparability("INCIDENCE", NOT_APPLICABLE) == "not_comparable"
    assert cross_era_comparability("REFERRALS", "NUM_REF_MEM_CLIN_12M") == "era_b_only"
    assert cross_era_comparability("COMORBIDITIES", NOT_APPLICABLE) == "era_a_only"
    assert cross_era_comparability("DEMENTIA_REGISTER", "RESIDENCE_TYPE") == "labels_only"
    assert cross_era_comparability("DEMENTIA_REGISTER", "AGE_GENDER") == "comparable"
    assert set(CROSS_ERA_COMPARABILITY.values()) <= {
        "comparable", "labels_only", "not_comparable", "era_a_only", "era_b_only"}
