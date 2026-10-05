# Marketplace Catalog Format Reference

Schema for the Claude Code marketplace catalog files that `marketplace-discover` reads. This document is a reading reference — `marketplace-discover` consults it so it doesn't need to re-derive the format from raw catalog data each invocation.

## Source files

Two distinct catalog locations, both read by `marketplace-discover`:

### 1. Main catalog
`~/.claude/plugins/marketplaces/claude-plugins-official/.claude-plugin/marketplace.json`

A single JSON file with the structure:
```json
{
  "$schema": "https://anthropic.com/claude-code/marketplace.schema.json",
  "name": "claude-plugins-official",
  "description": "Directory of popular Claude Code extensions ...",
  "owner": { "name": "Anthropic", "email": "support@anthropic.com" },
  "plugins": [
    { ...plugin entry... },
    { ...plugin entry... }
  ]
}
```

Typically ~326 entries in `plugins[]`.

### 2. External plugins directory
`~/.claude/plugins/marketplaces/claude-plugins-official/external_plugins/`

A directory containing subdirectories — one per third-party plugin. Each subdirectory has a `.claude-plugin/plugin.json` file. Typically ~15+ entries.

To enumerate: `ls ~/.claude/plugins/marketplaces/claude-plugins-official/external_plugins/` lists the plugin subdirs; for each, read `<subdir>/.claude-plugin/plugin.json` to extract the entry.

## Per-entry schema

Both sources use the same per-entry schema. Fields:

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | string | yes | Plugin identifier; used in install commands. Globally unique within the catalog. |
| `description` | string | yes | One-paragraph human-readable description of what the plugin does, who built it for, and when to use it. This is the field `marketplace-discover` keyword-matches against. |
| `author` | object | yes | `{name: "...", email?: "..."}` — the plugin's author or maintaining org. |
| `category` | string | recommended | One of: `development`, `productivity`, `security`, `design`, `infrastructure`, `data`, `communication`, etc. Used for filtering. |
| `source` | object | yes | Where the plugin is installed from. Schema: `{source: "git-subdir" \| "git-repo" \| "local", url: "...", path?: "...", ref?: "...", sha?: "..."}`. Combined with `name`, this builds the install command. |
| `homepage` | string | optional | URL to plugin's docs / GitHub / project page. Useful for "tell me more before I install" follow-ups. |

Example main-catalog entry:
```json
{
  "name": "42crunch-api-security-testing",
  "description": "Automate API security directly in Claude Code with 42Crunch ...",
  "author": { "name": "42Crunch" },
  "category": "security",
  "source": {
    "source": "git-subdir",
    "url": "https://github.com/42Crunch-AI/claude-plugins.git",
    "path": "plugins/api-security-testing",
    "ref": "v1.5.5",
    "sha": "5c8074d846b852c21da23bbf6effbfdabb18ba2d"
  },
  "homepage": "https://42crunch.com"
}
```

## How marketplace-discover uses this

1. **Load**: read main `marketplace.json` once, parse the `plugins` array. Then enumerate `external_plugins/` and load each `plugin.json` to extend the candidate set.
2. **Keyword filter**: substring-match user keywords against `name + description + category` (case-insensitive). Captures the candidate set (5-30 entries typical).
3. **Semantic rank**: read each candidate's full `description`, rank by relevance to the user's intent. Top 5 advance.
4. **Build install command**: from `source.source` + `source.url` + `source.path` + `source.ref`, construct the `claude plugins install` invocation.

## Build-vs-install signal

If a top-5 candidate has `match strength = high` AND the user's described need fits the candidate's `description` cleanly (no major gap), `marketplace-discover` flags it as "consider installing rather than building." The user always makes the final call.
