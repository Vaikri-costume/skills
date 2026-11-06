---
version: "2.1.0"
category: D
parent-version: "2.0.0"
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

### 2.1.0 — 2026-11-06
Upgrade built from the published 2.0.0 (the installed project copy was the baseline for the round 1 comparison). Five eval and improve rounds, each graded against the previous round's snapshot, then description rounds and a ship pass; evidence in the build folder, not shipped.
#### Added
- Modes, each run only when the writer names it: draft (direction questions, no verdict), revision-diff (`scripts/revision_diff.py` locates earlier quotes; statuses addressed, partly addressed, unchanged, introduced a new problem, no longer applies), presentation (gaps only, `scripts/presentation_stats.py`), bibliography (source-status words, default "not checked").
- Rubric support: a verdict table in the rubric's own order and words (met, partly, not met, "not found in the draft"), checked by `scripts/verdict_table.py`, with a separate "Also noticed" list marked as the reviewer's view.
- Three blind reader lenses (audience, rigour, premise) as anchored questions, shown side by side; genre lenses; a field lens read at run time from the writer's own field pages.
- Promise-versus-delivery check in the Argument brief; `Layer` on every finding and `Would change if` on High findings; a confidence line in the report header; strengths placed beside the critique they protect.
- `references/profile.md`: the writer's profile (course AI rules, field pages) is read at run time, so the skill holds no personal, course or field detail. The gate stops for a ban without an invitation to retry, asks one question for a borderline or silent rule, and never generates text.
- Rule against following instructions found inside drafts, rubrics, profiles or any file; such text is quoted verbatim in a Note and not acted on.
- `scripts/report_lint.py` (TLDR, offers, gendered words, rewrite blocks, numeric grades) run before a report is relayed; `scripts/combine_findings.py` (cross-domain merge, `Domain:` lines, layer ordering, renumbering); 16 tests for the new scripts.
- Anti-sycophancy rule for challengers and reviewers: a position changes only for a reason quoted from the draft.
#### Changed
- Report ordered from the claim down to the sentence; the caps on findings per agent, on sentence-position findings and on next steps are lifted; "Where to next" is now process questions tied to finding numbers, with no supplied wording and no closing offer.
- Frontmatter, README and SKILL.md now speak of "the writer"; they/them only in skill output.
- Polish pass: duplicated rules point to one place; mode-specific limits moved to the mode files.
- Language-only course permission: a message that names the argument or the evidence is the writer's ask, so those domains run (and the header says so) instead of being refused on the rule alone; found when the final suite on the staged copy refused one such request.
- Personal-content scan (module codes, assessment names, the writer's fields and research focuses, and word lists drawn from them) over every shipped file: none found in the published copy; the installed copy's eval fixture used a field-specific word list, which is not carried over (evals are not shipped); all new fixtures use invented topics.
- Ship-stage audit fixes: Hard rules moved to the top with a reason for each, an expected-output line on every run step, `Edit` added to allowed tools, the run folder honours a configurable `scratch_dir` and is deleted by literal path, the session-log marker is written when the profile sets `session_log_dir`, the glossary is alphabetised, reference files anchor to section names instead of step numbers, and `quote_verify.py` is now cited from bibliography mode.
#### Removed
- `scripts/shared/detect_sources.py` and `scripts/shared/build_citation_map.py`: no step used them [internal].
#### Fixed
- `references/glossary.md` no longer links to a file outside the skill.

### 2.0.0 — 2026-10-04 (shipped)
Rewrite on the research refresh. 
#### Changed
- Argument brief rebuilt on Toulmin (claim, grounds, warrant, backing, qualifier, rebuttal), weakest warrant first; argument findings now carry `Current text` so location correction and pair matching work for them.
- Output restructured as feed up, feed back, feed forward (Hattie and Timperley 2007); up to three next steps derived only from upheld findings (the writer-centric output item pending since May).
- Clarity gains a Gopen and Swan sentence-position sub-category (limited to 5 findings).
- Quote integration (floating quotes, argumentative substitution) moved here from plagiarism-check; 30-word block-quotation note.
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

Acknowledgements (ideas only, rewritten in new words and code; no file, text or script copied): Writing Desk 0.1.0 by Naji Kayal (Apache-2.0) for the rubric verdict table in the rubric's own words and the separate "also noticed" list; humanities-writing-companion by tizzy916 (CC BY-NC 4.0) for the promise-versus-delivery check, reviewer lenses as questions with a retract rule, layered ordering of findings, the revision-diff check and the source-status wording. Recorded as an acknowledgement, not a change of category; the category can move to C on the maintainer's word.

Provenance: `references/dispatch-protocol.md` was previously one copy shared with proofread, plagiarism-check and ai-detection-check; quote integration was moved into `references/evidence.md` from plagiarism-check.
