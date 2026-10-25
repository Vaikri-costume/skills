# skill-creator-ccvw

## What this skill does

Creates new skills, improves existing ones, and measures skill performance — a CCVW-convention fork of Anthropic's skill-creator. It walks you from "I want a skill for X" through drafting, evaluation (running Claude with and without the skill on test prompts), iteration on feedback, and convergence. Along the way it enforces CCVW structure (mandatory glossary, structured frontmatter, scripts/references/assets directories), checks the marketplace so you don't rebuild something that already exists, and records proper attribution for forked or pattern-derived skills.

It's the **build** phase of a three-skill ecosystem: **build** (this skill) → **trace** (skill-tracer, finds bugs) → **ship** (skill-publisher, polishes + publishes).

## Intent

This skill prioritizes **structural uniformity and provenance correctness** over speed-to-first-draft. Every skill it scaffolds gets the full CCVW structure (README + HISTORY + glossary + the three mandatory dirs) even for a quick personal skill, because the cost of retrofitting structure later is higher than the cost of scaffolding it up front. It also prioritizes **catalog-awareness** — the marketplace-discover pre-check runs before every new build so the user makes an informed build-vs-install decision.

The deliberate trade-off: more scaffolding ceremony at creation time, in exchange for skills that are trace-ready, ship-ready, and attributable from day one. Fixes that strip the mandatory structure "to keep it simple" violate this intent — the structure is load-bearing for the trace + ship phases downstream.

It optimizes for Claude Code as the build environment regardless of the skill's eventual tier; portability to other runtimes is checked at tier-transition and enforced at ship time by skill-publisher, not imposed during the build.

## When to use / When NOT to use

**Use when:**
- Building a new skill from scratch ("I want a skill that does X")
- Improving or evolving an existing skill
- Forking someone else's skill (it captures attribution + preserves LICENSE)
- Running evals to measure a skill's performance or triggering accuracy

**Don't use when:**
- You just want to find bugs in a finished skill → use `/skill-tracer` instead
- You want to ship/publish/PR a traced skill → use `/skill-publisher` instead
- You want to search the marketplace without building → use `/marketplace-discover` directly

## How to invoke

- Slash command: `/skill-creator-ccvw` or natural language
- Natural language: "create a skill for X", "improve my skill Y", "evaluate skill Z", "fork this skill"
- The four decision routes it walks through automatically: Path 1 (installs an existing marketplace match instead of building), Path 2 ("improve my skill Y" — evolves an installed skill), Path 3 (adapts part of someone else's skill — e.g. "adapt the useful part of that skill"), Path 4 (build new from scratch) — you don't need to name the path, just describe what you want.
- The eval/iterate loop (with-skill vs. baseline comparison runs, a browser viewer to review outputs and leave feedback) runs automatically once a draft exists — "test this" / "run the evals" also triggers it directly.
- "keep going until it finds nothing" / "keep improving until nothing new turns up" — runs the opt-in loop-until-dry mode (cap 3 rounds).
- `--static <path>` on the viewer script for a headless/Cowork-friendly single-file report instead of a local server.
- "optimize the description" / "make this trigger better" — runs the description-tuning loop.
- `--with-iterate-quality`, or just asking for readability/efficiency feedback — opts into the extra iterate-quality checks (off by default).
- "is the new version actually better than the old one?" — runs the blind A/B comparison mode.
- `python -m scripts.package_skill <path> <output-dir>` (run from the skill's own directory; the output directory keeps the `.skill` file out of the source tree) — zips a finished skill into an installable `.skill` file for local use.
- Personal settings (workspace, session-log folder, scratch folder, author name, helper model) come from environment variables (`CCVW_EVAL_WORKSPACE`, `CCVW_SESSION_LOG_DIR`, `CCVW_SCRATCH_DIR`, `CCVW_AUTHOR`, `CCVW_HELPER_MODEL`) or a `config/user-profile.md` file, read by `scripts/skill_config.py`; none is required.

Example:
```
"I want a skill that summarizes PDFs into bullet points"
→ marketplace-discover check → intent interview → scaffold (SKILL.md + README + HISTORY + dirs)
→ draft → eval against test prompts → iterate on feedback → suggest /skill-tracer when ready
```
- Also: "turn this conversation into a skill" (answers are taken from the conversation), "make this skill better/smarter" / "add features to a skill" / "plan a skill upgrade" (improve workflow), "fork this skill" / "evolve someone else's skill" (attribution questions and license preservation), skipping evals for subjective skills ("just vibe"), re-entering description optimization when a skill misfires, and resuming an in-progress multi-iteration build in a new session. On Claude.ai or Cowork see `references/runtime-adaptations.md`. When iteration converges the skill suggests `/skill-tracer <name>` then `/skill-publisher <name>`.

## Features & modes

- **Build a new skill.** Walks the whole loop: asks what the skill is for, checks whether one already exists, scaffolds the standard folder (SKILL.md, README.md, HISTORY.md, glossary, scripts/, references/, assets/), drafts it, tests it and iterates. Trigger: "I want a skill that does X", "create a skill for X", or "turn this conversation into a skill" (it takes the answers from the conversation first).
- **Check the marketplace first.** Before any new build it asks marketplace-discover for existing skills. A strong match can be installed instead of building; a weak match waits for your go-ahead. If marketplace-discover is missing or errors, it carries on and builds. Automatic; you can also say you already ran the check and give the result.
- **Improve an existing skill.** Evolves a skill you already have, keeping its attribution, and shows whether the new version beats the old one. Trigger: "improve my skill Y", "make this skill better/smarter", "add features to a skill", "plan a skill upgrade".
- **Adapt part of someone else's skill.** Reads the other skill's licence first, stops and asks if it is unknown or restrictive, takes nothing from a candidate flagged as a red flag, and copies no text unless the licence allows it. It records the source and licence in HISTORY.md. Trigger: "adapt the useful part of that skill" or naming a skill to borrow from.
- **Fork with attribution.** Asks which of four categories fits (direct fork, derivative work, idea inspiration, independent design), records your author name, and keeps the original LICENSE for direct forks. When unsure it picks the more-attributing option. Trigger: "fork this skill", "evolve someone else's skill".
- **Intent capture and test cases.** Asks for 2 to 3 concrete use cases, trigger phrases, output format, what the skill optimises for, standing preferences and audience, then proposes 2 to 3 test prompts saved in the skill's `evals/evals.json`. Steps that must be exact are marked to become scripts. Say so if you want to skip evals (e.g. "just vibe"); the skip is reported.
- **Evals, benchmark and viewer.** Runs each test prompt with and without the skill (or against the old version when improving), grades both, reports pass rates, time and tokens, and opens a browser viewer where you leave feedback. One test runs first as a pilot. Trigger: automatic once a draft exists, or "test this" / "run the evals".
- **Headless viewer.** Writes one self-contained HTML report instead of starting a server, for Cowork or no-browser setups. Automatic there, or `--static <path>` on `eval-viewer/generate_review.py`.
- **Loop until nothing new turns up.** Repeats evaluate-and-improve until a round finds nothing new, capped at 3 rounds, with a ledger of findings and a stated stop reason. Trigger: "keep going until it finds nothing" / "keep improving until nothing new turns up".
- **Blind A/B comparison.** An independent judge compares two outputs without knowing which is which, then a second pass explains the winner. Optional. Trigger: "is the new version actually better than the old one?".
- **Description tuning.** Builds 16 to 20 should-trigger and should-not-trigger queries, lets you review them in a page, then tunes the description in a loop and applies the best one only if the run ended cleanly. Offered after create or improve; or "optimize the description" / "make this trigger better".
- **Iterate-quality checks (opt-in).** Efficiency and readability advisories, off by default. Trigger: `--with-iterate-quality` or ask for readability or efficiency feedback.
- **Lint checks and pre-handoff self-check.** Three checks (frontmatter, portability for the chosen tier, attribution) run at scaffold, at tier changes and before handoff, then a short checklist (description, kebab-case name, a durable log point for multi-stage workflows, examples, every cited reference file exists). Blocking findings must be fixed first; the one exception is an author name that differs from your GitHub login, which you may keep and which is reported. Automatic.
- **Three audience tiers.** `personal`, `claude-users` (default; Claude Code and Cowork) or `model-agnostic`; the tier decides which features and paths are allowed. Set during intent capture. A tier change, install or publish happens only when you explicitly ask.
- **Keeps personal data out.** Workspace, session-log folder, scratch folder, author name and helper model come from environment variables or a profile file, with safe defaults. Session logging is off unless you set a folder. Test helpers run on Sonnet by default, never Opus.
- **Build planning and resume.** Multi-iteration builds keep a plan and task tree so a new session can pick up where the last stopped. Automatic.
- **Other runtimes.** Claude.ai (no helper agents) and Cowork (no display) change how tests run and how feedback is captured; see `references/runtime-adaptations.md`.
- **Local packaging.** Zips a finished skill into a `.skill` file for local use when a file-presenting tool exists: `python -m scripts.package_skill <path> <output-dir>`. Releasing is skill-publisher's job.
- **Handoff.** When iteration finishes it suggests `/skill-tracer <name>` (find bugs, up to 5 cycles), then `/skill-publisher <name>` (polish, tier checks, PR).

## Structure

- **`SKILL.md`** is the workflow the skill follows, from intent capture through packaging, with Examples and a Troubleshooting table.
- **`README.md`, `HISTORY.md`, `LICENSE.txt`** hold this overview, the provenance and changelog, and the preserved upstream licence.
- **`references/`** is background read only when a step needs it:
  - what a CCVW skill must contain: `skill-structure-spec.md`, `portability-spec.md`, `attribution-spec.md`, plus the scaffolds `readme-template.md`, `history-template.md`, `glossary-template.md`, and the vocabularies `ccvw-glossary.md` and `glossary.md`;
  - writing and planning: `skill-writing-style.md`, `build-planning.md`, `mcp-enhancement-skills.md`, `intent-and-decide-details.md`, `iterate-quality-checks.md`;
  - testing and improving: `eval-run-procedure.md`, `improve-existing-skill.md`, `blind-comparison.md`, `description-optimization.md`, `viewer-ui.md`, `recommendations-template.md`, `runtime-adaptations.md`, and the worker prompt templates in `dispatch-prompts/`;
  - checks and delivery: `lint-details.md`, `package-and-present.md`, `schemas.md` (JSON shapes).
- **`scripts/`** are helpers that give the same result every run: linting and validation (`quick_validate.py`, `portability_lint.py`, `attribution_lint.py`, `validate_eval_set.py`); eval running and scoring (`eval_workspace.py`, `render_prompt.py`, `check_isolation.py`, `write_timing.py`, `aggregate_benchmark.py`, `merge_notes.py`, `loop_ledger.py`); description tuning (`run_eval.py`, `run_loop.py`, `improve_description.py`, `generate_report.py`); settings, packaging and shared code (`skill_config.py`, `package_skill.py`, `utils.py`). Their tests are in `tests/`.
- **`agents/`** holds briefs for helper agents: `grader.md`, `comparator.md`, `analyzer.md`.
- **`assets/`** holds `eval_review.html`, the page for reviewing trigger queries.
- **`eval-viewer/`** holds `generate_review.py` and its template `viewer.html`, which make the results viewer.
- **`evals/`** holds this skill's own test prompts (`evals.json`), their fixtures and `graders.py`; it is left out of the packaged `.skill`.
- **Where outputs go:** eval and optimisation runs are never written inside the skill folder. They go to the `eval_workspace` setting, by default `${XDG_DATA_HOME:-~/.claude}/skill-creator-evals-ledger/<skill-name>/` (iteration folders with runs, grades, benchmark, feedback and viewer files, plus trigger-tuning results). A new skill is created in the folder you name, else in the current directory, never straight into `~/.claude/skills/`.

## How to install

This is a `claude-users` tier skill (Claude Code + Cowork) — no user-specific paths, only its own portable `${XDG_DATA_HOME:-$HOME/.claude}/skill-creator-evals-ledger/` namespace. Published at [`Vaikri-costume/skills`](https://github.com/Vaikri-costume/skills); to install elsewhere, copy the `skill-creator-ccvw/` directory into a `~/.claude/skills/` folder, or install the packaged `.skill` archive via Claude Code's or Cowork's skill-install flow.

## Sibling skills

- `skill-tracer` — the **trace** phase. Finds correctness bugs + inconsistencies in a built skill via cold-parallel agents. Suggested at iterate-end.
- `skill-publisher` — the **ship** phase. Polishes, runs tier-transition checks, audits CCVW compliance, and PRs to GitHub. Suggested after trace converges.
- `marketplace-discover` — invoked at the start of every new build to check the live catalog.
- `skill-creator` (upstream) — the Anthropic original this is forked from.

## For developers

The runtime workflow lives in [`SKILL.md`](SKILL.md). Provenance and changelog live in [`HISTORY.md`](HISTORY.md). To trace this skill for bugs: `/skill-tracer skill-creator-ccvw`. To ship a new version: `/skill-publisher skill-creator-ccvw`.
