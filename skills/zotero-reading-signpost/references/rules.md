# Zotero workflow rules, write lanes and capability table (read every run)

Rules for any Zotero work this skill does: what to do and in what order. They name no Zotero tools; the capability table at the end does. Lanes, libraries and collections come from the user's profile (`references/profile-template.md`). Case-only rules are sections of `references/cases.md` (shared or group library lanes, section 10; collections and tags in detail, section 11; existing AI-summary notes, section 12; patch log, section 13; case-only Zotero actions, section 14); read one section only, where a rule or step names it.

## Always
1. **Look before asking.** Find facts in the user's data first (every Zotero library including group ones, the graph, repos). Use real names, never placeholders.
2. **Capability check.** Read the capability table below and match it to the live Zotero tool list before the first Zotero call. Report mismatches.
3. **Settings first.** Any Zotero setting, preference or plugin change is applied before opening Zotero for a test; state this in every Zotero test brief. Why: Zotero rewrites its preferences file on close, so a setting edited while it is open can be lost. No change to settings or plugins without the user's typed words.
4. **Read before write; say what changes before the first write.** Read the item and its children. Say what would change (old value, new value). Write only inside the lane (Write lanes, below) and only after the user's yes for anything not already agreed.
5. **Tags and collections are the user's.** Tags: proposals only, never written; a lane's "tag" wording in the profile means permission to propose, not to write; report the wording for the user's decision. Collections: never create ad hoc ones, never propose them piecemeal, never move, rename or delete a collection itself; which collections an item is in changes only on the user's per-item yes, and never the Trash. Trashing, merging and deleting are never Claude's actions, whatever the phrasing; they need the user's per-item word, and the Zotero app does them. Lane grants that add items to a named collection, and locked collections: `references/cases.md` section 11 (Collections and tags), read whenever a lane names a collection or an item would change collection.
6. **Library check.** The active library can flip (the library list may not flag it: track it from the last successful switch). Switch to the item's library right before each write, confirm the key resolves there, and check the library after.
7. **Never invent.** No DOI, ISBN, identifier or abstract that did not come from an authoritative lookup or the work itself; no synthesised abstracts. Claude never writes a citation key; Better BibTeX owns it. A missing field is not evidence to delete. A tool's output is a hint to check, not the answer.
8. **Counts.** Before a multi-item edit, record how many items and what the field holds; after, check the same counts and diff the fields (Extra especially). Batches of 40 entries or fewer.
9. **Judge by reading, not by score.** Review means reading the passage against the claim; similarity scores and tool summaries only point where to look.
10. **Notes and annotations by Claude**: `SKILL.md`, Rules, Attribution. Never on the user's notes.
11. **No subagents** for Zotero work (`SKILL.md`, "Work alone: no subagents").
12. **Patch log for the `writer:: Gemini` mark** on an existing note, the one metadata field change this skill makes (metadata fixes are outside it, as its description says; step 12's combined annotation is a write the gate approved, recorded in `checks.md` and reported at verify, not a patch-log row): format and procedure in `references/cases.md` section 13 (Patch log), read before writing the row. Existing Gemini or NotebookLM notes are never replaced or deleted (`references/cases.md` section 12 (Existing AI-summary notes), read at step 11 when the item has one).

## Write lanes
The skill writes only where the profile's `libraries` entries allow.
1. Identify the item's library (personal or group) and collection. In a group or shared library, or where the use is not the personal-library default below, read `references/cases.md` section 10 (Shared or group library lanes).
2. Look up the lane in the profile (or the project's instructions, or ask the owner, with what you already checked). Do not infer one, except for items in the user's own personal library: there notes and annotations are within the lane unless the profile or project says otherwise. Highlights use the signpost colour only; tags are the user's.
3. Proceed only for the actions the lane explicitly names. The skill's write set: the Signpost Summary note (step 11, after the gate of step 10), an OCR copy of the item's PDF (step 2 or 7), the highlights (step 13), the in-place update of the user's existing annotation (step 12), the use-log entry in the module's AI-rules file (step 15; only when one applies, in that file's format; not a Zotero write, so it needs no lane) and, only on the user's per-item yes, the `writer:: Gemini` line appended to an existing AI-summary note (`references/cases.md` section 12 (Existing AI-summary notes)). Whenever the lane names notes and annotations for that collection, or item 2 of this list puts them within the lane, the OCR copy counts as named too (the owner's decision, recorded in `HISTORY.md`; it is PDF work and needs no separate approval). Every other Zotero action must be named by the lane. If an action the skill needs is not named (a lane that covers only adding or tagging items, or notes but not annotations), it is outside the lane: stop and report.
4. Never move, merge or delete items, touch the Trash or other collections, or change plugins or settings.

## Order of work: one reading, start to finish
The module AI-rules gate (step 0; the capability check runs first when the gate needs a Zotero read), the capability and library checks, the signpost steps of `SKILL.md`, then the use record in the AI-rules file's decisions and use log (step 15). If you cannot tell whether the module requires an acknowledgement of AI use in the assessed work (the acknowledgement sentence the AI-rules file's use-log format gives, which the user writes and places), ask the user.

## Escalate to the user, in the chat, with a recommendation
Anything outside the lane; anything in a locked collection other than a lane-granted add; trashing, merging, deleting; tags; collections; settings; a borderline module case; a mismatch you cannot resolve from the user's data.

## Zotero capability table

Skills and project instructions say what to do in words and point here. They never repeat tool names. This is the part of the table this skill uses on every run; actions used only in a case are in `references/cases.md` section 14 (Case-only Zotero actions), read where a step names it (attach an OCR copy: section 3 (Scans and OCR); collection lookups: section 1 (Module AI-rules gate) and section 6 (Books and reading lists); whole-text read: step 5; edit an annotation: step 12).

**Why this exists.** Tool names and options change between Zotero MCP versions, and the MCP server is the only way Claude reads PDFs and writes notes and annotations. So at the start of a Zotero task list the tools you can actually call now (the prefix varies: `mcp__zotero__`, `mcp__remote-devices__zotero__`, or another; if there are none, stop and say so, do not guess), find each needed action's row below, and match the live tool on what its own description says, not on the name alone. If a needed action has no live tool, or the table lists a tool the server no longer has, say so in one line and do not improvise with another tool.

Read-only unless the Write column says otherwise ("no (changes context)", "needs the user's" are not library writes). Every write follows the rules above.

| Action | What to look for | Tool today | Write | Gotchas |
|---|---|---|---|---|
| List libraries | List personal and group libraries with IDs | `zotero_list_libraries` | no | The output may not flag the active library: track it yourself from the last successful switch |
| Switch library | Set the active library | `zotero_switch_library` | no (changes context) | Every later call uses it. It can flip mid-session: re-switch before each write and check the library after |
| Find an item by words | Substring over title, creator, year | `zotero_search_items` | no | Short queries only: each extra word narrows. `search_all_libraries` when the library is unknown |
| Find by citation key | Better BibTeX key | `zotero_search_by_citation_key` | no | Needs Better BibTeX running |
| Read item metadata | One item, markdown, json or bibtex | `zotero_get_item_metadata` | no | Works on trashed items (says "In Trash"). Use `json` for exact field values |
| Read children | Attachments and notes of items | `zotero_get_item_children` | no | Returns the attachment key. Exactly these calls need the attachment key, never the parent key: read PDF pages, full text, PDF outline, page layout, attachment path, create annotation; the annotation-read call takes either key; the attach call takes the parent key. Pass keys in one call, at most 40 per call (rule 8, Counts) |
| Read PDF text by page | Page ranges, text or image | `zotero_read_pdf_pages` | no | 1-indexed physical pages, not printed labels. Use image format when a page garbles equations or tables |
| PDF outline | Bookmarks | `zotero_get_pdf_outline` | no | Often empty on scans: use the printed contents page |
| Local file path of an attachment | Absolute path | `zotero_get_attachment_path` | no | Local mode only |
| Read notes | List or search note text | `zotero_get_notes` | no | `raw_html` plus no truncation before editing a note |
| Read annotations | Highlights and comments | `zotero_get_annotations` | no | Always pass an item or attachment key; with none it returns the whole library |
| Check write ability | Which write backend is configured | `zotero_write_capabilities` | no | Call when a write fails, before asking for anything. The answer depends on the Zotero version (an older Zotero has no local writes; Zotero 10 has), so check each time and say which path the first approved write used |
| Authorise local writes | Dialog in Zotero | `zotero_authorize_local_writes` | needs the user's | Blocks until the user answers in the Zotero window: tell them to switch to Zotero first. Max about 5 prompts a minute. Never loop |
| Create, edit or trash a note | Parent key to create, note key to edit | `zotero_manage_note` | yes | Parent key to create, note key to edit. Update replaces the whole body unless `append`. Plain text or simple HTML only; Markdown is stored literally. Trashing a note is never Claude's action: the user does it in the Zotero app after naming the note (rule 5, Tags and collections) |
| Create an annotation | Highlight, area or sticky note | `zotero_create_annotation` | yes | Attachment key, 1-indexed page, exact text from the text layer (scans will not match), colour as hex, one annotation per phrase; matches text within one page only, so a page-split passage takes one call per page |
