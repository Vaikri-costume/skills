# Presentation format — proofread

The presentation agent organises all synthesised findings into a writer-facing report. Read this file and produce output in this exact format.

**Why every finding appears inline:** Truncation is silent data loss — the writer cannot tell what was omitted unless they explicitly ask for a saved report. All findings present means the revision pass is complete on first read.

**Output the full report as the direct content of your response.** Do not summarise the report and describe what it contains ("Report complete: 2 quick wins, 4 findings…"); do not paraphrase sections; do not say "session log updated" in place of the report. The executor passes your response straight to the writer — a summary in place of the report means the writer never sees the findings. Every section heading, every finding entry with all its fields, and the full coverage table must appear in your response output verbatim.

## Two confidence dimensions — keep separate

Each finding carries two independent tags:

- **Analysis confidence**: `HIGH` (both primary agents in the pair flagged the passage) or `UNVERIFIED` (only one agent flagged it). This comes from primary-agent synthesis.
- **Challenger verdict confidence**: one of the nine values in `references/challenger-synthesis-rules.md` (confirmed, confirmed-disputed, split, ambiguous, partial-upheld, partial-disputed, partial-ambiguous, partial-unaddressed, unverified-challenger).

The `[UNVERIFIED-CHALLENGER]` label is **only** for findings whose **challenger verdict** is literally `unverified-challenger` (both challengers failed and the finding was presented without adjudication). It is NOT a relabelling of analysis confidence `UNVERIFIED`. A finding can be `UNVERIFIED` (one agent flagged) AND `confirmed` (both challengers upheld) at the same time — that is a strong finding, not an unverified one. Keep the two dimensions visible separately on every entry; do not collapse them.

## Pass through location verbatim

Every finding's `Location:` field comes from the synthesised finding block. Use that exact paragraph number in the by-location heading and in any inline reference. Do NOT re-derive the location from the draft, do NOT renumber paragraphs, do NOT shift entries to neighbouring paragraphs. The agents already used [PARAGRAPH_MAP] when locating the finding; the location is canonical.

---

## Report skeleton

Read `assets/report-header-template.md` for the header. Then output the sections below in this order. Omit any section that has no findings (do not show empty headings).

```
[REPORT HEADER from assets/report-header-template.md]

---

### Quick wins — apply without judgment
[Check 1–3 findings with confirmed or partial-upheld verdicts AND HIGH confidence.
These are deterministic corrections — apply without judgment. One per line:
"Para [n]: [Current text] → [Proposed fix] (Check [n])"
Omit this section if there are none.]

---

### By location
[Group ALL confirmed, partial-upheld, and unverified-challenger findings by paragraph number.
For each paragraph with at least one such finding:

Para [n]: [opening words of paragraph from PARAGRAPH_MAP]
- [finding summary] | Check [n] | [HIGH/UNVERIFIED] | [severity] | [verdict tag]
  - Check 1–3 findings: show Current text + Proposed fix
  - Check 4–5 findings: show Current text + Pattern + Concern
  - Compound findings: show both concerns; label "⚠ Compound: spelling + consistency"
  - unverified-challenger findings: append "[UNVERIFIED-CHALLENGER]"

Omit this section if there are no such findings.]

---

### By type
[Group ALL confirmed, partial-upheld, and unverified-challenger findings by check number,
then severity within each check (High → Medium → Low).

For Check 1 (Grammar), Check 2 (Typos), Check 3 (British spelling): show Current text + Proposed fix.
For Check 4 (Consistency), Check 5 (Register quality): show Current text + Pattern + Concern.
unverified-challenger findings: append "[UNVERIFIED-CHALLENGER]".

Omit any check sub-section that has no findings. Omit the entire section if all are empty.]

---

### Needs your decision
[All findings with split, ambiguous, partial-ambiguous, or partial-unaddressed verdicts.
- For split: show both challengers' verdicts and reasons.
- For ambiguous and partial-ambiguous: show the challenger's specific question verbatim.
- For partial-unaddressed: note "one challenger upheld; the other returned no verdict for this finding."

Omit this section if none.]

---

### Disputed (for reference)
[All findings with confirmed-disputed or partial-disputed verdicts. Show Current text and the challengers' reasoning verbatim. Omit this section if none.]

---

### Vocabulary — migration recommendations
[MIGRATION_FINDINGS — terms found in other projects' canonical lists or the global list, with suggested actions (add to current project / promote to global). Omit this section if none.]

---

### Coverage

Bucket mapping (from `references/challenger-synthesis-rules.md`):
- upheld = confirmed + partial-upheld
- disputed = confirmed-disputed + partial-disputed
- ambiguous = split + ambiguous + partial-ambiguous + partial-unaddressed
- unverified-challenger = unverified-challenger

Check 1 (Grammar): [n] upheld (HIGH: [n], UNVERIFIED: [n]) | [n] disputed | [n] ambiguous | [n] unverified-challenger
Check 2 (Typos): [n] upheld (HIGH: [n], UNVERIFIED: [n]) | [n] disputed | [n] ambiguous | [n] unverified-challenger
Check 3 (British spelling): [n] upheld (HIGH: [n], UNVERIFIED: [n]) | [n] disputed | [n] ambiguous | [n] unverified-challenger
Check 4 (Consistency): [n] upheld (HIGH: [n], UNVERIFIED: [n]) | [n] disputed | [n] ambiguous | [n] unverified-challenger
Check 5 (Register quality): [n] upheld (HIGH: [n], UNVERIFIED: [n]) | [n] disputed | [n] ambiguous | [n] unverified-challenger
Total upheld: [n] | Total disputed: [n] | Total ambiguous: [n] | Total unverified-challenger: [n] | Migration recommendations: [n]
```

---
