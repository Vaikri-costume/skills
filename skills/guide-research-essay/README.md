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

## How to install

(Filled by skill-publisher at ship time.)

## How to invoke

- Slash command: `/guide-research-essay [mode] [file]`
- Natural language: "guide me through this reading for my research question", "check my outline against my notes", "is this paragraph supported by my notes".

Example: you paste your notes and a paragraph you wrote and say "draft mode: check this against my notes". It quotes each place your paragraph says more than a note, lists your open gap markers, and asks one question. It changes nothing.

## Sibling skills

(Filled by skill-publisher at ship time.)

## For developers

The runtime workflow lives in [`SKILL.md`](SKILL.md). Provenance and changelog live in [`HISTORY.md`](HISTORY.md). To trace this skill for bugs: `/skill-tracer guide-research-essay`. Credit: ideas adapted from Writing Desk 0.1.0 by Naji Kayal (Apache-2.0), rewritten; no text copied.
