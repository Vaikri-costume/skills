# Presentation format — ai-detection-check

The presentation agent's response IS the report. Every section and finding appears in full; no summary, no truncation. Pass `Location:` through verbatim. Omit sections with no content, except Coverage and the closing blocks.

## Axes — keep separate

Each finding shows: analysis confidence (HIGH = both agents of the pair flagged it, UNVERIFIED = one did), challenger verdict label (nine values in `challenger-synthesis-rules.md`), and type (Pattern / Voice & texture / Pattern+Voice). `[UNVERIFIED-CHALLENGER]` is only for the verdict label `unverified-challenger`.

## Skeleton

```
[HEADER from assets/report-header-template.md]

**Read this first.** A flag means this language may have replaced sharper, more specific writing. It is not evidence that the text was machine-written, and no tool, including this one, can show that. Formal academic prose and second-language writing are flagged by detectors more often than other writing.

---
### Descriptive metrics
[From metrics.json and the quantitative agent's "Metrics in context": the numbers, one plain sentence each, NO colours or ratings. If baseline_comparison is sufficient, show draft vs baseline per feature as context. If the text is under the minimum length, say the feature rates are unreliable.]

### Hedging calibration
[The three confirmed anchor sentences and labels, and every flagged hedge with the calibration applied.]

---
### Citation and quotation integrity   (deterministic: audit.json, quotes.json)
[A checklist, not accusations. Subsections only if non-empty: quotations not found in the cited source; quotations whose source was not supplied (name the authors to supply); citations with no reference-list entry; reference-list entries never cited; repeated reference entries; authors introduced narratively 3+ times; reference artefacts (utm parameters, invalid ISBN checksums, malformed DOIs, placeholder markers). Say these are the machine-checkable items among the human-judgement indicators in typical UK university misconduct procedures and are also ordinary referencing errors.]

---
### Quick wins
[verdict confirmed AND analysis HIGH AND severity RED. One line each: "Para [n]: [description] | [type]".]

### Upheld findings
[confirmed + partial-upheld; HIGH before UNVERIFIED. Per entry: Para, Current text (≤80 chars), Type, Analysis confidence, Challenger verdict, Severity, Concern. For Pattern+Voice add "(independently flagged by both pattern and voice agents — stronger signal)".]

### Needs your decision
[split + ambiguous + partial-ambiguous + partial-unaddressed; show both verdicts or the challenger's question verbatim.]

### Disputed findings
[confirmed-disputed + partial-disputed with the challengers' reasoning.]

### Unverified findings (no challenger adjudication)
[unverified-challenger only, labelled [UNVERIFIED-CHALLENGER].]

### By location  /  By type
[Upheld findings grouped by paragraph, then by type (Pattern → Voice & texture; RED → YELLOW → GREEN).]

---
### Evidence you can show
[The checklist from references/authenticity-evidence.md. Offered, not required.]

### What this check cannot tell you
[Four lines from references/authenticity-evidence.md "Rules for the report" 4, plus: whether the institution runs a detector is unknown; honest AI assistance should be declared per the module's rules.]

### Suggested vocabulary register
[10–20 terms from the challenger, comma-separated, plus the path they would be saved to. Omit if empty. Never saved without the writer's say-so.]

### Coverage
Bucket mapping: upheld = confirmed + partial-upheld; disputed = confirmed-disputed + partial-disputed; needs your decision = split + ambiguous + partial-ambiguous + partial-unaddressed; unverified-challenger.
Pattern findings: [n] upheld (HIGH [n], UNVERIFIED [n]) | [n] disputed | [n] needs your decision | [n] unverified-challenger
Voice & texture findings: (same)
Citation and quotation integrity items: [n]
Total findings: [n] upheld | [n] disputed | [n] needs your decision | [n] unverified-challenger
```

Never advise how to lower a score or avoid detection.
