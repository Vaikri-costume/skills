# Proofread — Register Brief (Research Essays)

Delivered to register proofreading agents (ProofRegister-A and ProofRegister-B) for research essays.

---

## Check 5 — Register quality (research essays)

Flag:
1. **Unresolved abbreviations:** first use of an abbreviation not spelled out.
2. **Informal contractions in formal analytical prose:** "it's", "doesn't", "can't", "we've", "they're" — unless they appear in direct quotation.
3. **Uncited claims:** a specific empirical claim, a contested interpretive position, or a reference to a named study — asserted without any citation or acknowledgment where one is clearly expected.

Do NOT flag: informal phrasing that is consistent throughout (consistent informal = author's register, not an error); hedging language; questions or rhetorical moves that do not assert a specific claim.

---

## Output format

Return EXACTLY this format for every finding. One entry per issue:

```
## Finding [n]
Location: paragraph [n], sentence [m] of the paragraph, [opening words of the sentence]
Current text: "[exact text as it appears in the draft]"
Pattern: [describe the register issue — which of the three types above, and specifically what was found]
Concern: [why this matters in formal analytical prose]
Check: 5
Severity: High / Medium / Low
```

Severity guide:
- High: clearly wrong register for research writing, or missing citation where one is required
- Medium: inconsistent but not misleading
- Low: preference-level register note

After all findings, append:

```
## Coverage
Check 5 (Register quality): [n] findings
Total: [n] findings
```

If no findings: write "## No findings — Check 5 (Register quality): no register issues found."
