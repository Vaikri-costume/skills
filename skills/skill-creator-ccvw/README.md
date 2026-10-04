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
- The three decision routes it walks through automatically: Path 1 (installs an existing marketplace match instead of building), Path 2 ("improve my skill Y" — evolves an installed skill), Path 3 (build new from scratch) — you don't need to name the path, just describe what you want.
- The eval/iterate loop (with-skill vs. baseline comparison runs, a browser viewer to review outputs and leave feedback) runs automatically once a draft exists — "test this" / "run the evals" also triggers it directly.
- `--static <path>` on the viewer script for a headless/Cowork-friendly single-file report instead of a local server.
- "optimize the description" / "make this trigger better" — runs the description-tuning loop.
- `--with-iterate-quality`, or just asking for readability/efficiency feedback — opts into the extra iterate-quality checks (off by default).
- "is the new version actually better than the old one?" — runs the blind A/B comparison mode.
- `python -m scripts.package_skill <path>` (run from the skill's own directory) — zips a finished skill into an installable `.skill` file for local use.

Example:
```
"I want a skill that summarizes PDFs into bullet points"
→ marketplace-discover check → intent interview → scaffold (SKILL.md + README + HISTORY + dirs)
→ draft → eval against test prompts → iterate on feedback → suggest /skill-tracer when ready
```
- Also: "turn this conversation into a skill" (answers are taken from the conversation), "make this skill better/smarter" / "add features to a skill" / "plan a skill upgrade" (improve workflow), "fork this skill" / "evolve someone else's skill" (attribution questions and license preservation), skipping evals for subjective skills ("just vibe"), re-entering description optimization when a skill misfires, and resuming an in-progress multi-iteration build in a new session. On Claude.ai or Cowork see `references/runtime-adaptations.md`. When iteration converges the skill suggests `/skill-tracer <name>` then `/skill-publisher <name>`.

## Features & modes

- **Build a new skill from scratch.** Runs the full create loop: interviews you about intent, checks the marketplace, records attribution and author, scaffolds the mandatory CCVW structure (`SKILL.md`, `README.md`, `HISTORY.md`, `scripts/`, `references/`, `assets/` and a glossary), drafts, then evaluates and iterates. Trigger: "I want a skill that does X", "create a skill for X", or "turn this conversation into a skill" (it pulls the answers from the conversation first).
- **Marketplace check, install instead of building.** Runs before every new build: searches the live catalog, and if a strong match exists you can install it and stop. If marketplace-discover isn't installed it skips the check and carries on. Automatic; or ask "is there already a skill for X?".
- **Improve or evolve an existing skill.** Hands off to a dedicated improve-existing-skill workflow that keeps the original's attribution and can reuse the eval and viewer machinery to show whether your changes helped. Trigger: "improve my skill Y", "make this skill better/smarter", "add features to a skill", "plan a skill upgrade", or choosing to build on a near-match from the marketplace.
- **Fork with attribution.** Asks which of four categories applies (direct fork, derivative work, idea inspiration, independent design), records the answer and the author in `HISTORY.md`, and keeps the original `LICENSE`; when unsure it picks the more-attributing category. Trigger: "fork this skill", "evolve someone else's skill".
- **Intent capture and test-case setup.** Asks for 2-3 concrete use cases, trigger phrases, output format, what the skill optimizes for, your standing preferences and the intended audience; marks mechanical steps to become bundled scripts rather than prose; proposes 2-3 test prompts saved to `evals/evals.json` inside the skill. You can skip evals for subjective skills. Automatic during a build.
- **Evals, benchmark and results viewer.** For each test prompt it runs the skill and a baseline (no skill, or the previous version) at the same time, grades both, computes pass-rate, time and token stats, and opens a browser viewer (Outputs and Benchmark tabs plus a Recommendations sidebar) where you leave feedback per run. Repeats until you're happy or progress stalls. Trigger: automatic once a draft exists, or "test this" / "run the evals".
- **Headless and Cowork viewer.** Writes one self-contained `review.html` instead of starting a local server. Automatic on Cowork and other no-server runtimes, or `--static <absolute-path>` on `eval-viewer/generate_review.py`. Claude.ai differs more (no subagents, often no browser); those adaptations are in `references/runtime-adaptations.md`.
- **Blind A/B comparison.** An independent judge compares two versions' outputs without knowing which is which; a follow-up pass explains why the winner won (ties are reported, not analyzed). Optional and more rigorous than the normal loop. Trigger: "is the new version actually better than the old one?".
- **Description optimization.** Builds 16-20 realistic should-trigger and should-not-trigger queries, lets you review and edit them in a small HTML picker, then a background loop of up to 5 rounds tunes the skill's description using a 60/40 train/held-out split and picks the best by held-out score. Offered after a skill is created or improved, or "optimize the description" / "make this trigger better"; re-run later with real queries the skill got wrong.
- **Iterate-quality checks (opt-in, off by default).** Efficiency and readability advisories (wasted work, jargon, dense text), separate from correctness grading. Trigger: `--with-iterate-quality`, or ask for readability or efficiency feedback.
- **Scaffold-time lints and pre-handoff self-check.** Three lints run automatically (frontmatter validity, tier portability, attribution well-formedness) at scaffold, at every tier change, and again before handoff, followed by a short content checklist (description, kebab-case name, error handling, examples, every cited reference file exists). It may ask you to confirm fixes; the tier only changes on your explicit request.
- **Three portability tiers.** Each skill is `personal`, `claude-users` (default; Claude Code and Cowork) or `model-agnostic`; the tier sets which features and paths are allowed. Stated during intent capture, or asked for at a tier change.
- **Multi-iteration build planning and resume.** For long builds it tracks a plan and task tree; on re-entry in a new session it reads those first to find where it left off. Automatic for multi-iteration builds.
- **Local packaging.** Zips the finished skill into an installable `.skill` file for quick local use (not the release build, which belongs to skill-publisher). Automatic at the end of a build when the `present_files` tool is available, or `python -m scripts.package_skill <path>` from the skill's folder.
- **Handoff to the next phases.** When iteration converges it suggests `/skill-tracer <name>` to find bugs, then `/skill-publisher <name>` to polish and ship.

## Structure

- **`SKILL.md`** — the recipe the skill follows: capturing intent, choosing install/improve/build, scaffolding, testing, iterating, description tuning and packaging; includes worked Examples and a Troubleshooting table.
- **`README.md`**, **`HISTORY.md`**, **`LICENSE.txt`** — this overview, provenance/attribution/changelog, and the license preserved from the upstream skill.
- **`references/`** — background loaded only when a step needs it:
  - what a CCVW skill must contain: `skill-structure-spec.md`, `attribution-spec.md`, `portability-spec.md`, and the `history-template.md`, `readme-template.md`, `glossary-template.md` scaffolds; `ccvw-glossary.md` (shared vocabulary) and `glossary.md` (this skill's own);
  - how to write one well: `skill-writing-style.md`, `build-planning.md`, `mcp-enhancement-skills.md`, `iterate-quality-checks.md`;
  - how to run and upgrade one: `improve-existing-skill.md`, `runtime-adaptations.md` (Claude.ai and Cowork differences), `viewer-ui.md`, `recommendations-template.md`;
  - data shapes: `schemas.md` (JSON formats for evals, grading and benchmark files).
- **`scripts/`** — helpers that give the same result every run:
  - validation and linting: `quick_validate.py`, `portability_lint.py`, `attribution_lint.py`, `validate_eval_set.py`;
  - evals and scoring: `aggregate_benchmark.py`;
  - description tuning: `run_eval.py`, `run_loop.py`, `improve_description.py`, `generate_report.py`;
  - packaging and shared code: `package_skill.py`, `utils.py`.
- **`agents/`** — briefs for helper agents: `grader.md` (checks a run against its expectations), `comparator.md` (blind A-vs-B judgment), `analyzer.md` (explains why a version won, or analyzes a benchmark run).
- **`assets/`** — `eval_review.html`, the page where you review and edit trigger-test queries before optimization.
- **`eval-viewer/`** — `generate_review.py` builds the results viewer (local server, or one static HTML file with `--static`); `viewer.html` is the template it fills in.
- **Where outputs go**: nothing from eval or optimization runs is written inside the skill folder. Outputs go to `${XDG_DATA_HOME:-$HOME/.claude}/skill-creator-evals-ledger/<skill-name>/` — `iteration-N/` (per-test runs, grading, benchmark, feedback, viewer files) and `trigger-opt/` (eval set, log, timestamped `results.json`). The skill's own `evals/evals.json` (its test prompts) lives in the skill folder and is left out of the packaged `.skill`.

## How to install

Already installed locally at `~/.claude/skills/skill-creator-ccvw/`. This is a `claude-users` tier skill (Claude Code + Cowork) — no user-specific paths, only its own portable `${XDG_DATA_HOME:-$HOME/.claude}/skill-creator-evals-ledger/` namespace. Published at [`Vaikri-costume/skills`](https://github.com/Vaikri-costume/skills); to install elsewhere, copy the `skill-creator-ccvw/` directory into a `~/.claude/skills/` folder, or install the packaged `.skill` archive via Claude Code's or Cowork's skill-install flow.

## Sibling skills

- `skill-tracer` — the **trace** phase. Finds correctness bugs + inconsistencies in a built skill via cold-parallel agents. Suggested at iterate-end.
- `skill-publisher` — the **ship** phase. Polishes, runs tier-transition checks, audits CCVW compliance, and PRs to GitHub. Suggested after trace converges.
- `marketplace-discover` — invoked at the start of every new build to check the live catalog.
- `skill-creator` (upstream) — the Anthropic original this is forked from.

## For developers

The runtime workflow lives in [`SKILL.md`](SKILL.md). Provenance and changelog live in [`HISTORY.md`](HISTORY.md). To trace this skill for bugs: `/skill-tracer skill-creator-ccvw`. To ship a new version: `/skill-publisher skill-creator-ccvw`.
