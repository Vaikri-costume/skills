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

## Features & modes

- **Build a new skill from scratch (Path 3)** — walks the full create loop: intent interview → marketplace check → attribution + author capture → scaffolds the mandatory CCVW structure (SKILL.md, README.md, HISTORY.md, scripts/references/assets, glossary) → draft → eval → iterate. Trigger: "I want a skill that does X" / "create a skill for X", or when the marketplace check finds no strong existing match.
- **Install an existing skill instead of building (Path 1)** — before any new build, it checks the live marketplace catalog for a skill that already does what you want; if there's a strong match you can install it directly and skip building entirely. Trigger: automatic first step of any new-skill request — no separate phrase needed, but you can also just ask "is there already a skill for X?".
- **Improve/evolve an existing installed skill (Path 2)** — hands off to a dedicated improve-existing-skill workflow (fork/attribution-aware) rather than the from-scratch scaffold. Trigger: "improve my skill Y", "evolve X to also do Y", or choosing to build on a weak/near marketplace match.
- **Run evals and iterate on feedback** — for each test prompt, runs the skill and a same-turn baseline (no-skill, or the pre-edit version) side by side, grades both, aggregates a pass-rate/time/token benchmark, and opens a browser viewer (Outputs + Benchmark tabs) for you to leave feedback per run; repeats until you're satisfied. Trigger: happens automatically once a draft exists — "test this", "run the evals", or just continuing past drafting.
- **Static/headless viewer mode** — for environments without a persistent local server (e.g. Cowork), writes a single self-contained `review.html` file instead of starting a server. Trigger: automatic on non-Claude-Code runtimes; otherwise available via the `--static <path>` flag on the viewer script.
- **Description-tuning / trigger-accuracy optimization** — builds a set of "should this skill fire" test queries, lets you review/edit them in a small HTML picker, then runs a background loop (up to 5 rounds) that tries to improve the skill's description so it triggers on the right prompts and stays quiet on near-misses. Trigger: offered automatically after a skill is created/improved, or ask "make this trigger better" / "optimize the description".
- **Blind A/B comparison between two skill versions** — an independent judge agent compares two outputs without knowing which skill produced which, then a follow-up pass explains why the winner won. More rigorous than the standard eval loop; optional and not needed for most builds. Trigger: "is the new version actually better than the old one?" or explicitly asking for a blind comparison.
- **Iterate-quality checks (opt-in, off by default)** — extra efficiency and readability advisories (wasted work, jargon, dense text) surfaced during iteration, separate from correctness grading. Trigger: add `--with-iterate-quality` to the invocation, or just ask for readability/efficiency feedback as you iterate.
- **Package the finished skill locally** — zips the skill into an installable `.skill` file for quick local use (not the polished release build — that's skill-publisher's job). Trigger: happens automatically at the end of a build if the packaging tool is available, or run it yourself as described in "How to invoke" once a skill is done.
- **Portability/attribution self-check before handoff** — runs three built-in lints (structure/frontmatter validity, tier-portability rules, attribution well-formedness) at scaffold time, at every tier change, and again before suggesting the next phase — not something you invoke separately, but worth knowing it happens automatically and may prompt you to confirm fixes.

## Structure

- **`SKILL.md`** — the step-by-step recipe this skill follows: capture intent → decide install/improve/build → scaffold → draft → eval/iterate → optimize description → package. Everything else in the skill exists to support one of these steps.
- **`references/`** — background material pulled in only when a given step needs it, not read all at once. Roughly four groups: (1) *what a CCVW skill must contain* — `skill-structure-spec.md`, `attribution-spec.md`, `portability-spec.md`, `history-template.md`, `readme-template.md`, `glossary-template.md`, `ccvw-glossary.md`/`glossary.md`; (2) *how to write one well* — `skill-writing-style.md`, `build-planning.md`, `mcp-enhancement-skills.md`, `iterate-quality-checks.md`; (3) *how to run/upgrade one* — `improve-existing-skill.md`, `runtime-adaptations.md` (Claude.ai/Cowork differences), `viewer-ui.md`; (4) *data shapes* — `schemas.md` (the JSON formats for evals, grading, and benchmark files).
- **`scripts/`** — deterministic helpers so the workflow doesn't rely on hand-written commands each time: validation/linting (`quick_validate.py`, `portability_lint.py`, `attribution_lint.py`, `validate_eval_set.py`), running and scoring tests (`run_eval.py` for description-trigger testing, `run_loop.py` for the description-optimization loop, `aggregate_benchmark.py` for turning graded runs into pass-rate/time/token stats, `generate_report.py` for the optimization loop's own live progress page), a few one-off utilities (`improve_description.py`, `package_skill.py` for zipping a finished skill, `utils.py` for shared helpers).
- **`agents/`** — instruction briefs for the subagents this skill dispatches: `grader.md` (checks a run's output against the test's expectations), `comparator.md` (blind A-vs-B judgment for the comparison mode), `analyzer.md` (explains why one version did better, used both after a blind comparison and after a normal benchmark run).
- **`eval-viewer/`** — the browser-based results viewer: `generate_review.py` builds it (either as a live local server or, in `--static` mode, a single self-contained HTML file) and `viewer.html` is the page template it fills in with each run's outputs, scores, and your feedback form.
- **Where outputs go**: nothing from a build or eval run is written inside the skill's own folder. It all goes to a centralized location outside `~/.claude/skills/` — `${XDG_DATA_HOME:-$HOME/.claude}/skill-creator-evals-ledger/<skill-name>/` — organized by iteration (`iteration-1/`, `iteration-2/`, …), each holding the per-test-case runs, grading, benchmark, and viewer files. The one exception is `evals.json` itself (the list of test prompts/checks), which lives with the skill's own source under `<skill-path>/evals/`.

## How to install

Already installed locally at `~/.claude/skills/skill-creator-ccvw/`. This is a `claude-users` tier skill (Claude Code + Cowork) — no user-specific paths, only its own portable `~/.claude/skill-creator-evals-ledger/` namespace. Published at [`Vaikri-costume/skills`](https://github.com/Vaikri-costume/skills); to install elsewhere, copy the `skill-creator-ccvw/` directory into a `~/.claude/skills/` folder, or install the packaged `.skill` archive via Claude Code's or Cowork's skill-install flow.

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

## Sibling skills

- `skill-tracer` — the **trace** phase. Finds correctness bugs + inconsistencies in a built skill via cold-parallel agents. Suggested at iterate-end.
- `skill-publisher` — the **ship** phase. Polishes, runs tier-transition checks, audits CCVW compliance, and PRs to GitHub. Suggested after trace converges.
- `marketplace-discover` — invoked at the start of every new build to check the live catalog.
- `skill-creator` (upstream) — the Anthropic original this is forked from.

## For developers

The runtime workflow lives in [`SKILL.md`](SKILL.md). Provenance and changelog live in [`HISTORY.md`](HISTORY.md). To trace this skill for bugs: `/skill-tracer skill-creator-ccvw`. To ship a new version: `/skill-publisher skill-creator-ccvw`.
