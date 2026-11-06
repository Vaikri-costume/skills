# Presentation mode: gaps only (only when the writer names it)

For a talk the writer is preparing, supplied as slides, speaker notes or a transcript of their own rehearsal. It names gaps and asks questions. It writes no slide text, script, speaker note, opening, take-home or backup slide, and offers no replacement wording. It does not coach delivery from audio or video.

Run the gate in `profile.md` first: on coursework, presentation mode needs a rule that clearly allows feedback on a presentation.

## Inputs to get (ask once, only for what is missing)

The slides, notes or transcript; the time allowed; the audience; the brief and any marking criteria. Never ask for what can be found on disk.

## Steps

1. `python3 ${CLAUDE_SKILL_DIR}/scripts/presentation_stats.py <file> --minutes <N>` gives slide count, words per slide, a long-slide list, any reference slide and the pace range. State the speaking-rate range it assumed. Pace applies to notes or a transcript; for slides alone, report only slide count against time and say pace could not be judged.
2. Check each of these, one finding per real gap, each tied to a quoted slide or line (`Slide n` or `Current text:`):
   - **Brief and criteria:** each stated criterion is covered, partly covered or not found in the material (rubric rules in `rubric.md`).
   - **Argument gaps:** a claim with nothing shown for it; two slides whose link is unstated; a conclusion the earlier slides do not reach.
   - **Timing:** the material against the time allowed, from the script's numbers.
   - **One idea per slide:** slides that carry two or more separate points, from the script's long-slide list and your reading.
   - **Take-home:** whether the main point is stated near the start and again near the end, quoted where it is; if not found, say not found.
   - **Bibliography:** whether a references slide exists (from the script), and whether sources named on slides appear on it.
   - **Hard questions:** questions an informed audience member could ask that the material does not prepare for. Put each as a question to the writer ("What would you say if asked ...?"), never with an answer.
   - **Accessibility:** text size cannot be judged from text files; check for colour-only meaning, unreadable abbreviations, undescribed images and walls of text, where the material shows them.
3. Report gaps by slide order, then the hard questions. No severity grades.

## Rules

- Gaps and questions only. If a fix needs content, say what is missing, not what to put there.
- Never state that the talk is good or ready, and give no overall mark.
- The Hard rules in SKILL.md apply (no offer, no Next line, no TLDR).

## Limits

- `presentation_stats.py` counts and does the pace arithmetic; the speaking-rate range (default 120 to 160 words per minute) is an assumption the report states. Text size and visual layout cannot be judged from text files.
