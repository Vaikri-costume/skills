# Proofread — Register Brief (Personal / Application / Other Essays)

Delivered to register proofreading agents (ProofRegister-A and ProofRegister-B) for personal, application, and other essays.

---

## Check 5 — Register quality (personal / application / other essays)

Flag register shifts: passages where formal academic register intrudes into an otherwise intimate or reflective voice, or vice versa, without apparent intentionality.

Do NOT flag:
- Consistent informal contractions throughout — flag only inconsistent register, not consistent choices.
- Occasional formal phrasing in an otherwise informal essay if it appears deliberate.
- Passages that are simply well-written in a different register — flag only where the shift is jarring or disruptive to the dominant voice.

---

## Output format

Return EXACTLY this format for every finding. One entry per issue:

```
## Finding [n]
Location: paragraph [n], sentence [m] of the paragraph, [opening words of the sentence]
Current text: "[exact text as it appears in the draft]"
Pattern: [describe the register shift — what the dominant register is and how this passage departs from it]
Concern: [why this shift is likely unintentional and how it affects the reader's experience of the essay]
Check: 5
Severity: High / Medium / Low
```

Severity guide:
- High: register shift is jarring and likely unintentional
- Medium: noticeable but the reader can follow the intent
- Low: subtle, worth noting but low impact

After all findings, append:

```
## Coverage
Check 5 (Register quality): [n] findings
Total: [n] findings
```

If no findings: write "## No findings — Check 5 (Register quality): no register issues found."
