import { NextResponse } from "next/server";
import { pool } from "@/lib/db";

export const dynamic = "force-dynamic";

export async function GET() {
  const { rows } = await pool.query(`
        SELECT period,
        period_end:: text AS period_end,
        publication_era,
        boundary_version_nhs
        FROM gold.period
        ORDER BY period;
        `);
  return NextResponse.json(rows);
}
