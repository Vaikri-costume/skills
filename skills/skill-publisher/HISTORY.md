---
version: "1.1.0"
category: B
parent-version: "1.0.1"
author:
  primary: "Vaikri-costume"
inspirations:
  - skill: "skill-tracer"
    by: "Vaikri-costume"
    pattern: "Recovery protocol + ledger machinery — in-flight markers, atomic-write protocol, recovery rules, and the per-skill accumulating ledger with a Phase column. Adapted from tracer's correctness-trace ledger to publisher's ship-phase ledger (POLISH/AUDIT/TIER/PACKAGE/PR)."
  - skill: "simplify"
    by: "Anthropic"
    pattern: "4-agent simplify pass (Reuse / Simplification / Efficiency / Altitude) with targeted-reversal-at-2 — invoked at Step 2 polish. The mandatory simplify that used to live in skill-tracer's Step 11 moved here."
  - skill: "skill-creator-ccvw"
    by: "Vaikri-costume"
    pattern: "CCVW Word/Spirit audit prompt + the portability/attribution lints + the three-file structure spec — publisher reads the structure skill-creator-ccvw scaffolds and reuses its lint scripts."
---

# History — skill-publisher

## Changelog

### 1.1.0 — 2026-06-17 (shipped)
- **Auto-tag on ship**: `scripts/github_pr.py` now creates + pushes an annotated `<skill>-v<version>` tag on the ship commit after a successful `gh pr create`, so the next ship has a `<last-ship-tag>` to diff from (`references/changelog-format.md`'s `git log <last-ship-tag>..HEAD`). Best-effort (a tag failure surfaces as a `tag_warning` field, never a ship-blocker — the PR already landed) and idempotent (skips an existing tag, safe for the exit-5 recovery re-run).
- Documented the per-skill `<skill>-v<version>` tag convention (the form a monorepo of several skills needs — a bare `v<version>` collides across skills sharing a version) in `references/changelog-format.md`, added the tag step + squash/rebase caveat to `references/github-pr-workflow.md`, and added a Step-9 ship-tag row to `references/ship-checklist.md`.

### 1.0.1 — 2026-06-07 (shipped)
- Correctness + clarity pass driven by `skill-tracer`: relocated deep exit-code/mechanism detail from SKILL.md into `references/` (PR/package/render exit codes, portability output interpretation, degraded-scaffold + install-form derivation) with accurate one-line pointers.
- Fixed real latent bugs: `quick_validate` exit-1 stdout disambiguation (`Skill is valid!` is exit-0 only), `portability_lint` exit-1-is-findings (not a hard gate-fail), attribution/`spdx_check` `--require` scoping, audit-skip ledger row `--root-cause`, ledger-path migration on name mismatch, bump-level default, `parent-version` pre-versioned coverage, plus ~15 further point-of-use corrections.
- Re-synced vendored `append_ledger.py` to canonical; suppressed `security_scan` self-flag false positives.

### 1.0.0 — 2026-05-30 (initial build)
- Built as the **ship** phase of the build → trace → ship skill ecosystem (build = skill-creator-ccvw, trace = skill-tracer, ship = this skill).
- **Absorbed from skill-tracer**: the CCVW Word/Spirit audit (`references/audit-prompt.md`), the mandatory simplify pass (`references/polish-pass.md`, was tracer's `simplify-cycle.md`), and the security checks (`references/security-checks.md`, was tracer's `security.md`). These are ship-time concerns, not correctness-trace concerns — moving them here let skill-tracer slim to bug-finding only.
- **10-step ship workflow**: resolve + read state → polish → CCVW audit → tier-transition checks → address findings → generate README install/sibling sections → version bump + changelog → package → GitHub PR → present.
- **Per-tier checks**: `personal` skips; `claude-users` runs portability + Cowork-compatibility + attribution + security; `model-agnostic` adds cross-runtime portability + agentskills.io verification.
- **Degraded mode**: ships skills with no HISTORY.md (prompts for attribution, local package only, no PR).
- Reuses skill-creator-ccvw's `portability_lint.py` + `attribution_lint.py` (doesn't reimplement).

## Lineage notes

skill-publisher is a Category B derivative — its workflow machinery (recovery protocol, ledger, atomic-write, cold-Agent dispatch for the audit) is recognizably skill-tracer's pattern, reimplemented for the ship phase. The simplify-pass mechanics are the `simplify` skill's, invoked rather than reimplemented. The structural spec + lint scripts are skill-creator-ccvw's, reused.

The three-skill split (build → trace → ship) came from observing that skill-tracer had accreted ship-phase concerns (portability sub-audit, simplify pass, CCVW audit) that diluted its correctness-finding focus. Moving those into a dedicated ship skill let each tool do one thing: creator builds, tracer finds bugs, publisher ships.
