---
name: skill-publisher
description: "Ship phase of the build → trace → ship skill ecosystem. Polishes a finished skill (mandatory simplify pass on SKILL.md + README.md), runs the CCVW Word/Spirit audit, runs tier-transition checks (portability + attribution + security + Cowork-compatibility per the target's audience tier), generates user-facing README sections (how-to-install, sibling skills), bumps the version + appends a changelog entry in HISTORY.md, packages for distribution, and — for skills with a marketplace/GitHub origin — opens a PR. Use whenever the user wants to ship, publish, release, package, or PR a skill — 'ship skill X', 'publish X', 'release X', 'make a PR for X', 'package X for the marketplace', or after skill-tracer converges and the user wants to distribute. Reads the target's README.md (intent) and HISTORY.md (provenance) — works in degraded mode if HISTORY.md is absent. Do NOT use to find bugs or check correctness (use skill-tracer) or to build or scaffold a skill (use skill-creator-ccvw)."
license: MIT
compatibility: Claude Code 2.0 or newer
metadata:
  tier: claude-users
  created: 2026-05-30
  created-by: Vaikri-costume
  parent-version: 2.0.0
  intended-audience: claude-users
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
  - Agent
  - Skill
  - AskUserQuestion
---

<!-- Provenance, version, attribution chain, and changelog live in HISTORY.md.
     Human-facing intent + how-to-install + sibling skills live in README.md.
     This frontmatter holds only the runtime contract the executor agent loads at startup. -->

# skill-publisher

## What this skill does

The **ship** phase of the build → trace → ship ecosystem. After skill-creator-ccvw builds a skill and skill-tracer finds its bugs, skill-publisher makes it release-ready: polishes the prose, audits CCVW compliance, runs the tier-transition checks appropriate to the target's audience, teaches the README how to install and use the skill, versions it, packages it, and opens a GitHub PR when there's an upstream to PR to.

Each phase suggests the next; skill-publisher is terminal — it produces a shippable artifact (and optionally a PR URL).

---

## When to invoke

- Slash command: `/skill-publisher <skill-name>` or `/skill-publisher <absolute-path>`
- Natural language: "ship skill X", "publish X", "release X", "make a PR for X", "package X for the marketplace"
- **Proactively** after skill-tracer converges on a skill the user intends to share — suggest the ship phase.
- **Opt-in triggering eval** (off by default to protect ship latency): `--triggering-eval --eval-set <queries.json>`, or natural language "eval the triggering / measure if X triggers" during a ship. Adds a measured trigger-accuracy gate to Step 3 (below-threshold → AUDIT cluster). Requires a `{query, should_trigger}` query set; without one, only the cheap description-confidence heuristic runs (it always runs, and feeds `--readiness`).

---

## Prerequisites

The target skill must exist as a directory containing at least a `SKILL.md`. Best results when it also has `README.md` (intent) and `HISTORY.md` (provenance) — skill-publisher works in degraded mode if HISTORY.md is absent (see Step 1). The orchestrator needs `Read`/`Edit`/`Write` on the target, `Agent` for the cold CCVW audit, `Bash` for lints + packaging + git, and `Skill` to invoke `simplify`. (skill-tracer is recommended but not required — its `stage_cold_prompts.py` is the canonical staging path for the Step 3 audit prompt; `references/audit-prompt.md` carries a substitute-by-hand fallback when skill-tracer is absent.)

---

## Runtime constraint — top-level invocation only

skill-publisher requires `Agent` to dispatch the cold CCVW Word/Spirit audit (Step 3). `Agent` is available only in the top-level Claude session — never from inside a nested Agent call. If the orchestrator detects it's a subagent (Agent unavailable), stop and tell the user: "skill-publisher must run from the top-level session; nested Agent dispatch is not available here."

---

## The ledger

skill-publisher records its work at `~/.claude/skill-publisher-ledger/<skill>.md` — one file per target skill, accumulating across ship runs. The Phase column values are POLISH / AUDIT / TIER / PACKAGE / PR (the closed publisher set; full row format + the legacy-phase read-tolerance in `references/ledger-format.md`). Recovery across compaction uses an `in-flight::` marker + atomic-write protocol; the marker format, action-keyword set, and recovery rules are in `references/recovery-protocol.md`.

---

## Workflow

> **Quote path placeholders.** Double-quote `<target>`, `<ledger>`, `<artifact>` and `<published_path>` in every actual command (`git -C "<target>" …`): a skill path may contain a space, and an unquoted placeholder word-splits under zsh (argparse error or the wrong file). Templates omit the quotes only for readability. Likewise a bare `scripts/<name>.py` anywhere in this skill means `~/.claude/skills/skill-publisher/scripts/<name>.py` — run it with that full path.

### Step 1 — Resolve target + read state

**First action: capture `<Runtime>`** (`date -u +%Y-%m-%dT%H:%M`) and reuse that exact string for every marker and row; then load `references/recovery-protocol.md` in full, reject a relative invocation argument, and run its Step-1 ledger-state dispatch. Full text: `references/step-details.md` "Moved: Step 1 first action".

**Capture invocation state:** `<Runtime>`, `<N>` (Run number from the ledger dispatch), `<triggering-eval>` and its eval set. Full text: `references/step-details.md` "Moved: Step 1 invocation state".

(Convention used throughout this skill: **"warn"** means emit a one-line message in your response text this turn — visible to the user — not a session-log entry.)

Resolve the target (bare name means `~/.claude/skills/<name>/`, otherwise the absolute path), verify SKILL.md exists, and bind `<target>` and `<skill>` (the frontmatter `name` is authoritative). Full text: `references/step-details.md` "Moved: Step 1 resolve target".

**Tier value check (run `python3 ~/.claude/skills/skill-publisher/scripts/portability_lint.py "<target>"` as soon as the target is resolved).** If it reports an `unknown-tier` finding, only `personal`, `claude-users` and `model-agnostic` exist. With a `close_match`: correct the field to it, tell the user, and carry on. With none: AskUserQuestion which of the three they meant; never guess between tiers, never ship on the unknown value.

Mode determination: the invocation's mode phrase alone decides `<mode>`, so read it before the Step-1 ledger dispatch above and before reading HISTORY.md: (a) `--readiness`, or NL "can this ship" / "readiness check" → `readiness`; (b) `--docs-only` → `docs-only`; (c) `--rollback`, or NL "undo the ship of X" / "roll back X" → `rollback`; (d) `--status`, or NL "did X merge" / "ship status of X" → `status`; (e) default → `full`.

**Readiness-mode exit (if `<mode>` is `readiness`).** Skip Steps 2–9: resolve the tier (pass `--tier <tier>` explicitly if `metadata.tier` and `metadata.intended-audience` diverge), run `python3 ~/.claude/skills/skill-publisher/scripts/readiness_report.py <target>` and print its output verbatim. Exit 0/1 = verdict (green-yellow / red); exit 2 = usage error — relay the `ERROR:` line, there is no verdict. Writes no ledger rows or markers (fully read-only). Details: `references/step-details.md` "Readiness mode".

**Lifecycle modes (`status`, `rollback`, `docs-only`).** Load `references/lifecycle.md` and follow the matching section; `rollback` always asks first and refuses on a merged PR; `docs-only` refuses unless every changed path is README.md or HISTORY.md. Full text: `references/step-details.md` "Moved: Step 1 lifecycle dispatch".

**Install mode (`--install`, or "install X on this machine").** Its own mode, never part of publishing. Run `python3 ~/.claude/skills/skill-publisher/scripts/install_local.py \"<target>\"` (dry run: lists added, changed and removed files), show the list, AskUserQuestion to confirm, then re-run with `--confirmed`. It backs up the current install first. Details: `references/step-details.md` "Install mode".

A `full` ship continues below.

**Helpers this ship will dispatch (print this list at the start of every full ship, before any dispatch, so the thread can anticipate each one):**

| Step | Helper | Role | Access |
|---|---|---|---|
| 2 | four `simplify` reviewers | phrasing-entropy review of SKILL.md + README.md | read; the orchestrator applies edits |
| 3 | one CCVW Word/Spirit auditor | audit against skill-creator-ccvw | read-only |
| 6 | one README-sections agent | drafts Features & modes + Structure | read-only |
| 7 | one changelog agent | proposes bump + entry (only when a published baseline exists) | read-only |

Every helper prompt starts with "You are the worker, no subagents, cannot redelegate.", holds no names or personal detail (write "the user"; use only they/them for the user and anyone whose pronouns are not stated), writes only to the session scratchpad, and runs on the profile's `helper_model` (default Sonnet, never Opus). One reviewer per role; no second pass unless a cluster is open.

Read the target's SKILL.md, README.md (`## Intent` becomes `<target-intent>`, fallback `## What this skill does`) and HISTORY.md (frontmatter and changelog). HISTORY.md absent means degraded mode: ask once for an attribution category (A/B/C/D or skip). Full rules: `references/step-details.md` "Moved: Step 1 root files" and `references/changelog-format.md`.

The audience tier is `metadata.intended-audience`; if it diverges from `metadata.tier`, warn and ask which is authoritative before Step 4's first command. Full text: `references/step-details.md` "Moved: Step 1 audience tier".

### Step 2 — Polish pass (mandatory)

**Pre-ship snapshot (first action of this step — full + docs-only modes).** Before any edit, copy the target's `SKILL.md`/`README.md`/`HISTORY.md` to `~/.claude/skill-publisher-ledger/<skill>.pre-ship/` so `--rollback` can restore a completed-but-wrong ship — per `references/lifecycle.md` "Pre-ship snapshot". A snapshot failure is a warning (rollback just won't be available this ship), not a blocker.

**Session-log marker:** `echo "**[$(date +%H:%M:%S)] SKILL:skill-publisher RUN:<skill> STEP:polish**" >> "${HOME}/.claude/session-logs/session-log-$(date +%Y-%m-%d).md"` — substitute the actual target skill name for `<skill>`. Non-blocking. **Then write in-flight marker** (per atomic-write table in `references/recovery-protocol.md`): write `in-flight:: <Runtime> polish run-<N>` to the ledger header (insert after the `# Ship ledger — <skill>` title line if absent; replace any existing `in-flight::` line in place).

**Load `references/polish-pass.md` now** (after the pre-ship snapshot, the session-log echo and the in-flight marker). Invoke the `simplify` skill on SKILL.md + README.md, apply every finding while preserving `<target-intent>`, and record each as a POLISH ledger row. Full text and the `append_ledger.py` form: `references/step-details.md` "Moved: Step 2 polish details".

After polish, check the SKILL.md body size: if it exceeds ~5,000 words (~500 lines) after polishing, flag it — the polish pass is the moment to push detail into `references/`, and an over-long SKILL.md taxes every session the skill loads in. Surface as a POLISH cluster (FIX = move a section to a reference; or STRENGTHEN/USER-PAUSE if the length is load-bearing). The 5,000-word ceiling rationale lives in `references/polish-pass.md`.

After polish, suggest the user re-run `/skill-tracer <skill>` if the polish made substantial edits (optional, user-chosen — chained by suggestion). Polish can introduce regressions the way any edit can; a verification trace catches them. Don't block on it.

### Step 3 — CCVW Word/Spirit audit (cold dispatch)

**Session-log marker (first action of this step):** `echo "**[$(date +%H:%M:%S)] SKILL:skill-publisher RUN:<skill> STEP:audit**" >> "${HOME}/.claude/session-logs/session-log-$(date +%Y-%m-%d).md"` — substitute the actual target skill name for `<skill>`. Non-blocking. **Then replace in-flight marker**: write `in-flight:: <Runtime> audit run-<N>` (replacing the Step 2 `polish run-<N>` marker in place, per atomic-write table).

Dispatch one cold audit Agent against skill-creator-ccvw per `references/audit-prompt.md` — **load it now** and follow its procedure; it owns the prompt body, the reference-skill resolution + fallback chain (skill-creator-ccvw → skill-creator → plugin-dev/skill-development), mtime capture, the malformed-result + ABORTED handling, and the result→GAP-collection rules. Collect the GAP blocks as `<audit-gaps>` (kept in context, not written to disk yet), each with a plain `G<n>` flag ID in output order — no hyphen, distinct from the hyphenated TIER sub-families `G-PORT*`/`G-ATTR*`/`G-COWORK*`. **Zero GAPs → proceed to Step 4.** Each GAP is an AUDIT-phase cluster, addressed at Step 5 per `references/ship-checklist.md`'s FIX/STRENGTHEN/USER-PAUSE rules.

This is the "is it CCVW-compatible in word and spirit?" gate — the publisher owns it now, not the tracer. A skill can be bug-free (tracer-clean) but still violate CCVW conventions; this audit catches that before release.

**Triggering signal.** Always run `triggering_eval.py <target> --json` (advisory confidence, never a cluster); only with `--triggering-eval` plus an eval set also run `--run-eval` (below threshold is an AUDIT cluster). Full handling: `references/step-details.md` "Moved: Step 3 triggering signal" and `references/ship-checklist.md`.

### Step 4 — Tier-transition checks (per audience tier)

**Session-log marker (first action of this step):** `echo "**[$(date +%H:%M:%S)] SKILL:skill-publisher RUN:<skill> STEP:tier**" >> "${HOME}/.claude/session-logs/session-log-$(date +%Y-%m-%d).md"` — substitute the actual target skill name for `<skill>`. Non-blocking. **Then replace in-flight marker**: write `in-flight:: <Runtime> tier run-<N>` (replacing the Step 3 `audit run-<N>` marker in place, per atomic-write table).

(`readiness` mode aggregates the cheap gates via `readiness_report.py`; this step also runs the Cowork check and the security scan.) Full text: `references/step-details.md` "Moved: Step 4 readiness note".

**Shared scripts are not sync-checked.** Each of skill-creator-ccvw, skill-tracer and skill-publisher owns an independent copy of `quick_validate`/`portability_lint`/`attribution_lint`/`render_ledger`/`append_ledger`; run this skill's own copies as-is (`references/tier-transition-checks.md` "Shared-script sync checks"; `scripts/check_shared_sync.py` is a dormant manual drift inspector).

Run the checks appropriate to the target's `metadata.intended-audience`. **Load `references/tier-transition-checks.md` now** — it is the authoritative full spec for every gate below (output-key interpretation, the blocking rule, the structural-blocker lists, and per-check mechanics); the per-tier bullets here are the summary, and if the two differ, follow the reference.

**Frontmatter-validity gate (claude-users+ — runs first, blocking).** Before the tier-specific checks, run the deterministic frontmatter gate:

```bash
python3 ~/.claude/skills/skill-publisher/scripts/quick_validate.py <target>; echo "exit:$?"
python3 ~/.claude/skills/skill-publisher/scripts/portability_lint.py <target> --tier <tier> > /tmp/skill-publisher-lint-out.json; echo "exit:$?"   # canonical temp file the reuse rule below reads
```

Append `; echo "exit:$?"` to commands whose exit code drives a branch (the Bash tool keeps no shell state). Full text: `references/step-details.md` "Moved: Step 4 exit codes".

A non-zero `quick_validate.py` exit is a **blocking TIER finding**; exit 3 = PyYAML not installed (environment gap — tell the user to `pip install pyyaml`, raise no cluster). `portability_lint.py` adds registration-correctness blockers (name == folder, no reserved prefix, no XML-shaped frontmatter, exact `SKILL.md`, plan-code leakage), each a TIER cluster at any shared tier. Full lists and the exit-1 disambiguation: `references/tier-transition-checks.md` "Frontmatter-validity gate".

- **`personal`**: skip Step 4 entirely (including the frontmatter gate).
- **`claude-users`**: reuse the portability JSON above, then run `link_check.py <target>` (broken links/unreadable files block; dead scripts advisory), the Cowork-compatibility check (`references/cowork-compatibility.md`), `attribution_lint.py` then `spdx_check.py <target>` (no `--require` here), `security_scan.py <target>` (`references/security-checks.md`; a non-empty `unreadable_files` means an incomplete scan) and `mcp_deps.py <target>`. Exit codes and finding→cluster rules: `references/step-details.md` "Step 4 gates"; `references/tier-transition-checks.md` wins on any conflict.
- **`model-agnostic`**: all `claude-users` checks plus `portability_lint.py --tier model-agnostic`, `compatibility: agentskills.io@1.0` verification and a user-confirmed cross-runtime install-surface note.


### Step 5 — Address findings

**Session-log marker (first action of this step):** `echo "**[$(date +%H:%M:%S)] SKILL:skill-publisher RUN:<skill> STEP:addressing**" >> "${HOME}/.claude/session-logs/session-log-$(date +%Y-%m-%d).md"` — substitute the actual target skill name for `<skill>`. Non-blocking. **Then replace in-flight marker**: write `in-flight:: <Runtime> addressing run-<N>` (replacing the Step 4 `tier run-<N>` marker in place, per atomic-write table).

Before addressing, confirm `<target-intent>`, `<N>` and `<Runtime>` are set (re-derive them from disk or the in-flight marker after a recovery resume). Full text: `references/step-details.md` "Moved: Step 5 preconditions".

For every cluster in `<audit-gaps>` + `<tier-clusters>`: FIX, STRENGTHEN or USER-PAUSE (intent-ambiguous means ask). **Load `references/ship-checklist.md` now** for the rules and the `append_ledger.py` row format, then run `close-round`. Full text: `references/step-details.md` "Moved: Step 5 addressing".

### Step 6 — Generate user-facing README sections

**Session-log marker (first action of this step):** `echo "**[$(date +%H:%M:%S)] SKILL:skill-publisher RUN:<skill> STEP:readme**" >> "${HOME}/.claude/session-logs/session-log-$(date +%Y-%m-%d).md"` — substitute the actual target skill name for `<skill>`. Non-blocking.

**Clear the in-flight marker** (per recovery-protocol.md atomic-write table: "cleared at Step 6"): remove the `in-flight::` line from the ledger header via Edit — this signals that steps 6–7 (README gen + version bump) are local edits, re-runnable if interrupted.

**Author the sections the publisher owns (cold agent, first).** Load `references/readme-agent-prompt.md`, dispatch the cold README agent on the final SKILL.md and the bare file list, apply its `FEATURES_AND_MODES` and `STRUCTURE` blocks after `## How to invoke` (replacing earlier ones), add any `INVOKE_GAPS` modes, and never re-author the creator's sections. Full text: `references/step-details.md` "Moved: Step 6 README agent".

Fill the README placeholders: `## How to install` (per tier, form from the upstream source URL, probe with `install_check.py`, never run an install) and `## Sibling skills` (from HISTORY.md `inspirations[]`). Full text: `references/step-details.md` "Moved: Step 6 placeholders" and `references/packaging.md`.

Together with the authored `## Features & modes` + `## Structure` above, these sections teach a new user **what the skill does, how to use it and in which mode, how it's laid out, how to install it, and what pairs with it** — the "polish it to also teach others" goal.

**Outcomes-first positioning (heuristic, not a gate).** Value-carrying README copy should lead with the outcome the user gets, not the mechanism; rewrite toward it, and add the MCP-plus-skill one-liner when the target pairs with an MCP server. Examples: `references/polish-pass.md` "Outcomes-first positioning"; full text: `references/step-details.md` "Step 6".

### Step 7a — Resolve upstream + diff against published state

**Resolve `<upstream>` and `<repo-path>` here** (HISTORY.md `author.history[].source`, else `inspirations[].source`; none means a ledger-only changelog) and write the `changelog run-<N>` marker. Full text: `references/step-details.md` "Moved: Step 7a resolution".

**Write the in-flight marker** `in-flight:: <Runtime> changelog run-<N>` (the diff-clone + cold agent dispatch below are a state-changing step per the atomic-write table; recovery rule for `changelog` re-runs Step 7a — the clone + dispatch are idempotent/cheap). Then:

```bash
python3 ~/.claude/skills/skill-publisher/scripts/github_pr.py <target> --upstream <upstream> --repo-path <repo-path> --diff-only; echo "exit:$?"
```

Run the command above; full output shapes, exit codes and fallbacks: `references/step-details.md` "Moved: Step 7a diff". On `no_published_state` or exit 2 or 6, fall back to a ledger-only changelog and tell the user the diff was skipped; otherwise run `diff_published.py` below.

```bash
python3 ~/.claude/skills/skill-publisher/scripts/diff_published.py <target> --published <published_path> > /tmp/skill-publisher-diff.json; echo "exit:$?"
```

Exit 0 → the structured diff is in `/tmp/skill-publisher-diff.json` (feed it to Step 7's changelog agent). Exit 1 → `no_published_state` (fall back to ledger-only). Exit 2 → path error (fix and re-run, or fall back). Reusing the same `<upstream>`/`<repo-path>` at Step 9 means the PR step never re-asks.

### Step 7 — Version bump + changelog

**Session-log marker (first action of this step):** `echo "**[$(date +%H:%M:%S)] SKILL:skill-publisher RUN:<skill> STEP:version**" >> "${HOME}/.claude/session-logs/session-log-$(date +%Y-%m-%d).md"` — substitute the actual target skill name for `<skill>`. Non-blocking.

**Pre-PR bump gate (after the HISTORY.md edit below).** Run `python3 ~/.claude/skills/skill-publisher/scripts/verify_ship.py "<target>" --version <new-version> --parent-version <prior> --changelog-only; echo "exit:$?"`. Exit 1 → read `required_failures`, fix the bump or marks and re-run; an unmarked `Removed` bullet is a QUESTION to the user (interface or internal?), never a guess. Do not continue to Step 8 until exit 0.

The third signal (tracer audit fixes): run `python3 ~/.claude/skills/skill-publisher/scripts/tracer_changelog_rows.py <skill>`: exit 0 → its text block is the `[TRACER_LEDGER_ROWS]` slot; exit 1 (no tracer ledger) → the literal `none` (use `--ledger` plus `--manifest ~/.claude/skill-publisher-ledger/<skill>.manifest.json` if the skill was traced under another name). Details: `references/step-details.md` "Step 7".

**Changelog sourcing.** With a structured diff from Step 7a, dispatch the cold changelog agent per `references/changelog-agent-prompt.md` (**load it now**) and use its `ENTRY` + `final_bump`; with no published state, source from this run's ledger rows alone per `references/changelog-format.md`. Then remove any `changelog run-<N>` marker. Reconciliation rules: `references/step-details.md` "Step 7".

In HISTORY.md: increment `version` (bind `<prior>`, `<new-version>` and `<bump-type>` — the highest SemVer level any change warrants: patch fixes, minor new capability, major breaking), append the changelog entry per `references/changelog-format.md`, and set SKILL.md `metadata.parent-version` to `<prior>` (bare unquoted semver, or `pre-versioned`). Degraded-mode handling is in `references/changelog-format.md`; the full bump rules: `references/step-details.md` "Step 7"; the re-run idempotency guards: `references/recovery-protocol.md` "No marker".

### Step 7b — Personal-data scan (before packaging)

Run `python3 ~/.claude/skills/skill-publisher/scripts/personal_data_scan.py \"<target>\" [--profile <user-profile file>]` (profile key `personal_terms`) and pipe the PR body and the new changelog entry to it as `-`. Home-directory paths, email addresses and the profile's `personal_terms` must be replaced with "the user" or a profile reference. The same scan flags any gendered pronoun in markdown and piped text: everything this skill writes (README sections, changelog entry, PR body, reports to the user) refers to the user, and to anyone whose pronouns are not stated, with they/them only. Exit 1 → each finding is a TIER cluster fixed in Step 5's way; re-run until exit 0. The same scan runs again on the staged PR files in Step 9's dry-run (`personal_data`), and a finding blocks the confirmed push (exit 9).

### Step 8 — Package for distribution (per tier)

**Session-log marker (first action of this step):** `echo "**[$(date +%H:%M:%S)] SKILL:skill-publisher RUN:<skill> STEP:packaging**" >> "${HOME}/.claude/session-logs/session-log-$(date +%Y-%m-%d).md"` — substitute the actual target skill name for `<skill>`. Non-blocking. **Then write in-flight marker**: write `in-flight:: <Runtime> packaging run-<N>` (the marker is absent after Step 6 cleared it — insert it fresh, per atomic-write table). **Important:** this `packaging run-<N>` marker is cleared by Step 9 on every path — if a PR is opened, Step 9 replaces it with `pr run-<N>` (cleared at Step 10); if no PR is opened, Step 9 clears the `packaging` marker before the no-PR exit. A stale `packaging` marker would cause the packaging-marker recovery (the `packaging` row of recovery-protocol.md's marker state-table) to re-fire Step 8 unnecessarily.

- **`personal`**: no packaging. Files stay in place.
- **`claude-users`** / **`model-agnostic`**: `python3 ~/.claude/skills/skill-publisher/scripts/package_skill.py <target> --tier <tier> --output <scratchpad>/<name>.skill > /tmp/skill-publisher-package-out.json` (always pass `--output` into the scratchpad: the default writes the archive next to the skill folder, inside the skills directory); read `packaged` (Step 10's `--artifact`) and `archive_sha256` (its `--expected-digest`) from it. Exit codes (model-agnostic adds exit 3 = conformance failure → PACKAGE cluster) and the Claude.ai zip route: `references/packaging.md`; full text: `references/step-details.md` "Step 8".
- **Unknown tier value**: handled by the Step 1 "Tier value check" (close match corrected and reported; otherwise ask). Never package on an unknown value.

### Step 9 — PR to GitHub (if upstream origin)

**Session-log marker (first action of this step):** `echo "**[$(date +%H:%M:%S)] SKILL:skill-publisher RUN:<skill> STEP:pr**" >> "${HOME}/.claude/session-logs/session-log-$(date +%Y-%m-%d).md"` — substitute the actual target skill name for `<skill>`. Non-blocking. **Then handle the in-flight marker by path**: if a PR will be attempted (upstream origin recorded, not degraded mode), write `in-flight:: <Runtime> pr run-<N>` (replacing the `packaging run-<N>` marker in place, per atomic-write table). If no PR will be opened (no upstream or degraded mode), do NOT write a `pr run-<N>` marker — instead clear the `packaging run-<N>` marker now and proceed marker-free through the no-PR path. (WHY: a stray `pr run-N` marker would make recovery Rule D assume a PR was attempted and run `gh pr list`, which is wrong when no PR was ever started.) If a crash happens after `gh repo create` on the no-upstream hosting path, no marker records it: the resume then starts at Step 6 with no marker, so check `gh repo view <name>` first and skip the repo-creation step when the repository already exists.

**Full-history scan (mandatory on every publish, before the confirm).** Run `python3 ~/.claude/skills/skill-publisher/scripts/history_scan.py <upstream> [--profile <user-profile file>] --work-dir <scratchpad> > <scratchpad>/history-report.json` (read-only: file contents, commit messages and author identities over every commit). Exit 0 is required. Any finding blocks the push: `github_pr.py` exits 10 on `--confirmed` without that clean report passed as `--history-report`. Past commits are fixed only by a rewrite: run `scripts/history_rewrite_plan.py <report> --out-dir <scratchpad>` (it prints, never runs), show the user the exact findings and commands (mirror backup first, `git filter-repo`, force-push), say that a force-push conflicts with a merge-never-rebase rule and that unpushed local commits must be bundled first, and run nothing without their typed yes for that exact list. Details: `references/step-details.md` "History scan".

**Prepare everything first, then ask once.** Do all of this without asking: stage the skill, run the personal-data scan and the full-history scan, make the PR-copy dry run, fill the PR body, and run the install dry run. Then send ONE message (one AskUserQuestion with separate questions, or one chat message) holding: (1) install on this machine, with the install dry-run list of added, changed and removed files; (2) push, with the dry-run summary (`removed_files`, `personal_data`, history result, marketplace and README choices); (3) if the history scan found anything, the exact findings list and the rewrite commands from `history_rewrite_plan.py`. Install is asked first and happens first; each item has its own yes, and a yes to one never covers another. Publishing itself never installs.

**Reuse Step 7a's resolution.** `<upstream>` + `<repo-path>` were already resolved at Step 7a (the resolution moved there so the changelog could diff against the published state) — reuse those exact values here; do NOT re-resolve or re-ask. (Step 7a's `--diff-only` clone at `clone_dir` is removed at Step 10; the full PR below makes its own clone — re-cloning a shallow repo is cheap and avoids reusing a possibly-stale checkout.) If Step 7a was skipped (it ran only when an upstream existed), there is no upstream and this is the no-PR / no-upstream-hosting path below.

**Load `references/github-pr-workflow.md` now** and follow it: it owns the whole PR path (upstream precedence, invocation arguments, exit codes, license gate, no-upstream hosting, source-recording invariant). Full text of the pieces that stay here: `references/step-details.md` "Moved: Step 9 PR reference".

**Step 9 orchestration** (full text: `references/step-details.md` "Moved: Step 9 orchestration"; read it before running `github_pr.py`). Write the `pr run-<N>` marker. The first `github_pr.py` call is always `--dry-run`: show the summary (`removed_files`, `personal_data`, marketplace and README states) and put it into the single ask above (do not ask separately); push only with `--confirmed` after the user's own yes for the push, never to main. Install is its own item and happens first; publishing never installs.

### Step 10 — Present result

**Mark verification first** (Step 10 is not done until verification passes): replace the `pr run-<N>` marker (or insert one, on the no-PR path where Step 9 cleared it) with `in-flight:: <Runtime> verify run-<N>` in the ledger header. The marker stays set until `verify_ship.py` exits 0; only then is it removed (see below), so an interrupted or failed verification leaves an unfinished ship that the next run recovers (`references/recovery-protocol.md`, marker `verify`). The Step-7a diff-clone is removed by this step's cleanup action below.

Post-ship verification: run `scripts/verify_ship.py` to confirm the ship actually landed:

```bash
python3 ~/.claude/skills/skill-publisher/scripts/verify_ship.py <target> --version <new-version> --parent-version <prior> [--artifact <path>] [--expected-digest <archive_sha256>] [--pr-url <url>]
# exit 0 = all required checks passed; exit 1 = a required check FAILED — read the `required_failures` array from the JSON output and report each named failure to the user, then STOP without replacing the run-summary comment or writing the ship manifest (leave the `verify run-<N>` marker set and add the line `verify-failed:: <the required_failures, joined with ; >` under it in the ledger header, so the next run sees an unfinished ship; the temp-file cleanup at the end of this step still runs, it is housekeeping) (a ship with known verification failures must not be recorded as landed — do not report success, do not proceed to the canonical-comment replacement or the manifest write below); exit 2 = usage/argparse error — TWO causes: (a) --version missing, or (b) --artifact passed without --expected-digest (they are co-required — re-run Step 8 to capture archive_sha256); the stderr message names which. Re-run with corrected arguments.
```

It checks the new version, its changelog heading and Keep-a-Changelog categories/bump (`--strict-changelog`), the artifact's SHA-256 (`--expected-digest`, always for shared tiers; omit `--artifact` for personal) and that the PR resolves. A `NOTE: PR check unverified` on stderr is informational. A pre-versioned target skips only the bump check. Details: `references/step-details.md` "Step 10".

**Replace the run-summary comment with the canonical form** (only after `verify_ship.py` above exits 0, so a failed verification leaves the generated `Round N total` comment and the ledger never reads as a completed ship; version and PR URL are known). Branch on what Run N already has: the canonical `<!-- Run N total:` line → leave it; the generated `<!-- Round N total:` line → recount the Run-N rows (do NOT re-run `close-round`, it would append a second comment) and Edit-replace it; neither → append the canonical line fresh. Recount rules: `references/ledger-format.md` "Run + invocation summary comments" and `references/step-details.md` "Step 10".

The canonical run-summary form and its degraded variants: `references/ledger-format.md` "Run + invocation summary comments" and `references/step-details.md` "Moved: Step 10 canonical form".

**On exit 0, remove the `verify run-<N>` marker (and any `verify-failed::` line) from the ledger header via Edit; the ship counts as landed from here.**

**Write the ship manifest** (after verify_ship passes — on EVERY ship path, including no-upstream and degraded). Record the durable ship facts for the lifecycle tools (Phase 4 status/rollback):

```bash
python3 ~/.claude/skills/skill-publisher/scripts/ship_manifest.py write <skill-name> \
  --version <new-version> --tier <tier> --timestamp <Runtime> \
  [--artifact <path>] [--digest <archive_sha256>] [--pr-url <url>] [--branch <branch>] [--tag <name>-v<version>] [--merge-strategy-unknown]
# writes ~/.claude/skill-publisher-ledger/<skill>.manifest.json; exit 0 ok; exit 2 usage (argparse); exit 3 I/O error (write failed)
```

Omit flags that don't apply (no artifact/digest for personal; no PR/branch/tag without a PR); use `--version n/a` on the full-skip degraded path and `--merge-strategy-unknown` when the upstream may squash/rebase. A manifest write failure (exit 3) is reported but does not un-ship. Degraded-skip verification and the render step: `references/step-details.md` "Step 10".

Render the ledger HTML with `render_ledger.py` (never block on a render failure; skip when the ledger is absent or has no data rows) and relay the `Wrote HTML to <path>` line. Full text: `references/step-details.md` "Moved: Step 10 ledger render".

**Clean up temp artifacts** (tmp-file hygiene — do this on every Step-10 exit path): `python3 ~/.claude/skills/skill-publisher/scripts/github_pr.py "<target>" --upstream <upstream> --repo-path <repo-path> --cleanup [--work-dir <scratchpad>]` removes Step 7a's diff-clone from inside Python (no shell `rm`, so no delete prompt). The two small temp JSON files (`/tmp/skill-publisher-diff.json`, `/tmp/skill-publisher-package-out.json`) are overwritten by the next ship; leave them. A missing clone is a no-op.

Publisher is terminal — no "suggested next". The skill is shipped.

---

## References

Each file is loaded or run at the step that names it. Annotated index: `references/step-details.md` "File index".
- References: `references/readiness-gates.md`, `references/ship-checklist.md`, `references/tier-transition-checks.md`, `references/cowork-compatibility.md`, `references/audit-prompt.md`, `references/polish-pass.md`, `references/security-checks.md`, `references/github-pr-workflow.md`, `references/changelog-agent-prompt.md`, `references/readme-agent-prompt.md`, `references/packaging.md`, `references/changelog-format.md`, `references/recovery-protocol.md`, `references/ledger-format.md`, `references/glossary.md`, `references/lifecycle.md`
- Scripts: `scripts/readiness_report.py`, `scripts/diff_published.py`, `scripts/tracer_changelog_rows.py`, `scripts/github_pr.py`, `scripts/marketplace_register.py`, `scripts/readme_register.py`, `scripts/package_skill.py`, `scripts/render_ledger.py`, `scripts/spdx_check.py`, `scripts/security_scan.py`, `scripts/mcp_deps.py`, `scripts/link_check.py`, `scripts/triggering_eval.py`, `scripts/install_check.py`, `scripts/frontmatter_util.py`, `scripts/verify_ship.py`, `scripts/ship_manifest.py`, `scripts/ship_status.py`, `scripts/check_shared_sync.py`, `scripts/sync_shared.py`, `scripts/{quick_validate,portability_lint,attribution_lint}.py` (`check_shared_sync.py` and `sync_shared.py` are dormant manual tools, not part of the ship flow).

**Sibling skills**: `skill-creator-ccvw` (build phase — scaffolds the structure publisher reads), `skill-tracer` (trace phase — finds bugs before ship), `marketplace-discover` (catalog the publisher PRs back to).
