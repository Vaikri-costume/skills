---
version: "2.0.2"
category: B
parent-version: "2.0.1"
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
