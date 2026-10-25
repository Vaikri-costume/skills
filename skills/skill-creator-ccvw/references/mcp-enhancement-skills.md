# Authoring MCP-Enhancement Skills

How to build a Category 3 (MCP Enhancement) skill — one whose job is to make an existing MCP server's tool access *reliable and well-used*, not merely available. Read this when the Capture-Intent category is MCP Enhancement, or when a skill's purpose is "help Claude use the `<service>` MCP well."

---

## The premise

If the user already has a working MCP server, the hard part (connectivity) is done. The skill is the **knowledge layer on top**: it captures the workflows and best practices that turn raw tool access into consistent, reliable outcomes. Without it, every conversation re-derives how to use the tools, results vary by how the user phrased the request, and failures get blamed on the connector when the real gap was workflow guidance.

So the skill's reason-for-being is to encode *how to use the server well* — the call sequences, the guardrails, the domain knowledge a user would otherwise have to supply by hand.

---

## What to elicit (at Interview-and-Research)

Beyond the generic scoping questions, an MCP-enhancement skill needs:

1. **The happy-path call sequence.** For each use case, the ordered MCP calls that accomplish it, and which call's output feeds the next (e.g. `create_customer` → use its `id` in `create_subscription`). Make the data-passing explicit — it's the most common place these skills break.
2. **Failure and empty-result handling.** What does the skill do when a call errors, returns nothing, or returns a partial result? Name the recoverable cases (retry, fall back, ask the user) vs. the abort cases. An MCP-enhancement skill with no failure handling is the single most common defect.
3. **Rate / ordering / dependency constraints.** Calls that must not run in parallel, rate limits to respect, operations that must happen before others. Encode these as explicit ordering in the workflow.
4. **Tool best-practices and gotchas.** The domain knowledge: which tool to prefer for a given job, arguments that are easy to get wrong, server-specific quirks. This is the embedded expertise that makes the skill worth more than the bare tool list.

---

## How to author it

- Use the **sequential-workflow** and (where quality improves with iteration) **iterative-refinement** authoring patterns from `references/skill-writing-style.md`.
- Name the exact MCP tool names the skill calls (they're case-sensitive) and list them in `allowed-tools`.
- Put the call sequence in the SKILL.md body; put any substantial server-specific reference (tool catalogs, error-code tables) in a `references/<service>.md` file loaded as needed.
- Add an **error-handling** section per the error-handling authoring pattern — for MCP skills this is load-bearing, not optional.

---

## Testing an MCP-enhancement skill

The skill must actually drive the calls correctly, so the test rule for tool/MCP-dependent skills applies in full: the "Tool/MCP-dependent skills" paragraph of `references/eval-run-procedure.md` (at least one real call that succeeds, and how to tell an MCP-setup failure from a skill failure).

The "0 failed API calls per workflow" success target (no tool or MCP call returns an error during a test run of the skill) is specific to skills that coordinate MCP/tool calls — it doesn't apply to a pure document-creation skill that makes no external calls.
