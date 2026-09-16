# NOW

_Single source of truth for "what's happening right now." This file gets overwritten each
session — history lives in WORKLOG.md, not here._

## In progress

_(empty — pick the top item below to start)_

## Up next (small, independently shippable — pick one at a time)

1. Build the Era-A measure crosswalk: `Measure` string → `(measure, breakdown, age, gender)`
   tuples, validated against Era-B's explicit dimension columns.
2. Design the value/metadata schema for silver rows: `value_raw`, `value_num`, `value_state`
   (numeric / suppressed / blank / not_applicable), `DQ` flag, `source_release`, `source_file`,
   `publication_era`, `ingested_at`, `dictionary_version`.
3. Implement derived-row handling: drop stored `ALL_AGED_*` rows, compute as Female + Male at
   silver-build time so nothing double-counts.
4. Validate Era-A ICB/Region/England aggregates against summed Sub-ICBs (findings §10, Q3) — the
   data is already loaded, so this is a quick evidence-gathering task before trusting the Era-B
   aggregation-by-summing rule.

## Blocked / needs Sunshine's input

- April & May 2026 PCDD publications aren't in the local data yet (findings §4/§6) — need to
  source and drop them into the raw data folder before they can be back-filled.
- Whether Era-B is ever revised is untestable until a second Era-B release exists (findings §10,
  Q1) — nothing to do here yet, just don't assume "latest release wins" logic gets exercised.
- The May 2025 and March 2026 raw files aren't in `data/raw/pcdd/` locally (only June 2026 is).
  The org crosswalk's Era-A-side claims (`COUNTRY`/`REGION` tokens, retired ICB codes,
  pre-reissue LTLA codes) are therefore tested as pure functions only — extend
  `tests/test_org_crosswalk.py` to re-derive them from raw data once those releases land.
- Docs mismatch: CLAUDE.md/NOW.md cite `../docs/findings.md` §6/§7/§9/§10 and
  `tests/test_eda_claims.py`, but findings.md has no numbered sections (it only covers the June
  2026 structure) and that test file doesn't exist. The numbered-section evidence actually lives
  in `notebooks/03_cross_release_qa.ipynb` (sections 7–10). Worth either exporting that
  notebook's findings into docs/findings.md or repointing CLAUDE.md.

## Needs a decision (don't invent an answer — add it here and ask)

- Is Sub-ICB `U2G6B` (new at 2026-06) the same organisation as retired `D4U1Y` under a new code,
  or a genuinely different Sub-ICB? The QA notebook only records the one-out/one-in code churn;
  local data can't settle it. Decides whether those two series may be joined across the era
  boundary. The crosswalk currently treats them as NOT continuous.
