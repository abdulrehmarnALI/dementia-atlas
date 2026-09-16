# NOW

_Single source of truth for "what's happening right now." This file gets overwritten each
session — history lives in WORKLOG.md, not here._

## In progress

_(empty)_

## Up next (small, independently shippable — pick one at a time)

Every one of context.md's seven "silver is finished when" criteria now has code and tests behind
it. What's left is review and tidy-up before gold:

1. **Silver milestone review (Sunshine).** Run `python -m src.build`, open the five Parquet files,
   and check the shape is what the app will want — in particular whether computed aggregates
   living in the same table as published rows (distinguished by `is_derived` / `source_file`) is
   convenient or a trap, and whether `minimum` rows should be surfaced or hidden by default.
2. Export the QA notebook's numbered findings into `docs/findings.md` so CLAUDE.md's references
   to §1–§10 resolve (currently only the June 2026 structure notes are there).
3. A short QA summary written by the build (row counts per release / level / state, number of
   `minimum` rows, breaks) into `data/processed/silver/build_summary.md`, so a re-run can be
   eyeballed without opening Parquet.

## Blocked / needs Sunshine's input

- April & May 2026 PCDD publications aren't in the local data yet (QA notebook §4/§6) — need to
  source and drop them into the raw data folder before they can be back-filled.
  `silver_schema.publication_era()` deliberately refuses those two months until a file is seen.
- Whether Era-B is ever revised is untestable until a second Era-B release exists (QA notebook
  §11, Q1) — nothing to do here yet; `find_revisions` will catch it when it can.
- Gold (PostGIS tables, app wiring) is the next phase and touches `db/` / `web/`, which this
  phase's rules keep off-limits — needs an explicit go-ahead and its own queue.

## Needs a decision (don't invent an answer — add it here and ask)

_(empty — the aggregate display rule was decided: bounded minimums, see context.md)_
