# Glossary — skill-publisher

See also: `~/.claude/skills/skill-creator-ccvw/references/ccvw-glossary.md` for shared CCVW terms (cluster, FIX, STRENGTHEN, USER-PAUSE, in-flight marker, ledger, tier, Word/Spirit, etc.). This file lists only terms specific to skill-publisher.

## Skill-specific terms

| Term | Definition |
|---|---|
| **ship phase** | The third phase of the build → trace → ship ecosystem. skill-publisher's job: take a built + traced skill and make it release-ready (polish, audit, tier-checks, version, package, PR). |
| **polish pass** | Step 2 — the mandatory `simplify` invocation on SKILL.md + README.md. Removes phrasing entropy accumulated during build + trace. Moved here from skill-tracer's old Step 11. Mechanics in `references/polish-pass.md`. |
| **CCVW Word/Spirit audit** | Step 3 — a cold Agent dispatch that checks the target against skill-creator-ccvw's documented requirements (Word = explicit rules; Spirit = how skills should be written). Moved here from skill-tracer's old Step 9. Prompt in `references/audit-prompt.md`. |
| **tier-transition check** | Step 4 — the per-audience-tier validation gate. `personal` skips; `claude-users` runs portability + Cowork + attribution + security + MCP-dependency declaration (if applicable); `model-agnostic` adds cross-runtime portability + agentskills.io verification. This is the exhaustive check set per tier — see `references/tier-transition-checks.md` for the authoritative spec. |
| **Cowork-compatibility check** | Part of the claude-users tier check — verifies the skill works in Cowork's runtime (viewer auto-launch, headless `--static` mode, feedback-via-download, TodoList reminders). Cowork is one of the two Claude runtimes (with Claude Code) that `claude-users` tier targets. Spec in `references/cowork-compatibility.md`. |
| **degraded mode** | The ship path when the target has no HISTORY.md. Prompts the user once for attribution category, generates a minimal HISTORY.md, then ships locally only — no version bump (no prior version), no PR (no upstream repo). |
| **Phase column (POLISH / AUDIT / TIER / PACKAGE / PR)** | The publisher ledger's Phase values, one per workflow stage that produces clusters. Distinct from skill-tracer's TRACE/SIMPLIFY/PORT-AUDIT — different skill, different phases. |
| **ship ledger** | The per-skill accumulating record at `~/.claude/skill-publisher-ledger/<skill>.md`. One file per target skill across all ship runs. Format in `references/ledger-format.md`. |
| **upstream origin** | A GitHub/marketplace source URL recorded in the target's HISTORY.md (`author.history[].source` or `inspirations[].source`). Its presence triggers Step 9's PR; its absence skips PR generation. |
| **version bump** | Step 7 — incrementing the target's HISTORY.md `version` (semver: patch/minor/major) and appending a changelog entry. Skipped in degraded mode. |
