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

## Next

- [x] Write the silver Parquet to `data/processed/silver/` — `python -m src.build`
- [ ] Hierarchy aggregation for Era-B measures (Sub-ICB → ICB → Region → England) with suppression propagation and a "computed" marker — waits on the "noisy measures" decision in NOW.md
- [ ] Load the mapping snapshots (practice → Sub-ICB → ICB → Region) so practice rows can be placed in the hierarchy
- [ ] Load the Era-B practice file (`pcdem-practice`)
- [ ] Era-A practice-level files (`prac-anti-psy`, `prac-ass-plans`) — waits on the suppression-semantics decision in NOW.md
- [ ] Back-fill April and May 2026 once those publications are sourced
- [ ] Mark comparability on every row in a way the app can use directly (series-break flags per measure and per organisation)
- [ ] Gold: app-ready tables into PostGIS — not before all of the above
