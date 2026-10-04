import type { AreaSnapshot, EnglandBenchmark } from "@/types/atlas";

interface SelectedAreaPanelProps {
  area: AreaSnapshot | null;
  england: EnglandBenchmark | null;
}

export default function SelectedAreaPanel({
  area,
  england,
}: SelectedAreaPanelProps) {
  const difference = area && england ? area.rate - england.rate : null;
  return (
    <aside>
      {!area ? (
        <>
          <h2>Explore an area</h2>
          <p>Select an area on the map to view its dementia data.</p>
        </>
      ) : (
        <>
          <p>{area.code}</p>
          <h2>{area.name}</h2>

          <strong>{area.rate.toFixed(1)}%</strong>
          <p>Estimated dementia diagnosis rate</p>

          {england && (
            <dl>
              <div>
                <dt>England</dt>
                <dd>{england.rate.toFixed(1)}%</dd>
              </div>

              <div>
                <dt>Difference</dt>
                <dd>
                  {difference !== null
                    ? `${difference > 0 ? "+" : ""}${difference.toFixed(1)} pp`
                    : "Unavailable"}
                </dd>
              </div>
            </dl>
          )}

          {area.rateLower != null && area.rateUpper != null && (
            <p>
              95% CI: {area.rateLower.toFixed(1)}%–
              {area.rateUpper.toFixed(1)}%
            </p>
          )}

          <dl>
            <div>
              <dt>Recorded 65+</dt>
              <dd>{area.recorded65Plus?.toLocaleString() ?? "Unavailable"}</dd>
            </div>

            <div>
              <dt>Estimated 65+</dt>
              <dd>{area.estimated65Plus?.toLocaleString() ?? "Unavailable"}</dd>
            </div>
          </dl>

          {area.dqFlag && <p>Data-quality flag applies to this observation.</p>}
        </>
      )}
    </aside>
  );
}
