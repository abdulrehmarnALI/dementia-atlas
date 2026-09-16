# NOW

_Single source of truth for "what's happening right now." This file gets overwritten each
session — history lives in WORKLOG.md, not here._

## In progress

_(empty — pick the top item below to start)_

## Up next (small, independently shippable — pick one at a time)

1. Implement hierarchy aggregation for Era-B measures (Sub-ICB → ICB → Region → England) with
   suppression propagation and an explicit "computed" marker, using the rule pinned in
   `tests/test_aggregation_evidence.py` (exact for register/list-size measures, approximate for
   the rest — see "Needs a decision"). Needs a per-period Sub-ICB → ICB → Region hierarchy:
   Era A has it on the age/sex file rows, Era B only in the mapping snapshot.
2. Load the mapping snapshots (practice → Sub-ICB → ICB → Region, per release) as a silver
   dimension table, left-joinable with an `unmapped` flag (context.md decision).
3. Load the Era-B practice file (`pcdem-practice`) into the observation frame — `MEASURE` is a
   roll-up of `BREAKDOWN` there, so the breakdown names (`DEMENTIA_REGISTER_0_64`, …) need
   decoding into age tokens the same way Era-A strings do.
4. Era-A practice-level crosswalk (`pcdem-prac-anti-psy`, `pcdem-prac-ass-plans`): their
   `Measure` names line up with Era B's `PRESCRIBING` / `REVIEWS` breakdowns and the practice
   file's `DEMENTIA_REGISTER_0_64` / `PAT_LIST_65_PLUS` (mixed case aside). Blocked on the
   suppression-semantics decision below.

## Blocked / needs Sunshine's input

- April & May 2026 PCDD publications aren't in the local data yet (QA notebook §4/§6) — need to
  source and drop them into the raw data folder before they can be back-filled.
  `silver_schema.publication_era()` deliberately refuses those two months until a file is seen.
- Whether Era-B is ever revised is untestable until a second Era-B release exists (QA notebook
  §11, Q1) — nothing to do here yet, just don't assume "latest release wins" logic gets exercised.
- Docs mismatch: CLAUDE.md points at `../docs/context.md` and `../docs/findings.md` §1–§10, but
  context.md lives at `pipeline/context.md` and findings.md has no numbered sections (it only
  covers the June 2026 structure). The numbered-section evidence is in
  `notebooks/03_cross_release_qa.ipynb`. Worth exporting the notebook's findings into
  docs/findings.md, or repointing CLAUDE.md.

## Needs a decision (don't invent an answer — add it here and ask)

- Is Sub-ICB `U2G6B` (new at 2026-06) the same organisation as retired `D4U1Y` under a new code,
  or a genuinely different Sub-ICB? Local data can't settle it (D4U1Y's parent ICB was itself
  retired). Decides whether those two series may be joined across the era boundary. The
  crosswalk currently treats them as NOT continuous.
- Computed aggregates for non-register measures: in Era A, published ICB figures for INCIDENCE,
  DELIRIUM_12M, YOUNG_ONSET, PALLIATIVE_CARE, COMORBIDITIES and MCI differ from the sum of their
  Sub-ICBs by up to ±11–15 patients (≤ 5.3% of the figure), in both directions, with no
  suppression to explain it; MCI also differs at Region level. Register/list-size measures sum
  exactly. Should the Atlas show computed Era-B ICB/Region aggregates for the noisy measures at
  all (flagged "computed, ±5%"), or only for the measures where summing is provably exact?
- Practice-level suppression semantics: the Era-A practice files publish 0 and 1–4 freely
  alongside `*` (70% of antipsychotic cells are `*`), so `*` there is NOT small-number
  suppression and neither dictionary explains it. Decide whether Era-A practice-level history
  is in scope for silver before anyone crosswalks those files.
