# Case sections (read one section only, when its case occurs)

Each section below is read only when a step of `SKILL.md` names it, and only that section: find its heading (`## N.`) with Grep, then Read from that line to the next `## ` heading with the Read tool's offset and limit. Do not read the whole file.

## 1. Module AI-rules gate (step 0, when the reading belongs to a taught module)

If the reading belongs to a taught module, read the project's record of AI rules for that module (the `ai_rules_file` named in the profile, or wherever the project's instructions name it) before anything else. Signposting is study support: it must never produce wording, ideas or arguments for assessed work. A reading not tied to one assessed piece may be signposted where the module level allows it; anything tied to one assessed piece, an unknown module level, or a module level that does not allow it (a no-AI assessment excepted, below) stops here, and Claude asks for the user's typed okay in chat, naming the module, assessment and stage (the stage of the assessed piece the reading feeds, for example planning or editing, not a numbered step of `SKILL.md`); a typed okay already recorded in the AI-rules file for this exact module, assessment and stage satisfies the stop for the whole signposting run (cite the file and section and go on). A typed okay given in chat during this run covers the same: this module, assessment and stage, for the rest of this run; step 15 records it in that file's decisions with the use (a dry run records both too, marked "dry run", `SKILL.md`, Rules, Dry run). A no-AI assessment stops here with no typed-okay route, as the AI-rules record says. A missing rule is not permission. Check from the module's reading list (the profile's `module_reading_list` collection, or the graph page that lists this reading, `references/method.md` section 1; read with the actions in `references/rules.md`, Zotero capability table, after its capability check (`SKILL.md` step 1, run first when this check needs a Zotero read), and for collection lookups section 14 (Case-only Zotero actions) below) that the reading is not tied to one assessed piece; where that cannot be confirmed (for example, an assessment could use the text the reading is about), treat it as tied and stop here to ask. If no record exists, ask what the rule is.

## 2. Several PDF attachments (step 2, when the item has more than one)

The attachment the user's message or the reading-list entry names supplies the page text and receives the highlights. If none is named, use the item's only or first PDF attachment and say in the chat, before step 5, which attachment key you will use (the output contract reports it).

## 3. Scans, OCR and restored runs (step 2 when the text check finds a scan, an OCR layer or dropped words; step 7 when quotes will not anchor)

- Scan with no text layer: OCR it at step 2, before step 5, as below. The OCR text layer never replaces the library file (it needs no approval: `SKILL.md`, Rules, Approval before every Zotero write). The OCR attachment's key is then the attachment key for steps 4 to 13, and the user's existing annotations are still read from every PDF attachment. In a dry run nothing is attached: step 5 reads the local OCR text.
- Scan that has an OCR layer: say so, and check the quotes in step 7 against that layer.
- Quotes will not anchor (`anchor_check.py` finds them missing, or its printed span does not match the planned place) because the text layer is garbled or scanned: OCR then, at step 7 (for example `ocrmypdf --force-ocr -l eng INPUT OUTPUT`, with the output outside the library folder) and attach the result to the same item as a new attachment (the attach-a-file action, section 14 (Case-only Zotero actions)); before attaching, read the item's children, and where an OCR copy from this run is already attached (a stop between the attach and the `ocr.md` write), record it in `ocr.md` and use it instead of attaching another. The moment it is attached, write `ocr.md` in the working folder: the OCR copy's key, the page range and the time. A resume, and each later chapter of a book or volume run (its `ocr.md` sits in the item's folder, `SKILL.md`, Working folder and checkpoints), reads `ocr.md` first and never attaches a second copy. Never overwrite or replace the original attachment. Where OCR is triggered only at step 7, the pass 1 points stay as they are; the OCR copy's text of each page `scope.md` lists is saved over its `pages/p<N>.txt`, so the quote check and every later check run against the attachment that receives the highlights. The report says the highlights are on an OCR copy and which attachment holds it. In a dry run the OCR still runs locally (output outside the library, nothing attached; `ocr.md` records the local output's path, page range and time, and a resume or later chapter reuses it), a garbled layer is checked against the local OCR text, and the OCR attachment is listed as planned.
- Where the text layer is still partly garbled after OCR (words replaced by symbols), a quote must lie wholly in readable text and begin and end on a whole sentence or clause; a page-split passage is highlighted per page (`references/method.md` section 2); a phrase whose passage is unreadable is listed as unanchored and handled as `SKILL.md` step 7 says (its point kept on another passage where one makes it), and the report says a text-layer copy would restore it.
- `pdftotext` drops runs of words (embedded fonts with no text mapping leave gaps or symbol strings while the page looks normal): render those pages to images (`pdftoppm -r 100`), read them, restore the missing words in the copy of the text used for checking, inside square brackets (`[restored words]`, which the PDF text never holds, so `anchor_check.py` finds no quote that spans them), and say which runs were restored; the PDF itself is never changed. A quote never spans a restored run (restored words are not in the PDF text layer, so a highlight on them cannot be created); a phrase whose passage lies in a restored run is listed as unanchored and handled as `SKILL.md` step 7 says.

## 4. Existing annotations (step 4, whenever the item has any user annotation, before the plan table is built at step 8)

The user's annotations are read in step 4 from every PDF attachment of the item. An annotation whose key an earlier run recorded (the keys in every `checks.md` under `signpost-work/<attachment key>/`, each earlier run's and chapter's subfolder included, `SKILL.md` steps 12 and 13) is a signpost from an earlier run of this skill, not the user's; where no record covers it, so is an annotation in the signpost colour (the profile's `signpost_colour`, `#c9a27a` by default) and a combined annotation from an earlier run (any colour, its comment holding Claude's text above a `---` line, or Claude's comment alone where the user's annotation had none, `SKILL.md` step 12); every other annotation is the user's. If the item already holds signposts from an earlier run (signposts this same book or volume run made on earlier chapters, whose keys are in those chapters' `checks.md`, do not count), stop at step 4: say how many there are and wait for the user's word before planning (this skill never deletes them; removing them is the user's action in Zotero). If the user says to go on, earlier signposts stay untouched: a planned quote lying within one is marked `earlier signpost` in the plan table, gets no new highlight, and is listed in the report. The plan table marks each planned quote against the user's annotations:
- `covered`: the quote lies within the annotation or equals it. `SKILL.md` step 12 combines in place: Claude's comment first, then a line `---`, then the user's original comment verbatim underneath; if the user's annotation has no comment, Claude's comment is written alone with no divider. No new highlight is created for that phrase, and the plan approval covers this write (the edit action, section 14 (Case-only Zotero actions)).
- `partial overlap`: they share only part of the text, including a single annotation lying wholly inside the quote. The gate (step 10) decides whether to combine as above or to create the planned highlight beside the user's annotation.
- The quote covers or overlaps more than one annotation: the table marks each, and the gate decides which annotation takes the comment.
- Never combine across attachments: where the user's annotation is on a different attachment from the one receiving the highlights (for example the original PDF while the highlights go on the OCR copy), it is left untouched, the planned highlight is an ordinary highlight on the receiving attachment, the table marks it "user annotation on another attachment, not combined", and the report names that annotation.

## 5. Dry run (step 1, when the user asks for a dry run)

A dry run (`SKILL.md`, Rules, Dry run) runs every step up to the gate (step 10) in one turn (every stop that waits for the user still applies, for example the module gate of section 1, a profile question, and earlier signposts at step 4, section 4) and writes nothing to Zotero (the working files of `SKILL.md`, Working folder and checkpoints, are still written). It lists the planned note and, if OCR was needed, the planned OCR attachment (section 3, Scans and OCR) instead of writing them, and marks steps 11 to 15 `not run: dry run` (for a taught-module reading, step 15's AI-rules entry, the use and any typed okay given in chat, is still written in that file's decisions and use log, marked "dry run"; it is not a Zotero write). Its report has the fields of the Output contract except those about writes and verify (exhaustively: summary and plan approved, note written, highlights created, differences at verify, the write path used on the first write, a highlight on the wrong page, the highlights being on an OCR copy and the attachment that holds it, the checkpoint); in their place it gives the planned note, the planned OCR attachment (only if OCR was needed), steps 11 to 15 as `not run: dry run`, and that the run has stopped at the gate rather than the checkpoint.

## 6. Books, edited volumes and module reading lists (before working through a book, edited volume or reading list)

A chapter or section at a time, with the full workflow and a checkpoint each time. For a module reading list, take the readings from the module's reading-list collection (collection lookups: section 14 (Case-only Zotero actions)), process only those the user asks for, in the order given, one at a time, announcing the week or session. Choosing which readings to skip is not this skill's job; a reading whose item already holds signposts from an earlier run stops at its step 4 (section 4, Existing annotations).

## 7. Creation failures (step 13, when a quote does not match at creation or a highlight lands on another page)

- If a quote does not match, retry on a shorter distinct run at a clause boundary within the approved quote (the gate's approval of the quote covers this retry, as part of the same highlight; it must still begin and end on a whole clause, and pass `scripts/anchor_check.py` on its page before it is created, so it is unique and its edges land on itself); if it still fails, report it. A shortened run is reported at verify with the approved quote beside it, as a difference from the plan.
- Never paraphrase, never anchor to a nearby passage, never accept the create tool's "did you mean" suggestion.
- A wrong-page highlight (one created on another page) is a failure: create no second highlight for that phrase, delete nothing (removing it is the user's action in Zotero), leave it in place and report it at verify with its page and the planned page, and, unless the highlights are already on an OCR copy, that an OCR copy would anchor it; no automatic OCR re-run.

## 8. Signpost colour in Zotero's colour list (before a test, or when the colour does not show as Signpost)

The colour has to be in Zotero's colour list to show as a named colour; that is a settings change done before a test (Settings first, `references/rules.md`), never by this skill. If it is absent from the list, the highlight still carries the hex.

## 9. Conditional report fields (step 15, when a scan, an OCR copy, a text mismatch, a wrong-page highlight, a restored run, an empty `related::`, an omitted `citekey::`, a user annotation left uncombined on another attachment or a planned quote on an earlier signpost occurred)

Add to the report, in addition to the Output contract fields of `SKILL.md`:
- that a scan had an OCR layer (only if it did)
- whether the text matched (only if it did not)
- that the highlights are on an OCR copy and which attachment holds it (only if OCR was used)
- for a wrong-page highlight, its page, the planned page, and, unless the highlights are already on an OCR copy, that an OCR copy would anchor it (no automatic re-run)
- any runs restored in the page texts of step 5 (found at step 2)
- that `related::` was left empty or `citekey::` omitted, and why (only if so, `references/method.md` section 1)
- each user annotation on another attachment that was not combined, with its attachment, page and text (only if any, section 4)
- each planned quote marked `earlier signpost`, with its page and the earlier signpost's comment (only if any, section 4)

## 10. Shared or group library lanes (step 1, when the item is in a group or shared library, or the use is not the personal-library default)

- In a shared library collaborators see everything written: say so before the first write in a session.
- The profile and project instructions name each use, its library, collection and lane; ask once if a use is not named.
- Taught-module readings in a shared group library: readings come from that library's module reading-list collection (the profile or project instructions name the library and collection key). The lane is whatever the profile or project currently grants for that collection. Notes and annotations are visible to the other group members, so the lane must name them explicitly; if it names only adding and tagging items, stop and report. Work module by module, one reading at a time, in the order the user gives (section 6), else in the module's order. Readings without an attachment cannot be annotated; list them for the owner.
- Anything else: ask once, in chat, with a recommendation.

## 11. Collections and tags in detail (when a lane names a collection or an item would change collection)

Which collections an item is in changes only on the user's per-item yes, except where the profile's lane grants adding items to a named collection (the user's standing okay for that lane and collection). Never in or out of any other locked collection (one the user or the project's instructions name as locked; it waits for the user's explicit unlock in that session), and never the Trash. Where a lane grant names a collection that is also locked, the grant wins for adding items there; removing or moving items there, or anything else in that collection, is still the user's.

## 12. Existing AI-summary notes (step 11, when the item has a Gemini or NotebookLM note)

Existing Gemini or NotebookLM notes are never replaced or deleted. If one is unmarked, propose the mark (note key, old ending, new ending) before writing it; apply `writer:: Gemini` only on the user's per-item yes, by appending the line (the append form of the note action, never replacing the body; NotebookLM counts as Gemini), and write a patch-log row (section 13, Patch log). Claude's own note sits beside it.

## 13. Patch log (before writing the patch-log row for the `writer:: Gemini` mark)

One log file, the `patch_log` path in the profile; blank means the user keeps no log (`references/profile-template.md`), so no row is written, and the write and its re-read still happen. One row per field changed, appended right after that write and its re-read (the `verified` field comes from the re-read) and before the next write, never reconstructed later:

`date | library | item key | field | old value | new value | source (URL, DOI lookup, PDF page, the user's words) | reason | by | verified (how)`

Old value is copied exactly, including empty. Escape in this order, backslash first: a backslash that is part of a value as `\\`, then a literal `|` as `\|` so the row keeps its 10 fields, then each newline in a multi-line value as the two characters `\n`. Source must be something a reader could open. Items stay clean: nothing about the fix goes into the item itself except the changed value. If the write failed or a hook rewrote it, log what actually landed.

## 14. Case-only Zotero actions (where a step or section names one: OCR attach, collection lookups, a whole-text read, editing a user's annotation)

This continues the capability table in `references/rules.md` (same rules: match the live tool on its own description; if the action has no live tool, say so in one line and do not improvise; every write follows `references/rules.md`). A whole-text read is used only when page reads cannot be.

| Action | What to look for | Tool today | Write | Gotchas |
|---|---|---|---|---|
| List collections | Tree with keys | `zotero_get_collections` | no | `include_trashed` shows trashed ones |
| Find a collection key | By name | `zotero_search_collections` | no | Words are ANDed. Trashed hidden unless asked |
| List items in a collection | Paged | `zotero_get_collection_items` | no | Paged; not recursive unless `include_subcollections` |
| Read whole text | Extracted full text | `zotero_get_item_fulltext` | no | Page-limited and expensive. Prefer page reads |
| Attach a file | To an existing item | `zotero_attach_file` | yes | Parent key, not attachment key. Idempotent on same file |
| Edit or delete an annotation | By annotation key | `zotero_update_annotation`, `zotero_delete_annotation` | yes | Edit only on the user's yes. Delete is permanent and never Claude's action: the user does it in the Zotero app after naming the annotation. Position cannot be edited |

## 15. Pass 3 worked examples (only when a test in `references/method.md` section 3 is unclear)

- Not a copy fails when the comment only re-words its quote: "weak record on institutions" against "None of these approaches has a strong track record".
- Every defined word gets its definition, explained as the paper does: "structural violence" (defined in the text as "poverty, inequality and discrimination"), "horizontal inequalities" (defined as those "that align with cultural, ethnic or religious identities").
- Text's own words: "market-driven economics" keeps the text's words; "after" for "following" or "across society" for "at societal level" swap them.
- Short label keeps what its passage carries: "NGOs and donors" lost the international financial interest, "Western-funded NGO industry" kept it.
- Compose the labels into a sentence: say where its wording goes beyond the text, for example "has X as its agenda" where the text says "embedded in", "is the work of" where the text says "supported by".
- Comment in summary reads naturally: "Holistic: a longer list of measures" and five fields joined by semicolons were judged harder to read.
- Every defined word gets its definition: "restorative justice", "continuum of gender-based violence", "transformative justice"; for a contrast, both sides ("transformation" and "transition"). "Liberal peace" and "reconstruction" are only named or described in that text, so they are phrases, not terms.
- Aids understanding, saying what the point does, not what it says: "The structural violence of poverty, marginalisation and exclusion shapes this violence too" only restates its highlight; the sentence should say what role structural violence plays in the argument, for example what it leads the authors to next.
- Text's own words, where a lifted sentence is re-explained but the text's wording stays exactly: "results in more of the same", "allowing everyday forms of violence to continue", "may take different forms and be of a different scale".
