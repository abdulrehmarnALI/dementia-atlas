# Dementia Atlas — Project Context

_Background and scope — the file to read to get up to speed on what this project is and why it's
built the way it is. Current task state lives in `pipeline/NOW.md` and `pipeline/WORKLOG.md`._

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
- **Era B's vocabulary is the silver vocabulary.** Era-A `Measure` strings are decoded *into*
  Era B's `MEASURE / BREAKDOWN / AGE / GENDER / ETHNICITY / DEMENTIA_TYPE / RESIDENTIAL_TYPE`
  tokens (`src/measure_crosswalk.py`), not the other way round. Era-A totals that Era B doesn't
  publish as a row (all-age register, 65+ register, all-age list size) get `breakdown = N/A`.
- **A sum over suppressed cells is published as a bounded minimum, not hidden.** Because `*`
  hides an integer in 0–4, any computed total has exact bounds: lower = sum of the numeric cells,
  upper = lower + 4 × (number of suppressed cells). Silver carries `value_num_lower` /
  `value_num_upper` on every row (equal to the value when numeric, 0/4 when suppressed), and a
  computed row over suppressed inputs gets `value_state = minimum` with `value_num` = the lower
  bound. A sum over a *blank* cell is blank — nothing can be said. One rule,
  `src/derived_rows.py::sum_with_state`, serves derived all-sex rows and hierarchy aggregates.
  Era-A validation: the arithmetic holds; containment against NHS England's own published MCI
  aggregates is only ~49% because their per-level computation noise (up to ±41) is wider than
  the bounds — that is a property of the publisher's method, not of the bounds.
- **Computed aggregates are filled in only where the publisher didn't publish**, sit in the same
  observation table with `is_derived = True` and no `source_file`, and never include the
  diagnosis-rate measures (ratios can't be summed). Register / list-size measures reproduce Era
  A's published figures exactly; the others carry the noise documented in
  `docs/aggregation_error_era_a.md`.
- **Series breaks are a property of an organisation or a measure, not of an observation.** They
  live in their own table (`src/series_breaks.py`, written as `pcdd_series_breaks.parquet`) keyed
  on `(org_level, org_code)` or `(measure, breakdown)` with an `effective_from` period and a
  `kind` (`closed`, `opened`, `boundary_change`, `definition_change`, `suppression_removed`,
  `discontinued`, `introduced`). Known breaks come from the crosswalks; late starts and early ends
  (the 2025-07 UTLA expansion, MCI from 2024-06, delirium from 2025-04) are read off the data. The
  app joins to this table; it never re-derives breaks from rows.
- **`U2G6B` is not `D4U1Y` under a new code — the two are never joined.** D4U1Y (NHS Frimley
  ICB – D4U1Y) closed on 31 March 2026 and its 66 practices were split three ways at the ICB
  reorganisation: 41 to the new `U2G6B` (NHS Thames Valley ICB), 14 to `D9Y0V` (Hampshire and
  Isle of Wight) and 11 to `92A`. So `U2G6B` starts fresh, and `D9Y0V` and `92A` keep their codes
  but change geography — a series on either is two different populations either side of
  2026-04, which a code-only check would miss. All three carry a `2026-04` series-break flag in
  `src/org_crosswalk.py` (`sub_icb_series_break`). Source: NHS England ODS, *ICB mergers 2026
  change summary* (linked from the module); practice counts verified from the March and June
  2026 mapping snapshots.
- **Practice-level history starts at June 2026.** The Era-A practice files
  (`pcdem-prac-anti-psy`, `pcdem-prac-ass-plans`, `pcdem-prac-data-date`) are held on disk but are
  out of scope for silver: their `*` suppression rule is different and undocumented, and the
  Atlas doesn't need practice-level time series before the Era-B format. The Era-B practice file
  loads from June 2026 onward.
- **Aggregation by summing Sub-ICBs is validated only for register / list-size measures.** Era A
  shows England = Σ Regions exactly and ICB = Σ Sub-ICBs exactly for `DEMENTIA_REGISTER`,
  `DEMENTIA_REGISTER_65_PLUS` and `PAT_LIST`, but the event-type measures (incidence, delirium,
  young onset, palliative care, comorbidities, MCI) differ from the sum by up to ±15 patients in
  both directions. Computed Era-B aggregates for those must carry a "computed" marker; the
  display rule is still to be chosen — the measured error per measure per level is in
  `docs/aggregation_error_era_a.md`, and it does *not* track suppression rate (the suppression-
  free files are just as inexact), so the rule should key on count size, not suppression.

## Gold (started 2026-09-16)

Gold is a reshaping of silver into what the app queries, nothing more — no new facts are
computed in gold. `pipeline/src/gold.py` builds seven tables from the silver Parquet and writes
them to `data/processed/gold/`; `pipeline/src/load_postgis.py` applies `db/schema.sql` and COPYs
them into a `gold` schema in PostGIS; `infra/docker-compose.yml` runs PostGIS locally.

- **`observation` is the fact table and is exactly silver's latest-release-wins frame**, keyed on
  `(period_end, org_level, org_code, measure_key)`, with `value` / `value_state` / bounds,
  `is_derived`, `dq_flag`, `comparability`. Computed aggregates and `minimum` rows are in it,
  distinguishable by `is_derived` and `value_state` — the app decides how to present them, gold
  doesn't hide them.
- **`measure_key` is a string**, `MEASURE:BREAKDOWN[:dim=value…]` — readable in a URL, stable
  across builds, no surrogate ids to keep in sync.
- **`diagnosis_rate` is the one wide table**, because the headline map needs register / estimate /
  rate / CI side by side per organisation-period and that's a fixed set of five measures.
  Everything else stays long.
- **Names come back in gold** (from the raw NAME columns, latest release wins, title-cased), for
  display only. Silver still has none.
- **Geometry comes from the ONS Open Geography Portal**, fetched once by `src/boundaries.py`
  through its public ArcGIS REST API into `data/raw/boundaries/` (gitignored, re-fetchable). Eight
  layers, all BGC (generalised, clipped to the coastline), EPSG:4326:
  Sub-ICB April 2023 and April 2026; ICB April 2023 (42) and April 2026 (36); NHS regions Jan
  2024; Local Authority Districts May 2026 (LTLA, uses the post-reissue codes); Counties and
  Unitary Authorities Dec 2025 (UTLA, 153 incl. the 2025-07 county councils); Regions Dec 2025
  (GOR). Every polygon resolves to an organisation silver knows and every organisation has a
  polygon — the build fails otherwise, which is how the boundary years were chosen.
- **NHS levels are drawn on the boundary set of their period**: `gold.period.boundary_version_nhs`
  is `2023-04` up to 2026-03 and `2026-04` from 2026-04. The app joins
  `geometry.boundary_version = period.boundary_version_nhs` and never has to know about the
  reorganisation. Local-authority levels have one set each.
- **`geom_web`** is `ST_SimplifyPreserveTopology(geom, 0.0005°)` (≈ 35–50 m), computed at load, for
  the browser; `geom` keeps the full BGC polygon.
- **GP practice coordinates come from api.postcodes.io** (free, no key, public postcode data),
  bulk-looked-up by `src/geocode.py` and cached in `data/raw/geocode/postcodes.parquet` so a
  rebuild sends only new postcodes. `gold.practice_location` has one row per practice ever seen
  in a mapping snapshot (latest snapshot wins), 99.97% with a point; the seven postcodes the
  service doesn't know stay NA rather than being guessed. Clustering on zoom is a MapLibre
  client feature, not pipeline work.
- **Tests build gold from the silver Parquet on disk**; the PostGIS round-trip test runs only when
  `DATABASE_URL` is set.

## Known open questions

Carried from findings §10 — these are genuinely unresolved, not homework someone forgot to do:

1. Are Era-B releases ever revised? Untestable until two Era-B publications share a period.
2. Do the April and May 2026 publications follow Era A or Era B? The boundary is *inferred* from
   the financial year, not observed. Those two months are also missing from local data entirely.
3. ~~Is Sub-ICB `U2G6B` a recode of retired `D4U1Y`?~~ Resolved — see decisions above.
4. What is NHS England's archive retention policy for past PCDD publications? Era B's
   single-month model makes the Atlas dependent on every month staying downloadable — if old
   releases disappear, the ingestion schedule becomes non-negotiable.
5. Why don't Era A's published ICB figures for event-type measures equal the sum of their
   Sub-ICBs (see decisions above)? Small, symmetric, unsuppressed gaps — the publisher appears
   to compute each level independently. Not answerable from the data.
6. What does `*` mean in the Era-A practice-level files? They publish 0 and 1–4 alongside it,
   so it isn't the Sub-ICB files' "0–4 suppressed" rule, and neither dictionary says. Moot for
   now — those files are out of scope (decision above) — but worth knowing if that ever changes.

## Add to this file when...

- A decision gets made in conversation, anywhere, that would change how someone picks this repo
  up cold.
- The *reasoning* behind a choice would otherwise only survive in a chat transcript.
- Not for task state. That's `pipeline/NOW.md` and `pipeline/WORKLOG.md`.
