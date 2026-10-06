# skill-tracer

## What this skill does

Finds bugs and verifies correctness in any target skill, codebase, or directory by running a
**2-tier cascade** each round: prepass (deterministic detectors for mechanical defects) →
code-review (two cold reviewer agents applying five lenses). From round 3 of a run the review covers
only the files the previous fixes touched; a clean review there is followed by a confirming full
sweep. Convergence is reached when, in one round, prepass finds nothing and a full-sweep review
raises nothing. The skill loops rounds automatically until convergence (or a requested round budget
or the round cap is reached).

Concrete use cases:

- **Post-build audit** — trigger: "trace skill X" after building or editing a skill → steps:
  prepass sweeps for broken refs and dead code, two cold reviewers check
  fidelity/executor-clarity/logic/integrity/design → result: all bugs
  clustered, fixed, and recorded in a ledger; converged skill ready to ship.

- **Pre-ship verification** — trigger: "is skill X clean?" before running skill-publisher →
  steps: one or more cascade rounds → result: zero-flags convergence confirmation, or a list of
  findings blocking ship.

- **Single bounded round** — trigger: "/skill-tracer skill X --rounds 1" → steps: one cascade
  round with its fixes applied → result: a ledger of that round's findings and fixes, reported as
  "stopped by budget-exhausted, not verified clean" unless the round converged.

## Intent

This skill exists to find bugs and verify correctness — not to polish, not to check portability,
not to audit CCVW compliance. Those concerns belong to other phases (skill-publisher for ship
readiness; skill-creator-ccvw for build quality). Conflating them into the tracer dilutes the
bug-finding signal and was deliberately removed in design.

**What the cascade optimizes for:**

- **Determinism + cold adversarial independence over speed and token cost.** Every cold agent
  (the code-reviewers) is dispatched with `subagent_type: Explore` so it has no Edit or
  Write tools — structural enforcement, not a prompt-only prohibition. Each agent sees the target
  cold: no sibling findings, no fix history, no "what changed" preamble. This independence is the
  adversarial-verify property — agents commit to findings before reconciliation. Any change that
  lets agents share context before reporting breaks the design's foundational guarantee and must
  be rejected, even if it would speed up a round.

- **Exhaustive per-round coverage over partial sweeps.** Convergence is keyed on whether cold
  agents surface flags, not on fix counts. A fix tally can mis-format or be incomplete;
  flags-surfaced is the robust signal. "A clean code-review IS convergence" is a load-bearing
  identity: you can only reach the code-review tier after a clean prepass in the same round, so a
  clean full-sweep code-review means both tiers verified clean in one round. A clean
  changed-files review never counts. A change that keys convergence on fix counts, or that allows
  skipping tiers, violates this.

- **Considered fixes over fast fixes.** Before applying any fix, the orchestrator weighs the
  finding against the target's documented `## Intent`. A fix that would trade away a stated design
  goal is an ORCHESTRATOR-PAUSE, not an auto-fix. The orchestrator resolves ORCHESTRATOR-PAUSEs
  from the README by default; it promotes to USER-PAUSE only when the intent is not derivable from
  the target's files. Promoting to USER-PAUSE to avoid making a derivable call is the lazy-pause
  anti-pattern and is forbidden.

**Deliberate trade-offs:**

- Rounds are more expensive than a single-pass analysis because they re-sweep from prepass after
  every code-review fix. This is intentional: any fix can introduce new mechanical defects, and
  re-verifying from the front is the only way to guarantee the cascade invariant holds at convergence.

- The FORBIDDEN-PAUSE rule prohibits offering to stop early for "diminishing returns", "tail issues",
  or token cost. The cascade either converges, exhausts its budget, or hits a genuine USER-PAUSE —
  no other stop is legitimate.

- Code-review always dispatches two generalist Sonnet agents (findings unioned before clustering),
  each applying all five lenses in one pass: two reviewers overlapped on only 8% of flags in the
  October 2026 self-run, so the second roughly doubles the finds for the cost of one more agent.

- From round 3 of a run the review reads only the files the previous fixes touched, because later
  rounds of the October 2026 self-run mostly re-reviewed unchanged files. A clean changed-files
  review always triggers a full confirming sweep, so convergence still means a whole-target pass.

- The interface is frozen from round 1 of a run: a fix adds no flag, mode, subcommand, file, ledger field, run-options
  key, row kind, shared helper module or doc section unless that is the only way to fix a real behaviour
  bug (otherwise it becomes an ORCHESTRATOR-PAUSE), and a wrong comment over correct behaviour is
  fixed in the comment, not the code. In the October 2026 runs, machinery added by earlier fixes
  drew a large share of the later flags.

- A round of 12 clusters or fewer goes to one fixer; only a larger round is split into batches of
  at most 12, one fixer per batch, run one after another (never in parallel: batches may edit the
  same files). A batch that touches a script or detector (`.py`) uses Opus; an all-doc batch uses
  Sonnet. Splitting a small round into a code and a doc fixer about doubled fixer tokens with no
  quality gain. Sonnet showed regressions on 17+ mixed clusters, so a change that enlarges batches
  or puts code clusters on Sonnet to save cost accepts that risk.
- A fixer adds no new behaviour (no new retry, cap, branch or exit path, no removed fallback): it
  makes the doc match the code or the code match its documented contract, or pauses.

- Before a fixer's decisions are recorded, `check_decisions.py` checks them (empty address, wrong
  kind prefix, banned dismissal vocabulary, missing cluster) and the same fixer re-emits on any
  problem; the fixer prompt lists those rules at its top.

**The four invariants** are the non-negotiable core: cold-read (agents always see the target
cold), considered-fix (every fix weighed against intent), no-orphan-flag (every finding gets
FIX / STRENGTHEN / ORCHESTRATOR-PAUSE — no finding is silently dropped), and WHY-strengthening
(when a finding flags a missing rationale for an intentional design decision, the fix is to add
the WHY, not remove the rule).

## When to use / When NOT to use

**Use when:**
- A skill was just built or edited and you want to find its bugs before shipping.
- You want a structured correctness audit of any CCVW skill or arbitrary codebase directory.
- You are about to run skill-publisher and want to confirm the target is clean first.

**Don't use when:**
- You want prose polish, portability checks, or CCVW compliance auditing → use `/skill-publisher`
  (ship phase) for those.
- The skill is still mid-feature-development and structurally incomplete → defer to
  `/skill-creator-ccvw` and finish building first; the cascade assumes a runnable target.
- You are inside a nested Agent call — skill-tracer requires the `Agent` tool, which is only
  available in the top-level Claude session. Attempting to invoke it as a subagent will fail;
  the skill detects this and stops immediately with an explanation.

## How to install

Copy the `skill-tracer/` folder to `~/.claude/skills/skill-tracer/` and confirm
`SKILL.md` is present. No external services or network access required.

## How to invoke

- Slash command: `/skill-tracer <skill-name-or-absolute-path>`
- Natural language: "trace skill X", "audit X for bugs", "check X for issues", "verify skill X",
  "run the cascade on X", "is skill X clean?"
- Flags: `--rounds N` (run at most N rounds, stopping earlier at convergence; `--rounds 1` for a
  single round)

Example:
```
/skill-tracer drive-organizer

→ Round 1:
    Tier 1 (prepass): sweeps for broken refs, dead code, lint — clusters and blast-fixes until clean.
    Tier 2 (code-review): dispatches 2 cold Sonnet generalists on the all-lens prompt →
      unions findings → orchestrator clusters → one fixer (batches of ≤12, one at a time, above 12)
      (Opus for code, Sonnet for docs), each checked by check_decisions.py.
→ If code-review has flags: fixes applied, round closes, re-enters at prepass for round 2.
→ From round 3: code-review reads only the changed files; if that is clean, a full sweep confirms.
→ If a full-sweep code-review is clean: converged. Skill is clean.
→ At convergence: "Converged after N round(s). Zero flags surfaced in the final full sweep."
   Audit ledger at $XDG_DATA_HOME/skill-tracer-audit-ledger/drive-organizer.md
   (default: ~/.local/share/skill-tracer-audit-ledger/drive-organizer.md)
   Suggested next step: /skill-publisher drive-organizer
```

## Known limits

v3.6 did not converge in its own self-run (it stalled after round 4 and a final sweep still found 2 flags). Its two cold reviewers vary between runs, so a clean round is weaker evidence than it looks, and the block-reread gate trusts the fixer's `Blocks:` line rather than verifying the re-read. Treat a converged run as strong but not conclusive. Details: the 3.6.0 entry in HISTORY.md.

## Sibling skills

- `skill-creator-ccvw` — the **build** phase; scaffolds a skill from intent-capture through
  SKILL.md authoring. Use before tracing: build → trace → ship.
- `skill-publisher` — the **ship** phase; polishes the README, runs the CCVW audit + simplify
  pass, checks portability and attribution, bumps version, opens a PR. Run after the tracer
  converges.

## For developers

The runtime workflow (cascade stages, script contracts, ledger format, recovery protocol) lives
in [`SKILL.md`](SKILL.md). Provenance and changelog live in [`HISTORY.md`](HISTORY.md). To trace
this skill for bugs: `/skill-tracer skill-tracer`. To ship a new version:
`/skill-publisher skill-tracer`.
