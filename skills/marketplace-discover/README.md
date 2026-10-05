# marketplace-discover

## What this skill does

Before you build a skill, hook or plugin, it searches the live Claude Code marketplace catalog and the third-party `external_plugins/` directory for something that already does the job. It ranks the best matches against your described need and recommends build versus install, with an optional install step.

## Intent

The aim is to avoid rebuilding what already exists. It reads the live catalog on disk, not a hardcoded list, so recommendations reflect what is actually installable today. It recommends; it never installs without being told to.

## When to use

- You ask "is there a plugin that does X" or "what exists for Y".
- You are about to build a skill, hook or plugin and want to check the catalog first.
- You want everything in the marketplace on a topic.

**Don't use** for general web search or for judging plugin quality beyond what the catalog describes.

## How to invoke

- `/marketplace-discover <described need>`
- Natural language: "check the marketplace for X before I build it".

## Features & modes

- **Catalog search.** Matches your described need against the main marketplace catalog and the third-party `external_plugins/`, then ranks the top five.
- **Build versus install.** Ends every search with an explicit recommendation, and offers to install a match after you confirm.
- **Freshness check.** Warns when the local catalog is more than 24 hours old.
- **Called by skill-creator-ccvw.** Runs read-only at its marketplace-check step; the result is recorded in the new skill's HISTORY.md by skill-creator-ccvw.

## Structure

- `SKILL.md`: the seven-step workflow, examples and troubleshooting.
- `references/marketplace-catalog-format.md`: the catalog schema and the install-command rule.
- `references/glossary.md`: skill-specific terms.
- `HISTORY.md`, `LICENSE`: provenance and MIT licence.

## How to install

```
claude plugins install Vaikri-costume/skills
```

Or copy the `marketplace-discover/` folder into `~/.claude/skills/`.

## Sibling skills

- `skill-creator-ccvw`: builds skills and calls this one first.
