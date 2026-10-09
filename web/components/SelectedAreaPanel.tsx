import type { AreaSnapshot, EnglandBenchmark } from "@/types/atlas";
import styles from "./SelectedAreaPanel.module.css";
import { Dot, LandPlot, Percent } from "lucide-react";
import type { GeographyLevel } from "@/types/atlas";

interface SelectedAreaPanelProps {
  level: GeographyLevel;
  area: AreaSnapshot | null;
  england: EnglandBenchmark | null;
}

const geographyLevelLabels: Record<GeographyLevel, string> = {
  sub_icb: "Sub-ICB Area",
  icb: "ICB Area",
  nhs_region: "NHS Region",
  gor: "Government Office Region",
  ltla: "Lower-tier Local Authority",
  utla: "Upper-tier Local Authority",
};

function generateAreaName(name: string, code: string) {
  const suffix = ` - ${code}`;
  return name.endsWith(suffix) ? name.slice(0, -suffix.length) : name;
}

interface ConfidenceRangeProps {
  rate: number;
  lower: number;
  upper: number;
  benchmark?: number;
}

function ConfidenceRange({
  rate,
  lower,
  upper,
  benchmark,
}: ConfidenceRangeProps) {
  const values = [
    rate,
    lower,
    upper,
    ...(benchmark != null ? [benchmark] : []),
  ];
  const min = Math.max(0, Math.floor((Math.min(...values) - 5) / 5) * 5);
  const max = Math.min(100, Math.ceil((Math.max(...values) + 5) / 5) * 5);
  const position = (value: number) => ((value - min) / (max - min)) * 100;

  return (
    <figure
      className={styles.ci}
      aria-label={`95% confidence interval: ${lower.toFixed(1)} to ${upper.toFixed(1)} percent`}
    >
      <div className={styles.ciHeader}>
        <figcaption>95% confidence interval</figcaption>
        <span className={styles.ciValues}>
          {lower.toFixed(1)}%–{upper.toFixed(1)}%
        </span>
      </div>

      <div className={styles.ciTrack} aria-hidden="true">
        <div
          className={styles.ciRange}
          style={{
            left: `${position(lower)}%`,
            width: `${position(upper) - position(lower)}%`,
          }}
        />
        <div
          className={styles.ciPoint}
          style={{ left: `${position(rate)}%` }}
        />
        {benchmark != null && (
          <div
            className={styles.ciBenchmark}
            style={{ left: `${position(benchmark)}%` }}
          />
        )}
      </div>

      <div className={styles.ciScale} aria-hidden="true">
        <span>{min}%</span>
        <span>{max}%</span>
      </div>

      <ul className={styles.ciLegend} aria-hidden="true">
        <li>
          <span className={styles.ciKeyPoint} /> Estimate
        </li>
        {benchmark != null && (
          <li>
            <span className={styles.ciKeyBenchmark} /> England
          </li>
        )}
      </ul>
    </figure>
  );
}

export default function SelectedAreaPanel({
  level,
  area,
  england,
}: SelectedAreaPanelProps) {
  const difference = area && england ? area.rate - england.rate : null;
  return (
    <aside className={styles.panel}>
      {!area ? (
        <>
          <div className={styles.emptyState}>
            <LandPlot className={styles.emptyStateIcon} aria-hidden="true" />

            <h2>Explore an area</h2>

            <p>
              Select an area on the map to view its estimated dementia diagnosis
              rate and compare it with England.
            </p>
          </div>

          <div className={styles.projectNotice}>
            <strong>Independent project · Work in progress</strong>
            <p>
              Uses publicly available health data. Not affiliated with or
              endorsed by NHS England or UK DRI.
            </p>
          </div>
        </>
      ) : (
        <>
          {/* Area Identity */}
          <div className={styles.areaCodeContainer}>
            <LandPlot className={styles.areaCodeIcon} aria-hidden="true" />
            <p className={styles.areaCodeLabel}>
              {geographyLevelLabels[level]}
            </p>
            <Dot aria-hidden="true" />
            <p className={styles.areaCode}>{area.code}</p>
          </div>

          <h2 className={styles.areaName}>
            {generateAreaName(area.name, area.code)}
          </h2>

          {/* Primary Measure */}
          <div className={styles.primaryMeasureContainer}>
            <p className={styles.primaryMeasureLabel}>
              Estimated dementia diagnosis rate:
            </p>
            <div className={styles.primaryMeasureValueContainer}>
              <div className={styles.rateGroup}>
                <strong className={styles.ratePrimary}>
                  {area.rate.toFixed(1)}
                </strong>
                <Percent className={styles.rateUnitIcon} aria-hidden="true" />
                <span className={styles.visuallyHidden}>percent</span>
              </div>
              <p className={styles.primaryMeasureAgeLabel}>Aged 65+</p>
            </div>
          </div>

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
            <ConfidenceRange
              rate={area.rate}
              lower={area.rateLower}
              upper={area.rateUpper}
              benchmark={england?.rate}
            />
          )}

          <dl>
            <div>
              <dt>Recorded 65+</dt>
              <dd>{area.recorded65Plus?.toLocaleString() ?? "Unavailable"}</dd>
            </div>

            <div>
              <dt>Estimated 65+</dt>
              <dd>
                {area.estimated65Plus != null
                  ? Math.round(area.estimated65Plus).toLocaleString()
                  : "Unavailable"}
              </dd>
            </div>
          </dl>

          {area.dqFlag && <p>Data-quality flag applies to this observation.</p>}
        </>
      )}
    </aside>
  );
}
