import { pool } from "@/lib/db";
import { NextResponse } from "next/server";

type URLParams = {
  level: string;
  vintage: string;
};

const VALID_LEVELS: readonly string[] = [
  "sub_icb",
  "icb",
  "nhs_region",
  "gor",
  "ltla",
  "utla",
];

export async function GET(
  _request: Request,
  { params }: { params: Promise<URLParams> },
) {
  const { level, vintage } = await params;

  // validation
  if (!VALID_LEVELS.includes(level)) {
    return NextResponse.json(
      { error: "Invalid level. Expected one of: " + VALID_LEVELS.join(", ") },
      { status: 400 },
    );
  }

  const VINTAGE_REGEX = /^\d{4}-\d{2}$/;
  if (!VINTAGE_REGEX.test(vintage)) {
    return NextResponse.json(
      { error: "Invalid vintage. Expected format: YYYY-MM" },
      { status: 400 },
    );
  }

  // query

  const result = await pool.query(
    `select json_build_object(
  'type', 'FeatureCollection',
  'features', json_agg(
    json_build_object(
      'type', 'Feature',
      'properties', json_build_object(
        'code', org_code,
        'name', name_in_boundary_file
      ),
      'geometry', ST_AsGeoJSON(geom_web, 5)::json
    )
    order by org_code
  )
) as fc
from gold.geometry
where org_level = $1
  and boundary_version = $2;`,
    [level, vintage],
  );
  // interpret query result
  if (result.rows[0].fc.features === null) {
    return NextResponse.json(
      { error: "No geometry found for the specified level and vintage" },
      { status: 404 },
    );
  }

  // response
  return NextResponse.json(result.rows[0].fc, {
    headers: { "Cache-Control": "public, max-age=86400" },
  });
}
