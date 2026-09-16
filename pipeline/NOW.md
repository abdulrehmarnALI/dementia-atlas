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
2. Write the mapping dimension table to Parquet alongside the observations in `src/build.py`
   (`mapping_loader` exists and is tested; the build doesn't call it yet), and attach the
   per-release hierarchy the aggregation step will need.
3. Surface series breaks on rows: `org_crosswalk.sub_icb_series_break()` and the ICB reorg
   give per-organisation breaks at 2026-04; the measure crosswalk gives per-measure
   comparability. Decide how these land on silver rows (a `series_break_from` column, or a
   separate breaks table) so the app never has to re-derive them.

## Blocked / needs Sunshine's input

- April & May 2026 PCDD publications aren't in the local data yet (QA notebook §4/§6) — need to
  source and drop them into the raw data folder before they can be back-filled.
  `silver_schema.publication_era()` deliberately refuses those two months until a file is seen.
- Whether Era-B is ever revised is untestable until a second Era-B release exists (QA notebook
  §11, Q1) — nothing to do here yet, just don't assume "latest release wins" logic gets exercised.
- Docs mismatch: CLAUDE.md points at `../docs/findings.md` §1–§10, but findings.md has no
  numbered sections (it only covers the June 2026 structure). The numbered-section evidence is
  in `notebooks/03_cross_release_qa.ipynb`. Worth exporting the notebook's findings into
  docs/findings.md. (context.md now lives at docs/context.md, where CLAUDE.md points.)

## Needs a decision (don't invent an answer — add it here and ask)

- Display rule for computed aggregates: the measured computed-vs-published error per measure per
  level is in `docs/aggregation_error_era_a.md` (CSV alongside). Sunshine to decide the display
  rule before hierarchy aggregation is implemented (NOW.md item 1).
