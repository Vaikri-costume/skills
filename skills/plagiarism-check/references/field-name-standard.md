# Field-name standard

Location correction and verdict synthesis match findings by exact field names. `correct_finding_locations.py` relies on `Current text: "…"` as the quoted draft passage. Change a field name in a brief only together with this file and the scripts.

## Source judgement agent (one per source)

The finding block, its option lists and the `## No findings` / `## Cleared matches` trailer are defined once, in `source-judgement.md` (Output format). Scripts match on `Current text: "…"` as the quoted draft passage and on the Finding number. The source is set by the orchestrator when it dispatches the agent (`PlagSource-<slug>-<run>`), not reported by the agent.

## Challenger (one agent)

```
## Challenger assessment: Finding [n]
Source: [slug]
Quote: "[exact text as reported by the judgement agent]"
Source check: [found / not found in the source text: quote the line, or say not found]
[Reasoning paragraph]
Verdict: UPHELD / DISPUTED: reason / AMBIGUOUS: question / NOT ASSESSED: reason
```
Match criterion for verdict synthesis: the Finding number. Labels: upheld, disputed, ambiguous, unaddressed (`synthesise_verdicts.py --single`).

## Deterministic outputs (JSON, no agent)

`overlap.json` (overlap_check.py), `audit.json` (citation_audit.py), `quotes.json` (quote_verify.py); reference-check mode adds `entries.json`, `records.json`, `verdicts.json` (reference_check.py). The presenter renders them; an agent never re-judges them.
