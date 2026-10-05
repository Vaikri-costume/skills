# Proofread — Consistency Brief

Delivered to consistency proofreading agents (ProofConsist-A and ProofConsist-B). Run the check below.

---

## Check 4 — Consistency

Find: the same concept named two different ways without apparent intentionality; hyphenation inconsistency (e.g., "post-colonial" and "postcolonial" mixed); capitalisation inconsistency for key terms; the same entity referred to by two different names alternating without clear reason.

Rules:
- Do NOT flag spelling variants inside directly quoted source material — only flag inconsistency in the writer's own prose.
- Plural forms of the same root word are not inconsistencies ("dupatta" / "dupattas").
- Intentional variation that follows a consistent pattern (e.g., full form on first use, abbreviated thereafter) is not an inconsistency.

---

## Output format

Return EXACTLY this format for every finding. One entry per issue:

```
## Finding [n]
Location: paragraph [n], sentence [m] of the paragraph, [opening words of the sentence]
Current text: "[exact text as it appears in the draft — show both variant forms if they occur in different sentences]"
Pattern: [describe the inconsistency — what the two forms are and where each appears in the essay]
Concern: [why this matters — potential reader confusion, ambiguity, or apparent lack of intentionality]
Check: 4
Severity: High / Medium / Low
```

Severity guide:
- High: creates genuine ambiguity about which referent is meant
- Medium: inconsistent but not ambiguous
- Low: minor capitalisation or hyphenation inconsistency

After all findings, append:

```
## Coverage
Check 4 (Consistency): [n] findings
Total: [n] findings
```

If no findings: write "## No findings — Check 4 (Consistency): no inconsistencies found."
