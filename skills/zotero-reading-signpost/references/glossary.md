# Glossary: zotero-reading-signpost

Maintainer reference, not read at runtime. Each term is defined in the place named.

| Term | Definition |
|---|---|
| **signposting** | showing, as highlights on the PDF, which words support each part of an approved summary |
| **part** | a phrase or term of a pass 1 point that rests on one stretch of the text and gets one highlight; in `anchor_check.py` the source quote searched for in the page text |
| **signpost colour** | `#c9a27a` light brown, used only by this skill (SKILL.md, Rules) |
| **attachment key** | the Zotero key of the PDF child item (SKILL.md, Rules) |
| **`writer::`** | property line marking who wrote the text (Claude, Gemini); absent means the user (SKILL.md, Rules, Attribution) |
| **write lane** | the Zotero locations and actions a project permits Claude to write (rules.md, Write lanes) |
| **gate** | the one approval of the summary and plan together (step 10); nothing goes into Zotero before it, except the OCR text-layer attachment. Step 0's module AI-rules gate is a separate stop |
| **dry run** | every step up to the gate, nothing written to Zotero; the working files and, for a module reading, the AI-rules use entry are still written (SKILL.md, Rules) |
| **Work alone: no subagents** | SKILL.md ground rule: one source, one chapter, main session, no agents |
| **Step numbers** | cross-references use the step numbers of SKILL.md's workflow list; changing that list means updating every `step N` pointer (grep for `step [0-9]`) |
| **Text check** | step 2 |
| **Reading scope** | step 4 |
| **Pass 1: the argument, as points** | step 6: the main claim and each step of the argument, before phrases, highlights and summary |
| **Verify** | step 14 |
| **Checkpoint** | step 15 |
| **Verbatim passages** | SKILL.md rule: anchor text matches the PDF text exactly |
| **One phrase or term, one highlight, tight** | SKILL.md rule: one highlight per phrase or term, no wider than its proving passage |
| **Pass 2: phrases, terms and their highlights** | step 7: each point broken into phrases and terms, each highlighted, repeats dropped, anchored, ordered by position |
| **Attribution** | SKILL.md rule: where `writer::` goes and where it does not |
| **Drop what repeats** | done in pass 2 (SKILL.md step 7), defined with the pass 3 tests (method.md section 3) |
| **Understanding check** | the user's questions (Not a copy, Short label, Shows why), run twice in pass 3 (method.md section 3) |
| **Not a copy** | the user's question, graded per highlight in pass 3 (method.md section 3) |
| **Short label** | the user's question, graded per highlight in pass 3 (method.md section 3) |
| **Shows why** | the user's question, graded per highlight in pass 3 (method.md section 3) |
| **Nothing added** | the user's rule, graded on each comment and on the summary in pass 3 (method.md section 3) |
| **Text's own words** | the user's rule, graded on each comment and on the summary in pass 3 (method.md section 3) |
| **Comment in summary** | the user's rule, graded on each comment and on the summary in pass 3 (method.md section 3) |
| **Whole passage** | the user's rule, graded per highlight in pass 3 (method.md section 3) |
| **Aids understanding** | the user's rule, graded on the summary in pass 3 (method.md section 3) |
| **Every claim backed** | the user's rule, graded on the summary in pass 3 (method.md section 3) |
| **Quote edges** | pass 3 test pointing to method.md section 2; `anchor_check.py` EDGE REPEATS |
| **Compose the labels into a sentence** | pass 3 test (method.md section 3) |
| **Every defined word gets its definition** | pass 3 test (method.md section 3) |
| **What cannot be simplified stays** | pass 3 test (method.md section 3) |
| **`signpost_colour`** | profile value: the highlight colour (profile-template.md) |
| **`signpost_tag_by_colour_rule`** | profile value: whether the user's colour rule adds the Signpost tag |
| **`summary_length_cap`** | profile value: the summary's cap as a share of the pages' word count |
| **`ai_rules_file`** | profile value: the AI-rules record read at step 0 |
| **`graph_notes_template`** | profile value: the note layout source |
| **`graph_reading_pages`** | profile value: where each reading is listed, for `related::` |
| **`module_reading_list`** | profile value: where module readings are listed |
| **`patch_log`** | profile value: the patch-log file |
| **Capability check** | rules.md rule 2 |
| **Settings first** | rules.md rule 3 |
| **Library check** | rules.md rule 6 |
| **Counts** | rules.md rule 8 |
| **Notes and annotations by Claude** | rules.md rule 10, which points to SKILL.md, Rules, Attribution |
| **Patch log for the `writer:: Gemini` mark** | rules.md rule 12; format in cases.md section 13 |
