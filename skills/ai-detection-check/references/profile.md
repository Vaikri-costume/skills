# The writer's profile: what ai-detection-check reads from it

The skill holds no personal, course or institution details. Everything specific to the writer is read at run time from their profile, a markdown file with bullets of the form ``- `key`: value``.

## Where the profile is

In this order: the file named by the environment variable `CCVW_USER_PROFILE`; else the first `config/user-profile.md` found walking up from the working directory; else a profile entry in the user's Claude memory index. A missing profile, or a missing key, is not an error: use the default in the table and carry on. Ask the writer only for a fact the run cannot continue without.

## Keys this skill reads

| Key | Meaning | Default when absent |
|---|---|---|
| `vocabulary_register` | Path to a file listing 10–20 terms that are standard in the writer's field | none: no extra vocabulary |
| `session_log_dir` | Folder for the optional one-line session-log marker | none: write nothing |
| `scratch_dir` | Folder the run folder is made under | the system temporary directory |

## Optional inputs named per run

- **Baseline:** the writer's own earlier texts (file paths) for a descriptive comparison; about 1,000 words in total. Never fetched or assumed; never stored.
- **Source texts** (`LABEL=PATH`): for quotation verification. Without them the quotation check reports "no source supplied".
- **Vocabulary register:** the key above, or 10–20 terms the writer types; the challengers may suggest terms, and nothing is saved without the writer saying where.
