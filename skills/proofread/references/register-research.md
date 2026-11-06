# Proofread — Register Brief (Research Essays)

Delivered to register proofreading agents (ProofRegister-A and ProofRegister-B) for research essays.

---

## Check 5 — Register quality (research essays)

Run the register audit below. Each row is one type; start every finding's Pattern with the bracketed tag so the audit table can count it. A word or phrase that fits two rows gets one finding under the first row it fits.

| Tag | Flag | Do not flag |
|---|---|---|
| `[abbreviation]` | First use of an abbreviation that is not spelled out | An abbreviation spelled out on first use, or a universally known one (UK, DNA) |
| `[contraction]` | Informal contractions in formal analytical prose: "it's", "doesn't", "can't", "we've", "they're" | Contractions inside direct quotation |
| `[colloquialism]` | Conversational words or phrases that lower the register: "kids", "a bit", "pretty good", "stuff", "get across", "nowadays" used as a time marker | Informal phrasing the essay uses consistently throughout (that is the author's register); idiom inside quotation |
| `[vague-quantifier]` | "a lot of", "lots of", "loads of", "plenty of", "a number of", "various", "several", "some" where the sentence makes an empirical claim and a number, range or named group is expected | A quantifier in a sentence that makes no empirical claim; "some" in "some argue" followed by a citation in the same sentence |
| `[uncited-claim]` | A specific empirical claim, a contested interpretive position, or a reference to a named study asserted without any citation or acknowledgment where one is clearly expected | Hedging language; questions or rhetorical moves that assert no specific claim |

Also do not flag consistent informal register, or any item inside a direct quotation.

---

## Output format

Return EXACTLY this format for every finding. One entry per issue:

```
## Finding [n]
Location: paragraph [n], sentence [m] of the paragraph, [opening words of the sentence]
Current text: "[exact text as it appears in the draft]"
Pattern: [tag] [describe the register issue: what was found, in one clause]
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
