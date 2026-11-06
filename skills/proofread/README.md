# proofread

## What this skill does

Proofreads a draft in strict British English: grammar, typos, spelling, consistency, and register quality (colloquialisms, contractions, vague quantifiers), with an optional canonical-terms file for project vocabulary (transliterations, names) and an optional style profile of the writer's own conventions. It proposes changes and never edits the draft.

- **Pre-submission proofread** — trigger: "proofread this" → steps: spelling, consistency and word-count prescans, six read-only proofreaders, challenger, tables, report → result: findings by location and type with quick wins, a was/now/why change table, a flagged-not-changed list, a register audit, a cut log and an AI-use line.
- **Word limit** — trigger: "I'm over my limit" or a stated limit → steps: word count by script, deletion-only cut candidates → result: a cut log on every run.
- **Commented copy** — trigger: "give me a copy with comments, leave my file alone" → steps: a script writes a separate file with comment lines → result: the original is untouched and the copy matches it once comments are removed.
- **Vocabulary check** — trigger: proofread with a terms file → steps: unrecognised terms looked up in the file, near-misses reported, new terms added only after confirmation → result: consistent project spellings.

## Intent

Strict British `-ise` (decided 2026-10-04): every `-ize`/`-ization`/`-yze` form is an error except words spelt `-ize` in every system (size, prize, seize, capsize, maize). Prefer the other standard British spellings. Searching is deterministic (scripts with tests); judgement about intent (consistency, register) is left to agents and a challenger; nothing is silently corrected. Quoted source spelling is never touched. The draft is never edited: every change is a proposal in a table the writer decides on, and a commented copy is a separate file. Anything personal (course rules, style conventions, terms) is read at run time from the writer's profile, so the skill itself carries no personal content. The style profile grows only from decisions the writer confirms in later runs, never from past writing. It runs when asked and never offers further checks.

## When to use / When NOT to use

**Use when:** a draft to check for errors before submission or during revision.

**Don't use when:** argument or structure feedback (use review-writing), rewriting sentences or writing text (the skill never rewrites), or code.

## How to invoke

`/proofread [draft path]`; "proofread this", "check my British spelling", "check grammar". Add the essay type ("it's a research essay"), a word limit ("1,500 words max"), "give me a copy with comments, leave my file alone", or "save the report to ..." as needed; you can also paste the draft instead of giving a path.

Worked example: say "proofread essay.md, it's a research essay". The skill runs the prescans, six read-only reviewers and a challenger, then returns findings by location and type with quick wins. Nothing in your draft is changed.

## Features & modes

proofread has one main run and a few optional extras that you switch on by what you ask for or what you give it. There are no command flags. Nothing changes your draft: every change is a proposal for you to decide on.

- **Full proofread (default)**: checks grammar, typos, strict British spelling (every -ize, -ization and -yze form is an error; quoted material is left alone), consistency and register in one pass. You get quick wins, findings grouped by paragraph, a was/now/why change table, a "flagged, not changed" list, a register audit, a cut log and an AI-use line. Trigger: "proofread this", "check my British spelling", "check grammar", or `/proofread [draft path]`. Give the essay type if you can (research, personal, application or other); it picks the register standard.
- **Research or personal register standard**: the tone and register check follows the essay type. Research essays are held to a formal academic standard; personal and application essays are judged by a standard suited to personal writing. Trigger: say the essay type, for example "it's a research essay".
- **Word limit and cut log**: the cut log is written on every run, with a word count. If you state a limit, it shows how far over you are and lists deletion-only cut candidates (filler words or phrases whose removal leaves the sentence grammatical). Trigger: "1,500 words max" or "I'm over my limit". The count includes quotations and excludes headings and the reference list.
- **Commented copy**: writes a separate file beside your draft, named `<draft name>-proofread-comments.<ext>`, with a hidden comment line after each paragraph that has a finding. The original is never touched, an existing file is never overwritten, and findings that cannot be placed are listed at the end of the copy. Trigger: "give me a copy with comments, leave my file alone".
- **Vocabulary check (terms file)**: checks unrecognised words against your list of project terms (transliterations, names). It reports wrong forms and near-misses as spelling findings, asks you once about unknown terms, and adds a term only after you confirm. Trigger: keep a `canonical-terms.md` beside the draft, give a path, or name a `terms_file` in your profile.
- **Style profile check**: if your profile names a one-page style profile, the run also flags departures from your own conventions (for example "per cent" rather than "%"). The profile grows only from conventions you confirm in later runs, never from your past writing. Trigger: set `style_profile` in your profile.
- **Course AI-rules gate**: if the draft is coursework, the skill first reads your recorded AI rules and stops, saying why, unless the rule allows language feedback or you confirm it does. Trigger: set `ai_rules` in your profile. With no profile and no coursework it carries on with the defaults.
- **Save the report**: the report appears in the conversation and is saved to a file only where you ask. Trigger: "save the report to ...".
- **Pasted text or bullet files**: you can paste the draft instead of giving a path. Files made of bullet lines are converted to ordinary paragraphs first so the paragraph numbers in the report are right. This is automatic.
- **Optional session-log line**: if your profile sets a log folder, one start line is added to that day's log. Otherwise nothing is written.

The skill runs only when asked. It never suggests further checks at the end of a report.

## Structure

- `SKILL.md`: the step-by-step run (gate, setup, prescans, six parallel reviewers, a challenger round, tables, report), with hard rules and known limits.
- `README.md`, `HISTORY.md`, `LICENSE`: the overview, the changelog and lineage, and the licence.
- `references/`: instructions loaded as a run needs them.
  - Run mechanics: `dispatch-protocol.md` (temporary run folder, dispatching and checking reviewers, combining results, saving and clean-up) and `glossary.md`.
  - Your profile: `profile.md` (where your profile lives, the keys it reads, the course AI-rules gate and the style profile).
  - Reviewer briefs: `surface.md` (grammar, typos, British spelling), `consistency.md`, and `register-research.md` / `register-personal.md` (tone and register by essay type).
  - Output contracts: `field-name-standard.md` (the fields every finding carries), `challenger-synthesis-rules.md` (how second-opinion verdicts are labelled), `presentation-format.md` (the layout of the final report).
- `scripts/`: Python helpers that do the searching and the tables, so the reviewers only judge.
  - Prescans: `check_british_spelling.py`, `check_consistency.py`, `word_count.py` (count and cut candidates), `style_check.py` (your own conventions).
  - Vocabulary and copy tools: `canonical_terms.py` (collect, check, add) and `annotate_copy.py` (the safe commented copy).
  - Report builder: `change_table.py` (change table, flagged-not-changed list, register audit).
  - `scripts/shared/`: helpers also used by the sibling writing skills (paragraph numbering, bullet stripping, quote masking, location correction, pair and verdict synthesis, citation tools).
  - `scripts/tests/` and `scripts/shared/tests/`: unit tests.
- `assets/report-header-template.md`: the report header and status notes.
- Outputs: intermediate files go in a temporary run folder that is deleted after the report. Nothing is written next to your draft except the commented copy when you ask for one.

## How to install

Source: `skills/proofread` in https://github.com/Vaikri-costume/skills. Needs Python 3.

- **Claude Code**: copy the `proofread/` folder to `~/.claude/skills/proofread/` (all skills there), or to a project's `.claude/skills/proofread/` (that project only). Claude finds it automatically.
- **Cowork / claude.ai**: upload the folder as a skill. The review runs several parallel reviewer agents, so it works best where subagents are available.
- **Model notes**: smoke-tested on Haiku, Sonnet and Opus with an invented essay. Sonnet and Opus give the fullest reports; Haiku completes the run but writes a more condensed report and is less careful about stating what could not be checked, so prefer Sonnet or Opus for anything you will rely on.

## Sibling skills

- `review-writing`: pairs after proofreading, for argument, evidence, clarity, voice.
- `plagiarism-check`: pairs as a separate pass for overlap with sources, patchwriting, citation integrity.
- `ai-detection-check`: pairs as a separate pass for authenticity review; not a detector.

## For developers

Needs Python 3. Run the tests with `python3 -m unittest discover -s ${CLAUDE_SKILL_DIR}/scripts/tests` (and `${CLAUDE_SKILL_DIR}/scripts/shared/tests` for the shared scripts). See `SKILL.md` for the run steps and `HISTORY.md` for changelog and lineage. Build, trace and ship with `skill-creator-ccvw`, `skill-tracer` and `skill-publisher` in https://github.com/Vaikri-costume/skills.

## Acknowledgements

The was/now/why change table and the flagged-not-changed list borrow ideas from Writing Desk 0.1.0 by Naji Kayal (Apache-2.0); ideas only, rewritten here, nothing copied.
