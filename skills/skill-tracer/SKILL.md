---
name: skill-tracer
description: "Cold-parallel trace of any skill via three direction agents (forward, backward, executor) reading the target independently — forward verifies claims against reality, backward verifies producer outputs have documented consumers, executor verifies the line-by-line path is unambiguous. The orchestrator collects ISSUE reports, applies considered fixes preserving the skill's intent, and re-dispatches cold until all three return clean (Condition A). The TRACE phase of the build → trace → ship ecosystem — correctness only; it does NOT polish prose, check portability, audit CCVW compliance, or run a simplify pass (those are skill-publisher's). Use whenever the user wants to trace, audit, check, review, or validate a skill — 'trace skill X', 'audit X for issues', 'is skill X clean', '/skill-tracer' invocations, or proactively after the user just created or edited a skill. Defers to feature-dev when the target is mid-feature-development."
license: MIT
compatibility: Claude Code 2.0 or newer
metadata:
  tier: claude-users
  created: "2026-05-27"
  created-by: Vaikri-costume
  parent-version: 2.0.1
  intended-audience: claude-users
allowed-tools:
  - Agent
  - Read
  - Edit
  - Write
  - Bash
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

**Not skill-tracer's job** (moved to other phases of the build → trace → ship ecosystem): prose polish / simplify pass, portability checks, CCVW Word/Spirit audit, attribution validation, security scan — those are skill-publisher's (ship phase). Efficiency + accessibility quality checks — those are skill-creator-ccvw's (build phase). skill-tracer finds bugs; it does not do quality or release work.

---

## When to invoke

- Slash command: `/skill-tracer <skill-name>` (or `/skill-tracer <absolute-path-to-skill-directory>`)
- Natural language: "trace skill X", "audit X for issues", "check skill X", "is skill X clean", "review skill X", "validate skill X"
- **Proactively** after the user just created or significantly edited a skill — offer to run a trace.
- **Mid-feature-development skills**: defer to feature-dev first. If the skill has commits in the last hour or the user says "I'm still building this", suggest feature-dev's explore → architect → implement → review pipeline; re-invoke skill-tracer once the skill is structurally complete. Tracing mid-development flags work-in-progress as defects, costing rounds feature-dev would resolve more cheaply.

After convergence, skill-tracer suggests `/skill-publisher <skill>` (the ship phase) — that's where polish + portability + CCVW audit + PR live.

---

## Prerequisites

The target skill must exist as a directory containing at least a `SKILL.md`. The orchestrator needs `Read`/`Edit`/`Write` on every file in the tree, `Agent` for parallel cold dispatch, and `Bash` for file enumeration. No external services. No network.

<!-- "CCVW" is an intentional unexpanded label naming the skill-creator-ccvw ecosystem. Treat as a proper noun; expansion reserved for a later public release. -->

---

## Runtime constraint — top-level invocation only

skill-tracer requires `Agent` to dispatch the three cold-parallel trace agents (Step 4). `Agent` is available only in the **top-level** Claude session — never from inside a nested Agent call. Full details and abort behaviour: `references/recovery-protocol.md` "Runtime constraint — top-level invocation only". If the orchestrator detects it's a subagent (Agent unavailable), stop and tell the user; do not simulate.

---

## The four invariants

1. **Cold-trace.** Each agent dispatch is independent — no sibling mentions, no fix-log carry-over, no "what changed since last round" preamble, **no target README or HISTORY**. The cold agents read SKILL.md + scripts + references for correctness; they never see the target's intent docs. Cold means cold. (This is the adversarial-verify pattern `deep-research` and `pr-review-toolkit` use; cold parallelism is its structural enforcement.)
2. **Considered-fix.** Between rounds, the orchestrator weighs each ISSUE against the target skill's documented intent (read from the target's README `## Intent` — orchestrator-side only) and load-bearing decisions. A fix is applied only when it preserves intent. Random "make the tracer happy" fixes are forbidden — they destroy the skill's design.
3. **No-orphan-flag.** Every ISSUE is addressed by FIX, STRENGTHEN, or USER-PAUSE — and the address must land inside the skill, not an external log. If a future cold round re-raises a previously addressed ISSUE, the address was incomplete — investigate and strengthen further.
4. **WHY-strengthening.** When an ISSUE flags a missing WHY for an intentional design decision, the fix is to **add the WHY**, not to remove the rule. Most common operational form of invariant 3.

---

## Invocation modes

| Mode | Invocation | What runs |
|---|---|---|
| **Full-convergence** (default) | `/skill-tracer <skill>` or natural language | Full loop: Steps 3–8 until Condition A (all three agents return clean in one cold round) |
| **Single-round** | `/skill-tracer <skill> --one-round` | One cold round through Steps 3–7 (round-close runs), then Step 9 — then stop. Diagnostic snapshot; no loop-back. |
| **Verify-only** | `/skill-tracer <skill> --verify-only` | One cold round through Steps 3–7 (round-close runs), then Step 9, applying **no fixes** — produces a ledger of would-FIX / would-STRENGTHEN / would-USER-PAUSE addresses; no loop-back. |

(All three modes run **Steps 1–2 first** — Step 1 recovery + Step 2 enumeration are entry-universal, on every invocation. The step spans in this table describe each mode's loop body from Step 3 onward, not the whole run.)

---

## Workflow

*Whenever any script invoked below exits **non-zero**, consult the **"Script error-handling contract"** section (near the end of this document) — the steps below describe each script's success path; that section is the executor's uniform rule for every non-zero exit.*

### Step 1. Resolve target and mode — read intent — check for in-flight recovery

**Mandatory first action of every invocation**, including post-compaction resume. (Compaction: Claude Code's automatic context compression when the window fills — it restarts the session, requiring all state to be re-read from disk.) No path bypasses Step 1. Reasoning from memory about what was in-flight pre-compaction is prohibited — re-read state from disk every time.

**Orchestrator state initialization (do at invocation start):**
- `<Runtime>`: ISO-8601 UTC now, `YYYY-MM-DDTHH:MM` (see recovery-protocol.md). Used in all in-flight markers + ledger rows this session.
- `<RUN_TIMESTAMP>`: `<Runtime>` with every `:` replaced by `-` (filesystem-safe). Used in the staged-prompt filenames (Step 4) and the tmp-cleanup glob (Steps 7 + 9). Derivation detail: `references/dispatch-protocol.md` "RUN_TIMESTAMP format".
- `<round-counter>`: 0. Incremented by 1 at the start of each round's Step 7. Drives the 10-round ask gate (separate from the cumulative ledger Round column).
- `<gate-dismissed>`: false. Set true when the user answers `y` at the 10-round gate; thereafter the gate check is skipped this invocation.
- `<stop-after-round>`: integer or `null`. Set in (b) — specifically its stop-after-round half, which runs *after* (a) (see the Order block below) — if the user says "just round N then stop" or equivalent.
- `<target-intent>`: the text of the target's README `## Intent` section, or `null` if no README / no Intent section. Read at (c) below. Used by Step 6's considered-fix; the cold agents never see it.
- Populated as steps run: `<target-skill-name>`, `<mode>` (set at (b)); `<round-number>` (set at (a)); `<dispatch-set>` = `["forward","backward","executor"]` (constant — always the three core directions); `<cluster-to-address-map>` (populated by Step 6); `<flag-to-cluster-map>` (populated by Step 5).

**Order:** First the **target/mode half of (b)** (gives `<target-skill-name>`, needed for (a)'s ledger path); then **(a) recovery check** (sets `<round-number>`); then the **stop-after-round half of (b)** (needs `<round-number>`); then **(c) read intent**. The two halves of (b) straddle (a) — resolve target/mode before (a), capture stop-after-round after it.

**(a) Recovery check.** Read the ledger at `~/.claude/skill-tracer-audit-ledger/<target-skill-name>.md`. Look for an `in-flight::` line in the header. **First run `scripts/ledger_state.py <ledger>`** (per recovery-protocol.md) — it returns `highest_round` + the parsed marker, which is what distinguishes the absence-rules (rule 4 = no prior rounds vs rule 5 = prior rounds exist). Then **execute the applicable recovery rule from `references/recovery-protocol.md`** — read the five recovery rules; exactly one applies based on marker state + `highest_round` (rules 4 and 5 both trigger on marker-absence, split by whether prior rounds exist). If `ledger_state.py` reports `in_flight.action_valid: false` (a marker present but with an unrecognized keyword), apply recovery-protocol.md's **"Unknown action keyword" fallback** — treat it as `dispatch round-N` and tell the user — the sixth path beyond the five rules. Execute that rule's actions in full (these are illustrative — creating the ledger (rule 4), recovering prior-round results from session JSONL (rule 1), or replacing a handoff marker (rule 3); see `references/recovery-protocol.md` for each rule's complete action set, e.g. rule 2 also rebuilds the in-memory `<flag-to-cluster-map>` (Step 5's flag→cluster map) from the prior session's JSONL). The reference documents the three valid action keywords (`dispatch`/`addressing`/`handoff`), marker format, round-number determination, `<encoded-cwd>` + `<Runtime>` definitions, and atomic-write protocol. After the rule runs, `<round-number>` is set.

**(b) Determine target and mode.**
- `<name>` (bare token or quoted name) → look up `~/.claude/skills/<name>/`.
- `<absolute-path>` → use directly.
- Neither extractable → ask the user for the path.

Verify the directory exists and contains SKILL.md. State the resolved mode at the top of the run. Mode triggers: `--one-round` / `--verify-only` flags select those modes; any other phrasing routes to full-convergence. Store `<mode>` as the flag string or `full-convergence`. Capture stop-after-round (after (a), so `<round-number>` is available): "just round N then stop" / "stop after round N" → `<stop-after-round> = N` (if `<round-number>` is already ≥ N — whether this is a fresh or a resumed invocation — treat as "stop after this round" → `<stop-after-round> = <round-number>`, so by the time Step 7 item 4 runs the `<stop-after-round> == <round-number>` case always holds and there is no unhandled `<`-case); "this round" → `<stop-after-round> = <round-number>`; "one round then stop" → treat as `--one-round` (WHY the split: `<stop-after-round>` is a *resumable* pause inside a full-convergence run — Step 7 writes a `handoff` marker so a later invocation resumes and keeps converging; `--one-round` is the *diagnostic* mode — one cold round, no loop-back, no handoff. Classify the user's stop-phrasing by intent: keep-converging-later → `<stop-after-round>`; one-shot snapshot → `--one-round`). `<stop-after-round>` persists across loop-backs and is re-checked at every round's Step 7 until `<round-number>` reaches it. Any unrecognized `--` flag → ask the user.

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
  ! -name "*.bak*"
```

(The `! -name "README.md"` / `HISTORY.md` / `LICENSE*` exclusions apply at the skill ROOT. A `references/README.md` — unusual — would still be excluded by name; that's acceptable, references docs rarely use those exact names.)

**Executable-but-unusual-extension check (required):** also run `find <absolute-skill-root> -type f -perm -u+x ! -name "*.md" ! -name ".*" ! -path "*/evals/iteration-*/*" ! -path "*-workspace/*" ! -name "*.bak*"` and merge any new paths into `[FILE_LIST]`. A single executable shipped without a conventional extension would otherwise be silently excluded.

Copied-byte-identical scripts get the full trace treatment — paste-from-another-skill does not certify. Write absolute paths to in-memory `[FILE_LIST]`, **excluding SKILL.md itself** — it's carried separately as `[SKILL_PATH]` (Step 3), and the Step-2 `find` lists it, so drop it from `[FILE_LIST]` to avoid duplication. (The cold agents' PRE-FLIGHT gate covers SKILL.md via `[SKILL_PATH]` AND every `[FILE_LIST]` file, so SKILL.md drift is still detected — see `references/prompt-template.md`.) `[FILE_LIST]` is deterministic from on-disk state, so recoverable by re-running this Step after compaction.

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
Substitute the actual `<target-skill-name>` and `<round-number>` values from context. Non-blocking — if the write fails, continue.

**Runtime-constraint check** (once, top of Step 4): confirm `Agent` is in the toolset. If not, abort per `references/recovery-protocol.md`.

**Atomic-write protocol entry** (before any Agent call): write `in-flight:: <Runtime> dispatch round-N` to the ledger header — the placement mechanics (insert the line if no `in-flight::` line exists yet, swap it in place if one does) are in `references/recovery-protocol.md` "Marker write/replace mechanics"; the ledger is guaranteed to exist by now (Step 1(a)'s recovery rule creates it on a first trace). **On the first dispatch of an invocation, if a resume mechanism is available — the harness `/loop` mechanism, or the `mcp__scheduled-tasks__create_scheduled_task` tool present in your toolset (if you can't confirm either is available, treat it as unavailable) — optionally arm the self-perpetuating resume wakeup** (one-shot) per recovery-protocol.md "Self-perpetuating resume wakeup" (read that section now if you are arming — it holds the scheduling-primitive choice and the canonical resume-prompt text) — **ask the user for the first interval** (WHY ask rather than use a fixed default: only the user knows how long this particular trace should run on its own before a safety resume kicks in; the *subsequent* re-arms are a fixed 5h because by then the per-round cadence is established — see recovery-protocol.md "Self-perpetuating resume wakeup"), then it re-arms itself a fixed 5h each firing while a marker is live and self-terminates when Step 8 clears the marker, so a session-limit / closed-session death mid-trace is recovered autonomously instead of leaving an orphaned in-flight marker no one resumes. If no such mechanism is available, skip arming (do not block the trace) — resume then relies on manual re-invocation. (This wakeup-arming ask, when it happens, occurs here — before prompt staging and before the same-turn dispatch block — so it does not split the three-Agent message; the same-turn requirement governs only those three Agent calls.)

**Prompt staging** (before any Agent call): stage all three prompts to `/tmp/skill-tracer-prompts/<direction>-<RUN_TIMESTAMP>.txt` — **prefer** `scripts/stage_cold_prompts.py` (canonical — its invocation, including the required `--spec` JSON of `[{label, slots}]` entries whose `label` is the bare direction name, is in `references/dispatch-protocol.md` "Prompt staging procedure"); the inline Bash+Python loop in `references/dispatch-protocol.md` is an equivalent fallback. If the stager exits non-zero (a missing file after write, or an unfilled `[SLOT]`), do NOT dispatch — see `references/dispatch-protocol.md` "Failure handling" to resolve first.

**Dispatch** (single assistant message, three Agent calls):

| Parameter | Value |
|---|---|
| `description` | one of exactly `Forward trace of <skill>` / `Backward trace of <skill>` / `Executor trace of <skill>`, where `<skill>` is the **bare `<target-skill-name>`** and the literal pattern `<Direction> trace of <skill>` is kept exactly (recovery rule 1's `recover_dispatch.py` matches `^(Forward\|Backward\|Executor)\s+trace\s+of\s+(.+)$` and compares the captured name to `<skill>` by stripped equality — so both rephrasing the `<Direction> trace of` prefix and using a path (rather than the bare skill name) would make the dispatch unrecoverable) |
| `subagent_type` | `general-purpose` |
| `prompt` | `Read /tmp/skill-tracer-prompts/<direction>-<RUN_TIMESTAMP>.txt and follow the instructions in that file verbatim. Do not improvise. Do not request the orchestrator's context. Your output is the report the file's instructions ask for.` |

**Same-turn requirement is load-bearing**: all three Agent calls in one assistant message. Serial dispatch would let the orchestrator's view of agent 1's result bias agent 2's prompt — the cold-parallel invariant fails. Rationale, self-check, and discard-and-retry recovery: `references/dispatch-protocol.md`.

After all three dispatches, wait for all three tool_results in parallel.

### Step 5. Collect ISSUE blocks and map to root causes

Each agent returns:
- A `PRE-FLIGHT` line per file (`PRE-FLIGHT <path>: <line_count> lines, last edited <yyyy-mm-dd>`). Run the drift test per `references/ledger-format.md` "PRE-FLIGHT drift test": the agent results arrive in-context (not on disk), so write each report to a temp file (e.g. `/tmp/skill-tracer-prompts/<direction>-report-<RUN_TIMESTAMP>.txt`) and pass it to `check_drift.py --file <report>` (or pipe its PRE-FLIGHT lines via stdin). Any line-count or date delta means the cold-trace property was violated (files edited between dispatch and now) → re-run Steps 2–4 for **all three** directions (the whole round is stale — Step 2 re-enumerates, Step 3 rebuilds the prompts from the fresh file list, Step 4 re-stages + re-dispatches), not just the drifted one. **`check_drift.py`'s other non-zero signals are single-direction, not all-three** (per `references/ledger-format.md`): exit **2** *with JSON printed* (`checked: 0` — no PRE-FLIGHT lines parsed, a malformed/aborted report) or a non-empty `unparseable` list even on exit 0 (garbled PRE-FLIGHT lines) means *that one report* is unusable, not that the files drifted — re-dispatch only that direction, the same single-direction response as `check_results.py` returning `usable:false` (below). (A *usage-error* exit 2 — **no JSON printed**, e.g. the report temp file is missing — is an orchestrator invocation bug, not a content signal: re-write the report file and re-run, do NOT re-dispatch; see "Script error-handling contract".) **Precedence when a report shows both:** exit 1 (drift/missing) always wins — run the all-three re-run regardless of any `unparseable` entries (a drifted round is stale wholesale, so the single-direction signal is moot). The exit-2 / non-empty-`unparseable` single-direction path applies only when there is no drift (exit 2, or exit 0 with a non-empty `unparseable` list).
- Zero or more `ISSUE` blocks (tag, file path, `Claim:`, `Target:`).
- A trailing `No issues found` or `No of issues found:: N`.

**Order the two re-dispatch checks: drift first, then `usable`.** The drift test (above) and this `usable` check differ in scope — drift means files changed mid-round, so the whole round is stale (re-run Step 2 + Step 4 for ALL three per `references/ledger-format.md`, and skip the per-direction check this round); `usable: false` is a single-direction substance failure. Run drift first; only if there's no drift, apply the per-direction `usable` check.

**Validate each direction's report with `scripts/check_results.py`** (`--file <report> --direction forward|backward|executor`, where `<report>` is the same per-direction temp file written for the drift test above — `/tmp/skill-tracer-prompts/<direction>-report-<RUN_TIMESTAMP>.txt`, already on disk) — it returns `usable` + `authoritative_count` per direction. Re-dispatch a direction **only when `usable` is false** — a genuine substance failure: `ABORTED`, no PRE-FLIGHT at all, or no trailing summary at all.

**A count mismatch is NOT a re-dispatch trigger.** If the agent's trailing `No of issues found:: N` disagrees with the actual number of `ISSUE` blocks, that's a clerical miscount, not a substance failure — the ISSUE blocks themselves (tag/Claim/Target) are the findings and are right there. **Recount from the actual blocks and proceed** (use `check_results.py`'s `authoritative_count`); log the discrepancy, don't reject. Re-running a whole direction's trace because it miscounted its own blocks wastes a full agent dispatch for nothing.

Re-dispatch procedure (only for the genuinely-unusable directions): same round-number + Runtime, overwrite the staged prompt file (the filename is identical because RUN_TIMESTAMP is unchanged), marker stays `dispatch round-N`. (A single-direction re-dispatch is **one** Agent call — the same-turn requirement [Step 4] is moot for a lone call; it governs only the multi-call initial dispatch, where the orchestrator could otherwise let one agent's result bias another's prompt. Issue the one re-dispatch as a normal single Agent call; if two or three directions are independently unusable, re-dispatch those in one same-turn message.)

**Re-dispatch is always a FRESH agent — never resume, continue, or fork the failed one.** The SDK supports resuming a subagent (cheaper via prompt-cache reuse), but that is forbidden here: resuming carries the prior agent's reasoning forward, which violates the cold-trace invariant (each dispatch must read the target with no prior context). And there's no cost penalty for going fresh — a subagent's verbose internal work stays in its own isolated context and never entered the orchestrator's, so a discarded agent costs the orchestrator nothing; re-running the work costs the same whether "resumed" or "fresh." Fresh wins on independence at no extra cost. (Do not "optimize" this by resuming — it silently breaks cold-trace.)

Collect every ISSUE block. Number sequentially per source: `F1, F2, …` (forward), `B1, B2, …` (backward), `E1, E2, …` (executor). These are the only three flag prefixes. Per-source counters are independent. Cluster grouping (three tests + when-in-doubt rule) and the ledger format spec live in `references/ledger-format.md`. The result of Step 5 is two in-memory maps: `<flag-to-cluster-map>` (flag-ID → cluster, consumed by Step 6 for the Flags column + Step 7 item 3 for `verify-auditability`'s `--expect` set; it is per-round and overwritten on each loop-back, so Step 9's cross-round counts come from the ledger + round-summary comments, not this map) and `<cluster-to-address-map>` (cluster → address, populated by Step 6, read by Step 7's anchor check).

### Step 6. Address every cluster — bias toward FIX, no orphan flags

**Atomic-write entry** (before cluster-by-cluster work): replace the marker with `in-flight:: <Runtime> addressing round-N`. This write is **unconditional** — Step 6 is entered every round, *including a zero-cluster (clean) round*, where the cluster loop below simply runs zero iterations; the `addressing round-N` marker is still written, so the marker present at Step 7/8 is uniformly `addressing round-N` on every path (this is what recovery-protocol.md's atomic-write table assumes).

For every cluster, decide and act. No DISMISS branch — every cluster gets FIX, STRENGTHEN, or USER-PAUSE. **Bias toward FIX** is the controlling rule; STRENGTHEN is the narrow exception when the artifact is correct and the cluster reflects intent the trace agents couldn't see. The full address-decision spec — two-step FIX test, two anti-patterns, four legitimate STRENGTHEN cases, three address formats with examples, PAUSE criteria, fix conservatism, regression-vs-cascade convergence check — lives in `references/address-decision.md`.

**Considered-fix uses `<target-intent>`.** Before applying a FIX, check it against the target's documented Intent (from Step 1c): would this change trade away what the skill explicitly optimizes for? If yes → USER-PAUSE (intent-ambiguous; the user decides), not auto-FIX. This is the operational form of the considered-fix invariant. If `<target-intent>` is null (no README Intent), use the SKILL.md description as fallback intent and note in the USER-PAUSE that intent was undocumented.

**Verify-only mode**: decide each cluster's would-be address but apply nothing; write the ledger row with a `would-` prefix — exactly one of `would-FIX` / `would-STRENGTHEN` / `would-USER-PAUSE` (the only `would-` forms `append_ledger.py` accepts; e.g. `would-FIX (...)`). A `would-STRENGTHEN` applies nothing, so it has no post-edit line-range — write it as `would-STRENGTHEN (<file>: <one-line plain-language summary of the text that would be added>)` (a summary, since nothing was applied there is no line-range or quoted text to capture), not the applied-STRENGTHEN `added at <file>:<line-range>` form. Then proceed to Step 7 like any round — Step 7's round-close (item 3: `close-round` + `verify-auditability`) runs on the `would-` rows, and its mode routing (item 4) handles the diagnostic exit (clear marker → Step 9). Verify-only does NOT bypass Step 7 — WHY: Step 9 aggregates from the round-summary comment that only `close-round` (a Step 7 action) writes, and the marker is cleared in Step 7 item 4; bypassing Step 7 would leave Step 9 nothing to read and the marker orphaned.

Write one ledger row per cluster as addressed (not batched), via `scripts/append_ledger.py append` — its argument set (`--runtime`, `--round`, `--phase TRACE`, `--cluster`, `--root-cause`, `--address`, `--flags`) and the row format + single-line / pipe-safe Address constraint are in `references/ledger-format.md`. Target: `~/.claude/skill-tracer-audit-ledger/<target-skill-name>.md`. Populate `<cluster-to-address-map>`.

### Step 7. End of round — loop inline to convergence (default), or hand off and exit

**Step 7 entry order:**
1. **Increment `<round-counter>` by 1.**
2. **Step 0 — verify every STRENGTHEN anchor landed** (skip if this round wrote zero *applied*-STRENGTHEN rows to the ledger — filter the Round-N rows for an Address beginning `STRENGTHEN (added at`; `would-STRENGTHEN` rows apply nothing and are excluded. Read the **ledger** here, not `<cluster-to-address-map>` — a rule-2 mid-addressing resume does not repopulate that in-memory map with pre-interruption addresses, whereas the ledger always holds the round's full set of rows). Re-read the ledger, filter this round's *applied*-STRENGTHEN rows (the same `STRENGTHEN (added at` filter — `would-STRENGTHEN` rows carry no line-range or quoted text, so they are excluded here too), re-read each named file at the named line range, confirm the quoted first-80-chars text is present. If missing (a later FIX overwrote it), re-apply to a stable location and update the row's anchor.
3. **Close the round** with `scripts/append_ledger.py close-round <ledger> --round N` — it appends the round-summary comment (`<!-- Round N total: raw flags A — clusters M — addresses: F FIX + S STRENGTHEN + P USER-PAUSE -->`) recomputed from the round's actual rows, not hand-counted — once per round, in all paths. Then assert the no-orphan-flag invariant with `scripts/append_ledger.py verify-auditability <ledger> --round N --expect "<every flag-ID raised this round, comma-separated>"` (the `--expect` list is the key-set of `<flag-to-cluster-map>` from this round's Step 5 — the map is per-round, overwritten on each loop-back, so the copy in hand is always the round being closed — every flag-ID the agents raised, passed **comma-separated**, e.g. `"F1,B2,E3"`; `append_ledger.py` splits `--expect` on commas, so space-separated values are read as a single flag-ID and spuriously fail the check); exit 1 means **either** (independent of `--expect`) a flag-ID appears in more than one row (double-counted), **or** (against `--expect`) a flag-ID is missing from the ledger (a cluster wasn't recorded) or is present on the ledger but absent from `--expect` (a stale or mistyped flag-ID recorded in a row) — reconcile the rows before proceeding.
4. **Mode routing:**
   - **`--one-round` or `--verify-only`** (the diagnostic modes): write the invocation-total comment, clear the in-flight marker (remove the `addressing round-N` line — Step 6's marker write is unconditional, so `addressing round-N` is what is present; the diagnostic round is complete, nothing is in flight), then proceed to Step 9. No loop-back.
   - **`<stop-after-round>` == `<round-number>`**: if **zero** clusters were raised this round, Condition A already holds → proceed to Step 8 (converged; the stop is moot — do NOT hand off). Otherwise → opt-in handoff (below).
   - **default (full-convergence)**: if zero clusters were raised → Condition A holds → proceed to Step 8. If clusters were raised → **first evaluate the 10-round ask gate** (see Stopping conditions): if `<round-counter>` ≥ 10 and `<gate-dismissed>` is false, ask — on `n` take the gate-stop path, on `y` set `<gate-dismissed>` and continue; otherwise (gate not triggered, or dismissed) → loop-back (item 5). (If `<stop-after-round>` is set to a round not yet reached — `<stop-after-round> > <round-number>` — it does not match the stop case above; the run stays on this default branch, and `<stop-after-round>` persists across the loop-back to be re-checked at each later Step 7 until `<round-number>` reaches it, per the (b) definition above.)
5. **Loop-back** (non-zero-cluster rounds): **increment `<round-number>` by 1** (N→N+1 — the cumulative ledger Round must advance before re-dispatch so the new round's marker, ledger rows, and round-summary all carry N+1; Step 1(a) sets it once and this is the only per-round advance), then re-run Step 2 in full (re-enumerate the file list — prior fixes may have added/removed files), and re-execute Steps 3–4 in the **same session**. Step 4's atomic-write writes the next `dispatch round-<N+1>` marker. The dispatched agents receive the **current** target state — no "what changed" preamble, no fix log, no carry-over. Cold-trace invariant unchanged.

**Invocation-total comment.** Wherever an exit path says "write the invocation-total comment" (Step 7 item 4's diagnostic exit, the 10-round-gate stop, the opt-in handoff, and Step 8 convergence), hand-write `<!-- Invocation <Runtime> total: rounds N..M — raw flags A — clusters X — addresses: F FIX + S STRENGTHEN + P USER-PAUSE -->` per `references/ledger-format.md` "Round and invocation summary comments". It spans the invocation's rounds (N..M), so no single-round script emits it — unlike the per-round summary, which `close-round` writes.

**Stopping conditions** (exhaustive):
- **Converged** (Condition A — all three agents clean in one cold round) → Step 9.
- **10-round ask gate**: when `<round-counter>` ≥ 10 and `<gate-dismissed>` is false, ask `Trace has run <round-counter> rounds without converging. Continue? (y/n)`. `y` → set `<gate-dismissed> = true`, continue (skip the gate for the rest of this invocation). `n` → this is its own terminal path (NOT the opt-in handoff below, though both write a `handoff` marker): write `in-flight:: <Runtime> handoff round-<round-number + 1>` (the marker carries the **cumulative `<round-number>` + 1** — the gate fires on `<round-counter>` but the marker and ledger use `<round-number>`, which diverge on a resumed trace), clean up tmp files (`rm -f /tmp/skill-tracer-prompts/*-<RUN_TIMESTAMP>.txt /tmp/skill-tracer-prompts/spec.json`), write the invocation-total comment, tell the user "Stopped at Round `<round-number>` at your direction. USER-PAUSE clusters (if any) remain — see ledger.", exit.

Compaction mid-round: the atomic-write marker already on the ledger is sufficient; the next invocation reads it and runs the matching recovery rule. No proactive yield.

Per-cluster addressing is fresh-decision per round — the orchestrator owns FIX/STRENGTHEN execution. A regression means the prior fix didn't stick; address it freshly next round (different scope/anchor/approach). USER-PAUSE is decision-based only, never a fix-failure fallback.

**Opt-in self-invoking handoff** (user said "just round N then stop"):
1. Write `in-flight:: <Runtime> handoff round-<N+1>` (keyword `handoff` — recovery-protocol distinguishes it from `dispatch`).
2. Clean up tmp files (`rm -f /tmp/skill-tracer-prompts/*-<RUN_TIMESTAMP>.txt /tmp/skill-tracer-prompts/spec.json`).
3. Write the invocation-total comment.
4. Tell the user: `Round N complete (M clusters: F FIX + S STRENGTHEN + P USER-PAUSE). Re-invoke /skill-tracer <skill-name> for round N+1, or stop here.`
5. Exit.

**Why inline is the default.** Full-convergence is named for the goal: keep going until clean. Asking the user to re-invoke between every round makes convergence the user's job. The inline loop holds the three agent reports in context for one round, then the round-N+1 cold dispatch reads the current file state so prior context is functionally discarded from the agents' perspective. This is the **ralph-loop pattern** (orchestrator-internal iteration with cold child dispatches); skill-tracer's per-round dispatch + addressing is the convergence-bounded specialization with handoff-on-stop as the escape.

### Step 8. Convergence — Condition A only

Convergence requires **Condition A — internal-clean**: all three trace agents return `No issues found` in one cold round.

(Earlier versions also required a Condition B — CCVW-compatibility, via a Step-9 audit. That moved to skill-publisher's ship phase. skill-tracer converges on correctness alone.)

The executor arrives at Step 8 only via Step 7's zero-clusters branch — Condition A is already confirmed clean. Step 8 is the named convergence anchor: clear the in-flight marker (remove the `addressing round-N` line from the ledger header — Step 6 always writes `addressing round-N`, so that is the marker present here; no new marker), write the invocation-total comment (see Step 7's "Invocation-total comment" note — convergence is the canonical "invocation completes" case), then proceed to Step 9.

### Step 9. Present result

Clean up the staged prompts first — `rm -f /tmp/skill-tracer-prompts/*-<RUN_TIMESTAMP>.txt /tmp/skill-tracer-prompts/spec.json` (every non-handoff exit lands at Step 9, so this covers convergence AND the diagnostic modes; the opt-in-handoff and 10-round-stop paths already remove them before exiting; the `*-<RUN_TIMESTAMP>.txt` glob sweeps both the staged `<direction>-<RUN_TIMESTAMP>.txt` prompts AND the `<direction>-report-<RUN_TIMESTAMP>.txt` report files written in Step 5). Then render the ledger HTML (`scripts/render_ledger.py ~/.claude/skill-tracer-audit-ledger/<target-skill-name>.md --open` — pure-stdlib; the ledger path is a required positional argument (no `--label`/`--config` needed — the skill-tracer ledger uses the script's defaults; those optional flags are for other ledger layouts); writes the HTML beside the ledger with the `.md` suffix **replaced** by `.html` (e.g. `skill-tracer.md` → `skill-tracer.html`, not `skill-tracer.md.html`) and opens it; on success prints the output path (`Wrote HTML to <path>`), so a headless environment still gets it; if `--open` cannot launch a browser (e.g. headless) the script still writes the HTML and exits **0**, printing a benign `(could not open in browser: …)` note to stderr after the `Wrote HTML` line — that is success, not an error; on a real error (e.g. the ledger is unreadable) it prints an `Error:` line to stderr and exits non-zero) and hand the user:
- A short summary: skill traced, rounds taken, final state (converged / stopped at round N).
- Per round: raw flag count, number of clusters after Step 5 grouping, and the ledger — every flag-ID mapped to its address. Aggregate counts from the round-summary comments Step 7 wrote.
- The round-on-round **regression trace** (per `references/address-decision.md` "Convergence check between rounds — test flag identity, not count"). Raw counts may stay flat or tick up across rounds due to cascade (round-N fixes opening previously-invisible gaps) — informative but secondary; the load-bearing metric is whether any prior-round Root cause re-appears in a later round (a regression).
- Any unresolved USER-PAUSE clusters (these don't block Step 6 — other clusters proceed — but resolution is required before convergence; surface for the user's decision).

If converged, suggest the next phase: `Suggested next: /skill-publisher <skill>` — the ship phase (polish + portability + CCVW audit + PR). skill-tracer is terminal for correctness; publisher is where release work happens.

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

| Script (step) | Non-zero exit | Class → action |
|---|---|---|
| `ledger_state.py` (1a) | 2 = ledger path is a directory / unreadable | broken-ledger → stop; tell the user the ledger at `<path>` is unreadable and cannot be auto-recovered; do not dispatch |
| `stage_cold_prompts.py` (4) | 1 unfilled slot / 2 usage error | invocation → fix per `references/dispatch-protocol.md` "Failure handling"; do NOT dispatch |
| `check_drift.py` (5) | **2 — two meanings, distinguish by whether JSON printed**: (i) usage error (`--file` missing / no stdin — *no JSON*) or (ii) no PRE-FLIGHT parsed (`checked: 0` — *JSON printed*) | (i) invocation → re-write the report temp file + re-run; do NOT mark the direction unusable · (ii) content → that report has no PRE-FLIGHT block; re-dispatch only that direction |
| `check_drift.py` (5) | 0 **with a non-empty `unparseable` list in the JSON** | content → read the JSON field, not the exit code alone: re-dispatch only that direction (garbled report) |
| `check_results.py` (5) | 2 = usage error (no JSON printed) | invocation → same as `check_drift` (i): re-write the report temp file + re-run; do NOT branch on a `usable` field that was never printed |
| `append_ledger.py append` (6) | 1 `REJECTED:` (a cell has a literal `\|`, an embedded newline, or an address not starting with a known kind) / 2 ledger not found | (1) content → fix the offending cell (swap `\|`→`/` or a dash, remove the newline, correct the address prefix) and re-run the write; do NOT leave the cluster unrecorded (it would fail `verify-auditability`) · (2) broken-ledger → stop; tell the user |
| `render_ledger.py` (9) | 1 not-found / 2 read / 3 parse-or-render / 4 write | terminal-cosmetic → surface the `Error:` line to the user and hand over the textual result; do NOT block or re-run the trace |

---

## References

**Direction definitions** (per Step 3's `[INLINED_TRACE_DEFINITION]` slot):
- `references/forward.md` — claims-to-reality verification.
- `references/backward.md` — producer-to-consumer verification.
- `references/executor.md` — line-by-line ambiguity verification.

**Mechanism specs** (Steps 1, 4, 5, 6):
- `references/recovery-protocol.md` — Step 1 recovery state machine, in-flight markers, atomic-write protocol, runtime constraint.
- `references/dispatch-protocol.md` — Step 4 prompt staging (Python loop + fallback), RUN_TIMESTAMP format, same-turn rationale, self-check + discard-and-retry.
- `references/ledger-format.md` — Step 5 ledger location, header, format, F/B/E flag scheme, cluster grouping, PRE-FLIGHT drift test, exact-line-numbers, anti-double-counting.
- `references/address-decision.md` — Step 6 bias-toward-FIX, anti-patterns, legitimate STRENGTHENs, three address formats, PAUSE criteria, regression-vs-cascade.

**Per-skill vocabulary:**
- `references/glossary.md` — skill-tracer-specific terms; see also `~/.claude/skills/skill-creator-ccvw/references/ccvw-glossary.md` (precedence: Step 3).

**Tooling:**
- `scripts/render_ledger.py` — pure-stdlib HTML renderer for the audit ledger; invoked at Step 9 as `render_ledger.py <ledger-path> --open` (the ledger path is a required positional argument).

**See also** (siblings, not invoked here):
- `skill-creator-ccvw` — build phase (scaffolds the structure; suggests trace at iterate-end).
- `skill-publisher` — ship phase (polish + CCVW audit + portability + PR; the simplify pass + CCVW audit that used to live in tracer moved there).
- `deep-research`, `pr-review-toolkit` — adversarial-verify lineage; see HISTORY.md inspirations.
- `ralph-loop` — the inline-loop shape Step 7 specializes.
- `feature-dev` — defer here when the target is mid-feature-development.
