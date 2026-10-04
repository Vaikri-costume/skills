# skill-publisher

## What this skill does

Takes a finished, traced skill, makes it release-ready, and distributes it: it polishes the prose (a mandatory simplify pass on SKILL.md + README.md), audits CCVW compliance, runs the tier-transition checks that match the skill's intended audience (portability, attribution, security, and Cowork-compatibility), writes the user-facing README sections that teach others how to install and use the skill, bumps the version and appends a changelog entry, packages the skill for distribution, and — when the skill has a GitHub/marketplace origin — opens a pull request.

It's the **ship** phase of a three-skill ecosystem: **build** (skill-creator-ccvw) → **trace** (skill-tracer) → **ship** (this skill).

## Intent

This skill prioritizes **release-readiness and teachability** over speed. It runs the full quality gate (polish + CCVW audit + tier checks + security) every ship, even for a small update, because a skill shared with others carries a higher correctness-and-clarity bar than one used privately — and the cost of shipping a broken or confusing skill to friends/family/coworkers is higher than the cost of the checks.

It deliberately **separates polish from bug-finding**: skill-tracer owns correctness (does the skill have bugs?), skill-publisher owns release quality (is it clean, compliant, installable, teachable?). The simplify pass and the CCVW Word/Spirit audit live here, not in the tracer, because they're ship-time concerns — applying them mid-build or mid-trace would add prose the tracer then has to re-examine.

It is **resilient to missing provenance**: a skill without HISTORY.md still ships (degraded mode — local package, no version bump, no PR), because the user shouldn't be blocked from sharing a hand-built skill just because it lacks a lineage file. But it prompts to backfill, because provenance makes the next ship smoother.

## When to use / When NOT to use

**Use when:**
- A skill has been built + traced and you want to share/distribute it
- You want to polish a skill's prose for release-quality clarity
- You want to PR a skill back to a marketplace/GitHub repo it came from
- You want to bump a skill's version + changelog and package it

**Don't use when:**
- The skill still has bugs → run `/skill-tracer` first
- You're still building/iterating → use `/skill-creator-ccvw`
- The skill is `personal` tier and you just want to use it locally (publisher's checks are for shared skills; personal skills skip most of them)

## How to invoke

- Slash command: `/skill-publisher <skill-name>` or natural language
- Modes (slash or natural language): `--readiness` ("can this ship"), `--docs-only` (README/HISTORY-only changes), `--rollback` ("undo the ship of X"), `--status [--repoint-tag]` ("did X merge"), `--triggering-eval --eval-set <queries.json>` (opt-in measured trigger accuracy during a full ship). The argument may be a bare skill name or an absolute path; relative paths are rejected. After skill-tracer converges, the publisher also suggests the ship phase on its own.
- Natural language: "ship skill X", "publish X", "release X", "make a PR for X", "package X for the marketplace"

Example:
```
"/skill-publisher my-pdf-summarizer"
→ polish (simplify SKILL.md + README) → CCVW audit → tier checks (claude-users: portability + Cowork + attribution + security)
→ address findings → fill README install + sibling sections → bump version + changelog → package .skill → (PR if upstream) → present
```

## Features & modes

**Invocation modes**

- **Full ship (default).** Runs the whole release pipeline: polish, cold audit, tier checks, fixes, README sections, version bump and changelog, packaging, and a PR if the skill has an upstream. Trigger it with `/skill-publisher <skill-name-or-absolute-path>`, or say "ship X", "publish X", "release X", "make a PR for X" or "package X for the marketplace".
- **Readiness check (`--readiness`).** Read-only "can this ship?" preview. It runs the cheap automated gates and prints a green, yellow or red verdict. It skips the audit and the other expensive steps, and writes no ledger rows or files. Trigger it with `--readiness`, or ask "can this ship" or "readiness check".
- **Docs-only ship (`--docs-only`).** A shortened ship for changes that touch only README.md and HISTORY.md. It polishes, validates, bumps the patch version, packages and opens the PR. It skips the cold audit and the behavioral tier checks. If anything else changed, it refuses and points you to a full ship.
- **Status (`--status`).** Read-only follow-up after a PR: whether it merged, whether the ship tag still points at the right place, and whether the marketplace catalog is stale. Add `--repoint-tag` only if you want a dangling tag fixed. Or ask "did X merge" / "ship status of X".
- **Rollback (`--rollback`).** Undoes the most recent ship. It restores the pre-ship copies of SKILL.md, README.md and HISTORY.md, deletes the packaged archive, and closes the open PR. It always asks you to confirm first, and refuses if the PR is already merged (offering a revert PR instead). Or say "undo the ship of X" / "roll back X".
- **Measured triggering eval (opt-in add-on).** Tests how often the skill's description actually triggers it, using a query set you provide as `{query, should_trigger}` entries. A result below the threshold becomes an audit finding to fix. Off by default to keep shipping fast; an add-on to a full ship, not a separate mode. Trigger it with `--triggering-eval --eval-set <queries.json>`. Without a query set only the quick description-confidence check runs.
- **Proactive suggestion.** After skill-tracer finishes on a skill you plan to share, the publisher suggests moving on to the ship phase.

**Notable features**

- **Polish pass.** A mandatory simplify pass on SKILL.md and README.md that preserves the skill's stated intent and keeps explanations that justify a rule.
- **Cold CCVW audit.** A fresh subagent with no prior context checks the skill against the CCVW conventions in letter and spirit. It must run from the top-level session, not from inside another subagent.
- **Tier-aware checks.** `personal` skips the checks, `claude-users` adds the shared-skill checks, `model-agnostic` adds cross-runtime checks: frontmatter validity, portability, links, Cowork compatibility, attribution and license, security scan, and MCP dependency declarations.
- **Cold README and changelog agents.** One fresh agent drafts the `## Features & modes` and `## Structure` sections from the final SKILL.md (regenerated every ship); another writes the changelog entry by comparing the local skill with its published version, the ship ledger and any skill-tracer fixes.
- **Version bump and changelog.** Applies the right SemVer level and adds a Keep-a-Changelog entry to HISTORY.md.
- **Packaging.** Builds a `.skill` archive (or a zip for Claude.ai) with a SHA-256 digest, in the form that fits the audience tier.
- **PR and marketplace registration.** The first run is always a dry-run preview that you confirm or cancel. The same commit registers the skill in the upstream `.claude-plugin/marketplace.json` (you choose which plugin it joins, or a new one, or none) so `claude plugins install` can actually offer it; a skill already listed is left alone. The same commit adds a row for the skill to the repo-root README's skill listing, under the section you choose, so the front page doesn't omit it. A license check runs before any public push, and a skill with no upstream can be offered a hosting branch instead.
- **Degraded mode.** A skill without HISTORY.md still ships locally: you are asked for an attribution category, or can skip, in which case there is no version bump and no PR.
- **Recovery after interruption.** The ship ledger records in-flight markers; if a run is cut short (for example by context compaction), the next run detects the marker and resumes at the right step.
- **Post-ship verification.** Confirms the version, changelog, archive digest and PR before recording the ship as landed, and renders a one-page HTML view of the ledger.

## Structure

- **`SKILL.md`** — the runtime workflow (10 steps plus mode dispatch); the source of truth.
- **`README.md`** / **`HISTORY.md`** / **`LICENSE`** — this file, provenance and changelog, MIT license.
- **`references/`** — detailed specs, loaded at the step that needs them:
  - gates and checks: `readiness-gates.md`, `tier-transition-checks.md`, `cowork-compatibility.md`, `security-checks.md`, `ship-checklist.md` (how findings get addressed);
  - agent prompts: `audit-prompt.md` (cold audit), `readme-agent-prompt.md` (README sections), `changelog-agent-prompt.md` (changelog entry);
  - pipeline mechanics: `polish-pass.md`, `packaging.md`, `github-pr-workflow.md` (including marketplace registration), `changelog-format.md`, `step-details.md` (step detail moved out of SKILL.md, plus a file index);
  - state and lifecycle: `ledger-format.md`, `recovery-protocol.md`, `lifecycle.md` (status, rollback, docs-only, pre-ship snapshot);
  - terms: `glossary.md`.
- **`scripts/`** — pure-Python helpers, grouped by job:
  - validation and lints: `quick_validate`, `portability_lint`, `attribution_lint`, `spdx_check`, `link_check`, `security_scan`, `mcp_deps`, `triggering_eval`, `readiness_report`;
  - packaging and publishing: `package_skill`, `github_pr`, `marketplace_register`, `readme_register`, `diff_published`, `install_check`, `tracer_changelog_rows`;
  - ledger and state: `append_ledger`, `render_ledger` (with `ledger-render-config.json`), `ship_manifest`, `verify_ship`, `ship_status`, `recover_dispatch`;
  - shared utilities `frontmatter_util`, `hashutil`; maintainer-only tools (not part of shipping) `check_shared_sync`, `sync_shared`.
- **`assets/`** — fill-in templates: `changelog-entry-template.md`, `pr-template.md`.
- **Outputs:**
  - ship ledger `~/.claude/skill-publisher-ledger/<skill>.md` (one file per skill, accumulating across runs; the rendered HTML sits beside it) and ship manifest `<skill>.manifest.json` (latest ship: version, tier, archive and digest, PR, tag);
  - pre-ship snapshot `<skill>.pre-ship/` (the latest ship only; what `--rollback` restores);
  - the packaged `.skill` archive for `claude-users` and `model-agnostic` skills (its path is reported at the end; `personal` skills are not packaged);
  - edits to the target skill's own SKILL.md, README.md and HISTORY.md; temporary files under `/tmp`, cleaned up at the end.

## How to install

**Claude Code** (from the marketplace in https://github.com/Vaikri-costume/skills):

```
/plugin marketplace add Vaikri-costume/skills
/plugin install ccvw-toolkit@ccvw-skills
```

**Manual** (Claude Code or Cowork): copy `skills/skill-publisher/` from that repo to `~/.claude/skills/skill-publisher/`, or install the packaged `.skill` archive. Claude.ai web: zip the folder and upload it under Settings > Capabilities > Skills.

## Sibling skills

- `skill-creator-ccvw` — the **build** phase. Scaffolds the SKILL.md + README.md + HISTORY.md structure the publisher reads.
- `skill-tracer` — the **trace** phase. Finds correctness bugs before ship. Run it before publishing.
- `marketplace-discover` — searches the catalog the publisher can PR a skill back to.
- `simplify` — invoked at Step 2 for the polish pass.

## For developers

The runtime workflow lives in [`SKILL.md`](SKILL.md). Provenance and changelog live in [`HISTORY.md`](HISTORY.md). To trace this skill for bugs: `/skill-tracer skill-publisher`.
