# Recovery Protocol

How skill-publisher recovers a ship run across compaction or session restart. Adapted from skill-tracer's recovery-protocol — same in-flight-marker + atomic-write mechanics, with publisher's action keywords.

SKILL.md Step 1 consults this when an `in-flight::` marker is present in the ship ledger. Without an in-flight marker, no *mid-run* recovery is needed — but Step 1 still consults the **No marker** case ("prior runs exist") to decide whether the prior ship completed or whether to start/resume a run.

---

## Step-1 ledger-state dispatch

Step 1 runs this dispatch against `~/.claude/skill-publisher-ledger/<skill>.md` (using the invocation argument as `<skill>` for the initial lookup — the SKILL.md frontmatter `name` is authoritative and is cross-checked in Step 1's target-resolution block). After it returns, `<N>` (the Run number) is set. Exactly one branch applies:

1. **Ledger file does not exist** (first-ever ship for this skill): run `mkdir -p ~/.claude/skill-publisher-ledger/ && mkdir -p "${HOME}/.claude/session-logs"` in Bash (the second mkdir ensures the session-log directory exists for the `echo >>` markers in Steps 2–9; non-blocking — a failure is warned, not fatal), then **Write** a new ledger at that path with the **Header template (new ledger)** from `references/ledger-format.md`. Start **Run 1**.
2. **Exists but cannot be read** (permission/encoding error): **USER-PAUSE** — report the exact path + error; do not proceed until the user resolves the file.
3. **Exists, readable, carries an in-flight marker**: run the matching recovery rule (the **Recovery rule expansions** + the **Marker state-table** below select it from the marker keyword). `<N>` = the marker's `run-N`.
4. **Exists, readable, marker present but unparseable** (matches `in-flight::` but fails the `<Runtime> <action> run-N` format, or names an unrecognized action keyword): apply the **Unknown keyword** fallback below (treat as `addressing`) **and surface the malformed marker to the user** before continuing — do not guess silently.
5. **Exists, readable, no marker**: consult the **No marker** case below — if prior rows exist it determines completed-vs-crashed (and whether to resume as Run N or start fresh); if the ledger has no data rows, start **Run 1**.

(Recovery Rule B (`addressing run-N`) and the other lettered rules resume *mid-workflow* and bypass Step 1's *interactive* target-read block — but Rule B itself first re-resolves the target path + tier and re-runs Steps 3–4 cold to rebuild the cluster set, so the audit/tier re-derivation is not skipped. This is the one exception to the "every invocation runs the interactive read" rule.)

---

## In-flight marker format

A single line in the ship-ledger header (between the title and the table header):

```
in-flight:: <Runtime> <action> run-N
```

Parse by splitting on whitespace: field 2 = `<Runtime>` (ISO-8601 `YYYY-MM-DDTHH:MM`), field 3 = `<action>`, field 4 = `run-N`.

---

## Marker state-table (single source of truth)

One row per marker — the **only** place the marker grammar lives. Each marker is written BEFORE its state-changing step (atomic-write protocol) and replaced/cleared AFTER; the same row gives the recovery action when that marker is found mid-flight. (This table replaces the former separate "action keywords" list + "atomic-write" table — one home, no per-feature triplication.)

| Marker `<kw> run-N` | Written before (step) | Replaced / cleared after | On recovery (resume action) |
|---|---|---|---|
| `polish` | Step 2 (simplify pass) | → `audit` at Step 3 | re-run Step 2 from scratch (idempotent — reads current files); discard partial polish rows; resume Step 3 |
| `audit` | Step 3 (CCVW audit dispatch) | → `tier` at Step 4 | **rule A** — recover the dispatch (`recover_dispatch.py --kind audit`); else re-dispatch a fresh cold Agent |
| `tier` | Step 4 (tier-transition lints) | → `addressing` at Step 5 | re-run Step 4's lints (deterministic static scans); discard partial TIER rows; resume Step 5 |
| `addressing` | Step 5 (cluster addressing) | cleared at Step 6 | **rule B** — re-derive the full cluster set cold, match by Root cause + Flags, continue from the first unaddressed |
| `changelog` | Step 7a (diff-clone + changelog agent) | cleared at Step 7 (after the changelog is sourced) | **rule C** — re-run Step 7a (clone + diff + agent dispatch are idempotent/cheap); optionally reclaim the dispatch via `recover_dispatch.py --kind changelog` |
| `packaging` | Step 8 (packaging) | → `pr` at Step 9 (or cleared if no PR) | re-run Step 8 (idempotent — overwrites the `.skill` + re-derives the digest); resume Step 9 |
| `pr` | Step 9 (PR creation) | cleared at Step 10 (ship complete) | **rule D** — caution: a PR may be half-created; check state before acting, never blind re-push |

The marker is a single line; write/replace/clear via one Edit at the `in-flight::` anchor (at most one such line ever). Same mechanics as skill-tracer's recovery-protocol "Marker write/replace mechanics". No new markers for the Step-8 **digest** (computed inside the `packaging` step) or the Step-10 **manifest** (a marker-free terminal write — see the note at the end of this file).

**Unknown keyword** → treat as `addressing` (the most conservative — re-derive clusters from the ledger and continue). Tell the user. (`scripts/ledger-render-config.json`'s `valid_actions` array mirrors this table's keyword set for `render_ledger.py`'s cosmetic `INVALID ACTION` HTML lint — keep the two in lockstep; this unknown-keyword→`addressing` rule, not the renderer, governs execution.)

---

## `<Runtime>` + `<encoded-cwd>`

Same definitions as skill-tracer's recovery-protocol: `<Runtime>` is the invocation-start UTC time `YYYY-MM-DDTHH:MM`; `<encoded-cwd>` is cwd with `/`→`-` and a leading `-`, used to locate session JSONLs under `~/.claude/projects/<encoded-cwd>/`. In practice, `recover_dispatch.py` auto-computes `<encoded-cwd>` from `os.getcwd()` — the orchestrator does not need to derive it manually. Pass `--project-dir` only when the publisher is running from a non-standard working directory and the auto-computed path would be wrong.

---

## Run number determination

Scan the ledger for the highest Run value. Resuming an in-flight run → continue at that Run (the run number identified by the marker's `run-N`). Starting fresh → highest + 1. Empty ledger → Run 1.

**Authority rule:** the ledger rows are the source of truth for run numbering. The marker's `run-N` field identifies *which* run was in flight (it was written atomically before the step began), not the run's canonical number. If the marker's N disagrees with the highest row-N in the ledger, trust the ledger rows to determine the last completed run; use the marker's N only to locate the in-flight entry in the ledger.

---

## Recovery rule expansions

The state-table above covers the simple cases inline (`polish`, `tier`, `packaging` — all idempotent re-runs). The four lettered rules and the no-marker case need expansion:

**Rule A — `audit run-N`** — recover the Step-3 audit Agent's result from the session JSONL with `python3 scripts/recover_dispatch.py --skill <skill>` (auto-locates the newest JSONL, matches the constant dispatch description `skill-creator-ccvw audit of <skill>`, pairs tool_use→tool_result most-recent-wins, handles the background-Agent `<task-notification>` case). **Before acting on the result, re-resolve the target like Rule B does** — a post-compaction resume bypasses Step 1's interactive read, so re-resolve the target SKILL.md path (from the invocation argument or the ledger) and re-read `metadata.intended-audience`; Step 4's frontmatter gate (`portability_lint.py <target> --tier <tier>`) needs both `<target>` and the authoritative `<tier>`. **Exit 0** with `result_text["audit"]` present and non-empty → audit recovered; resume at Step 4, then Step 5. (Exit 0 but `result_text["audit"]` absent or empty → treat as Exit 1.) **Exit 1** (no dispatch found, or dispatched-but-no-result) → re-dispatch the audit as a **fresh cold Agent** — never resume/fork the prior dispatch, which would leak prior reasoning and break the cold-audit invariant (each audit must read the skill as it currently exists, with no prior-run knowledge). **Exit 2** (JSONL not locatable) → re-dispatch fresh cold Agent (same as Exit 1; no audit to recover). The script only locates + pairs; the orchestrator judges usability (truncated or `ABORTED` result → re-dispatch). Not sync-contracted: this script is the publisher's own copy of the ecosystem recovery pattern — not checked by `check_shared_sync.py`.

**Rule B — `addressing run-N`** — the ledger's Run-N rows identify addressed clusters. Re-derive the full cluster set cold (re-run Steps 3–4) and match against addressed rows by Root cause + Flags; continue from the first unaddressed cluster. Before re-running Steps 3–4, re-resolve the target SKILL.md path (from the invocation argument or the ledger) and re-read `metadata.intended-audience`. **Match definition:** a re-derived cluster matches a ledger row when its Root cause text matches the row's Root cause column (case-insensitive substring) OR when at least one of its flag IDs appears in the row's Flags column. The first re-derived cluster with no matching row is the resume point.

**Rule C — `changelog run-N`** — re-run Step 7a (diff-clone + structured diff + changelog agent dispatch are all idempotent and cheap). Optionally, before re-dispatching, attempt `python3 scripts/recover_dispatch.py --skill <skill> --kind changelog`: if it exits 0 with `result_text["changelog"]` present and non-empty, the prior changelog agent's output is recoverable — use it and skip the re-dispatch. If the recovered text is absent, empty, truncated, or the script exits non-zero, re-dispatch a fresh cold changelog agent. Either way, continue to Step 7 (changelog sourcing + HISTORY.md write).

**Rule D — `pr run-N`** — **caution.** A PR may be half-created (branch pushed, PR not yet opened, or vice versa). First re-derive `<name>` from the target SKILL.md frontmatter and `<version>` from the target HISTORY.md (Step 7 wrote it before this marker). **If either file is unreadable** → USER-PAUSE (do not attempt `gh pr list` with a wrong name, do not re-push). Recovery: `gh pr list` for an existing PR matching `ship/<name>-v<version>`. Found → record URL, skip to Step 10. Branch pushed but no PR → `gh pr create` against it. Nothing pushed → re-run Step 9 from the branch step. NEVER blindly re-push — a double-push or duplicate PR is an outward-facing error.

**No marker** — two sub-cases based on ledger state:
- **Ledger empty (no rows):** first ship for this skill — set Run = 1, proceed to Step 2.
- **Prior runs exist:** the prior ship completed or crashed without a marker. If the last Run's summary comment shows a ship outcome (`<!-- Run N total: … shipped at tier … version … PR: … -->`), the ship completed — ask the user whether to start a new ship run; stop if they decline. If the comment is in the close-round form (`<!-- Round N total: … -->`) without a ship outcome, the crash landed in the marker-free window between Step 6 and the Step-10 canonical replacement — re-run from Step 6 onward **as Run N, NOT Run N+1**. This is the one place the "fresh run = highest + 1" rule is overridden: the crashed run's clusters were already written under Run N (its `Round N total` comment is on disk), so resuming as Run N+1 would re-run Steps 2–5 and append a second, duplicate cluster set under N+1, leaving Run N's comment forever un-canonicalized. Set `<N>` = the Run number in that `Round N total` comment, skip Steps 2–5 (their rows already exist for Run N), and resume at Step 6; Step 10 then replaces the existing `<!-- Round N total: … -->` with the canonical `<!-- Run N total: … -->` (the Edit-replace is keyed on the same N). Apply idempotency guards at Step 7: **(a)** if HISTORY.md is absent (degraded mode), skip the version-bump check; **(b)** if HISTORY.md is present, check whether it already carries the bumped version — skip the re-bump if so; **(c)** check `metadata.parent-version` in SKILL.md — skip that update if already set. If no summary comment exists at all for the last Run, the prior run crashed before Step 5's close-round (no Run-N rows are committed) — re-run that run from Step 1 (here Run = highest + 1 is correct, since no Run-N rows exist to duplicate).

---

## Runtime constraint

Like skill-tracer, the Step 3 audit needs `Agent` (top-level session only). If the publisher detects it's a nested subagent (Agent unavailable), stop and tell the user — don't simulate the audit.
