# Markdown Graph Manager

## What this skill does

Keeps a dual-format markdown knowledge graph healthy — a Logseq graph whose pages folder is simultaneously an Obsidian vault, where every file must stay valid in both apps at once. It audits the whole graph against a schema config, applies a strictly-limited set of safe fixes, and creates or edits pages with the schema enforced up front instead of cleaned up after.

## Intent

This skill prioritizes **format-contract safety over convenience**. A dual-format graph breaks silently: a YAML block or a `- [ ]` checkbox looks fine in one app and corrupts meaning in the other, and a bracketed link to a nonexistent page quietly creates phantom pages. So every write path is schema-validated by default, the fix subcommand applies only fixes whose safety is mechanically verifiable (everything else stays report-only forever), and bypassing validation requires an explicit passthrough opt-in with a visible banner. Fixes that would trade validation coverage for speed or convenience should be surfaced for human judgment, not applied automatically.

It also prioritizes **portability of the engine over baked-in personalization**: all schema vocabulary, required properties, and tolerance lists live in a swappable JSON config, and the scripts are pure-stdlib Python taking explicit `graph_root` + `schema_config` arguments — so the same skill works for any property-block markdown graph, on any agent runtime, with a different config file.

## When to use / When NOT to use

**Use when:** your graph is a Logseq-format graph (first-block `property::` metadata, outline bullets, keyword tasks) that other apps — Obsidian, Tine, Finalist — also read, and you want auditing, safe cleanup, or schema-enforced page creation/editing.

**Don't use when:** you have an ordinary Obsidian vault with YAML frontmatter and no Logseq compatibility requirement — Obsidian's own tooling or a frontmatter-native linter serves that better. Don't use it for bulk content migration between formats; it validates against one format contract, it doesn't convert between contracts.

**Tested on:** Claude Code with MCP-connected Obsidian and Logseq instances. When no live write API is reachable, the direct-file-write fallback in `references/layers/logseq-obsidian.md` is the path; it is untested against a live app window.

## How to invoke

- Slash command: `/markdown-graph-manager audit` (also `fix`, `fix --assets-only`, `write` (alias `create`), `edit`, `raw`, `list`/`read`/`search`/`list-tags`)
- Natural language: "audit my markdown graph", "check the graph for dangling links", "apply safe fixes to the graph", "add a new person page to my graph", "fix the graph's asset symlinks", "let me make a raw/unvalidated edit to this page", "find my page about X" / "list pages tagged Y"
- Also by phrase: "check for stale verified dates" (the stale-date check runs only on request); on a graph registered without a schema, `audit` narrows to link checks and says so; name an app (Apple Notes, Tine, Finalist) for its layer-specific operations.
- The three judgment-gated cleanup scripts (heading extraction, colon-label fix, property normalize) aren't invoked by phrase — they're run manually by whoever's operating the skill, one at a time, once a report-only finding has been reviewed. See `SKILL.md`'s "Judgment-gated maintenance scripts" for when each applies.

Example:
```
"check my graph schema"
→ resolves the graph root, runs schema-lint + graph-link-audit against the schema config,
→ prints one categorized report: e.g. 49 should-be-linked, 1 dangling-bracketed-link,
  3 missing-required-property — grouped by category, nothing modified.
```

## Features & modes

Every request goes to exactly one mode. The graph is always checked against a registry of live graphs first, so you never need to say which mode runs the safety check.

- **Audit (read-only)**: scans the whole graph and gives you one categorized report of schema, property, format and link problems. It never changes a file. Each finding names the page and line and is marked safe-fix or report-only. Trigger: `audit`, "audit my graph", "check graph schema", "check dangling links", "graph health check". It asks about draft pages before it starts. On a graph registered without a schema it checks links only and says so.
- **Deeper graph checks (part of audit)**: link health (dead-end pages, orphans, hub pages), unlinked mentions, relation verbs in Connections sections, and leftover template placeholders. Each finding is rated error, warn or info, and every fix is proposed with a reason, never applied automatically. Stale `verified::` dates are checked only if you ask. Trigger: runs inside `audit`; ask "check for stale verified dates" for the date check.
- **Safe fixes**: re-audits fresh, shows you a full pre-fix report, waits for your go-ahead, then applies only fixes that are mechanically certain. The schema pass is a dry run first. Everything else stays report-only, each finding with a specific recommendation. Trigger: `fix`, "apply safe fixes", "clean up graph schema".
- **Asset repair**: a separate maintenance action that repairs the assets folder link and asset links in pages. Trigger: `fix --assets-only`, "fix the graph's asset symlinks".
- **Create a page**: builds a new page with the schema enforced as it is written. It fills in the required properties for the page type, asks for values it cannot work out, and checks that the title and aliases are unique. Trigger: `write` or `create`, "add a page to my graph".
- **Edit a page**: applies the same checks to whatever you add or change, then writes through the right app's path. Both create and edit end with a read-back of the page on disk. Trigger: `edit`, "edit this graph page".
- **Raw / passthrough edit**: an explicit opt-in that skips validation and allows anything, including delete, rename and retag. It prints a PASSTHROUGH banner and waits for your confirmation. It is never entered on its own. Trigger: `raw`, or explicitly ask for an unvalidated edit.
- **Read-only lookup**: list, read, search and list tags. It works on any graph and cannot break the format. Where an app cannot do an operation (Apple Notes supports none), the skill says so. Trigger: `list`, `read`, `search`, `list-tags`, "find my page about X", "does this page exist", "list pages tagged Y".
- **Layer-specific operations**: tasks tied to one app, such as generating text for an app with no API, or a manual compatibility check for Apple Notes. An unsupported operation is reported as unsupported, never silently skipped. Trigger: name the app in the request.
- **Knowledge-graph rules**: when you create or restructure pages, the skill proposes and checks, and you write the notes. The rules cover:
  - whether a note is a concept, a topic or a fleeting stub, with three promotion criteria;
  - vocabulary pages written as codebook entries;
  - every Connections link starting with a relation verb from an editable list;
  - a duplicate check across filenames, titles and aliases before any page is created;
  - using only your existing Reading Notes and Reading Report templates.

  The skill never writes notes, relations or definitions for you, and it checks with you first if a page touches assessed work. Trigger: applies automatically on create and edit. Details: `references/graph-rules.md`.
- **Judgment-gated cleanup tools** (run by hand, one at a time, never bundled into safe fixes): turn a bold-labelled bullet into a real heading, convert a pre-approved list of "Label: value" lines to "Label - value", and normalize `type::` values and retired property names. These run only after you have reviewed the related report-only finding.
- **Graph resolution safety**: the graph path is validated against a registry. A retired graph is refused even if you name it, and an unknown path prompts a question instead of a guess. Automatic.
- **Maintenance freshness check**: at most once every 7 days it checks whether the apps that read your graph (Logseq, Obsidian, Tine, Finalist) have newer versions or documentation changes. It only reports or asks, never installs or downloads on its own, and never blocks your request. Automatic.
- **Unattended weekly run**: audit can run as a scheduled routine. It follows a fixed rule for what it may do without you present, which is read-only reporting. Trigger: set up a scheduled audit.

## Structure

- **`SKILL.md`**: the workflow itself. It sets how a request is routed to a mode, the steps of each mode, the graph-rules summary and the report format. Read this first if you want to change behaviour.
- **`references/`**: detail loaded only when needed.
  - Rules and checks: `rules.md` (the shared rules: drafts, bracket rule, safe-fix scope, pre-fix report, exit codes, read-back after a write), `graph-rules.md` (knowledge-graph conventions), `audit-checks.md` (what the deeper checks look for), `glossary.md` (finding names and terms).
  - Upkeep: `maintenance-check.md` (the weekly freshness check and where its timestamp is kept).
  - Per-app layers: `layers/` has one file each for Logseq/Obsidian (primary), Tine, Apple Notes and Finalist, covering what each app supports and how writes reach it. `layer-tine-caveats.md` and `layer-finalist-caveats.md` list what is still unverified; test those apps on a scratch copy first.
- **`scripts/`**: dependency-free Python helpers (standard library only), grouped by job.
  - Finding the graph: `graph-discovery.py`.
  - Auditing, read-only: `schema-lint.py`, `graph-link-audit.py`, `graph_audit.py`.
  - Safe fixes: `schema-pass.py` and `graph-link-audit.py --apply-safe-fixes`, plus `assets-audit.py` for assets.
  - Manual cleanup: `graph-heading-extract.py`, `graph-colon-label-fix.py`, `property-normalize.py`.
  - Shared code: `_common.py`, imported by the other scripts and never run directly.
  - `tests/`: unit tests for the audit and the maintenance scripts. Run `python3 -I -m unittest discover -s scripts/tests` from the skill folder.
- **`assets/`**: the swappable configuration and samples. Copy `example-graphs.json` (the graph registry) and `example-schema.json` (the schema vocabulary, required properties and tolerances) and adapt them for your own graph. `relation-vocabulary.json` holds the relation verbs you edit. `test-registry.json` and `test-schema.json` belong to the test fixture.
- **`evals/`**: `evals.json` (the test prompts) and a small fixture graph they run against. Copy the fixture to a scratch folder before running.
- **Where outputs go**: reports print in the conversation and nothing is saved, except the pre-fix report, which is saved to a scratch file before safe fixes. Page writes land in your graph. Outside the graph, the only persistent file is the maintenance-check timestamp.

## How to install

Version 2.0.0. Install from the public skills repository by copying the folder `skills/markdown-graph-manager/` from `https://github.com/Vaikri-costume/skills` to `~/.claude/skills/markdown-graph-manager/` (or a project's `.claude/skills/`). It needs Python 3 and nothing else. Copy `assets/example-graphs.json` and `assets/example-schema.json` somewhere you keep your own configuration and adapt them to your graph; the skill asks where the registry is on first use.

## Sibling skills

Optional, not required to use or maintain this skill:
- `skill-creator-ccvw`, `skill-tracer`, `skill-publisher`: build, audit and ship.

## For developers

The runtime workflow lives in [`SKILL.md`](SKILL.md). Provenance and changelog
live in [`HISTORY.md`](HISTORY.md). The skill is self-contained — scripts are pure-stdlib
Python invoked as `scripts/<name>.py GRAPH_ROOT SCHEMA_CONFIG`, and no companion skill
is required to use or maintain it. (If you have the CCVW toolchain installed, skill-tracer
and skill-publisher work on it like any other CCVW skill — optional, never required.)
