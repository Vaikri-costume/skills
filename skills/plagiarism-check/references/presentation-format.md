# Presentation format — plagiarism-check

The presentation agent's response IS the report. Every section and finding appears in full; no summary, no truncation. Pass `Location:` through verbatim. Omit a section with no content, except Coverage and Limits.

## Header

From `assets/report-header-template.md`. Always include the Limits block (from `misconduct-categories.md`, "What this skill cannot do").

## Sections, in order

1. **Needs attention first**: judgement findings with verdict `upheld` and Weight `major` or Severity RED. One line each: `Para [n] · [source] · [Category] · [Weight]: [one sentence]`. Cap 5; say how many more follow.
2. **Overlap with sources** (`overlap.json`): per source, verbatim-runs then short-matches, each with paragraph, the draft words, the source words and the judgement agent's call (flag / cleared and why). Show `coverage` per source as a percentage of the draft's words. Say `quoted_matches` were properly marked and not flagged.
3. **By source**: for each source with an upheld finding, `### Source: [slug]`, full finding entries (Checks 2, 3, 5 and flagged Check 1).
4. **Citation and quotation integrity** (`audit.json`, `quotes.json`): a checklist, not accusations. Subsections, each only if non-empty: quotations not found in the cited source; quotations with no source supplied (say which authors to supply); in-text citations with no reference-list entry; reference-list entries never cited; repeated reference entries; sources cited alone across 4+ consecutive paragraphs and the final quarter; authors introduced narratively 3+ times; reference artefacts (utm parameters, invalid ISBN checksums, malformed DOIs, placeholder markers). These are the machine-checkable items among the usual indicators of unauthorised AI use in UK procedures and are also ordinary referencing errors; say which fits.
5. **Self-plagiarism** (prior-submission overlap, if prior files were given): the same layout as section 2, labelled self-plagiarism.
6. **Needs your decision**: verdict `ambiguous` and `unaddressed`; show the challenger's question verbatim.
7. **Disputed (for reference)**: `[source]: "[quote excerpt]" — disputed because [reason]`.
8. **Not verified**: findings the location script marked `[QUOTE-UNMATCHED]` (the quote is not in the draft) — listed so nothing is silently dropped.
9. **Coverage**: per source, `[n] upheld | [n] disputed | [n] needs your decision | [n] not verified`; totals; number of deterministic items per audit subsection; sources that could not be resolved (no text available).

## Tone

Flags for the writer's review, not accusations. Say what to do: add quotation marks and a citation; rewrite from understanding; credit the framework; supply the missing source. Never advise how to avoid detection.

State once in the report, near the header, that the categories follow common UK university procedures and that the writer should adapt category names and thresholds to their own institution's policy.
