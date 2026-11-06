# The writer's profile and the gate

The skill holds no personal, course, institution or field detail. Everything specific to the writer is read at run time from their profile, a markdown file of bullets in the form ``- `key`: value``.

## Where the profile is

In this order: the file named by the environment variable `CCVW_USER_PROFILE`; else the first `config/user-profile.md` found walking up from the working directory; else a profile entry in the writer's Claude memory index. A missing profile or key is not an error: use the default below and carry on. Ask the writer only for a fact the run cannot continue without.

## Keys this skill reads

| Key | Meaning | Default when absent |
|---|---|---|
| `ai_rules` | Path to the file recording the course's AI rules for each assessment | none: if the draft belongs to coursework and no rule can be found, ask once which rule applies |
| `field_bank` | Path to the folder of the writer's field pages (one file per field: what a good argument, evidence and voice look like there, agreed with the writer) | none: no field lens (see `lenses.md`) |
| `session_log_dir` | Folder for the optional one-line session-log marker (`**[HH:MM:SS] SKILL:review-writing RUN:<run id> STEP:start**`, appended to the day's log at the start of a full review) | none: write nothing |
| `scratch_dir` | Folder for the run folder (`dispatch-protocol.md`, Run folder; exported as `SCRATCH_DIR`) | the system temporary directory |

## Step 0: runs only when asked

The skill runs only when the writer asks for it, in that message, naming a review or a mode. Never offer or suggest it (SKILL.md, Hard rules). A standing permission recorded in the rules file says what the writer allows, not that the skill may bring itself up. Stop here otherwise.

## The gate (coursework only)

Skip it for work that is not for a course (an application essay, a blog post, a conference talk). Otherwise, before any agent is dispatched:

1. Read the `ai_rules` file fresh. Name the course and the assessment the work feeds.
2. Classify what this skill would do: S (study support), F (feedback on the writer's own work) or G (generating text for the assessment). This skill is F only. G is never done, on any category, however the request is worded; say so and stop.
3. Apply the rules file's own table. When the rule bans AI for that assessment, the stop message names the course and assessment, quotes the clause, and says nothing was read or run; it adds no invitation to retry, no alternative and no other check. When the rule is borderline, omits the assessment, or does not clearly cover this mode (items 5 and 6), the message quotes the clause and asks exactly one question naming the course, assessment, mode and kind of feedback; the writer's typed answer in this conversation settles it, and nothing is read or run until then. Stop, say why and quote the clause when the entry bans AI for that assessment (a no-AI or "autonomy" category blocks feedback and drafts too), says nothing, or is unclear. An unstated rule is not permission. Carry on only when the entry allows feedback of this kind or the writer confirms in this conversation that it does.
4. Language-only permission: when the rule allows feedback on language, clarity, tone or structure but not on argument or substance, run only the Clarity and Voice domains and the structure parts of the report, and run Argument and Evidence only when the writer asks for them in that same message, each time. A message that names the argument or the evidence is that ask: run them, say in the header that they ran on the writer's request and that the rule covers language only, and never refuse on the rule alone once the writer has asked.
5. Presentation mode on coursework needs a rule that clearly allows feedback on a presentation; otherwise stop and ask once, naming course, assessment, mode and kind.
6. Borderline: stop and ask in one short message (course, assessment, mode, kind). Never read the rule in the writer's favour.
7. After a permitted run on work with a "declare" instruction, end the report with the AI-use line (`presentation-format.md`) and, if the rules file keeps a use log, tell the writer to add the row; never write to the rules file yourself.

## The field bank

The field lens is never written in the skill. When `field_bank` names a file, read the page for the field of the draft and apply only what it says. If the draft's field has no page, say so and use no field lens; do not guess a field's norms. Adding a page is done with the writer, from their own reading, never from past drafts.
