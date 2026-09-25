"use client";

import { useRouter, useSearchParams } from "next/navigation";

import type { AtlasPeriod } from "@/types/atlas";

type AtlasControlsProps = {
  periods: AtlasPeriod[];
  selectedPeriod: string;
};

export default function AtlasControls({
  periods,
  selectedPeriod,
}: AtlasControlsProps) {
  const router = useRouter();
  const searchParams = useSearchParams();

  function handlePeriodChange(period: string) {
    const params = new URLSearchParams(searchParams.toString());

    params.set("period", period);

    router.push(`/?${params.toString()}`);
  }

  return (
    <div>
      <label htmlFor="period">Period</label>

      <select
        id="period"
        value={selectedPeriod}
        onChange={(event) => handlePeriodChange(event.target.value)}
      >
        {periods.map((period) => (
          <option key={period.period} value={period.period}>
            {period.period}
          </option>
        ))}
      </select>
    </div>
  );
}
