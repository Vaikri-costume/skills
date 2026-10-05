# Field-name standard — ai-detection-check

Synthesis and location correction match findings by exact field names. The quoted draft passage is always `Current text: "…"` (the location script's regex is literal). Rename a field only together with this file, the scripts and the briefs.

## Quantitative interpretation agent (single)

Numbers come from `scripts/compute_metrics.py` and are authoritative. Output sections: `## Metrics in context`, `## Hedging calibration proposal` (three sentences A/B/C with labels SHOULD hedge / SHOULD NOT hedge / AMBIGUOUS). No findings, no ratings. The writer confirms the three labels (one AskUserQuestion) before they go to the challenger as anchors.

## Pattern agents (A/B pair)

```
## Finding [n]
Location: paragraph [n], sentence [m], [opening words]
Current text: "[exact verbatim quote from draft]"
Pattern: [pattern number and name from base.md]
Type: exact match / semantic equivalent
Severity: RED / YELLOW / GREEN
Explanation: [one sentence — what the pattern is doing here and why it matters]
```
After the findings: `## Pattern coverage` (count per pattern). Pair match: `--exact Pattern --substring "Current text"`.

## Voice and texture agents (A/B pair)

```
## Finding [n]
Location: paragraph [n], sentence [m], [opening words]
Current text: "[exact verbatim quote from draft]"
Issue: smooth texture / missing imperfection / preemptively safe language
Severity: RED / YELLOW / GREEN
Explanation: [one sentence]
```
Pair match: `--exact Issue --substring "Current text"`.

## Cross merge (pattern + voice)

A pattern finding and a voice finding whose `Current text` is identical or a substring of the other merge into one entry of type `Pattern+Voice`, higher severity, placed under Pattern, with the note "independently flagged by both pattern and voice agents — stronger signal". The orchestrator does this by comparing normalised `Current text` after pair synthesis.

## Challenger (A/B pair)

```
## Challenger assessment: Finding [n]
Type: Pattern / Voice & texture / Pattern+Voice
Analysis confidence: HIGH / UNVERIFIED
Current text: "[exact quote as reported by primary agent]"
[Reasoning paragraph]
Verdict: UPHELD / DISPUTED: reason / AMBIGUOUS: question
```
Synthesis: `synthesise_verdicts.py` (match by finding number).

## Deterministic outputs (no agent)

`metrics.json`, `patterns.json`, `audit.json`, `quotes.json`. Rendered by the presentation agent, never re-judged.
