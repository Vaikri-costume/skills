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

## How to install

Already installed locally at `~/.claude/skills/skill-creator-ccvw/`. This is a personal-tier meta-skill (the builder itself); it's not currently published to a marketplace.

## How to invoke

- Slash command: `/skill-creator-ccvw` or natural language
- Natural language: "create a skill for X", "improve my skill Y", "evaluate skill Z", "fork this skill"

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
