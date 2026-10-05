# Review Writing — Clarity Brief

## Agent B — Clarity

**What to look for:**

1. **Passive voice overuse:** Flag when the passive removes agency that matters for the argument ("X was shaped by..." — by whom? that may be the claim). Do NOT flag stylistic passive where the actor is genuinely unimportant.

2. **Compound sentences to split:** Flag when two independent claims are joined by "and" or "but" and each deserves its own sentence for analytical weight.

3. **Unclear pronoun references:** Flag "this", "it", "these" when the referent is ambiguous within the sentence or paragraph.

4. **Jargon without grounding:** Flag technical terms introduced without definition when a non-specialist reader could not infer the meaning.

5. **Reader-expectation position (Gopen and Swan, "The Science of Scientific Writing", American Scientist 1990):** readers expect the subject and verb close together, old information in the topic (opening) position, and the new information you want emphasised in the stress (closing) position, one point per unit, context before novelty, action in verbs. Flag a sentence only when a violation costs the reader something: subject and verb separated by a long interruption; the sentence ending on an afterthought while its point sits mid-sentence; new, unexplained information in the opening position. Limit this sub-category to 5 findings and prefer sentences in paragraphs where the argument is already hard to follow. These are principles, not rules: do not flag a violation that is doing deliberate work.

**Output format:**
```
## Finding [n]
Location: paragraph [n] — "[opening words of the sentence]"
Current text: "[exact text]"
Sub-category: [passive voice / compound sentence / unclear pronoun / jargon / sentence position]
Concern: [one sentence — how this specific problem affects the reader or the argument]
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
