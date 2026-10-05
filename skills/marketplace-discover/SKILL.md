---
name: marketplace-discover
description: "Search the live Claude Code marketplace catalog on disk for existing plugins, skills, hooks and MCP servers that match a described need, and recommend install versus build. Use when the user asks 'is there a plugin that does X', 'what plugins exist for Y', 'show me everything in the marketplace about Z', or 'before I build X, check if it already exists'; skill-creator-ccvw also calls it at its marketplace-check step. Do NOT use to build or improve a skill (use skill-creator-ccvw), for general web search, or to judge a plugin's quality beyond what the catalog says."
license: MIT
compatibility: Claude Code 2.0 or newer
metadata:
  tier: claude-users
  created: 2026-05-29T20:00
  created-by: skill-creator-ccvw
  parent-version: null
  intended-audience: claude-users
allowed-tools:
  - Read
  - Bash
  - Glob
  - Grep
---

# marketplace-discover

## What this skill does

Reads the live Claude Code marketplace catalog and the third-party external_plugins directory, matches user-described needs against plugin/skill descriptions, and presents a ranked "build vs install" recommendation BEFORE the user invests time building from scratch.

Closes the gap left by `claude-automation-recommender` (which reads hardcoded reference files, not the live catalog).

## When to invoke

- Slash command: `/marketplace-discover <described-need>`
- Natural language: "is there a plugin that does X", "what plugins exist for Y", "show me everything in the marketplace about Z", "before I build X, check if it already exists"
- Called by skill-creator-ccvw's marketplace-check step when a skill, hook or plugin is about to be built; it does not start itself otherwise
- When the user explicitly asks "search the marketplace for ..."

---

## Prerequisites

- Read access to `~/.claude/plugins/marketplaces/claude-plugins-official/.claude-plugin/marketplace.json`
- Read access to `~/.claude/plugins/marketplaces/claude-plugins-official/external_plugins/` (each subdirectory contains `.claude-plugin/plugin.json`)
- `Bash` for the optional install execution step

Reading the catalog needs no network. Reading a candidate's own `plugin.json` (Step 4) and the optional install (Step 6) fetch from the candidate's source and so do need a network connection; if it is unavailable, rank from the catalog entry alone and say so.

---

## Workflow

### Step 1. Parse the user's described need

Capture:
- Domain (e.g., "code review", "PR management", "session reporting", "memory")
- Action verbs (e.g., "review", "summarize", "lint", "audit", "search")
- Tool/integration mentions (e.g., "GitHub", "Slack", "Linear")
- Constraints (e.g., "must work offline", "Python only", "no MCP")

Expected output: a short need summary (domain, verbs, tools, constraints).

If the need is too vague (e.g., "a skill for productivity" — productivity means many things), ask the user 1-2 clarifying questions before scanning.

### Step 2. Catalog freshness check

```bash
catalog=~/.claude/plugins/marketplaces/claude-plugins-official/.claude-plugin/marketplace.json
mtime=$(stat -f %m "$catalog" 2>/dev/null || stat -c %Y "$catalog")
now=$(date +%s)
hours=$(( (now - mtime) / 3600 ))
```

If `hours > 24`, surface a warning to the user: "Catalog is N hours old; community plugins ship daily, so this catalog may be missing recent additions. Consider running `claude plugins update` first, then re-invoke this skill."

Expected output: the catalog's age in hours, plus a warning only if over 24.

Proceed with the existing catalog regardless — the warning is informational, not blocking. The threshold is 24 hours because the marketplace receives new entries daily; any longer than that risks recommending build-over-install for something that's now available.

### Step 3. Scan both sources

**Source A — main catalog**: `~/.claude/plugins/marketplaces/claude-plugins-official/.claude-plugin/marketplace.json`
- Schema: `{plugins: [{name, description, author, category, source, homepage}, ...]}`

**Source B — external_plugins**: `~/.claude/plugins/marketplaces/claude-plugins-official/external_plugins/`
- Each subdirectory contains a `.claude-plugin/plugin.json` with the same per-entry schema.

For each entry, extract `name + description + category + author` for the keyword/semantic match in Step 4.

See `references/marketplace-catalog-format.md` for full schema details.

Expected output: the combined entry list (main plus external). If the catalog file is missing or not valid JSON, stop and tell the user to run `claude plugins update`; skip any single external plugin whose `plugin.json` is absent and note it.

### Step 4. Match against user need

Two-pass matching:

**Pass 1 — keyword filter**: case-insensitive substring match of any user-need keyword in the entry's `name + description + category`. Captures a candidate set (usually 5-30 entries).

**Pass 2 — semantic rank**: read each candidate's full description and rank by relevance to the user's actual intent (not just keyword overlap). Top 5 candidates advance.

If Pass 1 yields no candidates, broaden once (synonyms, then the category alone) before reporting no match. For each top-5 candidate, ALSO read its own `.claude-plugin/plugin.json` (the entry's `source.url` points at it) for any extended description / dependency / version info that doesn't fit in the catalog summary. Expected output: up to five ranked candidates, each with a match strength.

### Step 5. Present ranked recommendations

Format per candidate:
```
**<name>** (<category>, by <author>)
<one-line summary of what it does — pulled or paraphrased from description>
Install: claude plugins install <name> --source <source.url>[#<source.ref>]   (for git-subdir sources include `source.path`, per `references/marketplace-catalog-format.md` step 4)
Homepage: <homepage if present>
Match strength: <high|medium|low> — <why this matched>
```

Order: highest match-strength first.

After all candidates: explicit "build vs install" framing:
- "If any of the above matches what you want, I can install it directly (with your confirmation). Otherwise, we proceed with building from scratch."

### Step 6. Optional direct install

If user chooses to install one of the recommendations, run the install command via Bash AFTER explicit user confirmation:

```bash
claude plugins install <name> --source <source.url>[#<source.ref>]   # add source.path for git-subdir sources
```

Report success/failure. If install fails, surface the error and offer to retry or proceed with build.

### Step 7. Record the marketplace check

This skill is read-only and writes no files. When skill-creator-ccvw invoked it, report that the check ran (with the date) so skill-creator-ccvw can record `checked-marketplace:` under `## Lineage notes` in the new skill's HISTORY.md, which is where that record lives. Standalone, nothing is recorded.

---

## Output format

Markdown to the user, structured as:

```
## Marketplace search for: <described need>

[Freshness warning if applicable]

Found N matches in the catalog (M main + K external_plugins):

### Top recommendations

1. **<name>** ... [as Step 5 format]
2. ...
3. ...

[other N-3 candidates listed more briefly]

### Build vs install

[explicit framing]
```

---

## Examples

**Example: before building.** User says: "Is there a plugin for managing GitHub PRs?" → freshness check (catalog 5 hours old, no warning) → keyword filter on "github", "pull request" gives 12 candidates → semantic rank keeps 5 → presents them with install commands and a build-vs-install note. Result: the user installs the top match or decides to build.

**Example: no match.** User says: "Is there a skill that audits my Zotero tags?" → Pass 1 finds nothing, broadens to "reference manager" and "tags" → still nothing → reports no match and recommends building.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| "Catalog not found" | marketplace not installed or moved | Run `claude plugins update`, then re-invoke |
| Warning that the catalog is old | Over 24 hours since last update | Run `claude plugins update`; results still shown |
| Zero candidates | Need described too narrowly | Broaden once, then report no match |
| Install fails | Network down or source unreachable | Surface the error; offer retry or build |

## References

- `references/marketplace-catalog-format.md` — catalog schema documentation
- `references/glossary.md` — skill-specific terms (inherits CCVW shared glossary)

### See also

- `skill-creator-ccvw` — the meta-skill that invokes marketplace-discover at its "Decide: install, improve, or build" step. marketplace-discover is the read-only catalog scanner; skill-creator-ccvw is the orchestrator that consumes the recommendations and routes the user to install / evolve / build.
