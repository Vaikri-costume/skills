# Markdown Graph Manager

## What this skill does

Keeps a dual-format markdown knowledge graph healthy — a Logseq graph whose pages folder is simultaneously an Obsidian vault, where every file must stay valid in both apps at once. It audits the whole graph against a schema config, applies a strictly-limited set of safe fixes, and creates or edits pages with the schema enforced up front instead of cleaned up after.

## Intent

This skill prioritizes **format-contract safety over convenience**. A dual-format graph breaks silently: a YAML block or a `- [ ]` checkbox looks fine in one app and corrupts meaning in the other, and a bracketed link to a nonexistent page quietly creates phantom pages. So every write path is schema-validated by default, the fix subcommand applies only fixes whose safety is mechanically verifiable (everything else stays report-only forever), and bypassing validation requires an explicit passthrough opt-in with a visible banner. Fixes that would trade validation coverage for speed or convenience should be surfaced for human judgment, not applied automatically.

It also prioritizes **portability of the engine over baked-in personalization**: all schema vocabulary, required properties, and tolerance lists live in a swappable JSON config, and the scripts are pure-stdlib Python taking explicit `graph_root` + `schema_config` arguments — so the same skill works for any property-block markdown graph, on any agent runtime, with a different config file.

## When to use / When NOT to use

**Use when:** your graph is a Logseq-format graph (first-block `property::` metadata, outline bullets, keyword tasks) that other apps — Obsidian, Tine, Finalist — also read, and you want auditing, safe cleanup, or schema-enforced page creation/editing.

**Don't use when:** you have an ordinary Obsidian vault with YAML frontmatter and no Logseq compatibility requirement — Obsidian's own tooling or a frontmatter-native linter serves that better. Don't use it for bulk content migration between formats; it validates against one format contract, it doesn't convert between contracts.

**Cross-runtime testing status:** the skill body is pure-stdlib Python + agentskills.io-spec markdown (no Claude-Code-only constructs), but live round-trip testing to date has only been done on Claude Code with MCP-connected Obsidian and Logseq instances. It has not yet been run against Gemini CLI, Cursor, or OpenCode — the `references/layers/logseq-obsidian.md` fallback (direct file write when no live write API is reachable) is the expected path there, untested in practice.

## How to invoke

- Slash command: `/markdown-graph-manager audit` (also `fix`, `fix --assets-only`, `write`, `edit`, `raw`, `list`/`read`/`search`/`list-tags`)
- Natural language: "audit my markdown graph", "check the graph for dangling links", "apply safe fixes to the graph", "add a new person page to my graph", "fix the graph's asset symlinks", "let me make a raw/unvalidated edit to this page", "find my page about X" / "list pages tagged Y"
- The three judgment-gated cleanup scripts (heading extraction, colon-label fix, property normalize) aren't invoked by phrase — they're run manually by whoever's operating the skill, one at a time, once a report-only finding has been reviewed. See `SKILL.md`'s "Judgment-gated maintenance scripts" for when each applies.

Example:
```
"check my graph schema"
→ resolves the graph root, runs schema-lint + graph-link-audit against the schema config,
→ prints one categorized report: e.g. 49 should-be-linked, 1 dangling-bracketed-link,
  3 missing-required-property — grouped by category, nothing modified.
```

## Features & modes

- **Audit (read-only)** — scans the whole graph and reports every schema, property and link problem in one categorized list; never changes a file. Trigger: `audit`, "audit my graph", "check graph schema", "check dangling links", "graph health check". With a declared schema it runs both the property/vocabulary linter and the link auditor; on a plain vault with no schema it narrows to link-checking only and says so, since format-contract rules would give false positives there.
- **Safe fixes** — re-audits fresh, then writes only fixes that are mechanically certain: wrapping a link in `[[brackets]]` once the target page is confirmed to exist, unwrapping a bracketed link whose target doesn't exist, deleting a property line with no value, stripping stray `**bold**`, and known canonical vocabulary mappings. Everything else stays report-only, each with a specific recommendation. Before applying, it shows the full pre-fix report and saves a copy to a scratch file, because stripping bold erases the evidence of bold-labeled bullets that should be headings. The schema pass runs as a dry run first. Trigger: `fix`, "apply safe fixes", "clean up graph schema".
- **Asset repair** — a separate maintenance action: checks the assets folder is correctly symlinked into the pages folder and repairs asset links in journal pages. Trigger: `fix --assets-only`, "fix assets".
- **Create a new page** — builds a page with the schema enforced as it's written: prefills the type's required properties (asking for values it can't derive), brackets links only to pages that exist (so no phantom pages), checks the title/filename/aliases are unique graph-wide, and follows the graph's format rules (no bold, no single-colon pseudo-labels, real headings, keyword tasks). Refuses on a graph with no schema unless you accept passthrough-equivalent behavior. Trigger: `write` / `create`, "add a page to my graph".
- **Edit an existing page** — runs the same checks on whatever you add or change, then writes through the right app's preferred path. Trigger: `edit`, "edit this graph page".
- **Raw / passthrough edits** — an explicit opt-in mode that skips schema checking and allows anything (delete, rename, retag, arbitrary edits). Prints a `PASSTHROUGH` warning banner and waits for confirmation; never entered by inference. Trigger: `raw`, or explicitly ask for raw / unvalidated editing.
- **Read-only lookup** — list, read, search and list tags; always available on any graph and can't break the format contract. Trigger: `list` / `read` / `search`, "find my page on X", "list pages tagged Y".
- **Graph resolution safety** — before any operation the graph path is checked against a registry of live and retired graphs; a retired graph is refused even when named explicitly, and an unknown path prompts a question instead of a guess. Automatic.
- **Per-app layers** — each app that reads these files has its own write-up of what it supports (Logseq/Obsidian full write support; Tine filesystem only; Apple Notes a manual read-compatibility check only; Finalist). An unsupported operation is reported as unsupported, never silently skipped. Automatic.
- **Judgment-gated cleanup tools** (run manually, one at a time, never bundled into "apply safe fixes"):
  - turning a bold-labeled bullet into a proper heading structure, where it's a genuine heading rather than ordinary text that merely looks like one;
  - converting a specific, pre-approved list of "Label: value" lines into "Label - value" (never a blanket find-replace, since that shape also occurs in quotes and citations);
  - Title-Casing property values and merging old duplicate property names into the current ones — an occasional tidy-up pass.
- **Maintenance freshness check** — runs quietly at most once every 7 days before any of the above: checks whether the apps that read this graph (Logseq, Obsidian, Tine, Finalist) have newer versions or documentation changes worth knowing about. It only reports or asks; it never downloads or installs anything, and never blocks your request.

## Structure

- **`SKILL.md`** — the main instructions: which mode to use for a request, the steps for each, and the rules that always apply (never guess the graph location, never enter passthrough by inference, always give a recommendation for report-only findings).
- **`references/`** — background material loaded as needed:
  - `glossary.md` (audit/graph vocabulary) and `maintenance-check.md` (the weekly freshness check and where its timestamp is stored);
  - `layers/` — one write-up per app that touches these files (Logseq/Obsidian, Tine, Apple Notes, Finalist): what each can do and how writes reach it;
  - `layer-tine-caveats.md` and `layer-finalist-caveats.md` — what is still unverified for those two apps; test on a throwaway copy before trusting them on a real graph.
- **`scripts/`** — dependency-free Python programs taking an explicit graph root and, where relevant, a schema config: `graph-discovery.py` (resolve the graph); `schema-lint.py` and `graph-link-audit.py` (audit engines); `graph-link-audit.py --apply-safe-fixes` and `schema-pass.py` (automatic safe-fix engines); `assets-audit.py` (assets symlink repair); `graph-heading-extract.py`, `graph-colon-label-fix.py`, `property-normalize.py` (manually-run cleanup tools).
- **`assets/`** — the two swappable JSON files that make the skill reusable: a schema config (vocabulary, required properties, tolerances) and a graph registry (which graph roots are live or retired, and which schema each uses). `example-graphs.json` and `example-schema.json` are shipped samples to copy and adapt.
- **Outputs**: reports print in the conversation; the one exception is the pre-fix report, saved to a scratch file such as `${TMPDIR:-/tmp}/mgm-prefix-report.md` before safe fixes. Outside your graph, the only persistent file written is the maintenance-check timestamp, kept in per-skill runtime storage (Claude-Code fallback: `${XDG_DATA_HOME:-$HOME/.claude}/markdown-graph-manager/maintenance-state.json`).

## How to install

No package registry entry exists for this skill yet — install manually (source: `skills/markdown-graph-manager` in https://github.com/Vaikri-costume/skills, once the ship PR is merged):

- **Claude Code**: copy this folder to `~/.claude/skills/markdown-graph-manager/`, or unzip the packaged `.skill` archive there.
- **Other agentskills.io@1.0 runtimes** (Gemini CLI, Cursor, OpenCode, etc.): the skill is spec-conformant (`compatibility: agentskills.io@1.0`, no Claude-Code-only frontmatter extensions), but install commands are runtime-specific and this skill has not yet been verified running on any of them (see "Cross-runtime testing status" above) — follow your runtime's own skill-install instructions for a local `.skill` package or raw skill folder, and treat the first run as a test.

## Sibling skills

Optional, not required to use or maintain this skill:
- **skill-tracer** — finds bugs/regressions in this skill's own instructions via cold-parallel audit.
- **skill-publisher** — polishes, versions, packages, and ships this skill (this is how it was published).

## For developers

The runtime workflow lives in [`SKILL.md`](SKILL.md). Provenance and changelog
live in [`HISTORY.md`](HISTORY.md). The skill is self-contained — scripts are pure-stdlib
Python invoked as `scripts/<name>.py GRAPH_ROOT SCHEMA_CONFIG`, and no companion skill
is required to use or maintain it. (If you have the CCVW toolchain installed, skill-tracer
and skill-publisher work on it like any other CCVW skill — optional, never required.)
