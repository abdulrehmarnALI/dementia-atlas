# Era A: computed (sum of Sub-ICBs) vs published aggregates

_Measured on the March 2026 release (13 monthly periods); the May 2025 release gives the same picture
to the second decimal - both are in `aggregation_error_era_a.csv`. "Computed" = sum of the published
Sub-ICB rows; "published" = the ICB / Region / England row NHS England published for the same
measure and period. Error = published − computed, on groups with no suppressed input. Relative
error is |error| / published._

Read this before choosing a display rule for Era-B computed aggregates.

| measure | level | groups | input suppression | exact | mean abs err | max abs err | p95 rel err | max rel err |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| MCI (all age/sex cells) | ICB | 12012 | 1.3% | 86% | 0.76 | 15 | 2.27% | 25.00% |
| MCI (all age/sex cells) | REGION | 2002 | 1.3% | 7% | 4.09 | 20 | 1.09% | 4.97% |
| MCI (all age/sex cells) | COUNTRY | 286 | 1.3% | 4% | 12.35 | 41 | 0.27% | 0.49% |
| COMORBIDITIES | ICB | 546 | 0.0% | 21% | 1.65 | 10 | 0.05% | 0.08% |
| COMORBIDITIES | REGION | 91 | 0.0% | 11% | 3.79 | 16 | 0.02% | 0.03% |
| COMORBIDITIES | COUNTRY | 13 | 0.0% | 0% | 8.54 | 19 | 0.01% | 0.01% |
| DEMENTIA_REGISTER_65_PLUS | ICB | 546 | 0.0% | 100% | 0.00 | 0 | 0.00% | 0.00% |
| DEMENTIA_REGISTER_65_PLUS | REGION | 91 | 0.0% | 100% | 0.00 | 0 | 0.00% | 0.00% |
| DEMENTIA_REGISTER_65_PLUS | COUNTRY | 13 | 0.0% | 100% | 0.00 | 0 | 0.00% | 0.00% |
| PALLIATIVE_CARE | ICB | 546 | 0.0% | 18% | 1.60 | 9 | 0.26% | 0.53% |
| PALLIATIVE_CARE | REGION | 91 | 0.0% | 11% | 4.27 | 14 | 0.08% | 0.09% |
| PALLIATIVE_CARE | COUNTRY | 13 | 0.0% | 8% | 13.15 | 22 | 0.02% | 0.02% |
| DELIRIUM_12M | ICB | 504 | 0.0% | 14% | 1.76 | 11 | 1.07% | 1.63% |
| DELIRIUM_12M | REGION | 84 | 0.0% | 11% | 4.33 | 12 | 0.31% | 0.49% |
| DELIRIUM_12M | COUNTRY | 12 | 0.0% | 0% | 12.00 | 36 | 0.16% | 0.17% |
| DEMENTIA_REGISTER | ICB | 546 | 0.0% | 100% | 0.00 | 0 | 0.00% | 0.00% |
| DEMENTIA_REGISTER | REGION | 91 | 0.0% | 100% | 0.00 | 0 | 0.00% | 0.00% |
| DEMENTIA_REGISTER | COUNTRY | 13 | 0.0% | 100% | 0.00 | 0 | 0.00% | 0.00% |
| INCIDENCE | ICB | 546 | 0.0% | 17% | 1.64 | 10 | 2.65% | 5.30% |
| INCIDENCE | REGION | 91 | 0.0% | 8% | 4.22 | 12 | 0.96% | 1.34% |
| INCIDENCE | COUNTRY | 13 | 0.0% | 0% | 10.92 | 26 | 0.27% | 0.36% |
| PAT_LIST_ALL | ICB | 546 | 0.0% | 100% | 0.00 | 0 | 0.00% | 0.00% |
| PAT_LIST_ALL | REGION | 91 | 0.0% | 100% | 0.00 | 0 | 0.00% | 0.00% |
| PAT_LIST_ALL | COUNTRY | 13 | 0.0% | 100% | 0.00 | 0 | 0.00% | 0.00% |
| YOUNG_ONSET | ICB | 546 | 0.0% | 20% | 1.66 | 11 | 0.61% | 0.92% |
| YOUNG_ONSET | REGION | 91 | 0.0% | 6% | 4.92 | 14 | 0.23% | 0.27% |
| YOUNG_ONSET | COUNTRY | 13 | 0.0% | 0% | 10.00 | 21 | 0.05% | 0.06% |
| DEMENTIA_ESTIMATE_65_PLUS | ICB | 546 | 0.0% | 80% | 0.02 | 0 | 0.00% | 0.00% |
| DEMENTIA_ESTIMATE_65_PLUS | REGION | 91 | 0.0% | 38% | 0.08 | 0 | 0.00% | 0.00% |
| DEMENTIA_ESTIMATE_65_PLUS | COUNTRY | 13 | 0.0% | 8% | 0.21 | 0 | 0.00% | 0.00% |
| DEMENTIA_REGISTER_65_PLUS | ICB | 546 | 0.0% | 100% | 0.00 | 0 | 0.00% | 0.00% |
| DEMENTIA_REGISTER_65_PLUS | REGION | 91 | 0.0% | 100% | 0.00 | 0 | 0.00% | 0.00% |
| DEMENTIA_REGISTER_65_PLUS | COUNTRY | 13 | 0.0% | 100% | 0.00 | 0 | 0.00% | 0.00% |

## What the table says

- **Register / list-size measures are exact at every level**: `DEMENTIA_REGISTER`, `DEMENTIA_REGISTER_65_PLUS`,
  `PAT_LIST_ALL`, and `nhs_rate`'s register. `DEMENTIA_ESTIMATE_65_PLUS` is exact to its published rounding (≤ 0.4).
- **Every other measure is inexact at every level, and suppression is not the reason** - the incidence and
  comorbidity/palliative files have zero suppressed cells, and MCI (the only suppressed input) is the *most* exact
  at ICB level (86%). So a rule keyed on suppression rate would be keyed on the wrong thing.
- **The error behaves like independent per-organisation noise that accumulates with the number of Sub-ICBs
  summed**: mean absolute error ≈ 1.7 at ICB (2-3 Sub-ICBs each), ≈ 4 at Region (≈ 15), ≈ 11 at England (106) -
  roughly √n growth - with mean error ≈ 0 (no bias) and both signs equally likely.
- **Relative error is therefore governed by count size, not level**: worst for `INCIDENCE` (monthly counts of
  new diagnoses, p95 ≈ 2.7% and max 5.3% at ICB), tiny for `COMORBIDITIES` (large counts, max 0.1%) and for
  anything at England level (< 0.4%). MCI's 25% max is a single small age/sex cell.
- Cause is not determinable from the data. The pattern is consistent with each level being computed
  independently from patient-level records (e.g. de-duplication or small perturbation per organisation)
  rather than by summing the published level below.

## Options this supports (not chosen yet)

1. Show computed aggregates for register/list measures only; withhold the rest at ICB/Region/England in Era B.
2. Show all computed aggregates, flagged `computed`, with a per-measure tolerance taken from this table
   (e.g. `INCIDENCE` ±5%, everything else ±2% at ICB, < 0.5% at England).
3. Show computed aggregates only where the count is large enough that the observed error is immaterial
   (a threshold on the computed value, since error is roughly constant in absolute terms).
