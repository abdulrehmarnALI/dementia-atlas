"""Boundaries for every organisation level, from the ONS Open Geography Portal.

Each level needs a polygon set whose codes match the codes silver carries, and the
NHS levels need two sets: the 42-ICB world Era A lives in (April 2023 boundaries)
and the post-reorganisation world (April 2026). ``BOUNDARY_LAYERS`` names them;
``fetch_layer`` downloads a layer once into ``data/raw/boundaries/`` via the portal's
public ArcGIS REST API (no key); ``load_boundaries`` turns the cached files into
gold-shaped geometry rows with ``org_code`` resolved per level.

Resolution rules: local-government levels are keyed by ONS code in silver already
(canonicalised across the 2025-08 reissue); NHS levels are keyed by ODS code, so the
boundary file's ONS code is mapped through every (ons_code, org_code) pair silver has
seen. A polygon that resolves to nothing, or an organisation with no polygon in the
set that should cover it, is an error - that check is also how the right
local-authority year was chosen.
"""

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .org_crosswalk import ENGLAND_ODS_CODE, ENGLAND_ONS_CODE, canonical_ltla_ons_code

PIPELINE_DIR = Path(__file__).resolve().parents[1]
BOUNDARY_DIR = PIPELINE_DIR / "data" / "raw" / "boundaries"
PORTAL = "https://services1.arcgis.com/ESMARspQHYMw9BZ9/arcgis/rest/services/{layer}/FeatureServer/0/query"


@dataclass(frozen=True)
class BoundaryLayer:
    org_level: str
    boundary_version: str     # YYYY-MM of the boundary set
    layer: str                # ONS Open Geography service name
    code_field: str
    name_field: str
    england_only: bool = False   # UK layers: keep E-codes only


BOUNDARY_LAYERS: tuple[BoundaryLayer, ...] = (
    BoundaryLayer("sub_icb", "2026-04", "Sub_Integrated_Care_Board_Locations_April_2026_Boundaries_EN_BGC", "SICBL26CD", "SICBL26NM"),
    BoundaryLayer("sub_icb", "2023-04", "Sub_Integrated_Care_Board_Locations_April_2023_EN_BGC", "SICBL23CD", "SICBL23NM"),
    BoundaryLayer("icb", "2026-04", "Integrated_Care_Boards_April_2026_Boundaries_EN_BGC", "ICB26CD", "ICB26NM"),
    BoundaryLayer("icb", "2023-04", "Integrated_Care_Boards_April_2023_EN_BGC", "ICB23CD", "ICB23NM"),
    BoundaryLayer("nhs_region", "2024-01", "NHS_England_Regions_January_2024_EN_BGC", "NHSER24CD", "NHSER24NM"),
    BoundaryLayer("ltla", "2026-05", "Local_Authority_Districts_May_2026_Boundaries_UK_BGC", "LAD26CD", "LAD26NM", england_only=True),
    BoundaryLayer("utla", "2025-12", "Counties_and_Unitary_Authorities_December_2025_Boundaries_UK_BGC", "CTYUA25CD", "CTYUA25NM", england_only=True),
    BoundaryLayer("gor", "2025-12", "Regions_December_2025_Boundaries_EN_BGC", "RGN25CD", "RGN25NM"),
)

# Which NHS boundary set applies to a reporting period: the reorganisation is
# effective 2026-04, so anything up to 2026-03 is the 42-ICB world.
NHS_BOUNDARY_VERSION_BEFORE = "2023-04"
NHS_BOUNDARY_VERSION_FROM_2026_04 = "2026-04"


def nhs_boundary_version(period: str) -> str:
    """``period`` is YYYY-MM."""
    return NHS_BOUNDARY_VERSION_BEFORE if period < "2026-04" else NHS_BOUNDARY_VERSION_FROM_2026_04


# --------------------------------------------------------------------------------------
# Fetch
# --------------------------------------------------------------------------------------

def cache_path(layer: str) -> Path:
    return BOUNDARY_DIR / f"{layer}.geojson"


def fetch_layer(layer: str, page_size: int = 500, timeout: int = 120) -> Path:
    """Download one layer as GeoJSON (EPSG:4326), paging through the FeatureServer
    query endpoint, and cache it. A cached file is returned without any network."""
    path = cache_path(layer)
    if path.exists():
        return path
    BOUNDARY_DIR.mkdir(parents=True, exist_ok=True)
    features, offset = [], 0
    while True:
        params = {"where": "1=1", "outFields": "*", "f": "geojson", "outSR": "4326",
                  "resultOffset": offset, "resultRecordCount": page_size}
        url = PORTAL.format(layer=layer) + "?" + urllib.parse.urlencode(params)
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            page = json.load(resp)
        if "error" in page:
            raise RuntimeError(f"{layer}: {page['error']}")
        got = page.get("features", [])
        features.extend(got)
        if not got or not page.get("properties", {}).get("exceededTransferLimit", False) and len(got) < page_size:
            break
        offset += len(got)
    if not features:
        raise RuntimeError(f"{layer}: no features returned")
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"type": "FeatureCollection", "features": features}, separators=(",", ":")), encoding="utf-8")
    tmp.replace(path)
    return path


def fetch_all(layers: tuple[BoundaryLayer, ...] = BOUNDARY_LAYERS) -> list[Path]:
    return [fetch_layer(spec.layer) for spec in layers]


# --------------------------------------------------------------------------------------
# Load and resolve
# --------------------------------------------------------------------------------------

def ons_to_org_code(silver: pd.DataFrame) -> dict[tuple[str, str], str]:
    """(org_level, ons_code) -> org_code for every pair silver has ever carried, so a
    boundary keyed on an old or new ONS code both resolve. England resolves to ENG."""
    rows = silver.loc[silver["ons_code"].notna(), ["org_level", "ons_code", "org_code", "source_release"]]
    rows = rows.drop_duplicates(["org_level", "ons_code", "org_code"]).sort_values("source_release")
    rows = rows.drop_duplicates(["org_level", "ons_code"], keep="last")
    lookup = {(r.org_level, r.ons_code): r.org_code for r in rows.itertuples()}
    lookup[("country", ENGLAND_ONS_CODE)] = ENGLAND_ODS_CODE
    return lookup


def _resolve(spec: BoundaryLayer, ons_code: str, lookup: dict) -> str | None:
    if spec.org_level in ("ltla", "utla", "gor"):
        return canonical_ltla_ons_code(ons_code)
    return lookup.get((spec.org_level, ons_code))


def load_boundaries(silver: pd.DataFrame, layers: tuple[BoundaryLayer, ...] = BOUNDARY_LAYERS,
                    fetch: bool = True) -> pd.DataFrame:
    """Every layer as gold ``geometry`` rows. Raises if any polygon does not resolve
    to an organisation silver knows (a code-set mismatch, i.e. the wrong boundary
    year), listing the offending codes."""
    lookup = ons_to_org_code(silver)
    known = set(zip(silver["org_level"], silver["org_code"]))
    rows, problems = [], []
    for spec in layers:
        path = fetch_layer(spec.layer) if fetch else cache_path(spec.layer)
        features = json.load(open(path, encoding="utf-8"))["features"]
        for f in features:
            props = f["properties"]
            ons = props[spec.code_field]
            if spec.england_only and not ons.startswith("E"):
                continue
            org_code = _resolve(spec, ons, lookup)
            if org_code is None or (spec.org_level, org_code) not in known:
                problems.append((spec.org_level, spec.boundary_version, ons, props.get(spec.name_field)))
                continue
            rows.append({
                "org_level": spec.org_level, "org_code": org_code, "ons_code": ons,
                "name_in_boundary_file": props.get(spec.name_field),
                "boundary_version": spec.boundary_version,
                "geometry_geojson": json.dumps(f["geometry"], separators=(",", ":")),
            })
    if problems:
        raise ValueError(f"{len(problems)} boundary polygons resolve to no known organisation, e.g. {problems[:8]}")
    out = pd.DataFrame(rows)
    dup = out.duplicated(["org_level", "ons_code", "boundary_version"], keep=False)
    if dup.any():
        raise ValueError(f"duplicate polygons: {out.loc[dup, ['org_level', 'ons_code', 'boundary_version']].head().to_dict('records')}")
    return out.sort_values(["org_level", "boundary_version", "ons_code"]).reset_index(drop=True)


def coverage(boundaries: pd.DataFrame, silver: pd.DataFrame) -> pd.DataFrame:
    """Per (org_level, boundary_version): organisations silver has at that level in the
    matching era, and how many have a polygon. The tests assert every count."""
    periods = silver["period_end"].dt.strftime("%Y-%m")
    rows = []
    for (level, version), polys in boundaries.groupby(["org_level", "boundary_version"]):
        at_level = silver[silver["org_level"] == level]
        if level in ("sub_icb", "icb"):
            at_level = at_level[periods[at_level.index].map(nhs_boundary_version) == version]
        orgs = set(at_level["org_code"])
        rows.append({"org_level": level, "boundary_version": version, "polygons": len(polys),
                     "organisations": len(orgs), "covered": len(orgs & set(polys["org_code"])),
                     "missing": sorted(orgs - set(polys["org_code"]))[:10]})
    return pd.DataFrame(rows)
