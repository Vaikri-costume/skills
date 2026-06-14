# Recovery Protocol

How skill-tracer recovers state across compaction, session restart, or any continuation from a prior turn. SKILL.md Step 1 consults this reference when an `in-flight::` marker is present; without a marker, recovery doesn't run and Step 1's bare target/mode resolution suffices.

The recovery state machine is read-only state: it inspects the ledger and (for some rules) the session JSONL to determine where the prior session left off. Once recovery completes, the orchestrator resumes at the step the prior session was interrupted in, with the prior session's Runtime preserved for the round in flight.

---

## In-flight marker format

The in-flight marker is a single line in the ledger header (the line between the title block and the `| Runtime |` table header). Format:

```
in-flight:: <Runtime> <action> round-N
```

There is at most one such line at any time. Parse by splitting on whitespace:
- Field 1: `in-flight::`
- Field 2: `<Runtime>` — ISO-8601 UTC time when the prior session's invocation started, formatted `YYYY-MM-DDTHH:MM` (no whitespace inside; safe to split on whitespace)
- Field 3: `<action>` — one of `dispatch` / `addressing` / `handoff` (see Action keywords below)
- Field 4: `round-N` — the round number this state applies to

---

## Action keywords

Three distinct keywords with distinct meanings — never overloaded. **This list is closed**: only these three values are valid; any other value triggers the "Unknown action keyword" fallback below.

- **`dispatch`** — mid-dispatch interrupted: Agent calls were issued in the prior session but the orchestrator did not finish recording all tool_results. Recovery rule 1 applies.
- **`addressing`** — mid-addressing interrupted: cluster-by-cluster Step 6 work was underway when the prior session ended. Recovery rule 2 applies.
- **`handoff`** — clean end-of-round self-invoking handoff written by Step 7 to signal "the next invocation should start round N from a fresh dispatch." This is NOT an interruption; the prior session completed all of round N's work and stopped at the end-of-round handoff. Recovery rule 3 applies.

**Unknown action keyword (typo, future variant, manual edit)**: treat as if it were `dispatch round-N` (the most conservative recovery — re-checks the JSONL for prior dispatches; if none found, re-dispatches cold). Tell the user: "Unknown in-flight action `<word>` at round N — treating as dispatch. If you intended a different recovery, edit the marker before re-invoking."

The distinct keyword is load-bearing: the recovery rules below branch on it. Never write `dispatch round-N` at end-of-round (use `handoff round-N+1` — Step 7), and never write `handoff round-N` mid-dispatch (use `dispatch round-N` — Step 4's atomic-write).

---

## `<Runtime>` definition (used throughout)

ISO-8601 UTC time when the invocation started, formatted `YYYY-MM-DDTHH:MM`. Generate from current wall-clock at invocation start. Use the same value in every in-flight marker the orchestrator writes during this session, and in every ledger row written for clusters addressed in this session — except where a recovery rule below directs otherwise (rules 1, 2, 3 preserve the prior session's Runtime for resumed rounds).

---

## `<encoded-cwd>` definition

The current working directory with `/` replaced by `-` and a leading `-` prepended.

Example: `/Users/yourname/Library/CloudStorage/OneDrive-Personal` → `-Users-yourname-Library-CloudStorage-OneDrive-Personal`

The Claude Code harness encodes session JSONL directories this way under `~/.claude/projects/<encoded-cwd>/`.

---

## Round number determination

Every invocation, before any other action: read the ledger state with `scripts/ledger_state.py <ledger-path>` rather than hand-scanning. It returns JSON with `highest_round`, `next_fresh_round` (= highest + 1), the parsed `in_flight` marker (`{runtime, action, round, action_valid}` or null), `last_round_clean`, and `row_count` — the two deterministic Step-1 reads (round scan + marker parse) in one call:

```bash
python3 ~/.claude/skills/skill-tracer/scripts/ledger_state.py ~/.claude/skill-tracer-audit-ledger/<skill>.md
```

It counts only data rows (regex allows the optional Phase column, so both current 7-column and pre-Phase 6-column back-compat rows match) and does NOT miscount the `<!-- Round N total: ... -->` summary comments (the easy-to-miss trap — those comments contain "Round N"). An absent/empty ledger returns `highest_round: 0, next_fresh_round: 1`.

The script READS state; it does NOT select the recovery rule — that judgment (marker presence + keyword + clean-vs-not) stays with the orchestrator over the returned JSON:
- Resuming an in-flight round N (per recovery rules below) → continue at Round N (from `in_flight.round`).
- Starting fresh → `next_fresh_round`.
- `action_valid: false` → the "Unknown action keyword" fallback below.

---

## Pre-Phase-column ledgers (back-compat)

Ledgers written before the Phase column existed have 6 columns (`Runtime | Round | Cluster | Root cause | Address | Flags`) instead of 7. To stay compatible:

When parsing, first detect column count by matching the header row (line starting `| Runtime | Round`). If 6 columns, treat all existing rows as `Phase=TRACE` implicitly. Migrate the ledger to 7 columns the first time this skill writes a new row (insert `TRACE` into the Phase column for every existing row in the same Edit that adds the new row). Don't migrate without writing — a no-op migration creates an in-flight artifact the next cold trace flags as orphan state.

---

## Recovery rules (mutually exclusive — exactly one applies per invocation)

1. **`in-flight:: <Runtime> dispatch round-N`** — mid-dispatch interrupted. Recover the prior session's dispatch results from the session JSONL with `scripts/recover_dispatch.py` rather than hand-parsing raw JSONL (hand-scanning is silently error-prone — easy to grab a discarded retry or a backgrounded agent's launch-ack instead of the real result):

   ```bash
   python3 ~/.claude/skills/skill-tracer/scripts/recover_dispatch.py --skill <skill-name>
   # auto-locates the newest JSONL under ~/.claude/projects/<encoded-cwd>/; override with --jsonl <path>
   ```

   It matches the three constant description strings (`Forward trace of <skill>`, `Backward trace of <skill>`, `Executor trace of <skill>` — skill-name match filters out unrelated dispatches), pairs each `tool_use` to its `tool_result` (handling the background-agent `<task-notification>` case), applies **most-recent-wins** so a discard-and-retry selects the retry not the stale dispatch, and returns JSON: `found` (per-direction tuid + result_line), `missing` (which of forward/backward/executor have no usable result), and `result_text` (the recovered report per direction). Exit 0 = all three recovered; exit 1 = one or more missing; exit 2 = the project dir or newest JSONL couldn't be located (nothing to recover from) — re-dispatch all three cold, and tell the user if the project dir looks wrong.
   - Expected count is always three — `<dispatch-set>` is the constant `[forward, backward, executor]` (skill-tracer is correctness-only; no per-round variation). The script's `missing` list IS the set to re-dispatch.
   - **Before consuming the recovered results, run the PRE-FLIGHT drift test** — pipe each direction's `result_text` to `scripts/check_drift.py` (see ledger-format.md). If any file's current line count or mtime differs from the recovered PRE-FLIGHT line, the cold-trace property has been violated (target files were edited between the prior dispatch and now), so the recovered results reflect stale state — discard and re-dispatch cold. (`recover_dispatch.py` LOCATES + PAIRS; `check_drift.py` validates freshness; the discard-vs-trust + which-directions-to-re-dispatch decision stays with the orchestrator.)
   - If PRE-FLIGHT confirms no drift, resume at Step 5 with the recovered results. If any tool_result is genuinely missing, re-dispatch only the missing direction(s) — the others are cold-valid. A direction that was dispatched but whose result wasn't recovered appears in BOTH `found` (with `result_line: null`) and `missing`; `missing` is authoritative (it IS the re-dispatch set) — re-dispatch it, do not treat its `found` entry as a recovered result.
   - Rows written for this resumed round use the **prior session's Runtime from the in-flight marker** (preserves round-as-cohesive-unit). Round = N from the marker.

2. **`in-flight:: <Runtime> addressing round-N`** — mid-Step-6 interrupted. Filter the ledger's rows by Round = N — the present rows are the addressed clusters. The `<flag-to-cluster-map>` (Step 5's flag→cluster map) is in-memory only, so this recovery must rebuild it: re-extract the trace agents' reports from the prior session's JSONL (rule 1's JSONL-parse procedure applies), then re-run Step 5's clustering procedure cold. Match the re-derived clusters against the addressed rows by Root cause + Flags — the first re-derived cluster whose row is not on the ledger is the next one to address. If no Round = N rows exist yet (interruption between the `addressing` marker write and the first row append), start at C1 of the re-derived cluster set. Rows for remaining clusters use the **prior session's Runtime** (same round, same Runtime). Round = N from the marker.

3. **`in-flight:: <Runtime> handoff round-N`** — prior session completed cleanly at Step 7 and signalled the next invocation to start round N. Replace the marker with `in-flight:: <current Runtime> dispatch round-N` (this session's atomic-write before the upcoming dispatch) and proceed to Step 3 → Step 4 for round N. Round = N from the marker. Use **current invocation's Runtime** for the new round's ledger rows.

4. **No `in-flight::` is present and no prior rounds exist (ledger absent or empty)**: this is the skill's first trace. Round = 1 (set `<round-number> = 1` — the same variable rule 5 sets explicitly; SKILL.md Step 1's "after the rule runs, `<round-number>` is set" depends on this assignment). Use current invocation's Runtime. Create the ledger at `~/.claude/skill-tracer-audit-ledger/<target-skill-name>.md` using ledger-format.md "Header template (new ledger)" format. Proceed to Step 2 → Step 3 → Step 4 (Step 4 will write the first in-flight marker before dispatching agents).

5. **No `in-flight::` is present but prior rounds exist in the ledger**: Before proceeding on either path (clean or not-clean), **`<round-number>` = highest existing Round + 1 is set immediately here** — this IS rule 5's action at Step 1(a), computable from `ledger_state.py`'s `highest_round` with no need for later steps (this is what "`<round-number>` set at (a)" means in SKILL.md). The in-flight marker is written later, at Step 4's atomic-write (`dispatch round-<N+1>`), after Steps 2–3 run — but it carries the round number already set here. So for the not-clean sub-case: set `<round-number>`, then proceed to Step 2 → Step 3 → Step 4. For the clean sub-case (user accepts): same path. Ambiguous state — the prior session either completed all its rounds (converged or stopped) but never wrote a handoff marker, OR crashed in a way that lost the marker. To distinguish: check whether the most recent prior round was clean (see "Definition: 'round was clean'" below). If clean → ask the user whether to start a fresh round (the trace previously converged; new round may be unnecessary). If user accepts (y): start a fresh round at Round = (highest existing Round + 1), using current invocation's Runtime, and proceed to Step 2 → Step 3 → Step 4. If user declines (n): exit Step 1 without proceeding (see "Definition: round was clean" below for the exact exit). If not clean → start a fresh round at Round = (highest existing Round + 1) using current invocation's Runtime. Do NOT ask about "fresh or continue" in the not-clean case — prior unaddressed clusters in the ledger combined with no handoff marker is a clear signal that work remains.

---

## Definition: "round was clean"

A round is clean if its round-summary comment in the ledger shows `raw flags 0` (format: `<!-- Round N total: raw flags 0 ... -->`). The summary comment is the single authoritative signal — written by Step 7 after the round completes, so its presence with `raw flags 0` means the round ran, found zero issues, and ended cleanly. `ledger_state.py` computes exactly this as its **`last_round_clean`** field (`true` / `false` / `null` when the highest round has no summary, i.e. cleanliness unknown); the orchestrator reads that field directly rather than re-scanning the comment by hand — this definition is what the field means.

If the summary comment is absent for the highest Round value present, the round did NOT end cleanly (Step 7 never ran), regardless of whether data rows exist — treat as not-clean and use rule 5's not-clean sub-case.

The most-recent-prior-round = highest Round value present in any data row OR round-summary comment (a converged round writes a `raw flags 0` summary but NO data rows, so keying on data rows alone would miss it; `ledger_state.py` counts both and returns that round as `highest_round`).

**If user declines to start a fresh round** (rule 5, clean case): exit Step 1 without proceeding. Tell the user "Trace state at Round N is trusted as-is; re-invoke /skill-tracer when you want a new cold round." Do not modify the ledger or write any marker.

---

## "Ask the user" rules — when, and why each path takes its default

- Rule (1b) of Step 1 (in SKILL.md — not duplicated here) asks the user when the invocation's target is path-ambiguous because the invocation itself didn't carry enough information (user-input gap; only the user can disambiguate).
- Rule 5 above asks the user only in the post-convergence sub-case because the ledger state is genuinely ambiguous and the user holds the intent ("do you want another round of a converged trace, or is the current state trusted?").
- Rule 5's not-clean sub-case does NOT ask because the ledger state itself is sufficient signal: unaddressed clusters + no handoff = work remains, continue silently.

The pattern: ask when the orchestrator's materials don't determine the answer; don't ask when they do.

---

## Atomic-write protocol

When the orchestrator begins any state-changing action that may not survive compaction, write the appropriate in-flight marker BEFORE the action; remove or replace it AFTER the action completes.

| Action | Marker written before | Marker cleared/replaced after |
|---|---|---|
| Step 4 dispatch (round N) | `in-flight:: <Runtime> dispatch round-N` | Replaced by `in-flight:: <Runtime> addressing round-N` at start of Step 6 |
| Step 6 addressing (round N) | `in-flight:: <Runtime> addressing round-N` (written by Step 6's opening atomic-write preamble — SKILL.md Step 6 owns the transition; this row documents it for cross-reference) | On the default inline-continuation path (Step 7), NO marker action occurs at Step 7 — Step 4 overwrites `addressing round-N` directly with `dispatch round-<N+1>` when the loop re-enters Step 4 (no intermediate clear; the overwrite is atomic per Step 4's marker write). On the opt-in handoff path, replaced by `in-flight:: <Runtime> handoff round-<N+1>` |
| Step 7 opt-in handoff OR 10-round ask-gate "stop" (end of round N) | `in-flight:: <Runtime> handoff round-<N+1>` | Cleared by the next invocation's rule (3) |
| Step 8 convergence (Condition A clean, round N) | (none written — removes the `addressing round-N` marker; Step 6's marker write is unconditional, so `addressing round-N` is always what is present here) | Cleared — in-flight line removed from ledger header. No new marker; trace is done. |
| Step 7 diagnostic-mode termination (`--one-round` / `--verify-only`, round N) | (none written — clears the `addressing round-N` marker; Step 6's marker write is unconditional, so `addressing round-N` is what is present. Both modes route through Step 7 item 3, so `close-round` has already written the round-summary comment in all paths — Step 9 can aggregate it.) | Cleared — in-flight line removed; the diagnostic round is complete, nothing in flight. |

**Resume-wakeup, armed/disarmed alongside the marker** (see "Self-perpetuating resume wakeup" below): arm a one-shot wakeup when the first `dispatch round-N` marker is written, at a first interval ASKED of the user; each firing re-arms a fixed 5h later *iff* a marker is still present; the chain self-terminates when Step 8 clears the marker (or a `handoff`/stop path ends the autonomous loop).

The `<Runtime>` in any marker the orchestrator writes is the **current invocation's Runtime** (one exception: the resume cases in recovery rules 1/2 keep the prior session's Runtime for the in-flight round; all other writes use current).

The ledger is the recovery source of truth; the in-flight marker is the only mutable state.

---

## Self-perpetuating resume wakeup (survival across session-limit / idle death)

The in-flight marker lets the *next* invocation recover — but something has to *cause* a next invocation. A long convergence trace (many rounds, each dispatching three cold agents) can outlive a session: hit a usage limit, get closed, or stall, and the trace simply stops with an `in-flight::` marker sitting on the ledger and no one to resume it. The self-perpetuating wakeup is the autonomous trigger that brings the trace back without the user re-invoking `/skill-tracer` by hand.

**Tie the wakeup lifecycle to the in-flight-marker lifecycle** — arm while a marker is live, disarm when it clears:

1. **Arm on first dispatch — ASK the user for the first interval.** When Step 4 writes the first `dispatch round-N` marker of an invocation, ask the user how long out to set the first resume wakeup (e.g. "How long should I wait before an autonomous resume-wakeup fires if this trace gets interrupted?"), then schedule a one-shot wakeup at `now + <that interval>`. This first interval is the user's call because only they know how long this particular trace should be given to finish on its own before a safety resume kicks in. Use the runtime's scheduling primitive (`mcp__scheduled-tasks__create_scheduled_task` with a future `fireAt`, or the harness equivalent). The wakeup's prompt is the canonical resume prompt below.
2. **Re-arm on each firing — fixed 5h thereafter (the self-perpetuating part).** When the wakeup fires, BEFORE doing recovery work it checks the ledger: if an `in-flight::` marker is still present (work remains), it **first schedules an identical wakeup `now + 5 hours`** (every interval AFTER the user-set first one is a fixed 5h — no re-asking), THEN resumes (runs Step 1 recovery on the marker). This chains the safety net across *repeated* deaths. If no marker is present (the trace converged or was cleanly handed off / stopped), it does **not** re-arm — the chain ends.
3. **Disarm on marker clear.** Step 8 convergence (marker removed) and the Step 7 opt-in-handoff / 10-round-stop paths (which write a `handoff` marker the user controls) are terminal for the autonomous chain: cancel any pending wakeup (or let the next firing self-terminate when it sees no `dispatch`/`addressing` marker).

**Canonical resume-wakeup prompt** (self-contained — a fresh session has no memory of the trace):
> Resume `/skill-tracer <skill-name>`. First read `~/.claude/skill-tracer-audit-ledger/<skill-name>.md` for the `in-flight::` marker and run Step 1 recovery (the applicable rule). If a `dispatch`/`addressing` marker is present (work remains), FIRST re-arm an identical one-shot wakeup 5 hours from now, THEN resume the trace to convergence. If no such marker is present, the trace is done — do not re-arm.

This is autonomous-survival infrastructure, distinct from compaction recovery: **compaction** recovery handles state loss *within* a live session (rules 1–5 above); the **wakeup** handles the session *ending entirely*. Both read the same in-flight marker; the marker remains the single source of truth. (WHY self-perpetuating rather than one recurring cron: a one-shot that re-arms only while a marker is live cannot outlive the work — it self-terminates the moment the trace converges, so there's no orphaned recurring job firing forever against a finished trace.)

---

## Marker write/replace mechanics

All marker writes are a single Edit at the in-flight anchor line — at most one such line ever, never write two in sequence even momentarily (the at-most-one invariant exists so a compaction landing mid-write doesn't leave the ledger with two markers that confuse the next Step 1 scan).

- **Write the marker**: insert the line if absent, or swap the line's content if present (anchor for Edit is the existing `in-flight::` line).
- **Clear the marker**: remove the line entirely, leaving surrounding blank lines intact.
- **Replace the marker**: a single Edit that swaps old in-flight line for new in one operation.

---

## Runtime constraint — top-level invocation only

skill-tracer requires the `Agent` tool to dispatch the three cold-parallel trace agents (Step 4 dispatches exactly three per round — forward, backward, executor). The `Agent` tool is available only in the **top-level** Claude session — not inside a nested `Agent` call.

If skill-tracer is invoked from within an Agent-launched subagent, the dispatch calls in Step 4 will fail, losing cold-parallel independence. The orchestrator must run from the top-level session (via `/skill-tracer`, natural-language trigger, or proactive invocation after a skill edit) — **never from inside an Agent subagent**.

If the orchestrator detects it is itself a subagent (e.g., `Agent` is unavailable, or the harness reports a nested context), stop and tell the user: "skill-tracer must run from the top-level session; nested Agent dispatch is not available here." Do not simulate.
