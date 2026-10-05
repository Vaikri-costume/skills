---
version: "2.0.0"
category: D
parent-version: "1.0.0"
author:
  primary: "Vaikri-costume"
  history:
    - role: "original"
      name: "Vaikri-costume"
      skill: "review-writing"
      license: "MIT"
      version: "2.0.0"
      date: "2026-10-04"
      source: "https://github.com/Vaikri-costume/skills"
inspirations: []
---

# History — review-writing

## Changelog

### 2.0.0 — 2026-10-04 (shipped)
Rewrite on the research refresh. 
#### Changed
- Argument brief rebuilt on Toulmin (claim, grounds, warrant, backing, qualifier, rebuttal), weakest warrant first; argument findings now carry `Current text` so location correction and pair matching work for them.
- Output restructured as feed up, feed back, feed forward (Hattie and Timperley 2007); up to three next steps derived only from upheld findings (the writer-centric output item pending since May).
- Clarity gains a Gopen and Swan sentence-position sub-category (limited to 5 findings).
- Quote integration (floating quotes, argumentative substitution) moved here from plagiarism-check; SOAS 30-word block-quotation note.
- Severity anchors added; no numeric grades.
- Citation inventory comes from the shared `citation_audit.py` (author-date, footnote, link, citekey); `count_citations.py` kept for Logseq drafts. The evidence appendix no longer greps a hard-coded `pages/` folder.
- SKILL.md from 453 lines to 48; persistence as in the other skills.
#### Added
- Scope note: own drafts only; publishers bar reviewers from uploading manuscripts to AI tools.
### 1.0.0 (pre-rewrite) — 2026-05-14
Layer A: `subagent_type` Explore changed to general-purpose (3 places); 2026-05-25: shared `extract_paragraphs.py` skips headings and properties, `count_citations.py` gained `--pages-dir`. Pending then: `agents/` restructure (not adopted), persistence redesign, line discipline (425 lines), writer-centric output (done), always-save report path (not adopted: saving stays opt-in), `Suggestion:` field and Location-only match key (not adopted). Still open: `evals/` content was not touched and may reference the old behaviour.

## Lineage notes

checked-marketplace: 2026-10-05

Independent design (category D). The 2026-05-14 "SKILL REWRITE STATUS" banner that used to open SKILL.md is recorded in the 1.0.0 entry above; its pending items are closed or explicitly not adopted.

Provenance: `references/dispatch-protocol.md` was previously one copy shared with proofread, plagiarism-check and ai-detection-check; quote integration was moved into `references/evidence.md` from plagiarism-check.
