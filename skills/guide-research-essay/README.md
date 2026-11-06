# guide-research-essay

## What this skill does

A coach for research essays. It guides you through reading a source, planning an essay and drafting it by asking one question at a time, quoting the page, and checking what you wrote against your own sources and notes. You do all the thinking and writing. It never writes, rewrites or suggests any of your text.

- **Reading for a research question** — trigger: "guide me through this reading for my question" → steps: you name the question, Claude asks what the text says on it, you explain, Claude checks your explanation against the page → result: your own understanding, tested against the source.
- **Reading in general** — trigger: "help me read this" → steps: questions before reading, close reading of a passage you pick, your explanation checked → result: a reading you understand.
- **Outline** — trigger: "check my outline against my notes" → steps: brief check, your position in your own words, structure questions, budget sum, evidence check → result: a list of flagged gaps for you to fix.
- **Draft** — trigger: "check this paragraph against my notes" → steps: purpose question, support, link and exactness checks, open gaps listed → result: a list of differences from your notes, none corrected.

## Intent

Built so that the user, not the tool, does the intellectual work. It optimises for understanding, synthesis and use of a source towards the user's own argument, and trades away convenience: it will not give a sample sentence, an outline, a summary or a fix, however nicely asked. Every critique quotes the page or the user's note so the user can verify it. It reads the user's own AI-rules file at run time and stops where that file says no AI or says nothing, so no module, assessment, field or research focus is written into the skill. Nothing is offered at the end of a reply.

## When to use / When NOT to use

**Use when:** you ask to be guided through a reading, an outline or a draft section, or want to know whether your outline or paragraph is supported by your notes.

**Don't use when:** you want text written or rewritten (it declines), spelling and grammar fixed, a whole-draft review, or plagiarism or AI-detection checks; use the matching skill instead.

## How to invoke

- Slash command: `/guide-research-essay [mode] [file]`, where mode is `reading-question`, `reading-general`, `outline` or `draft`.
- Natural language: "guide me through this reading for my research question", "help me read this", "check my outline against my notes", "add up my outline's word budgets", "is this paragraph supported by my notes", "list the gap markers in my draft", "probe my seminar questions", "help me get started without writing it for me".
- It needs your AI-rules file: it finds it through the profile key `ai_rules_file` (profile found through `$GUIDE_PROFILE`), or a path in your message, and reads it first on every use. The optional profile key `use_log_file` is where use-record rows are appended.

Example: you paste your notes and a paragraph you wrote and say "draft mode: check this against my notes". It quotes each place your paragraph says more than a note, lists your open gap markers, and asks one question. It changes nothing.

## Features & modes

Before any mode runs, the skill reads your own AI-rules file (the markdown file saying what AI help is allowed for each assessment). It stops if the file says no AI or is unclear about that kind of help; in the unclear case it quotes the file's wording and waits for your typed okay. It never writes text for you in any mode. Outline and draft modes need something you have already written.

- **Reading for a research question.** You name a question. It reads the real source, asks what the text says on it, then checks your own explanation: each claim is marked supported (with a quote), stronger or wider than the text, or not found on the cited page. It also asks for a counter-reading and which passage shows how the reading bears on your question. Trigger: `/guide-research-essay reading-question [file]`, or "guide me through this reading for my question".
- **Reading in general.** The same method with no question named. Also: close reading of a passage you pick, questions before reading, a concept map you draw (it asks about missing links), and seminar prep where you write the questions and it probes them. It teaches a reading technique once, only if you ask, and installs nothing without your okay. Trigger: `/guide-research-essay reading-general [file]`, or "help me read this".
- **Outline.** On an outline you wrote, with your notes and the brief: brief check, position prompt (where is your position stated; never a new thesis), structure prompts, a budget check (a script adds up the "N words" budgets against your limit and stated total), an evidence map (supported, stronger than the note, or no support found), and unused notes. Trigger: `/guide-research-essay outline [file]`, or "check my outline against my notes".
- **Draft.** On a paragraph or section you wrote: paragraph purpose, support check, link check (unstated "therefore" and "because"), exactness check (numbers, names, dates, quotes; differences listed, none corrected), gap list, a built-from trace and a length check. Trigger: `/guide-research-essay draft [file]`, or "check this paragraph against my notes".
- **Stuck prompts (outline and draft).** If you cannot begin, it asks only questions, such as which note is nearest to a claim. It never offers a sentence, heading or opening.
- **Use record.** If your rules file requires a use to be acknowledged, you get one row for your use log; the acknowledgement is yours to write and place.

It declines to write, rewrite or suggest any of your text, to give praise or scores, to quiz you, or to help text pass as unassisted. Every point quotes the page or your note, your files are never edited, and each reply ends with a single question and no suggested next step.

## Structure

- `SKILL.md`: the workflow the skill follows: rules, the AI-rules gate, the four modes, reply shape, use record, limitations.
- `references/glossary.md`: the skill's own terms with one-line definitions.
- `scripts/budget_check.py`: adds the "N words" budgets in an outline (`--limit N`) and counts words in a file (`--count`); prints JSON. It only adds and counts; judging proportion is the coaching conversation. Tests are in `tests/`.
- `evals/`: the test prompts and invented fixtures used to evaluate the skill.
- Outputs: nothing is written to your files, and there is no ledger. The only write is one use-record row appended to your `use_log_file` if you set one.
- No module, assessment, field or research focus belongs in any file of the skill; those limits come from your own rules file at run time.

## How to install

Copy the `skills/guide-research-essay` folder from https://github.com/Vaikri-costume/skills into `~/.claude/skills/guide-research-essay/`, then confirm with `/guide-research-essay` in a new session.

## Sibling skills

Separate requests, not offered by this skill: `proofread` (grammar and spelling), `review-writing` (whole-draft review), `plagiarism-check` and `ai-detection-check` (originality checks).

## For developers

The runtime workflow lives in [`SKILL.md`](SKILL.md). Provenance and changelog live in [`HISTORY.md`](HISTORY.md). To trace this skill for bugs: `/skill-tracer guide-research-essay`. Credit: ideas adapted from Writing Desk 0.1.0 by Naji Kayal (Apache-2.0), rewritten; no text copied.
