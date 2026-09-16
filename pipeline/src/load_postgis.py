"""Load the gold Parquet tables into PostGIS.

    python -m src.load_postgis                    # DATABASE_URL from the environment
    python -m src.load_postgis postgresql://...   # or given explicitly

Applies ``db/schema.sql`` (drops and recreates the gold schema), COPYs every gold
table in, builds geometries from their GeoJSON plus a simplified ``geom_web`` for
the browser, and practice points from lat / lon. Idempotent: run it after every
``src.gold`` build.

To run a database locally: ``docker compose -f infra/docker-compose.yml up -d`` and
``DATABASE_URL=postgresql://atlas:atlas@localhost:5434/atlas`` (5434, not 5432 - see
the compose file).
"""

import os
import sys
from pathlib import Path

import pandas as pd
import psycopg

from .gold import GOLD_DIR, GOLD_TABLES

REPO_DIR = Path(__file__).resolve().parents[2]
SCHEMA_SQL = REPO_DIR / "db" / "schema.sql"

# Parquet column -> the order the table expects; the schema's columns minus geom.
_LOAD_COLUMNS = {
    "organisation": ["org_level", "org_code", "ons_code", "name", "parent_org_level", "parent_org_code",
                     "first_period", "last_period", "is_current", "series_break_from"],
    "measure": ["measure_key", "measure", "breakdown", "age", "gender", "ethnicity", "dementia_type",
                "residential_type", "description", "unit", "is_additive", "comparability"],
    "period": ["period_end", "period", "publication_era", "source_release", "dictionary_version",
               "boundary_version_nhs", "n_rows"],
    "observation": ["period_end", "org_level", "org_code", "measure_key", "value", "value_state", "value_lower",
                    "value_upper", "is_derived", "dq_flag", "comparability", "source_release"],
    "diagnosis_rate": ["period_end", "org_level", "org_code", "register_65_plus", "estimate_65_plus", "diag_rate",
                       "diag_rate_ll", "diag_rate_ul", "dq_flag"],
    "series_break": ["scope", "org_level", "org_code", "measure", "breakdown", "effective_from", "kind", "note", "source"],
    "geometry": ["org_level", "org_code", "ons_code", "name_in_boundary_file", "boundary_version", "geometry_geojson"],
    "practice_location": ["practice_code", "practice_name", "postcode", "lat", "lon", "quality", "lsoa",
                          "sub_icb_code", "icb_code", "region_code", "unmapped", "source_release"],
}

# Load order respects foreign keys.
_LOAD_ORDER = ("organisation", "measure", "period", "observation", "diagnosis_rate", "series_break",
               "geometry", "practice_location")

# 0.0005 degrees is roughly 35-50 m in England: invisible at any zoom the app
# shows a whole organisation at, and cuts the BGC polygons to a fraction of their size.
WEB_SIMPLIFY_TOLERANCE_DEG = 0.0005

_POST_LOAD_SQL = f"""
UPDATE gold.geometry
   SET geom = ST_Multi(ST_MakeValid(ST_SetSRID(ST_GeomFromGeoJSON(geometry_geojson), 4326)));
UPDATE gold.geometry
   SET geom_web = ST_Multi(ST_MakeValid(ST_SimplifyPreserveTopology(geom, {WEB_SIMPLIFY_TOLERANCE_DEG})));

UPDATE gold.practice_location
   SET geom = ST_SetSRID(ST_MakePoint(lon, lat), 4326)
 WHERE lat IS NOT NULL AND lon IS NOT NULL;

ANALYZE gold.observation;
ANALYZE gold.diagnosis_rate;
ANALYZE gold.geometry;
"""


def _copy(cur: psycopg.Cursor, table: str, frame: pd.DataFrame) -> None:
    cols = _LOAD_COLUMNS[table]
    frame = frame[cols]
    with cur.copy(f"COPY gold.{table} ({', '.join(cols)}) FROM STDIN") as copy:
        for row in frame.itertuples(index=False, name=None):
            copy.write_row([None if pd.isna(v) else (v.to_pydatetime().date() if isinstance(v, pd.Timestamp) else v)
                            for v in row])


def load(database_url: str, gold_dir: Path = GOLD_DIR) -> dict[str, int]:
    frames = {name: pd.read_parquet(gold_dir / f"{name}.parquet") for name in GOLD_TABLES}
    counts = {}
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(SCHEMA_SQL.read_text(encoding="utf-8"))
            for table in _LOAD_ORDER:
                _copy(cur, table, frames[table])
                counts[table] = len(frames[table])
            cur.execute(_POST_LOAD_SQL)
            cur.execute("SELECT org_level || '@' || boundary_version, count(*) FROM gold.geometry GROUP BY 1 ORDER BY 1")
            counts["geometry_by_level_version"] = dict(cur.fetchall())
            cur.execute("SELECT count(geom) FROM gold.practice_location")
            counts["practice_points"] = cur.fetchone()[0]
        conn.commit()
    return counts


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    url = args[0] if args else os.environ.get("DATABASE_URL")
    if not url:
        print("usage: python -m src.load_postgis [DATABASE_URL]  (or set DATABASE_URL)", file=sys.stderr)
        return 2
    counts = load(url)
    for table, n in counts.items():
        print(f"{table:20s} {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
