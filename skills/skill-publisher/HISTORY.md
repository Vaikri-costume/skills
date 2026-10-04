---
version: "1.4.0"
category: B
parent-version: "1.3.0"
author:
  primary: "Vaikri-costume"
  # Single self-referential "original" entry: the publisher's source-recording convention
  # (references/github-pr-workflow.md) so the next ship knows where to PR. Not a fork chain.
  history:
    - role: "original"
      name: "Vaikri-costume"
      skill: "skill-publisher"
      license: "MIT"
      version: "1.0.0"
      date: "2026-05-30"
      source: "https://github.com/Vaikri-costume/skills"
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

### 1.4.0 — 2026-10-04 (shipped)
#### Added
- Marketplace registration: new `scripts/marketplace_register.py`; `github_pr.py` now lists the skill in the upstream `.claude-plugin/marketplace.json` in the same commit as the skill copy (a skill already listed is left alone, a repo without a catalog is skipped). The orchestrator asks which plugin to join. Flags `--marketplace-plugin`, `--marketplace-new-plugin` + `--marketplace-description`, `--no-marketplace`; dry-run and result JSON report `marketplace.state`; new exit 7 when the choice is unresolved on a confirmed push. Documented in `references/github-pr-workflow.md` and the `### Marketplace` block of `assets/pr-template.md`.
- Lifecycle modes: `--status [--repoint-tag]` (`scripts/ship_status.py`), `--rollback` (pre-ship snapshot restore, archive delete, PR close) and `--docs-only`, specified in `references/lifecycle.md`; plus the `--readiness` exit and the opt-in `--triggering-eval --eval-set` measured eval.
- Skill-tracer audit fixes are a third changelog signal via `scripts/tracer_changelog_rows.py`; the bump is `max(agent_bump, ledger_bump, tracer_bump)`.
- Cold README agent (`references/readme-agent-prompt.md`) regenerating `## Features & modes` and `## Structure` every ship.
- `references/step-details.md` (SKILL.md detail moved out verbatim, plus an annotated file index) and a `LICENSE` file.
- `attribution_lint`: `author.primary` is checked against the `gh`-authenticated login. A mismatch is blocking; a missing or unauthenticated `gh` is advisory only.
#### Changed
- SKILL.md trimmed from about 9,500 to about 6,200 words with no behavior change (deduplicated rules; Step 4, 6, 7, 8 and 10 detail moved to `references/step-details.md`).
- README: install section now gives the marketplace add/install commands and a manual path (it wrongly said personal-tier/unpublished); gained Features & modes, Structure and the missing modes under How to invoke.
- `package_skill.has_claude_extensions` uses all 7 canonical `portability_lint` patterns; `spdx_check` and `mcp_deps` delegate frontmatter parsing to `frontmatter_util`; `readiness_report` tolerates a quoted `source:` URL; `render_ledger`'s not-found message and `tracer_changelog_rows` use the XDG data path for the tracer ledger.
- `cowork-compatibility.md` marks its table as the closed set of adaptation points.
#### Removed
- `scripts/check_vendored_sync.py`, a maintainer-only sync check used by no documented publisher step (grade-candidates and mine-sources carry their own copies). `check_shared_sync.py` and `sync_shared.py` remain.
#### Fixed
- `ship_status.check_catalog` mishandled the `v` in `<name>-v<ver>` refs and reported a current catalog as stale.
- `verify_ship`'s changelog-entry terminator was asymmetric (`\s+` vs `\s*`) and over-ran into the next version block.
- `github_pr.py`'s docstring, comment and `--diff-only` note (and SKILL.md's clone_dir note) wrongly said Step 9 reuses the diff clone; `gh pr create` now reuses an existing open PR on a resume instead of duplicating it.
- `render_ledger` bucketed a blank Run cell into a phantom round 0, dropped 6-column pre-Phase rows and wrote `--output ~/x.html` to a literal `~` directory; `append_ledger`'s docstring now uses the "Run" label and no longer cites a non-existent `ledger_state.py`.
- `spdx_check` and `mcp_deps` hand-rolled frontmatter scans that parsed a BOM/CRLF SKILL.md as empty.
- `quick_validate` exited 1 on missing PyYAML, indistinguishable from invalid frontmatter; it now exits 3 (documented in Step 4 and `readiness-gates.md`).
- `changelog-format.md` carried a stale 2-term bump formula; `readiness-gates.md` omitted the `link_check` unreadable → RED outcome; `glossary.md` described only one degraded-mode sub-path.
- `recovery-protocol.md`: the no-marker inference was false on the degraded-skip path, and Rule B wrongly re-ran the cold audit in docs-only mode.
- SKILL.md Step 10 documents both `verify_ship` exit-2 causes, branches on which run-summary comment form exists before editing, and stops without writing the manifest on a failed verification; Step 7 notes the tracer-ledger name-mismatch case; Step 1/2 wording ambiguities fixed; path placeholders are double-quoted (zsh word-splitting).

### 1.3.0 — 2026-06-22 (shipped)
#### Added
- Readiness mode: `readiness_report.py` aggregates the cheap deterministic gates into a read-only green/yellow/red pre-ship verdict (`--readiness` / `readiness` invocation), with no ledger writes or version bump.
- `link_check.py` internal-link integrity gate (broken links, dead scripts, unreadable files), wired into the Step-4 tier checks and readiness mode.
- Content hashing end-to-end: a shared `hashutil.py` streaming SHA-256, a per-file `SHA256SUMS` manifest packaged inside each `.skill` archive, and a `verify_ship.py --expected-digest` re-hash that fails the ship if the artifact on disk is not byte-for-byte the one packaged.
- `ship_manifest.py` writes a durable ship manifest recording what landed (for the Phase-4 lifecycle tools).
- Diff-driven changelog: `diff_published.py` plus `github_pr.py --diff-only` (a read-only clone of the published state) feed a cold changelog agent that reconciles the structured diff against the run's ledger rows into a Keep-a-Changelog / SemVer entry.
- `triggering_eval.py` description-quality confidence heuristic plus an opt-in measured-accuracy run that delegates to skill-creator-ccvw's `run_eval.py`.
- `install_check.py` verifies the derived install command's target (repo reachability + marketplace-catalog presence), degrading to "unverified" offline.
- `frontmatter_util.py` and `sync_shared.py` shared helpers; `references/readiness-gates.md` documents the readiness gate set.
#### Changed
- Progressive-disclosure refactor of SKILL.md: 13 self-contained blocks of step mechanics moved out of SKILL.md into the reference files each step already loads (recovery-protocol, github-pr-workflow, ship-checklist, tier-transition-checks, ledger-format, changelog-format, audit-prompt, changelog-agent-prompt), leaving followable pointers — bringing SKILL.md from ~10,800 to ~8,350 words.
- Polished SKILL.md + README.md prose (source-precedence and per-tier portability redundancies, small verbosity); added an explicit negative-trigger boundary to the description.
- `recover_dispatch.py` now recovers either cold dispatch — the Step-3 audit or the Step-7 changelog proposal — selected by `--kind`, sharing one scan core.
- The dormant shared-script drift-inspection tool was reworked from `check_vendored_sync.py` into `check_shared_sync.py` (part of the sync-contract retirement) — inspection-only, not in the ship flow, so no user-facing capability is removed.
#### Fixed
- Correctness and trace fixes across the scripts: explicit UTF-8 encoding on ledger/scan file I/O, an `append_ledger.py` row-regex widened to tolerate alphanumeric phase tokens, `skill-tracer`→`skill-publisher` docstring corrections, and stale `check_vendored_sync.py` references updated to `check_shared_sync.py`.
#### Security
- `security_scan`: reworded an in-prose `eval (` reference so it no longer trips the scanner's own regex (a false-positive self-flag).

### 1.2.0 — 2026-06-20 (shared-script sync contract RETIRED)
The three sibling skills (skill-creator-ccvw, skill-tracer, skill-publisher) had kept five scripts in sync across copies (`quick_validate`/`portability_lint`/`attribution_lint` with creator; `render_ledger`/`append_ledger` with tracer). After they deviated significantly in practice, the contract is **retired** — each skill now owns its **independent** copy and may freely diverge.
- **Ship flow:** removed the Step-4 "verify shared scripts are in sync" gate; the `references/tier-transition-checks.md` "Shared-script sync checks" section now records the retirement (no Step-4 action for shared scripts).
- **`check_shared_sync.py`:** kept but **dormant** — a manual drift-*inspection* tool only; its docstring, internals, and DRIFT message now state divergence is expected and not a finding (per the user's "headers + docs only" choice — the script was not deleted).
- **Docs/headers:** the 4 vendor-header docstrings (quick_validate/portability_lint/attribution_lint/render_ledger), the SKILL.md reference notes, the `render_ledger` internal "byte-for-byte" comment, and skill-creator-ccvw's SKILL.md shared-scripts note all reframed from "peer copies / latest-and-better / keep in sync" → "independent copy, may diverge, no sync." (Supersedes the 2026-06-20 skill-creator-ccvw 1.0.2 "latest-and-better peers" reframe.)

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
