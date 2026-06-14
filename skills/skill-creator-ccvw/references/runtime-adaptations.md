# Runtime Adaptations — Claude.ai and Cowork

The default workflow assumes Claude Code with subagents and a browser. On Claude.ai (browser, no subagents) and Cowork (subagents, no display), some mechanics change. This reference documents what to adapt per feature × runtime.

These three (Claude Code, Claude.ai, Cowork) are the Claude-family runtimes skill-creator-ccvw itself runs in — the list is exhaustive for where the builder executes, so there is no fourth column. The `model-agnostic` tier (Gemini CLI, Cursor, OpenCode, …) describes the portability of the skill being *built*, not a runtime the builder runs in; skill-creator-ccvw is a Claude-Code-targeted builder.

## Adaptation matrix

| Feature | Claude Code (default) | Claude.ai | Cowork |
|---|---|---|---|
| Running test cases | Parallel via subagents | Sequential, no subagents; you run the skill yourself | Parallel via subagents (drop to sequential if timeouts) |
| Baseline runs | Run alongside with-skill | Skip (no meaningful baseline without independent execution) | Run normally |
| Eval viewer | Browser, server-mode | Skip if no browser → present results inline in conversation | `--static <path>` for standalone HTML; user opens link |
| Benchmarking | Quantitative | Skip (depends on baseline) | Quantitative |
| Feedback capture | Auto-saved server-side | Inline in conversation | `feedback.json` downloaded; read from downloads |
| Description optimization | `run_loop.py` / `run_eval.py` | Skip (requires `claude -p`) | Works (uses subprocess, not browser); save until skill is finished |
| Analyst pass (Step 4 sub-step 3) | Run as subagent after aggregation | Skip — dispatch is not available; leave `benchmark.json` `notes` as empty array | Run as subagent after aggregation |
| Blind comparison | Available | Skip (needs subagents) | Available |
| Packaging (`package_skill.py`) | Works | Works (user downloads `.skill`) | Works |

## Claude.ai specifics

**Running test cases without subagents.** For each test case, read the skill's SKILL.md, then follow its instructions to accomplish the test prompt yourself. Do them one at a time. Less rigorous than independent subagents (you wrote the skill and you're also running it, so full context), but a useful sanity check — and the human review step compensates. Skip baseline runs; just use the skill to complete the task. When you grade inline (no grader subagent), still write the same `grading.json` field contract the grader would emit — `summary{pass_rate,passed,failed,total}`, `timing{total_duration_seconds}`, and a per-expectation results array using the exact field names `text`/`passed`/`evidence` — so `aggregate_benchmark.py` reads these inline runs identically to subagent runs (an expectation missing any of those three fields generates a `Warning:` line but is **included** in the output — it is not dropped; fix the malformed expectation and re-aggregate before trusting the numbers). See `references/schemas.md` for the full grading.json shape.

**Reviewing results without a browser.** Present results directly in the conversation. For each test case, show the prompt and the output. If the output is a file the user needs to see (`.docx`, `.xlsx`, etc.), save to the filesystem and tell them where it is so they can download and inspect. Ask for feedback inline: *"How does this look? Anything you'd change?"*

**Iteration loop on Claude.ai.** Same shape — improve the skill, rerun the test cases, ask for feedback — just without the browser reviewer in the middle. Organize results into iteration directories on the filesystem if available.

## Cowork specifics

**Always generate the viewer.** Cowork's setup seems to disincline Claude from generating the eval viewer after running tests. Reiterate: whether you're in Cowork or Claude Code, after running tests, always generate the eval viewer for the human to look at before revising the skill yourself. Use `generate_review.py` — don't write custom HTML. **Generate the viewer BEFORE evaluating inputs yourself.** Get them in front of the human ASAP.

**Headless viewer.** No display → use `--static <output_path>` to write a standalone HTML file instead of starting a server. Proffer a link the user can click to open in their browser.

**Feedback flow.** The viewer's "Submit All Reviews" downloads `feedback.json` as a file (no running server to POST to). Read it from the downloads location (you may have to request access first).

**Packaging.** Works the same as Claude Code — `package_skill.py` needs Python and a filesystem only.

**TodoList reminder.** Cowork tends to skip viewer generation if not explicitly tracked. Add "Create evals JSON and run `eval-viewer/generate_review.py` so human can review test cases" to your TodoList.

## Updating an existing skill (any runtime)

When the user is updating an existing skill (not creating new):
- **Preserve the original name.** Use the skill's directory name and `name` frontmatter field unchanged. E.g., `research-helper` stays `research-helper.skill`, not `research-helper-v2`.
- **Copy to a writeable location before editing.** Installed skill path may be read-only. Copy to `/tmp/skill-name/`, edit there, package from the copy.
- **Stage in `/tmp/` first** if packaging manually, then copy to the output directory — direct writes may fail on permissions.
