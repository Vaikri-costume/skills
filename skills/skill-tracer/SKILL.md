---
name: skill-tracer
description: "Cold-parallel trace of any skill via three direction agents (forward, backward, executor) reading the target independently — forward verifies claims against reality, backward verifies producer outputs have documented consumers, executor verifies the line-by-line path is unambiguous. The orchestrator collects ISSUE reports, applies considered fixes preserving the skill's intent, and re-dispatches cold until all three return clean (Condition A). The TRACE phase of the build → trace → ship ecosystem — correctness only; it does NOT polish prose, check portability, audit CCVW compliance, or run a simplify pass (those are skill-publisher's). Use whenever the user wants to trace, audit, check, review, or validate a skill — 'trace skill X', 'audit X for issues', 'is skill X clean', '/skill-tracer' invocations, or proactively after the user just created or edited a skill. Defers to feature-dev when the target is mid-feature-development."
license: MIT
compatibility: Claude Code 2.0 or newer
metadata:
  tier: claude-users
  created: "2026-05-27"
  created-by: Vaikri-costume
  parent-version: 2.1.0
  intended-audience: claude-users
allowed-tools:
  - Agent
  - Read
  - Edit
  - Write
  - Bash
  - Skill
  - mcp__scheduled-tasks__create_scheduled_task
---

<!-- Provenance, version, attribution chain, and changelog live in HISTORY.md.
     Human-facing intent + how-to-install + sibling skills live in README.md.
     This frontmatter holds only the runtime contract the executor loads at startup. -->

# skill-tracer

## What this skill does

Finds bugs and inconsistencies in any skill by reading it cold from three independent directions, one round:

- **Forward** — starts from each claim in SKILL.md and works to the reality it points at (does the script emit that format? does the referenced step exist?).
- **Backward** — starts from each script output / brief output format and works back to find the consumer (does some step read this value? does it cover every case?).
- **Executor** — reads line-by-line as the executor would, asking at every line whether the action is unambiguous from text already read.

After dispatch, the orchestrator collects ISSUE blocks from all three reports, considers each against the target skill's documented intent, applies surgical fixes that preserve intent (or pauses for the user when intent is unclear), and re-dispatches all three cold. The loop continues until all three return clean in one cold round (**Condition A**). That's convergence — skill-tracer is correctness-only.

**Round-1 code-review pass (new skills only).** On round 1 of a brand-new trace — and on the first round of a re-trace of a skill updated since it last converged — skill-tracer runs one full-depth local pass of the sibling [`code-review`](#references) skill (`/code-review max`, no issue cap) over the **whole skill**, as the **first phase of round 1** *before* the cold agents dispatch. Its findings go through the same considered-fix gate and are recorded in the ledger as `REVIEW`-phase rows in that same round; then the cold trace runs in the second phase of the round. Step 2.5 has the trigger + flow. (At convergence, Step 9 suggests running `/code-review` once more as a final local pass.)

**Not skill-tracer's job** (moved to other phases of the build → trace → ship ecosystem): prose polish / simplify pass, portability checks, CCVW Word/Spirit audit, attribution validation, security scan — those are skill-publisher's (ship phase). Efficiency + accessibility quality checks — those are skill-creator-ccvw's (build phase). skill-tracer finds bugs; it does not do quality or release work.

---

## When to invoke

- Slash command: `/skill-tracer <skill-name>` (or `/skill-tracer <absolute-path-to-skill-directory>`)
- Natural language: "trace skill X", "audit X for issues", "check skill X", "is skill X clean", "review skill X", "validate skill X"
- **Proactively** after the user just created or significantly edited a skill — offer to run a trace.
- **Audit fixes**: "audit skill fixes for X", "check the fix quality on X", "did X's fixes actually land" → the `--audit-fixes` diagnostic mode (checks whether ledger-recorded fixes since last convergence truly landed; see `references/audit-fixes.md`).
- **Mid-feature-development skills**: defer to feature-dev first. If the skill has commits in the last hour or the user says "I'm still building this", suggest feature-dev's explore → architect → implement → review pipeline; re-invoke skill-tracer once the skill is structurally complete. Tracing mid-development flags work-in-progress as defects, costing rounds feature-dev would resolve more cheaply.

After convergence, skill-tracer suggests `/skill-publisher <skill>` (the ship phase) — that's where polish + portability + CCVW audit + PR live.

---

## Prerequisites

The target skill must exist as a directory containing at least a `SKILL.md`. The orchestrator needs `Read`/`Edit`/`Write` on every file in the tree, `Agent` for parallel cold dispatch, and `Bash` for file enumeration. No external services. No network.

<!-- "CCVW" is an intentional unexpanded label naming the skill-creator-ccvw ecosystem. Treat as a proper noun; expansion reserved for a later public release. -->

---

## Runtime constraint — top-level invocation only

skill-tracer requires `Agent` to dispatch the three cold-parallel trace agents (Step 4). `Agent` is available only in the **top-level** Claude session — never from inside a nested Agent call. If the orchestrator detects it's a subagent (Agent unavailable), stop and tell the user; do not simulate. The full rationale + the exact abort message live in `references/recovery-protocol.md` "Runtime constraint — top-level invocation only".

---

## The four invariants

1. **Cold-trace.** Each agent dispatch is independent — no sibling mentions, no fix-log carry-over, no "what changed since last round" preamble, **no target README or HISTORY**. The cold agents read SKILL.md + scripts + references for correctness; they never see the target's intent docs. Cold means cold. (This is the adversarial-verify pattern `deep-research` and `pr-review-toolkit` use; cold parallelism is its structural enforcement.)
2. **Considered-fix.** Between rounds, the orchestrator weighs each ISSUE against the target skill's documented intent (read from the target's README `## Intent` — orchestrator-side only) and load-bearing decisions. A fix is applied only when it preserves intent. Random "make the tracer happy" fixes are forbidden — they destroy the skill's design.
3. **No-orphan-flag.** Every ISSUE is addressed by FIX, STRENGTHEN, or USER-PAUSE — and the address must land inside the skill, not an external log. If a future cold round re-raises a previously addressed ISSUE, the address was incomplete — investigate and strengthen further.
4. **WHY-strengthening.** When an ISSUE flags a missing WHY for an intentional design decision, the fix is to **add the WHY**, not to remove the rule. Most common operational form of invariant 3.

---

## Invocation modes

| Mode | Invocation | What runs (the **loop body**; Steps 1–2 — and, for full-convergence, Step 2.5 — always run first, per the note below) |
|---|---|---|
| **Full-convergence** (default) | `/skill-tracer <skill>` or natural language | Full loop: Steps 3–8 until Condition A (all three agents return clean in one cold round), then Step 9 |
| **Single-round** | `/skill-tracer <skill> --one-round` | One cold round through Steps 3–7 (round-close runs), then Step 9 — then stop. Diagnostic snapshot; no loop-back. |
| **Verify-only** | `/skill-tracer <skill> --verify-only` | One cold round through Steps 3–7 (round-close runs), then Step 9, applying **no fixes** — produces a ledger of would-FIX / would-STRENGTHEN / would-USER-PAUSE addresses; no loop-back. |
| **Audit-fixes** | `/skill-tracer <skill> --audit-fixes` | **No trace.** Dispatches one cold audit agent to check whether the fixes recorded in the ledger **since the last convergence** actually landed properly (vs light-touch / band-aid / not-really-fixed / regressed). Read-only — reports the per-finding classification, applies no fixes, writes no rows. Full spec: `references/audit-fixes.md`. |

(All four modes run **Steps 1–2 first** — Step 1 recovery + Step 2 enumeration are entry-universal, on every invocation. **Full-convergence additionally runs the conditional Step 2.5** (round-1 code-review pass) as the first phase of round 1, before Step 3, when its trigger holds; the other three modes skip Step 2.5. The code-review phase and the cold trace share round 1 — it is not a separate round. **Audit-fixes** then skips the cold-trace loop entirely (Steps 3–8): after Steps 1–2 it dispatches the single audit agent per `references/audit-fixes.md` and reports.)

---

## Workflow

*Whenever any script invoked below exits **non-zero** — OR returns exit 0 with a **JSON content-signal** the step says to act on (the one such case: `check_drift.py` exit 0 with a non-empty `unparseable` list) — consult the **"Script error-handling contract"** section (near the end of this document). The steps below describe each script's success path; that section is the executor's uniform rule for every non-zero exit plus that one exit-0 content-signal.*

### Step 1. Resolve target and mode — read intent — check for in-flight recovery

**Mandatory first action of every invocation**, including post-compaction resume. (Compaction: Claude Code's automatic context compression when the window fills — it restarts the session, requiring all state to be re-read from disk.) No path bypasses Step 1. Reasoning from memory about what was in-flight pre-compaction is prohibited — re-read state from disk every time.

**Orchestrator state initialization (do at invocation start):**
- `<Runtime>`: ISO-8601 UTC now, `YYYY-MM-DDTHH:MM` (see recovery-protocol.md). Used in all in-flight markers + ledger rows this session.
- `<RUN_TIMESTAMP>`: `<Runtime>` with every `:` replaced by `-` (filesystem-safe). Used in the staged-prompt filenames (Step 4) and the tmp-cleanup glob (Steps 7 + 9). Derivation detail: `references/dispatch-protocol.md` "RUN_TIMESTAMP format".
- `<round-counter>`: 0. Incremented by 1 at the start of each round's Step 7 — i.e. once per *completed* round, since Step 7 is the round-close step (so after round N's trace+address work, the counter reads N entering Step 7). Drives the 10-round ask gate (separate from the cumulative ledger Round column).
- `<gate-dismissed>`: false. Set true when the user answers `y` at the 10-round gate; thereafter the gate check is skipped this invocation.
- `<stop-after-round>`: integer or `null`. Set by (b)'s stop-after-round capture (which runs after (a), so `<round-number>` is available) when the user says "just round N then stop" or equivalent.
- `<target-intent>`: the text of the target's README `## Intent` section, or `null` if no README / no Intent section. Read at (c) below. Used by Step 6's considered-fix; the cold agents never see it.
- `<dispatch-set>` = `["forward","backward","executor"]`: a **constant**, available from invocation start (no production step) — always the three core directions (skill-tracer is correctness-only; no per-round variation).
- Populated as steps run: `<target-skill-name>`, `<mode>` (set at (b)); `<round-number>` (set at (a)); `<cluster-to-address-map>` (populated by Step 6); `<flag-to-cluster-map>` (populated by Step 5, extended in round 1 by Step 2.5).

**Order:** First the **target/mode half of (b)** (gives `<target-skill-name>`, needed for (a)'s ledger path); then **(a) recovery check** (sets `<round-number>`); then the **stop-after-round half of (b)** (needs `<round-number>`); then **(c) read intent**. The two halves of (b) straddle (a) — resolve target/mode before (a), capture stop-after-round after it.

**(a) Recovery check.** **First run `scripts/ledger_state.py <ledger>`** (ledger at `~/.claude/skill-tracer-audit-ledger/<target-skill-name>.md`) — it returns `highest_round` + the parsed `in_flight` marker (`{runtime, action, round, action_valid}` or null). Exit **2** (ledger path is a directory or unreadable) → **stop** (broken-ledger case, "Script error-handling contract"). Then **apply the matching recovery rule from `references/recovery-protocol.md`** — exactly one of the five applies, selected from the marker + `highest_round`: no marker → `highest_round == 0` is rule 4, `> 0` is rule 5; a valid marker → rule 1/2/3 by keyword (`dispatch`/`addressing`/`handoff`); a **malformed** marker — `in_flight.round` null (truncated or unparseable token) *or* `action_valid: false` — routes to recovery-protocol.md's truncated-marker / unknown-keyword fallbacks (read there for the precedence). Execute that rule's full action set per the reference (it owns marker format, round-number determination, `<encoded-cwd>`/`<Runtime>`, the JSONL recovery + `<flag-to-cluster-map>` rebuild, and atomic-write). After the rule runs, `<round-number>` is set. **Mode interaction with an in-flight marker:** `--audit-fixes` is read-only and does **not** recover — it ignores any in-flight marker and audits the ledger as recorded (it never reads or writes the marker). For `--one-round` / `--verify-only`, if a `dispatch`/`addressing` marker from a *prior full-convergence* trace is present (an interrupted trace, not this diagnostic run's own write), do NOT diagnostic-over it: tell the user a trace is mid-flight at round N and let them resume it first. A `handoff` marker (clean end-of-round) does not block a diagnostic run.

**(b) Determine target and mode.**
- `<name>` (bare token or quoted name) → look up `~/.claude/skills/<name>/`; `<target-skill-name>` = `<name>`.
- `<absolute-path>` → use the directory directly; **`<target-skill-name>` = its basename** (the final path component, no trailing slash) — this is the value used in the ledger path `~/.claude/skill-tracer-audit-ledger/<target-skill-name>.md`, the dispatch descriptions, and the session-log marker, so it must be set on the path-invocation branch too, not only the bare-name branch.
- Neither extractable → ask the user for the path.

Verify the directory exists and contains SKILL.md. State the resolved mode at the top of the run. Mode triggers: `--one-round` / `--verify-only` / `--audit-fixes` flags select those modes (natural language "audit skill fixes" / "check fix quality since convergence" → `--audit-fixes`); any other phrasing routes to full-convergence. Store `<mode>` as the flag string or `full-convergence`. If `<mode>` is `--audit-fixes`, after Step 2 dispatch the audit agent per `references/audit-fixes.md` (scope = rounds since last convergence) and report — skip Steps 2.5–8. Capture stop-after-round (after (a), so `<round-number>` is available) by **two clauses**: **(1) classify intent** — a one-shot snapshot (even one naming a round, e.g. "just one diagnostic round, round 3") → `--one-round`; a keep-converging-later phrasing ("stop after round N", "this round") → a resumable `<stop-after-round>` pause. Intent is the tiebreaker when both seem to apply. **(2) compute** (keep-converging case only): **`<stop-after-round> = max(N, <round-number>)`** — you cannot stop in the past, so a named N at or below the current round collapses to `<round-number>`; this single `max` guarantees Step 7 item 4 ever sees only the `==` (this round) or `>` (future round) cases, never an unhandled `<`. A stop-intent phrasing naming **no parseable round** ("stop soon", "a couple more rounds") → ask the user for a specific N (do not guess). (WHY the split: `<stop-after-round>` is a *resumable* pause — Step 7 writes a `handoff` so a later invocation keeps converging; `--one-round` is the *diagnostic* mode — one round, no loop-back, no handoff.) `<stop-after-round>` persists across loop-backs, re-checked at each Step 7 until `<round-number>` reaches it. Any unrecognized `--` flag → ask the user.

**(c) Read target intent (soft).** Read the target's `README.md` `## Intent` section into `<target-intent>`. If README.md is absent or has no Intent section, set `<target-intent> = null` and print one line: `Note: no README Intent found at <target>; considered-fix decisions will use the SKILL.md description as fallback intent.` Proceed either way. **This is the ONLY target doc the orchestrator reads for intent — and only the orchestrator reads it. The cold agents (Step 4) never receive README or HISTORY content.** (HISTORY.md is provenance — irrelevant to correctness tracing; skill-tracer never reads it.)

### Step 2. Enumerate files in scope (for the cold agents)

Build the absolute-path file list the cold trace agents will read. **Resolve `<skill-root>` to an absolute path first** (`cd <skill-root> && pwd`, or `$HOME/.claude/skills/<name>/` for bare names).

The cold agents trace the skill's **runtime + supporting content**: SKILL.md, every `.md` under `references/` at any depth, every script in `scripts/`, every config/template/asset. They do NOT trace the human/provenance docs. Skip list:
- **`README.md` at the skill root** — human intent doc; the orchestrator reads its Intent (Step 1c), the cold agents do not trace it.
- **`HISTORY.md` at the skill root** — provenance + changelog; not correctness-relevant; nobody in skill-tracer traces it.
- **`LICENSE` / `LICENSE.*` at the skill root** — legal text, not workflow.
- `*-workspace/` at any depth (legacy eval output)
- `evals/iteration-*/` at any depth (same)
- `.bak*` files (pre-edit snapshots)
- `__pycache__/` directories and `*.pyc` / `*.pyo` files at any depth — compiled Python bytecode, auto-regenerated from the `.py` source the agents already trace. They are build artifacts, not authored content, and are binary (a cold agent cannot meaningfully read or PRE-FLIGHT them). Tracing them adds noise, never signal.
- Hidden files (`.DS_Store`, `.gitignore`, etc.)

Skip rule wins over include rule on overlap. The skip list is **closed** — the `find` command below is its exhaustive implementation: a file the `find` emits is in scope, a file it excludes is not. A file resembling provenance/eval output but matching no skip pattern (e.g. a `notes-workspace.md` that isn't under `*-workspace/`, an `evals/` dir not matching `iteration-*`) is **in scope** — trace it; do not extend the skip patterns to it.

```bash
find <absolute-skill-root> -type f \
  ! -name ".*" \
  ! -name "README.md" \
  ! -name "HISTORY.md" \
  ! -name "LICENSE" ! -name "LICENSE.*" \
  ! -path "*/evals/iteration-*/*" \
  ! -path "*-workspace/*" \
  ! -path "*/__pycache__/*" \
  ! -name "*.pyc" ! -name "*.pyo" \
  ! -name "*.bak*"
```

(The `! -name "README.md"` / `HISTORY.md` / `LICENSE*` exclusions apply at the skill ROOT. A `references/README.md` — unusual — would still be excluded by name; that's acceptable, references docs rarely use those exact names.)

**Executable-but-unusual-extension check (required):** also run `find <absolute-skill-root> -type f -perm -u+x ! -name "*.md" ! -name ".*" ! -path "*/evals/iteration-*/*" ! -path "*-workspace/*" ! -path "*/__pycache__/*" ! -name "*.pyc" ! -name "*.pyo" ! -name "*.bak*"` and merge any new paths into `[FILE_LIST]`. A single executable shipped without a conventional extension would otherwise be silently excluded.

Copied-byte-identical scripts get the full trace treatment — paste-from-another-skill does not certify. Write absolute paths to in-memory `[FILE_LIST]`, **excluding SKILL.md itself** — it's carried separately as `[SKILL_PATH]` (Step 3), and the Step-2 `find` lists it, so drop it from `[FILE_LIST]` to avoid duplication. (The cold agents' PRE-FLIGHT gate covers SKILL.md via `[SKILL_PATH]` AND every `[FILE_LIST]` file, so SKILL.md drift is still detected — see `references/prompt-template.md`.) `[FILE_LIST]` is deterministic from on-disk state, so recoverable by re-running this Step after compaction.

### Step 2.5. Round-1 code-review pass (conditional — new / updated-since-convergence skills only)

A full-depth local code review of the **whole skill**, run as the **first phase of round 1** (round N on a re-trace), *before* the cold agents dispatch. It is **not a separate round** — it shares the round with the cold trace that follows: the code-review findings and the cold-trace findings both land in round N (the code-review ones tagged `REVIEW`, the trace ones tagged `TRACE`), and the round is closed once, at Step 7, after the cold trace. The finding *source* for this phase is the `code-review` skill instead of the three cold agents; everything downstream (clustering, considered-fix, ledger rows) is the same machinery.

**When this runs (all must hold):**
1. `<mode>` is `full-convergence`. The diagnostic modes (`--one-round` / `--verify-only`) **skip Step 2.5** — they are pure cold-trace snapshots.
2. The recovery rule resolved at Step 1(a) is **rule 4** (first-ever trace — no prior ledger/rounds) **or rule 5's clean sub-case that the user accepted** (the prior trace converged and the user said `y` to a fresh round). Rules 1/2/3 (mid-trace resume) and rule 5's not-clean sub-case (an unconverged trace with work remaining) **never** trigger Step 2.5 — they are continuations of a trace, not a new one. (The Step-1(a) "Unknown action keyword" fallback is treated *as* `dispatch round-N` — i.e. rule-1 mid-trace-resume behavior — so it does **not** trigger Step 2.5 either.)
3. For the rule-5 path only: at least one in-scope file changed since the prior convergence. Run the Step-2 `find` (same scope filters) with `-newermt "<Runtime>"` appended, where `<Runtime>` is the **most recent `<Runtime>` recorded anywhere in the ledger** (the newest of the highest data row's Runtime and the latest `<!-- Invocation … -->` comment's Runtime) — i.e. when the skill was last traced; files newer than it changed since. (Use the last-trace timestamp because a *converged* round writes no data rows, so it has no per-row Runtime of its own.) Rule 4 skips this check — a first trace is always eligible. **Three outcomes:** ≥1 path → **run** Step 2.5; zero paths → unchanged → **skip**; **cannot evaluate** (the `find` errored, or no clean round's Runtime is determinable from the ledger) → **run** (review-when-in-doubt). A clean zero-path result is a skip, never "cannot evaluate".

If any condition fails, **skip Step 2.5 entirely** and proceed to Step 3 at `<round-number>` (unchanged behavior — round N starts directly with the cold agents).

**(a) Run the review over the WHOLE skill (not a diff).** Invoke the `code-review` skill at full local depth, no issue cap — **`/code-review max`** via the `Skill` tool (`skill: code-review`, `args: max`). Do **not** pass `--fix` (skill-tracer applies fixes itself, through the considered-fix gate — invariant 2) and do **not** pass `--comment` (no PR side-effects). `max` is the broadest local effort and may surface uncertain findings — intended here; the considered-fix gate filters them. WHY local, not `ultra`: skill-tracer is an offline workflow (no network — see Prerequisites); `ultra` is a cloud pass and is out of scope.

  **Scope = the whole skill, every in-scope file's full contents** — `[SKILL_PATH]` + every path in `[FILE_LIST]` (Step 2's enumeration; the authoritative scope). Do **not** rely on a working-tree diff: skills are not always under git (skill-tracer's own tree is not a git repo), and a brand-new skill has no diff at all, so diff-scoped review would see nothing. Pass the file set explicitly via the `Skill` tool's `args` — put `max` first, then the directive and the path list in the same `args` string: e.g. the `args` string is `max`, then a blank line, then `Review the full contents of these files, treating every line as under review (this is not a diff review):`, then one file path per line — joined with real newline characters. The path set is `[SKILL_PATH]` **as the first line**, then every `[FILE_LIST]` path — `[FILE_LIST]` excludes SKILL.md (Step 2 carries it separately as `[SKILL_PATH]`), so SKILL.md must be added explicitly or the review misses it. **If `/code-review` ignores the extra `args` content and reviews only a diff (or refuses a whole-file scope), that IS the "cannot be scoped to whole files" condition** → drop to the fallback general-purpose Agent below.

  **If `/code-review` cannot be scoped to whole files in this environment** (it only accepts a diff / PR, or is not installed), fall back to skill-tracer's own whole-skill review: dispatch one general-purpose Agent — `description` exactly `Code-review pass of <skill>` (the bare `<target-skill-name>`) — with code-review's `max` methodology: read the full contents of `[SKILL_PATH]` + every `[FILE_LIST]` file and report correctness bugs **and** reuse / simplification / efficiency findings, one finding per block. Collect its findings identically in (b). (This keeps the round-1 review working regardless of `/code-review`'s argument surface; tell the user which path ran.) **Recovery:** this fallback Agent is not one of the three `<Direction> trace of <skill>` dispatches, so `recover_dispatch.py` does not match it; a compaction during it is handled by recovery-protocol.md rule 2's `REVIEW`-phase branch — no `Forward/Backward/Executor trace` dispatch exists for the round, so recovery re-runs Step 2.5(a) wholesale (the review is idempotent — re-reading the current files). If neither path can run, skip the pass, tell the user, and proceed to Step 3 — do **not** block the trace.

**(b) Cluster and address each finding.** Treat each reported finding as a raw flag with the **`CR`** prefix (`CR1, CR2, …` — code-review; a distinct prefix because `F/B/E` are the cold directions and `C*` is the Cluster column — see `references/ledger-format.md` "Flag-ID scheme"). **One finding = one `CR` flag** — count one `CR` per distinct issue the review reports (one reported finding / issue block; the fallback Agent is told "one finding per block", and `/code-review` enumerates findings the same way — split any grouped output by individual issue; if `/code-review`'s output structure is opaque (no per-finding blocks or markers), segment by distinct `file:line` **first** (one `CR` per distinct `file:line`); a finding naming no `file:line` falls back to its distinct symptom. Two findings at the **same** `file:line` describing **different** defects are two `CR`s; the **same** defect restated across lines is one `CR`). Cluster them with the **cluster-grouping procedure in `references/ledger-format.md` "Cluster grouping procedure"** — read that reference directly here (Step 2.5 runs before Step 3, so do not rely on having reached Step 5; Step 5 uses the very same procedure). Build the round's `<flag-to-cluster-map>` now, mapping each `CR*` flag to its cluster. Number the clusters `C1, C2, …` **in the order their findings are first encountered** (a readability convention) — the **start** of round N's cluster sequence; the cold-trace clusters (Step 5) *continue* this numbering, not restart, since both phases share round N. (Cluster numbering is display-only — see `references/ledger-format.md` Cluster column for WHY. The `CR*` **flag-IDs**, by contrast, ARE machine-checked: every `CR*` flag must land in exactly one row at Step 7's `verify-auditability`.) Then address every cluster using **Step 6's procedure** — the shared address procedure this phase reuses (not duplicated). Its load-bearing rules, summarized here so this phase is actionable without reading ahead, are: bias-toward-FIX, considered-fix against `<target-intent>` (a code-review finding that would trade away documented intent is a USER-PAUSE, not an auto-FIX), no-orphan-flag; the full spec (address formats, anti-patterns) lives at Step 6 + `references/address-decision.md`. On entering the addressing work — before the first cluster is addressed, regardless of whether its address turns out to be FIX, STRENGTHEN, or USER-PAUSE — write the atomic-write marker `in-flight:: <Runtime> addressing round-<round-number>` (the same write Step 6 performs on entry; see Step 6 "Atomic-write entry").

**(c) Record in the ledger.** Write one row per cluster via `append_ledger.py append` with the **same required arg set as Step 6** (`--runtime <Runtime> --round <round-number> --cluster C<n> --root-cause … --address … --flags "CR…"`; all required — see `references/ledger-format.md` for the row spec, and `references/address-decision.md` for the `--address` column-string formats: `FIX (…)` / `STRENGTHEN (added at <file>:<lines>: "…")` / `USER-PAUSE (…)`), the only difference being **`--phase REVIEW`** (marks the row code-review-sourced) instead of `--phase TRACE`. Round = `<round-number>` (the shared round). Each row's `--flags` is the comma-separated list of `CR*` IDs grouped into **that** cluster (from the `<flag-to-cluster-map>` built in (b)); `--root-cause` is the cluster's one-line defect description (the code-review finding's root cause) and `--address` its considered-fix outcome — the same columns a `TRACE` cluster fills, just sourced from the review. Keep those `CR*` entries in `<flag-to-cluster-map>` — Step 5 *adds* the cold-trace `F*/B*/E*` entries to the same map (it does not clear it within the round), so Step 7's round-close `--expect` set is the **union** of these `CR*` flags and the cold trace's `F*/B*/E*` flags.

**(d) Proceed into the cold trace — same round, no loop-back, no close.** Do **not** close the round and do **not** increment `<round-number>` here — the code-review phase and the cold trace are one round. Proceed directly to **Step 3 → Step 4** for round `<round-number>` (Step 4's atomic-write overwrites the `addressing round-N` marker with `dispatch round-N`). Step 5 continues the cluster numbering after the `CR*` clusters; Step 7 closes round N once, counting **both** the `REVIEW` and `TRACE` rows (its `verify-auditability --expect` is the round's full flag union — built per Step 7 item 3). Convergence (Condition A) is decided by the cold trace only — the `REVIEW` clusters never block it (they are the pre-trace review), **except** an unresolved `REVIEW` `USER-PAUSE`, which does block until the user resolves it. **Step 8 is the authoritative statement of Condition A** (incl. this REVIEW/USER-PAUSE rule); this step does not restate it.

### Step 3. Build three dispatch prompts (forward, backward, executor)

Read `references/prompt-template.md`. Build one prompt per direction (always exactly three — forward, backward, executor; `<dispatch-set>` is constant). Fill the SLOTs:

| Slot | Value |
|---|---|
| `[DIRECTION]` | `forward` / `backward` / `executor` |
| `[SKILL_NAME]` | the target skill name |
| `[SKILL_PATH]` | absolute path to the target's `SKILL.md` |
| `[FILE_LIST]` | absolute paths of every supporting file from Step 2, one per line, bare (no quotes, no bullets). Excludes README/HISTORY/LICENSE per Step 2. |
| `[GLOSSARY]` | 5–15 one-line definitions selected per the precedence below; literal `none` if the skill has no domain vocabulary |
| `[INLINED_TRACE_DEFINITION]` | the full body of `references/<direction>.md`, pasted verbatim |

**Glossary precedence (read in order, first match per term):**
1. Target skill's `references/glossary.md` — authoritative skill-internal vocabulary.
2. `~/.claude/skills/skill-creator-ccvw/references/ccvw-glossary.md` — shared CCVW terms (skip if not installed).
3. The user's Claude config + memory, **if present** — `${XDG_CONFIG_HOME:-$HOME/.claude}/CLAUDE.md` + `${XDG_DATA_HOME:-$HOME/.claude}/memory/MEMORY.md` (on Claude Code these resolve to the `.claude` home dir) — user-level definitions. Optional: skip this source silently when the files are absent.
4. Cold derive — only if absent from all three. Read the term in context; write a one-line definition.

Include WHY in a glossary entry when the mechanical definition doesn't make design intent obvious. Worked-example vocabulary in the trace-definition files (`p1-next`, "delta-pending", etc.) is illustrative — do NOT extract into the target's `[GLOSSARY]`. Leave no slot un-substituted; literal `none` is valid only for `[GLOSSARY]`.

### Step 4. Dispatch all three, cold, in parallel — same-turn requirement

**Session-log marker (very first action of Step 4, before any check or write):** Emit a step marker to the shared session log so compact hooks can identify what is in progress:
```bash
echo "**[$(date +%H:%M:%S)] SKILL:skill-tracer RUN:<target-skill-name>-r<round-number> STEP:dispatch-round-<round-number>**" >> "${HOME}/.claude/session-logs/session-log-$(date +%Y-%m-%d).md"
```
Substitute the actual `<target-skill-name>` (the **bare skill name** — if the target was given as an absolute path, use its basename, not the slash-bearing path, so the `RUN:<name>-r<round>` field stays well-formed) and `<round-number>` (the orchestrator state variable — set in Step 1(a), incremented at each loop-back; write it as the bare integer, no padding) from context. Non-blocking, best-effort — compact hooks read it leniently, so the round format here is not a load-bearing parse contract; if the write fails, continue.

**Runtime-constraint check** (once, top of Step 4): confirm `Agent` is in the toolset. If not, abort per `references/recovery-protocol.md`.

**Atomic-write protocol entry** (before any Agent call — **WHY before**: a compaction or session death between dispatching the agents and recording their results would otherwise lose the round with no marker for the next invocation to recover from; writing the marker first makes the in-flight round recoverable): write `in-flight:: <Runtime> dispatch round-N` to the ledger header — the placement mechanics (insert the line if no `in-flight::` line exists yet, swap it in place if one does) are in `references/recovery-protocol.md` "Marker write/replace mechanics"; the ledger is guaranteed to exist by now (Step 1(a)'s recovery rule creates it on a first trace). **On the first dispatch of an invocation, optionally arm the self-perpetuating resume wakeup** per recovery-protocol.md "Self-perpetuating resume wakeup" — that section owns the whole mechanism (availability test for `/loop` vs `mcp__scheduled-tasks__create_scheduled_task`, the ask-the-user-for-the-first-interval rule, the fixed-5h re-arm, self-termination on marker clear, and the canonical resume-prompt text). Arm it here, *before* prompt staging, so the user-interval ask does not split the same-turn three-Agent message. If no resume mechanism is available, skip arming (do not block the trace) — resume then relies on manual re-invocation.

**Prompt staging** (before any Agent call): stage all three prompts to `/tmp/skill-tracer-prompts/<direction>-<RUN_TIMESTAMP>.txt` — use `scripts/stage_cold_prompts.py` (the **single** staging mechanism — its invocation, including the required `--spec` JSON of `[{label, slots}]` entries whose `label` is the bare direction name, is in `references/dispatch-protocol.md` "Prompt staging procedure"). If the stager exits non-zero (a missing file after write, or an unfilled `[SLOT]`), do NOT dispatch — see `references/dispatch-protocol.md` "Failure handling" to resolve first. (skill-tracer **never** passes `stage_cold_prompts.py --allow-unfilled`: an unfilled slot in a trace prompt is always a staging bug here, so the strict default — exit 1 on any leftover `[SLOT]` — is the wanted behavior. `--allow-unfilled` exists for other callers that legitimately template partial prompts.)

**Dispatch** (single assistant message, three Agent calls):

| Parameter | Value |
|---|---|
| `description` | one of exactly `Forward trace of <skill>` / `Backward trace of <skill>` / `Executor trace of <skill>`, where `<skill>` is the **bare `<target-skill-name>`** and the literal pattern `<Direction> trace of <skill>` is kept exactly (recovery rule 1's `recover_dispatch.py` matches `^(Forward\|Backward\|Executor)\s+trace\s+of\s+(.+)$` (the `\|` here is **markdown table-cell escaping** for the `|` character — the actual regex in `recover_dispatch.py` is `(Forward|Backward|Executor)` with bare-`|` alternation, not a literal `Forward|Backward|Executor` string; the regex is `re.IGNORECASE`, so casing of the `Forward/Backward/Executor` prefix does NOT matter — a lowercase slip is still recoverable) and compares the captured name to `<skill>` by stripped equality — so rephrasing the `trace of` wording, or using a path rather than the bare skill name, would make the dispatch unrecoverable (a case-only difference would not). `recover_dispatch.py` matches a tool_use whose name is **either `Agent` or `Task`** — the dispatch uses the `Agent` tool, but a harness that surfaces the same call under the `Task` name is still recoverable) |
| `subagent_type` | `general-purpose` — load-bearing: the cold agent must `Read` arbitrary target files, `Bash` `grep`/`wc`, and emit a free-form ISSUE report; `general-purpose` is the type carrying that toolset. A narrower/specialized type could lack file-read or shell access and silently fail the trace. |
| `prompt` | `Read /tmp/skill-tracer-prompts/<direction>-<RUN_TIMESTAMP>.txt and follow the instructions in that file verbatim. Do not improvise. Do not request the orchestrator's context. Your output is the report the file's instructions ask for.` |

**Same-turn requirement is load-bearing**: all three Agent calls in one assistant message. Serial dispatch would let the orchestrator's view of agent 1's result bias agent 2's prompt — the cold-parallel invariant fails. Rationale, self-check, and discard-and-retry recovery: `references/dispatch-protocol.md`.

After all three dispatches, wait for all three tool_results in parallel.

### Step 5. Collect ISSUE blocks and map to root causes

Each agent returns:
- A `PRE-FLIGHT` line per file (`PRE-FLIGHT <path>: <line_count> lines, last edited <yyyy-mm-dd>`). The agent results arrive in-context, so write each report — the **verbatim** agent tool_result text (preserving the exact `PRE-FLIGHT` / `ISSUE` / trailing-summary lines the parsers match; do **not** paraphrase or summarize) — to **`/tmp/skill-tracer-prompts/<direction>-report-<RUN_TIMESTAMP>.txt`** (this exact path — `check_results.py` below and the Step 9 cleanup glob depend on it) and run `check_drift.py --file <report>` (or pipe PRE-FLIGHT lines via stdin), per `references/ledger-format.md` "PRE-FLIGHT drift test". **Orchestrator decision: drift (exit 1 — any line-count delta, a now-missing file, or a >1-day date skew) means the whole round is stale → re-run Steps 2–4 for all three directions** (re-enumerate, rebuild, re-stage, re-dispatch), not just the drifted one. (A missing file here is always genuine drift, never a fix-removal — no FIX runs before Step 6.) **Exit 0 with empty `drift`/`missing`/`unparseable` = no drift, report well-formed → fall through to the per-direction `usable` check below.** **check_drift's single-direction signals** — exit 2 *with JSON* (`checked: 0`, no PRE-FLIGHT parsed) or a non-empty `unparseable` list on exit 0 (garbled report) — mean *that one report* is unusable → re-dispatch only that direction (same as `check_results.py` returning `usable:false` below). The exit-code decode, the usage-error exit 2 (no JSON → re-write the report file **from the in-context agent output**, do not re-dispatch), and the drift-wins precedence when one exit-1 result also lists `unparseable` are in `references/ledger-format.md` + the "Script error-handling contract" table.
- Zero or more `ISSUE` blocks (tag, file path, `Claim:`, `Target:`).
- A trailing `No issues found` or `No of issues found:: N`.

**Order the two re-dispatch checks: drift first, then `usable`.** The drift test (above) and this `usable` check differ in scope — drift means files changed mid-round, so the whole round is stale (re-run Step 2 + Step 4 for ALL three per `references/ledger-format.md`, and skip the per-direction check this round); `usable: false` is a single-direction substance failure. Run drift first; only if there's no drift, apply the per-direction `usable` check.

**Validate each direction's report with `scripts/check_results.py`** (`--file <report> --direction forward|backward|executor`, where `<report>` is the same per-direction temp file written for the drift test above — `/tmp/skill-tracer-prompts/<direction>-report-<RUN_TIMESTAMP>.txt`, already on disk) — it returns `usable` + `authoritative_count` per direction. Re-dispatch a direction **only when `usable` is false** — a genuine substance failure: `ABORTED`, no PRE-FLIGHT at all, or no trailing summary at all.

**A count mismatch is NOT a re-dispatch trigger.** If the agent's trailing `No of issues found:: N` disagrees with the actual number of `ISSUE` blocks, that's a clerical miscount, not a substance failure — the ISSUE blocks themselves (tag/Claim/Target) are the findings and are right there. **Recount from the actual blocks and proceed** (use `check_results.py`'s `authoritative_count`); log the discrepancy, don't reject. Re-running a whole direction's trace because it miscounted its own blocks wastes a full agent dispatch for nothing.

Re-dispatch procedure (only for the genuinely-unusable directions): same round-number + Runtime, overwrite the staged prompt file (the filename is identical because RUN_TIMESTAMP is unchanged), marker stays `dispatch round-N`. (A single-direction re-dispatch is **one** Agent call — the same-turn requirement [Step 4] is moot for a lone call; it governs only the multi-call initial dispatch, where the orchestrator could otherwise let one agent's result bias another's prompt. Issue the one re-dispatch as a normal single Agent call; if two or three directions are independently unusable, re-dispatch those in one same-turn message.) After a re-dispatch returns, run the drift + `usable` checks on the new report and collect its `ISSUE` blocks, then **merge them with the already-usable directions' blocks** — the round's flag set is the **union of all three directions**; do not discard or re-collect the directions that were usable the first time.

**Re-dispatch is always a FRESH agent — never resume, continue, or fork the failed one.** The SDK supports resuming a subagent (cheaper via prompt-cache reuse), but that is forbidden here: resuming carries the prior agent's reasoning forward, which violates the cold-trace invariant (each dispatch must read the target with no prior context). And there's no cost penalty for going fresh — a subagent's verbose internal work stays in its own isolated context and never entered the orchestrator's, so a discarded agent costs the orchestrator nothing; re-running the work costs the same whether "resumed" or "fresh." Fresh wins on independence at no extra cost. (Do not "optimize" this by resuming — it silently breaks cold-trace.)

Collect every ISSUE block. Number sequentially per source: `F1, F2, …` (forward), `B1, B2, …` (backward), `E1, E2, …` (executor). These are the only three flag prefixes. Per-source counters are independent. Cluster grouping (three tests + when-in-doubt rule) and the ledger format spec live in `references/ledger-format.md`. The result of Step 5 is two in-memory maps: `<flag-to-cluster-map>` (flag-ID → cluster, consumed by Step 6 for the Flags column + Step 7 item 3 for `verify-auditability`'s `--expect` set; it is per-round and overwritten **on each loop-back to a new round**, so Step 9's cross-round counts come from the ledger + round-summary comments, not this map) and `<cluster-to-address-map>` (cluster → address, populated by Step 6, read by Step 7's anchor check). **Round-1 two-phase note:** when Step 2.5's code-review phase ran, it already populated `<flag-to-cluster-map>` with the round's `CR*` entries; Step 5 here **adds** the cold-trace `F*/B*/E*` entries to that same map (it does not clear it within the round), so by Step 7 the map holds *every* flag raised in the round across both phases. "Overwritten" applies only across rounds (a loop-back), never between a round's own phases.

### Step 6. Address every cluster — bias toward FIX, no orphan flags

**Atomic-write entry** (before cluster-by-cluster work): replace the marker with `in-flight:: <Runtime> addressing round-N`. This write is **unconditional** — Step 6 is entered every round, *including a zero-cluster (clean) round*, where the cluster loop below simply runs zero iterations; the `addressing round-N` marker is still written, so the marker present at Step 7/8 is uniformly `addressing round-N` on every path (this is what recovery-protocol.md's atomic-write table assumes).

For every cluster, decide and act. No DISMISS branch — every cluster gets FIX, STRENGTHEN, or USER-PAUSE. **Bias toward FIX** is the controlling rule; STRENGTHEN is the narrow exception when the artifact is correct and the cluster reflects intent the trace agents couldn't see. The full address-decision spec — two-step FIX test, two anti-patterns, four legitimate STRENGTHEN cases, three address formats with examples, PAUSE criteria, fix conservatism, regression-vs-cascade convergence check — lives in `references/address-decision.md`.

**Considered-fix uses `<target-intent>`.** Before applying a FIX, check it against the target's documented Intent (from Step 1c): would this change trade away what the skill explicitly optimizes for? If yes → USER-PAUSE (intent-ambiguous; the user decides), not auto-FIX. This is the operational form of the considered-fix invariant. If `<target-intent>` is null (no README Intent), use the SKILL.md description as fallback intent and note in the USER-PAUSE that intent was undocumented.

**Resolving a USER-PAUSE, and enumerating unresolved ones for convergence.** A USER-PAUSE row persists on the ledger as history (`append_ledger.py` only appends — there is no delete). A pause is **resolved** when a later round records the user's decision as a **new row that names it**: a `FIX (… resolves USER-PAUSE round-N/C<m> …)` applying the chosen path, or a `STRENGTHEN (… resolves USER-PAUSE round-N/C<m>: accepted trade-off …)` when the user accepts the documented trade-off. Step 7/8's "no unresolved `USER-PAUSE`" test (which gates convergence) is computed by **scanning the whole ledger** for USER-PAUSE-addressed rows that have **no later row naming them as resolved** — those are the open pauses; convergence blocks while any remain. (This is the only cross-round set the convergence test needs; it is derived from the ledger each time, not held in `<cluster-to-address-map>`, which is per-round.)

**Verify-only mode**: decide each cluster's would-be address but apply nothing; write the ledger row with a `would-` prefix — exactly one of `would-FIX` / `would-STRENGTHEN` / `would-USER-PAUSE`. A `would-STRENGTHEN` applies nothing, so it carries a one-line summary, not an applied-STRENGTHEN `added at <file>:<line-range>` anchor — the `would-` forms live in `references/address-decision.md` "STRENGTHEN format" and the token-boundary parsing rule (`append_ledger.py` accepts only the three applied kinds + their three `would-` variants, each at a token boundary) in `references/ledger-format.md`. Then proceed to Step 7 like any round — Step 7's round-close (item 3: `close-round` + `verify-auditability`) runs on the `would-` rows, and its mode routing (item 4) handles the diagnostic exit (clear marker → Step 9). Verify-only does NOT bypass Step 7 — WHY: Step 9 aggregates from the round-summary comment that only `close-round` (a Step 7 action) writes, and the marker is cleared in Step 7 item 4; bypassing Step 7 would leave Step 9 nothing to read and the marker orphaned.

Write one ledger row per cluster as addressed (not batched), via `scripts/append_ledger.py append` — its argument set (`--runtime`, `--round`, `--phase TRACE`, `--cluster`, `--root-cause`, `--address`, `--flags`), the row format + single-line / pipe-safe Address constraint (**for an applied STRENGTHEN, re-read the file after the edit and capture the post-edit `<file>:<line-range>` + first-80-chars quote into the Address** — per `references/ledger-format.md` "Exact line numbers in STRENGTHEN"; Step 7 item 2's anchor-check verifies exactly that recorded range), **and the zsh shell-invocation guard** (invoke `python3` as the literal command word — never store the whole invocation in a shell variable, which zsh treats as one command and fails exit 127) are in `references/ledger-format.md`. Target: `~/.claude/skill-tracer-audit-ledger/<target-skill-name>.md`. Populate `<cluster-to-address-map>`.

### Step 7. End of round — loop inline to convergence (default), or hand off and exit

**Step 7 entry order:**
1. **Increment `<round-counter>` by 1.**
2. **Anchor-check — verify every STRENGTHEN anchor landed** (orchestrator-manual by design — no script enforces it, because re-reading arbitrary target files at arbitrary line ranges is not the fixed-shape operation a helper script can own; the orchestrator must run this check itself each round) (skip if this round wrote zero *applied*-STRENGTHEN rows to the ledger — filter the Round-N rows for an Address beginning `STRENGTHEN (added at` (a `would-STRENGTHEN` Address begins with `would-`, so this prefix naturally excludes it — see `references/address-decision.md` "STRENGTHEN format" for both literal forms); `would-STRENGTHEN` rows apply nothing and are excluded. Read the **ledger** here, not `<cluster-to-address-map>` — a rule-2 mid-addressing resume does not repopulate that in-memory map with pre-interruption addresses, whereas the ledger always holds the round's full set of rows). Re-read the ledger, filter this round's *applied*-STRENGTHEN rows (the same `STRENGTHEN (added at` filter — `would-STRENGTHEN` rows carry no line-range or quoted text, so they are excluded here too), re-read each named file at the named line range, confirm the quoted first-80-chars text is present. If missing (a later FIX overwrote it), re-apply to a stable location (the location-selection procedure — pick one this round's remaining clusters do not touch — is in `references/address-decision.md` "Verifying STRENGTHEN landed"; read it here) and update the row's anchor. **Updating the anchor is the one in-place ledger edit in the workflow** — `append_ledger.py` only appends, so hand-edit that row's Address cell to the new `<file>:<line-range>` (and refreshed quoted text), preserving the single-line / pipe-safe constraint (no literal `|`, no embedded newline — the same rules `append_ledger.py append` enforces; full spec in `references/ledger-format.md`). The anchor is what the *next* round's anchor-check reads, so it must point at the re-applied text; a stale anchor left here is also caught next round, but fix it now.
3. **Close the round** with `scripts/append_ledger.py close-round <ledger> --round N` (appends the round-summary comment, recomputed from the round's actual rows — once per round, all paths). Then assert the no-orphan-flag invariant with `scripts/append_ledger.py verify-auditability <ledger> --round N --expect "<flag-IDs>"`, where `--expect` is **every flag-ID raised this round across all its phases** — the key-set of `<flag-to-cluster-map>`, serialized as a **comma-separated list** (`F1,B2,E3`; `append_ledger.py` splits on commas and **strips each token**, so surrounding spaces are tolerated — the example rows' `F1, B3, E5` form works too. What fails is a **space-separated list with no commas**: the whole string is then read as one bogus flag-ID): the cold-trace `F*/B*/E*` from Step 5, **plus a full-convergence round 1's `CR*` flags** from Step 2.5 (the map is extended within a round, overwritten only on a loop-back — see Step 5's round-1 two-phase note; diagnostic modes skip Step 2.5, so `--expect` is `F*/B*/E*` only there). On exit 1, reconcile the round's rows before proceeding. The `--expect` format and the three exit-1 meanings (a flag double-counted, missing from the ledger, or present-but-absent-from-`--expect`; comma-split into a set, never a literal `…`, space-separated fails) live in `references/ledger-format.md` "Auditability invariant" + the row-writing spec.
4. **Mode routing** (evaluate the cases **in order; the first matching case wins**) — `--audit-fixes` never reaches Step 7 (Step 1(b) routes it to dispatch the audit agent and skip Steps 2.5–8), so these cases cover only the trace modes (`--one-round` / `--verify-only` / full-convergence):
   - **`--one-round` or `--verify-only`** (the diagnostic modes): write the invocation-total comment, clear the in-flight marker (remove the `addressing round-N` line — per Step 6's unconditional-write invariant that is always the marker present here; the diagnostic round is complete, nothing is in flight), then proceed to Step 9. No loop-back.
   - **`<stop-after-round>` is set AND `== <round-number>`** (checked only in full-convergence mode, after the diagnostic case above): if **zero cold-trace (`TRACE`-phase) clusters** were raised this round **and no unresolved `USER-PAUSE` cluster remains** (the same Condition-A test as the default case), Condition A already holds → proceed to Step 8 (converged; the stop is moot — do NOT hand off). Otherwise → opt-in handoff (below).
   - **`<stop-after-round>` is set AND `> <round-number>`** (the target round is not yet reached): does **not** match the stop case — proceed exactly as the **default full-convergence** case below (loop normally). `<stop-after-round>` persists across the loop-back and is re-checked at each later Step 7 until `<round-number>` reaches it (per the (b) definition).
   - **default (full-convergence)** — reached when neither stop case above matched, i.e. `<stop-after-round>` is `null`/unset (the normal full-convergence case; the `max(N,round)` rule guarantees a *set* `<stop-after-round>` is always `==` or `>`, never an unmatched value). Three sub-cases:
     - **zero `TRACE` clusters AND no unresolved `USER-PAUSE`** (any round/phase, incl. a round-1 `REVIEW` `USER-PAUSE`) → Condition A holds → proceed to Step 8.
     - **`TRACE` clusters were raised this round** (if an unresolved `USER-PAUSE` *also* remains, **first** surface it to the user per the third sub-case below so the loop-back doesn't bury it, then continue here) → **first evaluate the 10-round ask gate** (see Stopping conditions): if `<round-counter>` ≥ 10 and `<gate-dismissed>` is false, ask the gate question (exact text in "Stopping conditions" below) — on `n` run the **Handoff-stop sequence** (defined in "Stopping conditions" below) with its stop message, on `y` set `<gate-dismissed>` and continue; otherwise (gate not triggered, or dismissed) → loop-back (item 5).
     - **zero `TRACE` clusters but an unresolved `USER-PAUSE` remains** → do **NOT** loop-back (re-dispatching three cold agents cannot resolve a decision only the user can make, and would re-find nothing). Instead **surface the unresolved `USER-PAUSE`(s) to the user now**, get their decision, apply it (a FIX if they choose one, or accept the documented trade-off and clear the pause), then re-evaluate Condition A for this round: if it now holds → Step 8; if the user's decision introduced a new fix whose effect needs a cold check → loop-back (item 5). If the user defers the decision → write the opt-in handoff (below) so a later invocation resumes with the pause still open.

   *(The "`TRACE`-phase clusters" vs "all clusters" distinction only matters in round 1's two-phase structure — Step 8 is the authoritative statement of why `REVIEW`/`CR*` clusters are not part of the Condition-A test. In every round without a Step-2.5 phase, all clusters are `TRACE` clusters and the qualification is a no-op.)*
5. **Loop-back** (non-zero-cluster rounds): **increment `<round-number>` by 1** (N→N+1 — the cumulative ledger Round must advance before re-dispatch so the new round's marker, ledger rows, and round-summary all carry N+1; Step 1(a) sets it once and this is the only per-round advance), then re-run Step 2 in full (re-enumerate the file list — prior fixes may have added/removed files), and re-execute Steps 3–4 in the **same session**. Step 4's atomic-write writes the next `dispatch round-<N+1>` marker. The dispatched agents receive the **current** target state — no "what changed" preamble, no fix log, no carry-over. Cold-trace invariant unchanged.

**Invocation-total comment.** Wherever an exit path says "write the invocation-total comment" (Step 7 item 4's diagnostic exit, the 10-round-gate stop, the opt-in handoff, and Step 8 convergence), hand-write `<!-- Invocation <Runtime> total: rounds N..M — raw flags A — clusters X — addresses: F FIX + S STRENGTHEN + P USER-PAUSE -->` per `references/ledger-format.md` "Round and invocation summary comments". It spans the invocation's rounds (N..M), so no single-round script emits it — unlike the per-round summary, which `close-round` writes.

**Stopping conditions** (exhaustive):
- **Converged** (Condition A — all three agents clean in one cold round) → Step 9.
- **10-round ask gate**: when `<round-counter>` ≥ 10 and `<gate-dismissed>` is false, ask `Trace has run <round-counter> rounds without converging. Continue? (y/n)`. `y` → set `<gate-dismissed> = true`, continue (skip the gate for the rest of this invocation). `n` → run the **Handoff-stop sequence** (defined below) with the user message `Stopped at Round <round-number> at your direction. USER-PAUSE clusters (if any) remain — see ledger.` (A distinct trigger from the opt-in handoff, but the terminal steps are identical — hence the one shared sequence.)

Compaction mid-round: the atomic-write marker already on the ledger is sufficient; the next invocation reads it and runs the matching recovery rule. No proactive yield.

Per-cluster addressing is fresh-decision per round — the orchestrator owns FIX/STRENGTHEN execution. A regression means the prior fix didn't stick; address it freshly next round (different scope/anchor/approach). USER-PAUSE is decision-based only, never a fix-failure fallback.

**Handoff-stop sequence** (shared by the 10-round-gate `n` stop and the opt-in handoff — both end the invocation cleanly leaving a resumable `handoff` marker; they differ only in the user message passed in):
1. Write `in-flight:: <Runtime> handoff round-<N+1>`, N = `<round-number>` — **write the computed integer, not the literal expression** (if N is 6, write `round-7`; `round-6 + 1` would split on whitespace and `ledger_state.py` would parse only `round-6`, dropping the increment). Keyword `handoff` — recovery-protocol distinguishes it from `dispatch`; this is a **swap** of the `addressing round-N` marker Step 6 wrote (at most one in-flight line ever), per recovery-protocol.md "Marker write/replace mechanics". (The 10-round gate fires on `<round-counter>`, but the marker and ledger use `<round-number>` — they diverge on a resumed trace.)
2. Clean up tmp files: `rm -f /tmp/skill-tracer-prompts/*-<RUN_TIMESTAMP>.txt /tmp/skill-tracer-prompts/spec.json`.
3. Write the invocation-total comment.
4. Tell the user the caller-supplied message.
5. Exit.

**Opt-in self-invoking handoff** (user said "just round N then stop"): run the **Handoff-stop sequence** above with the message `Round N complete (M clusters: F FIX + S STRENGTHEN + P USER-PAUSE). Re-invoke /skill-tracer <skill-name> for round N+1, or stop here.`

**Why inline is the default.** Full-convergence is named for the goal: keep going until clean. Asking the user to re-invoke between every round makes convergence the user's job. The inline loop holds the three agent reports in context for one round, then the round-N+1 cold dispatch reads the current file state so prior context is functionally discarded from the agents' perspective. This is the **ralph-loop pattern** (orchestrator-internal iteration with cold child dispatches); skill-tracer's per-round dispatch + addressing is the convergence-bounded specialization with handoff-on-stop as the escape.

### Step 8. Convergence — Condition A only

Convergence requires **Condition A — internal-clean**: all three trace agents return `No issues found` in one cold round **and no unresolved `USER-PAUSE` cluster remains from any round or phase** (a `USER-PAUSE` awaiting the user's decision always blocks convergence — including a round-1 `REVIEW`-phase `USER-PAUSE`, which the cold trace would not re-raise on its own). (In round 1 with a Step-2.5 code-review phase, the cold trace runs *after* the code-review fixes are applied and reads the fixed files — so a clean cold trace there is a genuine clean cold round on the post-fix state. The `REVIEW`-phase `CR*` clusters are otherwise not part of the cold-trace-clean test — but an unresolved `REVIEW` `USER-PAUSE` still blocks convergence per the clause above.)

(Earlier versions also required a Condition B — CCVW-compatibility, via a Step-9 audit. That moved to skill-publisher's ship phase. skill-tracer converges on correctness alone.)

The executor arrives at Step 8 only via Step 7's zero-clusters branch — Condition A is already confirmed clean. Step 8 is the named convergence anchor: clear the in-flight marker (remove the `addressing round-N` line from the ledger header — per Step 6's unconditional-write invariant that is the marker present here; no new marker), write the invocation-total comment (see Step 7's "Invocation-total comment" note — convergence is the canonical "invocation completes" case), then proceed to Step 9.

### Step 9. Present result

(Post-compaction resume reaching Step 9 in a diagnostic mode after the marker was cleared at Step 7: `<round-number>` is the **highest round on the ledger** — the round just closed — and `<RUN_TIMESTAMP>` for the cleanup glob below is reconstructed from that round's Runtime column; if `<RUN_TIMESTAMP>` cannot be reconstructed, skip the cleanup — the `/tmp/skill-tracer-prompts` files are ephemeral and harmless.) Clean up the staged prompts first — `rm -f /tmp/skill-tracer-prompts/*-<RUN_TIMESTAMP>.txt /tmp/skill-tracer-prompts/spec.json` (every non-handoff **trace** exit lands at Step 9, so this covers convergence AND the `--one-round`/`--verify-only` diagnostic modes; the opt-in-handoff and 10-round-stop paths already remove them before exiting. `--audit-fixes` does **not** reach Step 9 — it terminates after its report per Step 1(b), and it stages **no** `/tmp/skill-tracer-prompts` files (it dispatches the audit agent directly, not via `stage_cold_prompts.py`), so it neither needs this cleanup nor renders; the `*-<RUN_TIMESTAMP>.txt` glob sweeps both the staged `<direction>-<RUN_TIMESTAMP>.txt` prompts AND the `<direction>-report-<RUN_TIMESTAMP>.txt` report files written in Step 5 — safe to sweep before rendering, since `render_ledger.py` reads only the ledger, never the report temp files). Then render the ledger HTML: `python3 ~/.claude/skills/skill-tracer/scripts/render_ledger.py ~/.claude/skill-tracer-audit-ledger/<target-skill-name>.md --open` (the `render_ledger.py` path is **skill-tracer's own install location** — `~/.claude/skills/skill-tracer/scripts/`, not the *target* skill's `<skill-root>`; if skill-tracer itself is installed elsewhere, e.g. a plugin dir, use that location — the directory the running skill-tracer's own SKILL.md/scripts were loaded from (the orchestrator is executing skill-tracer, so this path is known from the invocation, not a value to look up). Invoke with `python3` and the script's absolute path, like every other script in this skill; pure-stdlib; the ledger path is the only required argument — `--label`/`--config` are for other ledger layouts, the skill-tracer ledger uses the defaults). It writes the **ledger path with its final suffix replaced by `.html`** (`with_suffix(".html")`) — for the canonical `<target-skill-name>.md` ledger that is `<target-skill-name>.html`, beside the ledger (replaced, not appended) — and opens it. A headless environment (no browser to open) is **not** an error: the HTML is still written and the script exits **0**, printing a benign `(could not open in browser: …)` note. That exit-0 case is distinct from the script's **non-zero** exits (1–4, where the HTML may NOT have been written) — the terminal-cosmetic row of the "Script error-handling contract" table owns the per-exit decode; surface the `Error:` line and hand over the textual result regardless. Then hand the user:
- A short summary: skill traced, rounds taken, final state. In full-convergence mode this is **converged** (Condition A reached via Step 8) or **stopped at round N**. In the diagnostic modes (`--one-round` / `--verify-only`), which exit to Step 9 without passing Step 8, report it as **clean (diagnostic snapshot)** when the round raised **zero clusters**, or **N clusters found (diagnostic snapshot)** otherwise — never "converged" (a full-mode determination only). Count by re-reading the ledger and filtering rows with Round == `<round-number>` and Phase `TRACE` (each such row is one cluster raised — applied `FIX`/`STRENGTHEN`/`USER-PAUSE` in `--one-round`, `would-*` in `--verify-only`): "N clusters found" = that count, "clean" = zero. (Diagnostic modes skip Step 2.5, so they write no `REVIEW` rows — "zero clusters" and "zero `TRACE` rows" coincide here.)
- Per round: raw flag count, number of clusters after Step 5 grouping, and the ledger — every flag-ID mapped to its address. Aggregate counts from the round-summary comments Step 7 wrote.
- The round-on-round **regression trace** (per `references/address-decision.md` "Convergence check between rounds — test flag identity, not count"). Raw counts may stay flat or tick up across rounds due to cascade (round-N fixes opening previously-invisible gaps) — informative but secondary; the load-bearing metric is whether any prior-round Root cause re-appears in a later round (a regression).
- Any unresolved USER-PAUSE clusters (these don't block Step 6 — other clusters proceed — but resolution is required before convergence; surface for the user's decision). **This bullet is emitted in every mode** — full-convergence (where an unresolved USER-PAUSE blocks Condition A) AND the diagnostic modes (`--one-round`/`--verify-only`, where a `would-USER-PAUSE` or applied `USER-PAUSE` row was written): a diagnostic snapshot that recorded a pause still surfaces it here, even when reported "clean (diagnostic snapshot)" for cluster count.

If converged, suggest two next steps: (1) **a final code-review pass** — `Suggested next: /code-review max <skill>` — a full-depth local pass over the now-converged skill, to catch anything the cold trace's correctness lens doesn't cover (reuse / simplification / efficiency); and (2) the ship phase — `then: /skill-publisher <skill>` (polish + portability + CCVW audit + PR). WHY suggest code-review again after running it at round 1: the round-1 pass reviewed the pre-trace skill; convergence may have rewritten anchors, scripts, and references across many rounds, so a fresh review of the *converged* artifact is worthwhile. skill-tracer is terminal for correctness; the code-review pass is advisory and the publisher is where release work happens.

The skill is now traced.

---

## Information-flow design awareness

The trace agents flag hidden-information leaks (the "hidden-information leak" category present in each of forward, backward, and executor). When considering these flags, recognize that information-flow design is a deliberate skill property. The four design boundaries below are exhaustive — every leak ISSUE traces back to one:

- Cold dispatches must not see prior fix history.
- Sub-agent briefs are typically self-contained — orchestration details are hidden by design.
- The orchestrator's internal tracking should not leak into child task prompts.
- An actor's contract — "you receive only X, Y, Z" — must hold at the assembly point.

Step 6's address rules apply as usual (default to FIX; STRENGTHEN only for legitimate cases per `references/address-decision.md`). Often the fix is to remove the leak from the assembled prompt; sometimes the design shifted and the WHY needs strengthening at the boundary.

---

## Script error-handling contract

The steps above consume each script's **success** output (exit 0 + the JSON/expected stdout). This section is the executor's uniform rule for the **non-zero** exits. **A non-zero exit is never silently ignored** — classify it and act:

- **Invocation error** — the orchestrator called the script wrong (a `--file` path it should have written is missing, a malformed `--spec`); typically no useful stdout (often no JSON at all). Fix the invocation (re-write the missing temp file, correct the path/spec) and re-run. Do NOT treat it as a content signal or abort the trace.
- **Content signal** — the script ran fine and is reporting something about the data (drift, no-PRE-FLIGHT, a rejected row). Act per the documented meaning.
- **Broken-ledger abort** — the ledger itself is unreadable/missing where it must exist. Stop and tell the user; the trace cannot proceed.
- **Terminal-cosmetic** — a render failure at the very end. Surface the error and hand over the textual result anyway; the trace is already done.

The four classes above are the rule. The table below is the **single per-script home** that applies them — each row maps one script's non-zero exit(s) to its class + action. Step call-sites describe the success path (plus, where it's load-bearing, the one critical exit inline — e.g. `ledger_state.py` exit 2 → stop) and defer the full per-script exit semantics here, so they live once in this table rather than being re-derived at each call-site.

| Script (step) | Non-zero exit | Class → action |
|---|---|---|
| `ledger_state.py` (1a) | 2 = ledger path is a directory / unreadable | broken-ledger → stop; tell the user the ledger at `<path>` is unreadable and cannot be auto-recovered; do not dispatch |
| `recover_dispatch.py` (1a, rule 1) | 1 = one or more directions missing / 2 = project dir or newest JSONL not locatable | content → handle per `references/recovery-protocol.md` rule 1: exit 1 → re-dispatch only the `missing` directions (note `missing` folds two cases — a never-dispatched direction AND one present in `found` with `result_line: null`; `missing` is authoritative for both, so never consume a `found`-with-null direction); exit 2 → re-dispatch all three cold (nothing to recover), tell the user if the project dir looks wrong |
| `stage_cold_prompts.py` (4) | 1 unfilled slot **or a file missing after write** / 2 usage error | invocation → fix per `references/dispatch-protocol.md` "Failure handling" (read the JSON `unfilled` vs `missing` to tell which exit-1 cause it is); do NOT dispatch |
| `check_drift.py` (5) | **1 = drift or a now-missing file** (the JSON `drift`/`missing` lists are non-empty) | content → the round is stale wholesale: re-run Steps 2–4 for **all three** directions (re-enumerate, rebuild, re-stage, re-dispatch); this covers both a line-count/>1-day-date delta and a now-missing in-scope file |
| `check_drift.py` (5) | **2 — two meanings, distinguish by whether JSON printed**: (i) usage error (`--file` missing / no stdin — *no JSON*) or (ii) no PRE-FLIGHT parsed (`checked: 0` — *JSON printed*) | (i) invocation → re-write the report temp file + re-run; do NOT mark the direction unusable · (ii) content → that report has no PRE-FLIGHT block; re-dispatch only that direction |
| `check_drift.py` (5) | 0 **with a non-empty `unparseable` list in the JSON** | content → read the JSON field, not the exit code alone: re-dispatch only that direction (garbled report) |
| `check_results.py` (5) | 1 = `usable: false` (this direction's report is a genuine substance failure: `ABORTED`, no PRE-FLIGHT, or no trailing summary) / 2 = usage error (no JSON printed) | (1) content → re-dispatch **only that direction** (the per-direction `usable` path in Step 5) · (2) invocation → same as `check_drift` (i): re-write the report temp file + re-run; do NOT branch on a `usable` field that was never printed |
| `append_ledger.py append` (6) | 1 `REJECTED:` (a cell has a literal `\|`, an embedded newline, an address not starting with a known kind at a token boundary, a `--phase` outside `KNOWN_PHASES` = TRACE/REVIEW/SIMPLIFY — `PORT-AUDIT` is read-tolerated in old ledgers but **write-forbidden**, it belongs to skill-publisher — or a `--cluster` not matching `^C\d+$`) / 2 ledger not found | (1) content → fix the offending cell (swap `\|`→`/` or a dash, remove the newline, correct the address prefix, fix the `--phase` to one of TRACE/REVIEW/SIMPLIFY, or fix the `--cluster` to `C<n>`) and re-run the write; do NOT leave the cluster unrecorded (it would fail `verify-auditability`) · (2) broken-ledger → stop; tell the user |
| `append_ledger.py close-round` (7) | 2 = ledger not found | broken-ledger → stop; tell the user (the ledger must exist by Step 7) |
| `append_ledger.py verify-auditability` (7) | 1 = a flag-ID is double-counted, missing from the ledger, or present-but-absent-from-`--expect` (the JSON `duplicates` / `missing_from_ledger` / `unexpected_in_ledger` fields say which, and the `error` string concatenates both messages when both hold at once) / 2 = ledger not found | (1) content → reconcile the round's rows per Step 7 item 3 before proceeding (read all three JSON fields, not just the `error` string) · (2) broken-ledger → stop |
| `render_ledger.py` (9) | 1 not-found / 2 read (also `--config` not-found or invalid-JSON, but Step 9 passes no `--config`, so only the ledger-read failure is reachable here) / 3 parse-or-render / 4 write | terminal-cosmetic → surface the `Error:` line to the user and hand over the textual result; do NOT block or re-run the trace (a not-found at Step 9 means the just-written ledger is unexpectedly absent — still terminal-cosmetic: the trace is already done, report the textual result) |

---

## References

**Direction definitions** (per Step 3's `[INLINED_TRACE_DEFINITION]` slot):
- `references/forward.md` — claims-to-reality verification.
- `references/backward.md` — producer-to-consumer verification.
- `references/executor.md` — line-by-line ambiguity verification.

**Mechanism specs** (Steps 1, 4, 5, 6):
- `references/recovery-protocol.md` — Step 1 recovery state machine, in-flight markers, atomic-write protocol, runtime constraint.
- `references/dispatch-protocol.md` — Step 4 prompt staging (`stage_cold_prompts.py`, the single stager), RUN_TIMESTAMP format, same-turn rationale, self-check + discard-and-retry.
- `references/ledger-format.md` — Step 5 ledger location, header, format, F/B/E flag scheme, cluster grouping, PRE-FLIGHT drift test, exact-line-numbers, anti-double-counting.
- `references/address-decision.md` — Step 6 bias-toward-FIX, anti-patterns, legitimate STRENGTHENs, three address formats, PAUSE criteria, regression-vs-cascade.
- `references/audit-fixes.md` — the `--audit-fixes` diagnostic mode: scope (rounds since last convergence), the cold audit-agent prompt template, and report handling.

**Per-skill vocabulary:**
- `references/glossary.md` — skill-tracer-specific terms; see also `~/.claude/skills/skill-creator-ccvw/references/ccvw-glossary.md` (precedence: Step 3).

**Tooling:**
- `scripts/render_ledger.py` — pure-stdlib HTML renderer for the audit ledger; invoked at Step 9 as `render_ledger.py <ledger-path> --open` (the ledger path is a required positional argument).

**See also** (siblings):
- `code-review` — full-depth local code review (`/code-review <effort>`, effort `low`→`max` local + `ultra` cloud; `--fix` applies findings, `--comment` posts to a PR). Invoked programmatically via the `Skill` tool — `/code-review max` ≡ `Skill(skill: code-review, args: max)`, the same invocation. **Invoked by skill-tracer** at Step 2.5 (round-1 pass, `max`, no `--fix` — findings flow through the considered-fix gate) and suggested again at Step 9 after convergence.
- `skill-creator-ccvw` — build phase (scaffolds the structure; suggests trace at iterate-end).
- `skill-publisher` — ship phase (polish + CCVW audit + portability + PR; the simplify pass + CCVW audit that used to live in tracer moved there).
- `deep-research`, `pr-review-toolkit` — adversarial-verify lineage; see HISTORY.md inspirations.
- `ralph-loop` — the inline-loop shape Step 7 specializes.
- `feature-dev` — defer here when the target is mid-feature-development.
