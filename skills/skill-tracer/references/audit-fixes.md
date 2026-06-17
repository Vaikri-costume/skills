# Audit-fixes mode

`--audit-fixes` (natural language: "audit skill fixes", "check fix quality since convergence") is a **diagnostic, read-only** mode: it checks whether the fixes recorded in a skill's ledger since its last convergence actually landed properly in the files — or were applied light-touch / band-aid and recorded as `FIX` without resolving the root cause. It dispatches one cold audit agent and reports the per-finding classification; **it applies no fixes** (like `--verify-only`, it previews state). The orchestrator decides what to do with the report.

WHY this mode exists: a long convergence trace records many `FIX` addresses across many rounds. A fix can be recorded as done while only partially landing (one of three duplicated copies updated; a pointer added beside still-duplicated bulk; a STRENGTHEN where a FIX was warranted). Those drift back into the skill silently — a later cold trace eventually re-raises them, but at the cost of rounds. This mode surfaces them on demand without waiting for the trace to rediscover them.

---

## When to invoke

- Flag: `/skill-tracer <skill> --audit-fixes`
- Natural language: "audit skill fixes for X", "check the fix quality on X", "did X's fixes actually land", "audit X since last convergence".
- Useful right after a long convergence run, before `/skill-publisher`, or whenever you suspect recorded fixes were not fully applied.

Runs Steps 1–2 first (entry-universal target/mode resolution + recovery check), like every mode. Skips Step 2.5 and the cold-trace loop entirely — it is not a trace, it is a fix-quality check over the existing ledger.

---

## Scope — "since last convergence"

The audit covers every data row whose Round is **strictly greater than the last converged round**:

- The **last converged round** = the highest **closed** round (one that has a `<!-- Round N total: … -->` summary comment) with **zero `TRACE`-phase data rows**. Determine it by counting **data rows**, NOT by reading the summary comment — the comment carries only total `raw flags`/`clusters` across all phases, so a round-1 that converged *with* a code-review phase shows nonzero clusters in its comment yet is cold-trace-clean; counting `TRACE`-phase rows is the phase-aware test (the same one `ledger_state.py`'s `last_round_clean` applies to the highest round, and the "round was clean" definition recovery-protocol.md uses). Scan rounds from the highest downward; the first whose closed-and-zero-`TRACE`-rows test passes is the last converged round.
- If the skill has **never converged** (no clean round), audit **all** rounds.
- If the last round IS clean (nothing new since convergence), report "no post-convergence rounds to audit" and stop.

State the resolved scope (`auditing rounds <since+1>..<highest>`) at the top of the run.

---

## Dispatch

Dispatch **one** general-purpose Agent, `description` exactly `Audit fixes of <skill>` (the bare `<target-skill-name>`), with the prompt template below — substitute `<skill-root>`, `<ledger-path>`, and `<since-round>` (the last converged round; the agent audits rounds `> <since-round>`). The agent is read-only and returns the classification report; it proposes no fixes (the orchestrator owns fixing).

### Prompt template

```
You are auditing the quality of fixes recorded in a skill's audit ledger against the actual current state of its files. Be adversarial and exhaustive — assume many fixes may have been applied in a LIGHT-TOUCH / LAZY / band-aid way and recorded as "FIX" when they were not real, full fixes.

## Inputs

- Skill under audit: `<skill-root>` (SKILL.md, references/*.md, scripts/*.py)
- Ledger (the record of every finding and how it was addressed): `<ledger-path>`
  - 7-column markdown table: `| Runtime | Round | Phase | Cluster | Root cause | Address | Flags |`
  - Phase: TRACE (cold-trace findings), REVIEW (code-review findings), SIMPLIFY (cleanup findings).
  - Address column states the claimed fix: `FIX (...)`, `STRENGTHEN (added at <file>:<lines>: "...")`, or `USER-PAUSE (...)`.
- Scope: audit EVERY finding (every data row) with Round > <since-round> through the highest round present. Rounds at or below <since-round> are prior, already-converged work — ignore.
- Note: the highest round may be CURRENT/in-flight — some of its addressed findings may have been edited into the files but not yet have a ledger row. Where you see a recent file edit that looks light-touch but has no matching row in the highest round, report it anyway.

## What to do

1. Read the ledger. Extract every row in scope. For each, note its Root cause, Address (the claimed fix), and Flags.
2. Read the full current contents of SKILL.md, every references/*.md, and every scripts/*.py.
3. For EVERY in-scope finding, classify the actual state of its fix:
   - PROPERLY FIXED — the claimed Address genuinely and fully landed; the root cause is actually resolved.
   - LIGHT-TOUCH — a band-aid: e.g. a "see reference" pointer was added while the duplicated bulk still sits in BOTH places (a real consolidation DELETES the duplicate); a parenthetical was added that grew the doc instead of resolving the issue; a partial trim; a STRENGTHEN where a FIX was warranted purely to avoid the work.
   - NOT REALLY FIXED / FALSE CLAIM — the Address claims a fix that is not present in the files, or claims "already covered" when it is not.
   - REGRESSED / NEW INCONSISTENCY — the fix introduced a new problem: a pointer to content that is NOT actually in the named reference, a broken cross-reference, a STRENGTHEN anchor whose quoted text is no longer at the named line, or a contradiction with another part of the doc (e.g. a multi-target fix that updated the script and one doc but left a third location asserting the opposite).
4. Quote the relevant current file lines as evidence for each classification.

## Special attention

- Consolidation/duplication findings: verify the duplicate was actually DELETED, not just cross-referenced. A pointer added next to the still-present bulk is LIGHT-TOUCH.
- Any STRENGTHEN address with an `added at <file>:<line-range>: "<quote>"` anchor: open that file at that range and confirm the quoted text is actually there.
- Any Address that says or implies "already covered / already consistent / no change needed": verify that claim is true against the files.
- Count how many findings fall in each class and list them.

## Output

Report ONLY — do not propose, prescribe, or describe any fix. The orchestrator decides and applies all fixes. For each finding return exactly: Round+Cluster (e.g. "R42 C18"), the status (one of the four classes), and the evidence (quoted current lines +, for a light-touch/false/regressed call, the specific reason it fails). Be exhaustive across all in-scope rounds.
```

---

## After the report

Present the classification to the user, grouped by class, with the counts. Every non-`PROPERLY FIXED` finding is a real open defect: feed it back through Step 6's considered-fix gate (bias-toward-FIX; STRENGTHEN only for the legitimate cases) and record the re-fix in the ledger — under the **current** round if a trace is in flight, otherwise as a fresh round. The audit mode itself writes no ledger rows and applies no fixes; it only produces the report.
