---
version: "2.2.1"
category: D
parent-version: "2.2.0"
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

### 2.2.1 — 2026-11-16
Patch from the cold audit and a four-lens polish review (reuse, simplification, efficiency, altitude) of 2.2.0.
#### Changed
- SKILL.md sections now follow the standard order (hard rules before the run steps, known limitations after them, Examples and Troubleshooting last); the session-log marker is written again at the agents, challenge and present steps so a compaction can tell which phase was active.
- The four-bucket verdict mapping is written once, in `references/presentation-format.md`; `references/challenger-synthesis-rules.md` points to it.
- Wording tightened in SKILL.md and README (duplicated rules, vague referents, a stale README line about the session log); `parent-version` set to 2.2.0.

### 2.2.0 — 2026-11-14
Prompt-free upgrade. Rebuilt from 2.1.0 and evaluated over five rounds, each against the previous round's snapshot (round 1 against installed 2.1.0), then real description trigger tests. Real defects found and fixed are listed below; round reports are in the build's `evidence/`.
#### Added
- `scripts/tofile.py` runs a script and saves its output to a named file, so a step needs no shell redirect.
- `scripts/runfolder.py new|remove` makes and removes the run folder (it refuses any folder that is not a proofread run folder), so a run needs no `mktemp` or `rm`.
- `scripts/report_lint.py` checks the finished report for offers, next-step lines, gendered words about the writer, American spellings outside quotations and a TL;DR.
- Cut log states `Under by` when a draft is under its stated limit (`word_count.py` returns `under_by`).
- Tests for the run tools, the report lint and the word-count margin.
#### Changed
- Every step is one plain `python3` command with absolute paths; `<run>` stands for the run folder path in place of a shell variable.
- A numbered read order sits at the top of SKILL.md: this file, then the profile and rules file, and only then the draft.
- The run-folder removal step is stated as safe and required.
- Report-lint fix loop capped at three passes; Expected output lines added to steps 1, 3 and 9; `scratch_dir` listed in `references/profile.md`; the spelling exception list lives in `references/surface.md` only; the cut log says "N words short" and "Under by" is 0 when over (cold audit findings).
- `description` widened to name the file of a draft, spell-checking, -ise versus -ize, how many words it is and what filler to cut to fit a limit.
- `scripts/shared/citelib.py`: `first_surname` no longer splits a surname that contains "and" (such as Brandt or Anderson).
#### Fixed
- `scripts/shared/synthesise_verdicts.py`: a "## Suggested vocabulary register" section after the last challenger assessment was read as part of that assessment (found in an ai-detection-check run); the assessment block now ends at that heading. A new `--partial` flag gives the `partial-*` labels when only one challenger ran (one file without the flag still gives the plain `upheld | disputed | ambiguous` words), and `references/dispatch-protocol.md` says to use it. Tests added.
- The shared surname splitter cut "Brandt" and "Anderson" at "and".
- The commented-copy and report steps no longer depend on shell redirection or `rm` that a permission prompt would block.
#### Removed
- [internal] Four bundled shared scripts the skill never calls (not part of the interface): `build_citation_map.py`, `citation_audit.py`, `detect_sources.py`, `quote_verify.py`.

### 2.1.0 — 2026-11-06
Upgrade planned in SKL-018 (plan: hq/ccvw-skills/plans/proofread.md). Evaluated over five rounds against the previous round's snapshot (round 1 against the installed 2.0.0), then description rounds.
#### Added
- Register audit: Check 5 findings carry a type tag and are counted by type in the report; the research register brief gains colloquialism and vague-quantifier checks.
- Style profile check (`scripts/style_check.py`): flags departures from the writer's own confirmed conventions; the profile never grows from past writing.
- Cut log on every run (`scripts/word_count.py`): word count, any stated limit, how far over, deletion-only cut candidates, and the count that would remain.
- Change table, flagged-not-changed list and AI-use line (`scripts/change_table.py`); surface findings gain a Reason field; overlapping findings are marked.
- Commented copy (`scripts/annotate_copy.py`): a separate file that never overwrites and is checked to restore the draft once comments are stripped; comments sit after their bullet in bullet files.
- Quote masking helper (`scripts/shared/quotes.py`) for block quotes and British single-quoted text, with tests.
- `references/profile.md`: the writer's profile (course AI-rules gate, style profile, terms file, optional session-log folder); the gate is generic and read at run time.
- Known limitations and a References table in SKILL.md; Features & modes and Structure sections in the README.
#### Changed
- Skill and README descriptions widened to register, word count and the never-edits guarantee, with a Do-NOT-use clause for rewriting and code (trigger check: Sonnet proxy, 28 queries, 8 held out, all correct).
- Prescans run together; added Tables and annotated-copy steps; expected output stated for steps 7, 10 and 11.
- "Never" became "Hard rules (never)", with never-edit-in-place, no unconfirmed style-profile entries and no volunteered checks added.
- Gate, spelling policy and never-rules de-duplicated; Files and Example trimmed; README test commands moved to For developers.
- Consistency Check 4 now quotes only the earliest occurrence as one span so A/B pairs match; style findings are authoritative with a `[convention]` prefix.
- Bullet files are converted to paragraphs before the paragraph map; the commented copy is made from the original.
- `created-by` set to the author login; `parent-version` set to 2.0.0.
#### Fixed
- The run folder is deleted by literal absolute path, not through a shell variable.
- Block quotes and British single-quoted text were flagged as the writer's own spelling; they are now masked and apostrophes no longer open a quote.
- The consistency prescan only skipped paired double quotes; it now uses the shared quote mask.
- Bullet-only files were counted as one paragraph, giving wrong paragraph numbers in the report.
- The consistency prescan stopword list had lost two third-person pronoun entries (a wording cleanup), so capitalised and lower-case forms were reported as capitalisation variants; restored, with a test.
- The change table ignored the plain labels the single-challenger synthesis prints.
#### Removed
- [internal] Personal terms and a lineage note from tests, briefs and docstrings (checked with the private term list and a full-history scan before publishing).
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

The change table, the was/now/why layout and the flagged-not-changed list borrow ideas from Writing Desk 0.1.0 by Naji Kayal (Apache-2.0); ideas only, rewritten in this skill's own words, nothing copied.
