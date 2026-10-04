import AtlasControls from "@/components/AtlasControls";
import { pool } from "@/lib/db";

import type {
  AreaSnapshot,
  AtlasPeriod,
  EnglandBenchmark,
} from "@/types/atlas";
import AtlasExplorer from "@/components/AtlasExplorer";
import SiteHeader from "@/components/SiteHeader";
import SiteFooter from "@/components/SiteFooter";

// the page reads ?level= and ?period= from the url and uses them to build the map
export default async function Home({
  searchParams,
}: {
  searchParams: Promise<{
    level: string;
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

  const valuesResult = await pool.query<AreaSnapshot>(
    `
    SELECT
      d.org_code AS code,
      o.name,
      d.diag_rate AS rate,
      d.diag_rate_ll AS "rateLower",
      d.diag_rate_ul AS "rateUpper",
      d.register_65_plus AS "recorded65Plus",
      d.estimate_65_plus AS "estimated65Plus",
      d.dq_flag AS "dqFlag"
    FROM gold.diagnosis_rate d
    LEFT JOIN gold.organisation o
      ON o.org_level = d.org_level
      AND o.org_code = d.org_code
    WHERE d.period_end = $1
      AND d.org_level = $2
    ORDER BY d.org_code;
  `,
    [selectedPeriod.period_end, level],
  );

  const englandResult = await pool.query<EnglandBenchmark>(
    `
    SELECT
      diag_rate AS rate,
      diag_rate_ll AS "rateLower",
      diag_rate_ul AS "rateUpper"
    FROM gold.diagnosis_rate
    WHERE period_end = $1
      AND org_level = 'country'
      AND org_code = 'ENG'
    LIMIT 1;
  `,
    [selectedPeriod.period_end],
  );

  const england = englandResult.rows[0] ?? null;

  return (
    <>
      <SiteHeader />
      <main>
        <section>
          <p>Dementia data across England</p>
          <h1>Explore dementia diagnosis across England</h1>
          <p>
            Explore geographic variation and change over time using publicly
            available dementia data.
          </p>
        </section>
        <AtlasControls
          periods={periods}
          selectedPeriod={selectedPeriod.period}
        />
        <AtlasExplorer
          level={level}
          areas={valuesResult.rows}
          england={england}
          boundaryVintage={selectedPeriod.boundary_version_nhs}
        />
      </main>
      <SiteFooter />
    </>
  );
}
