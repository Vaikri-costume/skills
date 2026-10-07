# Glossary — plagiarism-check

See also: [`ccvw-glossary.md`](../../skill-creator-ccvw/references/ccvw-glossary.md) for shared CCVW terms. This file lists only skill-specific terms.

Shared mechanics: `$RUN` (temp run folder), `[QUOTE-UNMATCHED]` (the quote is not in the draft). This skill uses four verdict labels (upheld, disputed, ambiguous, unaddressed; see `challenger-synthesis-rules.md`) and no A/B pair.

## Skill-specific terms

| Term | Definition |
|---|---|
| `Check 1/2/3/5` | the judgement checks: 1 overlap-match review, 2 synthesis versus summary, 3 framework origin, 5 paraphrase distance (see `source-judgement.md`); there is no Check 4 |
| `citation-check` | default mode: compares the draft with its cited sources only |
| `full-scan` | mode that compares the draft with every source page in the project |
| `judgement agent` | the single read-only agent that judges one source |
| `overlap.json / audit.json / quotes.json` | deterministic outputs rendered but never re-judged |
| `PlagSource-<slug>-<run>` | name of the judgement agent for one source (`<slug>` source label, `<run>` run id) |
| `short-match` | 4 to 5 identical words with 3+ content words; weak evidence |
| `verbatim-run` | 6 or more identical consecutive words outside quotation marks |
| `Weight` | poor-academic-practice, minor or major (typical UK procedure weights) |
