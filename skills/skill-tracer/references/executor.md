# Executor Trace — Definition

An **executor trace** reads SKILL.md (and every supporting file in scope) from the perspective of the executor who is about to follow it. The agent imagines itself as the next cold dispatch arriving at this skill with no prior context, opening SKILL.md at line 1, and proceeding line by line. At every line, the question is: *"If I were the executor, could I act on this without guessing?"*

An executor trace asks: *"SKILL.md says X — when I, the executor, reach this line for the first time, is the action I must take unambiguous?"*

This trace verifies that the document, read as a text, gives the executor a single readable path through it. The unit of failure is a line a careful reader cannot act on without inventing meaning the text does not supply. This is the approach this trace takes — line-by-line, in the executor's order. Any issue surfaced while reading this way is flaggable, regardless of which category list it most closely fits. If you notice a script that does not behave as the document claims, or a script output that no part of the document consumes, flag that too — any issue that defeats the executor belongs in the report.

Read top-to-bottom in the executor's order. Do not skip ahead to resolve a reference; if a reference is unresolvable at the point the executor first encounters it, that is the gap. The executor cannot read pages they have not yet reached.

---

## What counts as an executor-trace issue

A line is an issue when one of the following is true. Each item below is a complete category; the executor agent flags the line and quotes the failing text.

**1. Unresolvable referent.** The line uses a noun phrase ("the file", "the tracking row", "the result", "the agent's output", "the staging path") whose antecedent the executor cannot identify with certainty from text already read. A pronoun or definite article that points to more than one candidate, or to no candidate visible at this point in the document, is a gap.

**2. Action whose operation is not specified.** The line tells the executor to do something where the *what* and *how* of the action are not pinned down by text already read. The test is per-line — not by verb class. "Verify the dispatch", "ensure the file exists", "handle the failure" are obviously ambiguous, but so are "write the source name" (where? in what format?), "send the message" (which message? to whom?), "load the brief" (which brief? from which file?), "read the row" (which file's row? which row?). Flag any line where the executor cannot, from text already read, state both the exact action to take and the procedure for taking it.

**3. Branch without trigger.** The line describes a branch (an "if", an "otherwise", a "when X, do Y") where the condition is not testable from values the executor has in hand at that step. The executor cannot evaluate `if the source is stale` if no earlier step has told them what `stale` means or where the staleness signal comes from.

**4. Branch without exit.** The line opens a branch but does not say what to do when the branch completes — does the executor return to the parent step, advance to the next step, stop, or loop? If the next-line behaviour depends on which branch was taken and the text does not say, that is a gap.

**5. Missing case.** The line enumerates cases ("if A → X; if B → Y") but a value the executor can plausibly observe falls into neither A nor B. The executor reaching value C has no instruction. Flag the missing case and quote the enumeration.

**6. Undefined term at point of use.** The line uses a domain term or skill-internal noun ("delta-pending row", "the orchestrator's tracking file", "the cold dispatch property", "the in-flight write") that has no stable definition in materials the actor at this line has loaded. A term defined only later in the document is a gap at every earlier point it is used — the executor reads in order. A term defined only in a glossary or reference doc the actor at this line has not loaded — for example, a term used in a brief inlined into a sub-agent's prompt where the sub-agent does not load the glossary — is also a gap. The trace agent's full-view access is not the runtime actor's access. Flag the term and the first use that defeats the executor.

**7. Two-reading line.** A line that two careful readers can read in two distinct ways, each leading to a different action. Quote both readings under `Target:` and the actions each leads to. Whether the surrounding context resolves the ambiguity is the orchestrator's judgement; your job is to surface the two readings.

**8. Implicit precondition.** A step assumes the executor has done something earlier (captured a value, opened a file, set a variable) that no earlier step explicitly told them to do. The executor following the document literally has not done it. Flag the consuming line and quote the assumed precondition.

**9. Forward reference unresolvable at point of use.** A line says "as described in step 7" or "see the brief" or "per the schema" where the referenced material is unreachable at the moment the executor needs it (the step is far ahead; the brief is in a file not yet loaded; the schema is in a section the executor cannot access without already understanding what it points to). A pointer the executor cannot follow at the point of use is a gap.

**10. Conflicting instructions adjacent.** Two consecutive or nearby lines instruct the executor to do incompatible things, with no language saying which one wins or under what condition each applies. The executor has no rule for choosing.

**11. Quantifier or scope ambiguity.** "All", "every", "any", "the latest", "the first", "the relevant", "the matching" applied to a set whose membership the executor cannot enumerate from the text. The executor knows the rule applies to *something* but cannot tell to *what*.

**12. Silent format expectation.** The line instructs the executor to read or write a value but does not specify the format precisely enough for the executor to do so without inventing details. ("Write the source name" — with hyphens or underscores? Bare or quoted? On its own line or inline?) Flag the format ambiguity. Whether a later step's parser depends on the format choice is the orchestrator's judgement; your job is to surface that the executor has to invent.

**13. Missing WHY at point of use.** A line states a rule the executor must follow whose reason is not given at the rule's location — same line, same step, same block the actor loading this rule would necessarily load together with it. The executor can follow the rule mechanically but cannot judge edge cases where the rule's spirit applies and its letter does not. A WHY that lives "nearby" in the document but in a paragraph the actor might not load with the rule (selectively loaded skill, sub-agent brief that carries the rule but not the surrounding paragraph, partial reads) is a gap at the rule's location. Flag the rule and quote the bare statement.

**14. Stale or self-contradicting language.** A line uses tense, person, or framing that contradicts the document's stance elsewhere ("the executor will" in one place, "the agent should" in another, when both refer to the same actor). Flag the inconsistency and quote both framings. Whether it forces the executor to make a decision is the orchestrator's judgement.

**15. Hidden-information leak at point of use.** A line on the executor's path exposes, references, or instructs the assembly of information that the skill's design — stated in SKILL.md or implied by the structure — intends a downstream actor (a sub-agent the executor will dispatch, the next cold trace round, a child task, the user) to be blind to. Examples: a step that assembles a sub-agent prompt and inlines the orchestrator's tracking state when the brief is supposed to be self-contained; a step that re-dispatches a trace agent and includes the prior round's ISSUE report when each dispatch is cold; a step that surfaces internal sequencing data to an actor whose contract is to receive only X, Y, Z. Quote the line and the design boundary it violates.

**16. List of unmarked closure.** The line presents a list (categories, examples, cases, values, paths, options, conditions, file types, error codes) without stating whether it is closed (complete and final — items outside the list are out-of-scope or violations) or open (illustrative and extensible — items outside the list are also valid and need the same handling). The executor reading the list cannot judge how to handle anything not named: do they refuse / error / fall through to a default, or do they extend the pattern to the new case? Either explicit marker resolves it ("these are the only X" / "examples include — there may be others"). Without one, the executor is forced to guess and two readings give different actions. Quote the list and the surrounding text that should carry the closure marker.

(These categories overlap and are entry points, not a closed set. The prompt body's "Beyond the listed categories" and "Anti-double-counting" sections govern flagging beyond this list and de-duping overlaps.)

---

## Recurring patterns in procedural skills (real defects — flag every instance)

In skills documenting a multi-step protocol (build / trace / ship workflows), a handful of the categories above recur heavily — and precisely because they are numerous, they are easy to wave off as stylistic nitpicks. They are NOT nits: each defeats a cold executor and is a real defect. Flag every instance with the same discipline as a one-off. The recurring ones: **action-unspecified** (cat 2 — a step names an action but no procedure/script for it), **unresolvable-referent** (cat 1 — a value/label with no antecedent in text already read), **missing-case / edge-case gap** (cat 5), **silent-format-expectation** (cat 12 — a substituted value whose exact format is load-bearing but unstated), and **missing-WHY-at-point-of-use** (cat 13). Two more are introduced by editing the skill itself: **label-overloading** (one label — e.g. `(b)` — reused for two distinct things) and **unguarded-conditional** (an "if X is available / if applicable" branch with no test for X).

(Orchestrator edit-time guard — applies when addressing these clusters, not to the cold agent's read: re-check each FIX against this list before moving on. The commonest cascade is a fix that *introduces* a fresh instance — an added conditional with no test, a new dangling referent, a value referenced without saying how to derive it. Catching it at edit time is one whole round cheaper than the next trace catching it.)

---

## Reading procedure

This procedure is specific to the executor direction (forward and backward read once each; only the executor needs a two-pass read because the second-pass test — "could the executor act on this without guessing?" — depends on having the document's full world already loaded, which only the first pass establishes). The orchestrator does not coordinate the two passes; they happen entirely within the executor agent's own work, between the pre-flight gate and the first ISSUE emission.

Read SKILL.md and every file in the file list once, in full, from top to bottom. Then read SKILL.md a second time, again from top to bottom, this time as the executor walking through it. The first pass builds the document's world; the second pass walks the executor through that world.

On the second pass, at each line, ask the questions in the category list above, in roughly the order they appear. The order is rough because some categories nest — an unresolvable referent inside a branch trigger is one issue, not two.

When a line is fine, move on without comment. The trace agent's silence on a line is the trace agent's confirmation that the line is clear. Do not narrate the read.

Read all supporting files completely on the first pass so that, on the second pass, when SKILL.md refers to a brief, a script, a reference doc, or a glossary, the executor agent knows whether the reference is reachable. A reference is reachable when the file exists in the file list and contains material that an executor reading at this point could load. A reference to material in a file the executor would not have loaded yet is unreachable.

---

## Worked example — what an `ISSUE` block looks like

```
ISSUE [unresolvable-referent]: SKILL.md step 4 says "read the tracking file and update the row" but two tracking files have been mentioned earlier (the per-source `[source-id]-tracking.md` and the global `phase-status.md`). The executor at step 4 cannot tell which file to open.
File: ~/.claude/skills/p1-next/SKILL.md
Claim: "Step 4: read the tracking file and update the row to status `delta-pending`."
Target: Step 2 references `phase-status.md` as the per-skill status file; step 3 references `[source-id]-tracking.md` as the per-source row store. Step 4 does not say which "the tracking file" refers to. The executor has two candidates and no rule for choosing.
```

```
ISSUE [action-unspecified]: SKILL.md step 6 instructs the executor to "verify the dispatch succeeded" without saying how. The executor following the document literally has no procedure to check.
File: ~/.claude/skills/q1-next/SKILL.md
Claim: "Step 6: verify the dispatch succeeded before proceeding to step 7."
Target: No earlier step describes what `verify` consists of. The executor does not know whether to check a return code, scan the latest session JSONL, read a tracking row, or wait for a sentinel file. Each leads to a different next action.
```
