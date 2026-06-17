# Backward Trace — Definition

A **backward trace** reads the skill starting from each script's actual `print()` / `sys.exit()` / file-write statements, each script-output file, and each agent brief's documented output format. From each output, the agent works back toward SKILL.md and the supporting files to find every place that claims to consume, interpret, or act on that output, and verifies the consumer is accurate, exhaustive, and present.

A backward trace asks: *"The producer emits X — does every place that references X describe it correctly, and does every value X can take have a documented handling?"*

This is the approach this trace takes — it reads the materials from producers back to consumers. Any issue surfaced while reading this way is flaggable, regardless of which category list it most closely fits.

---

## What counts as a backward-trace issue

A line, output, or step is an issue when one of the following is true. Each item is a complete category; the trace agent flags it with exact-quote evidence.

**1. Missing consumer for an actionable error output.** A script emits an error reachable in normal execution flow (not gated by an upstream failure that would have already aborted), but no step in SKILL.md tells the executor how to handle it. Quote the error production site and note the absence.

**2. Missing consumer for a decision output.** A script (or an agent brief's documented output) emits a value the executor must branch on — `FOUND` vs `NOT_FOUND`, exit codes, JSON summary fields, enum cells in an agent's output table — but no step in SKILL.md reads the value. Quote the production site and note the absence.

**3. Incomplete case coverage on a documented consumer.** SKILL.md reads the output and acts on some of its possible values, but not all. Three exit codes possible, two documented. Five enum values permitted, four handled. List every value the output can take; verify each has an explicit instruction. A consumer that handles two of three cases is a real gap even if it looks documented.

**4. Output of uncertain classification.** When you cannot confidently classify an output as informational (always prints, no branching signal — `Cleanup complete.`) or upstream-failure (only reachable after a prior gate would have aborted), default toward the consumer-required side (actionable or decision) and flag the output. Note the classification you considered under `Target:`. The orchestrator confirms the classification.

**5. Guard problem.** A guard intended to make an error unreachable has partial coverage, unclear trigger conditions, or covers some paths to the output and not others. Flag the output and quote the guard. The orchestrator confirms the guard's coverage.

**6. Sequencing violation.** A step reads a value `X` produced by a step that comes later in SKILL.md. The producer must come before the consumer; reading backward from the consumer to find the producer reveals the inversion. Quote both sites.

**7. Name drift between producer and consumer.** The name the consuming step uses is not identical to the name the producing step assigns. A status string written `Phase 2 Pass 1 compiled` and read `Phase 2 - Pass 1 compiled` is silent drift. The producer's name and every reader's name must match character-for-character. Quote all sites.

**8. Synthesis missing.** A step references a value with no upstream producer in the skill. The value is neither harness-supplied (see External-input rule) nor produced by any earlier step or script. Quote the consuming step.

**9. Declared-but-unused input (incomplete step).** A step lists an input or captured value that no part of the step body actually consumes. This usually signals an incomplete step — the step was meant to use the value and the wiring was never finished, so the executor holds a value with no instruction to act on it. Quote the listing and the empty consumer. (This is a correctness gap — a missing use — not a cleanup suggestion.)

**10. Bare rule referenced downstream without WHY.** For each rule the step enforces or relies on, locate the rule's primary statement. A rule referenced from a step whose decisions depend on edge-case judgement, with the rule stated bare ("do X" with no reason given), is a gap — the executor and any future editor cannot evaluate edge cases, cannot decide whether a proposed deviation is safe, and cannot tell whether the rule still applies when the surrounding context changes. Quote the bare statement and the downstream reference.

**11. Hidden-information leak from producer to consumer.** A producer (script output, brief, dispatch-assembly step) emits information into a consumer context the skill's design intends to keep blind to it. Examples: an orchestrator step that writes the fix history into the next cold dispatch's prompt when each dispatch should be independent; a brief-assembly step that injects parallel-agent structure into a brief the design says is self-contained; a status file the producer writes that an unintended consumer ends up reading. Quote the design boundary (explicit in SKILL.md or implicit in the structure) and the actual leak.

**12. Enum closure unmarked.** A producer (script, brief, schema definition, configuration enum, status-field documentation) emits or documents a list of permitted values without specifying whether the list is closed (the only values that can occur — anything else is a contract violation requiring the consumer to refuse or error) or open (representative values — others may legitimately appear and need handling). The consumer reading the enum cannot tell how to interpret an unlisted value. Closely related to category 3 (incomplete case coverage), but distinct: there the consumer documents N cases when N+1 values can occur; here the producer's enum itself is intent-ambiguous, so neither side knows what the contract is. Quote the producer's listing and the consumer's reading, plus the absent closure marker.

For skills that dispatch agents with inlined briefs, the brief's documented output format is treated as a script-output equivalent for categories 1–4: the brief is the producer; every column and enum value the brief tells the agent to emit is an output value the executor's parser must handle; case coverage on every documented enum value applies. Agents following text instructions are producers just like scripts with `print()`.

(These categories overlap and are entry points, not a closed set. The prompt body's "Beyond the listed categories" and "Anti-double-counting" sections govern flagging beyond this list and de-duping overlaps.)

---

## Worked example — what an `ISSUE` block looks like

```
ISSUE [missing-consumer-case]: p1_recovery.py exits with code 2 when the dispatch JSONL is missing, but SKILL.md §1a documents only exit codes 0 and 1. An executor encountering exit 2 has no documented action.
File: ~/.claude/skills/p1-next/SKILL.md
Claim: "Decision rules: Both agents FOUND → ... ; One FOUND, one NOT FOUND → ... ; Both NOT FOUND → ..."
Target: p1_recovery.py line 93: `print(f"ERROR: dispatch JSONL not found: {jsonl_path}", file=sys.stderr); return 2`. SKILL.md does not describe what the executor should do on exit 2.
```
