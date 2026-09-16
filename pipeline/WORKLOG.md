# WORKLOG

_Append-only. One entry per session, newest at the bottom. Keep each entry to a few lines — this
is a skimmable log, not a transcript._

## Format

```
### YYYY-MM-DD — <short title>
- What was done
- What it touched (files/tables)
- What's next (should match what got moved into NOW.md)
```

---

### 2026-09-15 — Docs scaffold created

- Added CLAUDE.md, NOW.md and WORKLOG.md to give Claude Code stable context and a small-batch
  working rhythm for the silver-layer build.
- Seeded NOW.md's "Up next" queue from the EDA findings doc (org/measure crosswalks, value schema,
  derived-row handling, aggregate validation).
- Next: pick item 1 or 5 from NOW.md to start silver work.

### 2026-09-15 - Organisation crosswalk built (src/org_crosswalk.py)

- Built NOW.md item 1: `ORG_TYPE` -> controlled `org_level` (12 tokens -> 9 levels; GOR kept
  distinct from nhs_region, 9 vs 7 entities), `ENG` <-> `E92000001` England alias, the 2025-08
  LTLA ONS reissue (E08000016->E08000038, E08000019->E08000039), and the 2026-06 ICB reorg.
  The reorg crosswalk is keyed per Sub-ICB (23 reassignments), not ICB->ICB, because QJG and
  QM7 each split across two new ICBs - old->new is many-to-many.
- Touched: new `src/org_crosswalk.py`, new `tests/test_org_crosswalk.py` (14 tests, all pass;
  re-derive the claims from the raw June 2026 CSVs with plain pandas), pytest added to root
  requirements.txt. All evidence traced to notebooks/03_cross_release_qa.ipynb section 8.
- Found: `tests/test_eda_claims.py` referenced by CLAUDE.md doesn't exist (tests/ was empty -
  this session's test file establishes the pattern instead), and docs/findings.md has no
  numbered sections - noted both in NOW.md. Also parked "is U2G6B the recoded D4U1Y?" under
  Needs a decision.
- Next: NOW.md item 1 (Era-A measure crosswalk) - but it needs the Era-A raw files locally to
  be testable, so item 4 (validate Era-A aggregates) has the same blocker; item 2 (value/
  metadata schema) is doable with June 2026 data alone.

### 2026-09-16 - Measure crosswalk, silver value schema, derived rows, aggregation evidence

- Committed and pushed last session's org crosswalk plus the context/QA files, then extended
  its tests to re-derive the Era-A side from the March 2026 release that landed since: the 23
  Sub-ICB reassignments are provably the complete set of parent changes between the two
  mapping files, and D4U1Y's parent ICB was itself retired (explains why QNQ has no successor).
- Built `src/measure_crosswalk.py`: Era-A (family, Measure) -> Era B's MEASURE/BREAKDOWN/
  AGE/GENDER/... shape, Era-B tokens as the silver vocabulary, PAT_LIST gender-casing fix, and
  a cross-era comparability class per (measure, breakdown). Decoded 65+ register sums tie to
  the published headline in 106/106 Sub-ICBs in both eras.
- Built `src/silver_schema.py` (value_raw/value_num/value_state, DQ flag, three date
  spellings, era + dictionary version, SILVER_COLUMNS) and `src/derived_rows.py` (drop
  published ALL_AGED_* rows, recompute Female + Male with suppression propagation; 8,268/8,268
  cells tie).
- Evidence for the aggregation rule in `tests/test_aggregation_evidence.py`: England = sum of
  Regions exactly everywhere; ICB = sum of Sub-ICBs exactly ONLY for register/list-size
  measures; INCIDENCE, DELIRIUM, YOUNG_ONSET, PALLIATIVE, COMORBIDITIES and MCI are off by up to
  +/-15 patients (<= 5.3%) in both directions with no suppression involved. Parked as a decision.
- Found, not expected: the practice-level Era-A files (now on disk) publish 0 and 1-4 next to
  '*', so their suppression rule is not the 0-4 rule; a '.' missing token (12 PAT_LIST cells)
  the notebook never saw, treated as blank; dates come in three spellings in one release.
- Touched: src/{measure_crosswalk,silver_schema,derived_rows}.py, tests/ (60 tests, all pass),
  NOW.md, context.md. Nine commits, pushed.
- Next: the silver loader (NOW.md item 1), then hierarchy aggregation once the "computed
  aggregates for noisy measures" decision is made.

### 2026-09-16 (later) - Silver loader; May 2025 landed

- May 2025 raw files arrived (schema identical to March 2026, as the QA notebook said).
- Built `src/silver_loader.py`: every raw CSV classified into a family; the nine analytical
  families (two rate files, seven Era-A Sub-ICB families, Era-B consolidated Sub-ICB file) load
  into the SILVER_COLUMNS frame via the org/measure crosswalks, value classification and
  derived rows. Cross-release revision check (`find_revisions`) and latest-release-wins
  resolution. `python -m src.build` writes Parquet to data/processed/silver/.
- Re-derived the notebook's headline on the loaded frame: 33,394 published observations
  overlap between May 2025 and March 2026 (35,302 minus the 1,908 ALL_AGED rows silver
  drops), zero differ.
- Vectorised `derive_all_sex_rows` so a full release derives in well under a second.
- Added `PROGRESS.md` (undated done/next list) at Sunshine's request; pinned pyarrow.
- Touched: src/{silver_loader,build}.py, src/{derived_rows,measure_crosswalk}.py (small),
  tests/test_silver_loader.py (70 tests total, all pass), NOW.md, PROGRESS.md.
- Next: hierarchy aggregation (NOW.md item 1) once the noisy-measures decision is made; mapping
  snapshots and the Era-B practice file are unblocked and could go first.

### 2026-09-16 (later still) - Decisions recorded; mapping + practice loaders

- Q3 (U2G6B vs D4U1Y) recorded as NOT continuous, with the ODS source. Local mapping
  snapshots show D4U1Y's 66 practices went three ways: U2G6B 41, D9Y0V 14, 92A 11 - 92A was
  not in Sunshine's brief. Those 66 are the only practices that changed Sub-ICB, so D9Y0V,
  92A and U2G6B all carry a 2026-04 series-break flag (`sub_icb_series_break`).
- Q2: practice-level history starts June 2026. All three Era-A practice files are on disk in
  both releases (anti-psy, ass-plans, data-date) - not just data-date - and stay out of scope.
- Q1: measured computed-vs-published error per measure per level, both Era-A releases ->
  docs/aggregation_error_era_a.md (+csv). Error does NOT track suppression; it grows ~sqrt(n)
  with the number of Sub-ICBs summed and is largest relatively for INCIDENCE. No rule chosen.
- Moved context.md to docs/context.md (where CLAUDE.md already pointed); added the decisions.
- Built src/mapping_loader.py (dimension table, NULL sentinel -> unmapped flag, names
  stripped) and loaded the Era-B practice file into silver (42,616 rows, age decoded from the
  breakdown name, comparability era_b_only). 81 tests pass. Committed, not pushed.
- Next: mapping table into the build, series breaks on rows, aggregation once a display
  rule is chosen.
