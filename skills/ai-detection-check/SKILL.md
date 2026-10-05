---
name: ai-detection-check
description: "Review a draft for AI-typical writing patterns, over-smooth or generic texture, hedging calibration, and citation integrity (quotations missing from the cited source, uncited reference-list entries, invented or malformed references), and say what evidence of the writer's own process they can show. Use when the user asks whether a draft sounds like AI, is too polished, formulaic or generic, or might be flagged by AI-detection tools, or before submitting an essay where originality of voice matters. Reports descriptive metrics and flags for revision; it never claims to prove or disprove AI authorship and never coaches evasion. Do NOT use for grammar or spelling (use proofread), argument feedback (use review-writing) or overlap with sources (use plagiarism-check)."
license: MIT
compatibility: Claude Code 2.0 or newer, Python 3
metadata:
  argument-hint: "[optional: draft file path]"
  tier: claude-users
  created: 2026-05-14T00:00
  created-by: user
  parent-version: 1.0.0
  intended-audience: claude-users
allowed-tools:
  - Read
  - Bash
  - Glob
  - Grep
  - Agent
  - AskUserQuestion
  - Write
---

# ai-detection-check

An authenticity and revision review, not a detector. Detectors are unreliable, easy to evade, and biased against formal and second-language writing, so this skill reports descriptions and flags, never a score or a verdict. Evidence and policy context: `references/authenticity-evidence.md`. Mechanics: `references/dispatch-protocol.md` (read it at the start of a run). The citation checks here are a lightweight authenticity signal; `plagiarism-check` is the tool for full source-overlap and citation-integrity review.

## Run

1. **Setup** (dispatch-protocol.md, "Run folder" and "Input"): run folder, draft, essay type. Ask once, optionally, for 10–20 field-specific terms (vocabulary register; "skip" is fine). Offer an optional baseline: the writer's own earlier texts (file paths) for a descriptive comparison; they need about 1,000 words in total. Offer optional source texts (`LABEL=PATH`) for quotation verification. Never fetch or assume either.
2. **Deterministic scans** into `$RUN` (an `{"error": …}` stops the run). Expected output: `metrics.json` (descriptive features, optional baseline block), `patterns.json` (flags with locations), `audit.json` (citation and reference lists, issues), `quotes.json` (verified or missing quotations):
   - `python3 ${CLAUDE_SKILL_DIR}/scripts/compute_metrics.py <draft> [--baseline <files…>] > $RUN/metrics.json`
   - `python3 ${CLAUDE_SKILL_DIR}/scripts/find_ai_patterns.py <draft> > $RUN/patterns.json`
   - `python3 ${CLAUDE_SKILL_DIR}/scripts/shared/citation_audit.py <draft> > $RUN/audit.json`
   - only if sources were supplied: `python3 ${CLAUDE_SKILL_DIR}/scripts/shared/quote_verify.py <draft> --source <surname>=<path> … > $RUN/quotes.json`
3. **Briefs** (read in full from `references/`): `agent-quant.md`; `base.md` plus `appendix-research.md` or `appendix-personal.md` for the pattern agents; `base.md` and `agent-voice.md` for the voice agents. Field names: `field-name-standard.md`.
4. **Dispatch five agents in parallel** (dispatch-protocol.md, "Agent rules"; `Explore`): Quantitative (single; gets `metrics.json`), Pattern A/B (identical prompts; gets `patterns.json`, which they verify in context and extend with semantic equivalents), Voice A/B (identical prompts; gets `metrics.json` for the baseline block only).
5. **After return** (dispatch-protocol.md, "After agents return"): correct locations; pair-synthesise Pattern (`--exact Pattern --substring "Current text"`) and Voice (`--exact Issue --substring "Current text"`); cross-merge a Pattern and a Voice finding with the same normalised `Current text` into one `Pattern+Voice` entry (higher severity, "independently flagged by both — stronger signal"); renumber, Pattern first. Expected output: one numbered findings list, Pattern first.
6. **Calibration gate:** show the three hedging anchors with the quantitative agent's rationale in one AskUserQuestion; the writer confirms or corrects each label. Never proceed on unconfirmed labels.
7. **Challenge** (dispatch-protocol.md, "Challenger"): two identical challengers. Context block for them: essay type, vocabulary register, the hedging norms from the appendix used, the confirmed anchors. **Scope rule:** assess only against that block; never import norms from adjacent fields; if the block is silent, AMBIGUOUS: insufficient context. For the voice and baseline material: a departure from the writer's baseline is context, not evidence. Challengers also return `## Suggested vocabulary register` (10–20 terms). Rules: `challenger-synthesis-rules.md`.
8. **Present** (dispatch-protocol.md, "Presentation"): `references/presentation-format.md`, `assets/report-header-template.md`; inputs: metrics, patterns summary, audit, quotes, findings, verdict lines, anchors, status notes. Expected output: the full report, relayed verbatim.
9. **Save on request, then clean up** (dispatch-protocol.md, "Save and cleanup"). A suggested vocabulary register is only saved if the writer says where.

## Never

- State or imply that the text is, or is not, machine-written; or give a "detection score".
- Advise how to lower a score, humanise text or avoid detection. If asked: this check finds places where specific thinking may be missing, and honest AI assistance is declared, not disguised.
- Flag text for being well written, clear or formal.
- Rate a metric RED/YELLOW/GREEN: no published threshold exists.
- Drop an UNVERIFIED finding.

## Files

`references/`: `base.md`, `appendix-research.md`, `appendix-personal.md`, `agent-quant.md`, `agent-voice.md`, `authenticity-evidence.md`, `field-name-standard.md`, `challenger-synthesis-rules.md`, `presentation-format.md`, `glossary.md`. `scripts/`: `compute_metrics.py`, `find_ai_patterns.py`, `tests/`. Shared scripts: `${CLAUDE_SKILL_DIR}/scripts/shared/` (`citation_audit.py`, `quote_verify.py`, paragraph and location scripts, pair and verdict synthesis), plus `references/dispatch-protocol.md`.

## Example

User: "Does this essay sound like AI? It's draft.md." -> Claude runs the three scans, dispatches the agents, asks the writer to confirm the hedging anchors, challenges the findings -> a report of descriptive metrics, numbered flags for revision and an evidence-you-can-show checklist, with no verdict on authorship.

## Troubleshooting

| Cause | Fix |
|---|---|
| `python3` missing | Install Python 3, or say the scans cannot run; do not guess the metrics |
| Draft unreadable or empty (`{"error": …}`) | Ask for a path to a text or Markdown file, or pasted text |
| Baseline files unparseable or under about 1,000 words | Drop the baseline or ask for other earlier texts; the report says no comparison was made |
| Source label mismatch (`quotes.json` lists a source as not supplied) | Make `LABEL` match the surname used in the draft's citations, then re-run `quote_verify.py` |
| Any script returns `{"error": …}` | Stop, read the message, fix the input, re-run; never continue on partial output |
