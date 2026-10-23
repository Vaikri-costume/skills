# Graph rules: turning reading into linked knowledge

Applies on top of the dual-format write rules in `references/layers/logseq-obsidian.md` ("Write rules that always apply": property:: blocks, no YAML, bare `[[Page]]` links, global title/alias uniqueness). The skill proposes and checks; the user builds the notes, relations and concept pages. Nothing here writes content for the user or for assessed work (module AI-rules gate first when a page touches assessed work).

## Contents
1. Concept, topic or fleeting
2. Vocabulary pages written like a codebook
3. Claim-titled pages
4. Links carry a relation
5. Duplicate check before any page is created
6. Reading pages: the user's existing templates only
7. Page-kind test
8. Journal graduation
9. Maps on request
10. Read-only sources and decision log
11. Templates keep `writer::` blank

## 1. Concept, topic or fleeting
- **Concept**: a timeless, definitional term (orientalism, hybridity, sartorial agency). One page per concept. An author's usage of the term is a sub-block on the concept page, attributed to that author.
- **Topic or thread**: an evolving debate. Lives on a Thread, Lens or Period page, not a concept page.
- **Fleeting stub**: a vague idea with no name or no self-contained definition yet. It stays a stub (a single block, no page of its own) until it has both.
- **Promote** a stub to a page when all three hold: more than three paragraphs of sourced content; a second source corroborates it; it keeps being cited. The skill names which of the three are met and which are not. The user decides.

## 2. Vocabulary pages written like a codebook
A `type:: Vocabulary` entry has four labelled blocks: Definition; Counts as; Does not count as; One verbatim example with citation key and page. Each label is a `heading:: true` bullet with its content in a child bullet (the layer's write rules forbid bold and `Label: value`). The example is copied from the source, never composed. This stops a term drifting between readings; the user's Zotero tag registry (kept outside this skill) maps tags to these pages. The skill proposes missing blocks as questions; the user writes the definition.

## 3. Claim-titled pages
Where a page is about one argument, its title may state the claim ("Hybridity undoes the colonial binary") instead of naming the topic. Proposed only; titles must still be unique and disambiguated at creation (suffix, never a clash found later).

## 4. Links carry a relation
Every link in a Connections section starts with a relation verb from `assets/relation-vocabulary.json`, then the link, then a colon and one line of reason:

`- extends [[Hybridity]]: builds on the term to cover clothing`

The vocabulary starts from eight verbs (extends, complicates, contradicts, applies to a different case, supplies the primary source for, responds to, reframes, disputes the reading of). The user edits it and can grow later: the user adds a verb by editing the JSON, or tells Claude to. The skill never invents a verb or a relation; it proposes "which verb fits?" questions. The `relations` audit check reads the same file.

## 5. Duplicate check before any page is created
Before creating or renaming a page, search three places, not one: filenames, `title::` values, `alias::` values (also the aliases of existing pages). Report the hits and route to "update that page" or "link to it". Only when all three are empty is the page absent. Disambiguate generic titles at creation. An alias exists so that a mention in source or annotation text resolves to the right page, so choose it by that test: would this exact string, found in a real excerpt, identify only this page? That excludes a bare word such as "Empire", "dynasty" or "period"; a region-wide qualifier such as "South Asia" or "India" that fits many pages; and a common surname or common word unqualified (use the qualified form, for example "Gupta period" rather than "Gupta").

## 6. Reading pages: the user's existing templates only
No new reading template. Reading Notes pages use `Reading Notes Template` and Reading Report pages use `Reading Report Template` (in `pages/Templates/`), property order `related::` (the module), `type:: Reading Notes`, `writer::`, `citekey::`, `alias::`, `author::`, then Notes / Summary, Annotations (the user's colour sub-headings), Connections. Module hub and Week pages already list the readings. The skill does not change the layout and does not fill the user's Annotations headings. If a Zotero note that Claude wrote is converted, it keeps `writer:: Claude`.

## 7. Page-kind test (on request, like journal graduation and maps)
One page, one kind: reference (vocabulary, entity: neutral), explanation (thread, lens, period), how-to (the user's own procedures). A page that mixes kinds is proposed for splitting, never split silently.

## 8. Journal graduation (on request, not offered)
Scan the journal blocks the user names for `#to-expand` or three or more links in one block and list them as stub candidates. The user decides what becomes a page.

## 9. Maps on request
Mermaid first; an obsidian-json-canvas file only if the user asks for a canvas. Maps draw existing pages and relations; they add none.

## 10. Read-only sources and decision log
Verbatim quote files, PDF extracts and any `raw/` source folder are read-only. A decision log (date, claim or interpretive decision, reason, what would change it) is plain blocks in a page the user chooses; The skill proposes entries, the user keeps them.

## 11. Templates keep `writer::` blank
Templates keep `writer::` blank: rule Templates and the blank writer in `references/rules.md`. Only a page made from a template gets a filled value. The audit flags a filled `writer::` on a template.
