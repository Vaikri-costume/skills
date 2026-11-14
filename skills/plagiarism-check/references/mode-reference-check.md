# Reference-check mode

Runs only when the writer names it ("reference check", "check my references"). It tells the writer which listed works exist, are described correctly, and say what the draft claims. It checks and formats; it never verifies, fixes a work it cannot find, or writes a citation for the writer. The gate (`profile.md`) has already run.

## What leaves the machine

The data sent is limited by the Hard rules in SKILL.md (title, first author, year, DOI and ISBN only). Say so in the report header. If the writer declines lookups, run `lookup --offline`: every entry becomes Review with "not looked up".

## Steps (`$RUN` is the run folder)

1. **Parse**: `python3 ${CLAUDE_SKILL_DIR}/scripts/tofile.py $RUN/entries.json ${CLAUDE_SKILL_DIR}/scripts/reference_check.py parse <draft>`. Each entry has the fields the writer gave, the fields missing, and the kind of place to look for each (never an identifier). Expected: one object per list entry. Zero entries: stop and say the list was not found.
2. **Cross-check** (document-wide): `python3 ${CLAUDE_SKILL_DIR}/scripts/tofile.py $RUN/cross.json ${CLAUDE_SKILL_DIR}/scripts/reference_check.py cross <draft>` and `python3 ${CLAUDE_SKILL_DIR}/scripts/tofile.py $RUN/audit.json ${CLAUDE_SKILL_DIR}/scripts/shared/citation_audit.py <draft>`. Every in-text citation needs a list entry and every entry a citation; `near_match` says when a year or an author's spelling differs. Steps 1 and 2 are independent: issue the parse, cross and audit commands in one message; `lookup` is the first step that needs `entries.json`.
3. **Look up**: `python3 ${CLAUDE_SKILL_DIR}/scripts/tofile.py $RUN/records.json ${CLAUDE_SKILL_DIR}/scripts/reference_check.py lookup $RUN/entries.json` (add `--offline` when the writer declined lookups). Expected: one record per entry with a `status` of found, none, unreachable or not looked up. Before declaring any source unreachable, try in order: the writer's library (Zotero tools when available), a source folder the writer supplied, the OpenAlex `open_access` link in the record; then ask the writer for the text.
4. **Verdicts**: `python3 ${CLAUDE_SKILL_DIR}/scripts/tofile.py $RUN/verdicts.json ${CLAUDE_SKILL_DIR}/scripts/reference_check.py verdicts $RUN/entries.json $RUN/records.json`. Field verdicts: MATCH, CONTAINS (one value inside the other), TYPO, ABSENT, CONTRADICTION. Outcomes: **Clean**, **Fix** (a field differs from the record: a proposed correction goes in the patch log), **Not found** (an article whose DOI or title no index knows: possibly fabricated or mis-cited, never fixed), **Review** (anything else: books, reports, archives and web pages are often absent from the indexes, so absence is not evidence they are invented; an identifier whose record is a different work is flagged `frankenstein`; a lookup that failed). More than 70% Not found with no definite fake means suspect parsing first.
5. **Claim fidelity** (only for works whose text is available, from the library or a supplied folder): one judgement agent per source (`dispatch-protocol.md`, Agent rules; name `PlagSource-<slug>-<run>`; brief = `source-judgement.md` with Check 6 only and no overlap input), dispatched in the same message as `verdicts` since it needs only `entries.json` and the source texts; its output goes through the location correction and challenger steps like any finding, and `## No findings` means every claim is `supports`. Other works: `not checked`. Never decide what a work says from memory.
6. **Present**: `python3 ${CLAUDE_SKILL_DIR}/scripts/tofile.py $RUN/table.md ${CLAUDE_SKILL_DIR}/scripts/reference_check.py table $RUN/verdicts.json` writes the outcome table, the patch log and the two fixed lines; the report adds the cross-check, the claim-fidelity statuses and the header from `presentation-format.md`. Then the report check in `dispatch-protocol.md`, Presentation (with `--refs`). Expected: exit 0.

## Rules specific to this mode

- A proposed correction is a row in the patch log (entry, field, original, proposed, source, reason). The original value is always kept; nothing is applied to the draft or the list.
- A DOI, ISBN or URL missing from an entry is never supplied, not even when a record shows one. Say only that it is not given.
- An identifier from an index record may appear only inside a note about that record ("the record found is a book review, DOI …"), labelled as the record's and never as a value for the entry; the report never cuts an entry's text mid-identifier.
- Missing fields are listed with the kind of place to look (the title page, the article's first page), never with an identifier.
- Say the Limits line (`acceptable-use.md`) and once that entries are formatted or checked, not verified.
- A metadata problem in the writer's Zotero library is reported as a note ("for the library") and never edited here.
