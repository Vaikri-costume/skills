---
name: markdown-graph-manager
description: "Manage a dual-format Logseq/Obsidian property-block graph: schema-validated page writes and edits, a read-only audit (schema, links, relations, placeholders), safe fixes, and the rules that turn reading notes into linked knowledge (concept vs topic, codebook vocabulary pages, relation-carrying links, duplicate check). Use for pages, audits, dangling links and 'does this page exist' in a registered property-block graph. Not for plain YAML vaults, Zotero library work, or writing the user's notes for them."
license: MIT
compatibility: Claude Code 2.0 or newer; Python 3 (standard library only); Logseq and Obsidian MCP servers optional
metadata:
  tier: claude-users
  created: 2026-08-11T13:44
  created-by: skill-creator-ccvw
  parent-version: "1.3.0"
  intended-audience: claude-users
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
  - Grep
  - Glob
---

<!-- Provenance, version, attribution chain, and changelog live in HISTORY.md (not this frontmatter).
     Human-facing intent + how-to-install + sibling skills live in README.md.
     This frontmatter holds only the runtime contract the executor agent loads at startup. -->

# Markdown Graph Manager

Manages a markdown knowledge graph that must stay valid in two apps at once — a Logseq graph whose pages folder is simultaneously an Obsidian vault — and stays aware of other markdown apps reading the same files. The format contract (outline bullets, first-block `property:: value` metadata, no YAML frontmatter, keyword tasks, bare wikilinks) is fixed in the scripts and the layer docs; all schema vocabulary lives in external JSON configs under `assets/`, not in this skill: the **schema config** (vocabulary, required properties, canonicalization, tolerance lists) and the **graph registry** (which graph roots are live, which are dead, which schema each uses). Swap those two files (and `assets/relation-vocabulary.json`, the relation verbs the user edits) to run this skill on a different graph. Terms used below are defined in `references/glossary.md`.

## Step -1: maintenance freshness check (before every subcommand, once Step 0 has resolved the graph; not on Step 0's refusal paths)

Read the state file (location: `references/maintenance-check.md`). If its timestamp is under 7 days old, proceed silently. If the file or its timestamp is missing, treat it as never checked. Otherwise run that file's two checks (app-version gaps against the `app_watchlist` key of the graph registry that Step 0 resolved, which degrades to a "check manually" note when the registry has no such key; documentation-currency diff), present one compact notice, update the timestamp, and continue to the requested subcommand. Expected: silence when fresh, otherwise one short notice. The check reads release and documentation pages but **never downloads or installs anything on its own initiative**: a version gap is reported as a question to the user, and only the user installs or explicitly confirms a download command. If a source has no clean API, degrade to a "check manually" note — never fail the actual subcommand over a maintenance check.

## Step 0: resolve the graph

Never operate on a hardcoded or guessed path. The `scripts/` and `assets/` paths in the commands below are relative to this skill's folder. `<registry>` is the path of the graph registry JSON (a copy of the shipped sample, kept wherever the user keeps it, e.g. `assets/.private/`; if the request does not name it, ask the user where it is) and `SCHEMA_CONFIG` the path of the schema config file named by the resolved entry's `schema_config` value (the registry stores a bare filename, read as a file in the same folder as the registry; the shipped sample entry names `example-schema.json`, which sits next to it in `assets/`). `assets/example-graphs.json` and `assets/example-schema.json` are shipped samples showing the shape — copy and adapt them for a real graph:

```bash
python3 scripts/graph-discovery.py <registry> --list          # what graphs exist
python3 scripts/graph-discovery.py <registry> --resolve PATH  # validate a candidate
```

Expected: `--list` prints JSON listing every registry graph with its `dead`/`ok` flags; `--resolve` prints a JSON status for the path (exit 0 when it matches a live graph, otherwise one of the statuses below).

- `rejected-dead` (exit 1, a JSON status; a Python traceback with exit 1 means the registry file itself is unreadable, which is not a dead graph): refuse, full stop — a dead graph root is rejected even when the user passes it explicitly; tell them why.
- `unknown` (exit 2 with a JSON status on stdout; a usage error also exits 2 but prints no JSON): don't guess. Ask the user, and treat the gap as "the registry needs updating," not as license to proceed.
- `registered-but-invalid` (exit 3; `--list` also exits 3 when any entry is not ok, so read the entry of the wanted graph and proceed if that one is ok): the graph is registered but its root or pages folder is missing or dead. Report which and ask the user to fix the registry; do not operate on it.
- Ambiguous which live graph is meant: ask.
- The resolved entry tells you `root_resolved` (the registry's `root` with `~` expanded: this is the `GRAPH_ROOT` every command below takes), `pages_dir` (`.` for a flat vault) and `schema_config` (null = no declared schema — see subcommand notes below).

## Subcommands

Route the user's request to exactly one of these. Mode is never inferred silently: schema-validated is the default for anything that reads like "add/edit a note"; passthrough only on explicit request.

**A. `audit`** — "audit/lint my graph", "check graph schema", "check dangling links", "graph health check". Read-only: it never writes to the graph (only Step -1 may update its own state file).
1. Resolve graph (Step 0). Ask about draft pages before running any script (rule: Drafts, `references/rules.md`).
2. With a schema: run both scripts and merge into ONE categorized report (grouped by category, never by originating script):
   ```bash
   python3 scripts/schema-lint.py GRAPH_ROOT SCHEMA_CONFIG [--pages-dir DIR] --quiet
   python3 scripts/graph-link-audit.py GRAPH_ROOT SCHEMA_CONFIG [--pages-dir DIR]
   ```
   Pass the resolved entry's `pages_dir` as `--pages-dir DIR` to both. Read the exit codes by the rule Exit codes (`references/rules.md`). Expected: `schema-lint.py` prints one line per finding; `graph-link-audit.py` prints findings by category with counts.
3. Without a schema (`schema_config: null`): run ONLY `graph-link-audit.py GRAPH_ROOT assets/example-schema.json --pages-dir DIR --links-only` and say so plainly. The script requires a schema file, but `--links-only` uses none of its rules, so the shipped sample stands in (keep `assets/example-schema.json` valid JSON); `--links-only` still applies the location-independent dangling-bracket rule. Skip schema-lint entirely: format-contract checks (YAML, headings, title uniqueness, property rules, bold-markdown) would be false positives on a plain vault. This route is for a graph the user registered as schema-less; an unregistered plain YAML vault stays out of scope, as the description says. This route cannot leave pages out, so the Drafts question does not arise.
4. With a schema, also run the read-only graph checks and fold them into the same report; a defect that two scripts both report is listed once (rule: Equivalent codes across scripts, `references/rules.md`). Read `references/audit-checks.md` first. This script reads the same graph and uses none of the other scripts' output, so run it in the same batch as the two step 2 scripts:
   ```bash
   python3 scripts/graph_audit.py PAGES_DIR --schema SCHEMA_CONFIG --relations assets/relation-vocabulary.json [--exclude "NAME,NAME"]
   ```
   `PAGES_DIR` is the resolved entry's `pages_resolved` value (the absolute pages folder). It covers properties, format, links (dead-end, orphans, hubs), unlinked mentions, relation verbs and leftover placeholders, and names page and line for every finding (`error`, `warn` or `info`). It has no fix mode: each fix is proposed with the reason, and is applied later as an edit (the `edit` subcommand) only after the user's yes for that one finding. Exit codes: rule Exit codes. Drafts: rule Drafts. Stale `verified::` dates are not in the default run; on request only, run `--checks stale` by itself.
5. Report and stop (rule: Pre-fix report, for `inline-bold-heading` next to `bold-markdown`). Expected: one report grouped by category with counts, and nothing in the graph changed. Categories and which are safe-fixable: `graph-link-audit.py` prints category names; `schema-lint.py` prints free-text lines: give each the glossary term from `references/glossary.md` where one exists (the "bold-heading-plus-dash" line is `inline-bold-heading`, a "missing required property" line is `missing-required-property`) and otherwise a short plain category name (for example YAML frontmatter, markdown heading, vocabulary). Mark each line safe-fix or report-only by the rule Safe fixes.
   An unattended run follows rule Unattended run (weekly routine).

**B. `fix`** — "apply safe fixes", "clean up graph schema". Always re-audits fresh first (never fix from a stale report), running the audit once and reusing that run as the input to the pre-fix report below, then:

Follow the rule Pre-fix report (`references/rules.md`) before applying anything.

```bash
python3 scripts/schema-pass.py GRAPH_ROOT SCHEMA_CONFIG            # dry-run; add --apply after review
python3 scripts/graph-link-audit.py GRAPH_ROOT SCHEMA_CONFIG [--pages-dir DIR] --apply-safe-fixes
```
Which categories are written, in what order, and the no-schema route: rule Safe fixes (`references/rules.md`). Expected: the dry run lists the files it would change and writes nothing; `--apply` and `--apply-safe-fixes` report the changed files and counts. Dry-run `schema-pass.py` first and read the file list it prints; the go-ahead on the pre-fix report covers its `--apply`, after the backup question of rule Safe fixes. Drafts: rule Drafts. Everything else stays report-only, apart from the judgment-gated scripts below — report changed vs. skipped-needs-judgment counts. `fix --assets-only` = `python3 scripts/assets-audit.py GRAPH_ROOT`, a separate maintenance action: it creates a missing `assets` symlink, moves stray files out of a real `assets` folder, creates `pages/assets` if missing and fixes `../../assets/` links. For an existing symlink it only prints where it points.

**Judgment-gated maintenance scripts (invoke manually, never as part of `--apply-safe-fixes`).** The first two write report-only categories, so each runs only once the orchestrator has done the judgment work in the Output contract's "Report-only findings get a recommendation" rule; the third is an occasional cleanup of the type mapping (rule Safe fixes). None runs unattended:
- `graph-heading-extract.py GRAPH_ROOT [--pages-dir DIR] [--apply]` — converts a bullet that starts with a bold label and whose parent bullet is not already a `heading:: true` heading (the shape `inline-bold-heading` flags, plus other bold-label bullets such as bibliography entries, so read the dry run before `--apply`) into real `heading:: true` + child-bullet structure; skips (flags for manual review) the case where content likely lives in re-indented sibling bullets rather than a clean same-line split.
- `graph-colon-label-fix.py GRAPH_ROOT INCLUDE_LIST.json [--apply]` — converts an explicit, orchestrator-picked list of `Label: value` locations (the JSON file holds `{"file": "pages/X.md", "line": 12}` entries, line 1-based as `schema-lint.py` reports it) to `Label - value`; re-validates each location against current file content before writing, never a blind pattern-match across the graph. Build the list from a fresh `schema-lint.py` run made after any other fix or heading extraction, because those shift line numbers, and run one include list once: a converted line that still holds a later colon matches again.
- `property-normalize.py GRAPH_ROOT SCHEMA_CONFIG [--apply]` — maps `type::` values through the schema config's `canonicalization.type` (unmapped values: rule Safe fixes) and renames retired `block-type::`/`item-type::` lines to `type::` (without merging two lines into one; an `item-type::` whose value is one of the config's `zotero_itemtypes` is Zotero's own and is left alone); dry-run by default, and the type-only subset of what `schema-pass.py` already does, so an occasional cleanup pass, not part of every `fix` run.

Rule Pages-folder-only scripts (`references/rules.md`) limits `schema-pass.py`, `property-normalize.py` and `assets-audit.py`.

**C. `write` / `create`** — schema-validated new page. Open `references/rules.md` and `references/layers/<layer>.md` once, up front, and reuse them for the steps below and the read-back. If the Drafts question has not been asked this session, ask it before step 3 (rule Drafts). Refuse for a no-schema graph unless the user accepts passthrough-equivalent, which is the raw/passthrough subcommand's route (banner and confirmation included).
1. Look up the page's `type::` in the schema config's `required_properties`; prefill every required property (ask for values you can't derive).
2. Apply rule Bracket rule (`references/rules.md`) to every link-type property value of the schema config.
3. Check the new title/filename/alias for case-insensitive uniqueness against the whole graph — refuse on a clash; proactively disambiguate generic-sounding titles.
4. **Apply the layer's "Write rules that always apply" checklist (`references/layers/<layer>.md`: no bold, no single-colon pseudo-labels, real `heading:: true`) while generating the content, not as a post-hoc lint pass.** Every layer whose `check_schema_support` is true carries it; it is mandatory for every line written.
5. Write via the layer's preferred path (`references/layers/`), run the read-back (rule Read-back after a write, `references/rules.md`) on that page, then confirm what was validated and prefilled and the read-back result. Expected: the page on disk passes the read-back with no findings.

**D. `edit`** — schema-validated change to an existing page: run the same validation pipeline as the write/create subcommand (the bracket rule, the title uniqueness check and the layer's write-rules checklist) on the change before writing, route through the layer's edit path, then do the write/create subcommand's final read-back step. The format checklist applies to edited/added lines exactly as to a full new page.

Both write/create and edit produce correctly-formatted content the first time; `audit`/`fix` exist to catch drift and pre-existing content, not to be the routine cleanup step after every write.

**E. `raw` / passthrough** — explicit opt-in ONLY. Print the banner `PASSTHROUGH — schema validation skipped, may violate the graph's format contract`, get confirmation, then execute via the layer's tools. Full range (delete, rename, tags, arbitrary edits). Never enter this mode by inference.

**F. Read-only ops** — list / read / search / list-tags: ungated on every layer that supports them (an operation the layer doc does not map is unsupported there: say so), can't violate the contract (the Apple Notes layer supports none of them: say so).

**G. Layer-specific ops** — routed per `references/layers/`: e.g. text generation for apps with no API, or a manual compatibility-check procedure for apps with no automation hook at all (Apple Notes). A layer that can't support an operation returns unsupported — say so; never silently no-op or silently fall back.

## Graph rules (read `references/graph-rules.md` before creating or restructuring pages)

Applies on top of write/create and edit. The skill proposes and checks; the user builds the notes, relations and concept pages (those two subcommands write the page structure, the required properties and the content the user supplies, and never compose notes, relations or definitions), and nothing is written for the user or for assessed work (if a page touches assessed work, the module AI-rules gate named in the project's instructions comes first; if the project names no such gate, ask the user before writing).
- Concept, topic or fleeting stub, with the three promotion criteria; vocabulary pages written as codebook entries (Definition, Counts as, Does not count as, one verbatim example with citation key and page).
- Every link in a Connections section starts with a relation verb from `assets/relation-vocabulary.json` (eight to start, the user edits the list) and a one-line reason. Never invent a verb: ask which fits. Existing pages without verbs are reported as warnings with a proposal; the user edits them.
- Duplicate check before any page is created: filenames, `title::` and `alias::` (also existing aliases); route to "update" or "link" on a hit.
- Reading pages use only the user's existing Reading Notes and Reading Report templates; the skill never changes their layout or fills the user's annotation headings. Templates: rule Templates and the blank writer.
- Page-kind test, journal graduation and Mermaid or canvas maps only when asked. Source folders are read-only.

## Zotero boundary

Zotero metadata, tags and collections are not this skill's job: follow `.claude/shared/zotero-mcp/rules.md` (relative to the project root; if it is not there, say so and stay out of library work; its "One reading, start to finish" gives the order, including where the duplicate check and audit fall). Workflows in that file call this skill's modes; this skill never edits the library.

## Layers

A layer = one app-facing view of the same files. A registered graph uses the logseq-obsidian layer; another layer applies only when the user names that app for the write. Adapter contract and per-layer tool mapping: `references/layers/logseq-obsidian.md` (primary; MCP write path + direct-write fallback), `references/layers/tine.md` (no adapter — filesystem only; caveats in `references/layer-tine-caveats.md`), `references/layers/apple-notes.md` (no adapter, no automation hook at all — read-compatibility is a manual check only), `references/layers/finalist.md` (caveats in `references/layer-finalist-caveats.md`). **Read the relevant caveats file before any first-time interaction between a new app and a live graph — the caveats name what is still unverified and must be scratch-copy-tested first.**

## Examples

**"check my graph schema"** → resolve graph (Step 0) → ask about draft pages, then run `schema-lint.py`, `graph-link-audit.py` and `graph_audit.py` (the audit subcommand) → one categorized report, e.g. `49 should-be-linked, 1 dangling-bracketed-link, 3 missing-required-property`, grouped by category, nothing written.

**"apply safe fixes"** → re-audit fresh → show the pre-fix report including any `inline-bold-heading` findings and wait for the go-ahead (rule Pre-fix report) → run the two fix scripts in the order rule Safe fixes gives (the fix subcommand) → report of what changed vs. what stayed report-only with a recommendation for each.

**"add a new person page for Priya"** → resolve graph → look up `Entity or Person` in the schema config's `required_properties`, prefill/ask for values → check title uniqueness → apply the layer's write-rules checklist while generating → write via the layer's preferred path (the write/create subcommand) → confirm what was validated and prefilled.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| A write succeeds but doesn't appear in the already-open Logseq/Obsidian window | Direct-file-write fallback was used (no live MCP write API reachable) | Expected — disclose it per the layer doc ("won't appear until the app reloads"); tell the user to reload, don't claim live-sync |
| A page made with the Logseq MCP create/update-page tool has properties or nested blocks converted from YAML or `#` headings in `content` | The tool's `content` parameter auto-converts YAML/`#` on write — it doesn't know this graph forbids both (the layer doc's Logseq MCP gotcha has the details) | Always pass properties via the tool's structured `properties` object, never as YAML-in-content; build `heading:: true` structure via direct block edits, not `#` in content |

## Output contract

Audit adds: pages scanned (the scripts' counts, which differ because each skips different folders), findings with page:line (and the severity `graph_audit.py` assigns: error, warn or info), hubs, checks skipped and why, and the line "nothing in the graph was changed". Write adds: the read-back result.

This skill writes no session-log step markers: each run is short and ends in a report or a written file, and the pre-fix report file is the checkpoint a resumed run reads. Every audit, fix, write and edit run ends with: what was scanned/written (counts), findings grouped by category with safe-fix vs report-only marked, and — for writes — exactly which files changed. Fixes never touch report-only categories (the judgment-gated scripts above are the only scripted way those are written, run manually one at a time; who fixes which finding, and when, is set by rule Safe fixes in `references/rules.md`); nothing is ever installed or downloaded without the user's explicit confirmation.

**Report-only findings get a recommendation, not a raw dump.** A category stays report-only because it needs judgment a script can't safely automate — that's exactly the case where the orchestrator (you) should still DO the judgment work, not hand the user an unresolved list. Before presenting any report-only finding, read the surrounding context (the page itself, sibling content, established conventions elsewhere on the same page or graph, the user's documented preferences in memory) and propose a specific resolution — "here's what I'd do and why" — for the user to approve or redirect, never bare "here's the ambiguous thing, you decide." Where the value is the user's to supply (a relation verb, a required property value, a definition), the proposal is the question that offers the candidates found in context; the skill does not write the value.
