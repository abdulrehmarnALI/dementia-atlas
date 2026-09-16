"""Load raw PCDD releases into the silver observation model.

One entry point per level of ambition:

- ``load_file``     one raw CSV -> silver rows exactly as published (no derived rows)
- ``load_release``  one release folder -> silver rows, published ALL-sex rows dropped and
                    recomputed (see ``derived_rows``)
- ``build_silver``  every release folder under ``data/raw/pcdd`` -> one frame, with the
                    cross-release revision check applied and "latest release wins"
                    resolution available separately

Families loaded: the two diagnosis-rate files (both eras), the seven Era-A Sub-ICB
measure families, the Era-B consolidated Sub-ICB file and the Era-B practice file.
The Era-A practice-level files are classified but deliberately not loaded
(docs/context.md: practice-level history starts at June 2026). Mapping snapshots are
a dimension table, loaded by ``mapping_loader``.
"""

import re
import warnings
from pathlib import Path

import pandas as pd

from .derived_rows import derive_all_sex_rows, drop_published_all_sex_rows
from .measure_crosswalk import (
    AGE_TOKENS,
    ALL,
    NOT_APPLICABLE,
    cross_era_comparability,
    decode_era_a_measure,
    era_a_family_for_filename,
    normalise_gender,
)
from .org_crosswalk import canonical_ltla_ons_code, normalise_ons_code, to_org_level
from .silver_schema import (
    DIMENSION_COLUMNS,
    SILVER_COLUMNS,
    SILVER_KEY,
    classify_values,
    conform,
    dictionary_version,
    parse_dq_flag,
    parse_period_end,
    publication_era,
)

_RELEASE_NAME = re.compile(r"^\d{4}-\d{2}$")

# --------------------------------------------------------------------------------------
# File classification
# --------------------------------------------------------------------------------------

_OTHER_FAMILY_PATTERNS: dict[str, re.Pattern] = {
    "nhs_rate": re.compile(r"^pcdem-nhs-rate"),
    "la_rate": re.compile(r"^pcdem-la-rate"),
    "sub_icb_consolidated": re.compile(r"^pcdem-sub-icb"),
    "practice_measures": re.compile(r"^pcdem-practice-"),
    "practice_mapping": re.compile(r"^(gp-reg-pat-prac-map|mapping-file)"),
    "practice_data_date": re.compile(r"^pcdem-prac-data-date"),
    "practice_anti_psy": re.compile(r"^pcdem-prac-anti-psy"),
    "practice_ass_plans": re.compile(r"^pcdem-prac-ass-plans"),
}

ERA_A_CATEGORY_FAMILIES = frozenset({"sicbl_age_sex", "sicbl_ethnicity", "sicbl_dem_type", "sicbl_res_type"})
ERA_A_MULTI_LEVEL_FAMILIES = frozenset({"sicbl_cog_imp", "sicbl_incidence_onset_delirium", "sicbl_comor_pall_care"})
RATE_FAMILIES = frozenset({"nhs_rate", "la_rate"})

LOADED_FAMILIES = (RATE_FAMILIES | ERA_A_CATEGORY_FAMILIES | ERA_A_MULTI_LEVEL_FAMILIES
                   | {"sub_icb_consolidated", "practice_measures"})

# Era-B practice file: MEASURE is a roll-up of BREAKDOWN, and the register / list-size
# breakdowns carry an age grouping in their name.
_PRACTICE_AGE_BREAKDOWN = re.compile(r"^(?:DEMENTIA_REGISTER|PAT_LIST)_(?P<age>0_64|65_PLUS)$")


def classify_file(filename: str) -> str | None:
    """Which family a raw CSV belongs to, or None for anything unrecognised."""
    family = era_a_family_for_filename(filename)
    if family:
        return family
    for family, pattern in _OTHER_FAMILY_PATTERNS.items():
        if pattern.match(filename):
            return family
    return None


def read_raw(path: Path) -> pd.DataFrame:
    """Lossless read: strings only, no NA coercion, BOM tolerated."""
    return pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")


# --------------------------------------------------------------------------------------
# Per-family shaping: raw columns -> the silver grain columns + value_raw + dq_raw
# --------------------------------------------------------------------------------------

def _decode_measures(family: str, measures: pd.Series) -> pd.DataFrame:
    keys = {m: decode_era_a_measure(family, m) for m in measures.unique()}
    decoded = measures.map(keys)
    return pd.DataFrame({
        field: decoded.map(lambda key, field=field: getattr(key, field))
        for field in ("measure", "breakdown", *DIMENSION_COLUMNS)
    }, index=measures.index)


def _shape_rate(raw: pd.DataFrame, family: str) -> pd.DataFrame:
    org_level = raw["ORG_TYPE"].map(to_org_level)
    if family == "nhs_rate":
        org_code = raw["ORG_CODE"]
    else:
        # la_rate has no ODS code; the ONS code is the identity, canonicalised across
        # the 2025-08 reissue so a series joins on org_code. The two reissued codes
        # are unitary authorities, which appear at both LTLA and UTLA, so the
        # canonical form applies at every tier. ons_code keeps the published value.
        org_code = raw["ONS_CODE"].map(canonical_ltla_ons_code)
    return pd.DataFrame({
        "period_end": raw["ACH_DATE"],
        "org_level": org_level,
        "org_code": org_code,
        "ons_code": raw["ONS_CODE"].map(normalise_ons_code),
        "measure": raw["MEASURE"],
        "breakdown": NOT_APPLICABLE,
        "age": ALL, "gender": ALL, "ethnicity": ALL, "dementia_type": ALL, "residential_type": ALL,
        "value_raw": raw["VALUE"],
        "dq_raw": raw["DQ"],
    })


def _shape_era_a_category(raw: pd.DataFrame, family: str) -> pd.DataFrame:
    out = pd.DataFrame({
        "period_end": raw["ACH_DATE"],
        "org_level": "sub_icb",
        "org_code": raw["SUB_ICB_ODS_CODE"],
        "ons_code": raw["SUB_ICB_ONS_CODE"],
    })
    out = pd.concat([out, _decode_measures(family, raw["Measure"])], axis=1)
    out["value_raw"] = raw["Value"]
    out["dq_raw"] = ""
    return out


def _shape_era_a_multi_level(raw: pd.DataFrame, family: str) -> pd.DataFrame:
    out = pd.DataFrame({
        "period_end": raw["ACH_DATE"],
        "org_level": raw["ORG_TYPE"].map(to_org_level),
        "org_code": raw["ORG_CODE"],
        "ons_code": raw["ONS_CODE"].map(normalise_ons_code),
    })
    out = pd.concat([out, _decode_measures(family, raw["Measure"])], axis=1)
    out["value_raw"] = raw["Value"]
    out["dq_raw"] = ""
    return out


def _shape_era_b_sub_icb(raw: pd.DataFrame, family: str) -> pd.DataFrame:
    return pd.DataFrame({
        "period_end": raw["ACH_DATE"],
        "org_level": raw["ORG_TYPE"].map(to_org_level),
        "org_code": raw["ODS_CODE"],
        "ons_code": raw["ONS_CODE"].map(normalise_ons_code),
        "measure": raw["MEASURE"],
        "breakdown": raw["BREAKDOWN"],
        "age": raw["AGE"],
        "gender": raw["GENDER"].map(normalise_gender),
        "ethnicity": raw["ETHNICITY"],
        "dementia_type": raw["DEMENTIA_TYPE"],
        "residential_type": raw["RESIDENTIAL_TYPE"],
        "value_raw": raw["VALUE"],
        "dq_raw": "",
    })


def _shape_era_b_practice(raw: pd.DataFrame, family: str) -> pd.DataFrame:
    age = raw["BREAKDOWN"].str.extract(_PRACTICE_AGE_BREAKDOWN)["age"].fillna(ALL)
    unknown = set(age.unique()) - AGE_TOKENS - {ALL}
    if unknown:
        raise ValueError(f"Practice breakdown names decode to unknown age tokens {sorted(unknown)}")
    return pd.DataFrame({
        "period_end": raw["ACH_DATE"],
        "org_level": raw["ORG_TYPE"].map(to_org_level),
        "org_code": raw["ODS_CODE"],
        "ons_code": pd.NA,                # practices have no ONS geography code
        "measure": raw["MEASURE"],
        "breakdown": raw["BREAKDOWN"],
        "age": age,
        "gender": ALL, "ethnicity": ALL, "dementia_type": ALL, "residential_type": ALL,
        "value_raw": raw["VALUE"],
        "dq_raw": "",
    })


def _shaper(family: str):
    if family in RATE_FAMILIES:
        return _shape_rate
    if family in ERA_A_CATEGORY_FAMILIES:
        return _shape_era_a_category
    if family in ERA_A_MULTI_LEVEL_FAMILIES:
        return _shape_era_a_multi_level
    if family == "sub_icb_consolidated":
        return _shape_era_b_sub_icb
    if family == "practice_measures":
        return _shape_era_b_practice
    raise ValueError(f"Family {family!r} is not loaded into silver (yet)")


# --------------------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------------------

def load_file(path: Path, release: str, ingested_at: pd.Timestamp | None = None) -> pd.DataFrame:
    """One raw CSV -> silver rows, exactly as published (no derived rows)."""
    family = classify_file(path.name)
    if family is None:
        raise ValueError(f"Unrecognised raw file {path.name!r}")
    shaped = _shaper(family)(read_raw(path), family)

    values = classify_values(shaped["value_raw"])
    comparability = {
        pair: cross_era_comparability(*pair)
        for pair in shaped[["measure", "breakdown"]].drop_duplicates().itertuples(index=False, name=None)
    }
    out = pd.DataFrame({
        "source_release": release,
        "source_file": path.name,
        "publication_era": publication_era(release),
        "dictionary_version": dictionary_version(release),
        "ingested_at": ingested_at or pd.Timestamp.now(),
        "period_end": parse_period_end(shaped["period_end"]),
        **{col: shaped[col] for col in ("org_level", "org_code", "ons_code", "measure", "breakdown", *DIMENSION_COLUMNS)},
        "value_raw": shaped["value_raw"],
        "value_num": values["value_num"],
        "value_state": values["value_state"],
        "value_num_lower": values["value_num_lower"],
        "value_num_upper": values["value_num_upper"],
        "dq_flag": parse_dq_flag(shaped["dq_raw"]),
        "is_derived": False,
        "comparability": [comparability[p] for p in zip(shaped["measure"], shaped["breakdown"])],
    })
    return conform(out)


def release_files(release_dir: Path) -> list[Path]:
    """The raw CSVs in a release folder that silver currently loads, in name order."""
    return sorted(p for p in release_dir.glob("*.csv") if classify_file(p.name) in LOADED_FAMILIES)


_DICTIONARY_FILE = re.compile(r"^PCDD-(\d{4})-data-dictionary\.xlsx$")


def check_dictionary_version(release_dir: Path, release: str) -> None:
    """Warn if the data dictionary shipped in the release folder is not the one
    ``dictionary_version()`` computes from the release month.

    The computed version assumes one dictionary per financial year; a mid-year
    re-issue would only show up as a differently named file on disk.
    """
    on_disk = [f"PCDD-{m.group(1)}" for p in release_dir.iterdir()
               if (m := _DICTIONARY_FILE.match(p.name))]
    expected = dictionary_version(release)
    if on_disk and on_disk != [expected]:
        warnings.warn(
            f"{release}: dictionary on disk is {on_disk} but dictionary_version() gives "
            f"{expected!r}; rows will carry {expected!r}. Check whether NHS England has "
            "re-issued the dictionary mid-year.", stacklevel=2)


def load_release(release_dir: Path, release: str | None = None,
                 ingested_at: pd.Timestamp | None = None) -> pd.DataFrame:
    """One release folder -> silver rows with all-sex rows derived, not stored."""
    release = release or release_dir.name
    ingested_at = ingested_at or pd.Timestamp.now()
    check_dictionary_version(release_dir, release)
    published = pd.concat(
        [load_file(p, release, ingested_at) for p in release_files(release_dir)], ignore_index=True)
    kept = drop_published_all_sex_rows(published)
    derived = derive_all_sex_rows(kept)
    out = pd.concat([kept, derived], ignore_index=True)
    _assert_unique_key(out, release)
    return conform(out)


def _assert_unique_key(df: pd.DataFrame, label: str) -> None:
    dup = df.duplicated(list(SILVER_KEY), keep=False)
    if dup.any():
        sample = df.loc[dup, list(SILVER_KEY)].head(5).to_dict("records")
        raise ValueError(f"{label}: {int(dup.sum())} rows share a silver key, e.g. {sample}")


# --------------------------------------------------------------------------------------
# Across releases
# --------------------------------------------------------------------------------------

OBSERVATION_KEY = tuple(c for c in SILVER_KEY if c != "source_release")


_REVISION_COLUMNS = ["source_release", "value_raw", "value_num", "value_state"]


def find_revisions(df: pd.DataFrame) -> pd.DataFrame:
    """Observations published by more than one release whose value differs.

    "Differs" means a different ``value_state`` or a different ``value_num`` - so
    ``*`` -> ``3`` is a revision, but ``62`` -> ``62.0`` (a formatting change, which
    Era B's format shift makes plausible) is not. Evidence to date says this is
    always empty (context.md revision policy), so the build fails loudly if it is
    not. Rows are one per (observation, release).
    """
    key = list(OBSERVATION_KEY)
    published = df[~df["is_derived"].astype(bool)]
    overlap = published[published.duplicated(key, keep=False)]
    if overlap.empty:
        return overlap.iloc[0:0][key + _REVISION_COLUMNS]
    # astype(str) keeps NaN missing (pandas 3), which nunique would then ignore - so
    # spell out the missing case before building the signature.
    number = overlap["value_num"].round(9).astype("string").fillna("none")
    signature = overlap["value_state"].astype("string") + "|" + number
    distinct = signature.groupby([overlap[c] for c in key], dropna=False, sort=False).nunique()
    revised_keys = distinct[distinct > 1].reset_index()[key]
    return (overlap.merge(revised_keys, on=key)[key + _REVISION_COLUMNS]
            .sort_values(key + ["source_release"]).reset_index(drop=True))


def overlapping_observations(df: pd.DataFrame) -> int:
    """Number of distinct observations published by more than one release."""
    key = list(OBSERVATION_KEY)
    both = df[df.duplicated(key, keep=False)]
    return int(len(both.drop_duplicates(key)))


def resolve_latest_release(df: pd.DataFrame) -> pd.DataFrame:
    """One row per observation: the most recent source_release wins.

    "Most recent" is a string sort, which is only chronological because releases are
    named ``YYYY-MM`` - so that is checked first.
    """
    releases = df["source_release"].dropna().unique()
    malformed = [r for r in releases if not _RELEASE_NAME.match(str(r))]
    if malformed:
        raise ValueError(f"source_release must be YYYY-MM to sort chronologically; got {malformed}")
    key = list(OBSERVATION_KEY)
    return (df.sort_values(["source_release"], kind="stable")
              .drop_duplicates(key, keep="last")
              .reset_index(drop=True))


def build_silver(raw_root: Path, releases: list[str] | None = None,
                 ingested_at: pd.Timestamp | None = None) -> pd.DataFrame:
    """Every release folder under ``raw_root`` -> one silver frame. Raises if any
    overlapping observation has been revised between releases."""
    ingested_at = ingested_at or pd.Timestamp.now()
    dirs = sorted(p for p in raw_root.iterdir() if p.is_dir() and (releases is None or p.name in releases))
    frames = [load_release(d, d.name, ingested_at) for d in dirs]
    out = pd.concat(frames, ignore_index=True)
    revisions = find_revisions(out)
    if not revisions.empty:
        raise ValueError(
            f"{len(revisions)} revised observations between releases - the no-revision "
            f"assumption no longer holds. First: {revisions.head(3).to_dict('records')}")
    return out


def write_silver(df: pd.DataFrame, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    conform(df).to_parquet(path, index=False)
    return path


def read_silver(path: Path) -> pd.DataFrame:
    return conform(pd.read_parquet(path))
