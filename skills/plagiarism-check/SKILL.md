---
name: plagiarism-check
description: "Check a draft essay for plagiarism risk before submission: unmarked verbatim overlap with sources, close paraphrase (patchwriting), summary instead of synthesis, unattributed frameworks, self-plagiarism against earlier submissions, and citation integrity (quotations missing from the source, uncited reference-list entries, unmatched citations). Handles author-date, footnote, Logseq markdown and plain Markdown drafts. Categories follow common UK university misconduct procedures; adapt category names and thresholds to your own institution. Use when the user asks to check for plagiarism, originality, or whether the draft is too close to its sources, or before submitting a research essay. Modes: citation-check (cited sources) and full-scan (all project sources). Do NOT use for grammar/spelling (use proofread), argument feedback (use review-writing) or AI-style review (use ai-detection-check)."
license: MIT
compatibility: Claude Code 2.0 or newer, Python 3
metadata:
  argument-hint: "[optional: draft file path]"
  tier: claude-users
  created: 2026-05-14T00:00
  created-by: user
  parent-version: 1.0.0
  intended-audience: claude-users
  mcp-server: zotero (optional; provides zotero_search_items and zotero_get_item_fulltext)
allowed-tools:
  - Read
  - Bash
  - Glob
  - Grep
  - Agent
  - AskUserQuestion
  - Write
  - mcp__zotero__zotero_search_items
  - mcp__zotero__zotero_get_item_fulltext
---

# plagiarism-check

Scripts find; one read-only agent per source judges; one challenger verifies against the texts; one agent presents. Shared mechanics are in `${CLAUDE_SKILL_DIR}/references/dispatch-protocol.md` (read it at the start of a run). Vocabulary and limits: `references/misconduct-categories.md`. The categories follow common UK university misconduct procedures; adapt the category names and thresholds to the user's own institution.

Voice comparison against the writer's past work is not part of this skill (it is an authorship question; see ai-detection-check). Quote-integration and floating-quote checks live in review-writing.

## Run

1. **Setup** (`dispatch-protocol.md`, Run folder and Input). Essay type. Mode: `citation-check` (default) or `full-scan` (every source page in the project; needs a source folder or Logseq pages dir). Ask for prior submissions only if the writer wants a self-plagiarism check.
2. **Cited works.** `python3 ${CLAUDE_SKILL_DIR}/scripts/shared/detect_sources.py --mode <mode> --draft-path <draft> --format <author-date|logseq|plain-md> [--pages-dir <dir>] [--sources-dir <dir>] > $RUN/sources.json` (author-date also covers footnote drafts). Expected output: JSON list, one entry per cited work with a `resolved` flag. For each entry with `"resolved": false`, look the work up in Zotero (`zotero_search_items`, then `zotero_get_item_fulltext`) and write the text to `$RUN/sources/<slug>.txt`. Still nothing: list it under "no text obtained"; never guess its content.
3. **Deterministic checks** into `$RUN`:
   - `python3 ${CLAUDE_SKILL_DIR}/scripts/overlap_check.py <draft> --source <slug>=<logseq page> … --plain <slug>=<text file> … [--plain prior:<name>=<file>] [--common-terms <file>] > $RUN/overlap.json`
   - `python3 ${CLAUDE_SKILL_DIR}/scripts/shared/citation_audit.py <draft> > $RUN/audit.json`
   - `python3 ${CLAUDE_SKILL_DIR}/scripts/shared/quote_verify.py <draft> --source <surname>=<path> … --all-sources-fallback > $RUN/quotes.json`
   Expected output: `overlap.json` lists verbatim-run and short-match hits per source (empty list if none); `audit.json` and `quotes.json` list citation and quote checks. Each prints `{"error": …}` and exits 1 on failure: stop and say why.
4. **Scope gate** (only if more than 8 sources): AskUserQuestion — judge all / only sources with overlap matches / cancel.
5. **Judge** (`dispatch-protocol.md`, Agent rules; `Explore`): one agent per source, in parallel, prompt = `references/source-judgement.md` plus `source-judgement-research.md` or `source-judgement-personal.md`, that source's matches from `overlap.json`, the paragraph map, the draft path, the source text path. Names `PlagSource-<slug>-<run>`. A source with no matches still gets Checks 2, 3 and 5 in citation-check mode.
6. **Correct and combine** (`dispatch-protocol.md`, After agents return, steps 1 and 2 only): `correct_finding_locations.py … --flag-unmatched` per agent; concatenate findings in source order, renumber. No pair synthesis. Empty list: skip to 8.
7. **Challenge** (`dispatch-protocol.md`, Challenger): one `Explore` agent, rules from `references/challenger-synthesis-rules.md`, then `synthesise_verdicts.py $RUN/Challenger.md --single --findings N`. Expected output: one `Finding n: <upheld|disputed|ambiguous|unaddressed>` line per finding.
8. **Present** (`dispatch-protocol.md`, Presentation): `references/presentation-format.md` and `assets/report-header-template.md`; inputs `overlap.json`, `audit.json`, `quotes.json`, findings, verdict lines, status notes.
9. **Save on request, then clean up** (`dispatch-protocol.md`, Save and cleanup).

## Never

- Present flags as findings of misconduct or comment on intent: only a marker can judge intent, and the report states its limits every time.
- Compare against `author::` annotation lines or the writer's own notes as if they were sources: they are the writer's metadata, so matches would be false positives.
- Advise how to avoid detection: the skill supports honest citation, not evasion.
- Drop a finding because the challenger disputed it: it moves to "Disputed" so the writer can see and weigh the reasoning.
- Invent a source's text when none could be obtained: a made-up comparison text produces false verdicts.

## Example

User: "Check this essay for plagiarism before I submit" (draft path given).
Actions: citation-check mode, `detect_sources.py`, Zotero lookup for unresolved works, the three scripts, one agent per source, challenger, presentation agent.
Result: a report with flags by category and weight (typical UK terms), a citation-integrity checklist, and a limits statement.

## Troubleshooting

- Agent fails twice (no `## Finding` or `## No findings`) -> cause: malformed output; fix: record "agent unavailable" for that source and say so in the header.
- Zotero lookup unresolved -> cause: work not in the library; fix: ask for a source text file, else list under "no text obtained".
- Zotero MCP missing (optional) -> cause: server not connected; fix: supply a folder of source texts via `--sources-dir`.
- Empty `sources.json` -> cause: wrong `--format` or no citations detected; fix: re-run with the right format and check the draft path.
- Script returns `{"error": ...}` -> cause: bad path or argument; fix: read the message, correct the input, re-run.

## Files

`references/`: `source-judgement.md`, `source-judgement-research.md`, `source-judgement-personal.md`, `misconduct-categories.md`, `field-name-standard.md`, `challenger-synthesis-rules.md`, `presentation-format.md`, `glossary.md`. `scripts/`: `overlap_check.py`, `tests/`. Shared: `${CLAUDE_SKILL_DIR}/scripts/shared/` (`citation_audit.py`, `quote_verify.py`, `detect_sources.py`, paragraph and location scripts, `synthesise_verdicts.py`), `${CLAUDE_SKILL_DIR}/references/dispatch-protocol.md`.
