# Changelog Agent Prompt (skill-publisher Step 7)

The cold agent that proposes the version bump + changelog entry by reconciling **three
independent signals at equal weight**: the structured diff of the local skill vs its
published state (`diff_published.py`), this run's **ship-ledger** rows, and the
**skill-tracer audit-ledger rows since the last ship** (`tracer_changelog_rows.py`).
None alone is complete — the ship ledger misses out-of-ledger manual edits; the diff
misses the *intent* behind a change and is absent when there's no published state; the
**tracer ledger carries the bug-fix WHY + severity** that neither of the others does
(the diff shows code *changed*, not *why* or how severe — which is exactly what the
**Fixed** section and the bump need). The agent unions them, flags where they disagree,
and emits a Keep-a-Changelog / SemVer entry. The third signal is optional: when no
skill-tracer audit ledger exists for the target, the slot is the literal `none` and the
agent reconciles the first two as before (no regression).

This mirrors `audit-prompt.md`'s cold-dispatch shape (a single Agent, a constant
description, a completion sentinel). It is dispatched only when a published state
exists (`diff_published.py` exited 0); the no-published-state fallback (ledger-only)
is handled inline by Step 7 without this agent.

---

## Building the slots (orchestrator-side, before dispatch)

- `[STRUCTURED_DIFF]` — the full JSON `diff_published.py` printed (the `added` /
  `removed` / `modified[].diff` object). If it is large, keep it whole — the agent
  needs the per-file unified diffs to describe changes accurately.
- `[LEDGER_ROWS]` — this run's ship-ledger rows (every Run-`<N>` row this invocation:
  the POLISH / AUDIT / TIER clusters — the publisher's cluster-bearing phases), one per line, `Root cause | Address` form.
- `[TRACER_LEDGER_ROWS]` — the **skill-tracer audit-ledger rows since the last ship**,
  from `python3 ~/.claude/skills/skill-publisher/scripts/tracer_changelog_rows.py <skill>`
  (its text block verbatim — one applied CODE-REVIEW/TRACE/REVIEW fix per line, with its
  round, flags, root-cause and FIX/STRENGTHEN address). If that script **exits 1** (no
  tracer ledger for this skill), fill this slot with the literal `none`.
- `[PRIOR_VERSION]` — the HISTORY.md `version` being superseded (or `pre-versioned`).
- `[USER_DESCRIPTION]` — any change description the user gave, or the literal `none`.

Dispatch with `description` = **`changelog proposal for <skill>`** (the bare skill
name) — the constant string `recover_dispatch.py` matches for recovery
(`^changelog\s+proposal\s+for\s+(.+)$`). `subagent_type` `general-purpose`.

---

## The filled prompt

```
You are the changelog agent for the <skill> skill. Produce a version bump + changelog
entry by reconciling three independent signals AT EQUAL WEIGHT. Do not assume one is more
authoritative than the others — a real change can appear in any or all of them.

This is a focused reconciliation task. Use only the inputs below; do not read other files
or request prior context.

## Input 1 — structured diff (local vs last published state)
[STRUCTURED_DIFF]

## Input 2 — this ship run's ship-ledger rows (what the publisher recorded it changed)
[LEDGER_ROWS]

## Input 3 — skill-tracer audit fixes since the last ship (the bug-fix WHY + severity)
These are correctness fixes the tracer recorded that the diff/ship-ledger do not explain.
Each names a real bug and its FIX/STRENGTHEN. Map them into the **Fixed** section (a FIX),
or **Security** (a security fix) / **Changed** (a STRENGTHEN that added/changed a WHY).
May be the literal `none`.
[TRACER_LEDGER_ROWS]

## Prior version (the version being superseded)
[PRIOR_VERSION]

## User-described change (may be `none`)
[USER_DESCRIPTION]

## Your task
1. Enumerate every meaningful change. For each, decide its SOURCE:
   - `from: both`       — present in the diff AND described by a ship-ledger row
   - `from: diff-only`  — visible in the diff but NO ship-ledger row explains it (an
                          out-of-ledger manual edit — these matter most; never drop one)
   - `from: ledger-only`— a ship-ledger row with no corresponding diff hunk (e.g. a change
                          already in the published state, or a non-file change)
   - `from: tracer-ledger` — an Input-3 audit fix (name the specific bug it fixed; a tracer
                          fix usually also shows as a diff hunk, but Input 3 supplies the WHY
                          the diff alone cannot — prefer it for the Fixed bullet's wording)
2. Categorize each change under a Keep-a-Changelog heading: Added / Changed /
   Deprecated / Removed / Fixed / Security. (Map Conventional-Commits intent: feat→Added
   or Changed; fix→Fixed; refactor/perf/docs→Changed; removal→Removed; security→Security.)
   Every Input-3 fix becomes a concrete **Fixed** (or Security/Changed) bullet naming the
   bug — never collapse them into one vague "various fixes" line.
3. Recommend a SemVer BUMP from the union of changes:
   - major — a breaking change (removed/renamed command, changed output format/contract)
   - minor — new backward-compatible capability (Added)
   - patch — fixes / docs / internal-only (Fixed / Changed with no contract change)
   Choose the HIGHEST level any single change warrants. **Factor Input-3 severity**: a
   correctness fix is a patch signal, but a tracer fix that changed a behavior/contract
   (not just an internal bug) can push minor — judge by what the fix actually changed.
4. Report DISCREPANCIES — anything that needs a human decision: a diff hunk you cannot
   explain, a ledger row contradicting the diff, or an ambiguous bump level.

## Output format (exactly these sections, in order)
BUMP: <major|minor|patch>

CHANGES:
### Added
- <one line> (from: <both|diff-only|ledger-only|tracer-ledger>)
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
  real change the ship ledger missed, and a `tracer-ledger` change is a real bug fix the
  diff under-explained, so both stay in the entry.
- **Bump** — `final_bump = max(agent_bump, ledger_bump, tracer_bump)` where `ledger_bump`
  is the level this run's ship-ledger rows imply (a TIER/AUDIT fix → patch; a new capability
  → minor; a breaking change → major) and `tracer_bump` is the level the Input-3 tracer
  fixes imply (a correctness fix → patch; a fix that changed a behavior/contract → minor).
  Take the highest of the three.
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
