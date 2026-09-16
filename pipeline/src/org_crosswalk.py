"""Organisation crosswalk for the PCDD silver layer.

Everything in this module traces to evidence in ``notebooks/03_cross_release_qa.ipynb``
(sections 8 and 10). Four separate problems are handled:

1. ``ORG_TYPE`` -> controlled ``org_level``. The releases use three different
   vocabularies for the same organisational levels (``SUB_ICB`` vs ``SUB_ICB_LOC``,
   ``REGION`` vs ``NHS_REGION``, three spellings of country).
2. England's identifier alias: ``nhs_rate`` publishes England with the string ``ENG``
   in its ONS_CODE column; every other file uses the real ONS code ``E92000001``.
3. The LTLA ONS code reissue at 2025-08: two authorities keep existing but are
   republished under new ONS codes mid-series.
4. The ICB reorganisation at the 2026-06 era boundary: 42 ICBs become 36, and the
   old -> new relationship is many-to-many (two old ICBs split across new ones), so
   the reliable crosswalk is per Sub-ICB, not per ICB.
"""

# --------------------------------------------------------------------------------------
# 1. ORG_TYPE -> controlled org_level
# --------------------------------------------------------------------------------------

# GOR (9 Government Office Regions, la_rate) is deliberately NOT collapsed into
# nhs_region (7 NHS regions) - they are different entity sets despite both being
# "regions". Likewise LTLA/UTLA stay distinct: 132 ONS codes exist at both tiers
# (unitary authorities), so the tier is part of an organisation's identity.
ORG_LEVEL_BY_ORG_TYPE: dict[str, str] = {
    # England, published under three ORG_TYPE spellings - one entity, one level.
    "COUNTRY": "country",                  # Era-A multi-level measure files
    "COUNTRY_RESPONSIBILITY": "country",   # nhs_rate (all eras)
    "COUNTRY_GEOGRAPHICAL": "country",     # la_rate (all eras)
    # NHS commissioning hierarchy.
    "NHS_REGION": "nhs_region",            # nhs_rate
    "REGION": "nhs_region",                # Era-A multi-level measure files
    "ICB": "icb",                          # nhs_rate + Era-A measure files
    "SUB_ICB_LOC": "sub_icb",              # nhs_rate
    "SUB_ICB": "sub_icb",                  # Era-A measure files + Era-B consolidated file
    "PRACTICE": "practice",                # Era-B practice measures file
    # Local-government geography (la_rate).
    "GOR": "gor",
    "UTLA": "utla",
    "LTLA": "ltla",
}

ORG_LEVELS = frozenset(ORG_LEVEL_BY_ORG_TYPE.values())


def to_org_level(org_type: str) -> str:
    """Map a source ORG_TYPE token to the controlled org_level vocabulary.

    Raises KeyError on anything unrecognised - an unknown ORG_TYPE in a new release
    means the crosswalk needs a decision, not a silent pass-through.
    """
    try:
        return ORG_LEVEL_BY_ORG_TYPE[org_type]
    except KeyError:
        raise KeyError(
            f"Unknown ORG_TYPE {org_type!r}: not in the controlled vocabulary. "
            "A new release has introduced a token this crosswalk has never seen - "
            "add it deliberately, don't coerce it."
        ) from None


# --------------------------------------------------------------------------------------
# 2. England alias
# --------------------------------------------------------------------------------------

ENGLAND_ODS_CODE = "ENG"        # ORG_CODE (and, wrongly, ONS_CODE) in nhs_rate
ENGLAND_ONS_CODE = "E92000001"  # real ONS code, used by la_rate and Era-A files


def normalise_ons_code(code: str) -> str:
    """Return the real ONS code for a published ONS_CODE value.

    Only England is affected: nhs_rate puts the string ``ENG`` in its ONS_CODE
    column. Every other code passes through unchanged.
    """
    return ENGLAND_ONS_CODE if code == ENGLAND_ODS_CODE else code


def is_england(code: str) -> bool:
    return code in (ENGLAND_ODS_CODE, ENGLAND_ONS_CODE)


# --------------------------------------------------------------------------------------
# 3. LTLA ONS code reissue (2025-08)
# --------------------------------------------------------------------------------------

# At 2025-08 two LTLAs are republished under new ONS codes; the LTLA count stays at
# 296 throughout, so this is a recode of continuing authorities, not a boundary change.
LTLA_REISSUE_EFFECTIVE = "2025-08"
LTLA_ONS_CODE_REISSUES: dict[str, str] = {
    "E08000016": "E08000038",
    "E08000019": "E08000039",
}


def canonical_ltla_ons_code(code: str) -> str:
    """Map a pre-2025-08 LTLA ONS code to its reissued successor; identity otherwise."""
    return LTLA_ONS_CODE_REISSUES.get(code, code)


# --------------------------------------------------------------------------------------
# 4. ICB reorganisation (2026-06 era boundary)
# --------------------------------------------------------------------------------------

ICB_REORG_EFFECTIVE = "2026-06"

ICB_CODES_RETIRED_2026_06 = frozenset({
    "QH8", "QHG", "QJG", "QM7", "QMJ", "QMM",
    "QNQ", "QNX", "QRV", "QU9", "QUE", "QXU",
})

ICB_CODES_INTRODUCED_2026_06 = frozenset({
    "D7T5G", "S0E4D", "S1Y5D", "S9B9J", "T6Y0W", "Z9B2Z",
})

# The Sub-ICB set changes by exactly one code at the same boundary (count stays 106).
# Whether U2G6B is D4U1Y recoded, or a genuinely different organisation, is not
# decidable from the local data - do not treat them as a continuous series.
SUB_ICB_CODES_RETIRED_2026_06 = frozenset({"D4U1Y"})
SUB_ICB_CODES_INTRODUCED_2026_06 = frozenset({"U2G6B"})

# The 23 Sub-ICBs whose parent ICB changed at 2026-06, as {sub_icb: (old_icb, new_icb)}.
# This is the authoritative form of the reorganisation: old ICB -> new ICB is
# many-to-many (QJG splits into D7T5G and T6Y0W; QM7 into D7T5G and S1Y5D), so any
# ICB-level series crossing 2026-06 compares different organisations and must be
# rebuilt from Sub-ICBs instead.
SUB_ICB_ICB_REASSIGNMENTS_2026_06: dict[str, tuple[str, str]] = {
    "06Q": ("QH8", "D7T5G"),
    "07G": ("QH8", "D7T5G"),
    "99E": ("QH8", "D7T5G"),
    "99F": ("QH8", "D7T5G"),
    "99G": ("QH8", "D7T5G"),
    "06T": ("QJG", "D7T5G"),
    "07H": ("QM7", "D7T5G"),
    "10Q": ("QU9", "S0E4D"),
    "14Y": ("QU9", "S0E4D"),
    "15A": ("QU9", "S0E4D"),
    "06H": ("QUE", "S1Y5D"),
    "06K": ("QM7", "S1Y5D"),
    "06N": ("QM7", "S1Y5D"),
    "M1J4Y": ("QHG", "S1Y5D"),
    "09D": ("QNX", "S9B9J"),
    "70F": ("QNX", "S9B9J"),
    "97R": ("QNX", "S9B9J"),
    "92A": ("QXU", "S9B9J"),
    "06L": ("QJG", "T6Y0W"),
    "07K": ("QJG", "T6Y0W"),
    "26A": ("QMM", "T6Y0W"),
    "93C": ("QMJ", "Z9B2Z"),
    "W2U3Z": ("QRV", "Z9B2Z"),
}


def icb_successors(old_icb_code: str) -> frozenset[str]:
    """The new ICB codes that absorbed a retired ICB's Sub-ICBs.

    Derived from the Sub-ICB reassignments, so it reflects what the data shows
    rather than an assumed one-to-one recode. May contain more than one code (a
    split), or be empty: QNQ is retired but none of its Sub-ICBs appear on both
    sides of the boundary in the local data, so it has no observable successor.
    """
    return frozenset(
        new for old, new in SUB_ICB_ICB_REASSIGNMENTS_2026_06.values() if old == old_icb_code
    )


def new_icb_for_sub_icb(sub_icb_code: str, old_icb_code: str) -> str:
    """The post-2026-06 parent ICB for a Sub-ICB, given its pre-reorg parent.

    Falls back to the old code when the Sub-ICB was not reassigned - most Sub-ICBs
    kept their parent ICB through the reorganisation.
    """
    reassignment = SUB_ICB_ICB_REASSIGNMENTS_2026_06.get(sub_icb_code)
    if reassignment is None:
        return old_icb_code
    old, new = reassignment
    if old != old_icb_code:
        raise ValueError(
            f"Sub-ICB {sub_icb_code!r} was reassigned from {old!r}, but the caller "
            f"says its pre-reorg parent was {old_icb_code!r} - the source data and "
            "the crosswalk disagree."
        )
    return new
