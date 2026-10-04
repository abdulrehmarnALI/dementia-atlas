"use client";

import AtlasMap from "./AtlasMap";
import { useState } from "react";
import { DiagnosisRate } from "@/types/atlas";

interface AtlasExplorerProps {
  level?: string;
  values: DiagnosisRate[];
  boundaryVintage: string;
}

export default function AtlasExplorer({
  level,
  values,
  boundaryVintage,
}: AtlasExplorerProps) {
  const [selectedCode, setSelectedCode] = useState<string | null>(null);

  return (
    <>
      <AtlasMap
        level={level ?? "sub_icb"}
        values={values}
        boundaryVintage={boundaryVintage}
        selectedCode={selectedCode}
        onSelectArea={setSelectedCode}
      />
    </>
  );
}
