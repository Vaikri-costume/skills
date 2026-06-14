# skill-publisher

## What this skill does

Takes a finished, traced skill and makes it release-ready, then distributes it. It polishes the prose (a mandatory simplify pass on SKILL.md + README.md), audits CCVW compliance, runs the tier-transition checks that match the skill's intended audience (portability, attribution, security, and Cowork-compatibility), writes the user-facing README sections that teach others how to install and use the skill, bumps the version and appends a changelog entry, packages the skill for distribution, and — when the skill has a GitHub/marketplace origin — opens a pull request.

It's the **ship** phase of a three-skill ecosystem: **build** (skill-creator-ccvw) → **trace** (skill-tracer) → **ship** (this skill).

## Intent

This skill prioritizes **release-readiness and teachability** over speed. It runs the full quality gate (polish + CCVW audit + tier checks + security) every ship, even for a small update, because a skill shared with others carries a higher correctness-and-clarity bar than one used privately — and the cost of shipping a broken or confusing skill to friends/family/coworkers is higher than the cost of the checks.

It deliberately **separates polish from bug-finding**: skill-tracer owns correctness (does the skill have bugs?), skill-publisher owns release quality (is it clean, compliant, installable, teachable?). The simplify pass and the CCVW Word/Spirit audit live here, not in the tracer, because they're ship-time concerns — applying them mid-build or mid-trace would add prose the tracer then has to re-examine.

It is **resilient to missing provenance**: a skill without HISTORY.md still ships (degraded mode — local package, no version bump, no PR), because the user shouldn't be blocked from sharing a hand-built skill just because it lacks a lineage file. But it prompts to backfill, because provenance makes the next ship smoother.

## When to use / When NOT to use

**Use when:**
- A skill has been built + traced and you want to share/distribute it
- You want to polish a skill's prose for release-quality clarity
- You want to PR a skill back to a marketplace/GitHub repo it came from
- You want to bump a skill's version + changelog and package it

**Don't use when:**
- The skill still has bugs → run `/skill-tracer` first
- You're still building/iterating → use `/skill-creator-ccvw`
- The skill is `personal` tier and you just want to use it locally (publisher's checks are for shared skills; personal skills skip most of them)

## How to install

Already installed locally at `~/.claude/skills/skill-publisher/`. This is a personal-tier meta-skill (the publisher itself); not currently published to a marketplace.

## How to invoke

- Slash command: `/skill-publisher <skill-name>` or natural language
- Natural language: "ship skill X", "publish X", "release X", "make a PR for X", "package X for the marketplace"

Example:
```
"/skill-publisher my-pdf-summarizer"
→ polish (simplify SKILL.md + README) → CCVW audit → tier checks (claude-users: portability + Cowork + attribution + security)
→ address findings → fill README install + sibling sections → bump version + changelog → package .skill → (PR if upstream) → present
```

## Sibling skills

- `skill-creator-ccvw` — the **build** phase. Scaffolds the SKILL.md + README.md + HISTORY.md structure the publisher reads.
- `skill-tracer` — the **trace** phase. Finds correctness bugs before ship. Run it before publishing.
- `marketplace-discover` — searches the catalog the publisher can PR a skill back to.
- `simplify` — invoked at Step 2 for the polish pass.

## For developers

The runtime workflow lives in [`SKILL.md`](SKILL.md). Provenance and changelog live in [`HISTORY.md`](HISTORY.md). To trace this skill for bugs: `/skill-tracer skill-publisher`.
