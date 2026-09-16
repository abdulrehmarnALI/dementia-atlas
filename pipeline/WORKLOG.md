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
