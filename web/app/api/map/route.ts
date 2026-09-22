import { NextRequest, NextResponse } from "next/server";
import { pool } from "@/lib/db";

export const dynamic = "force-dynamic";

const LEVELS = new Set(["sub_icb", "icb", "nhs_region", "ltla", "utla", "gor"]);

// returns a GeoJSON FeatureCollection for one period and one level
// e.g. /api/map?period=2025-06&level=icb
export async function GET(req: NextRequest) {
  const period = req.nextUrl.searchParams.get("period") ?? "2026-06";
  const level = req.nextUrl.searchParams.get("level") ?? "sub_icb";

  // check inputs before they go anywhere near the db
  if (!LEVELS.has(level) || !/^\d{4}-\d{2}$/.test(period)) {
    return NextResponse.json({ error: "bad period or level" }, { status: 400 });
  }

  // postgres builds the whole geojson itself so there's no looping over rows in TS
  // ST_AsGeoJSON(..., 5) = 5 decimal places (~1m), default is 9 which is way bigger than needed
  // the ::json cast matters, without it the geometry comes back as a quoted string
  // coalesce is there because json_agg gives null when nothing matches
  //
  // joins on org_level + org_code together, org_code alone isn't unique
  // (some ONS codes are both an LTLA and a UTLA)
  //
  // only sub_icb and icb have two boundary versions (before/after the 2026 reorg),
  // so only those need matching to the period. everything else has one set.
  // found this when utla came back with 0 rows
  //
  // $1 and $2 are params so nothing from the url gets pasted into the sql
  const { rows } = await pool.query(
    `
    SELECT json_build_object(
      'type', 'FeatureCollection',
      'features', coalesce(json_agg(
        json_build_object(
          'type', 'Feature',
          'properties', json_build_object(
            'org_code',  d.org_code,
            'name',      o.name,
            'diag_rate', d.diag_rate
          ),
          'geometry', ST_AsGeoJSON(g.geom_web, 5)::json
        )
      ), '[]'::json)
    ) AS geojson
    FROM gold.diagnosis_rate d
    JOIN gold.organisation o
      ON o.org_level = d.org_level
     AND o.org_code  = d.org_code
    JOIN gold.period p
      ON p.period_end = d.period_end
    JOIN gold.geometry g
      ON g.org_level = d.org_level
     AND g.org_code  = d.org_code
     AND (g.org_level NOT IN ('sub_icb', 'icb') OR g.boundary_version = p.boundary_version_nhs)
    WHERE p.period = $1
      AND d.org_level = $2
    `,
    [period, level],
  );

  return NextResponse.json(rows[0].geojson);
}
