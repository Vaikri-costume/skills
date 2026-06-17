# skill-tracer

## What this skill does

Finds bugs and inconsistencies in any skill by reading it cold from three independent directions — forward (does each claim match reality?), backward (does each producer's output have a documented consumer?), and executor (can the executor act on each line without guessing?). Three agents read the target in parallel, blind to each other, then the orchestrator collects their findings, applies considered fixes that preserve the skill's intent, and re-dispatches cold until all three come back clean.

On the **first round of a brand-new skill** (and of a re-trace of a skill that changed since it last converged), skill-tracer first runs one full-depth local pass of the sibling `code-review` skill (`/code-review max`, no issue cap) over the **whole skill** (every file's full contents, not a diff) — as the first phase of round 1. Its findings route through the same considered-fix gate and are recorded in the ledger; then the cold trace runs in the second phase of the same round. At convergence it suggests a final `/code-review` pass over the finished skill.

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

`claude-users` tier — a meta-skill (it operates on other skills), shareable to anyone running Claude Code or Cowork.

- **Claude Code / Cowork (marketplace):** install from the `Vaikri-costume/skills` marketplace, then invoke `/skill-tracer`. (See that repo's README for the exact `claude plugins` command for your setup.)
- **Manual:** copy this folder to `~/.claude/skills/skill-tracer/`.
- **Claude.ai web:** zip the skill folder and upload via **Settings → Capabilities → Skills**.

## How to invoke

- Slash command: `/skill-tracer <skill-name>` or `/skill-tracer <absolute-path>`
- Natural language: "trace skill X", "audit X for issues", "check skill X", "is skill X clean", "review skill X", "validate skill X"
- Modes: `--one-round` (diagnostic snapshot), `--verify-only` (report would-be fixes, apply none), `--audit-fixes` (check whether ledger-recorded fixes since the last convergence actually landed — read-only)

Example:
```
"/skill-tracer my-pdf-summarizer"
→ 3 cold agents (forward/backward/executor) read it independently → orchestrator clusters findings
→ applies intent-preserving fixes → re-dispatches cold → converges when all 3 return clean
→ suggests /skill-publisher to ship
```

## Quick start

1. **Point it at a skill:** `/skill-tracer <skill-name>` (or an absolute path). No setup — it reads the skill cold.
2. **Round 1 (new/updated skills):** it first runs a full-depth `/code-review` pass over the whole skill, then dispatches the three cold trace agents (forward, backward, executor).
3. **Review mid-run (optional):** each round it surfaces clustered findings and the fixes it's applying; an intent-ambiguous fix is paused for your decision (USER-PAUSE). You don't have to intervene — it converges on its own.
4. **Convergence:** the loop repeats until all three directions return clean in one cold round; the audit ledger (HTML) opens with every finding mapped to its fix.
5. **Then ship:** it suggests `/code-review max <skill>` once more, then `/skill-publisher <skill>`.
- **Other things you can do:** `/skill-tracer <skill> --one-round` for a one-shot diagnostic snapshot; `--verify-only` to preview fixes without applying; `--audit-fixes` to check that past fixes actually landed. Full reference: [`SKILL.md`](SKILL.md).

## Sibling skills

- `code-review` — full-depth local/cloud code review. skill-tracer **invokes** it at round 1 of a new (or updated-since-convergence) skill — `/code-review max`, full local depth, no issue cap — and routes the findings through its considered-fix gate into the ledger (`REVIEW`-phase rows, `CR*` flags). After convergence it suggests running `/code-review` once more on the finished artifact.
- `skill-creator-ccvw` — the **build** phase. Scaffolds the skill; suggests trace at iterate-end.
- `skill-publisher` — the **ship** phase. Polishes + tier-checks + PRs. The CCVW audit + simplify pass that used to live in tracer moved there.
- `deep-research`, `pr-review-toolkit` — adversarial-verify lineage (see HISTORY.md inspirations).
- `ralph-loop` — the inline-loop shape Step 7 specializes.

## For developers

The runtime workflow lives in [`SKILL.md`](SKILL.md). Provenance and changelog live in [`HISTORY.md`](HISTORY.md). To trace this skill for bugs: `/skill-tracer skill-tracer`.
