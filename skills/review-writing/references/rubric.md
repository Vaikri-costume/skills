# When the writer supplies a rubric or brief

Applies to the full review, presentation mode and draft mode.

## Verdict table

After the report's main sections, add a table in the rubric's own order and its own words (copy each criterion's wording unchanged). Columns: Criterion | Verdict | Quoted line.

| Verdict | Use when |
|---|---|
| met | the draft does what the criterion says; the quoted line is where |
| partly | something in the draft addresses it but not all of it; quote it and say which part is missing |
| not met | the draft addresses it and falls short of the criterion; quote it and say how |
| not found in the draft | nothing in the draft addresses it; leave the quote cell as a dash |

A missing requirement is "not found in the draft", never "partly" or "not met". Every verdict other than "not found in the draft" carries a quote taken from the draft.

Check the table before relaying it: `python3 ${CLAUDE_SKILL_DIR}/scripts/verdict_table.py <rubric file> <report file> --draft <draft>`. Fix every problem it lists. (Save the table to a file under `$RUN` for the check.)

## Also noticed

Points the review found that no rubric criterion covers go in a separate list headed "Also noticed (my view, not from the rubric)". They are the reviewer's own view and are never merged into the table. The same quote and no-rewrite rules apply.

## What the table never does

No overall mark, no ranking of criteria, no "top changes" list that supplies content, no prediction of a grade.
