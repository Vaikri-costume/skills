# Glossary — markdown-graph-manager

This glossary is self-contained: every term this skill's own files use is defined below, and nothing here requires any other skill or toolchain to resolve. (If this skill happens to be installed alongside the CCVW skill family, its shared glossary at `skill-creator-ccvw/references/ccvw-glossary.md` defines that family's build-process vocabulary — optional background only, never needed to run this skill.)

## Skill-specific terms

| Term | Definition |
|---|---|
| `blank-title-collision` | two or more files each carrying a valueless `title::` line, which in Logseq is an explicit empty-string title override — they fight for the same blank page identity and all but one silently vanish from the UI |
| `dangling-bracketed-link` | a `[[bracketed]]` link-type property value whose target page does not exist — always unbracketed by the fix subcommand, so the phantom page is never created (the exceptions are listed in rule Bracket rule in `references/rules.md`). Self-healing: once a real target page is created, the next audit's `should-be-linked` check re-brackets it (for an aliased link `[[X|alias]]` only the alias text is kept, so that one is re-linked by hand). |
| `dangling-link` | the same rule for a `[[bracketed]]` link in body prose, in a property value whose key is not a link-type property, or inside one comma-separated element of a link-type property value that holds more than one link or other text (such as `[[A]] [[B]]` or `[[A]] (draft)`; a list of single links is reported per element as `dangling-bracketed-link`): unbracketed always, with the same exceptions (rule Bracket rule in `references/rules.md`). Not self-healing: once the target page exists, the user re-brackets the link by hand. |
| `missing-required-property` | a page whose `type::` requires a property it lacks (`schema-lint.py` prints "missing required property"; `graph_audit.py` calls it `required-properties`); report-only, never auto-fixed, because the value has to come from the user |
| `empty-property-value` | a `key::` line with no value (an explicit blank override in Logseq); safe-fix: delete the line, except the cases named in rule Templates and the blank writer (`references/rules.md`) |
| `dead graph` | a folder that looks like a graph root but is retired and must never be operated on; the discovery script hard-rejects known dead paths even when passed explicitly |
| `format contract` | the set of rules a page must satisfy to stay valid in every app reading the graph (property-block metadata, no YAML, keyword tasks, bare wikilinks, heading properties) |
| `inline-bold-heading` | a `- **Label** — content` bullet, all on one line — report-only always (structural judgment: is this meant as a heading?). When it IS meant as a heading, the fix is two separate blocks: the label as its own bullet with `heading:: true`, and the content as a further-indented child bullet. Note: the `bold-markdown` safe-fix strips `**` unconditionally and will make a line stop matching this check, even when it was never structurally resolved — see rule Pre-fix report in `references/rules.md` |
| `bold-markdown` | any `**bold**` text anywhere in the graph — safe-fix always, unconditional (no bold formatting anywhere in this graph), strips the `**` markers and keeps the plain text; never restructures |
| `single-colon pseudo-label` | a short label-like phrase at the start of a bullet followed by a single `:` (never `::`, which is a real property) mimicking property syntax without being one — e.g. `University Affiliation: ...` should be `University Affiliation - ...`. Report-only always: ordinary prose also produces this shape (quote attributions, citations, sentence fragments), so a real-vs-prose read needs a human/orchestrator judgment call per instance — never auto-fixed. High-repetition labels graph-wide (3+ identical occurrences) are strong evidence of a genuine template field; singletons need individual reading |
| `graph root` | the directory containing a graph's `pages/` folder; the scripts that work on a graph take it (for `graph_audit.py`, its pages folder, next to which, when it is named `pages`, it also reads an `assets` folder for attachment names) as an explicit argument and never self-locate |
| `layer` | one app-facing view of the same markdown files (Logseq/Obsidian, Tine, Apple Notes, Finalist), each documented in `references/layers/` |
| `layer adapter` | the abstract operation set a layer maps to concrete tools — list/read/search/check_schema_support/create/edit/validate; a layer that cannot support an operation returns unsupported, never silently no-ops |
| `links-only mode` | the audit degradation for a graph with no declared schema (plain vault): dangling-link reporting only, because property rules, title-uniqueness and the no-bold rule are format-contract checks that would false-positive there |
| `live graph` | a graph root confirmed as actively in use; the only kind the skill may write into |
| **block-type::** | a retired property name for the page or block type; `schema-pass.py` and `property-normalize.py` rename it to `type::` |
| **item-type::** | a retired property name for the page type, renamed to `type::` by the same scripts; its value is left alone when it is one of the Zotero item types in the schema config |
| `passthrough mode` | explicit opt-in write mode that skips schema validation, always announced with a visible banner and confirmed before executing |
| `safe fix` | a violation category whose correction is mechanically verifiable (target-existence lookup, valueless-line deletion, known canonical mapping) — the only categories `fix` ever writes; all others stay report-only |
| `schema config` | the external JSON file (e.g. in `assets/`) holding all vocabulary, required-property, link-property, canonicalization, and tolerance data (`schema-lint.py` requires `type_vocab`, `writer_vocab_plain`, `status_vocab` and `zotero_only_properties` to be present); the scripts do not hardcode these lists, apart from the few names listed in rule Roles fixed in the format contract (`references/rules.md`) |
| `schema-validated mode` | the default write/edit path — required properties prefilled, link values bracket-checked against page existence, titles checked for case-insensitive uniqueness before anything is written |
| `should-be-linked` | a plain link-type property value whose target page exists on disk — safe to wrap in `[[brackets]]` because existence was verified by lookup, not guessed |
| `tolerated property` | a property another app writes for its own features (e.g. a `tine.*::` namespace) that no script flags; the schema config's tolerance lists exempt it from `schema-lint.py`'s Zotero-reserved-property finding (`graph_audit.py`'s info-level `zotero-only-property` does not read them) |

## Graph rules and audit terms

| Term | Definition |
|---|---|
| concept | a timeless, definitional term with its own page; an author's use of it is a sub-block attributed to that author |
| topic / thread | an evolving debate; lives on a Thread, Lens or Period page, not a concept page |
| fleeting stub | an idea without a name and a self-contained definition yet; stays a single block, not a page |
| codebook entry | a vocabulary page with Definition, Counts as, Does not count as and one verbatim example (citation key and page) |
| relation | the verb at the start of a Connections line, taken from `assets/relation-vocabulary.json`, followed by the link and a one-line reason |
| dead-end link | a link cited but never defined (no page exists) |
| orphan / hub | a page nothing links to / the most linked-to pages |
| unlinked mention | a page's title, filename or alias appears in text without a link; a candidate only, judged by reading the sentence |
| read-back | re-reading a page after writing it to catch leftover template text; a leftover placeholder is a failed write |
| propose then confirm | every `graph_audit.py` fix is shown and applied by hand only after the user's yes for that one finding; the `fix` subcommand's safe-fix categories (rule Safe fixes, `references/rules.md`) are applied together after one go-ahead on the pre-fix report |

## When to update this glossary

- When you add functionality that introduces new vocabulary, add the term here in the same edit pass — a term used in SKILL.md but missing here forces every future reader (human or agent) to re-derive its meaning, and re-derivations drift.
- When you rename a term in SKILL.md, update it here in the same edit pass.
- If you run any external audit or review tooling over this skill and it has to define a term cold, write that term back here afterward — but no such tooling is required to use or maintain this skill.
