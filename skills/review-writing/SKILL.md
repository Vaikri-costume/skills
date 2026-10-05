---
name: review-writing
description: "Give a substantive analytical review of a draft: argument structure (Toulmin: claim, grounds, warrant, rebuttal), clarity (including Gopen and Swan sentence position), evidence and quote integration, and voice consistency, as feed up, feed back and feed forward. Use when the user asks to review a draft, whether an argument works, if it is clear, to check evidence, how the structure is, for feedback, what is missing, or whether the voice is consistent. For error-checking (grammar, spelling) use proofread instead. Works for research essays, personal statements and application essays, with criteria adapted to essay type. For the writer's own drafts only."
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

# review-writing

Analytical review of the writer's own drafts. Four domains, each run by an A/B pair of read-only agents; scripts do the counting, location correction and synthesis. Shared mechanics: `${CLAUDE_SKILL_DIR}/references/dispatch-protocol.md` (read it at the start of a run).

Scope: the writer's own drafts. Do not paste someone else's manuscript into an AI tool; publishers such as Elsevier bar reviewers from doing so and hold the reviewer accountable for the content.

## Run

1. **Setup** (`dispatch-protocol.md`, Run folder and Input): run folder, draft, essay type. For research essays also: `python3 ${CLAUDE_SKILL_DIR}/scripts/shared/citation_audit.py <draft> > $RUN/audit.json` (its `sources_per_paragraph` is the citation inventory; Logseq drafts may add `python3 ${CLAUDE_SKILL_DIR}/scripts/count_citations.py <draft> [--pages-dir <dir>] > $RUN/citations.json`). For non-research essays the inventory is "not applicable". Expected output: `audit.json` with a `sources_per_paragraph` map.
2. **Briefs** (read in full from `references/`, each followed by `severity-anchors.md`): `arg-structure.md`; `clarity.md`; `evidence.md` plus `evidence-research.md` or `evidence-personal.md`; `voice.md` plus `voice-research.md` or `voice-personal.md`. Field names: `field-name-standard.md`.
3. **Dispatch eight agents in parallel** (`dispatch-protocol.md`, Agent rules; `Explore`, four A/B pairs with identical prompts): Argument, Clarity, Evidence (gets the citation inventory as ground truth: it judges which claims need support, it does not recount; and a source folder path only if one was supplied), Voice. Say: "Eight reviewers running…"
4. **After return** (`dispatch-protocol.md`, After agents return): correct locations for all four pairs (argument findings now carry `Current text`); pair-synthesise with `--exact Element` (Argument), `--exact Sub-category` (Clarity), none (Evidence, Voice) and `--substring "Current text"`; cross-domain merge: a Clarity or Voice finding whose normalised quote equals one in Argument or Evidence merges into one entry tagged `Cross-domain (merged)` with the higher severity. Order: Argument → Evidence → Clarity → Voice; renumber. Expected output: one numbered findings list (each with a confidence label) after location correction and pair synthesis. Collect the Strengths sections and the argument agents' "Reading of the draft"; pick the 2–3 most specific, distinct strengths.
5. **Challenge** (`dispatch-protocol.md`, Challenger): two identical challengers. Scope rules to put in their prompt:
   - Research essays: heavy engagement with foundational sources is expected, and a "needs support" flag may reflect appropriate reliance on the writer's analysis, so judge whether the gap is real.
   - Personal and application essays: the standard is concrete specificity, not citation density.
   - All essays: never import norms from fields the draft does not represent. If the context is insufficient, the challenger answers `AMBIGUOUS: insufficient context` for that finding (a valid verdict, not a prohibition).

   Rules: `challenger-synthesis-rules.md`. Expected output: one `Finding n: label` line per finding from `synthesise_verdicts.py`.
6. **Present** (`dispatch-protocol.md`, Presentation): `references/presentation-format.md` and `assets/report-header-template.md`; inputs: findings, verdict lines, strengths, both readings of the draft, status notes. The report is feed up, feed back, feed forward.
7. **Save on request, then clean up** (`dispatch-protocol.md`, Save and cleanup).

## Never

- Comment on the writer instead of the writing, or give numeric grades: feedback must be actionable on the text, and grades invite arguing over a number.
- Offer next steps that add criticism no finding supports: unsupported advice cannot be traced to evidence in the draft.
- Drop an UNVERIFIED finding: one agent's finding is weaker but may still be real; the writer decides.
- Rewrite the draft: suggestions describe what a better version would do, so the voice stays the writer's.

## Example

User: "/review-writing essay.md" (research essay). Actions: citation audit; eight reviewers; location correction and pair synthesis; two challengers; presentation. Result: a feed up / feed back / feed forward report with numbered findings, 2-3 strengths and up to three next steps.

## Troubleshooting

| Cause | Fix |
|---|---|
| A script fails | Read its stderr; re-run with the corrected path or argument; do not skip location correction |
| No draft path or text | Ask once (path or paste), per `dispatch-protocol.md`, Input |
| An agent returns no findings and no `## No findings` section | Counts as failed: re-dispatch once, then note "agent unavailable" in the header |
| An agent returns no Strengths section | Take strengths from its partner; if neither has any, say so in the report |
| `python3` missing | Install Python 3; without it the audit and synthesis scripts cannot run |

## Files

`references/`: `arg-structure.md`, `clarity.md`, `evidence.md`, `evidence-research.md`, `evidence-personal.md`, `voice.md`, `voice-research.md`, `voice-personal.md`, `severity-anchors.md`, `field-name-standard.md`, `challenger-synthesis-rules.md`, `presentation-format.md`, `glossary.md`. `scripts/`: `count_citations.py`. Shared: `${CLAUDE_SKILL_DIR}/scripts/shared/` (`citation_audit.py`, paragraph and location scripts, pair and verdict synthesis), `${CLAUDE_SKILL_DIR}/references/dispatch-protocol.md`.
