# Finalist compatibility caveats

Verified against Finalist 4.0's own documentation (`finalist.works/docs/markdown-files/`) on its release day, 2026-08-11.

**Standing rule: the integration is real but UNVERIFIED for a property-block graph. Never point Finalist at a live Logseq-format graph without a throwaway-copy test first.** Let the Step -1 documentation-currency check flag any change in its documented format support.

## What its docs actually promise

- Any folder of `.md` files becomes a native notebook; edits round-trip; tasks checked in Finalist write back into the source file.
- Documented metadata dialects — and ONLY these: **YAML frontmatter**, **Obsidian Tasks** checkbox syntax (`- [ ] … 📅 date`), **Dataview inline fields** (`[due:: date]`).

## Why that's a risk for this graph family

A dual-format Logseq/Obsidian graph uses **neither** of Finalist's documented formats: metadata is a first-block `property:: value` run (no YAML anywhere), and tasks are keyword-form (`TODO`/`DOING`/`DONE`/`WAITING`/`CANCELLED`), never `- [ ]` checkboxes. The docs say nothing about what Finalist does with a format it doesn't recognize — preserve it, strip it, or rewrite tasks into checkbox syntax on write-back. Undocumented ≠ safe.

## The throwaway-copy test (before any live use)

1. Copy 3–5 representative pages to a scratch folder — include at least one page with a `related::` property block and one with a `TODO`/`DOING` keyword task.
2. Point Finalist at the scratch folder; open pages; interact with a task (check it off).
3. Diff every file afterward: any rewriting of the property block, any conversion of keyword tasks to checkboxes, any injected YAML → the layer stays generate-text-only for this graph.
