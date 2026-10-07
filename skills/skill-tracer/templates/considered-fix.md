# Considered-Fix  (Round [ROUND])

## Output contract and pre-record check

[OUTPUT_CHECK]

## First instruction — READ THESE BEFORE ANYTHING ELSE

Read **[HOW_TO_FIX]** then **[README]** before making any fix and before reading any other file.

- `[HOW_TO_FIX]` is the complete doctrine: how to choose FIX vs STRENGTHEN, the ORCHESTRATOR-PAUSE criteria, blast-closure, and the No-orphan-flag invariant.
- `[README]` — the target's intent source. Normally its README.md, whose `## Intent` section governs every decision below; when the target has no README.md this path is its SKILL.md and the frontmatter `description:` is the documented intent (how-to-fix.md "The considered-fix constraint").

If either file is unreadable, or `[README]` is readable but has neither a `## Intent` section nor a frontmatter `description:` (the intent is null; how-to-fix.md "The considered-fix constraint"), emit ORCHESTRATOR-PAUSE for every cluster with the question naming the unreadable path, or saying the intent is null.

---

## Work items

Clusters (this round's tier: Prepass or Code Review):

```json
[CLUSTERS]
```

Blast radius per cluster — **when you fix a cluster, also go to each of these locations and check whether they need the same or a related fix.** A fix that changes a shared token (a renamed identifier, a status string, a duplicated pattern) must land at EVERY affected site, not just the cluster's primary location. Treat each listed location as a site to inspect and, if affected, fix:

```json
[BLAST]
```

Files to read / edit (pointers — do NOT inline source):

```
[SKILL_FILES]
```

---

## Instructions

Per the doctrine in `[HOW_TO_FIX]`, for EACH cluster: apply the considered fix at the cluster's site, AND visit every location in that cluster's blast radius — if a blast location needs the same or a related fix, apply it there too. The fix is complete only when it has landed at every affected site (fix-impact closure); name all touched files in `address` / `touched_files`.

- **Cluster `guidance` field:** if a cluster carries a `guidance` field, the orchestrator attached it after weighing the skill's intent — follow it as the primary steer for that cluster's fix.

- **Fix the code AND its related documentation in the same pass.** A code change that alters what a script produces or how it behaves (a new field, a changed value/format, a narrowed set) is not complete until every reference doc that describes that contract is updated to match — and vice versa. Code↔doc drift is the producer↔consumer blast category ([HOW_TO_FIX] "Fix-impact closure — cover the full blast radius").
- **The blast-radius set above is a SEED, not a ceiling.** It is the radius the detectors could pre-compute; you must enumerate the FULL radius yourself per [HOW_TO_FIX] "Fix-impact closure — cover the full blast radius" (grep the shared token across the whole skill) and fix every site you find, then run `check_fix_radius.py` to verify coverage before writing each cluster's decision. Do not stop at the listed locations. **`touched_files` in your output is mechanically re-checked** — `ledger_cascade.py fill-address` re-runs `check_fix_radius.py` itself against whatever you list there for every TOKEN-BLAST cluster's FIX, and rejects every decision of the call if a site is still uncovered. List every file you actually edited, not just the flagged one.
- **Edit only files under the target skill directory** (the files listed under "Files to read / edit" above). Never modify any other skill, script, or path.
- **After editing any `.py` file, run `python3 -m py_compile <file>`** and confirm it passes before emitting that cluster's decision; a fix that breaks compilation is not done.

---

## Output contract

Emit a single JSON object with a `decisions` array — one decision block per cluster. No prose after the JSON. (The object form is required: the downstream `ledger_cascade.py --mode fill-address` reads `data["decisions"]`; a bare array is not accepted.)

```json
{
  "decisions": [
    {
      "cluster": "C1",
      "decision": "FIX | STRENGTHEN | ORCHESTRATOR-PAUSE",
      "address": "<one line — see address formats in [HOW_TO_FIX] \"Address column formats (required for the ledger row)\"; for ORCHESTRATOR-PAUSE: the precise question>",
      "touched_files": ["<absolute path>", "..."],
      "closure": ["Siblings: <file:line updated|unchanged, ...>", "Bound: <limit, edge case, existing remedy | none added>", "Claims: <sentence -> file:line, ...>", "Blocks: <file:start-end of each block you rewrote, re-read whole | none rewritten>"]
    }
  ]
}
```

Rules:
- The top-level value is an object with one key, `decisions`, whose value is the array of per-cluster blocks.
- `decision` must be exactly `FIX`, `STRENGTHEN`, or `ORCHESTRATOR-PAUSE`.
- `address` must start with the decision word (upper-case) **immediately followed by a space and an open paren** — `FIX (<file>: <summary>)` or `STRENGTHEN (added at <file>:<lines>: "...")`. An ORCHESTRATOR-PAUSE address is `ORCHESTRATOR-PAUSE (<question>)` or the bare question, which `ledger_cascade.py` wraps in that form. A colon right after the kind (e.g. `FIX: added X`) is **REJECTED** by the downstream `fill-address` step (it tallies as zero and the round can't record the fix) — always use the `FIX (…)` / `STRENGTHEN (…)` paren form. Name every blast-covered file touched (for FIX/STRENGTHEN). See `[HOW_TO_FIX]` "Address column formats (required for the ledger row)" for the exact format per decision type.
- `touched_files` lists every file edited; empty list for ORCHESTRATOR-PAUSE.
- `closure` is required on every FIX (the Closure block, `[HOW_TO_FIX]` "Closure block"): four one-line strings labelled `Siblings:`, `Bound:`, `Claims:` and `Blocks:`, none empty. `check_decisions.py` sends back a FIX without them.
- No `|` and no newlines inside any field value.

## Fix depth (standing rule)

Apply the **deepest root fix that does not widen the interface** (`[HOW_TO_FIX]` "Fix at the root" and
"Frozen interface"): where a doc and code disagree, decide which side states the documented intent and
change the other side, at the shared source rather than at each symptom. "Does not widen the interface"
means no new CLI flag, mode, subcommand, file, ledger field, run-options key, row kind, shared helper module, doc section, or any other new interface element such as an output JSON field, status value or exit code (moving
duplicated logic into an existing shared module is fine; it adds no interface). When the behaviour is
already correct and only a comment or doc is wrong, fix the comment or doc, not the code.

## Frozen interface

[INTERFACE_RULE]

Any change to a persisted key or format (a ledger column, a run-options key, a marker, a JSON field
another script reads) must be versioned and migrated: the reader still accepts the old form and
converts it, and the doc that describes the format names both. Observed: in the October 2026 self-run,
round 1 added a subcommand and sidecar files and rounds 2-8 kept finding contradictions in them; in
a later comparison, helpers, fields and a row kind added in round 1 drew about three of round 2's flags.
