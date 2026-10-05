---
name: proofread
description: "Proofread a draft essay or any text in strict British English: grammar, typos, spelling (strict -ise, never -ize), consistency, and register quality for research versus personal writing. Use whenever the user shares or pastes a draft and asks to proofread, check grammar or spelling, check British spelling, or check consistency, before submission or during revision. Maintains an optional canonical-terms file of project vocabulary (transliterations, names) across runs. For argument and structure feedback use review-writing, for overlap with sources use plagiarism-check, for AI-style review use ai-detection-check."
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

# proofread

Strict British proofreading. Deterministic scripts do the searching; read-only agents do the judging; scripts do the synthesising. Detail lives in `references/`; the shared mechanics are in `${CLAUDE_SKILL_DIR}/references/dispatch-protocol.md` (read it once at the start of a run).

## Spelling policy (decided 2026-10-04)

Strict British `-ise`. Every `-ize`, `-ization`, `-yze` form is an error, even if used consistently, except words spelt `-ize` in every system (size, prize, seize, capsize, maize). Prefer the other standard British spellings (colour, analyse, catalogue, programme, centre). Quoted source material is never changed.

## Run

1. **Setup** (`dispatch-protocol.md`, Run folder and Input): run folder, draft path or paste, essay type (`research | personal | application | other`), paragraph map. Ask for a terms file path only if the writer wants vocabulary checking; otherwise look for `canonical-terms.md` beside the draft. Never invent one.
2. **Pre-scans** into `$RUN` (each prints JSON; an `{"error": …}` aborts with that message). Expected output: `spelling.json` and `consistency.json`, each a JSON object of findings with paragraph numbers:
   - `python3 ${CLAUDE_SKILL_DIR}/scripts/check_british_spelling.py <draft> > $RUN/spelling.json`
   - `python3 ${CLAUDE_SKILL_DIR}/scripts/check_consistency.py <draft> > $RUN/consistency.json`
3. **Briefs:** read in full from `references/`: `surface.md` (Checks 1–3), `consistency.md` (Check 4), and `register-research.md` or `register-personal.md` (Check 5, by essay type). Field names must match `references/field-name-standard.md`.
4. **Dispatch six agents in parallel** (`dispatch-protocol.md`, Agent rules; `Explore`, A/B pairs with identical prompts; independent reads catch what one misses, and read-only means the draft is never altered): Surface (gets `spelling.json`), Consistency (gets `consistency.json`), Register. Prompt skeleton and pair rules are in the protocol. Say: "Six proofreader agents running…" Expected output: six agent reports, each with `## Finding` or `## No findings`.
5. **After return** (`dispatch-protocol.md`, After agents return): correct locations, then pair-synthesise per check:
   - Surface: `--exact Check --substring "Current text"`; Consistency and Register: the same.
   - Merge a Check 3 finding with a Check 4 finding for the same word (compare case-folded, hyphen-stripped forms of both the American and British variants); keep one compound entry, higher severity, with the note `⚠ Also flagged by Consistency check: …`, labelled "⚠ Compound: spelling + consistency" in the report.
   - Order for the report: Surface, Consistency, Register; renumber. Expected output: three merged finding lists (`*-merged.md`), HIGH or UNVERIFIED per finding.
6. **Vocabulary check** (only if a terms file exists and the surface agents listed unrecognised terms):
   - `python3 ${CLAUDE_SKILL_DIR}/scripts/canonical_terms.py collect $RUN/<SurfaceA>.md $RUN/<SurfaceB>.md > $RUN/unrecognised.txt` (expected: one term per line)
   - `python3 ${CLAUDE_SKILL_DIR}/scripts/canonical_terms.py check --terms <file> [--other <file>] [--global <file>] --words $RUN/unrecognised.txt`
   - `matched-incorrect` and `near-matched` become Check 3 findings (Severity High, in the field structure of `references/field-name-standard.md`), tagged UNVERIFIED when the class is `near-matched`. Matches from other or global files are migration suggestions for the report. `unresolved` terms go to the writer in one AskUserQuestion ("type the correct spelling, or leave blank to skip"); confirmed terms are appended with `canonical_terms.py add --terms <file> <term>…`. Never write to a terms file without that confirmation.
7. **Challenger** (`dispatch-protocol.md`, Challenger): two identical challengers (independent verdicts; disagreement shows a finding is contestable), rules from `references/challenger-synthesis-rules.md`; extra scope rules for this skill:
   - Check 3: do not uphold a finding inside directly quoted material. Under the strict policy an `-ize` form is never "acceptable variation".
   - Check 4: do not uphold a variation that follows a consistent pattern (full form then abbreviation; one form only inside quotations). If intent cannot be told, AMBIGUOUS with a specific question.
   - Check 5: do not uphold a register that is consistent throughout.
   - Compound findings: UPHELD if either concern is upheld; DISPUTED only if both are disputed.
8. **Presentation** (`dispatch-protocol.md`, Presentation): agent reads `references/presentation-format.md` and `assets/report-header-template.md`. Inputs: findings, verdict lines, status notes, migration suggestions.
9. **Save on request, then clean up** (`dispatch-protocol.md`, Save and cleanup).

## Example

User: "proofread my essay.md, it's a research essay". Actions: setup, both prescans, six Explore agents, synthesis, two challengers, presentation. Result: a report of findings by location and type (Surface, Consistency, Register) with verdicts and quick wins; nothing in the draft is altered.

## Troubleshooting

- `python3: command not found` -> install Python 3 (or use `python`), then rerun the prescans.
- Prescan prints `{"error": …}` -> fix the cause it names (usually draft path), rerun; do not dispatch agents without it.
- Draft unreadable or empty -> ask for the path again or for the text pasted; do not guess.
- Terms file missing -> skip the vocabulary check and say so; never create one unasked.

## Never

- Rewrite the writer's prose or silently correct it; every change is a finding, so the writer decides.
- Treat quoted source spelling as an error; quotations are the source's words, not the writer's.
- Add terms to a terms file without the writer's confirmation; a wrong entry would silently excuse later errors.
- Drop an UNVERIFIED finding; one agent's catch may be the one the other missed.

## Files

`references/`: `surface.md`, `consistency.md`, `register-research.md`, `register-personal.md`, `field-name-standard.md`, `challenger-synthesis-rules.md`, `presentation-format.md`, `glossary.md`. `scripts/`: `check_british_spelling.py`, `check_consistency.py`, `canonical_terms.py`, `tests/`. Shared: `${CLAUDE_SKILL_DIR}/scripts/shared/` (paragraph map, location correction, pair and verdict synthesis), `${CLAUDE_SKILL_DIR}/references/dispatch-protocol.md`.
