# Iterate-Quality Checks

Quality checks skill-creator-ccvw applies during the iterate-loop (opt-in via `--with-iterate-quality`). These were absorbed from skill-tracer's cadenced trace directions (efficiency + accessibility) — but adapted: instead of being dispatched as cold-parallel agents (skill-tracer's model for finding correctness bugs), these run as an **orchestrator-side checklist** the builder walks during iteration to catch quality issues before the skill goes to trace + ship.

**Why these live in the builder, not the tracer:** skill-tracer's job is correctness (does the skill have bugs/inconsistencies?). Efficiency and accessibility are quality concerns — a skill can be bug-free but wasteful or hard to read. Those are the builder's job to get right during iteration, and the publisher's job to final-check before release. The tracer stays focused on correctness.

**When to run:** during the iterate-loop, after each draft, when `--with-iterate-quality` is set. Default off (the publisher runs the final quality gate at ship time); on when the user wants quality feedback earlier in the build.

**How to apply:** the orchestrator reads the current SKILL.md (and supporting files) and walks each category below, surfacing findings to the user as quality observations (not blocking — the user decides which to act on). Unlike trace findings, these don't go on a ledger — they're iterate-time advisories.

---

## Efficiency checks

Read SKILL.md and supporting files hunting for wasted work — redundant operations, missed caching, oversized prompts, procedures that take N steps when fewer would suffice. The question: *"For each operation the executor performs, is it necessary? Is it minimal? Does it reuse prior work or redo it?"*

**1. Redundant re-reads.** A step that reads a file the executor already read in this workflow without intervening writes. Two consecutive `Read` calls for the same path; a script re-loading a config it has in memory.

**2. Redundant re-computations.** A step computing a derived value already computed and cacheable. Two `find` calls for the same pattern; two `jq` extractions of the same field.

**3. N+1-style patterns.** A loop issuing one external call per item when one bulk call would fetch all. Per-file shell-out when a single glob would do; per-result re-dispatch when one batched call covers them all.

**4. Oversized prompts.** A dispatched-agent prompt including more context than the agent consumes. Inlining a full reference doc when one section is read; passing the entire ledger when only the recent round is needed.

**5. Missed caching.** An expensive operation whose result is stable across invocations, with no caching layer. A daily-changing API result fetched every call; an expensive `find` over a rarely-changing tree.

**6. Inefficient procedure.** N actions to reach an end-state another step reaches in fewer. Three sed calls when one would do; a multi-pass rewrite when single-pass works.

**7. Synchronous when parallel is possible.** Independent operations issued serially when they could run in parallel. Dispatching agents one at a time when same-turn batch is supported.

**8. Unbounded growth.** State accumulated without trimming — a log never rotated, an in-memory list growing per iteration without a maxlen, a session JSONL re-scanned from the beginning when the tail is what matters.

**9. Wrong granularity of dispatch.** Dispatching a sub-agent for a task trivial enough to do inline (dispatch cost > task cost), or running inline a task heavy enough to warrant a sub-agent.

**10. Tool-call thrash.** Many small tool calls when one larger call would do — multiple `Edit` calls for adjacent lines; multiple `Bash` invocations when a single piped command runs end-to-end.

**11. Speculative work.** Work done upfront whose result is only used in a rare branch — fetching data only consumed in an error path; parsing structures only acted on under a low-probability condition.

**12. Re-reading own prior output.** A step that writes a file then re-reads it instead of using the value the script had in hand.

**13. Pessimistic concurrency limits.** A script serialized "to be safe" when the actual contention surface allows parallelism without correctness risk.

**14. Repeated agent dispatches with overlapping context.** Multiple agents dispatched for related work, each receiving the same large context block independently.

---

## Accessibility checks (general readability — cats 1-14)

Read SKILL.md, instructions, and output templates checking whether the skill's text is reachable, understandable, and operable by users with diverse needs — varying expertise, native languages, assistive-technology setups, sensory abilities, reading contexts. The question: *"Can someone without my context, without my visual baseline, without my technical fluency, follow this skill?"*

**1. Unexplained jargon.** A technical term used without definition or pointer-to-definition at point-of-use. "compaction" without saying what it is; "JSONL" without "newline-delimited JSON"; "MCP server" without context.

**2. Acronyms without expansion.** Acronyms on first mention without spelling out. "PR" without "pull request" at first occurrence; "MCP" without "Model Context Protocol".

**3. Color-only or visual-only signals.** Outputs conveying state via color/visual cue without a text label. A "red"/"green" status with no PASS/FAIL text; an HTML report using badge color as the only success-indicator.

**4. Missing alt text in generated content.** A skill producing images, diagrams, charts without alt-text or a textual fallback.

**5. Dense walls of instruction.** A step/section running more than ~80 lines without subheadings, lists, tables, or visual breaks. Hard to scan, easy to lose place in, especially for screen-reader users.

**6. Implicit cultural / regional / temporal context.** Instructions assuming a timezone, currency, locale, calendar, or reading order without making it explicit. "by end of day" without timezone; "$50" without currency code.

**7. Required mouse / GUI / touch interaction.** Outputs/instructions requiring click, hover, drag, or non-keyboard action without a keyboard-accessible alternative.

**8. Single-modality output.** Primary output in one modality (audio only, visual only) without a textual alternative.

**9. Reading-level mismatch.** A skill targeted at non-experts written at expert-level complexity, OR an expert-targeted skill written with so much hand-holding it's slow to read for its audience.

**10. Language-only-in-one-language.** Examples/prompts/templates only in one language when the user base spans multiple.

**11. Time-pressure language.** "Quickly", "immediately", "right now", "without delay" used as instructions when no real time constraint exists. Creates stress for users with processing-time differences.

**12. Sensory-required confirmations.** Requiring the user to verify success by looking at a visual element, listening to an audio cue, or feeling a vibration — without an alternative verification path.

**13. Assumed prior knowledge.** Instructions referencing earlier steps, prior conversations, prior runs without making the reference explicit. "as you saw before"; "the same way we did it last time".

**14. Inaccessible error messages.** Errors surfacing as exit codes, raw stack traces, or technical strings without human-readable explanation of what went wrong and what the user can do.

---

## Note on accessibility cats 15-16 (personalization + plan-code leakage)

The original accessibility direction in skill-tracer had two more categories:
- **Cat 15** — author-identity / personalization leakage (the skill mentions a specific person's name, hardcodes a username, references "my"/"I built this for")
- **Cat 16** — plan-document / decision-code references (the skill body references internal planning artifacts like "(per D5)", "(per the plan)")

These are NOT in this file — they moved to `references/portability-spec.md` "Personalization rules" section and are enforced by `scripts/portability_lint.py` (they're portability/shareability concerns: a skill that leaks the author's identity or references a plan file the installer doesn't have isn't cleanly shareable). The iterate-quality checks here cover general readability (cats 1-14); the lint covers personalization (cats 15-16).

---

## Output of an iterate-quality check

Unlike trace findings (which go on a ledger with FIX/STRENGTHEN/USER-PAUSE addresses), iterate-quality findings are surfaced to the user as a simple advisory list:

```
Iterate-quality check (efficiency + accessibility):
  Efficiency:
    - Step 4 reads prompt-template.md, then Step 7's loop-back re-reads it each round (cat 1, redundant re-read). Consider capturing once.
    - Step 9 dispatches 3 lint invocations serially (cat 7, parallelizable). Consider same-turn batch.
  Accessibility:
    - "MCP" used at line 40 without expansion (cat 2). First-use should spell out "Model Context Protocol".
    - Step 1 runs 95 lines without a subheading (cat 5, dense wall). Consider sub-step labels.

These are quality advisories, not bugs. Address the ones that matter for your skill's audience; skip the rest. The publisher will re-check at ship time.
```

The user decides which to act on. No ledger, no convergence loop — just feedback during iteration.
