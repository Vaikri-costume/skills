# Authenticity evidence and policy context

Read by the presentation agent for the limits, the machine-checkable indicators and the "Evidence you can show" sections. Background on detectors, dated and labelled: `references/detector-landscape.md` (last reviewed 2026-11-12). The writer's own institution and course rules are never assumed: they come from the profile (`references/profile.md`).

## Why the report is framed as it is

- No detector proves authorship. Independent tests find non-zero false positives and a sharp fall in detection after paraphrasing or "humanising"; vendors themselves say a score is not sole evidence.
- Plain, formulaic, formal and second-language writing is flagged more often, because it is more predictable. The best-known study (2023, older detectors) found high false-positive rates on second-language essays; newer vendor claims have not been independently confirmed for that group.
- A tool score can look precise without the validation behind it. This skill therefore reports no percentage, likelihood or verdict, and does not imitate a detector.
- In UK practice, complaint bodies have upheld cases where a detector flag was used without showing the student the evidence or considering whether the tool is less reliable for some writers. Institutional misconduct procedures generally name human-judgement indicators (below), not a score, and often invite the writer to a meeting with notes, drafts and readings.

## Indicators a script can check (verifiable, independent of any detector)

| Indicator (typical procedure wording, paraphrased) | Check |
|---|---|
| quotations that do not exist or are not in the cited source | `quote_verify.py` |
| bibliography entries not cited in the text | `citation_audit.py` → `uncited_bibliography` |
| repetition: authors introduced repeatedly, repeated bibliography entries | `citation_audit.py` → `author_reintroductions`, `duplicate_bibliography` |
| context of quotations and sources cannot be verified | `quote_verify.py` → `no-source-supplied` |
| vagueness on topics covered in class; not answering the question | human judgement; the skill cannot check |

Machine-written references also carry artefacts: `utm_` parameters, invalid ISBN checksums, malformed DOIs and placeholder markers. They are reported under `artefacts`. A reference that cannot be found is reported as not found, never replaced or repaired.

## What flagging systems tend to react to (describe, never instruct)

Systems that score text look for predictable word choice and even sentence rhythm, stock phrases and over-regular structure. Honest writing can show the same features: a short or plain style, a formal register, careful second-language prose, a heavily edited draft, or a text shaped by a grammar checker. The report may say that a feature of this draft is of the kind such systems react to, and that its presence says nothing about how the text was written. It never advises how to change the draft in order to lower a flag, never recommends a tool to rewrite or "humanise" text, and never treats the absence of a flag as a clean result.

## Evidence you can show (the one defence that does not depend on a classifier)

Offered, never required: dated drafts or version history; reading notes and annotations with dates; the source trail (library entries, highlights, saved copies); outline iterations; notes on why the topic or argument was chosen; the reading list with what was actually read; and a record of any AI use and what for, in the form the institution asks. Keeping these is good practice whatever any tool says, and they are what an informal meeting about a concern usually asks for.

## Rules for the report

1. Never present a metric, pattern or smoothness flag as evidence of machine authorship, and never state or imply that the text is or is not machine-written.
2. Never advise how to lower a score, avoid detection or humanise text. If asked: this check finds places where specific thinking may be missing, honest AI assistance is declared and not disguised, and the evidence of the writer's own process is what helps.
3. Never give a percentage, likelihood or grade of machine authorship, even if asked; say why a number would mislead.
4. State when the writer's profile (formal academic register, second-language writing, a plain short-sentence style) raises false-positive risk elsewhere. Never infer the writer's background; ask only if the run needs it.
5. Say what is unknown: whether the institution runs a detector, and what it would report.
