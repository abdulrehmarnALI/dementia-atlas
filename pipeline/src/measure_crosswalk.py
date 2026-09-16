"""Era-A measure crosswalk for the PCDD silver layer.

Era A (May 2025, March 2026) encodes *what* is measured and *which category* it is
inside a single ``Measure`` string, with the category vocabulary implied by which file
the row came from (``FEMALE_AGED_65_69`` in the age/sex file, ``WHITE`` in the
ethnicity file, ``MCI_MALE_AGED_40_44`` in the cognitive-impairment file). Era B
(June 2026 onward) makes the same information explicit as a ``MEASURE`` column, a
``BREAKDOWN`` column and five dimension columns.

This module decodes an Era-A ``(family, Measure)`` pair into the Era-B shape so both
eras land on one observation grain. Evidence: ``notebooks/03_cross_release_qa.ipynb``
section 7 (category vocabularies byte-identical across eras; Era-A 65+ age/sex sums
reconcile exactly to the published 65+ register in 106/106 Sub-ICBs; ``ALL_AGED_*``
is exactly ``FEMALE + MALE``).

Deliberately NOT covered here:
- the five diagnosis-rate measures (``nhs_rate`` / ``la_rate``): identical names and
  schema in every release, nothing to crosswalk;
- the Era-A practice-level files (``pcdem-prac-anti-psy``, ``pcdem-prac-ass-plans``):
  whether they are the same measures as Era B's ``PRESCRIBING`` / ``REVIEWS`` is an
  open question (notebook §11, Q4/Q5), so they wait for a decision.
"""

import re
from dataclasses import dataclass

# --------------------------------------------------------------------------------------
# Controlled vocabulary - Era B's own tokens, adopted as the silver vocabulary
# --------------------------------------------------------------------------------------

ALL = "ALL"                 # dimension not broken down on this row
NOT_APPLICABLE = "N/A"      # BREAKDOWN token for a measure that has no breakdown

AGE_BANDS: tuple[str, ...] = (
    "0_39", "40_44", "45_49", "50_54", "55_59", "60_64",
    "65_69", "70_74", "75_79", "80_84", "85_89", "90_PLUS",
)
# Era-A totals that Era B does not publish as a single row. ``65_PLUS`` also appears
# in Era B's practice-file breakdown names, so it is a published token, not invented.
AGE_TOTALS: tuple[str, ...] = ("65_PLUS",)

GENDERS: tuple[str, ...] = ("Female", "Male")

ETHNICITY_CATEGORIES = frozenset({
    "ASIAN_OR_ASIAN_BRITISH", "BLACK_OR_AFRICAN_OR_CARIBBEAN_OR_BLACK_BRITISH",
    "INCONCLUSIVE_ETHNIC_GROUP", "MIXED_OR_MULTIPLE_ETHNIC_GROUPS", "NOT_DEFINED",
    "NOT_STATED", "OTHER_ETHNIC_GROUP", "WHITE",
})
DEMENTIA_TYPE_CATEGORIES = frozenset({
    "ALZHEIMERS_DISEASE", "FRONTOTEMPORAL", "INCONCLUSIVE_DEMENTIA_TYPE", "LEWY_BODY",
    "MIXED_DEMENTIA_TYPES", "OTHER_SPECIFIED_DEMENTIA_TYPES",
    "OTHER_UNSPECIFIED_DEMENTIA_TYPES", "VASCULAR_DEMENTIA",
})
RESIDENTIAL_TYPE_CATEGORIES = frozenset({
    "INCONCLUSIVE_RESIDENTIAL_TYPE", "NO_PERMANENT_ADDRESS", "NURSING_HOME",
    "OTHER_RESIDENTIAL_TYPE", "PRIVATE_RESIDENCE", "RESIDENTIAL_CARE_HOME",
})

# Era B's BREAKDOWN token for the residential-type split is RESIDENCE_TYPE while the
# dimension column is RESIDENTIAL_TYPE. Both spellings are the publisher's.
BREAKDOWN_AGE_GENDER = "AGE_GENDER"
BREAKDOWN_ETHNICITY = "ETHNICITY"
BREAKDOWN_DEMENTIA_TYPE = "DEMENTIA_TYPE"
BREAKDOWN_RESIDENCE_TYPE = "RESIDENCE_TYPE"


def normalise_gender(token: str) -> str:
    """Canonicalise a published gender token to Era B's ``Female`` / ``Male`` / ``ALL``.

    Era A spells gender in upper case inside ``Measure`` strings, and Era B's own
    ``PAT_LIST`` rows use ``FEMALE`` / ``MALE`` while every other measure uses
    ``Female`` / ``Male`` - a casing defect in the June 2026 file.
    """
    upper = token.upper()
    if upper == "FEMALE":
        return "Female"
    if upper == "MALE":
        return "Male"
    if upper == ALL:
        return ALL
    raise ValueError(f"Unknown gender token {token!r}")


# --------------------------------------------------------------------------------------
# The decoded shape
# --------------------------------------------------------------------------------------

@dataclass(frozen=True)
class MeasureKey:
    """One Era-B-shaped measure identity: what is counted, and for which category."""
    measure: str
    breakdown: str
    age: str = ALL
    gender: str = ALL
    ethnicity: str = ALL
    dementia_type: str = ALL
    residential_type: str = ALL


# --------------------------------------------------------------------------------------
# Era-A file families
# --------------------------------------------------------------------------------------

# Family names follow the QA notebook. The stem regexes tolerate the publisher's own
# inconsistencies (``pcdem_sicbl-cog-imp`` uses an underscore where the rest use a
# hyphen).
ERA_A_FAMILY_PATTERNS: dict[str, re.Pattern] = {
    "sicbl_age_sex": re.compile(r"^pcdem[-_]sicbl[-_]age[-_]sex"),
    "sicbl_cog_imp": re.compile(r"^pcdem[-_]sicbl[-_]cog[-_]imp"),
    "sicbl_ethnicity": re.compile(r"^pcdem[-_]sicbl[-_]ethnicity"),
    "sicbl_dem_type": re.compile(r"^pcdem[-_]sicbl[-_]dem[-_]type"),
    "sicbl_res_type": re.compile(r"^pcdem[-_]sicbl[-_]res[-_]type"),
    "sicbl_incidence_onset_delirium": re.compile(r"^pcdem[-_]sicbl[-_]incidence"),
    "sicbl_comor_pall_care": re.compile(r"^pcdem[-_]sicbl[-_]comor"),
}

ERA_A_FAMILIES = frozenset(ERA_A_FAMILY_PATTERNS)


def era_a_family_for_filename(filename: str) -> str | None:
    """Which Era-A measure family a raw CSV belongs to, or None if it is not one
    (rate files, mapping, practice-level files)."""
    for family, pattern in ERA_A_FAMILY_PATTERNS.items():
        if pattern.match(filename):
            return family
    return None


# --------------------------------------------------------------------------------------
# Decoding
# --------------------------------------------------------------------------------------

_AGE_SEX = re.compile(r"^(?P<sex>ALL|FEMALE|MALE)_AGED_(?P<band>\d+_\d+|\d+_PLUS)$")
_MCI_AGE_SEX = re.compile(r"^MCI_(?P<sex>FEMALE|MALE)_AGED_(?P<band>\d+_\d+|\d+_PLUS)$")

# Measures that have no breakdown in either era: the Era-A string is already the
# Era-B MEASURE token.
_PLAIN_MEASURES = frozenset({"DELIRIUM_12M", "INCIDENCE", "YOUNG_ONSET",
                             "PALLIATIVE_CARE", "COMORBIDITIES"})


def decode_era_a_measure(family: str, measure: str) -> MeasureKey:
    """Decode an Era-A ``Measure`` string, given the file family it came from.

    Raises ValueError for anything not in the known vocabulary - a new token in a
    future Era-A archive release needs a deliberate mapping, not a guess.
    """
    if family not in ERA_A_FAMILIES:
        raise ValueError(f"Unknown Era-A family {family!r}")

    if family == "sicbl_age_sex":
        m = _AGE_SEX.match(measure)
        if m and m["band"] in AGE_BANDS:
            return MeasureKey("DEMENTIA_REGISTER", BREAKDOWN_AGE_GENDER,
                              age=m["band"], gender=normalise_gender(m["sex"]))

    elif family == "sicbl_cog_imp":
        m = _MCI_AGE_SEX.match(measure)
        if m and m["band"] in AGE_BANDS:
            return MeasureKey("MCI", BREAKDOWN_AGE_GENDER,
                              age=m["band"], gender=normalise_gender(m["sex"]))

    elif family == "sicbl_ethnicity":
        if measure in ETHNICITY_CATEGORIES:
            return MeasureKey("DEMENTIA_REGISTER", BREAKDOWN_ETHNICITY, ethnicity=measure)

    elif family == "sicbl_dem_type":
        if measure in DEMENTIA_TYPE_CATEGORIES:
            return MeasureKey("DEMENTIA_REGISTER", BREAKDOWN_DEMENTIA_TYPE, dementia_type=measure)

    elif family == "sicbl_res_type":
        if measure in RESIDENTIAL_TYPE_CATEGORIES:
            return MeasureKey("DEMENTIA_REGISTER", BREAKDOWN_RESIDENCE_TYPE, residential_type=measure)

    elif family == "sicbl_incidence_onset_delirium":
        if measure in _PLAIN_MEASURES:
            return MeasureKey(measure, NOT_APPLICABLE)
        if measure == "DEMENTIA_REGISTER":       # all-age register total
            return MeasureKey("DEMENTIA_REGISTER", NOT_APPLICABLE)
        if measure == "PAT_LIST_ALL":            # all-age, all-sex list size
            return MeasureKey("PAT_LIST", NOT_APPLICABLE)

    elif family == "sicbl_comor_pall_care":
        if measure in _PLAIN_MEASURES:
            return MeasureKey(measure, NOT_APPLICABLE)
        if measure == "DEMENTIA_REGISTER_65_PLUS":
            return MeasureKey("DEMENTIA_REGISTER", NOT_APPLICABLE, age="65_PLUS")

    raise ValueError(f"Unknown Era-A Measure {measure!r} in family {family!r}")


def is_derived_all_sex_row(family: str, measure: str) -> bool:
    """True for Era-A ``ALL_AGED_<band>`` rows, which are exactly Female + Male and
    must be recomputed at silver-build time rather than stored (see NOW.md item on
    derived rows)."""
    return family == "sicbl_age_sex" and measure.startswith("ALL_AGED_")


# --------------------------------------------------------------------------------------
# Cross-era comparability, per (measure, breakdown)
# --------------------------------------------------------------------------------------

COMPARABLE = "comparable"                # same concept, values reconcile or are definitional
COMPARABLE_LABELS_ONLY = "labels_only"   # same categories, but Era-A values are suppressed
                                         # (or the denominator differs) so totals will not tie
NOT_COMPARABLE = "not_comparable"        # definition changed at the boundary - do not trend
ERA_A_ONLY = "era_a_only"                # discontinued or unpublished in Era B
ERA_B_ONLY = "era_b_only"                # new in Era B

# Keyed on the decoded (measure, breakdown). Taken from the notebook's §7.2 table.
CROSS_ERA_COMPARABILITY: dict[tuple[str, str], str] = {
    ("DEMENTIA_REGISTER", BREAKDOWN_AGE_GENDER): COMPARABLE,       # 65+ bands only in Era A
    ("DEMENTIA_REGISTER", BREAKDOWN_ETHNICITY): COMPARABLE,
    ("DEMENTIA_REGISTER", BREAKDOWN_DEMENTIA_TYPE): COMPARABLE_LABELS_ONLY,   # ~1% suppressed
    ("DEMENTIA_REGISTER", BREAKDOWN_RESIDENCE_TYPE): COMPARABLE_LABELS_ONLY,  # ~14% suppressed
    ("DEMENTIA_REGISTER", NOT_APPLICABLE): COMPARABLE,             # total = sum of AGE_GENDER
    ("MCI", BREAKDOWN_AGE_GENDER): COMPARABLE_LABELS_ONLY,         # ~1% suppressed
    ("PAT_LIST", NOT_APPLICABLE): COMPARABLE,                      # Era B: sum of AGE_GENDER
    ("PAT_LIST", BREAKDOWN_AGE_GENDER): ERA_B_ONLY,
    ("INCIDENCE", NOT_APPLICABLE): NOT_COMPARABLE,                 # month -> quarter (note 7)
    ("YOUNG_ONSET", NOT_APPLICABLE): COMPARABLE,
    ("DELIRIUM_12M", NOT_APPLICABLE): COMPARABLE,
    ("PALLIATIVE_CARE", NOT_APPLICABLE): COMPARABLE,
    ("COMORBIDITIES", NOT_APPLICABLE): ERA_A_ONLY,
    ("FRAILTY", "*"): ERA_B_ONLY,
    ("PRESCRIBING", "*"): ERA_B_ONLY,      # Era-A practice-level equivalence undecided
    ("REFERRALS", "*"): ERA_B_ONLY,        # explicitly not comparable to earlier (note 6)
}


def cross_era_comparability(measure: str, breakdown: str) -> str:
    """Comparability class for a (measure, breakdown); ``"*"`` entries cover every
    breakdown of that measure."""
    try:
        return CROSS_ERA_COMPARABILITY[(measure, breakdown)]
    except KeyError:
        try:
            return CROSS_ERA_COMPARABILITY[(measure, "*")]
        except KeyError:
            raise KeyError(f"No comparability class for ({measure!r}, {breakdown!r})") from None
