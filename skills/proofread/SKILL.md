---
name: proofread
description: "Proofread a draft essay or any prose in strict British English: grammar, typos, spelling (strict -ise, never -ize), consistency, and register (colloquialisms, contractions, vague quantifiers). Returns proposed changes in a was/now/why table, a cut log against any word limit and an AI-use line; it never edits or rewrites the draft, and writes a separate commented copy on request. Use whenever the user shares or pastes a draft and asks to proofread, check grammar, typos, British spelling, consistency, tone or register, or word count, before submission or during revision. Optional canonical-terms file for project vocabulary. Do NOT use to rewrite or rephrase sentences, write text, or proofread code; for argument and structure feedback use review-writing, for source overlap plagiarism-check, for AI-style review ai-detection-check."
license: MIT
compatibility: Claude Code 2.0 or newer, Python 3
metadata:
  argument-hint: "[optional: draft file path]"
  tier: claude-users
  created: 2026-05-14T00:00
  created-by: Vaikri-costume
  parent-version: 2.0.0
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

Strict British proofreading. Deterministic scripts do the searching and the tables; read-only agents do the judging; scripts do the synthesising. Detail lives in `references/`; the shared mechanics are in `${CLAUDE_SKILL_DIR}/references/dispatch-protocol.md` (read it once at the start of a run).

It runs when the writer asks and is never volunteered: do not suggest running it, and end the report without proposing further checks. This does not block the writer from using any other skill when they ask for it. Refer to the writer as "the writer" or "they"; never assume gender.

## Spelling policy (decided 2026-10-04)

Strict British `-ise`. Every `-ize`, `-ization`, `-yze` form is an error, even if used consistently, except words spelt `-ize` in every system (size, prize, seize, capsize, maize). Prefer the other standard British spellings (colour, analyse, catalogue, programme, centre). Quoted source material is never changed.

## Gate (first, before any run)

Read `references/profile.md` once: it says where the writer's profile lives, what each key means and how to apply the course AI rules. If the draft is coursework, apply that gate and stop, saying why, unless a rule allows language feedback or the writer confirms it does. With no profile and no coursework, carry on with the defaults.

## Run

1. **Setup** (`dispatch-protocol.md`, Run folder and Input): run folder, draft path or paste, essay type (`research | personal | application | other`), paragraph map. Note a word limit if the writer gives one. If the profile sets `session_log_dir`, append one line `**[HH:MM:SS] SKILL:proofread RUN:<run id> STEP:start**` to the day's log there; with no key, write nothing. Ask for a terms file path only if the writer wants vocabulary checking; otherwise look for `canonical-terms.md` beside the draft. Never invent one. Read the writer's style profile if the profile names one (`references/profile.md`).
2. **Pre-scans** into `$RUN` (each prints JSON; an `{"error": …}` aborts with that message):
   Independent of each other, so run them together:
   - `python3 ${CLAUDE_SKILL_DIR}/scripts/check_british_spelling.py <draft> > $RUN/spelling.json`
   - `python3 ${CLAUDE_SKILL_DIR}/scripts/check_consistency.py <draft> > $RUN/consistency.json`
   - `python3 ${CLAUDE_SKILL_DIR}/scripts/word_count.py <draft> [--limit N] > $RUN/words.json` (word count, limit, deletion-only cut candidates)
   - only when the profile names a style profile: `python3 ${CLAUDE_SKILL_DIR}/scripts/style_check.py <draft> <style profile> > $RUN/style.json` (departures from the writer's own conventions; pass it to the Consistency agents as authoritative, like `consistency.json`, to be reported as Check 4 with the Pattern starting `[convention]`)
3. **Briefs:** read in full from `references/`: `surface.md` (Checks 1–3), `consistency.md` (Check 4), and `register-research.md` or `register-personal.md` (Check 5, by essay type). Field names must match `references/field-name-standard.md`. When a style profile exists, paste its Quick Reference into the register brief as the writer's own conventions.
4. **Dispatch six agents in parallel** (`dispatch-protocol.md`, Agent rules; `Explore`, A/B pairs with identical prompts): Surface (gets `spelling.json`), Consistency (gets `consistency.json`), Register. Prompt skeleton and pair rules are in the protocol. Say: "Six proofreader agents running…" Expected output: six agent reports, each with `## Finding` or `## No findings`.
5. **After return** (`dispatch-protocol.md`, After agents return): correct locations, then pair-synthesise per check:
   - Surface: `--exact Check --substring "Current text"`; Consistency and Register: the same.
   - Merge a Check 3 finding with a Check 4 finding for the same word (compare case-folded, hyphen-stripped forms of both the American and British variants); keep one compound entry, higher severity, with the note `⚠ Also flagged by Consistency check: …`, labelled "⚠ Compound: spelling + consistency" in the report.
   - Order for the report: Surface, Consistency, Register; renumber into one file `$RUN/findings.md`. Expected output: three merged finding lists (`*-merged.md`), HIGH or UNVERIFIED per finding.
6. **Vocabulary check** (only if a terms file exists and the surface agents listed unrecognised terms):
   - `python3 ${CLAUDE_SKILL_DIR}/scripts/canonical_terms.py collect $RUN/<SurfaceA>.md $RUN/<SurfaceB>.md > $RUN/unrecognised.txt` (expected: one term per line)
   - `python3 ${CLAUDE_SKILL_DIR}/scripts/canonical_terms.py check --terms <file> [--other <file>] [--global <file>] --words $RUN/unrecognised.txt`
   - `matched-incorrect` and `near-matched` become Check 3 findings (Severity High, in the field structure of `references/field-name-standard.md`), tagged UNVERIFIED when the class is `near-matched`. Matches from other or global files are migration suggestions for the report. `unresolved` terms go to the writer in one AskUserQuestion ("type the correct spelling, or leave blank to skip"); confirmed terms are appended with `canonical_terms.py add --terms <file> <term>…`. Never write to a terms file without that confirmation.
7. **Challenger** (`dispatch-protocol.md`, Challenger): two identical challengers, rules from `references/challenger-synthesis-rules.md`; extra scope rules for this skill:
   - Check 3: do not uphold a finding inside directly quoted material.
   - Check 4: do not uphold a variation that follows a consistent pattern (full form then abbreviation; one form only inside quotations). If intent cannot be told, AMBIGUOUS with a specific question.
   - Check 5: do not uphold a register that is consistent throughout.
   - Compound findings: UPHELD if either concern is upheld; DISPUTED only if both are disputed.
   Save the verdict lines to `$RUN/verdicts.txt`. Expected output: `Finding n: label` lines covering every finding number.
8. **Tables:** `python3 ${CLAUDE_SKILL_DIR}/scripts/change_table.py $RUN/findings.md --verdicts $RUN/verdicts.txt > $RUN/tables.md` (omit `--verdicts` when the challenger step was skipped). It gives the change table (was, now, why), the flagged-not-changed list and the register audit. The report carries `tables.md` verbatim and never adds a row of its own.
9. **Presentation** (`dispatch-protocol.md`, Presentation): agent reads `references/presentation-format.md` and `assets/report-header-template.md`. Inputs: findings, verdict lines, `tables.md`, `words.json`, status notes, migration suggestions. The report ends with the cut log and the AI-use line.
10. **Annotated copy, only when the writer asks for comments in a file:** write it beside the draft as `<draft name>-proofread-comments.<ext>` (add `-2`, `-3` if that name is taken) with `python3 ${CLAUDE_SKILL_DIR}/scripts/annotate_copy.py <draft> $RUN/findings.md --out <copy>`. The script refuses to overwrite any file and checks that stripping its comments restores the draft. Expected output: JSON with `placed` and `unplaced` counts and the copy's path.
11. **Save on request, then clean up** (`dispatch-protocol.md`, Save and cleanup). Expected output: the report file only where the writer asked, and no run folder left behind.

## Example

User: "proofread my essay.md, it's a research essay, 1,500 words max". Result: the full report with a cut log against 1,500 and an AI-use line; essay.md is not altered.

## Troubleshooting

- `python3: command not found` -> install Python 3 (or use `python`), then rerun the prescans.
- Prescan prints `{"error": …}` -> fix the cause it names (usually draft path), rerun; do not dispatch agents without it.
- Draft unreadable or empty -> ask for the path again or for the text pasted; do not guess.
- Terms file missing -> skip the vocabulary check and say so; never create one unasked.
- `annotate_copy.py` refuses -> choose another `--out` name.

## Hard rules (never)

- Rewrite the writer's prose or silently correct it; every change is a finding, so the writer decides. Never edit the draft file in place; comments go in a separate copy.
- Treat quoted source spelling as an error; quotations are the source's words, not the writer's.
- Add terms to a terms file, or entries to a style profile, without the writer's confirmation (a wrong entry silently excuses later errors); never build a style profile from past writing.
- Drop an UNVERIFIED finding; one agent's catch may be the one the other missed.
- Volunteer or run another check, or create a profile; the writer asks.

## Known limitations

- The A/B pairs and two challengers need a runtime that can dispatch read-only subagents; without them, one pass per role is possible but every finding is UNVERIFIED and there are no quick wins.
- The word count includes quotations and excludes headings and the reference list; a course that counts differently needs its own number.
- `style_check.py` matches the listed forms exactly; it cannot see a convention written only as guidance.
- British single-quote masking can mis-pair a possessive plural followed by a space (the dogs' bowls); the agents' judgement covers the rest.

## References

| Path | Purpose | When to read |
|---|---|---|
| `references/dispatch-protocol.md` | Run folder, agent rules, synthesis, presentation | once at the start of a run |
| `references/profile.md` | The writer's profile: AI rules, style profile, terms file | at the Gate |
| `references/surface.md`, `consistency.md`, `register-research.md`, `register-personal.md` | The agent briefs for Checks 1 to 5 | step 3 |
| `references/field-name-standard.md`, `challenger-synthesis-rules.md`, `presentation-format.md`, `glossary.md` | Field contract, verdict labels, report format, terms | steps 5 to 9 |
| `scripts/` (with `tests/` and `shared/`) | Prescans, tables, copy tool and synthesis helpers | named in each step |

Sibling skills: `review-writing`, `plagiarism-check`, `ai-detection-check`.
