# The writer's profile: what ai-detection-check reads from it

The skill holds no personal, course or institution details. Everything specific to the writer is read at run time from their profile, a markdown file with bullets of the form ``- `key`: value``.

## Where the profile is

In this order: the file named by the environment variable `CCVW_USER_PROFILE`; else the first `config/user-profile.md` found walking up from the working directory; else a profile entry in the user's Claude memory index. A missing profile, or a missing key, is not an error: use the default in the table and carry on. Ask the writer only for a fact the run cannot continue without.

## Keys this skill reads

| Key | Meaning | Default when absent |
|---|---|---|
| `ai_rules` | Path to the file that records the course's AI rules for each assessment | none: if the draft is coursework and no rule can be found, ask once which rule applies |
| `vocabulary_register` | Path to a file listing 10–20 terms that are standard in the writer's field | none: no extra vocabulary |
| `session_log_dir` | Folder for the optional one-line session-log marker | none: write nothing |
| `scratch_dir` | Folder the run folder is made under | the system temporary directory |

## Reading the AI rules (the gate)

This skill runs only when the writer asks for it in that message; it is never offered. Read the rules file fresh each run (it records each assessment's AI level, the kinds of permitted use and any decision log). If the draft belongs to coursework:

1. Name the assessment the work feeds and what this skill would do with it: study support (S), feedback on the writer's own work (F) or generating for the assessment (G).
2. G is never allowed and this skill never generates assessed text. When the rule for the assessment bans AI feedback, says nothing, or is unclear, stop and say why in one short message. Do not read an unclear rule in the writer's favour. Carry on only when the rule allows feedback on the writer's own work, or the writer confirms in this conversation that it does.
3. Where the rule asks the writer to record AI use, say so in the report's last line so they can reuse it.

Work that is not coursework (an application, a blog post, a funding text) skips the gate. This skill checks the writer's own writing; it is not covered by a rule that allows language feedback only, so on coursework the writer's confirmation is asked for each time unless the rules file records it.

## Optional inputs named per run

- **Baseline:** the writer's own earlier texts (file paths) for a descriptive comparison; about 1,000 words in total. Never fetched or assumed; never stored.
- **Source texts** (`LABEL=PATH`): for quotation verification. Without them the quotation check reports "no source supplied".
- **Vocabulary register:** the key above, or 10–20 terms the writer types; the challengers may suggest terms, and nothing is saved without the writer saying where.
