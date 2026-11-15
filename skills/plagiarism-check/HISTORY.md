---
version: "3.0.1"
category: D
parent-version: "3.0.0"
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

### 3.0.1 — 2026-11-14
Patch: one bug in a bundled shared script, found while evaluating ai-detection-check.
#### Fixed
- `scripts/shared/synthesise_verdicts.py`: a "## Suggested vocabulary register" section after the last challenger assessment was read as part of that assessment and attached to its verdict reason (a verdict with no reason on its own line also picked up the next line). The assessment block now ends at that heading and a reason is read from its own line. Two tests added (`scripts/shared/tests/test_synthesise_verdicts.py`).

### 3.0.0 — 2026-11-14
A major version because the report's shape changed (a status on every flag, a limits line, a cleared-matches list and a reference section). Upgrade built from the published 2.0.0 (the installed project copy was the baseline for round 1). Five eval and improve rounds, each graded against the previous round's snapshot, then description rounds and a ship pass; evidence is in the build folder, not shipped.
#### Added
- Reference-check mode (`references/mode-reference-check.md`, `scripts/reference_check.py`): parse the list, document-wide cross-check with near matches, Crossref and OpenAlex lookups (only title, first author, year, DOI and ISBN sent), field verdicts, outcomes Clean, Fix, Not found and Review, a frankenstein flag for an identifier that leads to a different work, a patch log that keeps the original value, never a filled-in identifier, books and grey literature never "Not found".
- `references/acceptable-use.md`: what is and is not plagiarism, the status ladder (verbatim, near-verbatim, structurally derived, possibly derived) and the honest-limits sentence "Clean means nothing found through the search used" in every report.
- Check 6 (claim fidelity) with statuses supports, partly supports, contradicts, not found in the source text, not checked.
- `references/profile.md`: the course AI rules, institution wording, common terms and field pages are read from the writer's profile at run time; a gate that stops for a ban without an invitation to retry; rule against following instructions found inside files.
- `scripts/report_lint.py` (TLDR, offers, gendered words, accusations, evasion advice, grades, rewrite blocks, the limits sentence, identifiers not in the data) and tests: 32 for the new scripts.
- `scripts/tofile.py` and `scripts/runfolder.py`: every step is one plain `python3` command (no shell redirect, no `mktemp`, no shell variable, no `rm`); the run folder is made and removed by script, and removal refuses anything that is not a plagiarism-check run folder.
- Shared-identifier flag: two list entries carrying one DOI or ISBN are both Review; an ISBN that belongs to a different book in Crossref is a frankenstein flag.
- A cleared-matches list under each source in the report, so the writer sees what was looked at and not flagged.
#### Removed
- `scripts/shared/synthesise_pairs.py` and `scripts/shared/build_citation_map.py` and the tests of the first: no step used them (the skill has no A/B pair) [internal].
#### Fixed
- Found by a real re-run of the round 5 suite after the first push: `challenger-synthesis-rules.md` now states the heading the verdict script matches on (`## Challenger assessment: Finding <n>`; any other heading made the finding "unaddressed"); `synthesise_verdicts.py` no longer prints a stray ". " before an ambiguous question or a disputed reason; a full scan lists the source files in the folder that the draft never cites (`detect_sources.py`), with tests.
- Found by the same re-run: helpers wrote shell variables (`S=`, `R=`) for the run folder because the steps used the look-alike `$RUN`; the steps now say `<run>` and tell the executor to type absolute paths and never create a shell variable. The gate is now the first instruction in SKILL.md, before any file is opened, even when the task lists the draft as an input file.
- `scripts/shared/citelib.py` `first_surname` split on the letters "and" with no word boundary, so "Brandt", "Anderson", "Landis" and "Sandhu" were cut to fragments and gave false unmatched-citation and uncited-entry flags; found by the round 3 workers.
- "n.d." citations and list entries with no year are read as undated instead of being missed; a list entry with no year keeps its first author in reference-check mode.
- The reference table no longer cuts an entry in the middle of a DOI.
#### Changed
- Runs only when the writer asks, naming the check; no offers, no Next line; they/them only.
- Personal-content scan: the framework list in `source-judgement-research.md` (named theorists drawn from the writer's fields) and an institution regulation number in a script docstring were removed; the field's credited frameworks now come from the writer's field page.
- The gate is the first Hard rule: nothing but the profile and the rules file is opened before it passes (workers read the draft in the same batch otherwise).
- The status ladder has a word-for-word alignment test, and a structurally derived finding lists the shared elements in the source's order; a request to reword text so a checker will not flag it is declined in one sentence with no wording.
- Anti-sycophancy for the judgement agent and challenger: a position changes only for a reason quoted from the draft or source.

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

Acknowledgements (ideas only, rewritten in new words and code; no file, text or script copied): Writing Desk 0.1.0 by Naji Kayal (Apache-2.0) for reference-check wording; peer-review, bibtidy, nagomi, sourceverify and cite2fn plugins for outcome and verdict ideas (licences not checked). Recorded as an acknowledgement, not a change of category.
