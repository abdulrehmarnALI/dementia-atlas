"""Practice mapping snapshots -> a silver dimension table.

Each release ships one snapshot of practice -> Sub-ICB -> ICB -> NHS region, taken at
an extract date *after* the reporting period. Two facts from the QA notebook shape
this module:

- The snapshot is not a strict superset of the practices measured: a practice that
  closed between period end and extract date is measured but unmappable. So joins
  from observations to this table are LEFT joins, and rows carry an ``unmapped`` flag
  rather than being dropped (docs/context.md decision).
- One June 2026 row carries the literal string ``NULL`` in all three hierarchy
  columns. That is a published sentinel, not a missing value, and becomes
  ``unmapped=True`` with the codes set to NA.

Era A carries PCN and system-supplier columns that Era B dropped; they are kept as
nullable columns so the shape is identical across eras. Names are display strings,
stripped of the stray whitespace the May 2025 file carries, and never joined on.
"""

from pathlib import Path

import pandas as pd

from .silver_schema import parse_dates

NULL_TOKEN = "NULL"

MAPPING_COLUMNS: dict[str, str] = {
    "source_release": "string",
    "source_file": "string",
    "extract_date": "datetime64[ns]",
    "practice_code": "string",
    "practice_name": "string",
    "practice_postcode": "string",
    "pcn_code": "string",            # Era A only
    "pcn_name": "string",            # Era A only
    "sub_icb_code": "string",
    "sub_icb_ons_code": "string",
    "sub_icb_name": "string",
    "icb_code": "string",
    "icb_ons_code": "string",
    "icb_name": "string",
    "region_code": "string",
    "region_ons_code": "string",
    "region_name": "string",
    "supplier_name": "string",       # Era A only
    "unmapped": "boolean",
}

_RENAME = {
    "EXTRACT_DATE": "extract_date",
    "PRACTICE_CODE": "practice_code",
    "PRACTICE_NAME": "practice_name",
    "PRACTICE_POSTCODE": "practice_postcode",
    "PCN_CODE": "pcn_code",
    "PCN_NAME": "pcn_name",
    "SUB_ICB_LOCATION_CODE": "sub_icb_code",
    "ONS_SUB_ICB_LOCATION_CODE": "sub_icb_ons_code",
    "SUB_ICB_LOCATION_NAME": "sub_icb_name",
    "ICB_CODE": "icb_code",
    "ONS_ICB_CODE": "icb_ons_code",
    "ICB_NAME": "icb_name",
    "COMM_REGION_CODE": "region_code",
    "ONS_COMM_REGION_CODE": "region_ons_code",
    "COMM_REGION_NAME": "region_name",
    "SUPPLIER_NAME": "supplier_name",
}

HIERARCHY_CODE_COLUMNS = ("sub_icb_code", "icb_code", "region_code")
_NAME_COLUMNS = ("practice_name", "pcn_name", "sub_icb_name", "icb_name", "region_name", "supplier_name")


def load_mapping(path: Path, release: str) -> pd.DataFrame:
    raw = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    unknown = set(raw.columns) - set(_RENAME) - {"PUBLICATION"}
    if unknown:
        raise ValueError(f"{path.name}: unexpected mapping columns {sorted(unknown)}")
    df = raw.rename(columns=_RENAME)
    for col in MAPPING_COLUMNS:
        if col not in df.columns:
            df[col] = pd.NA
    df["source_release"] = release
    df["source_file"] = path.name
    df["extract_date"] = parse_dates(df["extract_date"])

    hierarchy = df[list(HIERARCHY_CODE_COLUMNS)]
    df["unmapped"] = (hierarchy == NULL_TOKEN).any(axis=1) | (hierarchy == "").any(axis=1)
    for col in HIERARCHY_CODE_COLUMNS + ("sub_icb_ons_code", "icb_ons_code", "region_ons_code"):
        df[col] = df[col].mask(df[col].isin([NULL_TOKEN, ""]), pd.NA)
    for col in _NAME_COLUMNS:
        df[col] = df[col].astype("string").str.strip()

    if df["practice_code"].duplicated().any():
        raise ValueError(f"{path.name}: duplicate practice codes")

    out = df[list(MAPPING_COLUMNS)].copy()
    for col, dt in MAPPING_COLUMNS.items():
        out[col] = out[col].astype(dt)
    return out.reset_index(drop=True)


def hierarchy(mapping: pd.DataFrame) -> pd.DataFrame:
    """Distinct Sub-ICB -> ICB -> region triples from a snapshot, with a check that
    each Sub-ICB has exactly one parent chain (else the snapshot is inconsistent)."""
    h = (mapping.loc[~mapping["unmapped"], ["source_release", *HIERARCHY_CODE_COLUMNS]]
         .drop_duplicates().reset_index(drop=True))
    parents = h.groupby(["source_release", "sub_icb_code"]).size()
    if (parents > 1).any():
        raise ValueError(f"Sub-ICBs with more than one parent chain: {parents[parents > 1].index.tolist()}")
    return h
