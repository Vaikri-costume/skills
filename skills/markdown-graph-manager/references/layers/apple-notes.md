# Layer: Apple Notes — native markdown import, read-compatibility only

This layer's requirement is narrow. It is NOT "sync graph pages to Apple Notes" — it is "confirm the graph's markdown files are readable by Apple Notes' own native markdown import." No bidirectional bridge is needed or wanted.

## What Apple Notes actually does (macOS Tahoe / iOS 26+, native, no third-party tool)

Confirmed via Apple's own release documentation and independent write-ups: Notes natively imports and exports `.md` files, converting Markdown syntax into its rich-text format on import (and back on export). Verified supported syntax: headings, lists, links, bold, italics. Verified NOT supported: tables, footnotes, diagrams — these fail to render correctly.

**Unverified**: what happens to this graph's Logseq-specific syntax on import — first-block `property:: value` lines, bare `[[wikilinks]]` (Apple Notes has no page-linking concept), `heading:: true` (vs. real `#` headings), keyword tasks (`TODO`/`DOING`). No documentation states whether these pass through as inert plain text (harmless) or are dropped/mangled. This has never been tested against this graph's actual files.

## Why no bridge tool

A bidirectional sync bridge (e.g. `shakedlokits/stash`) was evaluated and rejected: it solves a problem this layer doesn't have (the need is read-compatibility, not live sync), it was unreliable in testing (`push` created a duplicate note per run; `pull` couldn't find a note it had just created), and it writes real YAML frontmatter (`apple_notes_id::`), which conflicts with this graph's no-YAML convention. Do not reintroduce it for this layer's purpose.

## Adapter mapping

| Method | How |
|---|---|
| `check_schema_support` | false — Apple Notes has no property-block concept |
| `create` / `edit` | **Unsupported.** There is no write path for this layer, by design — it isn't needed |
| `list` / `read` / `search` | **Unsupported as a scriptable call.** Apple Notes' markdown import is a manual GUI action only (File → Import, or drag-and-drop) — there is no CLI, Shortcuts action, or AppleScript hook for it. This skill cannot drive it. |
| `validate` | not applicable |

## What this skill actually does for this layer

Nothing automated — it can't be. The only actionable step is a **manual compatibility check the user runs themselves**:

1. Copy 2–3 representative graph pages to a scratch folder (include one with `related::`/`project::` properties and one with a `TODO`/`DOING` task, same spirit as the Finalist throwaway-copy test in `references/layer-finalist-caveats.md`).
2. In Notes.app: File → Import to Notes (or drag the files in).
3. Open the imported notes and check: did the property lines and task keywords render as plain inert text (fine — just unstyled) or did anything get silently dropped?

Until that manual check happens, treat this layer's read-compatibility as unverified, not assumed-safe.
