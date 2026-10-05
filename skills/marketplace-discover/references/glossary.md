# Glossary — marketplace-discover

See also: [`~/.claude/skills/skill-creator-ccvw/references/ccvw-glossary.md`](../../skill-creator-ccvw/references/ccvw-glossary.md) for all CCVW shared terms (cluster, FIX, STRENGTHEN, in-flight marker, Round, Phase, ledger, cold-trace, tier, etc.). This file lists ONLY terms specific to marketplace-discover.

## Skill-specific terms

| Term | Definition |
|---|---|
| **build-vs-install signal** | The recommendation marketplace-discover surfaces when a top-ranked candidate is a strong-enough match that the user should consider installing rather than building. Surfaced as explicit text the user must respond to before any build proceeds. |
| **candidate set** | The plugins/skills/hooks/MCP servers that pass the Step 4 keyword filter against the user's described need. Typically 5-30 entries before the semantic rank narrows to top 5. |
| **catalog freshness signal** | A warning surfaced when `marketplace.json`'s file mtime is more than 24 hours old, suggesting the user run `claude plugins update` before relying on the search results. Informational only — does not block the search. |
| **external_plugins** | Third-party plugins under `~/.claude/plugins/marketplaces/claude-plugins-official/external_plugins/`, each in its own subdirectory with a `.claude-plugin/plugin.json` file. Distinct from the main `marketplace.json` catalog; marketplace-discover scans both. |
| **install command** | The `claude plugins install <name> --source <source.url>[#<source.ref>]` invocation marketplace-discover constructs from a candidate's `source` field. Offered to the user; runs only after explicit user confirmation. |
| **main catalog** | `~/.claude/plugins/marketplaces/claude-plugins-official/.claude-plugin/marketplace.json` — the primary plugin index. |
| **match strength** | Per-candidate `high` / `medium` / `low` ranking emitted by Step 4's semantic pass. Drives the order recommendations are presented and whether the build-vs-install signal fires. |
| **pre-eval marketplace check** | The step skill-creator-ccvw runs at its "Decide: install, improve, or build" step — invokes marketplace-discover with the user's described need before any draft work begins. skill-creator-ccvw records the date as a `checked-marketplace:` line under `## Lineage notes` in the new skill's HISTORY.md so re-triggers don't re-ask. |
