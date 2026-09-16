# PCDD Data Pipeline — Claude Code Guide

_This file lives at `pipeline/` in the Dementia Atlas repo, alongside `data/`, `notebooks/`, `src/`,
`tests/`, `web/`. The wider repo also has `api/`, `db/`, `infra/` and `docs/` at the root — this
file only governs work done inside `pipeline/`._

## Read these first, every session

1. **`../docs/context.md`** — what this project is, why it's sequenced this way, what "done" looks
   like for the current phase, decisions already made, open questions. Read this before anything
   else; it's the file that explains *why*.
2. **`../docs/findings.md`** — the EDA findings, §1–§10, with evidence for every claim. The
   reference for any schema or crosswalk decision.
3. **`NOW.md`** — what's in progress and what's queued.
4. **`WORKLOG.md`** — skim the last two or three entries for where the previous session left off.

## What this is

This folder is the data pipeline for the **UK Dementia Atlas** (the Next.js + PostGIS + MapLibre
web app that lives in `web/`). It ingests NHS England's Primary Care Dementia Data (PCDD) and turns
it into the tables the Atlas will query.

Architecture: **bronze → silver → gold.** Silver is the current phase — see `../docs/context.md`
for the full seven-point definition of what finishing silver means.

Raw releases live under `data/raw/pcdd/<YYYY-MM>/`. `notebooks/03_cross_release_qa.ipynb` is the
EDA notebook — **historical evidence, not production code.** Don't edit it, refactor it, or import
from it. New logic goes in `src/` (building on `data_sources.py`, `ingest.py`, `org_crosswalk.py`),
backed by tests.

## How to work

**Aim for a whole milestone per session, not a single task.** Work through `NOW.md`'s queue in
order and keep going as long as the next item is unblocked and you're not guessing. Chaining three
or four related tasks together is fine and expected. Finishing the silver layer over several
sessions is the goal.

**Stop and check in when — and only when —**
- you hit something in "Needs a decision" territory: a genuine fork where the data can't settle it
  and picking wrong would be expensive to unwind;
- a task turns out to be blocked (missing data, missing file, an assumption that didn't hold);
- you've finished the queue, or finished a coherent chunk of it and the next item is a different
  kind of work;
- you're about to do something structural that wasn't in `NOW.md` — a big refactor, a new
  dependency, restructuring `src/`, touching anything outside `pipeline/`.

**Don't** stop just to report progress mid-flow, and don't ask permission for the obvious next step
of a task already queued.

**Keep the trail readable.** The reason for `NOW.md` and `WORKLOG.md` is that Sunshine should be
able to understand a session by skimming five lines, not by reading the transcript. Volume of work
is fine; opacity isn't. So:
- Update `NOW.md` as you go — move items out of the queue as they're done, add anything new to
  "Blocked" or "Needs a decision" the moment you hit it.
- Add **one** `WORKLOG.md` entry per session, at the end, a few lines, plain English.
- When you finish, summarise in plain English: what you built, what you decided and why, what you
  found that you weren't expecting, and what's next.

**Evidence over invention.** Every schema or crosswalk decision traces to `../docs/findings.md`, to
the QA notebook, or to a fresh check you ran and wrote down. If you genuinely can't settle
something from the data, put it under "Needs a decision" in `NOW.md` and carry on with something
else — don't pick an answer quietly and build on it.

**New logic gets a test.** Follow the pattern in `tests/test_org_crosswalk.py`: re-derive the claim
from the raw CSVs with plain pandas, independently of the module under test, so a bug in the module
can't make its own test pass.

**Scope discipline.** This phase is pipeline-only. Don't touch `web/`, `api/`, `db/` or `infra/`
unless a task explicitly says to. If a task is ballooning, prefer finishing a narrower version well
over a broad version you then have to explain.

## Git

Match the existing history — it's a clean conventional-commits log on `master`, no PR workflow.

- **Commit as you go**, at natural checkpoints — one logical change per commit, not one giant
  end-of-session dump. A new module and its tests can be one commit; that module plus an unrelated
  docs fix should be two.
- **Format:** `type: lowercase description`. Types in use: `feat`, `fix`, `docs`, `chore`, `wip`.
  Use `wip` honestly, for genuinely exploratory commits that aren't finished.
- Keep the subject line under ~72 chars. Add a body when the *why* isn't obvious from the subject —
  especially for data decisions ("keyed per Sub-ICB because QJG and QM7 each split across two new
  ICBs").
- **Don't push without being asked.** Commit freely; leave pushing to Sunshine unless told
  otherwise.
- Don't create branches, don't rewrite history, don't amend past commits.
- Never commit anything from `data/raw/` or `.venv/`. If something's missing from `.gitignore`, fix
  the ignore file rather than working around it.

## Key facts worth not re-deriving

- Two schema eras: Era A (May 2025, March 2026 — split files, rolling 13-month window) and Era B
  (June 2026 onward — consolidated files, single period). Findings §3.
- No revisions found between overlapping Era-A releases — 35,302 observations, 100% identical.
  Findings §5.
- Era B publishes one month only. Every monthly release must be ingested or that month is lost
  permanently. Findings §4.
- `ALL_AGED_*` = `Female + Male` in 100% of Era-A cells — derive it, never store it. Findings §7.
- Suppression is per-measure, not global. `*` means an integer in 0–4, not missing. Findings §6.
- ICB is the least stable geography and cannot be trended across 2026-06. Findings §8.
- Never join on organisation names. Findings §8.
