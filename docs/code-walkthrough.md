# Code walkthrough — `pipeline/src/`

_For the person maintaining this who didn't write it. What each module does, how they fit, and a
plain-English account of the bits where the code is denser than the idea behind it. Not a design
doc (that's `context.md`) and not a findings doc (that's the QA notebook)._

## How the modules fit together

```
raw CSVs (data/raw/pcdd/<release>/)
        │
        │  silver_loader.classify_file()      which family is this file?
        ▼
silver_loader._shape_*()                    raw columns → the silver grain columns
        │     uses  org_crosswalk            ORG_TYPE → org_level, England alias, LTLA reissue
        │     uses  measure_crosswalk        Era-A Measure string → measure/breakdown/dimensions
        ▼
silver_loader.load_file()                   + value parsing (with bounds), dates, DQ, era, comparability
        │     uses  silver_schema            classify_values, parse_period_end, conform, …
        ▼
silver_loader.load_release()                drop published all-sex rows, recompute them
        │     uses  derived_rows             (the one summing rule lives here)
        ▼
silver_loader.build_silver()                all releases → one frame; revision check
        │
        ├──► aggregation.fill_missing_aggregates()   Sub-ICB → ICB / region / England, where not published
        │        uses  mapping_loader.hierarchy()     (from the practice mapping snapshots)
        │
        ├──► series_breaks.build_series_breaks()     org and measure breaks, known + read off the data
        │
        ▼
build.py                                    writes five Parquet files to data/processed/silver/
        │
        ▼
gold.py                                     reshapes silver into seven app tables → data/processed/gold/
        │
        ▼
load_postgis.py                             db/schema.sql + COPY into PostGIS; dissolves ICB/region outlines
```

Two modules predate all of this and aren't part of the build: `data_sources.py` and `ingest.py` are
S3 download stubs from before the raw files were kept locally. Nothing imports them; their
docstrings say so.

The dependency direction is strictly downward: the crosswalks and the schema know nothing about
files; the loader knows about files; aggregation and series breaks know about loaded frames. If
you're looking for *why* a value is what it is, start at the loader and follow the imports.

---

## `silver_schema.py` — the shape of a silver row, and the small parsers

**What it does.** Defines `DIMENSION_COLUMNS` (the five breakdown dimensions — the single
definition everything else is checked against), `SILVER_COLUMNS` (the 24 columns every silver row
has, with their pandas dtypes, in canonical order) and `SILVER_KEY` (the 11 columns that identify
one observation). Then four parsers that turn published text into typed columns: `classify_values`,
`parse_dq_flag`, `parse_dates` / `parse_period_end`, and two release-level lookups,
`publication_era` and `dictionary_version`. `conform()` forces any frame into the canonical column
order and dtypes.

**The rules that matter most.**

- `value_raw` is kept verbatim and everything else is derived from it. `classify_values` never
  turns an unknown token into NaN — it raises and names the token. NHS England has already used
  `*`, blank, `N/A`, `NULL` and `.` as sentinels with different meanings; a new one should stop
  the build, not vanish.
- Every row carries **exact bounds**, `value_num_lower` / `value_num_upper`: equal to the value
  when numeric, `0` / `4` when suppressed (a `*` hides an integer in 0–4 in every file silver
  loads), NaN when blank. This is what lets computed totals be honest — see `derived_rows`.
- There are five `value_state`s. Four are published (`numeric`, `suppressed`, `blank`,
  `not_applicable`); the fifth, `minimum`, only ever appears on computed rows: `value_num` is a
  lower bound and `value_num_upper` the upper bound.
- `org_code` is an ODS code for NHS levels but an ONS code for local-government levels (la_rate
  publishes no ODS code). Join on `(org_level, org_code)`, never on `org_code` alone.

**Where it's denser than it looks.**

- `classify_values` builds `value_state` by *overwriting in sequence*: first every row that parsed
  as a number gets `numeric`, then rows equal to `*` get `suppressed`, then blank/`.` get `blank`,
  then `N/A` gets `not_applicable`. The conditions are mutually exclusive so order doesn't really
  matter, but "later assignments win" is the right mental model. Anything still unassigned at the
  end is an unknown token → error. Bounds are then two `where`s: the value itself, except on
  suppressed rows.
- `parse_dates` handles the publisher's three date spellings by running one regex per spelling and
  parsing only the rows that match it (`out[mask] = pd.to_datetime(raw[mask], format=…)`). Rows
  matching no spelling stay `NaT` and trigger the error.
- `publication_era` deliberately *refuses* `2026-04` and `2026-05`. The Era-A/Era-B boundary has
  only been observed between the March and June 2026 releases; a file from the gap would need
  classifying by eye first.
- `dictionary_version` is computed, not looked up: the financial year of the release month gives
  `PCDD-2526`, `PCDD-2627`, and so on. It assumes one dictionary per financial year; the loader
  warns if the dictionary file actually in the release folder says otherwise.

---

## `org_crosswalk.py` — who an organisation is, across releases

**What it does.** Pure lookup tables and one-line functions; no pandas. Four problems:

1. `ORG_LEVEL_BY_ORG_TYPE` / `to_org_level()` — the releases spell the same organisational level
   three ways (`SUB_ICB`, `SUB_ICB_LOC`; `REGION`, `NHS_REGION`; three spellings of country). One
   controlled vocabulary. `GOR` (9 local-government regions) is *not* merged into `nhs_region`
   (7 NHS regions) — different entities. Unknown `ORG_TYPE` raises.
2. `normalise_ons_code()` / `is_england()` — the `nhs_rate` file puts the string `ENG` where an ONS
   code should be; everything else uses `E92000001`.
3. `LTLA_ONS_CODE_REISSUES` / `canonical_ltla_ons_code()` — two local authorities got new ONS codes
   at 2025-08 mid-series. They are unitary authorities, so the same codes appear at LTLA *and*
   UTLA; the loader puts the *canonical* code in `org_code` at every tier (so a series joins) and
   the *published* code in `ons_code` (so nothing is lost).
4. The 2026-04 ICB reorganisation. This is the part to read slowly:
   - Old ICB → new ICB is **many-to-many** (QJG and QM7 each split across two new ICBs), so there
     is no ICB-to-ICB rename table. The authoritative record is `SUB_ICB_ICB_REASSIGNMENTS_2026_04`:
     for each of the 23 Sub-ICBs whose parent changed, `(old_icb, new_icb)`.
   - `icb_successors(old)` derives "which new ICBs absorbed this old one" from that table; it can
     return several codes, or none (QNQ's only Sub-ICB was itself closed).
   - `new_icb_for_sub_icb(sub, old_parent)` gives the post-reorg parent, and *raises* if the caller's
     idea of the old parent disagrees with the table — a mismatch means the source data and the
     crosswalk have diverged, and guessing would hide that.
   - One Sub-ICB (`D4U1Y`, Frimley) closed and was split three ways. `SUB_ICB_SUCCESSORS_2026_04`
     records where its practices went; `SUB_ICB_BOUNDARY_BREAKS_2026_04` lists the three receiving
     Sub-ICBs, two of which keep their code but not their geography. `sub_icb_series_break(code)`
     answers "from what period is this Sub-ICB's history not comparable with its present?"

**Naming note.** Every reorganisation constant is suffixed `_2026_04` — the date the change legally
took effect (per ODS). The data only *shows* it from the June 2026 release, because April and May
2026 aren't held; `ICB_REORG_FIRST_OBSERVED_RELEASE` records that.

---

## `measure_crosswalk.py` — what a row measures, across eras

**What it does.** Era A encodes "what is counted" and "which category" in one `Measure` string whose
meaning depends on which file it came from (`WHITE` in the ethnicity file; `FEMALE_AGED_65_69` in
the age/sex file; `MCI_MALE_AGED_40_44` in the cognitive-impairment file). Era B has explicit
`MEASURE`, `BREAKDOWN` and five dimension columns. This module decodes Era A *into* Era B's shape,
using Era B's own tokens as the silver vocabulary.

**Key pieces.**

- `MeasureKey` — a frozen dataclass: `measure, breakdown` plus the five dimensions, defaulting to
  `ALL`. Frozen so it's hashable — the loader decodes each *distinct* Measure string once and maps
  rows through a dict. An import-time assertion checks its dimension fields are exactly
  `silver_schema.DIMENSION_COLUMNS`, in order.
- `decode_era_a_measure(family, measure)` — one `if family == …` branch per Era-A file family. Each
  branch either returns a `MeasureKey` or falls through to the `ValueError` at the bottom, so an
  unexpected string in a known file, or a known string in the wrong file, both fail. The
  `_PLAIN_MEASURES` set covers measures with no breakdown at all (`INCIDENCE`, `DELIRIUM_12M`, …),
  which decode to `breakdown = "N/A"` — Era B's own token for "no breakdown".
- Three Era-A totals that Era B never publishes as a single row (all-age register, 65+ register,
  all-age list size) decode to `breakdown = "N/A"` with `age = "65_PLUS"` where relevant.
  `AGE_TOKENS` is the full set of values `age` may take (`AGE_BANDS` plus the `0_64` / `65_PLUS`
  totals); the loader validates the practice file's age decoding against it.
- `normalise_gender()` — Era A spells `FEMALE`/`MALE`; Era B spells `Female`/`Male` except on
  `PAT_LIST` rows where it reverts to upper case. One function, three spellings in, one out.
- `CROSS_ERA_COMPARABILITY` / `cross_era_comparability(measure, breakdown)` — a per-(measure,
  breakdown) label from the QA notebook's §7.2 table: `comparable`, `labels_only` (same categories
  but Era-A values suppressed), `not_comparable` (definition changed), `era_a_only`, `era_b_only`.
  **Lookup is two-step:** exact `(measure, breakdown)` first, then `(measure, "*")` as a wildcard
  for measures whose every breakdown has the same answer (`FRAILTY`, `PRESCRIBING`, …). Neither
  found → `KeyError`, so a new breakdown in a future release has to be classified on purpose.

---

## `derived_rows.py` — the summing rule, and the rows silver computes rather than stores

**What it does.** Two things that belong together because they share one rule.

*The rule.* `sum_with_state(values)` is the specification for every computed total in silver:

- any blank or not-applicable input → the total is blank, with no bounds (nothing can be said);
- all inputs numeric → a numeric sum, whose bounds are itself;
- otherwise (some inputs suppressed, or inputs that are themselves minima) → a **`minimum`**:
  `value_num` = the sum of lower bounds, `value_num_upper` = the sum of upper bounds.

It's written as the simplest possible function and *is not what runs in production* — `sum_groups`
is. A test asserts the two agree group by group on real data with suppressed and blank cells
injected, so the readable version stays the source of truth.

*All-sex rows.* Era A publishes an `ALL_AGED_<band>` row that is provably Female + Male. Storing it
would make any sum over gender double-count, so `drop_published_all_sex_rows()` removes it and
`derive_all_sex_rows()` rebuilds it — for both eras, from the rule above, with `is_derived = True`
and no `value_raw`.

**`GROUP_COLUMNS`** — the columns that identify one derived all-sex group — is an explicit list,
and an import-time assertion checks that every `SILVER_COLUMNS` entry is either in it or in the
per-row set. Add a column to the schema and the import fails until you say which side it belongs
on. (Aggregation reuses this list minus the organisation columns.)

**`sum_groups` — what the vectorised version is actually doing.**

The obvious implementation is "group the rows, loop over the groups, call `sum_with_state` on
each". That's a Python loop over tens of thousands of groups per build, so the function does the
same thing with column arithmetic. Read it in three steps:

1. **Turn the facts the rule needs into 0/1 columns**: `_blank` (state is blank or not-applicable)
   and `_numeric`. Summing a 0/1 column inside a group is the same as counting.
2. **Group and aggregate**: `n` (rows in the group), `n_blank`, `n_numeric`, and the two bounds
   summed directly (`value_num_lower`, `value_num_upper`). Any `extra` aggregations the caller
   asks for — `derive_all_sex_rows` passes Female/Male counts and `ingested_at` — ride along.
   `dropna=False` is essential: `ons_code` can be NA and pandas would otherwise silently drop
   those groups.
3. **Apply the rule with masks, in priority order**: `value_state` starts as `minimum`, is
   overwritten to `numeric` where `n_numeric == n`, and overwritten again to `blank` where
   `n_blank > 0`; `value_num` is the summed lower bound, and all three value columns are blanked
   where the group is blank. Those two `.loc` assignments *are* the if/elif chain in
   `sum_with_state`.

`derive_all_sex_rows` then keeps only groups with exactly one Female and one Male row (a group
missing a sex produces nothing — absence of a row is not a zero), sets `gender = ALL`, and puts the
frame back into silver column order and dtypes.

---

## `silver_loader.py` — raw files in, silver rows out

**What it does.** The only module that knows about file names and raw column names.

- `classify_file(name)` — regex on the file name → a family name. Era-A families come from
  `measure_crosswalk.era_a_family_for_filename`; everything else from `_OTHER_FAMILY_PATTERNS`.
  `LOADED_FAMILIES` is the subset the build loads; the Era-A practice files are classified (so
  nothing is "unrecognised") but skipped by decision.
- One `_shape_<family>()` function per raw layout. Each returns the same intermediate frame: the
  silver grain columns, plus `value_raw` and `dq_raw` as published text. This is where the
  crosswalks are applied. Nothing is parsed yet.
- `load_file()` takes that shaped frame and adds everything else: provenance columns, parsed
  dates, `value_num` / `value_state` / bounds, the DQ flag, `comparability`. Then `conform()`.
- `load_release()` concatenates a folder's files, drops the published all-sex rows, derives them,
  asserts `SILVER_KEY` is unique, and warns if the dictionary file in the folder isn't the one
  `dictionary_version()` computes.
- `build_silver()` does that for every release folder and runs `find_revisions()`; a non-empty
  result stops the build with the first few offending rows in the message.
- `resolve_latest_release()` collapses to one row per observation, newest `source_release`
  winning. It checks every release name is `YYYY-MM` first, because "newest" is a string sort.
  `OBSERVATION_KEY` is `SILVER_KEY` minus `source_release`.

**Where it's denser than it looks.**

- `_decode_measures` decodes each distinct Measure string once into a `MeasureKey`, maps rows to
  keys, then unpacks the key's fields into columns with one small `.map` per field (a dict
  comprehension over `("measure", "breakdown", *DIMENSION_COLUMNS)`).
- `load_file` builds `comparability` the same way: one lookup per distinct `(measure, breakdown)`
  pair, then a list comprehension over rows.
- `find_revisions`: restrict to published (non-derived) rows, keep only observations that appear in
  more than one release, build a per-row signature `"<state>|<number>"`, count distinct signatures
  per observation, and return the rows for observations with more than one. It compares state and
  number, not `value_raw`, so `62` vs `62.0` is not a revision but `*` vs `3` is. One pandas
  wrinkle is spelled out in a comment: `astype(str)` keeps NaN as missing, which `nunique` would
  then ignore, so the number is filled with the word `none` first.

---

## `mapping_loader.py` — the practice → Sub-ICB → ICB → region snapshots

**What it does.** Each release ships one snapshot of which practice belongs to which Sub-ICB, ICB
and NHS region, as of an extract date *after* the reporting period. `load_mapping()` turns it into a
dimension table with a fixed 19-column shape across both eras (Era-A-only columns like PCN and
supplier become NA in Era B). `hierarchy()` reduces a snapshot to distinct Sub-ICB → ICB → region
triples (codes and ONS codes) and refuses a snapshot where a Sub-ICB has two parents.

**Two things to know.**

- June 2026 has one row whose three hierarchy codes are the literal string `NULL`. With pandas'
  defaults that reads as NaN and looks like missing data; here it's detected before any NA
  replacement and becomes `unmapped = True`, with the codes then set to NA. Practices in the
  observation frame are meant to be *left*-joined to this table; an unmapped practice keeps its
  rows.
- Names are stripped of whitespace (the May 2025 file has trailing spaces on some ICB names) and
  are for display only. Never join on them.

---

## `aggregation.py` — Sub-ICB rows up to ICB, NHS region, England

**What it does.** Era B publishes its Sub-ICB measures at Sub-ICB level only; the levels above
have to be computed. `aggregate_sub_icbs()` joins Sub-ICB rows to the release's hierarchy and runs
`sum_groups` once per target level, so a group with suppressed inputs comes out as a `minimum`
with exact bounds. `fill_missing_aggregates()` keeps only the aggregates whose observation key
has *no* published row — in Era B that's everything except the rate file; in Era A it's the four
Sub-ICB-only category files. `compare_to_published()` is the validation view: every computed
aggregate that *does* have a published counterpart, side by side.

**Three rules.**

- Ratios don't sum: `NON_ADDITIVE_MEASURES` (the diagnosis rate and its confidence limits) are
  refused as inputs.
- A Sub-ICB missing from the hierarchy is an error, not a silently smaller total.
- Aggregates are silver rows with `is_derived = True` and no `source_file` (many files feed one
  aggregate). `AGGREGATE_GROUP` is `derived_rows.GROUP_COLUMNS` minus the organisation columns
  and `source_file`, plus `gender` — gender is part of the grain here, unlike in all-sex
  derivation.

What Era A says about trusting this is in `docs/aggregation_error_era_a.md`: register / list-size
measures reproduce the published figures exactly; the rest carry the publisher's own per-level
noise.

---

## `series_breaks.py` — where a series stops being comparable with itself

**What it does.** A break is a property of an organisation or a measure, not of an observation,
so breaks are a separate table keyed on `(org_level, org_code)` or `(measure, breakdown)` with an
`effective_from` period (`YYYY-MM`, the first period the new state applies to) and a `kind`.

- `known_org_breaks()` — the 2026-04 reorganisation, straight from the org crosswalk: ICBs
  `closed` / `opened`, `QRL` `boundary_change` (it absorbed part of Frimley via D9Y0V), Sub-ICB
  `D4U1Y` closed, `U2G6B` opened, `D9Y0V` and `92A` boundary changes.
- `known_measure_breaks()` — every non-`comparable` entry in `CROSS_ERA_COMPARABILITY`, mapped
  to a kind: `not_comparable` → `definition_change`, `labels_only` → `suppression_removed`,
  `era_a_only` → `discontinued`, `era_b_only` → `introduced`.
- `breaks_from_data(silver)` — read off the loaded rows: local-authority organisations whose
  series start after or end before their level's span (the 21 UTLAs that appear at 2025-07), and
  measures whose first period is later than the earliest period held (MCI from 2024-06, delirium
  from 2025-04). NHS levels are left to the known breaks so nothing is double-counted.

A measure can have more than one break (MCI: introduced 2024-06 *and* suppression removed
2026-04), so the uniqueness key includes `kind`.

---

## `gold.py` — silver reshaped for the app

**What it does.** Reads the five silver Parquet files and produces seven app-shaped tables, with
no new facts computed: `organisation` (one row per org, with name, parent, first/last period,
series-break period), `measure` (one row per measure/breakdown/dimension combination with a stable
string `measure_key` and a dictionary description), `period`, `observation` (the fact table —
silver's latest-release-wins frame with a `measure_key`), `diagnosis_rate` (the five headline
measures pivoted wide), `series_break` (copied through) and `geometry` (Sub-ICB polygons as GeoJSON
text). `python -m src.gold` writes them to `data/processed/gold/`.

**Things to know.**

- `organisation_names()` re-reads the raw `NAME` columns because silver dropped them on purpose.
  Latest release wins; names are title-cased with `ICB` / `NHS` restored.
- Parents come from the latest hierarchy snapshot: Sub-ICB → ICB → NHS region → England, practice
  → Sub-ICB. Local-authority tiers have no parent in the data except GOR → England.
- `dictionary_descriptions()` reads the Era-B data dictionary and corrects its two naming slips
  (`REVIEW` → `REVIEWS`, `PAT_LIST_65_PLUS` as a measure name).
- The GeoJSON's `SICBL26CD` is an ONS code; the join to `org_code` goes through
  `organisation.ons_code`.

## `load_postgis.py` — gold into PostGIS

Applies `db/schema.sql` (drop-and-recreate the `gold` schema), `COPY`s each table in foreign-key
order, converts the GeoJSON text to PostGIS geometry, then **dissolves ICB and NHS-region
outlines from the Sub-ICB polygons** with `ST_Union`, grouped by the current parent in
`gold.organisation`. Needs `DATABASE_URL`; `infra/docker-compose.yml` gives you a local PostGIS.

## `build.py` — the command

`python -m src.build` from `pipeline/`. Optional release names as arguments restrict the build (a
name with no folder is an error, not a silently smaller build). Writes five files to
`data/processed/silver/`: `pcdd_observations` (every release, published rows plus computed
aggregates), `pcdd_latest` (one row per observation, latest release wins), `pcdd_mapping`,
`pcdd_hierarchy`, `pcdd_series_breaks`.

---

## How to trace one number

Take a June 2026 Sub-ICB row for `DEMENTIA_REGISTER`, `ETHNICITY = WHITE`, value `849`.

1. `classify_file("pcdem-sub-icb-jun-2026.csv")` → `sub_icb_consolidated`.
2. `_shape_era_b_sub_icb`: `ORG_TYPE = SUB_ICB` → `org_level = sub_icb`; `ODS_CODE` → `org_code`;
   dimensions copied across; gender normalised; `value_raw = "849"`.
3. `load_file`: `period_end = 2026-06-30`; `value_num = 849.0`, `value_state = numeric`,
   bounds `849.0 / 849.0`; `dq_flag = False`; `comparability = comparable`;
   `publication_era = B`; `dictionary_version = PCDD-2627`.
4. `load_release`: not an all-sex row, so kept as published; `is_derived = False`.
5. `build_silver`: appears in one release only, so no revision check applies.
6. `fill_missing_aggregates`: this row and its sibling Sub-ICBs under the same ICB are summed into
   an ICB row (`is_derived = True`, `source_file` NA); if any sibling were `*` the ICB row would
   be a `minimum` with `value_num_upper` = lower + 4 per suppressed sibling.

For the equivalent March 2026 row the only differences are steps 1–2: the file is
`pcdem-sicbl-ethnicity-mar-2026.csv` (family `sicbl_ethnicity`), and `_shape_era_a_category` calls
`decode_era_a_measure("sicbl_ethnicity", "WHITE")`, which returns
`MeasureKey("DEMENTIA_REGISTER", "ETHNICITY", ethnicity="WHITE")`.
