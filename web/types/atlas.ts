export type DiagnosisRate = {
  code: string;
  rate: number;
};

export type AtlasMapProps = {
  level: string;
  values: DiagnosisRate[];
};
