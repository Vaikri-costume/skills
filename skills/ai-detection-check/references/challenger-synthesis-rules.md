# Challenger synthesis rules — ai-detection-check

After both AIChallenger-A and AIChallenger-B return, run `python3 ${CLAUDE_SKILL_DIR}/scripts/shared/synthesise_verdicts.py A.md B.md --findings N`. The script implements the table below (matching by finding number); this file is its specification, and tests in `${CLAUDE_SKILL_DIR}/scripts/shared/tests/` cover it.

## Match criterion

Match findings across both challengers by **finding number** (same Finding [n]) AND by `Current text:` quote (substring match). The challenger receives a numbered list of synthesised findings; both challengers operate on the same numbering, so identity is by number — but the Current text quote check guards against challenger drift.

## Verdict synthesis (the nine values)

| Both A | Both B | Verdict confidence label | Meaning |
|--------|--------|-------------------------|---------|
| UPHELD | UPHELD | **confirmed** | Both challengers agreed this is a real concern |
| DISPUTED | DISPUTED | **confirmed-disputed** | Both challengers agreed this is discipline-standard / context-appropriate |
| UPHELD | DISPUTED | **split** | Challengers disagreed |
| DISPUTED | UPHELD | **split** | Challengers disagreed |
| AMBIGUOUS | (any) | **ambiguous** | At least one challenger could not decide |
| (any) | AMBIGUOUS | **ambiguous** | At least one challenger could not decide |

When **one challenger failed** (no verdict for the finding from that agent): use the surviving challenger's verdict and tag with the `partial-` prefix:
- Surviving says UPHELD → **partial-upheld**
- Surviving says DISPUTED → **partial-disputed**
- Surviving says AMBIGUOUS → **partial-ambiguous**
- Surviving has no verdict for the finding either → **partial-unaddressed**

When **both challengers failed**: tag every finding **unverified-challenger**. Note in the output header: "challenger agents both failed — findings presented without adjudication."

## Three orthogonal confidence axes (read carefully)

ai-detection-check carries THREE independent confidence dimensions per finding. The presentation agent must keep them visible separately:

1. **Analysis confidence** — `HIGH` (both primary agents in the pair flagged it) or `UNVERIFIED` (only one flagged it). Set during Step 6 primary-agent synthesis.
2. **Challenger verdict confidence** — one of the nine values above. Set during Step 9 challenger synthesis.
3. **Finding type** — Quantitative metric / Pattern (B agents) / Voice & texture (C agents). Determines which output section the finding lands in.

A single finding can be `(UNVERIFIED, confirmed, Voice & texture)` — only one C agent flagged it, but both challengers upheld it, and it goes in the Voice section. That is a meaningfully strong finding *despite* UNVERIFIED analysis. Do not collapse the three axes; they measure different things.

The `[UNVERIFIED-CHALLENGER]` label is **only** for findings whose *challenger verdict* is literally `unverified-challenger`. Do NOT apply that label to findings whose *analysis* confidence is UNVERIFIED.

## Storage format

Store all verdicts as `[CHALLENGER_VERDICTS]`, one entry per finding number, with all three axes:

```
Finding 1: type=Pattern, analysis=HIGH, verdict=confirmed
Finding 2: type=Voice, analysis=UNVERIFIED, verdict=split
Finding 3: type=Pattern, analysis=HIGH, verdict=ambiguous
Finding 4: type=Pattern+Voice, analysis=HIGH, verdict=confirmed (cross-merged)
```

Pass this verbatim to the presentation agent.

## Coverage table bucket mapping (used by the presentation agent)

The presentation coverage table aggregates the nine verdict values into four buckets:

- **upheld**: confirmed + partial-upheld
- **disputed**: confirmed-disputed + partial-disputed
- **needs your decision**: split + ambiguous + partial-ambiguous + partial-unaddressed
- **unverified-challenger**: unverified-challenger only (NOT analysis-UNVERIFIED)

## NOT_ASSESSED handling

The Step 8 challenger prompt instructs: *"if you cannot assess one, write `## Challenger assessment: Finding [n] — NOT ASSESSED — [reason]`."* This is a deliberate non-skip — the challenger explicitly declares the finding wasn't evaluated, so synthesis treats it like a per-finding agent failure, not as silent absence.

Synthesis rules for `NOT ASSESSED`:
- Both challengers return NOT_ASSESSED for a finding → verdict = **partial-unaddressed**, falls into the "needs your decision" bucket. Note the reason from at least one challenger in the entry.
- One challenger returns NOT_ASSESSED, the other returns UPHELD/DISPUTED/AMBIGUOUS → treat the NOT_ASSESSED challenger as a per-finding failure; surviving challenger's verdict becomes the synthesis verdict with `partial-` prefix (partial-upheld / partial-disputed / partial-ambiguous).

This keeps NOT_ASSESSED visible as actionable (via `partial-` markers and the "needs your decision" bucket), rather than silently dropping the finding.
