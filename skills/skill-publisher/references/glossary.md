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
| **degraded mode** | The ship path when the target has no HISTORY.md. Prompts the user once for attribution category (A/B/C/D) or 'skip' — two sub-paths: **(a) attribution declared** → scaffolds a minimal HISTORY.md and runs Steps 2–5 + a first changelog entry at the scaffold's initial `1.0.0` (no *increment*, since there is no prior version; a PR can still open if an upstream is recorded); **(b) 'skip'** → ships as-is without provenance, bypassing Steps 2–5 entirely, no version bump, no PR (offers a hosting branch instead). Both still package + verify. Full spec: `changelog-format.md` "Degraded-mode HISTORY.md scaffold". |
| **Phase column (POLISH / AUDIT / TIER / PACKAGE / PR)** | The publisher ledger's Phase values, one per workflow stage that produces clusters. Distinct from skill-tracer's `TRACE`/`REVIEW` — different skill, different phases. |
| **ship ledger** | The per-skill accumulating record at `~/.claude/skill-publisher-ledger/<skill>.md`. One file per target skill across all ship runs. Format in `references/ledger-format.md`. |
| **upstream origin** | A GitHub/marketplace source URL recorded in the target's HISTORY.md (`author.history[].source` or `inspirations[].source`). Its presence triggers Step 9's PR; its absence skips PR generation. |
| **version bump** | Step 7 — incrementing the target's HISTORY.md `version` (semver: patch/minor/major) and appending a changelog entry. Skipped in degraded mode. |
| **mode phrase** | The invocation flag or natural-language phrase that selects `readiness`, `docs-only`, `rollback`, `status` or `full` mode (SKILL.md Step 1); decided from the invocation text alone. |
| **`docs-only`** | The mode for a ship whose changed paths are only README.md and HISTORY.md; skips the cold audit and behavioural tier lints (`references/lifecycle.md`). |
| **`needs_choice`** | `marketplace.state` value in `github_pr.py`'s dry-run JSON: the catalog exists, the skill is not listed, and the user must pick a plugin. |
| **`needs_row`** | `readme.state` value in `github_pr.py`'s dry-run JSON: the repo-root README does not link the skill and a section must be chosen. |
| **`pr_url`** | Field in `github_pr.py`'s success JSON holding the opened PR's URL; absent on a dry run. |
| **`clone_dir`** | Field in `github_pr.py --diff-only`'s JSON naming the temporary upstream clone; removed at Step 10. |
| **`no_published_state`** | JSON flag from `github_pr.py --diff-only` / `diff_published.py` meaning the skill is not yet published at the repo path, so the changelog is sourced from ledger rows alone. |
| **`close-round`** | `append_ledger.py` subcommand that writes the generated `Round N total` summary comment after a run's rows. |
| **`pre-versioned`** | Literal value of SKILL.md `metadata.parent-version` meaning the skill has no prior version to supersede. |
| **`in-flight::`** | Line-start ledger-header property that marks a ship run mid-flight, in the form `in-flight:: <Runtime> <action> run-N`; a mention elsewhere in a line is not a marker. |
| **`required_failures`** | Array in `verify_ship.py`'s JSON naming each required check that failed. |
| **`raw_flags`** | Count of raw findings in a generated `Round N total` ledger comment; omitted from the canonical `Run N total` comment. |
| **`would_fail_at_tiers`** | `portability_lint.py` JSON array of tier names a finding would block; the target's own tier appearing in it means the finding blocks. |
| **`blocks_tier`** | Field of a `portability_lint.py` violation naming the tier it blocks; a `(warning)` suffix marks a soft violation. |
| **`allowed-tools`** | SKILL.md frontmatter field listing the tools a skill may call; `mcp__*` entries in it are a Claude extension flagged at `model-agnostic`. |
| **`author-identity-mismatch`** | Blocking `attribution_lint.py` violation: HISTORY.md `author.primary` differs from the `gh`-authenticated GitHub login. |
| **`YYYY-MM-DDTHH:MM`** | UTC timestamp form of `<Runtime>`, captured once at Step 1 with `date -u +%Y-%m-%dT%H:%M`. |
| **third signal** | The skill-tracer audit-ledger rows since the last ship, fed to the changelog agent by `tracer_changelog_rows.py` (Step 7). |
