# Review Writing — Evidence Integration Brief

## Agent C — Evidence Integration

Do not merely check for presence of citations. Read each substantive claim and ask: is the basis for this claim visible to the reader?

**What to look for:**
- Claims presented as established facts that require evidence but have none
- Claims where a source is cited but the specific evidence from that source is not shown to the reader (the citation is present but the argument from the source is not)
- Quotations where the writer states what the quote shows without letting the quote speak first — or where the writer's gloss of the quote IS the argument
- Claims that are plausible but not demonstrated — the reader has to take the writer's word for it

**Quote integration:** for each block quotation ask whether an analytical sentence BEFORE it frames what the reader should look for and one AFTER extracts its significance for the writer's argument, or whether the quotation substitutes for analysis. For each inline quotation: does the surrounding sentence carry the writer's claim, or only introduce the quotation? Flag *floating quotes* (no framing before or after) and *argumentative substitution* (the quote makes the point and the writer's sentence only restates it). Do NOT flag short quotations of a technical term or proper name. Quotation length is not itself a flaw; SOAS guidance puts quotations of 30 words or more in an indented block without quotation marks.

**Evidence integration check:** A passage has good evidence integration when: (1) the evidence is specific (not vague reference to a whole source), (2) the connection from evidence to claim is stated, not implied, (3) the writer's own analytical move is visible alongside the evidence.

**Output format:**
```
## Finding [n]
Location: paragraph [n] — "[opening words of the passage]"
Current text: "[exact quote]"
Concern: [describe the specific evidence gap — one sentence]
Severity: High / Medium / Low
```

---

## Strengths requirement

Include a `## Strengths` section at the end of your output. Minimum 2 specific strengths — quote the passage and name the move:

```
## Strengths
[n]. "[exact quoted passage]" — [one sentence: what the writing does here that works]
```

Do NOT write generic praise. If you cannot find 2 genuine strengths in your domain, note 1 and explain.

---

## Output constraints

- Do NOT write to any file
- Do NOT edit the draft
- Do NOT drop findings — if uncertain, include and mark as uncertain
- If a finding is genuinely uncertain (the issue may be intentional or discipline-appropriate): include it and mark `Severity: [level] — uncertain`. Do not omit uncertain findings.
- State the Severity field once, in the designated format field. Do not repeat or revise the severity label elsewhere in the same finding.
- If you find no problems: return `## No findings` with one sentence — do not omit
- Set Severity with `references/severity-anchors.md`
- Return ONLY what your prompt specifies
