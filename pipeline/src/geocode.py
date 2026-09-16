"""GP practice coordinates from postcodes, via api.postcodes.io.

The mapping snapshots carry every practice's postcode but no coordinates.
``geocode_postcodes`` looks postcodes up in bulk (100 per request, free, no key) and
caches the answers in ``data/raw/geocode/postcodes.parquet``, so a rebuild sends only
postcodes it has never asked about. A postcode the service does not know (terminated,
mistyped) is cached with NA coordinates rather than retried forever.
"""

import json
import urllib.request
from pathlib import Path

import pandas as pd

PIPELINE_DIR = Path(__file__).resolve().parents[1]
CACHE = PIPELINE_DIR / "data" / "raw" / "geocode" / "postcodes.parquet"
BULK_URL = "https://api.postcodes.io/postcodes"
BATCH = 100

CACHE_COLUMNS = {"postcode": "string", "lat": "float64", "lon": "float64", "quality": "Int64", "lsoa": "string"}


def normalise_postcode(postcode: str) -> str:
    return " ".join(str(postcode).upper().split())


def _read_cache(path: Path) -> pd.DataFrame:
    if path.exists():
        return pd.read_parquet(path)
    return pd.DataFrame({c: pd.Series(dtype=t) for c, t in CACHE_COLUMNS.items()})


def _lookup_batch(postcodes: list[str], timeout: int = 60) -> list[dict]:
    body = json.dumps({"postcodes": postcodes}).encode()
    req = urllib.request.Request(BULK_URL, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.load(resp)
    if payload.get("status") != 200:
        raise RuntimeError(f"postcodes.io: {payload}")
    rows = []
    for item in payload["result"]:
        r = item.get("result")
        rows.append({"postcode": normalise_postcode(item["query"]),
                     "lat": r["latitude"] if r else None, "lon": r["longitude"] if r else None,
                     "quality": r["quality"] if r else None, "lsoa": (r or {}).get("codes", {}).get("lsoa")})
    return rows


def geocode_postcodes(postcodes, cache_path: Path = CACHE, fetch: bool = True) -> pd.DataFrame:
    """One row per distinct postcode in ``postcodes``: lat / lon / quality / lsoa, NA
    where unknown. Cached answers are never re-requested."""
    wanted = sorted({normalise_postcode(p) for p in postcodes if isinstance(p, str) and p.strip()})
    cache = _read_cache(cache_path)
    missing = [p for p in wanted if p not in set(cache["postcode"])]
    if missing and fetch:
        new = []
        for i in range(0, len(missing), BATCH):
            new.extend(_lookup_batch(missing[i:i + BATCH]))
        cache = pd.concat([cache, pd.DataFrame(new)], ignore_index=True)
        for col, dt in CACHE_COLUMNS.items():
            cache[col] = cache[col].astype(dt)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache.to_parquet(cache_path, index=False)
    return cache[cache["postcode"].isin(wanted)].reset_index(drop=True)


def practice_locations(mapping: pd.DataFrame, cache_path: Path = CACHE, fetch: bool = True) -> pd.DataFrame:
    """One row per practice from the latest mapping snapshot, with coordinates."""
    latest = mapping.sort_values("source_release").drop_duplicates("practice_code", keep="last")
    latest = latest.assign(postcode=latest["practice_postcode"].map(normalise_postcode))
    coords = geocode_postcodes(latest["postcode"], cache_path, fetch)
    out = latest.merge(coords, on="postcode", how="left")
    cols = ["practice_code", "practice_name", "postcode", "lat", "lon", "quality", "lsoa",
            "sub_icb_code", "icb_code", "region_code", "unmapped", "source_release"]
    return out[cols].sort_values("practice_code").reset_index(drop=True)
