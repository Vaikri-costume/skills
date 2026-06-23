---
version: "2.6.1"
category: C
parent-version: "2.6.0"
version: "2.7.0"
category: C
parent-version: "2.6.1"
author:
  primary: "Vaikri-costume"
  history:
    # Original work by Vaikri-costume (not a fork); this records the canonical home
    # repo so skill-publisher Step 9 auto-resolves the upstream to PR back to.
    - role: "original"
      name: "Vaikri-costume"
      skill: "drive-organizer"
      version: "1.0.0"
      date: "2026-06-11"
      license: "MIT"
      source: "https://github.com/Vaikri-costume/skills"
inspirations:
  - skill: "claude-code-cowork-skills-file-organizer"
    by: "smithjoshua"
    pattern: "PARA-method file organisation (Projects/Areas/Resources/Archive) with an inbox workflow and content-based classification — the conceptual seed for this skill's grouping model and _Inbox staging"
---

# History — drive-organizer

## Changelog

### 2.7.0 — 2026-06-24

#### Added
- **rules-viewer Settings panel (Phase 3 — the configurability gating feature).** A collapsible
  **⚙ Settings** panel is now embedded in the rules-viewer (`rules-viewer`, port 5003). It reads the
  current effective config via a new `_settings_for_viewer()` helper (defaults applied; legacy
  top-level `vision` normalised into `model_capabilities`) and writes back via `_write_user_config()`,
  which atomically merges changes into `<root>/.organizer/config.json` while preserving unrelated keys
  (`areas`, `root`, `profile`). Editable settings: `peek` (read file contents), `vision` (see images),
  `auto_approve` (W1 fast-path auto-approval), `skip_types` (normalised to a deduped sorted `.ext`
  list), `skip_over_mb` (cleared when blank). "Save settings" POSTs to a new `/config` route — entirely
  separate from `/save` and `/apply` — so settings changes never touch the rule set and vice-versa. The
  GET payload now carries a `settings` object the panel renders on load. This panel is the designated
  single settings surface: every future toggle/dial wires in here.

### 2.6.1 — 2026-06-24

Documentation and structure only — `organizer.py` is untouched, no behaviour change (a patch release).

#### Changed
- **Docs — viewer screenshot.** Added `assets/viewer.png`, a screenshot of the browser
  proposal-review viewer (grouped destinations, inline-editable folder/filename fields, per-row
  approve / reject / flag / inbox / delete), referenced from the README; `assets/README.md`
  describes it.
- **SKILL.md structural refactor** (~9,970 → ~8,230 words). Relocated point-of-use / agent-facing
  detail into references, leaving SKILL.md a leaner contract + pointers; the residual is the
  load-bearing core-loop executor contract.
  - Per-file classification logic each fan-out agent applies (pre-bucket by Q1, lazy-load rules +
    path_vocab, entity matching in `content_peek`, the per-level routing decision + templates
    fallback, the both-axes file-type rules, RAW/images/photos/atomic/external/audio handling) →
    moved into `references/classify-prompt.md` under "Per-file classification logic".
  - Inbox-arbiter reclamation sweep mechanics (trigger rationale, dispatch + `[CAPABILITIES]` fill,
    the `confirm_inbox`/`reroute_high`/`reroute_low` apply rules) → moved into
    `references/arbiter-prompt.md` under "When + how the orchestrator runs the sweep".
  - generate-viewer submit-response interpretation (log-line cases + manual registry-patch recovery)
    and the process-return learning-loop accelerators (W5) + ordering rationale + delete-routing note
    → moved into `references/subcommands.md`; SKILL.md keeps the numbered pipeline + pointers.
  - Model-capabilities subsection compressed to the capability one-liner + a pointer.

### 2.6.0 — 2026-06-23

#### Added
- **Cowork-reachable review path — `generate-viewer --static`.** The proposal-review viewer is a
  localhost HTTP server (port 5002), unreachable from Cowork/remote sessions where the user's browser
  isn't on this host. `--static` (auto-enabled when `DRIVE_ORG_HEADLESS=1` or a Cowork env marker —
  `CLAUDE_COWORK` / `COWORK` / `CLAUDE_CODE_COWORK` — is set) writes, instead of starting the server:
  a self-contained editable `proposals_review.html` (review and approve in any browser via a
  client-side Blob download — no server, no localhost POST), plus a pre-filled `proposals_approved.json`
  (every file defaulted to `approved` at its proposed destination, so accepting all needs no browser
  at all). The approved-entry schema is identical to the served viewer's — only the transport differs,
  so process-return is unchanged. The default localhost behaviour is unchanged.
- **`generate-viewer --no-open`** — run the localhost viewer server without auto-opening a browser
  (local headless testing where port 5002 is reachable), matching `rules-viewer --no-open`.
- SKILL.md documents `--static` / `--no-open`, the auto-detection, and the two fallback outputs.

### 2.5.0 — 2026-06-23

#### Changed
- **Batched cloud pre-trigger in `scan`.** Cloud-only placeholder downloads are now kicked all at
  once — `scan` first selects the whole batch (file/GB caps + skip-rehash), then opens every selected
  cloud-only file to start its download and polls the set once, so N downloads proceed concurrently
  and overlap the hashing pass instead of the previous one-file-at-a-time trigger→poll. The
  byte-stability confirmation (stat → sleep → stat) is likewise batched to a single wait across the
  whole set.
- Selection logic (bucket priority order, caps, first-admission exception, skip-rehash) is unchanged
  and runs before the download phase; the per-batch timeout (`DRIVE_ORG_DL_TIMEOUT`) and the deferral
  of files still online-only after the timeout are preserved.
- SKILL.md documents the batched download behaviour.

### 2.4.0 — 2026-06-23

#### Added
- **Optional-dependency graceful degradation.** The backend probes `mutagen`, `PyMuPDF`, and
  `Pillow` at startup and prints a single stderr notice of any inactive features; every call site
  degrades cleanly (a weaker signal, not a crash) when a library is absent.
- `exif` subcommand documented as the vision-off image-routing path; the arbiter prompt gains a
  `[CAPABILITIES]` slot (peek/vision ON/OFF) matching the classify fan-out contract.
- `tidy-builtin-categories.json` expanded with broader generic category entries.

#### Changed
- **De-personalization of the shipped skill.** Removed the original author's personal names,
  production-company and character examples, and personal folder references from SKILL.md,
  `references/`, the viewer UI, and `BUILTIN_VOCAB`; remaining examples reframed as illustrative
  generics. The shipped skill is now generic and universal.
- Renamed the `.tidy-rules.json` project-metadata key `production_period` → `date_range` (more
  general); back-compat reads the legacy key and migrates it on write.
- Removed a hardcoded personal folder name from the skip sets in favour of the existing
  external-folder mechanism.
- Corrected the auto-approve description in two SKILL.md spots to "W1 fast-path (deterministic rule
  match)" rather than "high-confidence classifier verdict".
- Arbiter-sweep section now names the `[INBOX_BATCH_JSON]` slot and states the pointer-not-inline WHY.
- Clarified the rejected-button cell: the served `para_subfolder` is the verdict destination carried
  through for process-return to reclassify against the baseline.
- process-return now fills a null `file_date` when a date becomes readable, instead of carrying null
  and silently skipping the period update.
- Scoped the batch-loop idempotency claim: replaying a consumed `approved.json` reports MISSING;
  generate a fresh batch.
- Documented the intentional `IMAGE_EXTS` two-consumer split (backend constant + agent-facing list;
  a Markdown reference cannot import a Python set).
- Consolidated the `date_range` buffer value (`buffer_days=30`) to a single prose home in SKILL.md.
- Replaced the Camera RAW extension enumeration in SKILL.md with a pointer to
  `references/file-type-routing.md` as the authoritative set.

#### Fixed
- `reconcile --accept` now re-derives `para_category = _para_category(new_para)` when rewriting
  `para_subfolder`, restoring the projection invariant.
- `_bootstrap_apply` guards each rule with `isinstance(rule, dict)` before `.get()`, preventing a
  crash on a non-object rule entry.
- Added `.arw` to the tidy-builtin Pictures RAW extension list.
- Added `flagged` to `scan`'s terminal-status exclusion set, so a content/mtime change no longer
  re-exposes a flagged file to `propose` without a peek.
- move-journal lost-move branch now emits a WARNING naming both paths and directs to `reconcile`
  before clearing the entry (previously silent).
- Corrected the `_para_category` docstring: the viewer's `inferCategory` is client-side display-only
  and intentionally not a mirror of the backend function.
- Rewrote the module Usage docstring to cover all subcommands and point to `organizer.py -h`.

### 2.3.0 — 2026-06-20
- **Automated eviction — `cleanup --evict`.** The new flag dehydrates the organised top-level
  grouping folders (e.g. `WORK/`, `PERSONAL/` — never the `_Inbox/`/`Archive/` staging folders) to
  online-only, freeing local disk while cloud copies stay (re-downloadable). Per-OS, best-effort:
  macOS `brctl evict` (File-Provider/iCloud drives; OneDrive-on-macOS has no CLI → falls back to the
  manual recipe), Windows `attrib +U -P … /s /d` (OneDrive Files-On-Demand, unverified), Linux/other
  → manual recipe. Non-destructive of data and never errors the run: a per-folder failure, a missing
  tool, or an unsupported OS degrades to the printed recipe. Without `--evict`, `cleanup` is unchanged
  (empty-folder removal only). Minor bump.
- Docs: `references/subcommands.md` "cleanup" + SKILL.md cleanup step document `--evict` and keep the
  manual per-app recipe as the documented fallback.
- Ship-time polish (publisher Run 8): trimmed always-loaded duplication — dropped the cloud-detection
  mechanism cross-ref from the `compatibility` frontmatter, pulled the per-OS evict commands out of the
  SKILL.md cleanup step (they live in `references/subcommands.md`), and deduped the `[CAPABILITIES]`
  slot-fill instruction to a single home.

### 2.2.0 — 2026-06-20
- **Platform-agnostic cloud handling (Windows + Linux).** The default drive root is now resolved
  per-OS (`_default_root()` dispatches on `sys.platform`): macOS `~/Library/CloudStorage/OneDrive-Personal`,
  Windows `%OneDrive%` / `%USERPROFILE%\OneDrive`, Linux `~/OneDrive` (best-effort guess; override
  with `--root`). Cloud-placeholder detection already dispatched per-OS (macOS xattr/dataless verified;
  Windows `FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS`/`OFFLINE`, unverified); Linux treats files as local
  (a size-vs-blocks heuristic was rejected — sparse/compressed/reflinked files report zero blocks while
  fully local, and the scan poll loop would strand them). The download trigger (`open().read(1)`) is
  inherently cross-platform.
- **"Unverified on this OS" notice** — `status` and `scan` print a one-line best-effort note on
  Windows/Linux (cloud detection is verified only on macOS; falls back to treating files as local).
- Dropped the "macOS-oriented" framing from `compatibility`; `--root` help, README, and
  `references/subcommands.md` now describe the per-OS defaults + cross-platform detection. Verified
  on the >25GB four-loop gate (macOS); Windows/Linux ship best-effort, unverified. Minor bump.
- Ship-time refinements (CCVW audit + polish): scoped the invocation trigger from "organise, sort,
  or tidy files" to "organise, sort, or tidy a drive" for shared-tier composability; trimmed the
  always-loaded `compatibility` frontmatter (per-OS mechanism detail now lives in
  `references/subcommands.md`).

### 2.1.0 — 2026-06-20
- **Model-agnostic classification with graceful degradation.** The backend no longer assumes a
  vision-capable model. A new `model_capabilities` config block (`{peek, vision}`, both default
  `true`) plus `--no-peek` / `--no-vision` run flags (precedence: flag > config > default)
  declare whether the running model can open file CONTENTS and see IMAGES. `propose` resolves
  both and emits a `Model capabilities: peek=… vision=…` line on stderr; the orchestrator fills
  the new `[CAPABILITIES]` slot in `references/classify-prompt.md` so every classification agent
  degrades gracefully: peek off ⇒ classify from `content_peek` + name/path only; vision off ⇒
  route images by name/path + EXIF. No file is dropped — degradation falls to `_Inbox/` only
  when nothing matches.
- **New `exif` subcommand** — prints an image's routing metadata (date / camera / dimensions) as
  JSON for the vision-off path. Pillow-optional: degrades to the filename-derived date when
  Pillow or embedded EXIF is absent, and never errors (always prints a JSON object).
- **New `merge-category` subcommand** — adds one taxonomy category from a small JSON `--diff`
  (`{name, description, parent?}`) into the per-user templates override; Python owns the merge so
  a model never rewrites the whole nested templates file. Atomic write; shipped skeleton untouched.
- **Reliability — retry once, then route.** A classification batch that errors or returns
  malformed JSON is re-dispatched once; if it still fails, its files route to `_Inbox/` (surfaced
  in the viewer) rather than being dropped or aborting the run.
- **Bugfix (found in code review, pre-existing):** `_category_names()` read `compound_children`
  values as bare lists, but the templates store the `{"children": [...]}` dict shape — so compound
  children (Bills, Invoices, MOUs, Mood Boards, …) were never recognized as categories. Now reads
  the dict shape (tolerating a bare list too). This is also what makes `merge-category`'s `parent`
  linkage take effect. Two new malformed-config guards (`merge-category` `compound_children`,
  `propose` `model_capabilities`) degrade instead of crashing.
- Docs: capability-aware `references/file-type-routing.md` (vision gate + EXIF date fallback),
  `references/classify-prompt.md` `[CAPABILITIES]` ladder, `references/subcommands.md` `exif` +
  `merge-category` entries, glossary terms (`model_capabilities`, capability degradation, `exif`,
  `merge-category`). Minor bump — fully backward-compatible (all new behaviour defaults to the
  prior vision-on path).
- **Packaging:** added an MIT `LICENSE` file at the skill root and completed the attribution
  provenance — `author.history[]` now records the canonical home repo (`Vaikri-costume/skills`)
  so future ships auto-resolve the upstream.

### 2.0.0 — 2026-06-17
- **BREAKING — scan priority is now rules-based; the x-folder quarantine + `mark-unapproved` are removed.**
  Previously, unknown root folders were `x`-prefixed (via the `mark-unapproved` subcommand) to defer them,
  and scan bucketed by that `x` convention. Now a folder is simply scanned by **whether it has rules**: the
  6-bucket priority is P1/P2 = folders **with** rules (downloaded / cloud), P3/P4 = loose root files,
  P5/P6 = folders **without** rules. Unruled folders are scanned automatically at low priority and their
  files classified through the normal flow (landing in `_Inbox/` only when no rule matches) — no manual
  quarantine step.
  - **Removed:** the `mark-unapproved` subcommand (and its function, CLI parser, and dispatch entry) and the
    entire `x`-folder concept (every `startswith("x")` check across scan, download-batch, vocab-learning,
    dedup keeper, reconcile, coverage-gaps, project-metadata, and bootstrap).
  - **Migration:** drives that were previously `x`-prefixed need no migration to keep working — an
    `xFoo` folder is now just an unruled folder (scanned at P5/P6); the `x` prefix is inert. (Renaming such
    folders back is an optional cosmetic cleanup, not required.)
  - Verified: >25 GB four-loop sandbox gate (all invariants passed) + a diff-scoped code review (1 HIGH +
    2 MEDIUM + 2 LOW fixed, incl. a tuple-form `x`-prune in reconcile that would have falsely reported a
    file in an `xml/`-named folder as missing-on-disk).

### 1.3.1 — 2026-06-17
- **Phase-0 baseline hardening** — the clean diff baseline for the v2.x incremental delivery. A full
  uncapped whole-file code review (6 cold independent agents) surfaced **144 findings (12 critical, 34
  high, 52 medium, 46 low)**; all were fixed except the `x`-prefix matches (deleted by the upcoming
  scan-priority feature). Validated: py_compile + node --check (both viewers) + the >25 GB four-loop
  sandbox gate (all invariants passed). Recorded in `~/.claude/skill-tracer-audit-ledger/drive-organizer.md`.
  Highlights:
  - **Data-loss / corruption:** path-traversal guard on every JSON-driven destination (`cmd_execute`,
    duplicates co-locate, bootstrap) via a shared `_safe_dest`; atomic writes everywhere via `_atomic_write`;
    a move-intent journal so a crash mid-`execute` is recoverable; `cmd_merge` saves to temp→verify→replace
    (no in-place corruption) and refuses to archive on partial annotation transfer; `_rename_entity`
    boundary-anchored `current_path` rewrite + single-transaction commit + pre-scan abort on collision;
    `_merge_entities` refuses when source files would be orphaned.
  - **Dedup integrity:** never mark a file duplicate against a stale/missing row; never hash a partial cloud
    materialisation (confirm fully-local first); nanosecond mtime fast-check.
  - **Cross-platform cloud detection** (BL-C2, brought forward): `_is_placeholder` now dispatches per OS
    (macOS dataless flag + in-process xattr; Windows recall/offline attributes; Linux best-effort) — no more
    per-file `xattr` subprocess.
  - **Viewer:** all-flagged pages can submit; empty POSTs no longer truncate approvals; null `current_path`
    no longer blanks the page; segments normalised (no silent depth changes); Content-Length guarded.
  - **Security/robustness:** rules-viewer `</script>` XSS closed; fitz thread-lock; bounded XML/zip peeks;
    `_is_external` fails closed on a corrupt rules file; SQLite `busy_timeout`/WAL.

### 1.3.0 — 2026-06-16
- **Phase 8 — organiser intelligence + rules viewer/editor.** Added a browser **rules viewer/editor** (`rules-viewer`): rules aggregated by entity, semantically clustered (Areas/Projects/People/Categories/Policies/Atomic/Unknown), 250/session · 25/page, with usage stats, dead-rule flags, why-routed, conflict warnings, test-a-file, coverage gaps, full CRUD + rename/merge/bulk, **rethink** (re-inference, distinct from delete), area add/rename/remove, level-promotion, partial-apply + preview/undo, light/dark. Backed by a new `rules` aggregation subcommand + per-drive `entities.json` metadata.
- **Un-locked the area set** — the five groupings are now the *default*, not a hard limit; `_active_groupings()` reads the active set from templates `Q1_groupings` or a `config.json "areas"` override (more/fewer/renamed areas supported); `_normalize_grouping`, reconcile, and the grouping invariant all read it.
- **Faster, cheaper classification.** W1 deterministic auto-classify fast-path (toggleable) + W1b delegated **fan-out** classification ([[mine-sources]] pattern — one sub-agent per 25 files, briefed with paths not content), via canonical `references/classify-prompt.md`. Cost toggles: `vision` / `skip_types` / `skip_over_mb` / `auto_classify` / `auto_approve`.
- **Bootstrap rules-builder** (`bootstrap`) — reverse-engineer rules from an existing tree: atomic-unit folders detected + approved + **locked first** (never descended), then unruled folders sampled and inferred; cold-start + audit modes.
- **Inbox arbiter sweep** — when `_Inbox/` reaches ~100 files, a parallel arbiter pass (`references/arbiter-prompt.md`) re-judges all inboxed files against the now-larger rule set; lazy `_Inbox` routing is bounced back, low-confidence reroutes surface in the viewer.
- **Scan speed-ups (W4)** — skip-rehash unchanged files via a new `mtime` column (re-scan hashing ~0s); parallel SHA256 hashing (content-peek stays sequential — PyMuPDF isn't thread-safe).
- **Learning-loop speed-ups (W5)** — aliases route to their entity, negative signals suppress wrong destinations, signal inferred from approved siblings.
- **Hardening** — 5-round `skill-tracer` (65 fixes, incl. the auto-route destination-field bug, Python-3.9 import via `from __future__ import annotations`, and a parallel-`fitz` segfault) + this `skill-publisher` polish/audit pass (SKILL.md trimmed 554→493 to clear the 500-line guidance; duplications collapsed; clarity fixes).
- **Whole-file code review (19 fixes).** A max-effort code review over the entire backend — including never-before-reviewed original code — fixed: `_peek_pdf` slicing a non-sliceable PyMuPDF Document (every PDF peek silently returned nothing); `duplicates` mis-pairing id/path/size via parallel `GROUP_CONCAT` (could co-locate the wrong file); `merge` archiving originals before saving the merged canonical, and a `_dupN` archive-collision clobber; non-deterministic `variants` group ids (salted `hash()`) → stable `sha256`; `_rename_entity` SQL `REPLACE` corrupting unrelated path segments → exact prefix rewrite; `execute` committing only once at end (a mid-batch crash left files moved but un-recorded) → per-file commit; scan/download-batch now prune external + atomic folders at every depth (not just top level); the GB cap admits at least one oversized file (no permanent stall); a `_bootstrap_apply` path-traversal guard; a reconcile `--accept` self-flag loop; the rules viewer's `const DATA`/`<option> value=`/group-header/apostrophe-escaping bugs; and a `_locked_atomic_names` helper de-duplicating four copies of the same comprehension. Validated by `py_compile` + `node --check` on both viewers + a heavy >25 GB four-loop sandbox gate (all invariants passed).

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
