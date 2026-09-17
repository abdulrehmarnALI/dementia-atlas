# NOW

_Single source of truth for "what's happening right now." This file gets overwritten each
session — history lives in WORKLOG.md, not here._

## In progress

_(empty)_

## Up next (small, independently shippable — pick one at a time)

The pipeline end is complete: raw → silver → gold → PostGIS, with boundaries for every level and
era and a point for every practice. What's left is the app.

1. **Web app scaffold in `web/`** (Next.js + MapLibre + CSS Modules — stack per context.md). First
   milestone: one page showing the latest-period diagnosis rate as a choropleth, with a level
   switcher (Sub-ICB / ICB / region / LTLA / UTLA), reading `gold.diagnosis_rate` joined to
   `gold.geometry` on `period.boundary_version_nhs`. Needs its own queue once started. Decisions
   to make at the start: basemap (recommend OpenFreeMap — free, keyless), and whether the API
   serves boundaries as simplified GeoJSON from `geom_web` (fine at these sizes) or as vector
   tiles (`ST_AsMVT`).
2. Practice points on the map, clustered on zoom (`cluster: true` on a MapLibre GeoJSON source
   over `gold.practice_location`).
3. Export the QA notebook's numbered findings into `docs/findings.md` so the §1–§10 references
   resolve.
4. A short QA summary written by the build (row counts per release / level / state, number of
   `minimum` rows, breaks) next to the Parquet, so a re-run can be eyeballed without opening it.

## Blocked / needs Sunshine's input

- April & May 2026 PCDD publications aren't in the local data yet — needed to close the gap
  between the March and June 2026 releases. `silver_schema.publication_era()` refuses those two
  months until a file is seen and the era constants are updated.
- Whether Era-B is ever revised is untestable until a second Era-B release exists;
  `find_revisions` will catch it when it can.
- Era-A releases before May 2024 (for 2022+ history) — drop them in `data/raw/pcdd/YYYY-MM/`; an
  unrecognised file name or token will stop the build and say so.

## Needs a decision (don't invent an answer — add it here and ask)

_(empty)_
