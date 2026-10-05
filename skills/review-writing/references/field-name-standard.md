# Field-name standard — review-writing

Synthesis and location correction match findings by exact field names. The quoted draft passage is always `Current text: "…"`. Rename a field only together with this file, the briefs and the scripts.

## Argument agents (A/B pair)
`## Reading of the draft` (central claim, aim) then findings:
```
## Finding [n]
Location: paragraph [n] — "[opening words]"
Current text: "[sentence carrying the claim or move]"
Element: claim / grounds / warrant / backing / qualifier / rebuttal / sub-claim
Concern: [one sentence]
Severity: High / Medium / Low
```
Pair match: `--exact Element --substring "Current text"`.

## Clarity agents (A/B pair)
```
## Finding [n]
Location: paragraph [n] — "[opening words of the sentence]"
Current text: "[exact text]"
Sub-category: passive voice / compound sentence / unclear pronoun / jargon / sentence position
Concern: [one sentence]
Severity: High / Medium / Low
```
Pair match: `--exact Sub-category --substring "Current text"`.

## Evidence agents (A/B pair)
```
## Finding [n]
Location: paragraph [n] — "[opening words of the passage]"
Current text: "[exact quote]"
Concern: [one sentence]
Severity: High / Medium / Low
```
Pair match: `--substring "Current text"` (include quote-integration findings; name the sub-type in Concern).

## Voice agents (A/B pair)
```
## Finding [n]
Location: paragraph [n] — "[opening words of the passage]"
Current text: "[exact quote]"
Pattern: [one sentence]
Concern: [what the writer's own perspective might be]
Severity: High / Medium / Low
```
Pair match: `--substring "Current text"`.

All agents end with `## Strengths` (at least 2, each a quoted passage plus the move it makes) or `## No findings`.

## Challenger (A/B pair)
```
## Challenger assessment: Finding [n]
Domain: Argument structure / Clarity / Evidence / Voice / Cross-domain (merged)
Analysis confidence: HIGH / UNVERIFIED
Quote: "[exact text as reported by primary agent]"
[Reasoning paragraph]
Verdict: UPHELD / DISPUTED: reason / AMBIGUOUS: question
```
Synthesis: `synthesise_verdicts.py` (match by finding number).
