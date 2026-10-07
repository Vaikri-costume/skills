# skill-tracer

## What this skill does

Finds bugs and verifies correctness in any target skill (or another directory of docs and scripts
named by path) by running a
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

- A tier pass of 12 clusters or fewer goes to one fixer; only a larger pass is split into batches of
  at most 12, one fixer per batch, run one after another (never in parallel: batches may edit the
  same files). A pass of more than 15 clusters uses Opus fixers; a smaller one uses Sonnet.
  Splitting a small round into a code and a doc fixer about doubled fixer tokens with no quality gain. Sonnet showed regressions on 17+ mixed clusters, so a change that enlarges batches
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
- You want a structured correctness audit of any CCVW skill, or of a directory of docs and scripts named by path.
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
- Flags: `--rounds N` (run at most N rounds; stops earlier at convergence)
- Round cap: without `--rounds` a run stops after 8 rounds; `--rounds` above 8 raises the cap
- Resume: invoke it again on the same target to finish an open round after an interruption
- A bare name resolves to `~/.claude/skills/<name>/`; an absolute path can be any directory
- It may also start on its own after a skill is created or significantly edited
- Run it from the top-level Claude session (it dispatches agents)

Example:
```
/skill-tracer drive-organizer

→ Round 1:
    Tier 1 (prepass): sweeps for broken refs, dead code, lint — clusters and blast-fixes until clean.
    Tier 2 (code-review): dispatches 2 cold Sonnet generalists on the all-lens prompt →
      unions findings → orchestrator clusters → fixers (batching and model: SKILL.md "Fixer dispatch"),
      each checked by check_decisions.py.
→ If code-review has flags: fixes applied, round closes, re-enters at prepass for round 2.
→ Later rounds re-review changed files; a clean one is confirmed by a full sweep.
→ If a full-sweep code-review is clean: converged. Skill is clean.
→ At convergence: "Converged after N round(s). Zero flags surfaced in the final full sweep."
   Audit ledger at $XDG_DATA_HOME/skill-tracer-audit-ledger/drive-organizer.md
   (default: ~/.local/share/skill-tracer-audit-ledger/drive-organizer.md)
   Suggested next step: /skill-publisher drive-organizer
```

## Features & modes

- **Full audit (default).** `/skill-tracer <skill-name-or-absolute-path>`, or say "trace skill X", "audit X for bugs", "check X for issues", "verify skill X", "run the cascade on X", "is skill X clean?". Audits round after round until the target is verified clean, a round limit is reached, or a decision from you is needed. Each round has two stages: a deterministic prepass (broken file references, bad `Step N` pointers, dead scripts, mismatched sub-step labels, undocumented flags, duplicated regexes), then a code review by two independent read-only reviewer agents. Findings are grouped by root cause, fixed inside the target and recorded.
- **Bounded run.** `/skill-tracer <target> --rounds N` runs at most N rounds and stops earlier on convergence. If the budget runs out first, the result is reported as "stopped by budget-exhausted, not verified clean". `--rounds 1` is a single audit-and-fix pass.
- **Round cap.** Without `--rounds`, a run stops after 8 rounds and reports "NOT verified clean". Asking for more than 8 rounds raises the cap to match.
- **Any directory, not only skills.** An absolute path audits any directory of docs and scripts; a bare name is looked up as `~/.claude/skills/<name>/`.
- **Narrowed review, then a full sweep.** From round 3 the review reads only files the previous fixes touched. A clean result there is never counted as done: a full sweep always follows, and only a clean full sweep is convergence.
- **Considered fixes.** Every finding ends as FIX (change the target), STRENGTHEN (add the missing reason for an intentional design) or ORCHESTRATOR-PAUSE (the coordinating agent decides from the target's own docs). A fix may not add new behaviour or interface elements (flags, modes, files, ledger fields); those become pauses.
- **Questions only when needed.** It asks you one question (a USER-PAUSE) only when the right fix cannot be worked out from the target's files.
- **Post-fix safety gate.** After each batch of fixes, checks confirm no path, flag or identifier broke, no new behaviour slipped in and no doc block was rewritten without being re-read.
- **Audit ledger.** Each round's findings, root causes, fixes and pauses go to a ledger file (path under Structure).
- **Resume.** Invoking it again on the same target after an interruption, a compaction, a pause or an error finishes the open round from the saved run options. A new invocation after a clean finish or a gate stop starts a fresh run.
- **Merge-check.** When a run ends, it looks for another copy of the target (the installed `~/.claude/skills/<name>/` or a same-named folder in the same git checkout) and lists files that differ, so fixes made in an audited copy are not lost.
- **Honest outcomes.** It reports converged, stopped by the round gate, waiting on you, or stopped by a hard error. Anything but convergence is labelled "NOT verified clean". On convergence it suggests `/skill-publisher <target>`.
- **Proactive start.** It can start on its own after a skill is created or significantly edited.

## Structure

- `SKILL.md`: the workflow spine (round loop, stop rules, run options, stages, final report).
- `README.md`, `HISTORY.md`, `LICENSE`: intent and usage, version history and provenance, licence.
- `references/`: detail that SKILL.md points to.
  - `dispatch.md`: how reviewers and fixers are launched and checked, and the post-fix gate.
  - `recovery.md`: resuming an interrupted run, saved run options, hard errors, cleanup of temporary files.
  - `how-to-fix.md`: the FIX / STRENGTHEN / ORCHESTRATOR-PAUSE rules, the frozen-interface rule, closure checks.
  - `script-contract.md`: what each non-zero script exit means and a script index.
  - `glossary.md`: terms.
- `scripts/`: Python helpers, no network needed.
  - Stage entry points: `prepass_run.py`, `code_review_run.py`, `code_review_collect.py`, `cluster_enforce.py`.
  - Ledger: `append_ledger.py`, `ledger_cascade.py`, `ledger_common.py`, `render_ledger.py`.
  - Fix preparation and checking: `assemble_fix_prompt.py`, `check_decisions.py`, `fix_blast.py`, `check_fix_radius.py`, `post_fix_gate.py`.
  - Scoping and lint: `inscope.py`, `coverage_check.py`, `doc_lint.py`.
  - Housekeeping: `stage_cold_prompts.py`, `cleanup_tmp_prompts.py`.
- `cascade_sweep.py` (runs every detector over the target) and `cluster_prepass.py` (groups prepass findings by root cause) sit at the skill root.
- `detectors/`: one small check per mechanical defect type, plus a shared `_common.py`.
- `prompts/`: the reviewer lens instructions (design, executor, fidelity, integrity, logic).
- `templates/`: the cold code-review prompt and the fixer prompt the scripts fill in.
- `tests/`: automated tests for code review, fixer batching, the ledger flow, the post-fix gate and the round gate.
- `evals/`: `evals.json` (behaviour checks) and `triggering.json` (when the skill should and should not start).
- Outputs: the audit ledger at `${XDG_DATA_HOME:-$HOME/.local/share}/skill-tracer-audit-ledger/<target-name>.md` (one per target; a ledger recording another target is refused), staged prompt files under `/tmp/skill-tracer-prompts/` (removed at the end of a run), and a one-line progress note per round in the day's `~/.claude/session-logs/` file. Fixes are made in the target directory itself.

## Known limits

v3.6 did not converge in its own self-run (it stalled after round 4 and a final sweep still found 2 flags). Its two cold reviewers vary between runs, so a clean round is weaker evidence than it looks, and the block-reread gate trusts the fixer's `Blocks:` line rather than verifying the re-read. Treat a converged run as strong but not conclusive. A later 8-round re-trace by skill-creator-ccvw (raw flags 17, 10, 13, 3, 2, 2, 5, 4, all fixed) also hit the round cap without a clean full sweep. Details: the 3.6.0 entry in HISTORY.md.

Also not verified:
- The 11 fixes from the final full review were not reviewed again.
- One eval-2 check (a clean changed-files review followed by `--scope full`) was never exercised, and eval 0 stopped in round 2 with that round's 71 findings unfixed (4 caused by round 1's own fixes).
- Eval 5 cannot tell the old and new versions apart.
- Multi-skill folders: the fixer reads its intent only from `<target>/README.md` or `<target>/SKILL.md` and cannot find each skill's own design docs, and `doc_lint.py` reads only the top-level `SKILL.md`. Trace each skill folder as its own target.

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
