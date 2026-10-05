# Challenger rules — plagiarism-check (single verifying challenger)

One challenger sees every finding. For each finding it must do the verification the judgement agent cannot be trusted to do alone:

1. Find the quoted draft text in the draft (a finding whose quote is not in the draft is marked `[QUOTE-UNMATCHED]` by the location script: return DISPUTED: quote not found in draft).
2. Find the cited `Source passage` in the source text. If it is not there: DISPUTED: passage not in source.
3. Re-apply the check's conditions to the two passages side by side.
4. Apply the essay-type scope: a research essay engaging a foundational source closely may mirror its structure legitimately; a field-standard phrase is not overlap; a cited and marked quotation is not plagiarism.

State reasoning first, verdict last, the label exactly once. Do not infer norms from adjacent fields; if the draft or source is silent, return AMBIGUOUS with a specific question.

Run `synthesise_verdicts.py CHALLENGER.md --single --findings N`. Labels: **upheld** (confirmed), **disputed**, **ambiguous** (needs the writer), **unaddressed** (no verdict returned). Findings never disappear: disputed ones go to a "Disputed (for reference)" section with the reason.

Reasoning from the same model family shares its blind spots. Treat `upheld` as "verified against the texts", not as certainty, and keep the writer's judgement final.
