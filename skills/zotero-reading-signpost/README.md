# Zotero Reading Signpost

## What this skill does

Makes dense academic reading legible without doing the reading for you. Claude reads the real PDF chapter in Zotero, states the argument the text makes, ties each phrase and term of it to the source words that say it, and writes a short summary from those phrases in the text's own order. You approve the summary and the highlight plan together; then they become a note and light-brown highlights in the PDF. You read with that scaffolding in place, add your own annotations, and write your own summary.

- **Chapter signposting**: trigger "summarise and signpost this chapter" → steps: check tools, check the PDF has text, confirm it is the right text (only speaks if not), read the whole chapter, state the argument as points, break each point into phrases and terms and highlight each one's passage, drop what repeats, order them by where they sit in the text, write the summary from them in that order, check it and fix only what fails, approve the summary and plan together, then write the note in your Signpost Summary layout and highlight each phrase in `#c9a27a` → result: an approved summary note plus one highlight per phrase or term.
- **Module reading lists**: trigger "work through this week's readings" → steps: pick readings from the module list, one at a time, same workflow with a checkpoint each → result: signposted readings ready to study.
- **Book, section by section**: trigger "do this book chapter by chapter" → steps: the chapter workflow, pausing for approval after each → result: a signposted book without a single giant pass.

## Intent

This skill prioritises **your own understanding over speed**, and follows your own process step by step: the argument as points first, then the passage behind each phrase and term, and the summary written last, from those phrases in the order the text makes them, so every claim stays pinned to a passage and means what the text does. One approval before anything is written, one source at a time, verbatim passages and per-phrase highlights exist so you can check Claude's reading rather than take it on faith. Fixes that skip a gate, batch several chapters, or let Claude overwrite your annotations trade away the point of the method and need human judgment. Your own words are never edited or deleted; Claude only adds to them.

## When to use / When NOT to use

**Use when:** you have a PDF in Zotero, a dense text you want to read critically, and the Zotero MCP is connected.

It adds nothing beyond the text: no gloss, no inference, no follow-up reading, no questions, no offers, and no artificial limits on the number of highlights or the note's length (the summary has a suggested length).

**Don't use when:** you want bulk library clean-up or tag changes, metadata or citation fixes, a finished essay or your own summary written for you.

## How to invoke

- Slash command: `/zotero-reading-signpost <item key, citation key or title>` (optionally with a purpose)
- Natural language: "summarise and signpost chapter 3 of this book", "turn the AI summary on this paper into annotations", "prepare this week's reading for the module"

Example: "signpost chapter 1 of <citation key>" → Claude reads the chapter pages, shows the summary and the phrase-to-passage plan together, waits for your approval, then writes the note, creates the highlights, checks them, and stops for your go-ahead.
- Dry run: add "as a dry run" to the request; it runs up to the plan approval and writes nothing.
- Chapter or page range: name it with the item, e.g. "signpost pages 40 to 62 of <citation key>".
- Purpose: say it in the request, e.g. "signpost this for my essay on X"; it decides what the summary emphasises.
- Module reading list: "work through this week's readings"; one reading at a time, with an AI-rules stop for assessed readings.
- Book chapter by chapter: "do this book chapter by chapter"; the approval of each chapter's summary and plan stays.
- Whole book on: "run the whole book on" lifts only the end-of-chapter stop.
- Several PDF attachments: name the one to use in the request or the reading-list entry.
- Resume: ask again for the same item or chapter to continue an unfinished run; a finished run starts a new dated run.
- First run: the skill asks once for any profile value it needs and lacks (colour, summary length cap, library and write lane, module locations), then saves the answers.

## Features & modes

- **Single chapter or article signposting (default)**: Claude reads the real PDF pages of one chapter or article in Zotero. It states the text's argument as points, finds the exact source words behind each phrase and term, and writes a short summary from those phrases in the text's own order. Once you approve, it adds a Signpost Summary note and light-brown (`#c9a27a`) highlights. Trigger: name an item (item key, citation key or title), optionally with a chapter or page range, e.g. "signpost chapter 3 of <citation key>", "prepare this reading", or `/zotero-reading-signpost <item>`.
- **One approval (the gate)**: you see the summary, the highlight plan table and the check table together. Nothing goes into Zotero until you approve them. The summary aims at about 15% of the word count of the pages summarised; this is a guide, both counts are reported and no evidence is cut to fit. If you disagree, Claude goes back to the stage your objection points at (the argument, the item, the pages, or the plan or summary), then shows the gate again; only an approval of the version shown counts. Trigger: automatic in every run.
- **Purpose-aware summary**: a purpose named in your request decides what the summary emphasises from the text. Without one you get a plain statement of the argument, and Claude never asks about purpose. Trigger: say the purpose in the request.
- **Signpost Summary note**: after the gate, a Zotero note is written on the item with the approved summary, marked `writer:: Claude` once in its header, and read back to confirm it matches. Existing Gemini or NotebookLM notes are never replaced or deleted. Trigger: automatic after the gate.
- **Phrase-by-phrase highlights**: each phrase or term becomes one highlight on the smallest passage that proves or explains it (a term's highlight is its definition). The comment is only the phrase or term, and a phrase whose words another highlight already covers gets none. A passage that crosses a page break gets one highlight per page. Trigger: automatic; you see every planned highlight in the plan table (comment, exact quote, physical page, printed page label) before it is made.
- **Understanding check**: before you see the plan, Claude grades it and the summary against your rules and runs them through `plan_check.py`. The questions are whether comment and highlight are the same words, whether an easier phrase would do, and whether the highlight shows why the point is true. What fails is fixed; anything still failing is listed under "Could not fix", and the counts are reported. Trigger: automatic.
- **Verbatim anchoring**: every quote is checked against the PDF's own text, in more than one extraction order, so highlights land on the source's exact words. A phrase that cannot be anchored is never guessed: its point moves to another passage that makes it, and comes out only if no passage does; the report lists it. Trigger: automatic.
- **Scanned or garbled PDFs (OCR)**: a PDF with no usable text layer is OCR'd into a new attachment; the original file is never replaced. Highlights then go on the OCR copy. Trigger: automatic when the text check fails or quotes will not anchor.
- **Existing-annotation handling**: your own annotations are never recoloured or deleted, and what you wrote is only added to. If a planned quote lies within one of your highlights, Claude's comment goes above a `---` divider and your comment stays verbatim beneath, with your colour kept. Partial overlaps, quotes spanning several of your annotations, annotations on another PDF attachment, and signposts from earlier runs are marked in the plan table, and your approval decides. Trigger: automatic whenever your annotations overlap the plan.
- **Dry run**: runs every step up to the gate and writes nothing to Zotero; it lists the planned note and any planned OCR attachment instead. The working files and report are still written. For a taught-module reading it still records the AI use in the module's AI-rules file, marked "dry run". Trigger: add "as a dry run" to the request.
- **Verify and checkpoint**: after writing, Claude re-reads the item's annotations, confirms one highlight per planned phrase on the planned page, in the signpost colour and with its comment, reports any difference, then stops after the chapter. Trigger: automatic.
- **Resume**: each run saves its working files stage by stage in `signpost-work/<attachment key>/`. If a run stops partway, a new request on the same item continues from the first missing stage; after an approved gate it carries on from the first planned write not yet in Zotero, so nothing is written twice. A finished run is never reopened: a new request on a finished item starts a new run in a dated subfolder. Trigger: automatic; ask again for the same item or chapter.
- **Module reading list**: readings come from the module's reading-list collection; only the ones you ask for are processed, in the order given, one at a time, with the week or session announced. Before any taught-module reading, Claude checks the project's AI-rules record for that module and stops for your typed okay when the reading is tied to one assessed piece. Items with no PDF are listed for the module's owner. Trigger: "work through this week's readings".
- **Whole book or edited volume**: one chapter or section at a time with the full workflow and a checkpoint each time. "Run the whole book on" lifts only the end-of-chapter stop; the gate still applies to every chapter. Trigger: "do this book chapter by chapter".
- **Several PDF attachments**: if the item has more than one PDF, the one to use comes from your request or the reading-list entry. Trigger: name the attachment in the request.
- **Shared-library safety**: in a group or shared library, writes stay inside the lane the project grants, and Claude tells you before the first write that collaborators will see it. Trigger: automatic.
- **First-run profile**: your colour, summary length cap, library and write lane, and module AI-rules and reading-list locations come from a profile file. Claude asks once for any value it needs and lacks, then saves the answer. Trigger: automatic on first use.
- **Limits by design**: no subagents. No tags, collections, plugins or settings are touched, and nothing is deleted. It runs only when asked and makes no unasked offers. There are no artificial limits on the number of highlights or the note's length.

## Structure

- `SKILL.md`: the runtime workflow Claude follows (steps 0 to 15), its rules and the output contract; the source of truth.
- `README.md`: this user-facing overview. `HISTORY.md`: provenance and changelog. `LICENSE`: MIT.
- `references/`, loaded on demand and grouped by theme:
  - Read on every run: `method.md` (the Signpost Summary note layout, how to anchor a quote, the pass 3 understanding check and its tests, how to resume a run) and `rules.md` (the Zotero workflow rules, write lanes, and a capability table that matches each Zotero action to the live tool that provides it).
  - Case-only: `cases.md`, numbered sections read one at a time only where a step names them (the taught-module AI-rules gate, several PDF attachments, scans and OCR, existing annotations, dry run, books and reading lists, creation failures, the Signpost colour in Zotero, conditional report fields, shared or group library lanes, collections and tags, existing AI-summary notes, the patch log, case-only Zotero actions, worked examples of the pass 3 tests).
  - Setup: `profile-template.md` (the per-user profile).
  - Terms: `glossary.md` (maintainer reference, not read at runtime).
- `scripts/`, deterministic helpers run as `python3 -I <skill folder>/scripts/<script name>`:
  - Used by steps of the workflow: `anchor_check.py` (each planned quote exists verbatim in the page text), `plan_check.py` (the plan and summary checked together: not placed, order, overlaps, terms, comment length, same claim, negation, missing, tandem, wording, links), `cap_check.py` (the summary's length against the cap), `context_check.py` (the sentence before and after each highlight), `note_html.py` (the note's HTML).
  - Optional tools, called by no step: `copy_check.py` (summary clauses that copy the source), `term_check.py` (summary words the source never uses), `pin_check.py` (summary stretches with no highlight comment behind them), `tandem_check.py` (every highlight comment appears in the summary; `plan_check.py` already covers it).
  - `scripts/tests/`: unit tests for these scripts.
- `evals/evals.json`: eval prompts for measuring the skill.
- `assets/`: present but empty; the only template is the profile template.
- Outputs: the skill writes no files into its own folder.
  - Working files: each run keeps them in `signpost-work/<attachment key>/` in your working folder (the pages in scope, any OCR copy's key, page texts, the argument as points, the plan, the summary, the checks with the keys of the highlights made, and the report), written stage by stage. A book gets one subfolder per chapter, and a later run on a finished item gets its own dated subfolder.
  - Profile: `config/zotero-reading-signpost-profile.md`, or the path your project names.
  - Zotero: the Signpost Summary note, any OCR attachment and the highlights.
  - Taught modules: a taught-module reading also adds an entry to the module's AI-rules use log.
  - Chat: the report.

## How to install

Version 2.0.0. Install from the public skills repository by copying the folder `skills/zotero-reading-signpost/` from `https://github.com/Vaikri-costume/skills` to `~/.claude/skills/zotero-reading-signpost/` (or a project's `.claude/skills/`). It needs a Zotero MCP server that can read PDF pages and write notes and annotations. On the first run the skill reads your profile (`config/zotero-reading-signpost-profile.md`; template in `references/profile-template.md`), asks for any value it needs and does not find, and writes the answers back to the profile.

## Sibling skills

- `skill-creator-ccvw`, `skill-tracer`, `skill-publisher`: build, audit and ship.

## For developers

The runtime workflow lives in [`SKILL.md`](SKILL.md). Provenance and changelog live in [`HISTORY.md`](HISTORY.md). To trace this skill for bugs: `/skill-tracer zotero-reading-signpost`. To ship a new version: `/skill-publisher zotero-reading-signpost`.
