# plagiarism-check

## What this skill does

Checks a draft for plagiarism risk before submission and reports in SOAS misconduct-procedure terms (SOAS's public policy is a worked UK higher-education example; adapt category names and thresholds to your own institution's policy): unmarked verbatim overlap with sources, close paraphrase, summary instead of synthesis, unattributed frameworks, self-plagiarism, and citation integrity.

- **Citation check** — trigger: "check for plagiarism" → steps: find cited works, overlap script, citation and quote audits, one judgement agent per source, challenger, report → result: flags by SOAS category and weight, plus a citation-integrity checklist.
- **Self-plagiarism check** — trigger: supply earlier submissions → steps: overlap against those files → result: reuse percentage and locations (SOAS §2.6).

## Intent

Categories and weights follow SOAS University of London's public misconduct policy as a worked UK higher-education example; adapt the category names and thresholds to your own institution's policy. Scripts find, agents judge, a challenger verifies against the texts. It reports flags, not accusations, and says every time what it cannot do: it compares only the sources it is given and cannot replace the Turnitin similarity report. Overlap thresholds (6 words verbatim, 4 to 5 weak) are heuristics because SOAS and QAA publish none. Voice comparison with the writer's past work was removed (an authorship question) and quote-integration moved to review-writing.

## When to use / When NOT to use

**Use when:** a research essay that engages sources closely, before submission.

**Don't use when:** authorship or AI-style questions (use ai-detection-check); argument feedback (use review-writing).

## How to install

Source: `skills/plagiarism-check` in https://github.com/Vaikri-costume/skills. Needs Python 3.

- **Claude Code**: copy the `plagiarism-check/` folder to `~/.claude/skills/plagiarism-check/` (all skills there), or to a project's `.claude/skills/plagiarism-check/` (that project only). Claude finds it automatically.
- **Cowork / claude.ai**: upload the folder as a skill. The review runs several parallel reviewer agents, so it works best where subagents are available.
- **Optional Zotero connection** (`plagiarism-check` only): to fetch the full text of cited works automatically, connect a Zotero MCP server that provides `zotero_search_items` and `zotero_get_item_fulltext`. Without it, supply a folder of source texts or the check reports those sources as "no text obtained".
- **Model notes**: smoke-tested on Haiku, Sonnet and Opus with an invented essay. Sonnet and Opus give the fullest reports; Haiku completes the run but writes a more condensed report and is less careful about stating what could not be checked, so prefer Sonnet or Opus for anything you will rely on.

## How to invoke

`/plagiarism-check [draft path]`; "check for plagiarism", "is this too close to the sources".

Example: "check essay.md for plagiarism, full-scan" -> the skill detects sources, compares against every project source, and returns a report of flags by category and weight plus a citation-integrity checklist.

Needs Python 3 for the scripts. Run the tests with `python3 -m unittest discover -s scripts/tests` from the skill folder (and `scripts/shared/tests` for the shared scripts).

## Sibling skills

- `proofread`: run it for grammar and spelling after originality fixes.
- `review-writing`: run it for argument and quote integration; this skill leaves those to it.
- `ai-detection-check`: pairs for authenticity and voice questions; this skill covers source overlap only.

## For developers

See `SKILL.md` for the run steps and `HISTORY.md` for provenance and changelog. Build, trace and ship tooling (`skill-creator-ccvw`, `skill-tracer`, `skill-publisher`) lives in https://github.com/Vaikri-costume/skills.
