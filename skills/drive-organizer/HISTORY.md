---
version: "1.2.0"
category: C
parent-version: "1.1.0"
author:
  primary: "Vaikri-costume"
inspirations:
  - skill: "claude-code-cowork-skills-file-organizer"
    by: "smithjoshua"
    pattern: "PARA-method file organisation (Projects/Areas/Resources/Archive) with an inbox workflow and content-based classification — the conceptual seed for this skill's grouping model and _Inbox staging"
---

# History — drive-organizer

## Changelog

### 1.2.0 — 2026-06-15
- **Fixed cloud-placeholder detection** (real-OneDrive bug): `_is_placeholder` only checked legacy xattr markers, which modern FileProvider OneDrive files don't carry — so the entire cloud-download path (scan priorities P2/P4/P6) silently never fired. Now uses the macOS `UF_DATALESS` flag / zero-allocated-blocks signal (verified against 12/12 real placeholders). Found via real-OneDrive integration testing.
- **Fixed `merge` annotation data-loss**: it used an invalid `page.add_annot()` (silently swallowed), so PDF annotations never transferred yet the original was still archived. Now rebuilds annotations by type, and refuses to archive an original whose annotations didn't transfer (no-data-loss guard).
- **Grouping-casing normalization**: a viewer edit like `personal/...` now lands in canonical `PERSONAL/...` (top-level grouping forced ALL-CAPS in execute); reconcile remains the safety net for legacy miscased folders.
- First published release (claude-users tier): polished, packaged, versioned.

### 1.1.0 — 2026-06-13
- **Tier promotion to `claude-users`** (from `personal`): de-personalized SKILL.md, templates, and config. Shipped `references/subfolder-templates.json` reduced to a generic skeleton; each user's taxonomy now lives in a per-user override at `[root]/.organizer/templates.json` (deep-merged over the skeleton at load) with profile/memory-doc in `[root]/.organizer/config.json`. New `templates` subcommand prints the merged result. Existing setups reproduce exactly (verified byte-for-byte).
- **Added `reconcile` subcommand** — detects structure drift (misplaced files vs recorded destination, bad registry rows, mangled root folders); dry-run report by default, `--apply` moves misplaced files into place. Generates a synced `organize` YAML artifact for an optional keyword-level cross-check.
- **Changed duplicate handling** (NOTE: behavior change) — `duplicates --colocate ID` now places a duplicate **beside its group's keeper** as `<keeper-stem>_dupN` instead of archiving it to `Archive/_Duplicates/`. Groups now report a `keeper_id`. `--archive` kept as a deprecated alias (now co-locates).
- **Scan performance** — replaced the fixed `sleep(0.5)` single-retry placeholder check (which deferred slow downloads to re-scans) with an adaptive poll up to a configurable timeout (`DRIVE_ORG_DL_TIMEOUT`, default 30s); added per-phase timing (download-wait / hashing / content-peek) to the scan summary.
- **reconcile intent handling** — `reconcile` never guesses intent: relocated/misplaced files are reported with a `restore`-vs-`accept` suggestion (landing-spot heuristic), and the user decides per file via `--restore ID` / `--accept ID`; `--prune ID` drops a confirmed-deleted row. Recommended order: registry-backed misplaced files first, then deletions, then unregistered folders.
- **Fixed `variants`** — the fuzzy-name grouping stripped the trailing variant token (`v2`/`final`/`copy`) before removing the extension, so `…v2.txt` never matched and variants never grouped; now takes the stem first. (Caught by the integration harness.)

### 1.0.0 — 2026-06-11
- First CCVW-structured release of a pre-existing skill (backfill, no behaviour change in this entry).
- Added the mandatory CCVW root files: README.md, HISTORY.md, references/glossary.md, assets/.
- Rebuilt SKILL.md frontmatter to the lean runtime contract (license, compatibility, allowed-tools, metadata block with tier/created/created-by/parent-version/intended-audience); trimmed the description under the 1024-char limit and removed tag-shaped `<root>` content.

## Lineage notes

checked-marketplace: 2026-06-11T00:00

This skill was **inspired by** [smithjoshua/claude-code-cowork-skills-file-organizer](https://github.com/smithjoshua/claude-code-cowork-skills-file-organizer) — a PARA-method file organiser (Projects/Areas/Resources/Archive + inbox workflow + content-based classification). That skill seeded the grouping/_Inbox model here; the resemblance is corroborated by this backend's `para_category`/`para_subfolder` registry columns and `_Inbox/` staging. The implementation diverged substantially: a five-grouping taxonomy (ENTERTAINMENT/PERSONAL/WORK/EDUCATION/RESOURCES) rather than PARA's four, a four-level cascading-Q classifier, vision + content-entity semantic routing, cloud-placeholder download handling, a SQLite registry, an interactive browser approval loop, and a per-folder learning loop — none of which is lifted from the inspiration. Category **C** (idea inspiration): conceptual influence, no structural overlap. See also the README "Sibling skills" section.

A marketplace/FOSS scan (4 marketplaces ≈2,900 plugins, 2 organizer repos, 3 FOSS tools) at build time found no existing tool that replaces this skill's combination of semantic-classification-into-a-user-defined-taxonomy + cloud-drive handling + approval loop + learning loop. The FOSS tool [`organize`](https://github.com/tfeldmann/organize) is borrowed (not adopted) as a generated-artifact verification engine for the reconcile drift-check and as a dedup cross-check.
