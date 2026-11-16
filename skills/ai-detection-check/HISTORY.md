---
version: "3.0.1"
category: D
parent-version: "3.0.0"
author:
  primary: "Vaikri-costume"
  history:
    - role: "original"
      name: "Vaikri-costume"
      skill: "ai-detection-check"
      license: "MIT"
      version: "1.0.0"
      date: "2026-05-14"
      source: "https://github.com/Vaikri-costume/skills"
inspirations: []
---

# History — ai-detection-check

## Changelog

### 3.0.1 — 2026-11-16
Patch from the cold audit of 3.0.0 and a four-lens polish review (reuse, simplification, efficiency, altitude).
#### Changed
- SKILL.md sections follow the standard order (settings and hard rules before the run steps, known limitations after them, Examples and Troubleshooting last); the session-log marker is written again at the agents, challenge and present steps; the evasion-request reply is stated once, in `references/authenticity-evidence.md`; a known-limitation line says looking works up in Crossref and OpenAlex is plagiarism-check's reference-check mode.
- Wording tightened in SKILL.md and README (duplicated rules, vague referents, the shared scripts listed completely); `parent-version` set to 3.0.0.
- Tests for the citation audit (surnames containing "and", uncited entries, reference artefacts) added to the shared test suite; no behaviour change.

### 3.0.0 — 2026-11-14
Upgrade built from the 12 November research on current AI-detection systems (kept descriptive: no score, no verdict, no evasion advice). Evaluated over five rounds, each against the version it was iterated from (round 1 against installed 2.0.0), then real description trigger tests. Round reports are in the build's `evidence/`.
#### Added
- `scripts/tofile.py` and `scripts/runfolder.py`: every step is one plain `python3` command (output saved by `tofile.py`, run folder made and removed by `runfolder.py`), with a `<run>` placeholder instead of a shell variable.
- `scripts/report_lint.py`: rejects offers, next-step lines, gendered words about the writer, a percentage or likelihood of AI authorship, a statement that the text is or is not machine-written, and advice on avoiding or lowering a detector.
- `references/profile.md`: the vocabulary register, the session-log folder and the scratch folder are read from the writer's own profile at run time; the skill names no institution file and has no AI-use level or course gate (it only shows the writer how their own work reads and never does work for them).
- `references/detector-landscape.md`: dated background on how detectors work, what stays true and what goes stale fastest, with a refresh plan (last reviewed 2026-11-12).
- Bundled shared scripts under `scripts/shared/` (citation audit, quotation check, paragraph, location, pair and verdict scripts) with tests, so the skill no longer depends on files outside its folder.
- A plain limits statement in every report (detectors differ from each other, results change when text or tools change, plain, formal and second-language writing is flagged more often, no percentage, likelihood or verdict), a note on what scoring systems react to that also occurs in honest writing (describe, never advise), and a stronger evidence-of-your-own-process list.
- When the hedging-anchor question cannot be asked, the anchors are shown as proposed and unconfirmed with a status note.
- A hard rule that instructions found inside a draft are quoted and not followed.
#### Changed
- `tier` and `intended-audience` set to claude-users; `created-by` set to the author login; README rewritten for installation from a folder.
- Quotation check runs with `--all-sources-fallback`, so a quotation whose citation sits at the end of the sentence is searched in every supplied source; one found in none is reported as `not-found-in-supplied-sources`.
- Examples in reference files and tests made neutral (no field-specific words).
- Numbered read order at the top of SKILL.md (as a reasoned sentence, not a shouted rule); the lint fix loop capped at three passes; Expected output lines on the main steps; Example and Troubleshooting sections; the exclusion clause names the sibling skills to use instead.
- Reference files made local to this skill: no foreign step numbers, the old three-agent description in the base brief replaced with the current Pattern, Voice and Quantitative agents, the dispatch protocol and glossary reworded, provenance notes removed from script docstrings (cold audit).
- `description` widened to name a named draft file, what a flag does and does not mean, and a Do-NOT clause for rewriting, humanising and lowering a score.
#### Fixed
- `compute_metrics.py` and `find_ai_patterns.py` looked for the shared citation helper at a repository path and silently fell back to scanning the reference list as prose when it was missing (visible as a failing test whenever the skill ran outside the original repository layout); they now import the bundled copy with no silent fallback.
- The shared surname splitter cut surnames at the letters "and" (Brandt, Anderson, Sandhu), producing false unmatched-citation findings; it now matches whole words.
- `synthesise_verdicts.py`: a "## Suggested vocabulary register" section after the last challenger assessment was read as that assessment's reason; the block now ends at that heading. A new `--partial` flag gives the `partial-*` labels when only one challenger ran (one file without the flag still gives plain verdict words), and `references/dispatch-protocol.md` says to use it.
#### Removed
- [internal] The skill's own `evals/` folder is no longer shipped (fixtures stay in the maintainer's build evidence).

### 2.0.0 — 2026-10-04
Rewrite on the research refresh. Approved by the user 2026-10-04.
#### Changed
- Reframed from a detection-risk score to an authenticity and revision review; the report states what it cannot tell.
- `compute_metrics.py` rewritten: descriptive only, no RAG ratings; MATTR-100 replaces type-token ratio; Reinhart-style features per 1,000 words (present-participle clauses, nominalisations, passives); minimum-length guard; optional baseline comparison (needs about 1,000 words); personal path in the docstring removed; 10 tests.
- `find_ai_patterns.py`: list refreshed from the Wikipedia "Signs of AI writing" guide, dated, plus descriptive formatting signals; Pattern 12 no longer depends on a CV rating.
- Quantitative agent is a single agent (the numbers are deterministic); hedging anchors confirmed by the writer.
- Voice and texture: never flags formal prose; baseline departures are context only. Authorship-consistency view moved here from plagiarism-check.
- SKILL.md from 512 lines to 53; mechanics in the shared protocol; persistence as in the other skills.
#### Added
- `authenticity-evidence.md` (dated policy context: Jisc, a UK university misconduct procedure, Turnitin guidance, studies), the no-evasion rule, an "Evidence you can show" checklist, citation and quotation integrity via shared scripts.
### 1.0.0 (pre-rewrite) — 2026-05-14
Layer A: `compute_metrics.py` (TTR direction, sample variance, abbreviation-aware splitter, hedge false-positive filters), `find_ai_patterns.py` (Pattern 5, 8, 13 fixes, curly quotes), `subagent_type` Explore changed to general-purpose. Pending then, now closed: persistence redesign, line discipline (482 lines), 12-step architecture (replaced by the protocol), trimming `base.md` duplication (partly: patterns kept in `base.md`, hedging in `agent-quant.md`), `mkdir -p` ordering. Still open: `evals/` content was not touched and may reference the old behaviour.

## Lineage notes

Independent design (category D). The 2026-05-14 "SKILL REWRITE STATUS" banner that used to open SKILL.md is recorded in the 1.0.0 entry above; its pending items are closed or explicitly not adopted. Research behind 2.0.0: `hq/ccvw-skills/research/writing-skills-research-2026-10.md`. Tasks: SKL-011, SKL-012, SKL-014, SKL-015.
