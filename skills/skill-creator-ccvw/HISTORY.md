---
version: "1.0.1"
category: A
parent-version: "1.0.0"
author:
  primary: "Vaikri-costume"
  history:
    - role: "original"
      name: "Anthropic"
      skill: "skill-creator"
      version: "1.0.0"
      license: "MIT"
      source: "https://github.com/anthropics/skills"
    - role: "fork-adapter"
      name: "Vaikri-costume"
      date: "2026-05-27"
      changes-summary: "CCVW fork — centralized eval outputs, three-tier portability, mandatory glossary + structured frontmatter, marketplace-discover pre-check, attribution framework, build → trace → ship ecosystem split."
inspirations: []
---

# History — skill-creator-ccvw

## Changelog

### 1.0.1 — 2026-06-07 (shipped — claude-users)
- **Now ships at `claude-users` tier** (was personal): no user-personal-config reads; uses only its own `~/.claude/skill-creator-evals-ledger/` (a portable per-skill namespace).
- **Description exclusion clause added** ("Do NOT use to find bugs — use skill-tracer; or to polish/package/PR — use skill-publisher") to prevent over-triggering against near-neighbor siblings.
- **`parent-version` reconciled** from the non-conforming `pre-versioned` token to `1.0.0` (the superseded version); the fork lineage remains in `author.history`.
- **Fixed a portability-lint inconsistency** in its own canonical `portability_lint.py`: a skill's own per-user ledger is no longer flagged as a user-data-path (matching skill-publisher); only genuine user-personal config (CLAUDE.md/memory) is flagged.
- Shipped via skill-publisher (full 10-step ship; CCVW self-audit + claude-users tier gate passed).

### 1.0.0 — 2026-05-27 (CCVW fork of skill-creator)
- Forked from Anthropic's `skill-creator` (MIT). LICENSE preserved at skill root.
- **Centralized eval outputs** to `~/.claude/skill-creator-evals-ledger/<skill>/` instead of beside the target skill (keeps the skill tree clean; no eval-workspace artifacts the next trace flags as dead text).
- **Three-tier portability system** (`personal` / `claude-users` / `model-agnostic`) with `portability_lint.py` enforcement at scaffold + tier transitions.
- **Mandatory CCVW structure**: frontmatter fields (`license`, `compatibility`, `metadata`, `allowed-tools`); directories (`scripts/`, `references/`, `assets/`); per-skill `references/glossary.md`.
- **Marketplace-discover pre-build check** — checks the live catalog before building so the user isn't reinventing a mature community skill.
- **Attribution framework** — four-category system (fork / derivative / inspiration / independent) recorded in HISTORY.md, enforced by `attribution_lint.py`.
- **Build-planning** via `productivity:task-management` for multi-iteration builds.
- **Session-report with Claude-authored recommendations** sidebar in the eval viewer.

### 1.0.0 (later, 2026-05-30) — three-skill ecosystem refactor
- Audience tiers renamed: `shipped` → `claude-users` (Claude Code + Cowork), `cross-runtime` → `model-agnostic` (Gemini CLI / Cursor / OpenCode / agentskills.io).
- **Structural change**: skill history moved OUT of SKILL.md frontmatter into this `HISTORY.md`. README.md added for human intent. SKILL.md frontmatter shrunk to runtime-contract fields only.
- **Absorbed iterate-quality checks** from skill-tracer (efficiency + accessibility cats 1-14 → `references/iterate-quality-checks.md`; personalization cats 15-16 → `references/portability-spec.md` + `portability_lint.py`). These are quality concerns the builder owns during iteration, not correctness bugs the tracer finds.
- **Three-skill split**: build (this skill) → trace (skill-tracer, correctness-only) → ship (skill-publisher, polish + tier-checks + CCVW audit + GitHub PR). Each phase suggests the next; no auto-invocation.
- **Packager divergence (deliberate, not drift)**: this skill keeps its own minimal `scripts/package_skill.py` — it zips a freshly-built skill of *any* tier into an installable `.skill` for immediate local install (the "Package and Present" step, only when `present_files` is available). It is intentionally NOT skill-publisher's packager and is deliberately not routed to it: (1) fresh builds default to `personal` tier, which the publisher's tier-aware packager refuses by design, so routing would break the common build-time case; (2) the build skill stays independent of the ship skill (chain by suggestion, not hard dependency). Same filename across the two skills, deliberately different behavior; they never share a namespace (each lives in its own skill's `scripts/`). Both packagers now exclude `*.orig` / `*.bak*` so editor/patch backups never ship. (Resolves the "same-named script, different behavior" standardization finding by documenting the divergence rather than forcing a lossy merge.)

## Lineage notes

skill-creator-ccvw is a Category A fork of Anthropic's upstream `skill-creator`. The fork's distinctive contribution is the CCVW conventions layer (centralized evals, portability tiers, mandatory structure, attribution) plus the build → trace → ship ecosystem split. The upstream iterate-loop (test cases, eval-viewer, description optimization) is retained largely intact — that's the structural fingerprint that makes this Category A rather than B.

The "CCVW" label is intentionally unexpanded for now; it names this fork's convention ecosystem and is reserved for a public-facing expansion later.
