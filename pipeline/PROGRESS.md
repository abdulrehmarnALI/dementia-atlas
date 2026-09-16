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

## Next

- [ ] Hierarchy aggregation for Era-B measures (Sub-ICB → ICB → Region → England) with suppression propagation and a "computed" marker — waits on the display-rule decision (see the error table)
- [ ] Write the mapping table to Parquet in the build and hand its hierarchy to the aggregation step
- [ ] Back-fill April and May 2026 once those publications are sourced
- [ ] Put series breaks on rows the app can read directly: per-organisation (2026-04 reorg, D9Y0V/92A/U2G6B boundary changes, LTLA reissue) and per-measure (comparability class)
- [ ] Gold: app-ready tables into PostGIS — not before all of the above
