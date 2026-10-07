# Field-name standard — plagiarism-check

Synthesis and location correction match findings by exact field names. The location-correction script (`${CLAUDE_SKILL_DIR}/scripts/shared/correct_finding_locations.py`) relies on `Current text: "…"` as the quoted draft passage. Change a field name in a brief only together with this file and the scripts.

## Source judgement agent (one per source)

```
## Finding [n]
Location: paragraph [n] — "[opening words of the passage]"
Current text: "[exact verbatim quote from draft]"
Check: [1 / 2 / 3 / 5]
Source passage: "[relevant passage from this source]"
Category: [verbatim without reference / close paraphrase / unacknowledged quotation or paraphrase / citation practice]
Weight: [poor-academic-practice / minor / major]
Severity: RED / YELLOW / GREEN
Explanation: [one sentence]
```
followed by `## Cleared matches` (one line per judged-clear overlap match) or `## No findings`.

The source is set by the orchestrator when it dispatches the agent (`PlagSource-<slug>-<run>`), not reported by the agent. There is no A/B pair: confidence comes from the challenger's verification, not from agreement between two copies of the same model.

## Challenger (one agent)

```
## Challenger assessment: Finding [n]
Source: [slug]
Quote: "[exact text as reported by the judgement agent]"
Source check: [found / not found in the source text — quote the line, or say not found]
[Reasoning paragraph]
Verdict: UPHELD / DISPUTED: reason / AMBIGUOUS: question / NOT ASSESSED — reason
```
Match criterion for verdict synthesis: same Finding number. Labels: upheld, disputed, ambiguous, unaddressed (`synthesise_verdicts.py --single`).

## Deterministic outputs (JSON, no agent)

`overlap.json` (overlap_check.py), `audit.json` (citation_audit.py), `quotes.json` (quote_verify.py). The presentation agent renders them; they are never re-judged by an agent.
