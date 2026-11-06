# The writer's profile — what proofread reads from it

The skill holds no personal, course or institution details. Everything specific to the writer is read at run time from their profile, a markdown file with bullets of the form ``- `key`: value``.

## Where the profile is

In this order: the file named by the environment variable `CCVW_USER_PROFILE`; else the first `config/user-profile.md` found walking up from the working directory; else a profile entry in the user's Claude memory index. A missing profile, or a missing key, is not an error: use the default in the table and carry on. Ask the writer only for a fact the run cannot continue without.

## Keys this skill reads

| Key | Meaning | Default when absent |
|---|---|---|
| `ai_rules` | Path to the file that records the course's AI rules for each assessment | none: if the draft is coursework and no rule can be found, ask once which rule applies |
| `style_profile` | Path to the writer's one-page style profile | none: no extra conventions |
| `session_log_dir` | Folder for the optional one-line session-log marker | none: write nothing |
| `terms_file` | Path to the canonical-terms file | `canonical-terms.md` beside the draft, if it exists |

## Reading the AI rules (the gate)

Read the file fresh each run. Find the entry for the writer's assignment. This skill is feedback on language the writer has already written (grammar, spelling, flow, tone, consistency), never generation. Stop and say why when the entry bans AI feedback, says nothing, or is unclear for this assignment; carry on when it allows language feedback or the writer confirms in this conversation that it does. Where the rule asks the writer to reference AI use, the report's last line is the statement to reuse.

## The style profile

One page. The first section is a Quick Reference of the writer's own conventions (for example a spelling or hyphenation choice, a house term, how they write numbers); the sections after it give detail. The register agents receive the Quick Reference as the writer's conventions: a departure from it is a Check 4 or 5 finding only when the draft is inconsistent with the profile and with itself. The strict -ise policy always wins over the profile.

The profile is built from the writer's future work only. Never read past drafts to infer one. When the writer confirms a convention in a run and asks for it to be recorded, append one line under the Quick Reference; write nothing to it otherwise.

### Convention lines

Each convention in the Quick Reference is one list item the script `scripts/style_check.py` can read: ``- prefer: per cent | avoid: %, percent``. Forms after `avoid:` are comma-separated and matched exactly, in the writer's own prose only. Other Quick Reference lines are read by the agents as plain guidance.
