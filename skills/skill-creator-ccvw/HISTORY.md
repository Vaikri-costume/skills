---
version: "1.2.0"
category: A
parent-version: "1.1.1"
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
      source: "https://github.com/Vaikri-costume/skills"
inspirations: []
---

# History — skill-creator-ccvw

## Changelog

### 1.2.0 — 2026-08-17 (shipped)
#### Added
- `attribution_lint.py`: new `lint_author_identity` check verifies HISTORY.md's `author.primary` against the gh-authenticated GitHub username; blocking on mismatch, advisory when `gh` is unavailable.
- `run_eval.py`: pre-flight credential/CLI check before the eval suite runs, so environment failures no longer masquerade as 0% trigger recall.

#### Changed
- README.md: added Features & Modes and Structure sections; rewrote How to Install to reflect claude-users tier and its actual published location (Vaikri-costume/skills); closed several How to Invoke gaps.
- `references/schemas.md`: added a table of contents (467 lines, previously none).
- `references/ccvw-glossary.md`: reorganized shared-vocabulary entries (added "altitude", updated "Phase", removed several stale entries) to reflect current cross-skill terminology.
- Explicit UTF-8 encoding added to file reads/writes across most scripts and the eval viewer (Windows-portability robustness).

#### Fixed
- SKILL.md `metadata.parent-version` corrected to match HISTORY.md (was stale at 1.0.0).
- Pre-handoff self-check no longer false-positives on citations that legitimately name a sibling skill's own reference file.
- `run_eval.py`: isolated per-run tempdir for the synthetic command file (no longer collides with concurrent sessions' live `.claude/commands/`); stderr now drained concurrently to prevent a pipe-buffer deadlock; genuine CLI errors now raise instead of being scored as "did not trigger".
- `run_loop.py`: a crash inside `improve_description` now exits the loop gracefully with partial results saved, instead of crashing the run.
- `generate_review.py` / `viewer.html`: fixed prompt/eval_id extraction and sorting to handle missing/`None` eval_id correctly.
- `improve_description.py`: `char_count`/`over_limit` now recomputed against the final description rather than a stale pre-rewrite value.
- `package_skill.py`: excludes `.git` when packaging a skill archive.
- `utils.py`: resolves the `claude` binary via `shutil.which` (fixes Windows npm-shim invisibility) and strips a leading UTF-8 BOM from SKILL.md.
- `portability_lint.py`: skill ledger paths (`skill-tracer-audit-ledger`, `skill-creator-evals-ledger`) are now flagged as user-data paths at claude-users+ tier (reverses a prior deliberate exclusion).
- HISTORY.md: fork-adapter `author.history` entry now records `source: https://github.com/Vaikri-costume/skills` — its actual current home since the Run 1 PR — closing a gap where the mandatory source-recording invariant had never been satisfied.

### 1.1.1 — 2026-08-11 (upstream re-audit: 2 real bug fixes, 1 confirmed-already-ahead, Windows compat declined)
Live-upstream diff (fetched `anthropics/claude-plugins-official` raw files directly, not the 29-day-stale local marketplace cache) plus a GitHub issue sweep across every shared script/agent file, prompted by a real need: tuning `markdown-graph-manager`'s trigger description via `run_loop.py`.
- **`aggregate_benchmark.py` delta-sign fix (FIX).** `configs[0] - configs[1]` computed the improvement/regression delta off `sorted(eval_dir.iterdir())` alphabetical order, so the sign silently flipped depending on which config name happened to sort first — confirmed present in our fork, matching still-open upstream issue #1222. Fixed via name-based matching (`with_skill`/`new_skill` = primary, `without_skill`/`old_skill` = baseline) instead of positional indexing, with a printed stderr warning + alphabetical fallback for unrecognized config names. Verified against the exact scenario from the issue (old_skill better, with_skill worse: now correctly reports `-0.40`; the old positional code reported `+0.40`, i.e. an improvement misreported as a regression). SKILL.md's two prose sections documenting this as a "just read the means, don't trust the sign" workaround updated to reflect that recognized names now get a reliable sign.
- **`utils.py`/`run_eval.py` Windows-portability fixes (FIX, from upstream issue #1850, applicable — not Windows-only in effect since they're no-ops on POSIX).** Added `claude_binary()` (`shutil.which("claude") or "claude"`) so subprocess dispatch resolves through PATHEXT; wired into both `run_eval.py` call sites. `parse_skill_md` now opens with `encoding="utf-8-sig"` instead of `"utf-8"` so a leading BOM (some editors/OneDrive prepend one) doesn't break the frontmatter `---` split.
- **NOT applied: `select.select()`-on-Windows-pipes fix (#1850 bug 4).** The issue's proposed patch (readline-based, stdout-only) would have been a regression for us — it drops the concurrent-stderr-drain deadlock prevention already in this fork (see 1.0.3's `run_eval.py` history). A proper cross-platform replacement (thread+queue, preserving stderr-drain) was attempted but blocked twice by the Claude Code auto-mode permission classifier specifically on the "spawn threads reading raw subprocess file descriptors" pattern (isolated via smaller test edits — not a size issue). A partially-applied blocked edit briefly left `run_eval.py` with `select.select()` called but `select` unimported — a live `NameError` waiting on the first eval query; caught via `py_compile` before it shipped, reverted cleanly. Left unfixed: genuinely Windows-only impact, and this fork has no Windows users today. Revisit if that changes.
- **Confirmed ALREADY AHEAD of upstream (audit finding, no code change needed): worker-isolation / cross-session leak (issue #1749).** Upstream's `run_eval.py` writes each `ProcessPoolExecutor` worker's synthetic command file into a *shared* `project_root/.claude/commands/` (via `find_project_root()`, which the issue shows commonly resolves to `$HOME` under the documented invocation pattern) — causing both cross-worker trigger-detection corruption (~1/N apparent recall regardless of real description quality) and synthetic skill definitions leaking into unrelated concurrent Claude Code sessions as an apparent prompt-injection signature. This fork already isolates every worker into its own fresh `tempfile.mkdtemp()` (`eval_root`, `command_file`, and the subprocess `cwd` all scoped inside it, cleaned up via `shutil.rmtree` in `finally`) — exactly the issue's "suggested fix option 1," already implemented, predating this audit. Confirmed no pollution from a live `--num-workers 4` test run (no stray `~/.claude/commands/` files, no lingering tempdirs).
- **Confirmed already absorbed: #1523 "drop ANTHROPIC_API_KEY requirement"** (the most recent real upstream commit, 2026-04-23) — no `ANTHROPIC_API_KEY` reference remains in either fork or live upstream.
- **Declined: `package_skill.py` emoji/cp1252 crash (#1863, Windows-only).** Confirmed present (📦/✅/🔍/❌ prints crash on Windows' default cp1252 stdout codec) — not fixed, same Windows-only-impact reasoning as the `select.select` item above.
- **Endorsement check methodology note.** Checked reactions/comments across ~21 tracked upstream issue numbers via `gh api`; engagement is uniformly very low (max 2 reactions, mostly 0 comments, no linked PRs anywhere) — "community endorsement" is not a meaningful signal in this repo right now. The one substantive lead (#1749's cross-pollination/leak finding) came from actually reading a reply's technical content, not from reaction/comment counts. Don't gate a patch decision on engagement metrics here; read the actual report.

### 1.1.0 — 2026-08-10 (incremental-checkpointing requirement for multi-stage workflows)
- **New required checklist item.** Multi-stage workflow/skill designs (Pattern 1 "Sequential workflow orchestration" and Pattern 2 "Multi-MCP coordination" in `references/skill-writing-style.md`) must now name a durable write/log point after each stage — or after each unit within a stage, for stages processing many items — before advancing to the next stage. A design that defers all output to a single final report step is now a structural defect the pre-handoff self-check flags and fixes, not a style note.
- **Why:** a separate CCVW constitutional-governance-scoring workflow was designed so "you will see nothing until the final report is complete" (all output deferred to a final Stage 7 report). Context exhaustion mid-process — routine in long sessions, not an edge case — discarded all unwritten work every time, forcing 8 full session-restart cycles with zero usable output each time. A second, independent CCVW workflow-design session hit the identical failure shape separately.
- **Where it landed:** Pattern 1/2 skeletons + key-technique lines now name incremental checkpointing explicitly; a new "Incremental checkpointing" bullet added to "Cross-cutting authoring guidance" (distinct from the existing compaction-recovery bullet — that lets the *skill* resume its own execution, this ensures the *user* has real accumulating output); the Pre-handoff self-check content checklist in SKILL.md now has a checked item requiring this for any multi-stage workflow, with an explicit instruction to flag and fix designs that defer all output to a final step.

### 1.0.5 — 2026-08-04 (baseline-isolation gap in the eval ablation)
- **Step 1's baseline dispatch relied on instruction alone.** "No skill at all" / "point at the snapshot" told the baseline subagent not to use the skill, but it kept full filesystem access (Read/Glob/Bash/Skill/ToolSearch) for the whole run, so nothing stopped it from browsing `~/.claude/skills/`, grepping the skill's name, or invoking the Skill tool directly — silently invalidating the with-skill/baseline delta. Checked whether a structural fix (sandboxed dispatch, or independent transcript verification) was feasible: dispatched subagents leave no independently-inspectable tool-call record for the orchestrator (the parent session JSONL only logs the Agent dispatch + final return, per `references/jsonl-format.md`'s model), and switching to Workflow's per-agent journal.jsonl would break the explicit Agent-tool/Cowork-compatibility requirement this section states. Landed the best available mitigation instead: hard "do not touch `/skills/`, the skill name, or `SKILL.md`" constraints added to the baseline dispatch prompt, a required self-reported `## Isolation Check` path list in `transcript.md`, and a mandatory orchestrator grep of that transcript before trusting the comparison (discard + redispatch on any hit). Documented explicitly as harm-reduction, not a guarantee, since it is still self-report based.

### 1.0.4 — 2026-06-20 (shared-script sync contract retired)
- The lint scripts (`quick_validate`/`portability_lint`/`attribution_lint`) are no longer kept in sync with skill-publisher's copies. SKILL.md's shared-scripts note reframed from "peer copies, latest-and-better wins, propagate to publisher" → "this skill's own independent copies; may freely diverge; no sync." (Supersedes the 1.0.2 "latest-and-better peers" reframe. Full record in skill-publisher 1.2.0.)

### 1.0.3 — 2026-06-20 (code bugs found by skill-tracer `--code-review`, round 36)
First run of skill-tracer's new `--code-review` mode (nine cold lenses over the bundled `.py` as code) found 7 clusters from 9 raw flags; all addressed:
- **`generate_report.py` empty-history `max()` crash (HIGH)** — `generate_html` called `max(history,…)` unguarded, so the `--max-iterations 0` degenerate path still crashed with `ValueError` *one frame above* the run_loop guard added in 1.0.2. Guarded. (Found independently by 3 lenses.)
- **`generate_review.py` `build_run` eval_id overwrite** — the metadata-discovery loop broke only on a truthy `prompt`, overwriting a valid `eval_id` from a prompt-less candidate with a later `None`. Now keeps the first truthy prompt and first non-None eval_id independently.
- **`run_eval.py` vestigial `triggered`** — after the detection rewrite, `triggered` was init-False-never-set dead code; removed it, `return False` at both terminals.
- **`improve_description.py` stale `over_limit`** — computed pre-rewrite, never recomputed after the shorten branch; now recomputed on the final description.
- **`aggregate_benchmark.py runs_per_configuration`** (STRENGTHEN) — documented that `max(per-config)` overstates a config with fewer valid runs.
- **De-duplication** — `CLAUDECODE` env-strip → one `utils.claude_subprocess_env()` helper (FIX, 3 sites); the 1024-char limit's deliberate cross-validator duplication documented (STRENGTHEN — single-homing would couple the pure-stdlib/vendored validators).

### 1.0.2 — 2026-06-20 (run_eval triggering-detection fix + upstream community bring-ins + description trigger phrasings)
- **`run_eval.py` triggering detection no longer bails on the first non-Skill tool.** The old `else: return False` (plus the assistant-message early-return) scored a query "not triggered" the instant the model's first action wasn't `Skill`/`Read` — so under any global CLAUDE.md that calls `AskUserQuestion` first (or a model that `Bash`-greps before consulting), EVERY query scored non-trigger and the Description Optimization loop measured **0% recall for all descriptions**. Detection now scans to the `result` event, counting a trigger whenever the skill is consulted. This is Anthropic PR #1208's fix (= open #1323), which had never landed in CCVW. Load-bearing: without it the whole optimizer is unusable in any clarify-first environment.
- **Bring-ins from the live upstream open-PR queue** (community fixes absent from the frozen v1.0.0 base): `eval_id=None` sort-crash guard in `generate_review.py` + `viewer.html` (#1316); `preflight_check` + surfacing non-zero `claude -p` exits as errors instead of a silent "didn't trigger" in `run_eval`/`run_loop` (#1186); isolate trigger-eval command files into a throwaway tempdir so concurrent sessions never see the synthetic variant (#1261, merged with CCVW's real-`skill_name` naming); `analyzer.md` "unblids"→"unblinds" typo (#1184). The merged base upstream (local marketplace + live `anthropics/skills`) is otherwise **frozen at the v1.0.0 fork point** (last content commit 2026-03-06) — do NOT merge it back; it would regress the run_eval naming fix, dynamic `runs_per_config`, and the schemas.
- **Description trigger phrasings widened** to fix under-triggering: added "improve / upgrade / iterate on an existing skill; plan a skill upgrade or improvement" + literal phrasings ('plan a skill upgrade', 'skill improvement', 'make this skill better/smarter', 'add features to a skill'); compressed the feature-blurb middle to stay ≤1024.
- **Finding — auto-trigger reliability is governed by *self-servability*, not "meta-skill" category.** Measured with the fixed harness at low concurrency, reproduced 3×: skill-creator-ccvw caps at **~17% recall** because Claude self-serves on "edit my skill X" (it just opens and edits the files); skill-tracer hits **100% recall** (all_passed, iteration 1) because the cold-parallel trace methodology is not self-servable. No wording beats the self-servable ceiling — explicit invocation (`/skill-creator-ccvw`) is the reliable lever; the description fix still helps the build-from-scratch cases it can.
- **Shared lint scripts** (`quick_validate`/`portability_lint`/`attribution_lint`) reframed as **peer copies with skill-publisher (latest-and-better wins)**, not canonical/vendored.

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
