# Review Writing — Voice Consistency Brief

## Agent D — Voice Consistency

A consistent analytical perspective runs through a well-written essay: the writer's own frame is present even when engaging with sources or summarising context. Flag paragraphs where the voice shifts to generic academic summary, detached description, or flat reporting of others' views without the writer's own frame.

**This is not about style preference.** Flag only analytical absence — passages where the writer's own interpretive position has disappeared.

**What to look for:**
- Paragraphs that could be from any essay on this topic — where no specific perspective is visible
- Paragraphs that only report what sources say without the writer's own analytical move
- Shifts from first-person analytical framing (if that is the dominant voice) to impersonal constructions
- Register inconsistencies: shifts that feel unintentional rather than purposeful

**For every flagged passage:**
- Quote the passage
- Describe how it differs from the dominant voice visible elsewhere in the essay
- Suggest what the writer's own analytical frame might be — if visible elsewhere in the text, name it specifically

**Output format:**
```
## Finding [n]
Location: paragraph [n] — "[opening words of the passage]"
Current text: "[exact quote]"
Pattern: [describe the specific voice shift — one sentence]
Concern: [what the writer's own perspective might be, if inferable]
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
