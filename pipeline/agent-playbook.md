# Agent Playbook

_Distilled practices for working with coding agents, adapted to this repo. Drawn from the patterns
that recur across Anthropic's own Claude Code guidance and the better community collections
(`awesome-claude-code`, `claude-code-best-practices`, and similar). Not exhaustive — the useful
subset, with the reasoning kept in so it can be adapted rather than followed blindly._

---

## The core idea

Agents fail in two directions. They do **too little** — asking permission for every step, losing
context between sessions, re-deriving things already established. Or they do **too much** — one
session produces a thousand lines across fifteen files, all of it plausible, none of it reviewable,
and now you own code you don't understand.

Everything below is aimed at the second failure. The fix is never "write a better prompt." It's
structural: give the agent persistent context so it doesn't drift, and give it checkpoints so work
arrives in units you can actually check.

## Context files

**The memory hierarchy.** Three kinds of file, and mixing them is the most common mistake:

| File | Holds | Changes |
|---|---|---|
| `CLAUDE.md` | Working rules, conventions, where things live | Rarely |
| `docs/context.md` | Project background, scope, decisions and their reasoning | When a decision is made |
| `NOW.md` | What's in progress and queued | Every session — **overwritten, never appended** |
| `WORKLOG.md` | What happened | Every session — **appended, never rewritten** |

`CLAUDE.md` is loaded automatically at the start of every Claude Code session. That's its power and
its constraint: it's always in context, so it should be short and stable. Anything long, or
anything that changes often, belongs in a file it *points to* rather than in the file itself.

**Keep it tool-agnostic where you can.** `CLAUDE.md` is Claude-specific by name. Project knowledge
isn't — put it somewhere any assistant (or any human) can be pointed at, and have `CLAUDE.md`
reference it. Saves re-explaining the project every time you switch tools.

**Write rules as rules, not as prose.** "Use CSS Modules, not Tailwind" survives being skimmed.
"We've generally found CSS Modules works better for us" doesn't.

**Treat context files as living.** When an agent gets something wrong that it could have got right
with better information, the fix goes in the context file — not just in that session's correction.
A rule you have to repeat is a rule that belongs written down.

## Controlling scope

**Small, checkpointed units beat one big run.** Not because agents can't do big runs — they can —
but because a big run produces a review burden you'll skip, and skipped review is how you end up
maintaining code nobody read.

**Say where to stop, not just what to do.** The most useful line in any agent instruction is the
one describing the stopping condition. "Build the crosswalk, add tests, update the log, then stop
and summarise" produces reviewable work. "Build the silver layer" produces a weekend of archaeology.

**Tune the leash to the task.** Well-specified, evidence-backed, low-ambiguity work — let it run
through several tasks. Anything involving a judgement call, a new dependency, or a structural
decision — checkpoint before it, not after.

**Ask for plan-then-execute on anything substantial.** Having the agent state its approach before
writing code costs one exchange and catches misunderstandings while they're still cheap. Especially
worth it when you're not certain you specified the task well.

## Keeping work reviewable

**Demand a plain-English summary at the end of every session.** What was built, what was decided
and why, what turned up unexpectedly, what's next. This is the single highest-leverage habit:
it means you can stay oriented by reading four sentences rather than a diff.

**Make the agent write down what it found, not just what it did.** Unexpected discoveries are the
most valuable output of a session and the easiest to lose. A log entry noting "the test file
CLAUDE.md references doesn't exist" is worth more than the code that session produced.

**Commit as you go, in logical units.** One change per commit, with the *why* in the body when it
isn't obvious from the subject. Good commit history is the cheapest documentation there is, and it
makes a large session reviewable commit-by-commit instead of all at once.

**Tests that can't cheat.** Where a test exists to prove a claim about data, derive the claim
independently — different code path, ideally plainer tools — rather than calling the function under
test. A test that shares a bug with its subject passes happily and proves nothing.

## Prompting patterns that hold up

- **Point at files, don't paste them.** "Read `docs/context.md`" beats pasting its contents. The
  agent reads what it needs, and the file stays the single source of truth.
- **Reference prior decisions by name.** "Follow the revision policy in context.md" rather than
  re-explaining it — cheaper, and it keeps the written version authoritative.
- **Separate "explore" from "implement."** Asking for investigation and implementation in one go
  tends to produce implementation of an under-investigated problem. Two turns is usually faster in
  wall-clock terms.
- **Give it permission to say it doesn't know.** Agents default to producing an answer. Explicitly
  routing uncertainty somewhere — "add it to Needs a decision rather than picking one" — is what
  turns a silent guess into a flagged question.
- **Be specific about what not to touch.** Scope boundaries are easier to state than to infer.

## Anti-patterns

- **Letting `NOW.md` accumulate.** It's a snapshot. If it's growing, it's turned into a second
  worklog and stopped being scannable.
- **Vague quality words.** "Make it robust," "production-ready," "clean this up" — these license
  arbitrary amounts of work. Name the specific property you want.
- **Accepting work you haven't understood because it looks impressive.** Volume and correctness are
  uncorrelated. If you can't summarise what a session did, that's the signal to slow down, not to
  keep going.
- **Fixing the same misunderstanding in chat repeatedly.** Third time means it belongs in
  `CLAUDE.md`.
- **Letting the agent push, or work on branches, without a reason.** Commits are recoverable;
  pushes are public. Keep the boundary.

## Maintenance

Every few sessions, skim `CLAUDE.md` and ask: is anything here stale, contradicted by how the
project actually works now, or being ignored? Stale rules are worse than no rules — they get
followed. Two of the four items in this repo's first `NOW.md` were references to files that turned
out not to exist; that's normal, and catching it is the point.
