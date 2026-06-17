---
version: "2.2.0"
category: B
parent-version: "2.1.0"
published-to:
  repo: "https://github.com/Vaikri-costume/skills"
  path: "skills/skill-tracer"
author:
  primary: "Vaikri-costume"
inspirations:
  - skill: "deep-research"
    by: "Anthropic"
    pattern: "adversarial-verify — cold-parallel independent agents commit to claims before reconciliation. skill-tracer's cold-parallel F/B/E dispatch is the same shape; named retrospectively."
  - skill: "pr-review-toolkit"
    by: "Anthropic"
    pattern: "adversarial-verify sibling — independent agents committing before reconciliation, applied to PR review. Cited in invariant 1's cold-trace rationale."
  - skill: "ralph-loop"
    by: "community"
    pattern: "inline-with-cold-child-dispatch loop shape. Step 7's default inline-continuation is the convergence-bounded specialization."
---

# History — skill-tracer

## Changelog

### 2.2.0 — 2026-06-17 (exhaustive self-trace to convergence + `--audit-fixes` mode)
- **Added: `--audit-fixes` diagnostic mode.** Checks whether the fixes recorded in the ledger since the last convergence actually landed (vs light-touch / band-aid / regressed) by dispatching one cold audit agent over the rounds-since-convergence. Read-only — reports a per-finding classification, applies no fixes, writes no rows. Spec in `references/audit-fixes.md`; integrated into Step 1(a) recovery, Step 7 mode-routing, and the Step 9 exit set.
- **Exhaustive self-trace (rounds 31–47).** Forward + backward (the correctness directions) converged. Fixed script bugs across the ledger toolchain: `recover_dispatch` most-recent-wins on discard-retry + id-less-tuid skip + full-non-alphanumeric `encoded_cwd`; `_tally` token-boundary; `render_ledger` phantom-round-0 guard, `type(e).__name__` in the broad except, and 6-col back-compat row acceptance; `ledger_state` marker parse; `stage_cold_prompts` single-pass substitution; `append_ledger` `re.escape` in close-round + `utf-8` everywhere + `--cluster ^C\d+$` guard + close-round single-read. Introduced **`scripts/ledger_common.py`** as the single source of truth for the row / marker / PRE-FLIGHT / vocab parsers — `append_ledger`, `ledger_state`, `check_drift`, `check_results` import it; `render_ledger` stays standalone (config-driven, serves both this skill and skill-publisher).
- **Doc consolidations.** Resolved doc-vs-code contradictions and collapsed duplicated rules to single-home-plus-pointer — the malformed-marker tree, resume-wakeup, `verify-auditability --expect`, `check_drift` exit codes, the stop-after-round computation, the forward/backward/executor escape-hatch scaffold (→ `prompt-template.md`), and the TRACE-vs-all Condition-A invariant (→ Step 8 as the single authoritative home).
- **New mechanisms.** USER-PAUSE cross-round resolution + enumeration; Step-7 mode-routing completeness (`<stop-after-round>` `>` and `null` cases, the TRACE-clusters-plus-unresolved-USER-PAUSE precedence).
- **Final code-review fixes.** `check_results` ABORTED false-positive (a quoted `ABORTED` line in an ISSUE block no longer aborts the report — relevant when tracing skill-tracer on itself); the `--expect` comma-spacing doc claim corrected; the error-table `--cluster`-rejection row added.
- **Known / ratified.** SKILL.md grew to ~11k words; the cold-executor design keeps point-of-use detail inline (moving it to references re-triggers the executor cascade), so the length is ratified and flagged for a future deliberate structural pass.

### 2.1.0 — 2026-06-16 (round-1 code-review pass)
- **Added: round-1 code-review pass (SKILL.md Step 2.5).** On round 1 of a brand-new trace — and on the first round of a re-trace of a skill updated since it last converged — skill-tracer now runs one full-depth local pass of the sibling `code-review` skill (`/code-review max`, no `--fix`, no issue cap) as the **first phase of round 1**, before the cold agents dispatch. Runs in full-convergence mode only (diagnostic modes skip it). The post-update-convergence trigger gates on an mtime check (`find … -newermt "<prior convergence Runtime>"`) so an unchanged converged skill isn't re-reviewed for nothing.
- **Whole-skill scope, not a diff.** The pass reviews every in-scope file's full contents (`[SKILL_PATH]` + `[FILE_LIST]`), not a working-tree diff — skills aren't always under git (skill-tracer's own tree isn't) and a new skill has no diff. If `/code-review` can't be scoped to whole files, skill-tracer falls back to a single general-purpose Agent running code-review's `max` methodology over the file set.
- **Sub-phase of round 1, not a separate round.** The code-review phase and the cold trace share round 1: `REVIEW`-phase `CR*` rows and `TRACE`-phase `F/B/E` rows land under the same Round with one continuous cluster sequence; the round closes once (Step 7) and `verify-auditability --expect` is the union of both flag sets. **Condition A is tested over the `TRACE` clusters only** — the cold trace reads the post-code-review-fix files, so a clean cold trace in round 1 is a genuine clean cold round; `REVIEW` clusters never block convergence.
- **Findings go through the existing considered-fix gate**, not auto-applied: `--fix` is deliberately *not* passed, so each finding is clustered (Step 5) and addressed under Step 6's bias-toward-FIX + intent-preservation rules, preserving invariant 2. Recorded as **`REVIEW`-phase rows** with a new **`CR*`** flag prefix (distinct from the `C*` Cluster column).
- **Added: post-convergence suggestion** — Step 9 now suggests a final `/code-review max <skill>` pass over the converged artifact (the round-1 pass reviewed the pre-trace skill; convergence may have rewritten it across many rounds), then `/skill-publisher`.
- **`code-review` linked as a sibling** in SKILL.md "See also" + README, and `Skill` added to `allowed-tools` (skill-tracer invokes `/code-review` via the Skill tool).
- **Recovery: rule 2 handles the `REVIEW` phase** — an interrupted `addressing round-N` with no `Forward/Backward/Executor trace` dispatch in the JSONL is recovered by re-running the code-review phase then proceeding into the cold trace (same round); if a trace dispatch exists, the `REVIEW` rows are already done and only the trace addressing is recovered. Rules 4/5 note Step 2.5 is the first phase of round 1, not a separate round.

### 2.0.2 — 2026-06-07 (shipped — claude-users portability)
- **Now ships at `claude-users` tier** (was `personal`): guarded the glossary-precedence reads of the user's `CLAUDE.md`/`memory` to portable `${XDG_*:-$HOME/.claude}` form + explicitly optional, so the skill no longer hard-depends on personal config.
- **Fixed a portability-lint inconsistency** (canonical skill-creator-ccvw lint + vendored skill-publisher copy): a skill's own per-user ledger (e.g. `~/.claude/skill-tracer-audit-ledger/`) was flagged as a user-data-path while skill-publisher's own ledger was not — removed the skill-own-ledger entries from `USER_DATA_PATHS` so only genuine user-personal config is flagged.
- **Version field reconciled to 2.0.2** (it had lagged at 2.0.0 while the changelog already carried 2.0.1).
- Shipped via skill-publisher (full 10-step ship; CCVW audit + claude-users tier gate passed).

### 2.0.1 — 2026-05-30 (self-consistency + batch-edits fix-discipline)
- **Fix: description trimmed 1197 → 941 chars** so the skill passes the ≤1024 frontmatter-validity gate that skill-publisher now enforces at ship time (it previously would have been blocked by its own ecosystem's gate). Trimmed the glossary-precedence + README-Intent sentences — both fully documented in the body (Step 1c, Step 3), so no information lost.
- **Consistency: `compatibility` flattened to prose** `Claude Code 2.0 or newer`, matching skill-creator-ccvw + skill-publisher (was a nested `claude-code`/`agentskills-io` object). Cross-skill standardization; the tracer is personal-tier so the dropped structured agentskills.io declaration was aspirational.
- **Added: "Batch edits to the same document" fix-discipline** in `references/address-decision.md` — when several clusters in a round resolve in the same file, apply their fixes as one coordinated pass (not one-at-a-time), to remove the stale-read window that causes wrong-anchor / sibling-overwrite / double-touch errors. Composes with fix conservatism + Step-7 anchor verification.

### 2.0.0 — 2026-05-30 (three-skill ecosystem refactor — slimmed to correctness-only)
- **Major: slimmed to F/B/E correctness-only.** skill-tracer now finds bugs + inconsistencies via three cold-parallel direction agents (forward, backward, executor). That's its whole job.
- **Removed (moved to skill-publisher)**: the CCVW Word/Spirit audit (was Step 9), the mandatory simplify pass + verification re-trace (was Step 11), the portability sub-audit, the security cadenced direction, the `audit-references::` mtime tracking. These are ship-phase concerns — they live in skill-publisher now.
- **Removed (moved to skill-creator-ccvw)**: the efficiency + accessibility cadenced directions. Efficiency + accessibility (general readability) became iterate-quality checks in the builder; accessibility cats 15-16 (personalization + plan-code leakage) became portability-lint checks. These are quality/build concerns, not correctness bugs.
- **Convergence is now Condition A only** — F/B/E come back clean. No more Condition B (CCVW-compatibility); that gate moved to skill-publisher.
- **Removed flag prefixes**: EFF*, A11Y*, SEC*, G*, G-PORT*, SIM-*. Only F*/B*/E* remain.
- **Removed Phase column values**: PORT-AUDIT, SIMPLIFY. Only TRACE remains.
- **Added**: soft README.md `## Intent` read at Step 1 (orchestrator-side only — the cold agents never see it, preserving the cold-trace invariant). The orchestrator uses documented Intent to make considered-fix decisions: a fix that would violate stated Intent is a USER-PAUSE.
- **Structural**: frontmatter history moved to this HISTORY.md; README.md added.

### 1.x (pre-refactor) — 2026-05-27 → 2026-05-30
- Original cold-parallel three-agent trace. Grew Step 9 (CCVW audit + portability sub-audit), Step 11 (simplify), cadenced directions (efficiency/accessibility/security) — all of which the 2.0.0 refactor redistributed to creator + publisher.
- 11 rounds of self-trace hardened the recovery protocol, dispatch protocol, ledger format, and address-decision rules. Those are retained.

## Lineage notes

skill-tracer is Category B — original independent design whose cold-parallel dispatch is recognizable as deep-research's / pr-review-toolkit's adversarial-verify pattern, and whose inline loop is ralph-loop's shape. Named retrospectively; the patterns pre-existed as independent design and the inspirations credit the structural correspondence.

The 2.0.0 refactor was a deliberate narrowing: skill-tracer had accreted build + ship concerns that diluted its correctness-finding focus. The build → trace → ship split moved those out, leaving skill-tracer to do one thing well — find bugs and inconsistencies in any skill via cold-parallel reading.
