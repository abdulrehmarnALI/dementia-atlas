import AtlasMap from "@/components/AtlasMap";
import { pool } from "@/lib/db";
import type { DiagnosisRate } from "@/types/atlas";

// the page reads ?level= from the url and hands it to the map
export default async function Home({
  searchParams,
}: {
  searchParams: Promise<{ level?: string }>;
}) {
  const { level = "sub_icb" } = await searchParams;
  const result = await pool.query<DiagnosisRate>(
    `
      select
        org_code as code,
        diag_rate as rate
      from gold.diagnosis_rate
      where period_end = $1
        and org_level = $2
      order by org_code;
    `,
    ["2026-06-30", level],
  );

  const values = result.rows;

  return (
    <main>
      <AtlasMap level={level} values={values} />
    </main>
  );
}
