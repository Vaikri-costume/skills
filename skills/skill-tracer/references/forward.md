# Forward Trace — Definition

A **forward trace** starts from each claim in SKILL.md and works *forward* to verify that the scripts, file paths, and step references it points to actually exist and behave as described.

A forward trace asks: *"SKILL.md claims X — does the script/file/step actually deliver X?"*

This is the approach this trace takes — it reads each claim and walks forward to the reality the claim points at. Any issue surfaced while reading this way is flaggable, regardless of which category list it most closely fits.

Concretely, for each claim in SKILL.md:

1. **Locate the claim** — a stated output format, a script invocation, a cross-step reference, a variable name, a file path, or a decision rule.
2. **Find the target** — the actual script `print()` statement, the actual section heading, the actual file the script writes, the actual field name in the tracking file.
3. **Verify the claim** — does the script produce exactly the format described? Does the referenced step exist with that exact label? Does the variable name match what the script reads from the tracking file?
4. **Check for missing claims** — paths the executor must take (e.g., error branches, edge cases) that SKILL.md describes incompletely or not at all, leaving the executor without instruction when they occur.

---

## What counts as a forward-trace issue

A claim, reference, or section is an issue when one of the following is true. Each item is a complete category; the trace agent flags it with exact-quote evidence.

**1. Exact-string cross-step references.** When step A writes a value (e.g. a status field, a phase-status string) that step B reads and branches on, verify the strings are identical character-for-character. A status string written as `Phase 2 Pass 1 compiled` in one step must match the branching table in another step exactly. Any drift breaks the state machine silently.

**2. Inter-script file chains.** For each temp file a script writes, verify that the downstream script documented as its consumer reads from the same path with the same naming convention. A mismatch is silent — the writer succeeds, the reader fails with a file-not-found that looks like a missing upstream step.

**3. Output-format claims vs. actual `print()`.** When SKILL.md describes a script's output format ("the script outputs JSON with field X"), verify the `print()` statement actually produces that format. Drift here breaks executor parsing.

**4. Variable placeholder namespace.** A placeholder like `[run-id]` must be spelled identically everywhere it appears in the skill. `[id]` and `[run-id]` used interchangeably are ambiguous. Verify every placeholder against all its uses.

**5. Mode-conditional completeness.** For skills with multiple execution modes: for each mode, trace every path and verify no step references a variable, file, or agent output that doesn't exist in that mode's execution path.

**6. Analogous-step symmetry.** Skills with parallel structures (Pass 1 / Pass 2, fresh / delta) have analogous steps handling similar situations. List every case each analogous step handles and cross-check: if step 7 has a "only one agent FOUND" branch, step 3 must too.

**7. Agent description string consistency.** Three places must match exactly: the dispatch log template, the agent `description` parameter at the call site, and the recovery scan regex / re-dispatch log.

**8. Schema-column-name and enum-value consistency.** Verify every column name and enum value appears identically across all uses — agent brief, output-format table, the actual emitted output the executor parses, the compile-script's table-parsing regex, any reference doc that re-states the schema. A column named `Task-source` in the brief but written `task_source` in the parser is silent drift the next stage will swallow with wrong data.

**9. Why-consistency at point of use.** For each rule with a stated reason ("do X **because** Y" / "use X — Y would fail under condition Z"), locate every place that rule appears. Verify each occurrence carries the WHY at the point of use, OR a pointer to a WHY-bearing location the actor reading this occurrence has actually loaded. A rule restated without its reason becomes rote instruction; an agent or future editor reading only that location cannot generalise to edge cases the rule was designed to cover, and cannot evaluate proposed deviations against the original intent. A pointer to a section the actor has not loaded does not resolve the WHY — point-of-use access governs, not document-wide visibility.

**10. Terminology drift.** The same concept is named differently in different materials (a brief calls it "task pattern" while SKILL.md calls it "T-code unit"; one script writes `delta-pending` while a reference doc says `delta_pending`). The executor reading one location and acting on the other reaches the wrong state. Flag with all variant names quoted.

**11. Hidden-information leak in dispatch.** A prompt the orchestrator assembles for a downstream actor (sub-agent, dispatched trace agent, child task) contains information the skill's design — stated in SKILL.md or implied by the dispatch's structure — intends to hide from that actor. Examples: a sub-agent brief that inlines orchestration details when the design keeps briefs self-contained; a cold dispatch that carries prior fix history when each dispatch is independent; a child task prompt that exposes the parent's internal tracking. Quote the design boundary and the actual leak.

**12. List intent unmarked.** A list in SKILL.md, a brief, or a reference doc (categories, examples, cases, values, paths, conditions, options, file types) lacks an explicit marker stating whether the list is exhaustive (a defined closed enumeration — "these are all the X") or illustrative (a non-exhaustive sample — "examples include" / "such as" / "non-exhaustive"). The executor encountering the list cannot tell whether to treat items outside the list as out-of-scope (closed) or as cases requiring the same handling (open). Quote the list and the absent closure marker. This is the enumeration-as-ceiling pattern: a list that looks complete but isn't documented as such can be misread by an executor as a permission boundary, suppressing handling of legitimate cases outside the list.

(Attribution checking is NOT a forward-trace concern. A skill's missing/incorrect attribution is caught by skill-creator-ccvw at scaffold time (`attribution_lint.py`) and by skill-publisher at ship time. The forward trace's job is correctness — does each claim match reality — not lineage credit. If you notice the body claims a behavior that the skill's own SKILL.md/scripts contradict, that's an `internal-contradiction` (a real correctness bug); flag that. But "this skill borrowed a pattern without crediting it" is not a trace finding.)

(These categories overlap and are entry points, not a closed set. The prompt body's "Beyond the listed categories" and "Anti-double-counting" sections govern flagging beyond this list and de-duping overlaps.)

---

## Worked example — what an `ISSUE` block looks like

```
ISSUE [output-format-drift]: SKILL.md describes the script's output as a single bullet list, but the script emits per-line records followed by a JSON summary. An executor parsing per the documented format will fail on the trailing JSON line.
File: ~/.claude/skills/p1-next/SKILL.md
Claim: "Output: `delta-pending: N sources`, `new-pending: M sources`, `backfilled: K sources`."
Target: detect_growth.py prints `BACKFILL source-<id>: <linecount>` per source, then a final JSON line `{"backfilled": N, "delta_pending": M, "warnings": K, "new_corpus3": L}`. Field name is `new_corpus3`, not `new-pending`.
```
