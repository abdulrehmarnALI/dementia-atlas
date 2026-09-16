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
silver_loader.load_file()                   + value parsing, dates, DQ, era, comparability
        │     uses  silver_schema            classify_values, parse_period_end, conform, …
        ▼
silver_loader.load_release()                drop published all-sex rows, recompute them
        │     uses  derived_rows
        ▼
silver_loader.build_silver()                all releases → one frame; revision check
        │
        ▼
build.py                                    writes Parquet to data/processed/silver/

mapping_loader                              separate: practice → Sub-ICB → ICB → region snapshots
```

Two modules predate all of this and aren't part of the build: `data_sources.py` and `ingest.py` are
S3 download stubs from before the raw files were kept locally. Nothing imports them.

The dependency direction is strictly downward: the crosswalks and the schema know nothing about
files; the loader knows about everything. If you're looking for *why* a value is what it is, start
at the loader and follow the imports.

---

## `silver_schema.py` — the shape of a silver row, and the small parsers

**What it does.** Defines `SILVER_COLUMNS` (the 22 columns every silver row has, with their pandas
dtypes, in canonical order) and `SILVER_KEY` (the 11 columns that identify one observation). Then
four parsers that turn published text into typed columns: `classify_values`, `parse_dq_flag`,
`parse_dates` / `parse_period_end`, and two release-level lookups, `publication_era` and
`dictionary_version`. `conform()` forces any frame into the canonical column order and dtypes.

**The rule that matters most.** `value_raw` is kept verbatim and everything else is derived from
it. `classify_values` never turns an unknown token into NaN — it raises and names the token. That's
deliberate: NHS England has already used `*`, blank, `N/A`, `NULL` and `.` as sentinels with
different meanings, and a new one should stop the build, not vanish.

**Where it's denser than it looks.**

- `classify_values` builds `value_state` by *overwriting in sequence*: first every row that parsed
  as a number gets `numeric`, then rows equal to `*` get `suppressed`, then blank/`.` get `blank`,
  then `N/A` gets `not_applicable`. Order doesn't actually matter (the conditions are mutually
  exclusive) but reading it as "later assignments win" is the right mental model. Anything still
  unassigned at the end is an unknown token → error.
- `parse_dates` handles the publisher's three date spellings by running one regex per spelling and
  parsing only the rows that match it (`out[mask] = pd.to_datetime(raw[mask], format=…)`). Rows
  matching no spelling stay `NaT` and trigger the error. So the function is "try each known format
  on the rows that look like it", not "guess".
- `publication_era` deliberately *refuses* `2026-04` and `2026-05`. The Era-A/Era-B boundary has
  only been observed between the March and June 2026 releases; a file from the gap would need
  classifying by eye first.
- `dictionary_version` is computed, not looked up: the financial year of the release month gives
  `PCDD-2526`, `PCDD-2627`, and so on. It matches the two dictionaries on disk; it assumes NHS
  England issues exactly one per financial year.

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
   at 2025-08 mid-series. The loader puts the *canonical* code in `org_code` (so a series joins)
   and the *published* code in `ons_code` (so nothing is lost).
4. The 2026-04 ICB reorganisation. This is the part to read slowly:
   - Old ICB → new ICB is **many-to-many** (QJG and QM7 each split across two new ICBs), so there
     is no ICB-to-ICB rename table. The authoritative record is `SUB_ICB_ICB_REASSIGNMENTS_2026_06`:
     for each of the 23 Sub-ICBs whose parent changed, `(old_icb, new_icb)`.
   - `icb_successors(old)` derives "which new ICBs absorbed this old one" from that table; it can
     return several codes, or none (QNQ's only Sub-ICB was itself closed).
   - `new_icb_for_sub_icb(sub, old_parent)` gives the post-reorg parent, and *raises* if the caller's
     idea of the old parent disagrees with the table — a mismatch means the source data and the
     crosswalk have diverged, and guessing would hide that.
   - One Sub-ICB (`D4U1Y`, Frimley) closed and was split three ways. `SUB_ICB_SUCCESSORS_2026_04`
     records where its practices went; `SUB_ICB_BOUNDARY_BREAKS_2026_04` lists the three receiving
     Sub-ICBs, two of which keep their code but not their geography. `sub_icb_series_break(code)`
     is the one function the app layer should call: it answers "from what period is this Sub-ICB's
     history not comparable with its present?"

**Naming note.** The ICB-reorg constants carry a `_2026_06` suffix (the release where the change
was first *seen*) while the Sub-ICB ones carry `_2026_04` (when it legally *happened*, per ODS).
Both refer to the same event; `ICB_REORG_EFFECTIVE` and `ICB_REORG_FIRST_OBSERVED_RELEASE` spell out
the distinction.

---

## `measure_crosswalk.py` — what a row measures, across eras

**What it does.** Era A encodes "what is counted" and "which category" in one `Measure` string whose
meaning depends on which file it came from (`WHITE` in the ethnicity file; `FEMALE_AGED_65_69` in
the age/sex file; `MCI_MALE_AGED_40_44` in the cognitive-impairment file). Era B has explicit
`MEASURE`, `BREAKDOWN` and five dimension columns. This module decodes Era A *into* Era B's shape,
using Era B's own tokens as the silver vocabulary.

**Key pieces.**

- `MeasureKey` — a frozen dataclass: `measure, breakdown, age, gender, ethnicity, dementia_type,
  residential_type`, with dimensions defaulting to `ALL`. Frozen so it's hashable — the loader
  decodes each *distinct* Measure string once and maps rows through a dict.
- `decode_era_a_measure(family, measure)` — one `if family == …` branch per Era-A file family. Each
  branch either returns a `MeasureKey` or falls through to the `ValueError` at the bottom, so an
  unexpected string in a known file, or a known string in the wrong file, both fail. The
  `_PLAIN_MEASURES` set covers measures with no breakdown at all (`INCIDENCE`, `DELIRIUM_12M`, …),
  which decode to `breakdown = "N/A"` — Era B's own token for "no breakdown".
- Three Era-A totals that Era B never publishes as a single row (all-age register, 65+ register,
  all-age list size) decode to `breakdown = "N/A"` with `age = "65_PLUS"` where relevant. `65_PLUS`
  and `0_64` are published tokens (from Era B's practice file), not invented ones.
- `normalise_gender()` — Era A spells `FEMALE`/`MALE`; Era B spells `Female`/`Male` except on
  `PAT_LIST` rows where it reverts to upper case. One function, three spellings in, one out.
- `CROSS_ERA_COMPARABILITY` / `cross_era_comparability(measure, breakdown)` — a per-(measure,
  breakdown) label from the QA notebook's §7.2 table: `comparable`, `labels_only` (same categories
  but Era-A values suppressed), `not_comparable` (definition changed), `era_a_only`, `era_b_only`.
  **Lookup is two-step:** exact `(measure, breakdown)` first, then `(measure, "*")` as a wildcard
  for measures whose every breakdown has the same answer (`FRAILTY`, `PRESCRIBING`, …). Neither
  found → `KeyError`, so a new breakdown in a future release has to be classified on purpose.

---

## `derived_rows.py` — rows silver computes rather than stores

**What it does.** Era A publishes an `ALL_AGED_<band>` row that is provably Female + Male. Storing
it would make any sum over gender double-count, so `drop_published_all_sex_rows()` removes it and
`derive_all_sex_rows()` rebuilds it — for both eras, from one rule, with `is_derived = True` and no
`value_raw`. `sum_with_state()` states the rule in its simplest form: all inputs numeric → numeric
sum; any input suppressed → the total is suppressed; otherwise blank.

**The vectorised grouping in `derive_all_sex_rows` — what it's actually doing.**

The obvious implementation is "group the Female/Male rows by everything except gender, loop over
the groups, call `sum_with_state` on each". That's a Python loop over ~35,000 groups per build, so
the function does the same thing with column arithmetic instead. Read it in four steps:

1. **Keep only the rows that can contribute**: `breakdown == AGE_GENDER` and `gender` is `Female`
   or `Male`. (Existing `ALL` rows are ignored, whether published or derived.)
2. **Turn the facts we need about each row into 0/1 columns**: `_female`, `_male`, `_numeric`,
   `_suppressed`. Summing a 0/1 column inside a group is the same as counting.
3. **Group by `GROUP_COLUMNS`** — every silver column except gender, the value columns, `dq_flag`,
   `is_derived` and `ingested_at` — and aggregate. After this, one row per would-be ALL row, with:
   `n` (rows in the group), `female`, `male` (should each be 1), `n_numeric`, `n_suppressed`,
   `total` (pandas `sum`, which skips NaN, so it's a *partial* sum whenever anything was
   non-numeric), and `ingested_at` carried through. `dropna=False` is essential: `ons_code` can be
   NA and pandas would otherwise silently drop those groups.
4. **Apply the rule with masks**: keep only groups with exactly one Female and one Male
   (`n == 2 & female == 1 & male == 1` — a group missing a sex produces nothing, because absence of
   a row is not a zero). Then `all_numeric = n_numeric == 2`; `value_num` is the total where
   all-numeric and NaN otherwise; `value_state` starts as `numeric`, is overwritten to `blank` for
   any non-all-numeric group, and overwritten again to `suppressed` where the group had a
   suppressed input. That last pair of `.loc` assignments *is* `sum_with_state`'s if/elif chain,
   expressed as two overlapping masks applied in priority order.

Finally the frame is put back into silver column order and dtypes.

---

## `silver_loader.py` — raw files in, silver rows out

**What it does.** The only module that knows about file names and raw column names.

- `classify_file(name)` — regex on the file name → a family name. Era-A families come from
  `measure_crosswalk.era_a_family_for_filename`; everything else from `_OTHER_FAMILY_PATTERNS`.
  `LOADED_FAMILIES` is the subset the build actually loads; the Era-A practice files are classified
  (so nothing is "unrecognised") but skipped on purpose.
- One `_shape_<family>()` function per raw layout. Each returns the same intermediate frame: the
  silver grain columns, plus `value_raw` and `dq_raw` as published text. This is where the
  crosswalks are applied. Nothing is parsed yet.
- `load_file()` takes that shaped frame and adds everything else: provenance columns, parsed
  dates, `value_num`/`value_state`, the DQ flag, `comparability`. Then `conform()`.
- `load_release()` concatenates a folder's files, drops the published all-sex rows, derives them,
  and asserts `SILVER_KEY` is unique.
- `build_silver()` does that for every release folder and runs `find_revisions()`; a non-empty
  result stops the build with the first few offending rows in the message.
- `resolve_latest_release()` collapses to one row per observation, newest `source_release` winning.
  `OBSERVATION_KEY` is `SILVER_KEY` minus `source_release`.

**Where it's denser than it looks.**

- `_shape_rate` for `la_rate`:
  `raw["ONS_CODE"].where(org_level != "ltla", raw["ONS_CODE"].map(canonical_ltla_ons_code))`.
  pandas' `where` keeps the left-hand value *where the condition is true* and takes the right-hand
  value elsewhere — so this reads: "use the published ONS code, except for LTLA rows, where the
  canonical code is used". Easy to read backwards.
- `_decode_measures` decodes each distinct Measure string once into a `MeasureKey`, maps rows to
  keys, then unpacks the key's seven fields into seven columns with seven small `.map`s.
- `load_file` builds `comparability` the same way: one lookup per distinct `(measure, breakdown)`
  pair, then a list comprehension over rows.
- `find_revisions`: restrict to published (non-derived) rows, keep only observations that appear in
  more than one release, count distinct `value_raw` per observation, and return the rows for
  observations where that count is above one. It compares the *raw* token, so `*` versus `3` is a
  revision, and so would `62` versus `62.0` be.
- `resolve_latest_release` relies on `source_release` strings sorting chronologically, which
  `YYYY-MM` does.

---

## `mapping_loader.py` — the practice → Sub-ICB → ICB → region snapshots

**What it does.** Each release ships one snapshot of which practice belongs to which Sub-ICB, ICB
and NHS region, as of an extract date *after* the reporting period. `load_mapping()` turns it into a
dimension table with a fixed 19-column shape across both eras (Era-A-only columns like PCN and
supplier become NA in Era B). `hierarchy()` reduces a snapshot to distinct Sub-ICB → ICB → region
triples and refuses a snapshot where a Sub-ICB has two parents.

**Two things to know.**

- June 2026 has one row whose three hierarchy codes are the literal string `NULL`. With pandas'
  defaults that reads as NaN and looks like missing data; here it's detected before any NA
  replacement and becomes `unmapped = True`, with the codes then set to NA. Practices in the
  observation frame are meant to be *left*-joined to this table; an unmapped practice keeps its
  rows.
- Names are stripped of whitespace (the May 2025 file has trailing spaces on some ICB names) and
  are for display only. Never join on them.

---

## `build.py` — the command

`python -m src.build` from `pipeline/`. Optional release names as arguments restrict the build.
Writes the full observation frame and the latest-wins frame to `data/processed/silver/`.

---

## How to trace one number

Take a June 2026 Sub-ICB row for `DEMENTIA_REGISTER`, `ETHNICITY = WHITE`, value `849`.

1. `classify_file("pcdem-sub-icb-jun-2026.csv")` → `sub_icb_consolidated`.
2. `_shape_era_b_sub_icb`: `ORG_TYPE = SUB_ICB` → `org_level = sub_icb`; `ODS_CODE` → `org_code`;
   dimensions copied across; gender normalised; `value_raw = "849"`.
3. `load_file`: `period_end = 2026-06-30`; `value_num = 849.0`, `value_state = numeric`;
   `dq_flag = False`; `comparability = comparable` (from the table, `("DEMENTIA_REGISTER",
   "ETHNICITY")`); `publication_era = B`; `dictionary_version = PCDD-2627`.
4. `load_release`: not an all-sex row, so kept as published; `is_derived = False`.
5. `build_silver`: appears in one release only, so no revision check applies.

For the equivalent March 2026 row the only differences are steps 1–2: the file is
`pcdem-sicbl-ethnicity-mar-2026.csv` (family `sicbl_ethnicity`), and `_shape_era_a_category` calls
`decode_era_a_measure("sicbl_ethnicity", "WHITE")`, which returns
`MeasureKey("DEMENTIA_REGISTER", "ETHNICITY", ethnicity="WHITE")`.
