---
version: "2.0.0"
category: D
parent-version: "1.0.0"
author:
  primary: "Vaikri-costume"
  history:
    - role: "original"
      name: "Vaikri-costume"
      skill: "ai-detection-check"
      license: "MIT"
      version: "2.0.0"
      date: "2026-10-04"
      source: "https://github.com/Vaikri-costume/skills"
inspirations: []
---

# History — ai-detection-check

## Changelog

### 2.0.0 — 2026-10-04 (shipped)
Rewrite on the research refresh. 
#### Changed
- Reframed from a detection-risk score to an authenticity and revision review; the report states what it cannot tell.
- `compute_metrics.py` rewritten: descriptive only, no RAG ratings; MATTR-100 replaces type-token ratio; Reinhart-style features per 1,000 words (present-participle clauses, nominalisations, passives); minimum-length guard; optional baseline comparison (needs about 1,000 words); personal path in the docstring removed; 10 tests.
- `find_ai_patterns.py`: list refreshed from the Wikipedia "Signs of AI writing" guide, dated, plus descriptive formatting signals; Pattern 12 no longer depends on a CV rating.
- Quantitative agent is a single agent (the numbers are deterministic); hedging anchors confirmed by the writer.
- Voice and texture: never flags formal prose; baseline departures are context only. Authorship-consistency view moved here from plagiarism-check.
- SKILL.md from 512 lines to 53; mechanics in the shared protocol; persistence as in the other skills.
#### Added
- `authenticity-evidence.md` (dated policy context: Jisc, SOAS REG-183-10, Turnitin guidance, studies), the no-evasion rule, an "Evidence you can show" checklist, citation and quotation integrity via shared scripts.
### 1.0.0 (pre-rewrite) — 2026-05-14
Layer A: `compute_metrics.py` (TTR direction, sample variance, abbreviation-aware splitter, hedge false-positive filters), `find_ai_patterns.py` (Pattern 5, 8, 13 fixes, curly quotes), `subagent_type` Explore changed to general-purpose. Pending then, now closed: persistence redesign, line discipline (482 lines), 12-step architecture (replaced by the protocol), trimming `base.md` duplication (partly: patterns kept in `base.md`, hedging in `agent-quant.md`), `mkdir -p` ordering. Still open: `evals/` content was not touched and may reference the old behaviour.

## Lineage notes

checked-marketplace: 2026-10-05

Independent design (category D). The 2026-05-14 "SKILL REWRITE STATUS" banner that used to open SKILL.md is recorded in the 1.0.0 entry above; its pending items are closed or explicitly not adopted.

`references/dispatch-protocol.md` is a protocol shared with proofread, plagiarism-check and review-writing, kept as one copy per skill.
