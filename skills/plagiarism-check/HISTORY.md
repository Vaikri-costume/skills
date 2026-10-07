---
version: "2.0.0"
category: D
parent-version: "1.0.0"
author:
  primary: "Vaikri-costume"
  history:
    - role: "original"
      name: "Vaikri-costume"
      skill: "plagiarism-check"
      license: "MIT"
      version: "2.0.0"
      date: "2026-10-04"
      source: "https://github.com/Vaikri-costume/skills"
inspirations: []
---

# History — plagiarism-check

## Changelog

### 2.0.0 — 2026-10-04 (shipped)
Rewrite on the research refresh. All six open design decisions approved by the user 2026-10-04 as recommended (the original 4 May 2026 plan file is lost; the options were re-derived in the research doc, section 2.2):
1. Agent type: read-only `Explore` for every analysis, challenger and presentation agent.
2. Structural check redesign: replaced by `citation_audit.py` (sources per paragraph, dominance, uncited reference entries, repeated reference entries, author re-introductions, artefacts); quote-integration moved to review-writing.
3. Voice check: removed from this skill (authorship consistency is descriptive context in ai-detection-check).
4. Citation inventory: `detect_sources.py` now parses author-date and footnote citations (plus Logseq links and citekeys) with a Zotero lookup for unresolved works.
5. Persistence: temp run folder, opt-in save; state files, tracking file, JSONL recovery removed.
6. Pairing: scripts for deterministic work, one judgement agent per source, one verifying challenger.
#### Added
- `overlap_check.py` (6-word verbatim runs, weak 4 to 5-word matches, quoted spans excluded, prior-submission mode; 8 tests); shared `citation_audit.py`, `quote_verify.py`, `citelib.py` (tests).
- UK university vocabulary: categories and weights (poor academic practice, minor, major), self-plagiarism, a limits statement in every report.
#### Changed
- Frontmatter was invalid YAML (colon in the description); fixed. SKILL.md from 392 lines to 57.
- The "3 content words" overlap rule replaced by the tiers above.
### 1.0.0 (pre-rewrite) — 2026-05-14
Layer A: `subagent_type` Explore changed to general-purpose (4 places); no script-level fixes. Pending then, now closed: the six decisions, persistence redesign (11 /tmp refs, 19 state-file refs), line discipline (364 lines), removal of the old Checks 4, 6 and 7 (Acorn faults 19 to 21), Tier 1 cache key fault, `strip_markers` always. Still open: `evals/` content was not touched and may reference the old behaviour.

## Lineage notes

checked-marketplace: 2026-10-05

Independent design (category D). The 2026-05-14 "SKILL REWRITE STATUS" banner that used to open SKILL.md is recorded in the 1.0.0 entry above; its pending items are closed or explicitly not adopted.

The dispatch protocol in `references/dispatch-protocol.md` was originally written for the sibling writing skills and is now maintained as this skill's own reference.
