# Recovery Protocol

How skill-publisher recovers a ship run across compaction or session restart. Adapted from skill-tracer's recovery-protocol — same in-flight-marker + atomic-write mechanics, with publisher's action keywords.

SKILL.md Step 1 consults this when an `in-flight::` marker is present in the ship ledger. Without an in-flight marker, no *mid-run* recovery is needed — but Step 1 still consults rule 7 ("No marker, prior runs exist") to decide whether the prior ship completed or whether to start/resume a run.

---

## In-flight marker format

A single line in the ship-ledger header (between the title and the table header):

```
in-flight:: <Runtime> <action> run-N
```

Parse by splitting on whitespace: field 2 = `<Runtime>` (ISO-8601 `YYYY-MM-DDTHH:MM`), field 3 = `<action>`, field 4 = `run-N`.

---

## Action keywords (publisher-specific)

Each names which workflow step was interrupted:

- **`polish`** — mid-Step-2 (simplify pass) interrupted.
- **`audit`** — mid-Step-3 (CCVW audit Agent dispatched, result not yet recorded).
- **`tier`** — mid-Step-4 (tier-transition lints running).
- **`addressing`** — mid-Step-5 (cluster-by-cluster addressing).
- **`packaging`** — mid-Step-8 (packaging).
- **`pr`** — mid-Step-9 (PR creation — the riskiest to interrupt; see recovery rule below).

**Unknown keyword** → treat as `addressing` (the most conservative — re-derive clusters from the ledger and continue). Tell the user.

(`scripts/ledger-render-config.json`'s `valid_actions` array mirrors this keyword set for `render_ledger.py`'s `INVALID ACTION` HTML lint — keep the two in lockstep when the keyword set changes. That lint is cosmetic; this unknown-keyword→`addressing` rule, not the renderer, governs actual execution.)

---

## `<Runtime>` + `<encoded-cwd>`

Same definitions as skill-tracer's recovery-protocol: `<Runtime>` is the invocation-start UTC time `YYYY-MM-DDTHH:MM`; `<encoded-cwd>` is cwd with `/`→`-` and a leading `-`, used to locate session JSONLs under `~/.claude/projects/<encoded-cwd>/`. In practice, `recover_dispatch.py` auto-computes `<encoded-cwd>` from `os.getcwd()` — the orchestrator does not need to derive it manually. Pass `--project-dir` only when the publisher is running from a non-standard working directory and the auto-computed path would be wrong.

---

## Run number determination

Scan the ledger for the highest Run value. Resuming an in-flight run → continue at that Run (the run number identified by the marker's `run-N`). Starting fresh → highest + 1. Empty ledger → Run 1.

**Authority rule:** the ledger rows are the source of truth for run numbering. The marker's `run-N` field identifies *which* run was in flight (it was written atomically before the step began), not the run's canonical number. If the marker's N disagrees with the highest row-N in the ledger, trust the ledger rows to determine the last completed run; use the marker's N only to locate the in-flight entry in the ledger.

---

## Recovery rules (one applies per invocation)

1. **`polish run-N`** — re-run Step 2 from scratch. The simplify pass is idempotent enough (it reads current file state); discard any partial polish ledger rows for Run N and re-polish. Resume at Step 3 after.

2. **`audit run-N`** — recover the Step-3 audit Agent's result from the session JSONL with `python3 scripts/recover_dispatch.py --skill <skill>` (auto-locates the newest JSONL, matches the constant dispatch description `skill-creator-ccvw audit of <skill>`, pairs tool_use→tool_result most-recent-wins, and handles the background-Agent `<task-notification>` case). **Exit 0** with `result_text.audit` present and non-empty → audit recovered; resume at **Step 4** (run the tier-transition checks — the `audit run-N` marker per the atomic-write table is normally replaced by `tier run-N` at Step 4 before addressing), then Step 5 GAP-addressing. (Exit 0 but `result_text.audit` absent or an empty string → no usable audit text was captured; treat exactly as Exit 1 — re-dispatch the audit as a fresh cold Agent.) **Exit 1** (no dispatch found, or dispatched-but-no-result) → re-dispatch the audit as a **fresh cold Agent** — never resume/fork the prior dispatch, which would leak the prior run's context and break the cold-audit invariant. WHY the invariant matters: if the prior session's reasoning or findings leak into the re-dispatched audit agent, the agent cannot form an independent view of the current skill state. It ceases to be a cold read — it may approve findings the new polish already resolved, or miss regressions introduced since the prior dispatch. Each audit must read the skill as it currently exists, with no prior-run knowledge. **Exit 2** (the script could not LOCATE the session JSONL — `--jsonl` not found, project dir not found, or no `*.jsonl` in the dir; prints an `ERROR:` line to stderr, no JSON result on stdout) → there is nothing to recover from, so re-dispatch the audit as a fresh cold Agent (same as exit 1's action); do not treat the missing JSONL as an audit failure. (Exit 2 also fires on an argparse usage error — e.g. an omitted `--skill` — which prints argparse usage text rather than an `ERROR:` line; in that case fix the invocation and re-run rather than re-dispatching.) The script only LOCATES + PAIRS; the orchestrator judges whether the recovered text is a *usable* audit (a truncated or `ABORTED` result → re-dispatch). This script is skill-publisher's own copy of the ecosystem cold-dispatch recovery pattern — deliberately NOT sync-contracted (the publisher recovers one audit dispatch; skill-tracer recovers three trace directions), so it is not checked by `check_vendored_sync.py`.

3. **`tier run-N`** — re-run Step 4's lints (they're deterministic static scans; cheap to re-run). Discard partial TIER rows, regenerate. Resume at Step 5.

4. **`addressing run-N`** — the ledger's Run-N rows are the addressed clusters. Re-derive the full cluster set (re-run Steps 3-4 cold) and match against addressed rows by Root cause + Flags; continue from the first unaddressed cluster. Re-running Steps 3-4 needs inputs the Step-1 target-read block (bypassed on this resume) normally captures: first re-resolve the target SKILL.md path (from the invocation argument / ledger) and re-read the target's `metadata.intended-audience` tier, then re-run the audit (Step 3) and tier checks (Step 4). **Match definition:** a re-derived cluster matches a ledger row when its Root cause text matches the row's Root cause column (case-insensitive substring) OR when at least one of its flag IDs appears in the row's Flags column. The first re-derived cluster with no matching row is the first unaddressed cluster to continue from.

5. **`packaging run-N`** — re-run Step 8 (packaging is idempotent — overwrites the `.skill` artifact). Resume at Step 9.

6. **`pr run-N`** — **caution.** A PR may have been partially created (branch pushed, PR not yet opened, or vice versa). First re-derive the inputs the branch-name match needs (Step 1's interactive read is bypassed on resume): `<name>` from the target SKILL.md frontmatter `name`, and `<version>` from the target HISTORY.md `version` frontmatter (Step 7 wrote it before this marker). Recovery: check `gh pr list` for an existing PR matching `ship/<name>-v<version>`. If found, the PR exists — record its URL, skip to Step 10. If a branch was pushed but no PR, run `gh pr create` against it. If nothing was pushed, re-run Step 9 from the branch step. NEVER blindly re-push — check state first (a double-push or duplicate PR is a real outward-facing error).

7. **No marker** — two sub-cases based on ledger state:
   - **Ledger empty (no rows)**: this is the first ship for this skill — set Run = 1 and proceed to Step 2.
   - **Prior runs exist**: the prior ship completed or crashed without a marker. If the last Run's summary comment shows a ship outcome (tier + version + PR) in the form `<!-- Run N total: … shipped at tier … version … PR: … -->`, the ship completed; ask the user whether to start a new ship run. If the user declines, stop and await their instruction — do not start a new run without user intent. If the last comment is in the generated form `<!-- Round N total: … -->` (without a ship outcome — `close-round` ran but the Edit-replace to canonical form at Step 10 did not): the crash landed in the **marker-free window between Step 6 and the Step-10 canonical replacement** (Steps 6–7 carry no marker; a crash in Step 8/9 would have left a `packaging`/`pr` marker instead, so those are excluded). Re-run from Step 1 to redo the remaining work — Step 6 README-gen and the Step-10 canonical-comment replacement are idempotent; for Step 7, FIRST check whether HISTORY.md already carries the bumped version (if so, skip the re-bump) to avoid a double version bump on the re-run. If no summary comment exists at all for the last Run, the prior run crashed — re-run from Step 1.

---

## Atomic-write protocol

Write the marker BEFORE each state-changing step; replace/clear AFTER:

| Step | Marker before | After |
|---|---|---|
| Step 2 polish | `polish run-N` | replaced by `audit run-N` at Step 3 |
| Step 3 audit dispatch | `audit run-N` | replaced by `tier run-N` at Step 4 |
| Step 4 tier checks | `tier run-N` | replaced by `addressing run-N` at Step 5 |
| Step 5 addressing | `addressing run-N` | cleared at Step 6 (no marker through README-gen + version-bump — those are local edits, re-runnable) |
| Step 8 packaging | `packaging run-N` | replaced by `pr run-N` (or cleared if no PR) |
| Step 9 PR | `pr run-N` | cleared at Step 10 (ship complete) |

The marker is a single line; write/replace/clear via one Edit at the `in-flight::` anchor (at most one such line ever). Same mechanics as skill-tracer's recovery-protocol "Marker write/replace mechanics".

---

## Runtime constraint

Like skill-tracer, the Step 3 audit needs `Agent` (top-level session only). If the publisher detects it's a nested subagent (Agent unavailable), stop and tell the user — don't simulate the audit.
