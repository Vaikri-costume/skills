---
name: markdown-graph-manager
description: "Manage pages in a dual-format Logseq/Obsidian markdown knowledge graph — property:: block pages (no YAML frontmatter) that must stay valid across multiple apps reading the same files (Logseq, Obsidian, Tine, Apple Notes, Finalist). Use whenever the user wants to add or create a new graph page, edit an existing graph page and keep it schema-valid, audit or lint the graph, check graph schema or dangling wikilinks, run a graph health check, apply safe fixes, or clean up graph properties. Matches \"add a page to my graph\", \"edit this graph page\", \"audit my graph\", \"check dangling links in my graph\" — with or without the word schema. Also covers read-only search/listing and raw passthrough edits (explicit opt-in). Schema vocabulary loads from an external config, so it works on any property-block graph. Do NOT use for a plain YAML-frontmatter Obsidian vault with no Logseq property-block format — even for checking broken links there, since that's a generic vault check, not this graph's schema/format contract."
license: MIT
compatibility: agentskills.io@1.0
metadata:
  tier: model-agnostic
  created: 2026-08-11T13:44
  created-by: skill-creator-ccvw
  parent-version: "1.2.4"
  intended-audience: model-agnostic
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

Manages a markdown knowledge graph that must stay valid in two apps at once — a Logseq graph whose pages folder is simultaneously an Obsidian vault — and stays aware of other markdown apps reading the same files. The format contract (outline bullets, first-block `property:: value` metadata, no YAML frontmatter, keyword tasks, bare wikilinks) and all schema vocabulary live in external JSON configs under `assets/`, not in this skill: the **schema config** (vocabulary, required properties, canonicalization, tolerance lists) and the **graph registry** (which graph roots are live, which are dead, which schema each uses). Swap those two files to run this skill on a different graph. Terms used below are defined in `references/glossary.md`.

## Step -1: maintenance freshness check (before every subcommand)

Read the state file (location: `references/maintenance-check.md`). If its timestamp is under 7 days old, proceed silently. Otherwise run that file's two checks (app-version gaps, documentation-currency diff), present one compact notice, update the timestamp, and continue to the requested subcommand. The check **never downloads or installs anything**: a version gap is reported as a question to the user. If a source has no clean API, degrade to a "check manually" note — never fail the actual subcommand over a maintenance check.

## Step 0: resolve the graph

Never operate on a hardcoded or guessed path. `<registry>` is the graph registry JSON and `SCHEMA_CONFIG` the schema config named by the resolved entry; `assets/example-graphs.json` and `assets/example-schema.json` are shipped samples showing the shape — copy and adapt them for a real graph:

```bash
python3 scripts/graph-discovery.py assets/<registry>.json --list          # what graphs exist
python3 scripts/graph-discovery.py assets/<registry>.json --resolve PATH  # validate a candidate
```

Expected: `--list` prints JSON listing every registry graph with its `dead`/`ok` flags; `--resolve` prints a JSON status for the path (exit 0 when it matches a live graph, otherwise one of the statuses below).

- `rejected-dead` (exit 1): refuse, full stop — a dead graph root is rejected even when the user passes it explicitly; tell them why.
- `unknown` (exit 2): don't guess. Ask the user, and treat the gap as "the registry (and the memory it derives from) needs updating," not as license to proceed.
- Ambiguous which live graph is meant: ask.
- The resolved entry tells you `pages_dir` (`.` for a flat vault) and `schema_config` (null = no declared schema — see subcommand notes below).

## Subcommands

Route the user's request to exactly one of these. Mode is never inferred silently: schema-validated is the default for anything that reads like "add/edit a note"; passthrough only on explicit request.

**A. `audit`** — "audit/lint my graph", "check graph schema", "check dangling links", "graph health check". Read-only, never writes.
1. Resolve graph (Step 0).
2. With a schema: run both scripts and merge into ONE categorized report (grouped by category, never by originating script):
   ```bash
   python3 scripts/schema-lint.py GRAPH_ROOT SCHEMA_CONFIG --quiet
   python3 scripts/graph-link-audit.py GRAPH_ROOT SCHEMA_CONFIG [--pages-dir DIR]
   ```
3. Without a schema (`schema_config: null`): run ONLY `graph-link-audit.py ... --links-only` and say so plainly — format-contract checks (YAML, headings, title uniqueness, property rules) do not apply to a plain vault and would be false positives. Skip schema-lint entirely. `--links-only` still applies the location-independent dangling-bracket rule.
4. Report and stop. Expected: one report grouped by category with counts, and no file changed. Categories and which are safe-fixable: see the script's own header and `references/glossary.md`.

**B. `fix`** — "apply safe fixes", "clean up graph schema". Always re-audits fresh first (never fix from a stale report), then:

**Ordering trap: capture `inline-bold-heading` findings before applying `bold-markdown`.** Stripping `**` (the `bold-markdown` safe-fix) destroys the signal `schema-lint`'s `inline-bold-heading` check looks for — a flagged heading candidate reports clean on the next audit without having been restructured (heading:: true + child bullet). So before `fix --apply-safe-fixes`, show the user the full pre-fix audit report (including `inline-bold-heading` findings) so genuine candidates are restructured first or noted for follow-up, not silently forgotten. Also save that report to a scratch file (e.g. `${TMPDIR:-/tmp}/mgm-prefix-report.md`) before applying anything, so it survives a lost context mid-fix.

```bash
python3 scripts/graph-link-audit.py GRAPH_ROOT SCHEMA_CONFIG --apply-safe-fixes
python3 scripts/schema-pass.py GRAPH_ROOT SCHEMA_CONFIG            # dry-run; add --apply after review
```
Only the mechanically-safe categories are ever written (existence-verified bracket wraps, no-exception unbracketing of dangling bracketed links, deletion of valueless property lines, known canonical vocabulary mappings). Everything else stays report-only forever — report changed vs. skipped-needs-judgment counts. `fix --assets-only` = `python3 scripts/assets-audit.py GRAPH_ROOT` (symlink + asset-link repair, separate maintenance action).

**Judgment-gated maintenance scripts (invoke manually, never as part of `--apply-safe-fixes`).** These write the report-only categories once the orchestrator has done the judgment work in the Output contract's "Report-only findings get a recommendation" rule — they never run unattended:
- `graph-heading-extract.py GRAPH_ROOT SCHEMA_CONFIG [--apply]` — converts a bold-labeled bullet the audit flagged `inline-bold-heading` into real `heading:: true` + child-bullet structure; skips (flags for manual review) the case where content likely lives in re-indented sibling bullets rather than a clean same-line split.
- `graph-colon-label-fix.py GRAPH_ROOT --locations FILE:LINE[,FILE:LINE...] --apply` — converts an explicit, orchestrator-picked list of `Label: value` locations to `Label - value`; re-validates each location against current file content before writing, never a blind pattern-match across the graph.
- `property-normalize.py GRAPH_ROOT SCHEMA_CONFIG [--apply]` — Title-Cases property values and folds retired `block-type::`/`item-type::` into `type::` (dry-run by default); an occasional cleanup pass, not part of every `fix` run.

**C. `write` / `create`** — schema-validated new page. Refuse for a no-schema graph unless the user accepts passthrough-equivalent (state it plainly).
1. Look up the page's `type::` in the schema config's `required_properties`; prefill every required property (ask for values you can't derive).
2. Bracket rule for every `link_type_properties` value: bracket ONLY when the target page exists (check case-insensitively against titles, filenames, AND aliases, graph-wide); leave nonexistent targets plain so no phantom page is created.
3. Check the new title/filename/alias for case-insensitive uniqueness against the whole graph — refuse on a clash; proactively disambiguate generic-sounding titles.
4. **Apply the layer's "Write rules that always apply" checklist (`references/layers/<layer>.md`: no bold, no single-colon pseudo-labels, real `heading:: true`) while generating the content, not as a post-hoc lint pass.** Every layer with `supports_schema` carries it; it is mandatory for every line written.
5. Write via the layer's preferred path (`references/layers/`), then confirm what was validated and prefilled.

**D. `edit`** — schema-validated change to an existing page: run the same validation pipeline (C.2–C.4) on the change before writing, route through the layer's edit path. The format checklist applies to edited/added lines exactly as to a full new page.

Both C and D produce correctly-formatted content the first time; `audit`/`fix` exist to catch drift and pre-existing content, not to be the routine cleanup step after every write.

**E. `raw` / passthrough** — explicit opt-in ONLY. Print the banner `PASSTHROUGH — schema validation skipped, may violate the graph's format contract`, get confirmation, then execute via the layer's tools. Full range (delete, rename, tags, arbitrary edits). Never enter this mode by inference.

**F. Read-only ops** — list / read / search / list-tags: ungated, any layer, can't violate the contract.

**G. Layer-specific ops** — routed per `references/layers/`: e.g. text generation for apps with no API, or a manual compatibility-check procedure for apps with no automation hook at all (Apple Notes). A layer that can't support an operation returns unsupported — say so; never silently no-op or silently fall back.

## Layers

A layer = one app-facing view of the same files. Adapter contract and per-layer tool mapping: `references/layers/logseq-obsidian.md` (primary; MCP write path + direct-write fallback), `references/layers/tine.md` (no adapter — filesystem only; caveats in `references/layer-tine-caveats.md`), `references/layers/apple-notes.md` (no adapter, no automation hook at all — read-compatibility is a manual check only), `references/layers/finalist.md` (caveats in `references/layer-finalist-caveats.md`). **Read the relevant caveats file before any first-time interaction between a new app and a live graph — the caveats name what is still unverified and must be scratch-copy-tested first.**

## Examples

**"check my graph schema"** → resolve graph (Step 0) → run `schema-lint.py` + `graph-link-audit.py` (subcommand A) → one categorized report, e.g. `49 should-be-linked, 1 dangling-bracketed-link, 3 missing-required-property`, grouped by category, nothing written.

**"apply safe fixes"** → re-audit fresh → show the pre-fix report including any `inline-bold-heading` findings (see the ordering trap) → run `graph-link-audit.py --apply-safe-fixes` + `schema-pass.py` (subcommand B) → report of what changed vs. what stayed report-only with a recommendation for each.

**"add a new Person page for Priya"** → resolve graph → look up `Person` in the schema config's `required_properties`, prefill/ask for values → check title uniqueness → apply the layer's write-rules checklist while generating → write via the layer's preferred path (subcommand C) → confirm what was validated and prefilled.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| A write succeeds but doesn't appear in the already-open Logseq/Obsidian window | Direct-file-write fallback was used (no live MCP write API reachable) | Expected — disclose it per the layer doc ("won't appear until the app reloads"); tell the user to reload, don't claim live-sync |
| The Logseq MCP server's create/update-page tool writes YAML frontmatter or `#` headings into a page | The tool's `content` parameter auto-converts YAML/`#` on write — it doesn't know this graph forbids both | Always pass properties via the tool's structured `properties` object, never as YAML-in-content; build `heading:: true` structure via direct block edits, not `#` in content |

## Output contract

Every subcommand ends with: what was scanned/written (counts), findings grouped by category with safe-fix vs report-only marked, and — for writes — exactly which files changed. Audits never write; fixes never touch report-only categories; nothing is ever installed or downloaded without the user's explicit confirmation.

**Report-only findings get a recommendation, not a raw dump.** A category stays report-only because it needs judgment a script can't safely automate — that's exactly the case where the orchestrator (you) should still DO the judgment work, not hand the user an unresolved list. Before presenting any report-only finding, read the surrounding context (the page itself, sibling content, established conventions elsewhere on the same page or graph, the user's documented preferences in memory) and propose a specific resolution — "here's what I'd do and why" — for the user to approve or redirect, never bare "here's the ambiguous thing, you decide."
