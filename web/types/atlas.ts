export type DiagnosisRate = {
  code: string;
  rate: number;
};

export type AreaSnapshot = {
  code: string;
  name: string;
  rate: number;
  rateLower: number | null;
  rateUpper: number | null;
  recorded65Plus: number | null;
  estimated65Plus: number | null;
  // dq flag representing data quality reliability/concerns
  dqFlag: boolean;
};

export type EnglandBenchmark = {
  rate: number;
  rateLower: number | null;
  rateUpper: number | null;
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
  selectedCode: string | null;
  onSelectArea: (code: string | null) => void;
};

export type GeographyLevel =
  | "sub_icb"
  | "icb"
  | "nhs_region"
  | "gor"
  | "ltla"
  | "utla";
