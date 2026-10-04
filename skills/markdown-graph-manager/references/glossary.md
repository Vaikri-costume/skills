# Glossary — markdown-graph-manager

This glossary is self-contained: every term this skill's own files use is defined below, and nothing here requires any other skill or toolchain to resolve. (If this skill happens to be installed alongside the CCVW skill family, its shared glossary at `skill-creator-ccvw/references/ccvw-glossary.md` defines that family's build-process vocabulary — optional background only, never needed to run this skill.)

## Skill-specific terms

| Term | Definition |
|---|---|
| `blank-title-collision` | two or more files each carrying a valueless `title::` line, which in Logseq is an explicit empty-string title override — they fight for the same blank page identity and all but one silently vanish from the UI |
| `dangling-bracketed-link` | a `[[bracketed]]` link whose target page does not exist — property value or body prose alike — always unbracketed by the fix subcommand, no exceptions, so the phantom page is never created. Self-healing: once a real target page is created, the next audit's `should-be-linked` check re-brackets it. |
| `dead graph` | a folder that looks like a graph root but is retired and must never be operated on; the discovery script hard-rejects known dead paths even when passed explicitly |
| `format contract` | the set of rules a page must satisfy to stay valid in every app reading the graph (property-block metadata, no YAML, keyword tasks, bare wikilinks, heading properties) |
| `inline-bold-heading` | a `- **Label** — content` bullet, all on one line — report-only always (structural judgment: is this meant as a heading?). When it IS meant as a heading, the fix is two separate blocks: the label as its own bullet with `heading:: true`, and the content as a further-indented child bullet. Note: the `bold-markdown` safe-fix strips `**` unconditionally and will make a line stop matching this check, even when it was never structurally resolved — see the ordering-trap note in SKILL.md's `fix` subcommand |
| `bold-markdown` | any `**bold**` text anywhere in the graph — safe-fix always, unconditional (no bold formatting anywhere in this graph, confirmed 2026-08-11), strips the `**` markers and keeps the plain text; never restructures |
| `single-colon pseudo-label` | a short label-like phrase at the start of a bullet followed by a single `:` (never `::`, which is a real property) mimicking property syntax without being one — e.g. `University Affiliation: ...` should be `University Affiliation - ...`. Report-only always: ordinary prose also produces this shape (quote attributions, citations, sentence fragments), so a real-vs-prose read needs a human/orchestrator judgment call per instance — never auto-fixed. High-repetition labels graph-wide (3+ identical occurrences) are strong evidence of a genuine template field; singletons need individual reading |
| `graph root` | the directory containing a graph's `pages/` folder; every script takes it as an explicit argument, never self-locates |
| `layer` | one app-facing view of the same markdown files (Logseq/Obsidian, Tine, Apple Notes, Finalist), each documented in `references/layers/` |
| `layer adapter` | the abstract operation set a layer maps to concrete tools — list/read/search/check_schema_support/create/edit/validate; a layer that cannot support an operation returns unsupported, never silently no-ops |
| `links-only mode` | the audit degradation for a graph with no declared schema (plain vault): dangling-link reporting only, because property rules and title-uniqueness are format-contract checks that would false-positive there |
| `live graph` | a graph root confirmed as actively in use; the only kind the skill may write into |
| `passthrough mode` | explicit opt-in write mode that skips schema validation, always announced with a visible banner and confirmed before executing |
| `safe fix` | a violation category whose correction is mechanically verifiable (target-existence lookup, valueless-line deletion, known canonical mapping) — the only categories `fix` ever writes; all others stay report-only |
| `schema config` | the external JSON file (e.g. in `assets/`) holding all vocabulary, required-property, link-property, canonicalization, and tolerance data; the scripts carry none of it hardcoded |
| `schema-validated mode` | the default write/edit path — required properties prefilled, link values bracket-checked against page existence, titles checked for case-insensitive uniqueness before anything is written |
| `should-be-linked` | a plain link-type property value whose target page exists on disk — safe to wrap in `[[brackets]]` because existence was verified by lookup, not guessed |
| `tolerated property` | a property another app writes for its own features (e.g. a `tine.*::` namespace) that the linter must exempt from unknown-vocabulary findings |

## When to update this glossary

- When you add functionality that introduces new vocabulary, add the term here in the same edit pass — a term used in SKILL.md but missing here forces every future reader (human or agent) to re-derive its meaning, and re-derivations drift.
- When you rename a term in SKILL.md, update it here in the same edit pass.
- If you run any external audit or review tooling over this skill and it has to define a term cold, write that term back here afterward — but no such tooling is required to use or maintain this skill.
