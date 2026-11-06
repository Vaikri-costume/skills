---
version: "1.0.1"
category: C
parent-version: "1.0.0"
author:
  primary: "Vaikri-costume"
inspirations: []
---

# History — guide-research-essay

## Changelog

### 1.0.1 — 2026-11-06
#### Changed
- Docs: README: "Features & modes" and "Structure" sections; "How to install" and "Sibling skills" filled in; "How to invoke" lists the mode names, more triggers and the `ai_rules_file` and `use_log_file` profile keys.
- Docs: glossary: 11 headed terms (brief check, draft mode, exactness check, gap list, link check, outline mode, position prompt, reading in general, reading for a research question, study support, use record).
- Reading for a research question: an existing summary or note is checked directly instead of asking the user to explain the reading again; the old step 6 is merged into step 2.
- Reading in general: techniques are taught only when the user asks.
- Hard rules 2, 3, 4, 6, 7, 8, 9, 10 and 12 now give their reason.
- Redundant wording compressed (rules 4, 5 and 6, gate step 2, editing-type bullet, stuck prompts, use record ordering). Rule 5 now bans "opposite", "contradicts" and "reverses" in the built-from trace too; stuck prompts never ask what a paragraph is for.
- Budget check and Length check state their expected script output.
- Known limitations: states there is no checkpoint or session-log step; the only durable write is the optional `use_log_file` row.
#### Removed
- Provenance "See also" line from the runtime SKILL.md; the credit stays in README and in this file's lineage notes. [internal]
- Redundant "Declines to write, summarise or rewrite for them." sentence from the SKILL.md description. [internal]

### 1.0.0 — 2026-11-06
- Initial scaffold from the approved plan: four coaching modes (reading for a research question, reading in general, outline, draft), the AI-rules gate read from the user's own file at run time, a budget and word-count script with tests.

## Lineage notes

- Category C (idea inspiration). Ideas adapted from Writing Desk 0.1.0 by Naji Kayal (Apache-2.0): nothing invented, gaps shown not filled, an evidence map for outlines, differences listed and never corrected. Rewritten; no text copied. Its generating skills (write-draft, write-outline) are deliberately not carried over.
- Reading modes come from an in-house reading-coach plan merged on 2026-11-06.
- `checked-marketplace:` none. The marketplace steps were skipped for this build on the user's instruction of 2026-11-06.
