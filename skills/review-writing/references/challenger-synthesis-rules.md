# Challenger synthesis rules — review-writing

After both ReviewChallenger-A and ReviewChallenger-B return, run `python3 ${CLAUDE_SKILL_DIR}/scripts/shared/synthesise_verdicts.py A.md B.md --findings N`. The script implements the table below (matching by finding number); this file is its specification, and tests in `${CLAUDE_SKILL_DIR}/scripts/shared/tests/` cover it.

## Match criterion

Match by finding number — the executor numbered findings sequentially in the combined list from SKILL.md Run step 4, and challengers reference each by `## Challenger assessment: Finding [n]`.

## Three orthogonal confidence axes (preserve all three per finding)

Each finding entry in the verdict list carries three independent labels:

1. **Analysis confidence** (set by pair synthesis in SKILL.md Run step 4): `HIGH` (both primary agents flagged this finding) or `UNVERIFIED` (one primary agent flagged it, the other didn't).
2. **Challenger verdict confidence** (set by this synthesis): see verdict labels below.
3. **Domain**: `Argument structure` / `Clarity` / `Evidence` / `Voice` / `Cross-domain (merged)` (the primary-pair classification carries forward).

These axes are independent. A finding can be `(UNVERIFIED analysis, confirmed verdict, Evidence domain)` — only one primary agent flagged it, but both challengers upheld it as a real issue. That's a partial-strength finding worth surfacing, not a weak one.

## Verdict synthesis (the nine values)

For each finding, both challengers should return one of: `UPHELD`, `DISPUTED: reason`, `AMBIGUOUS: question`, or `NOT ASSESSED — reason`.

Apply this table:

| Challenger A returned | Challenger B returned | Verdict label |
|---|---|---|
| UPHELD | UPHELD | **confirmed** |
| DISPUTED | DISPUTED | **confirmed-disputed** |
| UPHELD | DISPUTED (or vice versa) | **split** |
| AMBIGUOUS | AMBIGUOUS | **ambiguous** |
| UPHELD | AMBIGUOUS (or vice versa) | **partial-ambiguous** (lean toward upheld in presentation) |
| DISPUTED | AMBIGUOUS (or vice versa) | **partial-ambiguous** (lean toward disputed in presentation) |
| UPHELD | NOT ASSESSED | **partial-upheld** |
| DISPUTED | NOT ASSESSED | **partial-disputed** |
| NOT ASSESSED | NOT ASSESSED | **partial-unaddressed** |
| One challenger failed | UPHELD/DISPUTED/AMBIGUOUS | **partial-{verdict}** prefix |
| Both challengers failed | n/a | **unverified-challenger** for every finding |

## Storage format

Keep all verdicts as the verdict list (the input to SKILL.md Run step 6), one entry per finding number, with all three axes:

```
Finding 1: domain=Argument structure, analysis=HIGH, verdict=confirmed
Finding 2: domain=Clarity, analysis=UNVERIFIED, verdict=split
Finding 3: domain=Evidence, analysis=HIGH, verdict=ambiguous
Finding 4: domain=Cross-domain (merged), analysis=HIGH, verdict=confirmed
```

Pass this verbatim to the presentation agent (dispatch-protocol.md, Presentation).

## Coverage table bucket mapping (used by the presentation agent)

The presentation coverage table aggregates the nine verdict values into four buckets:

- **upheld**: confirmed + partial-upheld
- **disputed**: confirmed-disputed + partial-disputed
- **needs your decision**: split + ambiguous + partial-ambiguous + partial-unaddressed
- **unverified-challenger**: unverified-challenger only (NOT analysis-UNVERIFIED)

## NOT_ASSESSED handling

The challenger prompt (SKILL.md Run step 5; dispatch-protocol.md, Challenger) instructs `NOT ASSESSED` as the answer when a challenger truly can't evaluate a finding. It's not a failure — it's a deliberate "I can't tell." Synthesis treats it like a per-finding agent failure, not as silent absence.

Synthesis rules for `NOT ASSESSED`:
- Both challengers return NOT_ASSESSED → verdict = **partial-unaddressed**, falls into the "needs your decision" bucket.
- One challenger returns NOT_ASSESSED, the other returns UPHELD/DISPUTED/AMBIGUOUS → treat the NOT_ASSESSED challenger as a per-finding failure; surviving challenger's verdict becomes the synthesis verdict with `partial-` prefix.

This keeps NOT_ASSESSED visible as actionable to the writer, rather than silently dropping the finding.
