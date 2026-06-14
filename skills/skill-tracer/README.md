# skill-tracer

## What this skill does

Finds bugs and inconsistencies in any skill by reading it cold from three independent directions — forward (does each claim match reality?), backward (does each producer's output have a documented consumer?), and executor (can the executor act on each line without guessing?). Three agents read the target in parallel, blind to each other, then the orchestrator collects their findings, applies considered fixes that preserve the skill's intent, and re-dispatches cold until all three come back clean.

It's the **trace** phase of the build → trace → ship ecosystem: **build** (skill-creator-ccvw) → **trace** (this skill) → **ship** (skill-publisher).

## Intent

This skill prioritizes **finding real bugs over breadth of concern**. It does ONE thing — correctness — and deliberately doesn't do quality polish, portability checks, CCVW compliance audits, or attribution validation. Those belong to the builder (quality) and the publisher (ship-readiness). Conflating them into the tracer (as earlier versions did) diluted the bug-finding and made every trace round carry concerns that weren't correctness.

The **cold-trace invariant** is load-bearing: each agent dispatch is independent, sees no sibling findings, no fix history, no "what changed" preamble. This is the adversarial-verify pattern — independent agents committing to claims before reconciliation. A change that lets agents see each other's findings, or feeds them the orchestrator's intent, breaks the independence the whole design depends on and must be rejected. (The orchestrator alone reads the target's README Intent — the cold agents never do.)

It optimizes for **considered fixes over fast fixes**: between rounds the orchestrator weighs each finding against the target skill's documented intent, and a fix that would trade away stated intent is surfaced as a USER-PAUSE rather than applied automatically.

## When to use / When NOT to use

**Use when:**
- A skill was just built or edited and you want to find its bugs ("trace skill X", "is X clean?")
- You want a structured correctness audit of any skill (not just CCVW skills)
- Before shipping — run trace, then `/skill-publisher`

**Don't use when:**
- You want to polish prose, check portability, or audit CCVW compliance → that's `/skill-publisher` (ship phase)
- You're still building/iterating → `/skill-creator-ccvw`
- The skill is mid-feature-development → defer to feature-dev first (trace assumes structural completeness)

## How to install

Already installed locally at `~/.claude/skills/skill-tracer/`. Personal-tier meta-skill.

## How to invoke

- Slash command: `/skill-tracer <skill-name>` or `/skill-tracer <absolute-path>`
- Natural language: "trace skill X", "audit X for issues", "check skill X", "is skill X clean", "review skill X", "validate skill X"
- Modes: `--one-round` (diagnostic snapshot), `--verify-only` (report would-be fixes, apply none)

Example:
```
"/skill-tracer my-pdf-summarizer"
→ 3 cold agents (forward/backward/executor) read it independently → orchestrator clusters findings
→ applies intent-preserving fixes → re-dispatches cold → converges when all 3 return clean
→ suggests /skill-publisher to ship
```

## Sibling skills

- `skill-creator-ccvw` — the **build** phase. Scaffolds the skill; suggests trace at iterate-end.
- `skill-publisher` — the **ship** phase. Polishes + tier-checks + PRs. The CCVW audit + simplify pass that used to live in tracer moved there.
- `deep-research`, `pr-review-toolkit` — adversarial-verify lineage (see HISTORY.md inspirations).
- `ralph-loop` — the inline-loop shape Step 7 specializes.

## For developers

The runtime workflow lives in [`SKILL.md`](SKILL.md). Provenance and changelog live in [`HISTORY.md`](HISTORY.md). To trace this skill for bugs: `/skill-tracer skill-tracer`.
