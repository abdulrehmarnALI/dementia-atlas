"use client";

import AtlasMap from "./AtlasMap";
import { useState } from "react";
import type {
  AreaSnapshot,
  DiagnosisRate,
  EnglandBenchmark,
} from "@/types/atlas";
import SelectedAreaPanel from "./SelectedPanel";
import styles from "./AtlasExplorer.module.css";

interface AtlasExplorerProps {
  level: string;
  areas: AreaSnapshot[];
  england: EnglandBenchmark | null;
  boundaryVintage: string;
}

export default function AtlasExplorer({
  level,
  areas,
  boundaryVintage,
  england,
}: AtlasExplorerProps) {
  const [selectedCode, setSelectedCode] = useState<string | null>(null);

  const selectedArea =
    selectedCode === null
      ? null
      : (areas.find((area) => area.code === selectedCode) ?? null);

  const mapValues: DiagnosisRate[] = areas.map(({ code, rate }) => ({
    code,
    rate,
  }));

  return (
    <div className={styles.explorer}>
      <div className={styles.mapArea}>
        <AtlasMap
          level={level}
          values={mapValues}
          boundaryVintage={boundaryVintage}
          selectedCode={selectedCode}
          onSelectArea={setSelectedCode}
        />
      </div>

      <SelectedAreaPanel area={selectedArea} england={england} />
    </div>
  );
}
