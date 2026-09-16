# NOW

_Single source of truth for "what's happening right now." This file gets overwritten each
session — history lives in WORKLOG.md, not here._

## In progress

_(empty)_

## Up next (small, independently shippable — pick one at a time)

Gold phase. The pipeline end is done (`src.build` → `src.gold` → `src.load_postgis`); what's
left is proving the database end and wiring the app.

1. Local-authority boundaries: LTLA / UTLA polygons (ONS Open Geography, 2025 boundaries) so the
   `la_rate` diagnosis rates can be mapped. Same pattern as the Sub-ICB GeoJSON → `geometry`.
2. Web app scaffold in `web/`: Next.js + MapLibre + CSS Modules, one page, reading
   `gold.diagnosis_rate` joined to `gold.geometry` for the latest period. Needs its own queue.
3. Export the QA notebook's numbered findings into `docs/findings.md` so CLAUDE.md's references
   to §1–§10 resolve.

## Blocked / needs Sunshine's input

- April & May 2026 PCDD publications aren't in the local data yet — needed to close the gap
  between the March and June 2026 releases. `silver_schema.publication_era()` refuses those two
  months until a file is seen and the era constants are updated.
- Era-A boundaries: the only boundary set held is April 2026 (post-reorganisation). Era-A ICB
  data (42 ICBs) has no matching outlines; either source the 2024/25 ICB boundaries or map Era A
  at Sub-ICB / region level only.
- Whether Era-B is ever revised is untestable until a second Era-B release exists;
  `find_revisions` will catch it when it can.

## Needs a decision (don't invent an answer — add it here and ask)

_(empty)_
