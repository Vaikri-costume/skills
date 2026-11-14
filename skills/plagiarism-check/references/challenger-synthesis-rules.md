# Challenger rules (single verifying challenger)

One challenger sees every finding and does the verification the judgement agent cannot be trusted to do alone:

1. Find the quoted draft text in the draft. A finding marked `[QUOTE-UNMATCHED]` by the location script: return DISPUTED: quote not found in draft.
2. Find the cited `Source passage` in the source text. If it is not there: DISPUTED: passage not in source.
3. Re-apply the check's conditions and the status ladder (`acceptable-use.md`) to the two passages side by side.
4. Apply the essay-type scope: a research essay engaging a foundational source closely may mirror its structure legitimately; field-standard phrases and cited, marked quotations are not plagiarism.

State reasoning first, verdict last, the label exactly once. Never import norms from a field the draft does not represent; if the draft or source is silent, return AMBIGUOUS with a specific question.

Hold a position: change a verdict only for a reason quoted from the draft or the source, and say which. A confident tone, the writer's stated intent or the finding's own phrasing is not a reason. DISPUTED names the quoted line that answers the finding; UPHELD names the quoted line that shows the overlap.

Run `synthesise_verdicts.py Challenger.md --single --findings N`. Labels: **upheld**, **disputed**, **ambiguous** (needs the writer), **unaddressed** (no verdict returned). Findings never disappear: disputed ones go to a "Disputed (for reference)" section with the reason. Reasoning from the same model family shares its blind spots, so `upheld` means "checked against the texts", not certainty; the writer's judgement stays final.
