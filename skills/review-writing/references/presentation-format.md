# Presentation format - review-writing

The presentation agent's response IS the report. Every section and finding appears in full; no summary, no truncation, no TLDR, no cap on the number of findings or sentences. Pass `Location:` through verbatim. Omit sections with no content, except Coverage.

The report follows the feedback model of Hattie and Timperley (2007): where the writing is going (feed up), how it is going (feed back), where to next (feed forward). It comments on the writing, never on the writer, uses "the writer" or "they", and writes no replacement wording.

## Skeleton

```
[HEADER from assets/report-header-template.md, including the confidence line]

### Where this draft is going
[From the argument agents' "Reading of the draft": the central claim as read, quoted, and what the draft seems to be trying to do. If the two agents' readings differ, show both: that difference is itself a finding about clarity of claim. Then the promise-versus-delivery result: each promise the opening makes and the quoted line that delivers it, or "not found in the draft".]

### Where it needs work
Order by layer, then by consequence within a layer: **Foundation** (claim and question), **Structure** (order, sections, evidence plan), **Paragraph**, **Sentence**. Within a layer: upheld findings with analysis HIGH and Severity High first, then Medium, then Low; confirmed before partial-upheld. Per finding: Para, Current text (<=80 chars), Domain, Analysis confidence, Challenger verdict, Severity, Concern, and for High findings "Would change if". After each layer's findings, a **Working nearby** line: a strength from the agents' Strengths sections that sits in or next to the same passage, quoted, with the move it makes, so the writer sees what to keep while revising. A strength shown here is not repeated below.

### What is working
[Remaining strengths not already placed under a layer: distinct passages. Format: > "[quote]" - [Domain]: [why this works].]

### Questions from three readers
[Only if the Lens pass ran. Three columns or three short lists: audience, rigour, premise; each question with its quoted line. Disagreements between lenses are shown side by side and left unreconciled. Withdrawn questions listed with where the draft answers them.]

### Rubric table
[Only if a rubric or brief was supplied: the verdict table and "Also noticed" list per `rubric.md`.]

### Where to next
[Process questions for the revision, each naming the finding numbers it concerns and asking the writer something they can answer from their own material ("Which sentence states the warrant that links paragraphs 3 and 4?"). Derived only from upheld findings. No new criticism, no supplied wording, claim, source or structure, no cap on how many, no closing offer.]

### Needs your decision
[split + ambiguous + partial-ambiguous + partial-unaddressed; both verdicts or the challenger's question verbatim.]

### Disputed (for reference)
[confirmed-disputed + partial-disputed: `[Domain] para [n]: "[quote excerpt]" - disputed because [reason]`.]

### Unverified findings
[analysis UNVERIFIED with a confirmed challenger, grouped by domain; and any `[UNVERIFIED-CHALLENGER]` findings.]

### Coverage
Bucket mapping: upheld = confirmed + partial-upheld; disputed = confirmed-disputed + partial-disputed; needs your decision = split + ambiguous + partial-ambiguous + partial-unaddressed; unverified-challenger.
Argument structure: [n] upheld (HIGH [n], UNVERIFIED [n]) | [n] disputed | [n] needs your decision | [n] unverified-challenger
Evidence / Clarity / Voice: (same)
Cross-domain (merged): [n] entries
Total findings: [n] upheld | [n] disputed | [n] needs your decision | [n] unverified-challenger

[AI-use line, only where the gate says the writer must reference AI use:]
AI use: Claude reviewed the draft's argument, evidence, clarity and voice and returned feedback only; it generated no text for the work.
```

## Other modes

Draft, revision-diff, presentation and bibliography modes use the shapes in their own `mode-*.md` files, not this skeleton, with the same rules: quoted evidence for every point, no wording supplied, no TLDR, no grades, no closing offer.

## Before relaying

Save the report to `$RUN/report.md` and run `python3 ${CLAUDE_SKILL_DIR}/scripts/report_lint.py $RUN/report.md`; fix each problem it lists, then relay the report verbatim.
