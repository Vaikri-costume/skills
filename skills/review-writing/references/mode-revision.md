# Revision-diff mode (only when the writer names it)

Question answered: did the writer's changes address the earlier feedback? Needs two inputs: the earlier review report (finding blocks with `Current text:` lines) and the revised draft. If the earlier report is missing, ask once for it; never reconstruct it.

## Steps

1. `python3 ${CLAUDE_SKILL_DIR}/scripts/revision_diff.py <earlier report> <revised draft>` locates each earlier quote (`unchanged`, `reworded`, `absent`) and its new paragraph. The script locates text only; it never decides whether a comment was addressed.
2. Read the earlier concern for each finding and the revised passage in full. Judge one status per earlier finding:
   - **addressed:** the concern no longer applies to the revised text, and you can say which words did it;
   - **partly addressed:** something changed that bears on the concern but the concern still holds in part; say which part;
   - **unchanged:** the concern still applies as written (including a passage the script marks `unchanged`, unless the surrounding text now answers it);
   - **introduced a new problem:** the change creates a different problem; describe it with a quote;
   - **no longer applies:** the passage was cut, or the claim it concerned is gone; say what replaced it.
3. Run one fresh pass over the revised passages the writer changed for problems the earlier report did not raise; list them separately as "new in the revision", each with a quote.

## Rules

- Split each earlier concern into its parts before judging (for example "no figure" and "no source" are two parts). "Addressed" needs every part met in the revised text; if one part is met and another is not, the status is "partly addressed" and the reason names the part still open.
- Judge a passage in its new context. A sentence left word for word can be addressed because the revision added grounds beside it; a reworded sentence can still carry the same problem. Say which, with the words that decide it.
- No rubber-stamping. "Addressed" needs a quoted revised line and the reason it meets the earlier concern. A reworded sentence that keeps the same problem is unchanged.
- Quote the earlier concern's wording and the revised line side by side for each finding. No new advice on how to fix an unchanged item; restate the earlier concern.
- The report is a table in the earlier report's finding order (finding number, earlier concern, status, revised quote, reason), then the "new in the revision" list. No score, no overall verdict word, no TLDR, no closing offer.
- Never rewrite the passage.

## Limits

- `revision_diff.py` only locates text; whether a comment was addressed is the reviewer's reading, never the script's.
