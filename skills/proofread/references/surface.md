# Proofread — Surface Brief

Delivered to surface proofreading agents (ProofSurface-A and ProofSurface-B). Run all three checks below.

---

## Check 1 — Grammar

Find: subject-verb agreement errors, article errors (a/an/the), preposition errors, tense inconsistencies within a passage, dangling modifiers. Flag each with the corrected form.

## Check 2 — Typos

Find: misspellings, duplicate words ("the the"), punctuation errors (missing full stops, double spaces, stray commas), stray characters.

## Check 3 — British spelling (strict -ise)

Policy: strict British spelling. `-ise`, never Oxford `-ize`. Every `-ize`, `-ization`, `-izing`, `-izer`, `-izable` and `-yze` form in the writer's own prose is an error, whether or not it is used consistently. The only `-ize` spellings allowed are words spelt that way in every system: size, prize, seize, capsize, maize, baize, assize and their inflections. Prefer the other standard British spellings too (colour, analyse, catalogue, programme for a plan or series, centre, defence, travelled, towards).

The prescan (`check_british_spelling.py`) has already found every instance in the writer's own prose; quoted material, URLs, wikilinks and the reference list are excluded. For each instance: confirm it in context, then report it with the prescan's British form as the Proposed fix. Findings tagged `verify:` (program, practice, licence/license, meter, judgment, curb, toward) depend on meaning: report them only when the context shows the American form is wrong, and say which sense you read.

Also look for what the script cannot: a British-spelling error that is not in its list (apply the same strict policy), and an American form inside a heading or caption the script treated as prose.

Do NOT flag spelling inside directly quoted source material. Genuine `-ize` verbs from a Greek `-s-` stem (synthesise, emphasise, hypothesise) are `-ise` errors like any other. When unsure, the Oxford English Dictionary's British headword decides.

---

## Output format

Return EXACTLY this format for every finding. One entry per issue:

```
## Finding [n]
Location: paragraph [n], sentence [m] of the paragraph, [opening words of the sentence]
Current text: "[exact text as it appears in the draft]"
Proposed fix: "[corrected text]"
Check: [1 / 2 / 3]
Severity: High / Medium / Low
```

Severity guide:
- High: changes meaning, introduces ambiguity, or is clearly wrong
- Medium: non-standard but not misleading
- Low: preference-level

After all findings, append:

```
## Unrecognised terms
[Every word or phrase in the draft that is not in a standard British English dictionary: transliterated terms, domain-specific terms, words from other languages used in English prose, proper nouns specific to the subject domain (person names, place names, film titles, institution names that would not appear in a general dictionary). When in doubt, include rather than exclude — the canonical vocabulary check handles known terms. If none found: write "None identified."]

## Coverage
Check 1 (Grammar): [n] findings
Check 2 (Typos): [n] findings
Check 3 (British spelling): [n] findings
Total: [n] findings
```
