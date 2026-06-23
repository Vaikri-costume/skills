# Changelog Agent Prompt (skill-publisher Step 7)

The cold agent that proposes the version bump + changelog entry by reconciling **two
independent signals at equal weight**: the structured diff of the local skill vs its
published state (`diff_published.py`) and this run's ledger rows. Neither alone is
complete — the ledger misses out-of-ledger manual edits; the diff misses the *intent*
behind a change and is absent when there's no published state. The agent unions them,
flags where they disagree, and emits a Keep-a-Changelog / SemVer entry.

This mirrors `audit-prompt.md`'s cold-dispatch shape (a single Agent, a constant
description, a completion sentinel). It is dispatched only when a published state
exists (`diff_published.py` exited 0); the no-published-state fallback (ledger-only)
is handled inline by Step 7 without this agent.

---

## Building the slots (orchestrator-side, before dispatch)

- `[STRUCTURED_DIFF]` — the full JSON `diff_published.py` printed (the `added` /
  `removed` / `modified[].diff` object). If it is large, keep it whole — the agent
  needs the per-file unified diffs to describe changes accurately.
- `[LEDGER_ROWS]` — this run's ledger rows (every Run-`<N>` row this invocation:
  the POLISH / AUDIT / TIER clusters — the publisher's cluster-bearing phases), one per line, `Root cause | Address` form.
- `[PRIOR_VERSION]` — the HISTORY.md `version` being superseded (or `pre-versioned`).
- `[USER_DESCRIPTION]` — any change description the user gave, or the literal `none`.

Dispatch with `description` = **`changelog proposal for <skill>`** (the bare skill
name) — the constant string `recover_dispatch.py` matches for recovery
(`^changelog\s+proposal\s+for\s+(.+)$`). `subagent_type` `general-purpose`.

---

## The filled prompt

```
You are the changelog agent for the <skill> skill. Produce a version bump + changelog
entry by reconciling two independent signals AT EQUAL WEIGHT. Do not assume one is more
authoritative than the other — a real change can appear in either or both.

This is a focused reconciliation task. Use only the inputs below; do not read other files
or request prior context.

## Input 1 — structured diff (local vs last published state)
[STRUCTURED_DIFF]

## Input 2 — this ship run's ledger rows (what the publisher recorded it changed)
[LEDGER_ROWS]

## Prior version (the version being superseded)
[PRIOR_VERSION]

## User-described change (may be `none`)
[USER_DESCRIPTION]

## Your task
1. Enumerate every meaningful change. For each, decide its SOURCE:
   - `from: both`       — present in the diff AND described by a ledger row
   - `from: diff-only`  — visible in the diff but NO ledger row explains it (an
                          out-of-ledger manual edit — these matter most; never drop one)
   - `from: ledger-only`— a ledger row with no corresponding diff hunk (e.g. a change
                          already in the published state, or a non-file change)
2. Categorize each change under a Keep-a-Changelog heading: Added / Changed /
   Deprecated / Removed / Fixed / Security. (Map Conventional-Commits intent: feat→Added
   or Changed; fix→Fixed; refactor/perf/docs→Changed; removal→Removed; security→Security.)
3. Recommend a SemVer BUMP from the union of changes:
   - major — a breaking change (removed/renamed command, changed output format/contract)
   - minor — new backward-compatible capability (Added)
   - patch — fixes / docs / internal-only (Fixed / Changed with no contract change)
   Choose the HIGHEST level any single change warrants.
4. Report DISCREPANCIES — anything that needs a human decision: a diff hunk you cannot
   explain, a ledger row contradicting the diff, or an ambiguous bump level.

## Output format (exactly these sections, in order)
BUMP: <major|minor|patch>

CHANGES:
### Added
- <one line> (from: <both|diff-only|ledger-only>)
### Changed
- <one line> (from: ...)
### Fixed
- <one line> (from: ...)
(omit any category with no entries; include Deprecated/Removed/Security only if used)

DISCREPANCIES:
- <one line each, or the single line `none`>

ENTRY:
### <leave the version+date heading to the orchestrator — body bullets only, grouped by the
     same Keep-a-Changelog categories, factual and concise, one line per meaningful change>

Then a final line, exactly:
CHANGELOG PROPOSAL COMPLETE
```

---

## Reconciliation (orchestrator-side, after the agent returns)

- **Union of changes** — take every change the agent listed; a `diff-only` change is a
  real change the ledger missed, so it stays in the entry.
- **Bump** — `final_bump = max(agent_bump, ledger_bump)` where `ledger_bump` is the level
  the ledger rows alone imply (a TIER/AUDIT fix → patch; a new capability → minor; a
  breaking change → major). Take the higher of the two.
- **When to ask the user** (otherwise proceed silently with the agent's proposal):
  1. the agent's BUMP and the ledger-implied bump disagree, OR
  2. `DISCREPANCIES` is not `none`, OR
  3. the bump level is genuinely ambiguous (the agent says so, or the change set spans
     levels without a clear headline change).
  Present the proposal + the specific conflict; let the user pick the bump / confirm the entry.
- **Completion check** — the agent's result must end with `CHANGELOG PROPOSAL COMPLETE`.
  If absent (truncated/aborted), re-dispatch the cold agent (it is cheap — same inputs).
- **Write** — fill `assets/changelog-entry-template.md` with `<new-version>` (= prior bumped
  by `final_bump`), the date, and the agent's `ENTRY` bullets; prepend to the HISTORY.md
  changelog body per `changelog-format.md`.

---

## No-published-state fallback (no agent)

When `diff_published.py` / `github_pr.py --diff-only` reports `no_published_state` (the
skill isn't published anywhere yet, or there's no upstream), skip this agent entirely and
source the changelog from the ledger rows alone (+ optional `<last-ship-tag>` git log and
the user description), exactly as `changelog-format.md` "Sourcing the change summary"
describes. The diff-driven reconciliation only adds value once a published baseline exists.
