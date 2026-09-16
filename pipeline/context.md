# Dementia Atlas — Project Context

_Background and scope. Tool-agnostic on purpose — this is the file to read (or paste into) any
assistant, Claude Code or otherwise, to get up to speed on what this project is and why it's built
the way it is. Working rules for Claude Code live in `pipeline/CLAUDE.md`; current task state lives
in `pipeline/NOW.md` and `pipeline/WORKLOG.md`._

---

## What the Dementia Atlas is

A geospatial web application over NHS England's **Primary Care Dementia Data (PCDD)**, showing
dementia diagnosis rates and register detail across England — Sub-ICB, ICB, NHS Region, and local
authority levels, over time.

It is a portfolio flagship as well as a real tool. The bar is "something a public-health analyst
would actually use," not "a map with dots on it." Two things follow from that:

- **The modelling layer is the point.** Plenty of dashboards render published NHS numbers. What
  makes this worth building is the layer on top — derived aggregates, series that are honestly
  comparable over time, and the data-quality provenance to justify both. The pipeline exists to
  make that layer trustworthy.
- **Series breaks are a first-class feature, not a bug to smooth away.** This data has genuine
  discontinuities: a full schema change at 2026-06, an ICB reorganisation (42→36), a reporting
  definition change for `INCIDENCE`, suppression rules removed, LTLA codes reissued mid-series.
  A chart that draws a straight line through those is lying. The Atlas should surface them — flag
  the break, refuse to trend what can't be trended, and say why.

## Stack

- **App:** Next.js, PostGIS, MapLibre. Styling via **CSS Modules — not Tailwind.**
- **Pipeline:** Python, pandas, pytest. Parquet for intermediate storage.
- **Repo layout:** one repo, several top-level folders — `pipeline/` (this data work), `web/`,
  `api/`, `db/`, `infra/`, `docs/`.
- **Environment:** Windows, VS Code, local `.venv` inside `pipeline/`.
- Broader stack across other projects: TypeScript, React, Node, Python, PostgreSQL, Azure, Docker,
  GIS.

## The pipeline, and why it's sequenced this way

**bronze → silver → gold.**

- **Bronze** — raw releases loaded losslessly, exactly as published, nothing cleaned.
- **Silver** — cleaned, crosswalked, typed, with data-quality metadata carried on every row.
  **Current phase.**
- **Gold** — app-ready tables in PostGIS. Not started, and shouldn't be until silver is solid.

The deliberate choice here: **EDA came before silver design.** Rather than guessing a schema and
discovering six weeks later that it can't represent the data, the EDA established what's actually
true — and the findings doc records each claim with the evidence behind it. Silver design should
keep working that way: decisions trace to evidence, and where evidence doesn't exist yet, that gets
written down as an open question instead of quietly assumed.

The same applies to how findings get written up. Where the data genuinely isn't clean, say so
plainly. Don't polish a QA doc to look more finished than the data is.

## Scope of the data work (what "done" looks like for this phase)

Silver is finished when:

1. All three held releases (May 2025, March 2026, June 2026) load into a single consistent
   observation model, across both schema eras.
2. Crosswalks exist and are tested: `ORG_TYPE` → controlled `org_level`; `ENG` ↔ `E92000001`;
   LTLA ONS reissue (2025-08); ICB reorg (2026-06); Era-A `Measure` strings → explicit
   `(measure, breakdown, age, gender)` tuples matching Era-B's dimension columns.
3. Every row carries provenance and quality metadata: `value_raw` / `value_num` / `value_state`
   (numeric | suppressed | blank | not_applicable), the `DQ` small-denominator flag,
   `source_release`, `source_file`, `publication_era`, `ingested_at`, `dictionary_version`.
4. Derived rows are computed, not stored — `ALL_AGED_*` is provably `Female + Male`, so storing it
   would double-count any naive sum.
5. Aggregation up the NHS hierarchy is implemented and **validated against Era-A's published
   aggregates** before being trusted for Era B (where those aggregates are no longer published).
6. Comparability is explicit: measures that can't cross the era boundary are marked as such in the
   model, not left for the frontend to figure out.
7. Suppression propagates — any aggregate built over a suppressed cell carries the flag.

Then, and only then, gold and the app build.

## Decisions already made

- **Notebook 03 (`notebooks/03_cross_release_qa.ipynb`) is historical evidence, not production
  code.** It's exploratory-quality and it did its job. Don't refactor it, don't import from it, and
  don't edit it. New logic goes in `src/` as fresh, tested code, *informed by* what the notebook
  found.
- **Revision policy:** evidence says "first release covering a period wins" (no revisions were
  found across overlapping Era-A releases). Implement "latest release wins" anyway, keep
  `source_release` on every row, and assert loudly in CI if a revision ever does appear.
- **Never join on organisation names** — casing flips between releases in both directions. Join on
  ODS/ONS codes only.
- **Practice→hierarchy joins are left joins with an `unmapped` flag**, never inner joins. An inner
  join silently drops practices that closed between the reporting period and the mapping extract
  date.

## Known open questions

Carried from findings §10 — these are genuinely unresolved, not homework someone forgot to do:

1. Are Era-B releases ever revised? Untestable until two Era-B publications share a period.
2. Do the April and May 2026 publications follow Era A or Era B? The boundary is *inferred* from
   the financial year, not observed. Those two months are also missing from local data entirely.
3. Is Sub-ICB `U2G6B` (new at 2026-06) a recode of retired `D4U1Y`, or a different organisation?
   Decides whether those series may be joined. Currently treated as **not** continuous.
4. What is NHS England's archive retention policy for past PCDD publications? Era B's
   single-month model makes the Atlas dependent on every month staying downloadable — if old
   releases disappear, the ingestion schedule becomes non-negotiable.

## Add to this file when...

- A decision gets made in conversation — here, in Claude Code, in ChatGPT, anywhere — that would
  change how someone picks this repo up cold.
- The *reasoning* behind a choice would otherwise only survive in a chat transcript.
- Not for task state. That's `pipeline/NOW.md` and `pipeline/WORKLOG.md`.
