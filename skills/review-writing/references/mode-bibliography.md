# Bibliography reviewer mode (only when the writer names it)

Question answered: is every in-text citation matched to a list entry, every entry cited, and what has actually been checked about each source? It reviews the writer's references; it never writes, completes, corrects or formats an entry.

## Steps

1. `python3 ${CLAUDE_SKILL_DIR}/scripts/shared/citation_audit.py <draft>` gives the citation inventory, unmatched citations, uncited entries and malformed-identifier flags. Treat its output as authoritative; do not recount.
2. To read a supplied source against a quotation or claim, `python3 ${CLAUDE_SKILL_DIR}/scripts/shared/quote_verify.py <draft> --source LABEL=PATH` checks every quotation of four or more words against the source text (`verified`, `not-found`, `no-source-supplied`, `uncited`); it supports "text checked" only. Give every list entry one status word, and no other wording, for what was actually done in this run:
   - **not checked:** the default. Nothing beyond the entry's presence in the list.
   - **identity matched:** the entry's authors, year and title were matched to a record the writer supplied or a source file on disk.
   - **text checked:** the source's text was available and read for the cited passage.
   - **supports:** the passage in the source supports the claim it is cited for (quote both).
   - **partly supports:** it supports only part of the claim (say which part).
   - **contradicts:** the passage says something that conflicts with the claim (quote both).
   A status above "not checked" needs a source file or record the writer supplied in this run, named in the table. Never infer a status from memory, and never mark a source as supporting a claim it was not read for.
3. Report: the status table (entry, status, evidence named), then citations with no entry, entries never cited, and malformed identifiers from the script.

## Rules

- Do not invent missing details (year, page, DOI) and do not state that an entry "looks right".
- No reformatted entries and no replacement wording.
- The Hard rules in SKILL.md apply (no offer, no Next line, no TLDR).

## Limits

- A status above "not checked" needs a source supplied in this run; the status words describe what was done, not how reliable the source is.
