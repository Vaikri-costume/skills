---
name: skill-publisher
description: "Ship phase of the build → trace → ship skill ecosystem. Polishes a finished skill (mandatory simplify pass on SKILL.md + README.md), runs the CCVW Word/Spirit audit, runs tier-transition checks (portability + attribution + security + Cowork-compatibility per the target's audience tier), generates user-facing README sections (how-to-install, sibling skills), bumps the version + appends a changelog entry in HISTORY.md, packages for distribution, and — for skills with a marketplace/GitHub origin — opens a PR. Use whenever the user wants to ship, publish, release, package, or PR a skill — 'ship skill X', 'publish X', 'release X', 'make a PR for X', 'package X for the marketplace', or after skill-tracer converges and the user wants to distribute. Reads the target's README.md (intent) and HISTORY.md (provenance) — works in degraded mode if HISTORY.md is absent. Do NOT use to find bugs or check correctness (use skill-tracer) or to build or scaffold a skill (use skill-creator-ccvw)."
license: MIT
compatibility: Claude Code 2.0 or newer
metadata:
  tier: claude-users
  created: 2026-05-30
  created-by: Vaikri-costume
  parent-version: 1.3.0
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

> **Quote path placeholders.** Double-quote `<target>`, `<ledger>`, `<artifact>` and `<published_path>` in every actual command (`git -C "<target>" …`): a skill path may contain a space, and an unquoted placeholder word-splits under zsh (argparse error or the wrong file). Templates omit the quotes only for readability.

### Step 1 — Resolve target + read state

**First action: capture `<Runtime>`** = current UTC `YYYY-MM-DDTHH:MM` (run `date -u +%Y-%m-%dT%H:%M`) — capture it before the recovery check below (which makes tool calls); reuse the identical `YYYY-MM-DDTHH:MM` string VERBATIM for every in-flight marker and ledger row this run, so recovery Rule B's marker read-back matches. **Next, load `references/recovery-protocol.md` in full** — the marker check requires it. **Then, before any ledger lookup, reject a relative invocation argument:** if the argument is a relative path (neither a bare name nor an absolute path), reject it and ask the user to re-invoke — this guard runs before the ledger dispatch so a traversal path is never used as `<skill>`. Only once it passes, run recovery-protocol.md's **Step-1 ledger-state dispatch** against `~/.claude/skill-publisher-ledger/<skill>.md`: it covers every case — ledger-absent (create + start Run 1), unreadable (USER-PAUSE), an in-flight marker (run the matching recovery rule), an unparseable/unknown-keyword marker (fallback + surface), and no marker (the No-marker case → completed/crashed/Run-1). After it returns, `<N>` (the Run number) is set.

**Capture invocation state** (do now, before any tool call that changes time):
- `<Runtime>` = the UTC timestamp captured as the First action above (reused, never re-derived).
- `<N>` = the Run number determined from the ledger state above (Run 1 for first-ever ship; highest-existing-run + 1 for a fresh run; current in-flight run number for a resumed run). Retain both values in conversation context throughout the run.
- `<triggering-eval>` = true if `--triggering-eval` is present OR the invocation matches "eval the triggering" / "measure (if/whether) X triggers" / "run the triggering eval"; else false. `<triggering-eval-set>` = the `--eval-set <path>` value if given, else null. Both are read at Step 3. (Independent of `<mode>` — the eval is an add-on to a `full` ship, not a mode; ignored in `readiness` mode, which runs only the cheap heuristic via `readiness_report.py`.)

(Convention used throughout this skill: **"warn"** means emit a one-line message in your response text this turn — visible to the user — not a session-log entry.)

Resolve the target: bare `<name>` → `~/.claude/skills/<name>/`; absolute path → use directly. (A relative path was already rejected above.) Verify SKILL.md exists. The resolved absolute skill-root path is bound to `<target>` and used verbatim in every downstream script command (Steps 4/8/9/10); later steps never re-derive it from the raw invocation argument. The target's SKILL.md frontmatter `name` field value is `<skill>` — used in all session-log markers (Steps 2–9) and the ledger path `~/.claude/skill-publisher-ledger/<skill>.md`. (If the frontmatter `name` differs from the invocation argument used for the initial ledger lookup, surface a warning and use the frontmatter value — it is authoritative. If a provisional ledger was created/read at the invocation-argument path during the initial lookup, move it to the frontmatter-name path before writing any rows — or, if it already holds prior-run rows, USER-PAUSE to reconcile — so the recovery marker and this run's rows do not split across two ledger files.)

**Determine `<mode>`.** After resolving the target, before opening the ledger or reading HISTORY.md, determine the invocation mode: (a) `--readiness`, or NL "can this ship" / "readiness check" → `readiness`; (b) `--docs-only` → `docs-only`; (c) `--rollback`, or NL "undo the ship of X" / "roll back X" → `rollback`; (d) `--status`, or NL "did X merge" / "ship status of X" → `status`; (e) default → `full`.

**Readiness-mode exit (if `<mode>` is `readiness`).** Skip Steps 2–9: resolve the tier (pass `--tier <tier>` explicitly if `metadata.tier` and `metadata.intended-audience` diverge), run `python3 ~/.claude/skills/skill-publisher/scripts/readiness_report.py <target>` and print its output verbatim. Exit 0/1 = verdict (green-yellow / red); exit 2 = usage error — relay the `ERROR:` line, there is no verdict. Writes no ledger rows or markers (fully read-only). Details: `references/step-details.md` "Readiness mode".

**Lifecycle-mode dispatch (if `<mode>` is `status`, `rollback`, or `docs-only`).** Load `references/lifecycle.md` and follow the matching section:
- **`status`** — run `ship_status.py --status <skill>` (add `--repoint-tag` only if the user asks to fix a dangling tag); print the output verbatim; read-only; exit.
- **`rollback`** — read the manifest, **AskUserQuestion to confirm**, restore the pre-ship snapshot, delete the artifact, and close the PR (REFUSE on an already-merged PR — offer a revert PR instead), then record a ledger row; exit. Outward-facing — never silent.
- **`docs-only`** — run Step 7a's diff first; **if every changed path is README.md/HISTORY.md**, run the reduced pipeline (polish + `quick_validate`/`spdx_check` + a patch bump + package + PR, skipping Step 3's cold audit and Step 4's behavioral tier lints); **else refuse** and route the user to a full ship. Then proceed through Steps 6–10 on the docs-only path.

A `full` ship continues below.

Read the target's three root files into in-memory state:
- **SKILL.md** — the runtime workflow being shipped. (No separate in-memory label needed — the executor follows it step by step and does not retain it under a named variable.)
- **README.md** — read the `## Intent` section into `<target-intent>` (used by the polish pass to preserve intent; if README.md is absent OR present without a `## Intent` section, warn and set `<target-intent>` to the target's SKILL.md `## What this skill does` section as fallback).
- **HISTORY.md** — read the YAML frontmatter (`version`, `category`, `author.primary`, `author.history`, `inspirations`) + changelog; later steps reference these fields by path. **If HISTORY.md is absent → degraded mode**: prompt the user once for an attribution category (A/B/C/D) or 'skip', then scaffold a minimal HISTORY.md (valid A/B/C/D) or ship locally ('skip'); retain the answer as `<attribution-answer>`. The full prompt text + re-ask, the closed minimal-field set, the `infer_category`/`author.primary` handling, and the **skip-branch consequences** (on 'skip', Steps 2–5 are bypassed — no close-round comment — no version bump, no upstream PR, Step 8 packages as normal) are in `references/changelog-format.md` "Degraded-mode HISTORY.md scaffold" + "On 'skip'". Those skip consequences are control-flow several downstream steps key on.

Determine the **audience tier** from `metadata.intended-audience` (one of `personal` / `claude-users` / `model-agnostic`) — it drives Step 4's checks and Step 8's packaging. If `metadata.tier` and `metadata.intended-audience` **diverge**, warn (state both fields + their values) and ask the user which is authoritative for this run — `portability_lint.py` reads `metadata.tier` when `--tier` is omitted, so a divergence would validate against the wrong tier. Steps 2–3 don't depend on the tier and can proceed while the user decides, but **resolve the divergence before Step 4's first command** (the portability gate needs the authoritative `--tier`); a valid answer names a field (`metadata.tier` / `metadata.intended-audience`) or a tier value directly (which is then the authoritative `--tier`).

### Step 2 — Polish pass (mandatory)

**Pre-ship snapshot (first action of this step — full + docs-only modes).** Before any edit, copy the target's `SKILL.md`/`README.md`/`HISTORY.md` to `~/.claude/skill-publisher-ledger/<skill>.pre-ship/` so `--rollback` can restore a completed-but-wrong ship — per `references/lifecycle.md` "Pre-ship snapshot". A snapshot failure is a warning (rollback just won't be available this ship), not a blocker.

**Session-log marker:** `echo "**[$(date +%H:%M:%S)] SKILL:skill-publisher RUN:<skill> STEP:polish**" >> "${HOME}/.claude/session-logs/session-log-$(date +%Y-%m-%d).md"` — substitute the actual target skill name for `<skill>`. Non-blocking. **Then write in-flight marker** (per atomic-write table in `references/recovery-protocol.md`): write `in-flight:: <Runtime> polish run-<N>` to the ledger header (insert after the `# Ship ledger — <skill>` title line if absent; replace any existing `in-flight::` line in place).

**Load `references/polish-pass.md` now (after the pre-ship snapshot, the session-log echo, and the in-flight marker write above — those three precede it)** — it owns the full simplify invocation procedure, 4-agent pass, Targeted Reversal, and regression handling. Then invoke the `simplify` skill on the target's SKILL.md + README.md to remove phrasing entropy (use the Skill tool — the invocation guidance is in `references/polish-pass.md`). Apply every finding with consolidation + intent awareness (preserve `<target-intent>`; don't simplify away load-bearing WHY content — a WHY is load-bearing when removing it would leave a rule undefended: the reader could not tell from context why the rule exists or why it must be that specific form; a comment that merely elaborates without defending a constraint is editorial, not load-bearing). Record each polish edit as a POLISH-phase ledger row, numbering clusters with the per-Run `C<n>` sequence (C1, C2, … continuing across POLISH/AUDIT/TIER/PACKAGE/PR within this Run, per `references/ledger-format.md`). The append form (Step 5 has the full spec) is `append_ledger.py append <ledger> --runtime <Runtime> --round <N> --phase POLISH --cluster C# --root-cause '...' --address '...' --flags '...'` — run `python3` as the literal command word, not via a shell variable (see `references/ship-checklist.md`). The publisher writes only FIX/STRENGTHEN/USER-PAUSE addresses (never would-*, which append_ledger also accepts only for skill-tracer verify-only parity). WHY record them: the POLISH rows make the polish pass auditable in the same ledger as the audit/tier work, and let a post-compaction resume see which edits already landed.

After polish, check the SKILL.md body size: if it exceeds ~5,000 words (~500 lines) after polishing, flag it — the polish pass is the moment to push detail into `references/`, and an over-long SKILL.md taxes every session the skill loads in. Surface as a POLISH cluster (FIX = move a section to a reference; or STRENGTHEN/USER-PAUSE if the length is load-bearing). The 5,000-word ceiling rationale lives in `references/polish-pass.md`.

After polish, suggest the user re-run `/skill-tracer <skill>` if the polish made substantial edits (optional, user-chosen — chained by suggestion). Polish can introduce regressions the way any edit can; a verification trace catches them. Don't block on it.

### Step 3 — CCVW Word/Spirit audit (cold dispatch)

**Session-log marker (first action of this step):** `echo "**[$(date +%H:%M:%S)] SKILL:skill-publisher RUN:<skill> STEP:audit**" >> "${HOME}/.claude/session-logs/session-log-$(date +%Y-%m-%d).md"` — substitute the actual target skill name for `<skill>`. Non-blocking. **Then replace in-flight marker**: write `in-flight:: <Runtime> audit run-<N>` (replacing the Step 2 `polish run-<N>` marker in place, per atomic-write table).

Dispatch one cold audit Agent against skill-creator-ccvw per `references/audit-prompt.md` — **load it now** and follow its procedure; it owns the prompt body, the reference-skill resolution + fallback chain (skill-creator-ccvw → skill-creator → plugin-dev/skill-development), mtime capture, the malformed-result + ABORTED handling, and the result→GAP-collection rules. Collect the GAP blocks as `<audit-gaps>` (kept in context, not written to disk yet), each with a plain `G<n>` flag ID in output order — no hyphen, distinct from the hyphenated TIER sub-families `G-PORT*`/`G-ATTR*`/`G-COWORK*`. **Zero GAPs → proceed to Step 4.** Each GAP is an AUDIT-phase cluster, addressed at Step 5 per `references/ship-checklist.md`'s FIX/STRENGTHEN/USER-PAUSE rules.

This is the "is it CCVW-compatible in word and spirit?" gate — the publisher owns it now, not the tracer. A skill can be bug-free (tracer-clean) but still violate CCVW conventions; this audit catches that before release.

**Triggering signal (description quality).** Run the **always-on confidence heuristic**: `python3 ~/.claude/skills/skill-publisher/scripts/triggering_eval.py <target> --json` → `description_quality.confidence` (high/medium/low, from the P1b negative-trigger-boundary + WHEN signals). It is advisory — the same field `--readiness` surfaces — so low confidence reinforces an audit description GAP but is **never itself a cluster**. If `<triggering-eval>` is true **AND `<triggering-eval-set>` is non-null**, ALSO run the opt-in measured accuracy: `python3 ~/.claude/skills/skill-publisher/scripts/triggering_eval.py <target> --run-eval --eval-set <triggering-eval-set> --json` (delegates to skill-creator-ccvw's `run_eval.py`, never reimplemented; `Agent`/`claude -p` latency, hence opt-in). The full handling — the exit 0/1/2/3 actions, the below-threshold (exit 1) → **AUDIT cluster** (flag `trigger-accuracy`, FIXed in Step 5 by rewriting the description), the broken-environment degrade (exit 3), and the natural-language-requested-but-no-`--eval-set` degrade — is in `references/ship-checklist.md` "On the description-quality row" (loaded at Step 5). The heuristic alone never adds a cluster; only a `--run-eval` below-threshold result does.

### Step 4 — Tier-transition checks (per audience tier)

**Session-log marker (first action of this step):** `echo "**[$(date +%H:%M:%S)] SKILL:skill-publisher RUN:<skill> STEP:tier**" >> "${HOME}/.claude/session-logs/session-log-$(date +%Y-%m-%d).md"` — substitute the actual target skill name for `<skill>`. Non-blocking. **Then replace in-flight marker**: write `in-flight:: <Runtime> tier run-<N>` (replacing the Step 3 `audit run-<N>` marker in place, per atomic-write table).

(The cheap deterministic gates below — `quick_validate`, `portability_lint`, `link_check`, `spdx_check`, `attribution_lint`, `mcp_deps` — are also aggregated by `scripts/readiness_report.py` for `readiness` mode per `references/readiness-gates.md`. A `--readiness` check surfaces what this step will find before Step 2–3 cost is incurred. `readiness_report.py` runs a **superset**: in addition to these six it adds advisory-only gates that Step 4 does not run as blocking TIER checks — `description` (the `triggering_eval` confidence heuristic, a NOTE), `history` (HISTORY.md presence), and `upstream_url` (whether a PR will open) — so the two gate sets are not identical, and a green/yellow readiness verdict folds in those advisory signals. This full step additionally runs the Cowork-compatibility check and security scan, which readiness mode omits.)

**Shared scripts are not sync-checked.** Each of skill-creator-ccvw, skill-tracer and skill-publisher owns an independent copy of `quick_validate`/`portability_lint`/`attribution_lint`/`render_ledger`/`append_ledger`; run this skill's own copies as-is (`references/tier-transition-checks.md` "Shared-script sync checks"; `scripts/check_shared_sync.py` is a dormant manual drift inspector).

Run the checks appropriate to the target's `metadata.intended-audience`. **Load `references/tier-transition-checks.md` now** — it is the authoritative full spec for every gate below (output-key interpretation, the blocking rule, the structural-blocker lists, and per-check mechanics); the per-tier bullets here are the summary, and if the two differ, follow the reference.

**Frontmatter-validity gate (claude-users+ — runs first, blocking).** Before the tier-specific checks, run the deterministic frontmatter gate:

```bash
python3 ~/.claude/skills/skill-publisher/scripts/quick_validate.py <target>; echo "exit:$?"
python3 ~/.claude/skills/skill-publisher/scripts/portability_lint.py <target> --tier <tier> > /tmp/skill-publisher-lint-out.json; echo "exit:$?"   # canonical temp file the reuse rule below reads
```

**Capture exit codes:** the Bash tool does not preserve shell state across calls, so append `; echo "exit:$?"` to each command where the exit code drives a branch (e.g. `python3 … quick_validate.py <target>; echo "exit:$?"`). Read the `exit:N` line from stdout to determine pass/fail before acting on the output.
`portability_lint.py` prints JSON to the canonical temp file `/tmp/skill-publisher-lint-out.json` (reuse it for the per-tier check when the tier matches; re-run only on a mismatch). `quick_validate.py` signals pass/fail by exit code only. A finding blocks the target's own tier iff the authoritative tier is in `would_fail_at_tiers` ("blocks" = address in Step 5, not halt Step 4). Output-key and soft-warning interpretation: `references/step-details.md` "Step 4 gates".

A non-zero `quick_validate.py` exit is a **blocking TIER finding**; exit 3 = PyYAML not installed (environment gap — tell the user to `pip install pyyaml`, raise no cluster). `portability_lint.py` adds registration-correctness blockers (name == folder, no reserved prefix, no XML-shaped frontmatter, exact `SKILL.md`, plan-code leakage), each a TIER cluster at any shared tier. Full lists and the exit-1 disambiguation: `references/tier-transition-checks.md` "Frontmatter-validity gate".

- **`personal`**: skip Step 4 entirely (including the frontmatter gate).
- **`claude-users`**: reuse the portability JSON above, then run `link_check.py <target>` (broken links/unreadable files block; dead scripts advisory), the Cowork-compatibility check (`references/cowork-compatibility.md`), `attribution_lint.py` then `spdx_check.py <target>` (no `--require` here), `security_scan.py <target>` (`references/security-checks.md`; a non-empty `unreadable_files` means an incomplete scan) and `mcp_deps.py <target>`. Exit codes and finding→cluster rules: `references/step-details.md` "Step 4 gates"; `references/tier-transition-checks.md` wins on any conflict.
- **`model-agnostic`**: all `claude-users` checks plus `portability_lint.py --tier model-agnostic`, `compatibility: agentskills.io@1.0` verification and a user-confirmed cross-runtime install-surface note.


### Step 5 — Address findings

**Session-log marker (first action of this step):** `echo "**[$(date +%H:%M:%S)] SKILL:skill-publisher RUN:<skill> STEP:addressing**" >> "${HOME}/.claude/session-logs/session-log-$(date +%Y-%m-%d).md"` — substitute the actual target skill name for `<skill>`. Non-blocking. **Then replace in-flight marker**: write `in-flight:: <Runtime> addressing run-<N>` (replacing the Step 4 `tier run-<N>` marker in place, per atomic-write table).

**Before beginning cluster addressing:** verify `<target-intent>` is available in context. If not (compaction resume via recovery Rule B skips Step 1), or if in any doubt: re-read the target README.md `## Intent` section from disk, or use the target SKILL.md `## What this skill does` as fallback — re-reading from disk is always safe. Likewise verify `<N>` (the Run number) and `<Runtime>` are set; if a recovery-Rule-B resume skipped the Step 1 Capture block, re-derive `<N>` from the ledger's highest Run value (resuming the in-flight run keeps that number — see recovery-protocol.md "Run number determination") and recover `<Runtime>` from the in-flight marker's timestamp field (`in-flight:: <Runtime> addressing run-N`), or re-capture current UTC if the marker is unreadable — `<Runtime>` feeds the `--runtime` argument of every append. Rule B re-runs Steps 3-4 to rebuild the cluster set, which need inputs the bypassed target-read block normally captures: re-resolve the target SKILL.md path (from the invocation argument → `~/.claude/skills/<skill>/`, or the recorded path) and re-read the target's `metadata.intended-audience` tier before re-running those steps.

For every cluster in `<audit-gaps>` (Step 3) + `<tier-clusters>` (Step 4), decide and act — FIX (change the artifact), STRENGTHEN (artifact correct, add a WHY), or USER-PAUSE (intent-ambiguous — ask); **load `references/ship-checklist.md` now** for the full address-decision rules + the exact `append_ledger.py` row format + the three address-string forms. Use `<target-intent>`: a fix that would violate the README's Intent is a USER-PAUSE. Write one ledger row per addressed cluster — `scripts/append_ledger.py append <ledger> --runtime <Runtime> --round <N (the Run integer)> --phase <POLISH|AUDIT|TIER|PACKAGE|PR> --cluster <C#> --root-cause '…' --address '…' --flags '…'` (run `python3` as the literal command word). Then `scripts/append_ledger.py close-round <ledger> --round <N>` (run it even on a zero-cluster Run; if it exits non-zero, surface the error and pause before Step 6). **Do NOT canonicalize the run-comment yet** — the canonical `<!-- Run N total: … -->` form needs the version (Step 7) + PR URL (Step 9), so it is written at Step 10 (which recomputes the counts across all Run-N rows, since PACKAGE/PR rows are appended after this close). Full canonical-comment + Edit-replace mechanics: `references/ledger-format.md` "Run + invocation summary comments".

### Step 6 — Generate user-facing README sections

**Session-log marker (first action of this step):** `echo "**[$(date +%H:%M:%S)] SKILL:skill-publisher RUN:<skill> STEP:readme**" >> "${HOME}/.claude/session-logs/session-log-$(date +%Y-%m-%d).md"` — substitute the actual target skill name for `<skill>`. Non-blocking.

**Clear the in-flight marker** (per recovery-protocol.md atomic-write table: "cleared at Step 6"): remove the `in-flight::` line from the ledger header via Edit — this signals that steps 6–7 (README gen + version bump) are local edits, re-runnable if interrupted.

**Author the user-facing sections the publisher owns (cold agent — do this first).** The creator scaffolds `## What this skill does` / `## Intent` / `## When to use` / `## How to invoke`; the publisher **additionally authors** `## Features & modes` (the skill's capabilities + every invocation mode) and `## Structure` (the layout map) — the two derived sections a user needs to pick the right mode and orient themselves, which the scaffold lacks. **Load `references/readme-agent-prompt.md` now** and follow it: build its slots from the **final** SKILL.md (this run's polished version) + the bare `references/`/`scripts/` file-path list (paths only — the agent reads them and derives each role itself) + the current README, dispatch the cold `readme sections for <skill>` agent (`subagent_type` `general-purpose`; no recovery marker — Step 6 is re-runnable and the draft is idempotent), then apply its `FEATURES_AND_MODES` / `STRUCTURE` blocks in canonical order (after `## How to invoke`, before `## How to install` — **replace** them if a prior ship wrote them; they are derived, not hand-tuned) and add any `INVOKE_GAPS` modes to `## How to invoke`. **Never re-author** the creator's What-it-does / Intent / When-to-use. Runs on every full ship so the modes/structure stay in sync as the skill evolves.

Fill in the README placeholders skill-creator-ccvw left for the publisher:
- **`## How to install`** — per tier: `personal` → "installed locally"; `claude-users` → marketplace install command + manual `~/.claude/skills/` path; `model-agnostic` → per-runtime install commands. The install-command FORM keys on whether a resolvable upstream source URL exists — `author.history[].source`, or `inspirations[].source` as Step 9's fallback (GitHub-registry → `claude plugins install <org>/<repo>`; unknown registry → USER-PAUSE; none → manual path only). Full form-derivation, the GitHub-host parse, the unknown-registry USER-PAUSE + WHY, and the previously-published git-tag check (which feeds Step 7's changelog sourcing, not the install form): `references/packaging.md` "Install-command form derivation".
  - After a `claude plugins install <org>/<repo>` command is generated, probe it with `install_check.py` — a confirmed problem is a warning, never a ship-blocker: `references/step-details.md` "Step 6".
- **`## Sibling skills`** — from HISTORY.md `inspirations[]` (omit the section if empty), else ask the user; never invent a pairing description. Sourcing cascade: `references/step-details.md` "Step 6".

Together with the authored `## Features & modes` + `## Structure` above, these sections teach a new user **what the skill does, how to use it and in which mode, how it's laid out, how to install it, and what pairs with it** — the "polish it to also teach others" goal.

**Outcomes-first positioning (heuristic, not a gate).** Value-carrying README copy should lead with the outcome the user gets, not the mechanism; rewrite toward it, and add the MCP-plus-skill one-liner when the target pairs with an MCP server. Examples: `references/polish-pass.md` "Outcomes-first positioning"; full text: `references/step-details.md` "Step 6".

### Step 7a — Resolve upstream + diff against published state

**This resolution moved here from Step 9** so the changelog (Step 7) can diff against the published state and Step 9 reuses the result (never re-resolves, never re-clones). Resolve and carry forward `<upstream>` + `<repo-path>`:
- `<upstream>` = HISTORY.md `author.history[].source` (Category A), else `inspirations[].source` (Category B). **None recorded, or degraded mode (no HISTORY.md):** there is no published baseline — skip to Step 7's **no-published-state fallback** (ledger-only changelog). Do not dispatch the changelog agent.
- `<repo-path>` = the in-repo location of the skill (e.g. `plugins/<name>` / `skills/<name>`); same value Step 9 needs. If the layout is unknown, ask the user (once — carry it to Step 9).

**Write the in-flight marker** `in-flight:: <Runtime> changelog run-<N>` (the diff-clone + cold agent dispatch below are a state-changing step per the atomic-write table; recovery rule for `changelog` re-runs Step 7a — the clone + dispatch are idempotent/cheap). Then:

```bash
python3 ~/.claude/skills/skill-publisher/scripts/github_pr.py <target> --upstream <upstream> --repo-path <repo-path> --diff-only; echo "exit:$?"
```

It clones the upstream to a stable dir and prints `{clone_dir, published_path}` (exit 0), or `{no_published_state: true, ...}` (exit 0 — the skill isn't published at `<repo-path>` yet), or exits **2** on failure. Exit 2 has two sub-causes that take the **same action** (fall back to ledger-only and tell the user the diff was skipped): a clone failure prints an `{error}` JSON on stderr, while an argparse usage error (a missing `--upstream`/`--repo-path`) prints usage text and **no** JSON — do not depend on an `{error}` key being present on exit 2 (Step 7a always supplies both args, so the usage variant should not arise). **Capture `clone_dir` + `published_path` to your response text** — `clone_dir` feeds Step 7's diff; it is removed at Step 10 by its known path (Step 9 makes its own clone, it does not reuse this one). On `no_published_state` (or any exit-2 fallback), take Step 7's fallback. Otherwise run:

```bash
python3 ~/.claude/skills/skill-publisher/scripts/diff_published.py <target> --published <published_path> > /tmp/skill-publisher-diff.json; echo "exit:$?"
```

Exit 0 → the structured diff is in `/tmp/skill-publisher-diff.json` (feed it to Step 7's changelog agent). Exit 1 → `no_published_state` (fall back to ledger-only). Exit 2 → path error (fix and re-run, or fall back). Reusing the same `<upstream>`/`<repo-path>` at Step 9 means the PR step never re-asks.

### Step 7 — Version bump + changelog

**Session-log marker (first action of this step):** `echo "**[$(date +%H:%M:%S)] SKILL:skill-publisher RUN:<skill> STEP:version**" >> "${HOME}/.claude/session-logs/session-log-$(date +%Y-%m-%d).md"` — substitute the actual target skill name for `<skill>`. Non-blocking.

**Third signal — tracer audit fixes.** Run `python3 ~/.claude/skills/skill-publisher/scripts/tracer_changelog_rows.py <skill>`: exit 0 → its text block is the `[TRACER_LEDGER_ROWS]` slot; exit 1 (no tracer ledger) → the literal `none` (use `--ledger` if the skill was traced under another name). Details: `references/step-details.md` "Step 7".

**Changelog sourcing.** With a structured diff from Step 7a, dispatch the cold changelog agent per `references/changelog-agent-prompt.md` (**load it now**) and use its `ENTRY` + `final_bump`; with no published state, source from this run's ledger rows alone per `references/changelog-format.md`. Then remove any `changelog run-<N>` marker. Reconciliation rules: `references/step-details.md` "Step 7".

In HISTORY.md: increment `version` (bind `<prior>`, `<new-version>` and `<bump-type>` — the highest SemVer level any change warrants: patch fixes, minor new capability, major breaking), append the changelog entry per `references/changelog-format.md`, and set SKILL.md `metadata.parent-version` to `<prior>` (bare unquoted semver, or `pre-versioned`). Degraded-mode handling is in `references/changelog-format.md`; the full bump and idempotency rules: `references/step-details.md` "Step 7".

### Step 8 — Package for distribution (per tier)

**Session-log marker (first action of this step):** `echo "**[$(date +%H:%M:%S)] SKILL:skill-publisher RUN:<skill> STEP:packaging**" >> "${HOME}/.claude/session-logs/session-log-$(date +%Y-%m-%d).md"` — substitute the actual target skill name for `<skill>`. Non-blocking. **Then write in-flight marker**: write `in-flight:: <Runtime> packaging run-<N>` (the marker is absent after Step 6 cleared it — insert it fresh, per atomic-write table). **Important:** this `packaging run-<N>` marker is cleared by Step 9 on every path — if a PR is opened, Step 9 replaces it with `pr run-<N>` (cleared at Step 10); if no PR is opened, Step 9 clears the `packaging` marker before the no-PR exit. A stale `packaging` marker would cause the packaging-marker recovery (the `packaging` row of recovery-protocol.md's marker state-table) to re-fire Step 8 unnecessarily.

- **`personal`**: no packaging. Files stay in place.
- **`claude-users`** / **`model-agnostic`**: `python3 ~/.claude/skills/skill-publisher/scripts/package_skill.py <target> --tier <tier> > /tmp/skill-publisher-package-out.json`; read `packaged` (Step 10's `--artifact`) and `archive_sha256` (its `--expected-digest`) from it. Exit codes (model-agnostic adds exit 3 = conformance failure → PACKAGE cluster) and the Claude.ai zip route: `references/packaging.md`; full text: `references/step-details.md` "Step 8".
- **Unknown tier value**: if `metadata.intended-audience` is none of the three above, this is a blocking TIER finding — USER-PAUSE with the current field value; ask the user to correct it to one of `personal`, `claude-users`, or `model-agnostic` before packaging.

### Step 9 — PR to GitHub (if upstream origin)

**Session-log marker (first action of this step):** `echo "**[$(date +%H:%M:%S)] SKILL:skill-publisher RUN:<skill> STEP:pr**" >> "${HOME}/.claude/session-logs/session-log-$(date +%Y-%m-%d).md"` — substitute the actual target skill name for `<skill>`. Non-blocking. **Then handle the in-flight marker by path**: if a PR will be attempted (upstream origin recorded, not degraded mode), write `in-flight:: <Runtime> pr run-<N>` (replacing the `packaging run-<N>` marker in place, per atomic-write table). If no PR will be opened (no upstream or degraded mode), do NOT write a `pr run-<N>` marker — instead clear the `packaging run-<N>` marker now and proceed marker-free through the no-PR path. (WHY: a stray `pr run-N` marker would make recovery Rule D assume a PR was attempted and run `gh pr list`, which is wrong when no PR was ever started.)

**Reuse Step 7a's resolution.** `<upstream>` + `<repo-path>` were already resolved at Step 7a (the resolution moved there so the changelog could diff against the published state) — reuse those exact values here; do NOT re-resolve or re-ask. (Step 7a's `--diff-only` clone at `clone_dir` is removed at Step 10; the full PR below makes its own clone — re-cloning a shallow repo is cheap and avoids reusing a possibly-stale checkout.) If Step 7a was skipped (it ran only when an upstream existed), there is no upstream and this is the no-PR / no-upstream-hosting path below.

**Load `references/github-pr-workflow.md` now** and follow it — it owns the whole PR path: when-it-runs + the `<upstream>` precedence (Category-A `author.history[].source` then Category-B `inspirations[].source`, reusing Step 7a's resolution), the `github_pr.py` flow (branch → copy → commit → push → `gh pr create` → ship-tag), the required-argument invocation + how to fill `--body-file` from `assets/pr-template.md`, the full **Exit code reference** (exits 1–7, the argparse-vs-git exit-2 distinction, the `--dry-run`-overrides-`--confirmed` rule, the exit-5 post-push caution, `tag_warning`), the **license gate** before any public push, the **no-upstream hosting-branch** path, and the **mandatory source-recording invariant** — *no publish/PR push leaves the skill without an `author.history[].source` pointing at where it now lives* (so a PR to a new target with no recorded source records that target).

The orchestration decisions that stay here: write the `pr run-<N>` marker (above). `github_pr.py`'s **first invocation is always a dry-run** (`{"dry_run": true}`, no `pr_url`) — present that summary and **AskUserQuestion: Confirm PR / Cancel** (leave the `pr run-<N>` marker in place while awaiting the answer). **Marketplace choice (before the confirm question).** `github_pr.py` also registers the skill in the upstream `.claude-plugin/marketplace.json` (same commit) — without that entry `claude plugins install` cannot offer it. If the dry-run's `marketplace.state` is `needs_choice`, **AskUserQuestion** which plugin to join (existing / new / don't register) and re-run the dry-run with the matching `--marketplace-*` flag so the diff you show includes it; an unresolved choice on a confirmed push exits 7. Mechanics: `references/github-pr-workflow.md` "Marketplace registration". **On confirm:** re-run with `--confirmed` and WITHOUT `--dry-run`, then carry the returned `pr_url` to Step 10's `--pr-url`. **On cancel / decline / no-upstream:** clear the `pr run-<N>` marker (Edit out the `in-flight::` line — a stray `pr` marker misleads recovery Rule D), then take the no-PR path — for no-upstream/degraded, offer the hosting-branch per the reference; for a plain decline, report the Step-8 artifact path — and proceed to Step 10. Write PR-phase ledger rows (`--phase PR`) only if a real PR-phase issue occurred (auth/push/gh-create failure, or a USER-PAUSE).

### Step 10 — Present result

**Clear in-flight marker first** (per atomic-write table: `pr run-N` is cleared at Step 10): if an `in-flight::` line is present, remove it from the ledger header via Edit — the ship is complete from this point. (On the no-PR path, Step 9 already cleared the marker, so there may be none here — that is expected; treat an absent marker as a no-op, not an error.) (The Step-7a diff-clone is removed by this step's "Clean up temp artifacts" action below, by its deterministic path — so it is reclaimed even on a recovery resume that re-entered at Step 9.)

**Replace the run-summary comment with the canonical form** (version and PR URL are now known). Branch on what Run N already has: the canonical `<!-- Run N total:` line → leave it; the generated `<!-- Round N total:` line → recount the Run-N rows (do NOT re-run `close-round`, it would append a second comment) and Edit-replace it; neither → append the canonical line fresh. Recount rules: `references/ledger-format.md` "Run + invocation summary comments" and `references/step-details.md` "Step 10".

The canonical form (used by both the Edit-replace branch and the append-fresh branch above): `<!-- Run N total: <X> clusters — <F> FIX + <S> STRENGTHEN + <P> USER-PAUSE — shipped at tier <tier>, version <prior>→<new>, PR: <url-or-none> -->`. (Degraded paths: on attribution-declared path (a) with no prior version, write `version <new> (initial)`; on the full-skip path with no version at all, write `version n/a (degraded skip)`.) (`raw_flags` is intentionally omitted from this canonical Run comment — it summarizes clusters + address kinds, not raw flag counts; `raw_flags` lives only in the per-round generated comment.) Full mechanics: `references/ledger-format.md` "Run + invocation summary comments".

**Post-ship verification next.** Run `scripts/verify_ship.py` to confirm the ship actually landed:

```bash
python3 ~/.claude/skills/skill-publisher/scripts/verify_ship.py <target> --version <new-version> --parent-version <prior> --strict-changelog [--artifact <path>] [--expected-digest <archive_sha256>] [--pr-url <url>]
# exit 0 = all required checks passed; exit 1 = a required check FAILED — read the `required_failures` array from the JSON output and report each named failure to the user, then STOP without writing the ship manifest (a ship with known verification failures must not be recorded as landed — do not report success, do not proceed to the manifest write below); exit 2 = usage/argparse error — TWO causes: (a) --version missing, or (b) --artifact passed without --expected-digest (they are co-required — re-run Step 8 to capture archive_sha256); the stderr message names which. Re-run with corrected arguments.
```

It checks the new version, its changelog heading and Keep-a-Changelog categories/bump (`--strict-changelog`), the artifact's SHA-256 (`--expected-digest`, always for shared tiers; omit `--artifact` for personal) and that the PR resolves. A `NOTE: PR check unverified` on stderr is informational. A pre-versioned target skips only the bump check. Details: `references/step-details.md` "Step 10".

**Write the ship manifest** (after verify_ship passes — on EVERY ship path, including no-upstream and degraded). Record the durable ship facts for the lifecycle tools (Phase 4 status/rollback):

```bash
python3 ~/.claude/skills/skill-publisher/scripts/ship_manifest.py write <skill-name> \
  --version <new-version> --tier <tier> --timestamp <Runtime> \
  [--artifact <path>] [--digest <archive_sha256>] [--pr-url <url>] [--branch <branch>] [--tag <name>-v<version>] [--merge-strategy-unknown]
# writes ~/.claude/skill-publisher-ledger/<skill>.manifest.json; exit 0 ok; exit 2 usage (argparse); exit 3 I/O error (write failed)
```

Omit flags that don't apply (no artifact/digest for personal; no PR/branch/tag without a PR); use `--version n/a` on the full-skip degraded path and `--merge-strategy-unknown` when the upstream may squash/rebase. A manifest write failure (exit 3) is reported but does not un-ship. Degraded-skip verification and the render step: `references/step-details.md` "Step 10".

Render the ledger HTML with `render_ledger.py` (shared with skill-tracer; `--config @~/.claude/skills/skill-publisher/scripts/ledger-render-config.json` is required; pass `--open` to auto-open the rendered HTML). Run the skip checks first (skip if the ledger is absent or has no data rows), then render and relay the `Wrote HTML to <path>` line to the user. The invocation, skip-check commands, the `@`-prefix / `~`-expansion note, and the full exit-code handling (rendering is non-blocking — never block on a render failure) are in `references/ledger-format.md` "Rendering". In your response text, provide the user:
- Install commands (marketplace + Claude Code + Cowork + cross-runtime, per tier)
- PR URL (if generated)
- The changelog entry just appended
- Summary of polish edits + audit findings + tier-checks that ran and passed
- File-changes summary

**Clean up temp artifacts** (tmp-file hygiene — do this on every Step-10 exit path): remove Step 7a's diff-clone and the temp diff/package files: `rm -rf "$(python3 -c 'import tempfile,os; print(os.path.join(tempfile.gettempdir(), "skill-publisher-diffclone-<name>"))')" /tmp/skill-publisher-diff.json /tmp/skill-publisher-package-out.json 2>/dev/null` (substitute the bare `<name>`). A missing path is a no-op.

Publisher is terminal — no "suggested next". The skill is shipped.

---

## References

Each file is loaded or run at the step that names it. Annotated index: `references/step-details.md` "File index".
- References: `references/readiness-gates.md`, `references/ship-checklist.md`, `references/tier-transition-checks.md`, `references/cowork-compatibility.md`, `references/audit-prompt.md`, `references/polish-pass.md`, `references/security-checks.md`, `references/github-pr-workflow.md`, `references/changelog-agent-prompt.md`, `references/readme-agent-prompt.md`, `references/packaging.md`, `references/changelog-format.md`, `references/recovery-protocol.md`, `references/ledger-format.md`, `references/glossary.md`, `references/lifecycle.md`
- Scripts: `scripts/readiness_report.py`, `scripts/diff_published.py`, `scripts/tracer_changelog_rows.py`, `scripts/github_pr.py`, `scripts/marketplace_register.py`, `scripts/package_skill.py`, `scripts/render_ledger.py`, `scripts/spdx_check.py`, `scripts/security_scan.py`, `scripts/mcp_deps.py`, `scripts/link_check.py`, `scripts/triggering_eval.py`, `scripts/install_check.py`, `scripts/frontmatter_util.py`, `scripts/verify_ship.py`, `scripts/ship_manifest.py`, `scripts/ship_status.py`, `scripts/check_shared_sync.py`, `scripts/sync_shared.py`, `scripts/{quick_validate,portability_lint,attribution_lint}.py` (`check_shared_sync.py` and `sync_shared.py` are dormant manual tools, not part of the ship flow).

**Sibling skills**: `skill-creator-ccvw` (build phase — scaffolds the structure publisher reads), `skill-tracer` (trace phase — finds bugs before ship), `marketplace-discover` (catalog the publisher PRs back to).
