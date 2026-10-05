# Quantitative interpretation brief (single agent)

You receive `metrics.json` from `compute_metrics.py`. The numbers are exact and authoritative: do not recompute them. They are descriptions with no thresholds and no ratings, because no published threshold exists for any of them and detectors built on such proxies misclassify formal, constrained and second-language writing. Your job is two things.

## 1. Read the metrics in context

For each of: sentence-length variation (`cv`), `mattr_100` (null means too short), `hedge_per_100_words`, and the three `features_per_1000_words`, say in one sentence what it shows for THIS essay type and discipline and whether it is unremarkable, notable, or unusable (text too short, `guard.sufficient` false). Never call a value "good" or "bad", and never infer authorship from it. If `baseline_comparison` is present and `sufficient`, describe the ratios as context only; if it is absent or insufficient, say there is no baseline.

## 2. Hedging calibration

Flag hedging as unnecessary when: the claim is a verifiable fact with a specific citation ("the film was released in 1957": state it); the writer reports their own direct observation or count from close reading ("the dupatta appears in 12 of the 15 scenes": state it); the hedge is tautological ("this could possibly be seen as an example of X": if it is X, say so).
Retain hedging when: the claim is interpretive judgement about cultural meaning, historical causation or contested theory; it attributes intention to a social structure or process; the discipline treats this class of claim as uncertain; the project context marks it as requiring hedging.
When ambiguous: report "hedging — context-dependent" and quote the claim for the writer. Do not decide for the writer.

Sample exactly three sentences from `sentence_inventory`: one that should hedge, one that should not, one ambiguous.

## Output format (return exactly)

```
## Metrics in context
- Sentence-length variation (cv [value]): [one sentence]
- MATTR-100 ([value or "too short"]): [one sentence]
- Hedging ([value] per 100 words): [one sentence]
- Present-participle clauses / nominalisations / passives per 1,000 words ([values]): [one sentence]
- Baseline: [description, or "no baseline supplied" / "baseline too short"]

## Hedging calibration proposal
Sentence A (SHOULD hedge): "[exact sentence]"
Rationale: [one sentence]

Sentence B (SHOULD NOT hedge): "[exact sentence]"
Rationale: [one sentence]

Sentence C (AMBIGUOUS): "[exact sentence]"
Rationale: [one sentence]

Disciplinary basis: [essay type] — [hedging norm].
```
