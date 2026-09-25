export type DiagnosisRate = {
  code: string;
  rate: number;
};

export type AtlasPeriod = {
  period: string;
  period_end: string;
  publication_era: string;
  boundary_version_nhs: string;
};

export type AtlasMapProps = {
  level: string;
  values: DiagnosisRate[];
  boundaryVintage: string;
};
