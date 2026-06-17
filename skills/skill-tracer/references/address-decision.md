# Address Decision

How the orchestrator decides FIX vs STRENGTHEN vs USER-PAUSE for each cluster, and the address formats each option must land on the ledger in. SKILL.md Step 6 owns the "for each cluster, decide and act" loop; this reference owns the decision rules and the format spec.

The four invariants (cold-trace, considered-fix, no-orphan-flag, WHY-strengthening) are in SKILL.md proper — they're invariants of the whole skill, not just Step 6. The rules below are Step 6's operational form of invariants 2, 3, and 4.

---

## Bias toward FIX — STRENGTHEN is the exception, not the peer

The default address for every cluster is FIX — change the underlying artifact so the issue no longer exists. STRENGTHEN is reserved for the narrow case where the artifact is already correct and the cluster reflects intent the trace agents could not see from the text in front of them.

Before choosing STRENGTHEN, rule out FIX with this two-step test:

1. **Can the underlying artifact be changed so the issue disappears?** If the cluster names a defect in a script, doc, or contract (wrong format, missing case, two artifacts disagreeing on a shared convention, broken cross-reference, undocumented behaviour), the answer is yes — FIX. Adding language to the skill saying "this defect is intentional" is not the right address; aligning the artifact to remove the defect is.

2. **If the artifact is genuinely correct, is the cluster's true root cause "trace agent did not see the intent"?** Only then does STRENGTHEN apply, and only when the added text would actually prevent the next cold agent from re-flagging — vague reassurance does not count.

---

## Anti-patterns (operational form of considered-fix invariant)

These are fixes that destroy the skill's design — the considered-fix invariant forbids them.

**Anti-pattern: STRENGTHEN to document drift.** When two artifacts (two scripts, a script and a doc, two doc sections) disagree on a shared format, value, contract, or convention, the correct fix is to **align them** — pick one as authoritative and change the other. Adding skill-text that says "this disagreement is intentional, please accept it" is rarely the right call: the executor still has to reconcile two artifacts at runtime, the cognitive cost was not reduced, and the underlying drift remains as a future defect surface. Default to FIX-by-alignment for any cluster whose root cause is "two artifacts disagree."

**Anti-pattern: STRENGTHEN to paper over a script bug.** If a script's behaviour does not match what the skill documents, the FIX is to update the script (or the doc, whichever is wrong). Adding skill-text saying "the script may also print X, treat as benign" is the wrong address — the next round's executor agent will still flag the same mismatch from the script side.

---

## Special case: hidden-information leak clusters

For hidden-information-leak clusters (the "hidden-information leak" category in forward, backward, and executor — see Information-flow design awareness in SKILL.md): the address is usually FIX-by-removal (remove the leaked information from the assembled prompt or sub-agent brief). STRENGTHEN applies only when the design has shifted and the leak is intentional but the WHY is missing — then add the WHY at the boundary (legitimate STRENGTHEN per "missing WHY for deliberate design choice" below).

---

## Four legitimate STRENGTHEN cases (exhaustive)

Any cluster that does not fit one of these defaults to FIX:

1. **Missing WHY for a deliberate design choice.** Adding the WHY at the point-of-use is the fix (WHY-strengthening invariant — invariant 4). The artifact is correct; what was missing is the reasoning text.

2. **Unmarked-closure list.** A list like "examples include X, Y, Z" without saying whether it's exhaustive. Adding the explicit closure marker ("these four are exhaustive" / "examples only — others valid") is a STRENGTHEN. The list is correct; what was missing is the closure-status text.

3. **Cross-reference variable used without "see preceding line" pointer.** Variables (Q, Y, X) used at a distance from their introduction where renaming to remove the ambiguity would touch many call sites. STRENGTHEN by adding the cross-reference pointer is acceptable.

4. **Unreachable-looking branch that is actually a real edge case** (verified by the orchestrator, not assumed). Adding the edge-case note with the specific condition that triggers the row is a STRENGTHEN. The branch is correct; what was missing is the why-it-exists text.

---

## The three addresses

```
(a) FIX (default — choose unless STRENGTHEN's narrow criteria apply) —
    apply a surgical change to the exact text/code the cluster points at,
    so the next cold trace will read the corrected material and not
    re-raise the same flags.

(b) STRENGTHEN (exception only) — when the artifact is correct and the
    cluster reflects intent the trace agents could not see (per the four
    legitimate cases above), do NOT log this externally and move on. The
    reasoning must land inside the skill at the point of use: add a WHY
    paragraph, a closure marker, a disambiguation note, an explicit "this
    is intentional because…" annotation. The next cold trace agent reads
    the strengthened skill and has the reasoning it needs.

(c) USER-PAUSE — only when the orchestrator cannot decide between FIX and
    STRENGTHEN (or between two FIX paths) without external judgement (per
    the PAUSE criteria below). Other clusters in the round proceed normally.
```

---

## PAUSE criteria (the only legitimate gate to ask the user)

- Two plausible FIX paths exist and the skill's documented intent does not clearly select between them.
- The cluster is tagged `internal-contradiction` AND both sides carry load-bearing roles (each referenced elsewhere or has consumers).
- A FIX would require modifying a script whose downstream consumers the orchestrator cannot enumerate from the materials.

**USER-PAUSE is decision-based ONLY — never a fix-failure fallback.** The PAUSE criteria above are all about decision authority (the orchestrator doesn't have enough information to choose between two valid paths). They are NOT about execution difficulty. If a FIX attempt didn't stick (regression in the next round), the orchestrator owns the re-fix — that's an execution problem, the orchestrator's job to figure out, not a reason to bug the user. Per-cluster addressing is fresh-decision per round: a regression on cluster C in round N+1 gets a new FIX (different scope, different anchor, different approach) or a new STRENGTHEN if appropriate, decided independently of the prior attempt. The orchestrator does not auto-escalate to USER-PAUSE because fixes are failing.

If none of the PAUSE criteria hold, the orchestrator must produce either a FIX or a STRENGTHEN. "Too much work", "the agent misunderstood but I'll just log it", "I'll skip this for now", "I've tried twice and it didn't work" — these are NOT valid addresses. The next cold round will catch any orphan flag and re-raise it, costing an extra round (no-orphan-flag invariant, invariant 3).

---

## Address column formats (required for ledger row)

These exact formats so the next cold round can verify the address landed; the audit ledger's auditability depends on the Address column being parseable.

**FIX format:**
```
FIX (<file>: <one-line summary of change>)
```
Name the file changed and summarise the edit in one line. Example: `FIX (q2_recovery_pass1.py: add file-fallback + start-marker to delta-cycle formula)`. Do not write `FIX (applied)` or `FIX (removed)` without naming the file and what.

**STRENGTHEN format:**
```
STRENGTHEN (added at <file>:<line-range>: "<quoted first 80 chars>")
```
Name the file, the line range where the new text landed, and the first 80 characters of the added text. Example: `STRENGTHEN (added at SKILL.md:147-149: "Note: this list is exhaustive — the executor must treat values outside this set as a contract violation.")`. (This is the **applied**-STRENGTHEN form. In `--verify-only` mode nothing is applied, so the row instead uses the `would-STRENGTHEN (<file>: <one-line summary>)` form — no line-range or quoted text — per SKILL.md Step 6.) 

To capture the exact `<line-range>`: re-read the file after the edit; quote the first 80 chars of the new text. Approximate anchors (`~line N`) are not acceptable — see ledger-format.md "Exact line numbers in STRENGTHEN".

**USER-PAUSE format:**
```
USER-PAUSE (<one-line question with both candidate fixes named>)
```
Present the question and the two (or three) plausible fix paths so the user can answer crisply. Example: `USER-PAUSE (pass2.md '?' Code: (a) remove the option from the brief OR (b) route '?' codes to Q2-C in q2_compare.py — which matches intent?)`.

---

## Fix conservatism

Change the minimum text needed to resolve the specific cluster. Verify the surrounding paragraph still reads correctly. A whole-section rewrite turns a one-cluster round into a multi-cluster round.

---

## Batch edits to the same document

When several clusters in a round resolve in the **same file**, apply their fixes as one coordinated edit pass over that file — not one cluster at a time with a re-read between each. Group the round's clusters by target file first; for each file, plan all its edits together, then apply them.

WHY: editing a file once per cluster means each edit invalidates the line numbers and surrounding context the next cluster's address was computed against. Applied serially, the second edit works from a stale read, the third from a stale-er one — a recipe for a fix landing at the wrong anchor, silently overwriting a sibling cluster's just-applied edit, or double-touching a line two clusters both reference. One coordinated pass per file removes the staleness window: every edit to that file is planned against the same known state.

This composes with fix conservatism (each individual edit still changes the minimum text) and with Step 7's STRENGTHEN-anchor verification (re-read the file *once after* the file's full edit pass to capture final line numbers, not after every cluster). It does not change which clusters get FIX/STRENGTHEN/USER-PAUSE — only the order and grouping of how the applied edits are written.

(This is a general fix-application discipline, not specific to one trace direction.)

---

## Convergence check between rounds — test flag identity, not count

Round-on-round, the orchestrator looks for **regressions**, not for raw-count decreases. The comparison key is the cluster's **Root cause** — the defect identity the ledger persists. (The verbatim `Claim:` quotes live only in each round's agent reports, not the ledger, so the durable cross-round signal is Root cause: cluster round N+1's findings, then compare those Root causes against prior rounds' addressed Root causes.)

- **Regression** — a round N+1 cluster's Root cause matches (same defect) one already addressed in a prior round. The earlier address was incomplete; investigate and strengthen it further. When you write the re-address row, prefix that cluster's Root cause with `regression:` — this is the marker `scripts/render_ledger.py` highlights in red, and the signal a human scanning the ledger reads to spot an incomplete prior fix.
- **Cascade (expected, not regression)** — round N+1's clusters are all-new Root causes (not seen in prior rounds). The flag count may stay flat or even tick up because round-N fixes opened previously-invisible adjacent gaps. This is healthy convergence behaviour, not a problem.

The test is: *no prior-round Root cause reappears in a later round*. Raw flag count is informative but secondary — a round 4 = 3 flags → round 5 = 4 flags is fine if all 4 are new Root causes (cascade), and a problem only if any one of them re-raises a prior round's cluster (regression).

When grading "did the trace converge," watch the regression trace (should approach zero), not the raw count.

---

## Verifying STRENGTHEN landed

Between rounds, the orchestrator may spot-check that each STRENGTHEN anchor (file + line range) still contains the quoted text. If a previous round's STRENGTHEN was overwritten by a later FIX, the cluster needs re-strengthening.

Step 7's mandatory anchor-check (entry-order item 2, "verify every STRENGTHEN anchor landed") makes this systematic at end-of-round: re-read the named file at the named line range and confirm the quoted first-80-chars text is present. If any anchor is missing, re-apply to a stable location (one the same round's remaining clusters do not touch — check unaddressed clusters' Target file/line references before deciding where to land), then **hand-edit that ledger row's Address anchor** to the new location (the one in-place ledger edit in the workflow — `append_ledger.py` only appends; preserve the single-line, pipe-safe constraint). See SKILL.md Step 7 item 2.
