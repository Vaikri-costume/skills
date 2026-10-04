# Layer: Logseq/Obsidian (one graph, one layer)

The primary layer: a Logseq-format graph whose pages directory is simultaneously an Obsidian vault. One layer, potentially several instances — the graph registry lists each instance with its `pages_dir` and `schema_config`. An instance with `schema_config: null` (a plain vault) has NO declared schema: `create`/`edit` there always run passthrough-equivalent and must say so plainly, never silently fall back; `audit` runs links-only.

## Adapter contract (all layers share this shape)

```
list / read / search / check_schema_support
create(spec, mode) -> WriteResult | GeneratedText | Unsupported
edit(ref, changes, mode) -> WriteResult | Unsupported
validate(spec_or_changes)   # only when supports_schema
```

A layer that can't support an operation returns unsupported — never a silent no-op.

## Method mapping

| Method | How |
|---|---|
| `list` / `read` / `search` (and all of `audit`/`fix`) | Direct filesystem — fast bulk scans over `pages_dir`, the proven pattern of the bundled scripts |
| `check_schema_support` | From the registry entry: `schema_config` non-null → full schema support |
| `validate` | The pipeline in SKILL.md subcommand C: required-property prefill, existence-conditional bracket rule, case-insensitive uniqueness |
| `create` / `edit` | Preferred: a live write API into the running app, when the runtime provides one — e.g. on Claude runtimes with an Obsidian Local-REST-API MCP server connected, use its write/patch/frontmatter/replace tools, because they keep the running app's state in sync in a way a raw file write doesn't guarantee. Fallback (any runtime without such tools, or when the app isn't running so the API isn't reachable): direct file write, with the explicit disclosure "written directly to disk; won't appear in an already-open app window until it reloads." Never pretend live-sync happened when it didn't. |

**Logseq MCP `create_page`/`update_page` gotcha (verified 2026-08-11):** these tools accept `content` as markdown that gets auto-converted — YAML frontmatter (`---`) becomes page properties, and markdown `#` headings become nested blocks. That conversion is exactly the format this graph forbids. Always pass properties via the tool's structured `properties` object parameter, never as YAML inside `content` — confirmed this produces correct native `property:: value` syntax on disk (schema-lint clean, byte-for-byte round-trip via `get_page_content`). Similarly avoid `#` headings in `content`; build `heading:: true` structure via direct block edits instead, since `create_page`'s own heading-conversion doesn't know about this convention either.

## Write rules that always apply (both paths)

Apply these DURING generation — don't write first and lint after. `write`/`create`/`edit` (SKILL.md subcommands C/D) require this checklist as a mandatory step for every line generated, not just the schema pipeline (required properties, bracket rule, title uniqueness).

- First-block `property:: value` metadata, contiguous, no blank lines splitting it; never YAML frontmatter.
- No `#` headings — a bullet with `heading:: true` on its own child line.
- No bold markdown (`**text**`) anywhere, ever — unconditional, no exceptions for emphasis, labels, or headings (confirmed 2026-08-11). A heading is never simulated with bold; use real `heading:: true` structure instead.
- No inline `- Label — description` crammed onto one line when `Label` is meant to function as a heading. A heading and its content are always two separate blocks: the heading bullet (plain text) carries `heading:: true` on its own child line; the content goes on a further-indented CHILD bullet below it, plain `-` prefix, never an em dash. (When the same shape is a flat glossary/bibliography-style entry rather than a real heading, leave it as one bullet — this is a judgment call, see `inline-bold-heading` in the glossary.)
- No single-colon pseudo-labels (`Label: value`, mimicking property syntax without being one) — use a hyphen instead (`Label - value`). Exception: a colon is correct and must stay when it's literally part of a quoted external title (a citation, a book title, a published work's own punctuation) — never rewrite someone else's title. Your own prose, notes, and labels always prefer the hyphen.
- **Writer attribution** (confirmed 2026-08-11): creating a page, or writing/replacing its whole content, sets the PAGE property `writer:: Claude`. Adding/editing BLOCKS within an existing page whose page-level `writer::` is already someone else (and that isn't changing) leaves the page-level property alone — instead add a BLOCK-level `writer:: Claude` property on just the blocks you added, per the graph's existing type/writer promotion rule (block-level values only for exception blocks that diverge from the page's dominant value).
- Tasks as keywords (`TODO`/`DOING`/`DONE`/`WAITING`/`CANCELLED`), never `- [ ]` checkboxes.
- Bare `[[Page Name]]` links; no `/` in page names.
- Bracket rule: link-property values bracketed only when the target exists; dangling brackets always removed.
- Case-insensitive global uniqueness of titles/filenames/aliases; disambiguate generic titles at creation time.
- Never hand-write app-internal properties (`id::`, `collapsed::`, `heading::` is set only via the heading convention above, `background-color::`, `graph-hide::`).
