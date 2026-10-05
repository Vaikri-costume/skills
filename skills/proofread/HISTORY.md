---
version: "2.0.0"
category: D
parent-version: "1.0.0"
author:
  primary: "Vaikri-costume"
  history:
    - role: "original"
      name: "Vaikri-costume"
      skill: "proofread"
      license: "MIT"
      version: "2.0.0"
      date: "2026-10-04"
      source: "https://github.com/Vaikri-costume/skills"
inspirations: []
---

# History — proofread

## Changelog

### 2.0.0 — 2026-10-04 (shipped)
Rewrite on the research refresh. 
#### Changed
- Spelling policy: strict British `-ise`. `check_british_spelling.py` rewritten: every `-ize`/`-yze` form is an error except a built exception list (size, prize, seize, capsize, maize, baize, assize and inflections; Greek `-s-` stem verbs such as synthesise are errors); larger British word list; quoted text, URLs, wikilinks and the reference list excluded; paragraph numbers match the shared map; 14 tests.
- Canonical vocabulary check is now a script (`canonical_terms.py`: collect, check, add; 4 tests) instead of two agent pairs; terms live in an explicit markdown file, not `memory/projects/*.md`.
- SKILL.md cut from 745 lines (about 14k tokens) to 64 lines; mechanics moved to the shared dispatch protocol; frontmatter completed (license, compatibility, metadata, allowed-tools).
- Persistence: run folder in the temp directory, no state or tracking files, no session-log appends, no JSONL recovery path (the dead Logseq project path is gone).
- Synthesis (pair and verdict) and location correction are shared scripts with tests.
#### Fixed
- Paragraph numbering differed between `extract_paragraphs.py` and `correct_finding_locations.py` when a draft had headings or property lines; both now share one function.
- `-ize` was flagged as an American error and the suffix regex could flag words such as "seize".
### 1.0.0 (pre-rewrite) — 2026-05-14
Layer A fixes applied that day: `SUFFIX_EXCLUSIONS` (size, prize, sense, dense, wheeled), curly-quote handling, `AMBIGUOUS` set, `subagent_type` Explore changed to general-purpose. Pending then and now closed: persistence redesign, line discipline (720 lines), 13-step architecture (not adopted; replaced by the protocol), strip_markers in both input modes (now always run on pasted text).
Still open: `evals/` content was not touched in this rewrite and may reference the old behaviour.

## Lineage notes

checked-marketplace: 2026-10-05

Independent design (category D). The 2026-05-14 "SKILL REWRITE STATUS" banner that used to open SKILL.md is recorded in the 1.0.0 entry above; its pending items are closed or explicitly not adopted. 

The dispatch protocol is a shared copy across the four writing skills; provenance lives here, not in the runtime doc.
