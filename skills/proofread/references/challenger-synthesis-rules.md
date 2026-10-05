# Challenger synthesis rules

After both ProofChallenger-A and ProofChallenger-B return, run `python3 ${CLAUDE_SKILL_DIR}/scripts/shared/synthesise_verdicts.py A.md B.md --findings N`. The script applies the table below; this file is the specification it implements and the tests in `${CLAUDE_SKILL_DIR}/scripts/shared/tests/` cover it.

## Match criterion

Match findings across both challengers by **finding number** (same Finding [n]). The challenger receives a numbered list of synthesised findings; both challengers operate on the same numbering, so identity is by number rather than by passage quote.

## Verdict synthesis

For each finding, compare the two challengers' verdicts and assign one of these nine labels:

| Both A | Both B | Verdict confidence label | Meaning |
|--------|--------|-------------------------|---------|
| UPHELD | UPHELD | **confirmed** | Both challengers agreed this is a real issue |
| DISPUTED | DISPUTED | **confirmed-disputed** | Both challengers agreed this is not an issue |
| UPHELD | DISPUTED | **split** | Challengers disagreed — present both verdicts to writer |
| DISPUTED | UPHELD | **split** | Challengers disagreed — present both verdicts to writer |
| AMBIGUOUS | (any) | **ambiguous** | At least one challenger could not decide; surface their question to the writer |
| (any) | AMBIGUOUS | **ambiguous** | At least one challenger could not decide; surface their question to the writer |

When **one challenger failed** (no verdict for the finding from that agent): use the surviving challenger's verdict and tag with the `partial-` prefix:
- Surviving says UPHELD → **partial-upheld**
- Surviving says DISPUTED → **partial-disputed**
- Surviving says AMBIGUOUS → **partial-ambiguous**
- Surviving has no verdict for the finding either → **partial-unaddressed**

When **both challengers failed**: tag every finding **unverified-challenger**. Note in the output header: "challenger agents both failed — findings presented without adjudication."

## Storage format

Store all verdicts as `[CHALLENGER_VERDICTS]`, keyed by finding number. Format as one line per finding:

```
Finding 1: confirmed
Finding 2: split
Finding 3: ambiguous
Finding 4: confirmed-disputed
Finding 5: partial-upheld
```

Use this format verbatim when passing `[CHALLENGER_VERDICTS]` to the presentation agent.

## Coverage table bucket mapping (used by the presentation agent)

The presentation agent's coverage table aggregates the nine labels into four buckets:

- **upheld**: confirmed + partial-upheld
- **disputed**: confirmed-disputed + partial-disputed
- **ambiguous**: split + ambiguous + partial-ambiguous + partial-unaddressed
- **unverified-challenger**: unverified-challenger

This collapse is intentional — readers care about the four actionable buckets. The full nine-value taxonomy is preserved in the per-finding entries so a reader can see whether an "upheld" finding had both challengers agreeing or only one challenger surviving.
