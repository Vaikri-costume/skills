# Dispatch protocol

The run-folder, agent, synthesis and presentation mechanics below apply to this skill; SKILL.md names the section each Run step uses. Paths are relative to the repository root (`${CLAUDE_PROJECT_DIR}`); shared scripts live in `${CLAUDE_SKILL_DIR}/scripts/shared/`.

## 1. Run folder

`python3 ${CLAUDE_SKILL_DIR}/scripts/runfolder.py new [<scratch_dir>]` creates a fresh folder (under the profile's `scratch_dir`, else the system temporary directory) and prints its absolute path. Throughout this skill `<run>` stands for that path: type the absolute path itself into every command. Never create a shell variable for it or for the skill folder (`${CLAUDE_SKILL_DIR}` is the skill's own folder: type its absolute path too). Every script step below is one plain `python3` command: to save a script's output use `python3 ${CLAUDE_SKILL_DIR}/scripts/tofile.py <out file> <script> <args>` instead of a shell redirect, so no step needs a pipe, a redirect or a compound command.

Nothing is written next to the draft or into any memory folder during a run. When the report has been delivered, delete the run folder with `python3 ${CLAUDE_SKILL_DIR}/scripts/runfolder.py remove <literal absolute path>` (it refuses anything that is not a plagiarism-check run folder). If the session is compacted mid-run, the run folder is still on disk: list it, read the newest agent outputs, and carry on from the last step whose output file exists. There is no resume question and no state machine.

## 2. Input

- **File path given:** use it. **Pasted text:** write it to `<run>/draft.md`, then `python3 ${CLAUDE_SKILL_DIR}/scripts/shared/strip_markers.py <run>/draft.md` (removes Logseq bullet markers). **Neither:** ask once with AskUserQuestion (path or paste).
- Ask for essay type (`research | personal | application | other`) only if it was not given and the skill needs it. Never ask for facts that can be found on disk.
- Paragraph map: `python3 ${CLAUDE_SKILL_DIR}/scripts/tofile.py <run>/paragraphs.json ${CLAUDE_SKILL_DIR}/scripts/shared/extract_paragraphs.py <draft>`. Every agent receives it; paragraph numbers in the report come from it, never from an agent's own count.

## 3. Agent rules

- **Agent type:** `Explore` (read-only; no Edit/Write) for every analysis, challenger and presentation agent. An edit-capable agent must never be used to review a draft. The orchestrator, not the agent, writes each agent's returned text to `<run>/<agent-name>.md`.
- **Prompt skeleton** (one prompt per check, composed from this skill's brief file read in full and pasted verbatim, never summarised):
  1. Role line and "report only; do not rewrite passages or write files".
  2. `Read <draft path> in full.` (If lines begin `- `, they are Logseq bullets: treat as prose.)
  3. Essay type and PARAGRAPH MAP.
  4. Verify-by-opening-words rule: before writing `Location: paragraph n`, find the paragraph's first 4–6 words in the map and use the map's number.
  5. Any prescan data the check needs (JSON from `<run>`), marked as authoritative: agents judge it, they do not recompute it.
  6. The brief, then its exact output format.
- **One judgement agent per source:** confidence comes from the challenger's check against the texts.
- **Names:** `PlagSource-<slug>-<run>`, `PlagChallenger-<run>`, `PlagPresent-<run>`. Dispatch independent agents in one message, in parallel.
- **Coverage:** an agent whose output has neither a `## Finding` nor a `## No findings` section counts as failed. Re-dispatch once; if it fails again, record "agent unavailable" for that check and say so in the report header.

## 4. After agents return

1. Save each raw output to `<run>/<agent-name>.md`.
2. `python3 ${CLAUDE_SKILL_DIR}/scripts/shared/correct_finding_locations.py <draft> <run>/<agent>.md --flag-unmatched --out <run>/<agent>-corrected.md` — overwrites paragraph numbers with the draft's own and marks findings whose quote is not in the draft `[QUOTE-UNMATCHED]` (treated as UNVERIFIED).
3. Combine: concatenate the corrected findings in source order and renumber `Finding 1…n`. Findings marked `[QUOTE-UNMATCHED]` are never dropped.
4. Empty list: skip the challenger and go straight to presentation with "no findings".

## 5. Challenger

Dispatch one challenger with the numbered findings in full plus the rules in `challenger-synthesis-rules.md`. Then `python3 ${CLAUDE_SKILL_DIR}/scripts/shared/synthesise_verdicts.py <run>/Challenger.md --single --findings N` produces `Finding n: label` lines (upheld, disputed, ambiguous, unaddressed) plus verbatim disputed reasons and ambiguous questions.

## 6. Presentation

One `Explore` agent reads `references/presentation-format.md` and `assets/report-header-template.md`, receives the findings, verdict lines and status notes, and returns the whole report as its response. If it fails twice, the orchestrator renders the report itself from the same inputs.

**Report check.** Save the report to `<run>/report.md`, run `python3 ${CLAUDE_SKILL_DIR}/scripts/report_lint.py <run>/report.md` (in reference-check mode add `--refs <run>/verdicts.json`), fix each problem by editing the file (never re-dispatch the presenter), and run it again. Relay the report verbatim, no summary and no truncation, only when it exits 0.

## 7. Save and cleanup

Reports quote the writer's essay, so saving is opt-in: only if the writer says "save that", ask where (suggest next to the draft) and write the report there. Then remove the run folder (section 1).

## 8. Output rule

Show one short progress line after each dispatch round. Do not narrate synthesis. Allow AskUserQuestion only for missing inputs and for the scope gates a skill names.
