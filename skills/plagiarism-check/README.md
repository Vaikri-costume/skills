# plagiarism-check

## What this skill does

Checks a draft for plagiarism risk before submission and reports in UK university misconduct-procedure terms (adapt category names and thresholds to your own institution's policy): unmarked verbatim overlap with sources, close paraphrase, summary instead of synthesis, unattributed frameworks, self-plagiarism, and citation integrity.

- **Citation check** — trigger: "check for plagiarism" → steps: find cited works, overlap script, citation and quote audits, one judgement agent per source, challenger, report → result: flags by category and weight, plus a citation-integrity checklist.
- **Self-plagiarism check** — trigger: supply earlier submissions → steps: overlap against those files → result: reuse percentage and locations (self-plagiarism).
- **Reference check** — trigger: "check my references", named by you → steps: parse the list, cross-check it against the citations, look each entry up in Crossref and OpenAlex, claim check where the text is available → result: Clean, Fix, Not found or Review per entry, a patch log that keeps the original value, and the line that entries are checked, not verified.

## Intent

Scripts find, agents judge, a challenger verifies against the texts. It reports flags, not accusations, and says every time what it cannot do: it compares only the sources it is given and cannot replace the Turnitin similarity report. Overlap thresholds (6 words verbatim, 4 to 5 weak) are heuristics because institutions and QAA publish none. Each flag has a status (verbatim, near-verbatim, structurally derived, possibly derived) and "Clean" always means nothing found through the search used. It runs only when you ask, names no field or course, and never offers another check. Voice comparison with the writer's past work was removed (an authorship question) and quote-integration moved to review-writing.

## When to use / When NOT to use

**Use when:** a research essay that engages sources closely, before submission, or you want to know whether your reference list holds real, correctly described works.

**Don't use when:** authorship or AI-style questions (use ai-detection-check); argument feedback (use review-writing).

## How to invoke

`/plagiarism-check [mode and draft path]`; "check for plagiarism", "is this too close to the sources", "reference check on essay.md", "check essay.md against every source in sources/".

- **Mode names**: citation-check is the default; say "full-scan" to compare against every source in a folder, or "reference check" for the reference list.
- **Earlier submissions**: name the files when you ask for the check to add a self-plagiarism comparison.
- **Sources**: give a folder or text files when Zotero is not connected; with more than 8 sources the skill asks whether to judge all, only those with overlap matches, or cancel.
- **Essay type and input**: research, personal, application or other; paste the text if you have no file.
- **Lookups**: say so if you do not want references looked up; every entry then becomes Review (not looked up).
- **Saving**: say "save that" and the report is written where you choose; otherwise nothing is kept.
- **Coursework**: name the course and assessment; the skill reads your course AI rules first and stops, quoting the rule, if they ban or do not clearly allow the check.

Example: "check essay.md for plagiarism, full-scan" -> the skill detects sources, compares against every project source, and returns a report of flags by category and weight plus a citation-integrity checklist.

Run the tests with `python3 -m unittest discover -s scripts/tests` from the skill folder (and `scripts/shared/tests` for the shared scripts).

## Features & modes

It runs only when you ask for it by name. It reports flags for you to review, never findings of misconduct, and never writes or rewrites your text.

- **Citation check (default)**: compares your draft with the works it cites; each flag has a status (verbatim, near-verbatim, structurally derived, possibly derived), a category and a weight, followed by a citation-integrity checklist (quotations missing from the source, entries never cited, citations with no entry). Trigger: "check essay.md for plagiarism", "originality check".
- **Full scan**: the same check against every source in a folder or page set, not only the works the draft cites. Trigger: "check essay.md for plagiarism, full-scan".
- **Reference check**: looks each entry up in Crossref and OpenAlex and returns Clean, Fix, Not found or Review, with a patch log of proposed corrections (your original value is kept; nothing is applied), a cross-check of citations against the list and, where the source text is available, whether the work says what your draft claims. Books, reports, archives and web pages are often missing from the indexes, so they are Review, never Not found. Trigger: "are my references real", "reference check on essay.md".
- **Self-plagiarism**: add earlier submissions to a citation check or full scan.
- **Safeguards**: one read-only agent judges each source, a separate challenger checks each flag against the texts (disputed flags are shown, never dropped), and a checker confirms the report is well formed. Every report states its limits. Instructions hidden inside a draft or source are quoted in a note and not followed.

## Structure

- `SKILL.md`: the workflow: hard rules, the gate, mode choice, and the run steps.
- `references/`: rules and mechanics loaded when a step needs them: the standard and limits (`acceptable-use.md`, `misconduct-categories.md`), the profile and gate (`profile.md`), run mechanics (`dispatch-protocol.md`, `field-name-standard.md`), judging (`source-judgement*.md`, `challenger-synthesis-rules.md`), reporting (`presentation-format.md`), reference-check mode (`mode-reference-check.md`) and a glossary.
- `scripts/`: deterministic helpers: overlap detection, the reference-list check, the report check, the run-folder and save-to-file helpers; `scripts/shared/` holds source detection, citation audit, quote verification, paragraph mapping and finding-location correction; `tests/` hold the unit tests.
- `assets/`: the report header template.
- Outputs: nothing is written next to your draft; each run uses a temporary folder that is deleted afterwards.

## How to install

Source: `skills/plagiarism-check` in https://github.com/Vaikri-costume/skills. Needs Python 3.

- **Claude Code**: copy the `plagiarism-check/` folder to `~/.claude/skills/plagiarism-check/` (all skills there), or to a project's `.claude/skills/plagiarism-check/` (that project only). Claude finds it automatically.
- **Cowork / claude.ai**: upload the folder as a skill. The check runs several parallel judgement agents, so it works best where subagents are available.
- **Optional Zotero connection**: to fetch the full text of cited works automatically, connect a Zotero MCP server that provides `zotero_search_items` and `zotero_get_item_fulltext`. Without it, supply a folder of source texts or the check reports those sources as "no text obtained".
- **Optional profile**: a markdown file of ``- `key`: value`` bullets (the keys are in `references/profile.md`) lets the skill read your course AI rules and institution wording at run time. Without one it uses its defaults.
- **Reference lookups** send only each entry's title, first author, year, DOI and ISBN to Crossref and OpenAlex (never draft text); they need internet access and can be switched off.
- **Model notes**: smoke-tested on Haiku, Sonnet and Opus with an invented essay. Sonnet and Opus give the fullest reports; Haiku completes the run but writes a more condensed report and is less careful about stating what could not be checked, so prefer Sonnet or Opus for anything you will rely on.

## Sibling skills

- `proofread`: run it for grammar and spelling after originality fixes.
- `review-writing`: run it for argument and quote integration; this skill leaves those to it.
- `ai-detection-check`: pairs for authenticity and voice questions; this skill covers source overlap only.

## For developers

See `SKILL.md` for the run steps and `HISTORY.md` for provenance and changelog. Build, trace and ship tooling (`skill-creator-ccvw`, `skill-tracer`, `skill-publisher`) lives in https://github.com/Vaikri-costume/skills.
