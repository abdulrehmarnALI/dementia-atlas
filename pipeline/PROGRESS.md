# Progress

_Plain running log of the pipeline build: what's done, in order, and what comes next.
No dates — WORKLOG.md has those. Tick things off here as they land._

## Done

- [x] Explored the June 2026 release (structure, grain, measure types) — `notebooks/00_june_2026_release_exploration.ipynb`
- [x] Explored the March 2026 release — `notebooks/00_march_2026_release_exploration.ipynb`
- [x] Wrote up first findings in plain English — `docs/findings.md`
- [x] Cross-release QA across May 2025 / March 2026 / June 2026: two schema eras, no revisions, what needs a crosswalk — `notebooks/03_cross_release_qa.ipynb`
- [x] Set up the working files (CLAUDE.md, NOW.md, WORKLOG.md, context.md, agent-playbook.md)
- [x] Organisation crosswalk: `ORG_TYPE` → `org_level`, England alias, LTLA code reissue, ICB reorg keyed per Sub-ICB — `src/org_crosswalk.py`
- [x] Measure crosswalk: Era-A `Measure` strings → Era-B `MEASURE / BREAKDOWN / AGE / GENDER / …`, plus cross-era comparability class — `src/measure_crosswalk.py`
- [x] Silver value + metadata schema: `value_raw` / `value_num` / `value_state`, DQ flag, dates, era, dictionary version, column shape — `src/silver_schema.py`
- [x] Derived rows: drop published `ALL_AGED_*`, recompute Female + Male, suppression carries through — `src/derived_rows.py`
- [x] Checked whether summing Sub-ICBs reproduces Era A's published ICB / Region / England figures: exact for register-type measures, approximately (±15) for the rest — `tests/test_aggregation_evidence.py`
- [x] Silver loader: all three releases → one observation frame, revision check, latest-release-wins, Parquet in/out — `src/silver_loader.py`
- [x] Write the silver Parquet to `data/processed/silver/` — `python -m src.build`
- [x] Decided: `U2G6B` is not `D4U1Y` recoded — Frimley's practices split three ways (U2G6B 41, D9Y0V 14, 92A 11); series-break flags for all three at 2026-04 — `src/org_crosswalk.py`, `docs/context.md`
- [x] Decided: practice-level history starts June 2026; Era-A practice files stay on disk but out of scope
- [x] Measured computed-vs-published aggregate error per measure per level for Era A — `docs/aggregation_error_era_a.md`
- [x] Mapping snapshots (practice → Sub-ICB → ICB → Region) load as a dimension table with an `unmapped` flag — `src/mapping_loader.py`
- [x] Era-B practice file loads into the observation frame — `src/silver_loader.py`
- [x] Build writes the mapping table and per-release hierarchy to Parquet alongside the observations — `src/build.py`
- [x] Code walkthrough for maintainers — `docs/code-walkthrough.md`
- [x] Readability pass on `src/`: walkthrough for maintainers, risks triaged and fixed (rename to legal dates, single-sourced dimensions, guards on release names and dictionary versions, revision check by value) — `docs/code-walkthrough.md`
- [x] Exact bounds on every value (`value_num_lower` / `value_num_upper`) and a `minimum` state for computed totals over suppressed cells; one summing rule shared by derived rows and aggregates — `src/derived_rows.py`
- [x] Hierarchy aggregation (Sub-ICB → ICB → Region → England) filling only the levels the publisher didn't publish, validated against Era A — `src/aggregation.py`
- [x] Series-breaks table: organisation breaks (2026-04 reorg, Frimley split, UTLA expansion) and measure breaks (definition, suppression, discontinued, introduced) — `src/series_breaks.py`
- [x] Gold tables built from silver: organisation, measure, period, observation, diagnosis_rate, series_break, geometry — `src/gold.py`, `data/processed/gold/`
- [x] PostGIS schema and loader (COPY + dissolved ICB / region outlines) and a local docker-compose — `db/schema.sql`, `src/load_postgis.py`, `infra/docker-compose.yml`

## Next

- [ ] Run the PostGIS load for real against the local container and fix what it turns up
- [ ] Local-authority (LTLA / UTLA) boundaries into `geometry`
- [ ] Web app scaffold: one map page over `gold.diagnosis_rate` + `gold.geometry`
- [ ] Export the QA notebook's numbered findings into `docs/findings.md`
- [ ] Build writes a short QA summary (`build_summary.md`) next to the Parquet
- [ ] Back-fill April and May 2026 once those publications are sourced
