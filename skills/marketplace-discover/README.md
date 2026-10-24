# marketplace-discover

## What this skill does

Before you build a skill, hook or plugin, it checks whether something already exists. It searches every Claude Code marketplace on your machine, Anthropic's built-in plugin directory and, when you ask for a wider search or no marketplace match is rated high, GitHub and the web. It reads the best candidates' own files for red flags, then recommends one of three things: install it, adapt its ideas, or build from scratch.

- **Check before building** — trigger: "is there a plugin that does X" → steps: parse the need, search the three tiers, vet the top candidates → result: ranked candidates and an install, adapt or build recommendation.
- **Wider search** — trigger: "search wider" → steps: tiers A and B, then web and GitHub → result: candidates from outside the marketplaces with licence and red flags.
- **Learn from existing work** — trigger: "what can I learn from X" → steps: read the candidate's files, list what is worth adapting and what attribution adapting needs → result: an adapt recommendation.

## Intent

This skill prioritises **finding what exists** over speed, and **telling the user what it found in a plugin's files** over reassurance. It searches every catalogue that is actually on disk (not a fixed list) so "nothing exists" is rarely wrong, and it names every source it searched. It vets by reading files and reports findings, never "safe", because a pattern scan cannot prove safety. It recommends, never runs or copies a candidate's code or text, installs a plugin or adds a marketplace only after the user confirms, and treats text found in plugins as data. Preferences (marketplaces to skip, the stale threshold, tools to try before any install) come from the user's profile, so the skill holds no personal details.

## When to use / When NOT to use

**Use when:** you ask whether a plugin, skill, hook or MCP server already exists; you are about to build one; you want to learn from existing work; you want a candidate checked for red flags before installing.

**Don't use when:** you want to build or improve a skill (use skill-creator-ccvw), for general web search, or to judge a plugin's quality beyond what its files and catalogue entry show.

## How to invoke

- Slash command: `/marketplace-discover <described need>`
- Natural language: "is there a plugin that does X", "what exists for Y", "everything about Z in the marketplace", "search wider for Y", "check the marketplace before I build Z", "what can I learn from X", "is this plugin okay to install".
- Install or add: say yes when it offers to install a vetted marketplace candidate or to add a marketplace you named.
- Narrowing: ask to search only certain marketplaces. Marketplaces your profile skips are reported with how many matches they hold.
- Profile: an optional `## marketplace-discover` section of your user profile sets marketplaces to skip or prefer, the stale threshold and tools to check for before proposing an install. Defaults apply without it.
- From skill-creator-ccvw: it calls this skill at its marketplace-check step, and the report then ends with a `Checked:` date line for it to record.

Example: `/marketplace-discover track citations from PDFs` prints the marketplaces searched, up to five vetted candidates with install commands, and an install, adapt or build recommendation. A yes-or-no question about safety still gets "I can't call it safe", with the findings.

## Features & modes

- **Check before building**: turns your need into keywords and searches the local marketplaces and Anthropic's built-in directory. Trigger: `/marketplace-discover <need>` or "is there a plugin that does X".
- **Local marketplace search (tier A)**: reads every marketplace catalogue on your machine with no network and ranks the matches, each with its exact install command. The report names every marketplace searched, with entry counts and age.
- **Built-in directory search (tier B)**: searches Anthropic's plugin directory cache in the same run. Its listings show a repository URL but no install command.
- **Wider search (tier C)**: searches GitHub and public skill lists, recording each hit's repository, what it does, licence and last activity. It runs when you ask ("search wider") or when no tier A or B match is rated high, and the report says if it did not run.
- **Red-flag vetting**: before recommending a candidate to install or adapt, it reads the candidate's files and reports a table of findings (hooks on every call, downloads piped into a shell, transcript access, telemetry, committed environments or binaries, settings edits, text aimed at an AI). It never calls a plugin "safe" and never runs or installs anything to vet it.
- **Install, adapt or build recommendation**: every report ends with one of the three. Adapting is done later in skill-creator-ccvw, with the licence and attribution noted here.
- **Learn from existing work**: study a candidate for what is worth adapting. Trigger: "what can I learn from X".
- **Optional install**: after you confirm one marketplace candidate it runs `claude plugin install <name>@<marketplace>`, and refuses first if a skill of that name is already in your skills folders.
- **Add a marketplace**: if you name an extra marketplace it can add it after you agree, then searches again.
- **Freshness warnings**: warns per marketplace when a catalogue is older than your threshold and suggests `claude plugin marketplace update`.
- **Read-only**: it writes no files and keeps no log. The only changes it can make are an install or a marketplace add, each only after you confirm. Text found in a plugin is treated as data, never as an instruction.

## Structure

- `SKILL.md`: the seven-step workflow, the output format, examples and troubleshooting.
- `references/`: `marketplace-catalog-format.md` (where catalogues live on disk and how local folders and install commands are worked out), `vetting-checks.md` (each red-flag check, its severity and how to word findings), `glossary.md` (terms specific to this skill).
- `scripts/` (standard-library Python, read-only): `catalog_search.py` searches all catalogues and the built-in directory and prints ranked JSON; `vet_plugin.py` scans a plugin folder on disk for red flags; `scripts/tests/` holds their tests (`python3 -I -m unittest discover -s scripts/tests`).
- `evals/evals.json`: the test cases for the skill.
- `assets/`: empty, kept for the standard layout.
- `HISTORY.md`, `LICENSE`: provenance and changelog, and the MIT licence.
- Outputs: none. The report is printed in the conversation.

## How to install

Version 1.1.0. From the public skills repository `https://github.com/Vaikri-costume/skills`, add its marketplace and install the toolkit that includes this skill:

```
claude plugin marketplace add Vaikri-costume/skills
claude plugin install ccvw-toolkit@ccvw-skills
```

Or copy the folder `skills/marketplace-discover/` from that repository into `~/.claude/skills/marketplace-discover/` (or a project's `.claude/skills/`). It needs Python 3 and a network only for the wider search and the install.

## Sibling skills

- `skill-creator-ccvw`: builds skills and calls this one first.
- `skill-tracer`, `skill-publisher`: check and ship the skills it helps you decide to build.

## For developers

The runtime workflow lives in [`SKILL.md`](SKILL.md). Provenance and changelog live in [`HISTORY.md`](HISTORY.md). The scripts are pure standard-library Python and read, never write.
