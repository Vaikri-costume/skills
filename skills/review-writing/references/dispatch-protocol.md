# Dispatch protocol

The run-folder, agent, synthesis and presentation mechanics below apply to this skill; SKILL.md names the section each Run step uses. Paths are relative to the repository root (`${CLAUDE_PROJECT_DIR}`); shared scripts live in `${CLAUDE_SKILL_DIR}/scripts/shared/`.

## 1. Run folder (no state files, no tracking file)

```bash
RUN=$(mktemp -d "${TMPDIR:-/tmp}/<skill>-XXXXXX")   # all intermediates go here
```

Nothing is written next to the draft or into any memory folder during a run. Delete `$RUN` (`rm -rf "$RUN"`) when the report has been delivered. If the session is compacted mid-run, the run folder is still on disk: list it, read the newest agent outputs, and carry on from the last step whose output file exists. There is no resume question and no state machine.

## 2. Input

- **File path given:** use it. **Pasted text:** write it to `$RUN/draft.md`, then `python3 ${CLAUDE_SKILL_DIR}/scripts/shared/strip_markers.py $RUN/draft.md` (removes Logseq bullet markers). **Neither:** ask once with AskUserQuestion (path or paste).
- Ask for essay type (`research | personal | application | other`) only if it was not given and the skill needs it. Never ask for facts that can be found on disk.
- Paragraph map: `python3 ${CLAUDE_SKILL_DIR}/scripts/shared/extract_paragraphs.py <draft> > $RUN/paragraphs.json`. Every agent receives it; paragraph numbers in the report come from it, never from an agent's own count.

## 3. Agent rules

- **Agent type:** `Explore` (read-only; no Edit/Write) for every analysis, challenger and presentation agent. An edit-capable agent must never be used to review a draft. The orchestrator, not the agent, writes each agent's returned text to `$RUN/<agent-name>.md`.
- **Prompt skeleton** (one prompt per check, composed from the skill's brief file read in full and pasted verbatim, never summarised):
  1. Role line and "report only; do not rewrite passages or write files".
  2. `Read <draft path> in full.` (If lines begin `- `, they are Logseq bullets: treat as prose.)
  3. Essay type and PARAGRAPH MAP.
  4. Verify-by-opening-words rule: before writing `Location: paragraph n`, find the paragraph's first 4–6 words in the map and use the map's number.
  5. Any prescan data the check needs (JSON from `$RUN`), marked as authoritative: agents judge it, they do not recompute it.
  6. The brief, then its exact output format.
- **Pair-blindness:** when a check runs as an A/B pair, write one prompt and dispatch it twice under two names. Do not tell either agent about the other.
- **Names:** `<Skill><Check>-A-<run>` and `-B-`. Dispatch independent agents in one message, in parallel.
- **Coverage:** an agent whose output has neither a `## Finding` nor a `## No findings` section counts as failed. Re-dispatch once; if it fails again, record "agent unavailable" for that check and say so in the report header.

## 4. After agents return

1. Save each raw output to `$RUN/<agent-name>.md`.
2. `python3 ${CLAUDE_SKILL_DIR}/scripts/shared/correct_finding_locations.py <draft> $RUN/<agent>.md --flag-unmatched --out $RUN/<agent>-corrected.md 2> $RUN/<agent>-corrections.log` — overwrites paragraph numbers with the draft's own and marks findings whose quote is not in the draft `[QUOTE-UNMATCHED]` (treated as UNVERIFIED).
3. Pair synthesis: `python3 ${CLAUDE_SKILL_DIR}/scripts/shared/synthesise_pairs.py $RUN/A-corrected.md $RUN/B-corrected.md [--exact Check] [--substring "Current text"] --out $RUN/<check>-merged.md`. If one agent failed, pass only A (or B) with `--single`. Match fields per skill are in that skill's `references/field-name-standard.md`. UNVERIFIED findings are never dropped.
4. Combine the merged files in the order the skill states and renumber `Finding 1…n`.
5. Empty list: skip the challenger and go straight to presentation with "no findings".

## 5. Challenger

Dispatch the challenger(s) with the numbered findings in full plus the skill's scope rules (state reasoning first, verdict last, one verdict label per finding, NOT ASSESSED with a reason if a finding cannot be judged). Then `python3 ${CLAUDE_SKILL_DIR}/scripts/shared/synthesise_verdicts.py $RUN/ChallengerA.md [$RUN/ChallengerB.md] --findings N` produces `Finding n: label` lines plus verbatim disputed reasons and ambiguous questions. Two confidence axes stay separate in the report: analysis confidence (HIGH / UNVERIFIED) and verdict label.

## 6. Presentation

One `Explore` agent reads the skill's `references/presentation-format.md` and `assets/report-header-template.md`, receives the findings, verdict lines and status notes, and returns the whole report as its response. The orchestrator relays it verbatim; no summary, no truncation. If it fails twice, the orchestrator renders the report itself from the same inputs.

## 7. Save and cleanup

Reports quote the writer's essay, so saving is opt-in: only if the writer says "save that", ask where (suggest next to the draft) and write the report there. Then remove `$RUN`.

## 8. Output rule

Show one short progress line after each dispatch round. Do not narrate synthesis. Allow AskUserQuestion only for missing inputs and for the scope gates a skill names.
