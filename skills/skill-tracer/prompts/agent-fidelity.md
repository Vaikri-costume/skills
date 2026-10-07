## Task — fidelity (F)

You are the **fidelity (F)** agent. Your job is to surface semantic defects: places where what the skill *says* diverges from what it *does*, where meaning is ambiguous enough that a consumer would have to guess, or where a claim is silently broken across execution paths.

You run **both reading orders internally** before writing any findings:

- **Forward pass** — start from each claim in SKILL.md and work forward to verify that the scripts, file paths, step references, and briefs it points to actually deliver what the claim asserts. Ask: *"SKILL.md claims X — does the script / file / step / brief actually deliver X?"*
- **Backward pass** — start from each script's actual `print()` / `sys.exit()` / file-write statements, each script-output file, and each brief's documented output format. From each output, work back to SKILL.md and the supporting files to find every place that claims to consume, interpret, or act on that output, and verify the consumer is accurate and exhaustive. Ask: *"The producer emits X — does every place that references X describe it correctly?"*

Both passes must complete before you output anything. The pass in which you found an issue is internal working — do not narrate it in the report.

---

### Checks

#### why-consistency-at-use

**Trigger:** A rule or constraint with a stated reason ("do X **because** Y" / "use X — Y would fail under condition Z") is restated or applied at a **claim or reference site** but the WHY is absent at that site, with no followable pointer to a WHY-bearing location the actor at that site has loaded.

**Scope:** claim and reference sites in SKILL.md, briefs, and reference docs. A rule whose WHY is co-located with or immediately preceding the reference site does not count. A followable pointer resolves the WHY for the full-skill executor (Read access to every file in scope); the WHY is missing only when the actor is a **narrowed context** — an inlined-brief sub-agent whose subset structurally excludes the WHY-bearing location.

**CONFIRM-IF:** a rule reference site carries only the bare instruction ("do X") with the rationale appearing only in a distant file; AND the actor at that site is either narrowed (brief-subset) or has no path to the WHY even via pointer.

**REJECT-IF:** the rationale is self-evident from the rule text itself ("path must be absolute"); OR the pointer is followable and the WHY material is present at the destination.

**Worked example:**

```
ISSUE [why-consistency-at-use]: SKILL.md §2 states "always emit timestamps in UTC — local-timezone drift caused silent dedup failures in prior runs," but the inlined sub-agent brief in Step 4 carries only "always emit timestamps in UTC" with no rationale and no pointer to §2 or any WHY-bearing location the brief's narrowed context includes.
File: SKILL.md
Claim: SKILL.md:17 "Step 4 brief: 'Emit each result row with a UTC timestamp.'"
Target: The sub-agent operating from the inlined brief cannot evaluate whether the rule applies to a user-supplied timestamp that already includes a timezone offset — the rationale ("dedup failures under local-timezone drift") is the only basis for that edge-case judgment, and it is absent from every location the brief-scoped actor can reach.
```

---

#### hidden-info-leak-in-dispatch

**Trigger:** A prompt the orchestrator assembles for a downstream actor (sub-agent, dispatched trace agent, child task) contains information the skill's design — stated in SKILL.md or implied by the dispatch's structure — **intends to hide from that actor**.

This is the **dispatch-boundary** implicit-context case: the leak is that the assembled prompt carries context the receiving actor was designed to be blind to. Examples: a sub-agent brief that inlines orchestration details when the design keeps briefs self-contained; a cold dispatch that carries prior fix history when each dispatch is stated to be independent; a child task prompt that exposes the parent's internal tracking state.

Quote the **design boundary** (explicit in SKILL.md or implicit in the dispatch structure) and the **actual leak**.

**Boundary note:** this check is about what the orchestrator *puts into* the dispatch prompt that should not be there. A silent transformation the producer applies to its *output data* before handoff — undeclared to the downstream consumer — is producer-to-consumer-hidden-leak, not this check.

**CONFIRM-IF:** the SKILL.md design boundary (explicit statement of cold dispatch, brief self-containment, independence, etc.) is present AND the actual prompt-assembly step inlines material that violates that boundary.

**REJECT-IF:** the material present in the prompt is high-level routing info ("routes to agent X for task Y") without revealing the agent's private decision criteria or internal state.

**Worked example:**

```
ISSUE [hidden-info-leak-in-dispatch]: The orchestrator's sub-agent prompt inlines the full fix history from the prior round, but SKILL.md §3 states "each dispatch is cold and independent."
File: SKILL.md
Claim: SKILL.md:24 "§3 Dispatch: each agent is dispatched cold with no prior-round context."
Target: Step 6 prompt-assembly block: "Include full fix_log.jsonl content in the agent prompt at dispatch" — the fix history is passed verbatim to a cold-dispatch actor, breaking the independence boundary.
```

---

#### list-intent-unmarked

**Trigger:** A list in SKILL.md, a brief, or a reference doc (categories, examples, cases, values, paths, conditions, options, file types) lacks an explicit marker stating whether the list is **exhaustive** ("these are all the X" / "only the following") or **illustrative** ("examples include" / "such as" / "non-exhaustive"). An executor encountering the list cannot tell whether items outside the list are out-of-scope (closed) or require the same handling (open).

This is the **enumeration-as-ceiling pattern**: a list that looks complete but is not documented as such can be misread as a permission boundary, suppressing handling of legitimate cases outside the list. Quote the list and the absent closure marker.

**CONFIRM-IF:** the list's intent is inferable from context but not stated, AND misreading intent would cause an executor to make a material error — treating a non-exhaustive set as a ceiling and suppressing legitimate cases, or treating an exhaustive set as extensible and adding invalid members.

**REJECT-IF:** the list is prefaced with "e.g." or "such as" (obviously illustrative); numbered steps with explicit sequencing language (obviously ordered); or prefaced with "including" or "among others" (obviously open-ended).

**Worked example:**

```
ISSUE [list-intent-unmarked]: SKILL.md §5 lists four output categories — "summary", "warning", "error", "skipped" — with no marker indicating whether these are the only categories the parser will emit (closed) or representative examples (open). An executor building a handler cannot determine whether an unlisted category such as "info" should be suppressed as out-of-scope or forwarded with the same handling as "summary."
File: SKILL.md
Claim: SKILL.md:31 "§5 Output categories: summary, warning, error, skipped."
Target: The list carries no closure marker ("only the following" / "exhaustive" / "examples include" / "non-exhaustive") — the enumeration-as-ceiling pattern: a list that looks complete but is undocumented as such functions as a silent permission boundary, suppressing handling of any category outside it.
```

---

#### output-of-uncertain-classification

**Trigger:** You cannot confidently classify an output as **informational** (always prints, no branching signal — "Cleanup complete.") or **upstream-failure** (only reachable after a prior gate would have aborted). When classification is uncertain, default toward the consumer-required side (actionable or decision) and flag. Note the classification you considered under `Target:`. The orchestrator confirms.

**Scope:** script `print()` / `sys.exit()` outputs, brief-documented output values, and any emitted value a downstream step must act on.

**CONFIRM-IF:** a cold reader cannot determine whether the output is informational or requires executor action, AND defaulting to the wrong category would cause wrong executor behavior.

**REJECT-IF:** the output's category is obvious from context (a single-sentence yes/no, a file path, a numeric score with stated scale) or the skill's invocation context makes the category unambiguous.

**Worked example:**

```
ISSUE [output-of-uncertain-classification]: scan.py emits "WARNING: source count exceeds threshold" on a path that is reachable in normal flow, but SKILL.md does not instruct the executor to act on it; a cold reader cannot determine whether this is informational or a decision signal requiring a branch.
File: SKILL.md
Claim: SKILL.md:38 (no consuming step documented for this output)
Target: scan.py line 78: `print("WARNING: source count exceeds threshold")` — emitted when source_count > MAX_SOURCES, a condition reachable in normal execution; classification considered: uncertain between informational and actionable; defaulting to actionable because executor behavior differs if this is a gate.
```

---

#### guard-problem

**Trigger:** A guard intended to prevent a downstream step from firing under a stated precondition — but the precondition has partial coverage, an unclear trigger condition, or covers some paths to the guarded step and not others. Flag the guarded step and quote the guard.

**CONFIRM-IF:** the prose guard claims to protect against a condition but at least one path to the guarded step exists that the guard does not cover; OR the guard's trigger condition is stated ambiguously so it is unclear which inputs it blocks.

**REJECT-IF:** the guard is described as conservative by design ("fail-safe default"), or the guard's scope is explicitly narrower than the full risk and that narrowness is documented.

**Worked example:**

```
ISSUE [guard-problem]: SKILL.md §3 documents a guard — "Skip Step 5 (source compilation) if the tracking file is absent" — but Step 5 is also reachable when the tracking file exists but contains zero entries. The guard covers the absent-file path and not the zero-entry path; Step 5 fires on zero-entry input despite the precondition ("no sources to compile") being equally unsatisfied.
File: SKILL.md
Claim: SKILL.md:45 "§3 Guard: if tracking file is absent, skip Step 5 and proceed to Step 6."
Target: Step 5 is reachable when the tracking file exists with zero entries — a path the guard does not cover. The guarded step (source compilation) fires on empty input, producing a zero-row output file that causes Step 6's branch to mis-classify the run as a successful empty compile rather than a skipped run.
```

---

#### bare-rule-referenced-without-WHY (claim/reference site)

**Trigger:** A rule or constraint **referenced** at a downstream claim or prose site — enforced in a prompt, invoked in a brief, restated in a reference doc — with (a) no rationale present at the reference site and (b) the actor's correct behavior depends on understanding why the rule exists (to know whether to propagate it, override it, or apply it conditionally to edge cases).

**Scope:** this check fires on **rule reference sites** in claims and prose docs. The definition site and reference site must be distinct locations.

**CONFIRM-IF:** the rule appears bare at the reference site with no WHY or pointer to a WHY; AND the actor at that site would make wrong edge-case decisions without knowing the reason (e.g., a sub-agent brief that carries "always use UTC timestamps" with no reason cannot evaluate whether that rule applies to a user-supplied timestamp that includes a timezone).

**REJECT-IF:** the rule's rationale is self-evident from the rule text itself; OR the rationale is stated immediately before or after the reference in the same passage; OR the reference site and definition site are the same passage.

**Worked example:**

```
ISSUE [bare-rule-referenced-without-WHY]: The sub-agent brief in Step 6 invokes the rule "never write partial output files — always write atomically to a temp path then rename" with no rationale and no pointer to a WHY-bearing location. The brief-scoped actor cannot evaluate whether the rule applies when writing to a network mount where rename is non-atomic, or whether a direct write is acceptable when the output path is already a temp path.
File: prompts/brief-step6.md
Claim: prompts/brief-step6.md:52 "Output rule: never write partial output files — always write atomically to a temp path then rename."
Target: The rule's definition site (SKILL.md §7) states the reason: "partial writes caused downstream parsers to read truncated JSON mid-write in prior runs." That rationale is absent from the brief and no pointer from the brief reaches §7 — the actor at this reference site cannot generalize to edge cases the rule was designed to cover.
```

---

#### producer-to-consumer-hidden-leak

**Trigger:** In a data pipeline (one skill component produces structured data that another consumes), the producer embeds **assumptions, filters, or transformations that are invisible to the consumer** and are not declared in the handoff contract. The consumer's behavior would differ if it knew — but it cannot, because the transformation is undeclared.

Quote the **design boundary** (the stated or implied handoff contract) and the actual undeclared transformation.

**Boundary note:** this check is about what the producer *does to its output data* before handing it off — an undeclared downstream-channel transformation (deduplication, sorting, field-dropping, normalization). The dispatch-boundary case — where the orchestrator puts information into a prompt that an actor was designed to be blind to — is hidden-info-leak-in-dispatch, not this check.

**CONFIRM-IF:** the producer applies a transformation before write/handoff AND the consuming step's documented behavior assumes raw/untransformed output (e.g., a count-based branch that assumes the raw count, when the producer deduplicates before writing).

**REJECT-IF:** the transformation is detectable by the consumer from the output shape alone (e.g., a sorted list the consumer can observe to be sorted); OR the transformation is irrelevant to the consumer's documented logic.

**Worked example:**

```
ISSUE [producer-to-consumer-hidden-leak]: The compile script silently deduplicates FOUND results before writing the output file, but the consuming step in SKILL.md branches on "2+ FOUND entries" with logic that assumes the raw count.
File: SKILL.md
Claim: SKILL.md:59 "Step 8: if compile output contains 2+ FOUND entries, escalate to recovery."
Target: compile.py line 33: `results = list(set(found_entries))` — duplicates removed before write; the consumer's ≥2 threshold sees the deduplicated count, not the raw agent output count SKILL.md's branching logic was designed around.
```

---

#### enum-closure-unmarked

**Trigger:** A value-set documented in SKILL.md, a brief, or a reference schema (statuses, categories, states, options) does not specify whether the set is **closed** (only these values are valid — anything else is a contract violation) or **open** (representative values — others may legitimately appear and need handling). A consumer building a handler, branch, or router over the set makes structurally different choices depending on closure intent. Neither side knows what the contract is because the producer's documented enum is intent-ambiguous.

**CONFIRM-IF:** a consumer building a handler over the value-set would make different structural choices (add a catch-all vs. hard-fail on unknown values) depending on closure intent, AND the contract document provides no signal either way.

**REJECT-IF:** closure is evident from domain (boolean true/false; HTTP status code class); OR a consumer has already written an explicit default/catch-all, resolving the ambiguity on its side.

**Worked example:**

```
ISSUE [enum-closure-unmarked]: SKILL.md §4 documents the agent output contract's "result" field as taking values "FOUND", "NOT_FOUND", or "SKIPPED" with no closure marker. The consuming step branches on FOUND vs NOT_FOUND and is silent on SKIPPED — but neither producer nor consumer knows whether "SKIPPED" is the complete third value (closed: hard-fail on anything else) or one of several possible non-terminal states (open: others may appear). A consumer building a handler makes structurally different choices — add a catch-all vs. hard-fail on unknown values — depending on closure intent, and the contract provides no signal either way.
File: SKILL.md
Claim: SKILL.md:66 "§4 Agent output contract: result field — one of: FOUND, NOT_FOUND, SKIPPED."
Target: The value-set carries no closure declaration ("only these three values are valid" / "representative — others may appear"). The consuming step (Step 7) branches on FOUND and NOT_FOUND; SKIPPED is undocumented at the consumer. A future producer emitting "DEFERRED" would be indistinguishable from a contract violation vs. a legitimate open-enum extension.
```

---

#### sequencing-violation

**Trigger:** A consumer step reads, uses, or depends on a value that is produced by a **later** producer step — step M consumes something that step N produces, where M runs before N in the skill's documented execution order. The consumer step receives a stale, empty, or undefined value at runtime.

Quote both the consuming step and the producing step with their positions in the execution order.

**CONFIRM-IF:** the consuming step names or uses a variable, file, state, or output that only comes into existence in a later step in the execution order AND the dependency is in the execution path (not merely in documentation order).

**REJECT-IF:** the value is produced outside the skill (by a prior skill, by the environment, or by user input) and merely referenced within the skill; OR the value is read-only persistent state that survives across invocations.

**Worked example:**

```
ISSUE [sequencing-violation]: Step 3 branches on the value of `compile_output_path`, but that path is not written until Step 7 runs the compile script — Step 3 runs first and reads an undefined variable.
File: SKILL.md
Claim: SKILL.md:73 "Step 3: if compile_output_path exists, skip re-compile; otherwise proceed."
Target: compile_output_path is first written in Step 7: "Run compile.py; the output is written to compile_output_path." Step 3 precedes Step 7 in the documented execution order, so the path is undefined when Step 3 evaluates it.
```

