import AtlasMap from "@/components/AtlasMap";
import AtlasControls from "@/components/AtlasControls";
import { pool } from "@/lib/db";

import type { AtlasPeriod, DiagnosisRate } from "@/types/atlas";

// the page reads ?level= and ?period= from the url and uses them to build the map
export default async function Home({
  searchParams,
}: {
  searchParams: Promise<{
    level?: string;
    period?: string;
  }>;
}) {
  const params = await searchParams;

  const level = params.level ?? "sub_icb";

  const periodsResult = await pool.query<AtlasPeriod>(`
    SELECT
      period,
      period_end::text AS period_end,
      publication_era,
      boundary_version_nhs
    FROM gold.period
    ORDER BY period DESC;
  `);

  const periods = periodsResult.rows;

  // use the requested period if it exists, otherwise default to the latest
  const selectedPeriod =
    periods.find((period) => period.period === params.period) ?? periods[0];

  if (!selectedPeriod) {
    throw new Error("No periods available");
  }

  const valuesResult = await pool.query<DiagnosisRate>(
    `
      SELECT
        org_code AS code,
        diag_rate AS rate
      FROM gold.diagnosis_rate
      WHERE period_end = $1
        AND org_level = $2
      ORDER BY org_code;
    `,
    [selectedPeriod.period_end, level],
  );

  return (
    <main>
      <AtlasControls periods={periods} selectedPeriod={selectedPeriod.period} />
      <AtlasMap
        level={level}
        values={valuesResult.rows}
        // keeps the map boundaries matched to the period being viewed
        boundaryVintage={selectedPeriod.boundary_version_nhs}
      />
    </main>
  );
}
