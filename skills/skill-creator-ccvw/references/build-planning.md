# Build Planning Across Iterations

How to use `productivity:task-management` (TASKS.md) to track multi-iteration skill builds, plus the skill use-case taxonomy that helps pick what kind of skill you're building. The SKILL.md only needs to know "for multi-iteration builds, use this"; the structure and timing details live here.

---

## Skill use-case categories (pick one at Capture-Intent)

Most skills fall cleanly into one of three categories. If a skill genuinely spans categories (rare), pick the dominant one and note the other in your design notes. If none of the three fits at all, flag it as "other" and proceed — the category is a planning aid, not a gate. Naming the category early tells you which authoring techniques to reach for and which `references/` to lean on. (Anthropic's `plugin-dev/skill-development` guide is the authoritative upstream source for skill structure; this section is the CCVW-flavored quick map — defer to that guide for anything structural it covers more fully.)

### Category 1 — Document & Asset Creation
Produces consistent, high-quality output: documents, presentations, apps, designs, code.
- **Techniques:** embed style guides + brand standards as prose or `assets/` templates; provide template structures for consistent output; add a pre-finalize quality checklist to the SKILL.md body; keep `allowed-tools` conservative (often no external tools — Claude's built-in document/code creation suffices). See `references/skill-writing-style.md` for the output-format-template pattern.

### Category 2 — Workflow Automation
Multi-step processes that benefit from one consistent methodology, including coordination across multiple MCP servers.
- **Techniques:** a step-by-step workflow with explicit validation gates between stages; templates for the common structures; built-in review/improvement sub-steps; iterative refinement loops with a clear stop condition. See the sequential-workflow and iterative-refinement authoring patterns in `references/skill-writing-style.md`.
- **Watch for scriptable steps here especially.** Category-2 skills hide the most *deterministic-validation* steps — "validate at each stage," "check the output matches the schema," "count the rows," "format the record" are illustrative examples of mechanical, same-input→same-output operations (not an exhaustive list — the test is same-input→same-output, not membership in these examples). Per Capture-Intent's design-time script-extraction prompt, mark these to ship as bundled `scripts/` helpers (with an input→output contract) rather than prose the executor re-derives every run. The validation gates *between* stages are the prime candidates; the *decisions* at each gate (proceed? escalate? ask the user?) stay prose.

### Category 3 — MCP Enhancement
Workflow guidance layered on top of an MCP server's raw tool access — turning "you have the tools" into "here's how to use them well."
- **Techniques:** coordinate multiple MCP calls in the right sequence; embed the domain expertise a user would otherwise have to supply; handle the common MCP failure/empty-result cases. When a working MCP server already exists, the skill's reason-for-being is to capture the workflows and best practices that make that server useful — not just to call it. Full modeling guidance: `references/mcp-enhancement-skills.md`.

A skill can blend categories (a workflow-automation skill that also creates documents). Pick the dominant one to choose the primary pattern, then borrow techniques from the others as needed.

---

## Task tracking

The rest of this file covers multi-iteration task tracking.

## When to use it

For any skill build expected to take more than a single-pass draft — i.e., anything where you anticipate at least two iteration cycles, or anything that may span sessions.

Single-pass drafts don't need a parent/subtask structure; they're done before context goes stale.

## Task hierarchy

- **Parent task**: `Build skill <skill-name>: <one-line goal>` — created at scaffold time, marked `in_progress` while iterating, marked `completed` when convergence is declared.
- **Iteration subtasks**: per planned iteration — `Iteration N: design + first eval`, `Iteration N: feedback-driven revisions`, `Iteration N: review`. Moved to `in_progress` at iteration start, `completed` when feedback is read and revisions queued for the next iteration.
- **Iteration-discovered sub-subtasks**: as the orchestrator surfaces issues during an iteration ("need to add a new sub-skill", "eval set needs expansion", "feedback raised a design concern"), add as sub-subtasks under the current iteration. Resolved with the iteration or carried forward as their own iteration subtask if substantive enough.

## When to update the task structure

- **At scaffold time**: create the parent task + the first iteration subtask.
- **At each iteration boundary** (Step 5's "user is done"): mark the current iteration subtask `completed`, update parent task notes with the iteration's pass-rate / key findings, create the next iteration subtask as `pending`.
- **Mid-iteration**: when the orchestrator identifies new work outside the current iteration's scope, add as sub-subtask under the current iteration OR as a new iteration subtask depending on scope.
- **At convergence** (post-skill-tracer if invoked, or at iterate-loop exit otherwise): mark the parent task `completed`. Optionally add a follow-up parent task for `Ship skill <skill-name>` if tier is transitioning to `claude-users` or `model-agnostic`.

## Why this matters

Without explicit task tracking, multi-session skill builds force the user (or the orchestrator) to re-derive the build's state from the workspace each time. With it, re-entering the project shows the full plan + status at a glance via the shared TASKS.md — no workspace inspection required.

## Recovery across sessions (the creator's recovery analog)

This plan-mode + detailed task tree **is** skill-creator-ccvw's recovery mechanism — the build-skill analog of what skill-tracer and skill-publisher do with an `in-flight::` marker + atomic-write + session-JSONL scan. The builder deliberately does NOT use that machinery: a build has no cold-dispatched parallel agents to recover and no ledger to reconstruct — its state lives in the durable plan + the task tree, which already persist across sessions. (A future trace may notice the builder lacks a `recovery-protocol.md` / `recover_dispatch.py` like its siblings — that absence is intentional, documented here.)

Three parts:
- **(a) Durable plan** — the build approach and the design decisions made along the way: use-case category, which steps were marked for scripting, tier, attribution category, captured intent. Held in plan mode (or a plan doc for a large build). This is the "why we're building it this way" a bare task list loses.
- **(b) Detailed task tree** — per-step / per-iteration state: the parent task + iteration subtasks + iteration-discovered sub-subtasks (per the hierarchy above). This is the "where we left off."
- **(c) Recover by reading both on (re)entry** — on resuming a build (new session or post-compaction), read the plan + the task tree FIRST, before touching the workspace or resuming the iterate loop. The task tree's `in_progress` item is the resume point; the plan supplies the decisions that item assumes. No marker to parse, no JSONL to scan.

Keep the task tree granular enough that the `in_progress` subtask alone names the next concrete action — that granularity is what makes the tree a recovery tool, not just a status display.
