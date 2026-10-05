# Field-name standard — proofread

This file is the canonical source for field names used in agent outputs and synthesis matching. Synthesis (`${CLAUDE_SKILL_DIR}/scripts/shared/synthesise_pairs.py`, `synthesise_verdicts.py`) matches findings by exact field names; if a brief is updated and a field name changes, synthesis fails silently — findings become UNVERIFIED or unmatched without any error. Both brief files (`references/surface.md`, `references/consistency.md`, `references/register-research.md`, `references/register-personal.md`) and SKILL.md synthesis logic must conform to the field names here.

## Surface agents (Checks 1–3 + Unrecognised terms)

Per-finding fields (in this order):

```
## Finding [n]
Location: paragraph [n], sentence [m] of the paragraph, [opening words of the sentence]
Current text: "[exact text as it appears in the draft]"
Proposed fix: "[corrected text]"
Check: [1 / 2 / 3]
Severity: High / Medium / Low
```

Match criterion (within the surface pair, A vs B): same `Check:` value AND `Current text:` quoted is identical or one is a substring of the other.

Unrecognised terms section (separate from findings):

```
## Unrecognised terms
[one term per line, or "None identified"]
```

## Consistency agents (Check 4)

Per-finding fields (in this order):

```
## Finding [n]
Location: paragraph [n], sentence [m] of the paragraph, [opening words of the sentence]
Current text: "[exact text as it appears in the draft]"
Pattern: [observation — the inconsistency observed across the draft]
Concern: [why the inconsistency matters]
Check: 4
Severity: High / Medium / Low
```

No `Proposed fix:` field — Check 4 findings are diagnostic, not prescriptive. The challenger or writer determines the correction.

Match criterion (within the consistency pair, A vs B): `Check: 4` AND `Current text:` quoted is identical or one is a substring of the other.

## Register agents (Check 5)

Per-finding fields (in this order):

```
## Finding [n]
Location: paragraph [n], sentence [m] of the paragraph, [opening words of the sentence]
Current text: "[exact text as it appears in the draft]"
Pattern: [observation — the register shift or quality issue observed]
Concern: [why the shift matters]
Check: 5
Severity: High / Medium / Low
```

No `Proposed fix:` field — Check 5 findings are diagnostic.

Match criterion (within the register pair, A vs B): `Check: 5` AND `Current text:` quoted is identical or one is a substring of the other.

## Challenger agents

Per-finding output:

```
## Challenger assessment: Finding [n]
Agent confidence: [HIGH / UNVERIFIED] | Check: [1–5]
Current text: "[exact quote as reported by primary agents]"
[Reasoning paragraph]
Verdict: [UPHELD / DISPUTED: reason / AMBIGUOUS: question]
```

Match criterion (synthesis across A and B challengers): same Finding number.

## Why field names are versioned here

A change to a brief that renames `Current text:` to `Source text:` in surface findings, but leaves the SKILL.md synthesis matching unchanged, would silently produce all UNVERIFIED outputs — every surface finding would fail to match its pair because the executor looks for `Current text:` and the agents now emit `Source text:`. The skill would still run, still produce a report, but the synthesis layer would be quietly broken. Treating field names as a contract — updated in this file whenever a brief changes — makes the link explicit.
