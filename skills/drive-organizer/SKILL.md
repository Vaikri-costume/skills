---
name: drive-organizer
description: "Cascading-Q file organiser that sorts any drive (cloud-synced, external, or local) into configurable top-level groupings (e.g. ENTERTAINMENT, PERSONAL, WORK, EDUCATION, RESOURCES). Invoke whenever the user runs /drive-organizer or a subcommand (status, scan, propose, generate-viewer, process-return, execute, cleanup, reconcile, duplicates, variants, merge, flagged, exif, merge-category, csv-export), or asks to organise, sort, or tidy a drive, process a batch into folders, detect duplicates or variant files (e.g. plain vs highlighted PDF), reconcile a drifted folder structure, or run a rolling download-and-organise workflow. Routing follows four cascading questions — top-level grouping, thing inside, functional area, leaf type — driven by per-folder .tidy-rules.json rules that grow lazily via a learning loop. Works on any drive via a configured root (set once per machine); a Python backend keeps a SQLite registry plus an auto-mirrored CSV so duplicates are caught across batches and state stays auditable."
license: MIT
compatibility: "Python 3.9+ (standard library). Optional: mutagen (audio metadata), PyMuPDF (PDF annotation merge), organize-tool (reconcile drift-check + dedup cross-check), Pillow (image EXIF metadata). Cross-platform cloud-placeholder detection: macOS verified, Windows/Linux best-effort. The browser approval viewer needs a local display. Runs in Claude Code and Cowork."
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
metadata:
  tier: claude-users
  created: "2026-05-18"
  created-by: Vaikri-costume
  parent-version: "2.2.0"
  intended-audience: claude-users
---

# Drive Organizer

Organises the user's files into a top-level grouping nested structure with prefix-propagation one level deep — see "Naming conventions" below. The **default** five groupings are `ENTERTAINMENT/`, `PERSONAL/`, `WORK/`, `EDUCATION/`, `RESOURCES/`, but the active set is **data-driven, not fixed at five**: the backend reads it via `_active_groupings()` from the merged templates' `Q1_groupings` or an optional `<root>/.organizer/config.json` `"areas": [...]` override (a user may have more, fewer, or differently-named areas). Everything that depends on the grouping set — `_normalize_grouping`, reconcile's known-roots, the grouping invariant — reads that same dynamic set. The Python backend (`organizer.py`) handles all file I/O and database work; the registry lives at `<root>/.organizer/` as `registry.db` (SQLite, authoritative) plus `registry.csv` (auto-mirrored by the backend after every mutation — the user can open it in Numbers/Excel to audit state). This skill handles vision analysis, classification decisions, and the interactive approval loop.

**Placeholders in commands**: `<root>` and `[root]` in any command below stand for the **active configured root** — the absolute path `status` prints as the active root (set once via `--root`; defaults to this OS's OneDrive sync folder). Run `status` once at session start, capture that path, and substitute it everywhere `<root>`/`[root]` appears before running a command. **If the root path contains a space** (e.g. `/Volumes/My Drive`), wrap the substituted path in double quotes — `sqlite3 "<root>/.organizer/registry.db" …`, `cat "<root>/.tidy-rules.json"`, `find "<root>" -name …` — or the shell word-splits it and the command fails. Likewise `$SKILL_DIR` = the skill's install dir (see First-time setup).

**User profile (optional)**: if `[root]/.organizer/config.json` defines a `profile` (a note on the user's roles/context), let it guide edge-case classification. With no profile set, classify from file content and folder context alone.

**Terminology**: unfamiliar terms below — cascading-Q, atomic-unit folder, `content_peek`, `.tidy-rules.json`, per-user override, active groupings — are defined in `references/glossary.md`. Read it first if any term is unclear.

## First-time setup

Before any command, verify the backend exists:
```bash
ls ~/.claude/drive-organizer/organizer.py 2>/dev/null || echo "MISSING"
```
If missing, install it:
```bash
mkdir -p ~/.claude/drive-organizer
# SKILL_DIR = this skill's install directory. The standard Claude Code location is
# below; if the skill is installed elsewhere, set SKILL_DIR to the dir reported at
# skill load time (the one holding this SKILL.md) before running the cp.
SKILL_DIR="$HOME/.claude/skills/drive-organizer"
cp "$SKILL_DIR/scripts/organizer.py" ~/.claude/drive-organizer/organizer.py
chmod +x ~/.claude/drive-organizer/organizer.py
```
Only `organizer.py` is copied to the runtime location; the `references/` (templates, glossary, routing tables) stay in `$SKILL_DIR` and are read from there — see "templates" below. The backend looks for `references/` at the standard skills path by default; **if the skill is installed elsewhere, also `export DRIVE_ORG_SKILL_DIR=<that dir>`** so `organizer.py` finds the references (otherwise templates load empty and the taxonomy silently degrades to the bare defaults). **Optional dependencies degrade, never crash:** PyMuPDF (PDF peek + annotation merge), `mutagen` (audio tags), Pillow (image EXIF) are each optional — absent, that signal just drops (peek → route by name/path; EXIF → filename date; `merge` exits with a clean "not installed" message). The backend probes at startup and prints ONE stderr line naming any inactive feature (silent when all present) — informational, not an error. (`organize-tool` is not a runtime dependency: reconcile only *emits* a YAML artifact for an optional manual cross-check.)

**To use on a different drive or folder**, add `--root <path>` before the subcommand:
```bash
python3 ~/.claude/drive-organizer/organizer.py --root /Volumes/MyDrive scan
```
The registry will be created at `<root>/.organizer/registry.db`. The first run on the default root auto-migrates the existing registry from `~/.claude/drive-organizer/registry.db`.

## Folder structure & classification rules

Classification has two layers:

1. **Templates (source of truth)** — `references/subfolder-templates.json` ships a *generic skeleton* (the five Q1 groupings + universal compound children). Each user's own taxonomy lives in a per-user override at `[root]/.organizer/templates.json`, which the backend **deep-merges** over the skeleton. Always load the merged result via `organizer.py templates` (not by cat-ing the shipped file) — it describes the *shape* of the entire tree: the five top-level groupings (Q1), what lives inside each (Q2), what subfolders each parent type expects (Q3), and what children compound subfolders like References/ and Financials/ contain (Q4), plus the canonical "in <folder>" description for every subfolder name. New users start from the bare skeleton and grow their taxonomy via the learning loop; the override file is written/extended as rules are learned.

2. **On-disk rules (lazy state)** — `.tidy-rules.json` files distributed across the folder tree:
   - **`<root>/.tidy-rules.json`** — Q1 routing: which signals go into which top-level grouping
   - **`<root>/[Grouping]/.tidy-rules.json`** — Q2 routing inside the grouping
   - **`<root>/[Grouping]/[Thing]/.tidy-rules.json`** — Q3 routing *inside* a thing (the project/person/etc. that was the Q2 answer; this file holds the Q3 choices made within it)
   - **`<root>/[Grouping]/[Thing]/[Compound]/.tidy-rules.json`** — Q4 routing inside compound subfolders

Each level's `.tidy-rules.json` answers **one question's worth of choices** — typically 5–10 rules, not 30+. The on-disk rules grow lazily: when a file is routed to a subfolder that exists in the template but not yet in the parent's rules, propose creates the subfolder AND adds the rule (learning loop in process-return).

**At the start of every propose session:** load `references/subfolder-templates.json` once. Then for each pending file, walk the on-disk rules cascade-style (root → grouping → thing → compound), consulting the template only when an on-disk rule for the matched signal is missing.

**Description format — required convention.** Every rule's `description` field must end with `in <FolderName>` where `<FolderName>` is the value of that rule's `folderName` field. The suffix is preceded by a space, **not a comma** — `… signal terms in <FolderName>`. This is not redundant: the `folderName` field tells the executor *where* to route; the `in <FolderName>` suffix on the description makes the rule self-describing as a sentence — readable in isolation, parseable by humans skimming a rules file, and unambiguous about destination. When you add or edit any rule (in templates or in any `.tidy-rules.json`), the description must include this suffix. (For robustness against pre-existing data, the backend's `_signal_from_description` also *tolerates* a stray comma-before-`in` — `… terms, in <FolderName>` — when recovering the signal, so a legacy rule written that way still parses. That tolerance is for old data only; new rules you write must use the space form, never the comma.)

Examples:
- ✅ `"Vendor bills, utility bills, supplier invoices in Bills"` (folderName: `Bills`)
- ✅ `"[Client] workshop notes for [Project] in [Client] Workshop Notes"` (folderName: `[Client] Workshop Notes`)
- ❌ `"Vendor bills, utility bills, supplier invoices, in Bills"` (comma before `in` — incorrect punctuation)
- ❌ `"Vendor bills, utility bills, supplier invoices"` (missing `in <folder>` — incomplete)
- ❌ `"Vendor bills... in Finance/Bills"` (sub-sub path — descriptions only name the direct destination this rule routes to)

New rules are extracted from **approvals**, not rejections — when the user approves a file with an edited destination, that's the signal a new rule belongs in `.tidy-rules.json` (see process-return step 2). Rejections downstream of that get reclassified against the now-updated rules.

Scan auto-learns folder names from the existing directory tree, so folders created manually are picked up on the next scan.

**Naming conventions:**
- Top-level grouping folders: ALL CAPS — `ENTERTAINMENT`, `PERSONAL`, `WORK`, `EDUCATION`, `RESOURCES`. Always, even if the user writes lowercase.
- Companies / top-level WORK entities: ALL CAPS — e.g. `[COMPANY A]`, `[COMPANY B]`
- All other folder names: standard Title Case — lowercase short function words (`a`, `an`, `the`, `and`, `or`, `but`, `for`, `of`, `to`, `in`, `on`, `at`, `by`) unless first or last word. So: `Bills for Reimbursement`, `Bank Statements`, `Statements and Proposals`, `Tales of the City`.
- Personal-tree person subfolders: one per person (e.g. `[Person]`) plus `Joint` — siblings to each other inside any PERSONAL or EDUCATION subfolder
- Universal subfolder types (Schedules, Docs, References, Financials) live at the project root, not nested inside one another

**Prefix propagation rule.** Names propagate one level down so the path tells you what you're looking at:

| Layout | Example |
|---|---|
| `PERSONAL/` Q2 children carry the PERSONAL prefix | `PERSONAL/PERSONAL Financial/`, `PERSONAL/PERSONAL Medical/`, `PERSONAL/PERSONAL Photos/` |
| `ENTERTAINMENT/` Q2 children carry the ENTERTAINMENT prefix | `ENTERTAINMENT/ENTERTAINMENT Music/`, `ENTERTAINMENT/ENTERTAINMENT Movies and TV Shows/` |
| `EDUCATION/` Q2 children carry the EDUCATION prefix | `EDUCATION/EDUCATION Research/`, `EDUCATION/EDUCATION Masters Applications/` |
| `RESOURCES/` Q2 children carry the RESOURCES prefix | `RESOURCES/RESOURCES Fonts/`, `RESOURCES/RESOURCES Templates/` |
| `WORK/` does NOT propagate to its company children — companies are already specific enough | `WORK/[COMPANY A]/`, `WORK/[COMPANY B]/` |
| Company names DO propagate to their project children | `WORK/[COMPANY]/[COMPANY] [Project]/`, `WORK/[COMPANY]/[COMPANY] CLIENT [Person]/` |
| Beyond the project level, generic subfolder names carry no prefix | `WORK/[COMPANY]/[COMPANY] [Project]/Scripts/`, `PERSONAL/PERSONAL Financial/[Person]/Bills/` |

The grouping set is data-driven (not fixed at five). The default: **`WORK` is the one grouping whose Q2 children do NOT inherit the prefix** (companies are already specific); **every other grouping — including any user-defined area — DOES propagate its prefix to its Q2 children** (e.g. a custom `HEALTH` area → `HEALTH/HEALTH Records/`). When in doubt for a new area, propagate.

The legacy flat naming (everything at the root level) is being migrated into this nested structure. During the migration, both styles may coexist.

## Folder tree output

When the user asks to see the folder tree ("show me the folder tree", "what's the structure look like", "list the folders"), show the **intersection of rule-defined structure AND actual filesystem state** (what's organised, not what's possible). Full procedure — how to gather the two inputs via `rules --json` + a filesystem walk, the include/exclude rules, the WHY, and the output format — is in `references/subcommands.md` "folder-tree".

## Full batch cycle

```
1. scan             — fill 250-file / 20GB batch by priority order:
                       P1  downloaded files in folders WITH rules
                       P2  cloud-only files in folders WITH rules (trigger downloads to local)
                       P3  loose downloaded files at the drive root (no parent folder)
                       P4  loose cloud-only files at the drive root (trigger downloads)
                       P5  downloaded files in folders WITHOUT rules
                       P6  cloud-only files in folders WITHOUT rules (trigger downloads)
                       Stop once cumulative size hits 20GB OR file count hits 250.
2. propose          — backend prints raw pending-file records to stdout; Claude classifies + writes proposals_classified.json
3. generate-viewer  — serve browser UI; user reviews and submits
4. process-return   — handle approved/rejected/inbox/flagged; reclassify rejected; peek flagged
5. execute          — move files, update registry (which auto-mirrors to registry.csv)
6. cleanup          — remove empty folders; free disk via sync app
7. repeat from 1
8. (after all batches done) duplicates → variants → merge
```

`scan` now does its own downloading — there's no separate `download-batch` step in the cycle. The legacy `download-batch` subcommand still exists for manual top-ups but isn't part of the loop. Each scan fills the batch by walking priorities 1→6 until the budget is hit; priorities lower than where the cap landed are skipped this round. **Downloads are batched**: scan first selects the whole batch (caps + skip-rehash), then kicks every selected cloud-only file's download up front and polls the set once — so the network waits overlap each other and the hashing, rather than downloading one file at a time. Tune the per-batch wait with `DRIVE_ORG_DL_TIMEOUT` (seconds).

The registry remembers everything across batches — original names, paths, hashes, content previews — so duplicates and variants are caught even if they appeared in different batches. (Every mutation also mirrors to `registry.csv` — see the intro.)

**Important:** `duplicates`, `variants`, and `merge` are **final-pass commands only**. During the batch loop, scan flags duplicates in the registry but nothing is moved or deleted.

**Recovery (after a context compaction):** the SQLite registry at `<root>/.organizer/registry.db` is the authoritative state and survives context loss — no in-conversation marker is needed because state lives in the registry, not the chat. To resume an interrupted organise session, run `status` (active root + counts by status), then `scan` to pick up where the registry left off; the batch loop is idempotent, so re-running any step is safe — the one caveat is `execute`: replaying an already-applied `proposals_approved.json` reports its moved files as `MISSING` (expected, not a failure), so generate a fresh batch rather than re-running a consumed one.

**Handling unknown (unruled) folders:** A folder either has rules (its own `.tidy-rules.json`, or a matching entry in the root `.tidy-rules.json`) or it doesn't. Folders **without** rules are scanned at low priority (P5/P6, after ruled folders and loose root files); their files are classified through the normal flow, landing in `_Inbox/` when no rule matches. When `scan` reports `Folders with no rules`, you *may* ask the user about a folder and create a `.tidy-rules.json` to route its files — optional; they're processed either way.

---

## Subcommands

### No subcommand

**Always run the backend check and confirm the active root first**:
```bash
ls ~/.claude/drive-organizer/organizer.py 2>/dev/null || echo "MISSING"
python3 ~/.claude/drive-organizer/organizer.py status
```
Install if missing (see First-time setup above).

The `status` output shows the active root. If the user wants to work on a different folder, set it once with:
```bash
python3 ~/.claude/drive-organizer/organizer.py --root /path/to/folder status
```
This saves the new root for all future sessions. No `--root` flag needed after that.

Run scan:
```bash
python3 ~/.claude/drive-organizer/organizer.py scan --limit 250
```

Read the output (check in this order):
- **If scan reported `Folders with no rules`** → optional: add a `.tidy-rules.json` to each so its files route by rule instead of `_Inbox/`. Not a precondition for propose — they're scanned (low priority) and classified either way (see "Handling unknown (unruled) folders").
- `Pending classify > 0` → go to **propose**.
- `Pending classify = 0` **AND `Skipped` = 0 AND the run did not stop at a cap** ("→ All priorities drained within cap") → all batches are done; move to the final pass (`duplicates` → `variants` → `merge`).
- `Pending classify = 0` **but `Skipped` > 0 or the run hit a cap** → work remains (downloads that failed, or files past the cap). Run `scan` again to pick them up. **Permanent-skip guard:** if two consecutive scans report the *same* `Skipped` count and add no new pending files, those files are persistently unavailable (online-only with no connectivity, zero-byte, or unreadable) — they will never drain. Stop re-scanning, tell the user which files keep skipping (the `skip <path>: …` stderr lines name them), and treat the drive as done *excluding* them — then **proceed to the final pass** (`duplicates` → `variants` → `merge`) exactly as in the fully-drained case above. The skipped files are not lost: a file that was already registered keeps its existing row, and a first-time file that scan could not read is simply not inserted yet — either way a later scan, once the file becomes available, picks it up.

---

### Lower-frequency subcommands → `references/subcommands.md`

Detailed documentation for `status`, `download-batch`, `flagged`, `reconcile`, `duplicates`, `variants`, `merge`, `exif`, `merge-category`, and `csv-export` lives in **`references/subcommands.md`**. Consult that reference when invoking any of them. One-line summaries:

| Subcommand | What it does |
|---|---|
| `status` | Show active root + registry counts by status. Run at session start to confirm which drive is configured |
| `exif` | Print an image's routing metadata (date/camera/dimensions) as JSON for vision-off routing. Pillow-optional, degrades to the filename date, never errors |
| `merge-category` | Add one taxonomy category from a small JSON `--diff` into the per-user templates override (Python owns the merge, so a model never rewrites the whole nested file) |
| `download-batch` | Legacy — `scan` does this inline. Manual top-up for pre-warming a chunk of the drive |
| `flagged` | List files marked `?` in the viewer. Peek + reclassify each, add back to next batch |
| `reconcile` | Maintenance — detect drift (misplaced files, bad registry rows, mangled root folders); dry-run by default with a per-file `restore`/`accept` suggestion (intent never guessed), `--restore`/`--accept`/`--prune ID` to decide each, `--apply` to bulk-restore. Run when the structure has "drifted/got ruined" |
| `duplicates` | Final pass — show SHA256 groups (each with a `keeper_id`); co-locate extra copies beside the keeper as `<keeper-stem>_dupN`, one ID at a time |
| `variants` | Final pass — fuzzy-name groups for potential merge candidates |
| `merge` | Final pass — combine PDF annotations across versions of the same doc |
| `csv-export` | Manual refresh of registry.csv (auto-mirrored on every mutation, so rarely needed) |

---

### scan

```bash
python3 ~/.claude/drive-organizer/organizer.py scan --limit 250 --limit-gb 20
```

Caps each batch at 250 files OR 20GB cumulative size (whichever hits first). `scan` walks files in this priority order, triggering cloud downloads inline when it reaches a cloud-only file inside the budget:

1. **Folder-with-rules, downloaded** — files already on local disk in folders that have a `.tidy-rules.json` or appear in the root `.tidy-rules.json`. No download needed.
2. **Folder-with-rules, cloud-only** — placeholder (online-only) files in ruled folders. Scan triggers the sync app to download each, then **polls until it materialises** (up to a 30s timeout, configurable via the `DRIVE_ORG_DL_TIMEOUT` env var) before hashing — so a slow download completes in this pass instead of being deferred to a re-scan.
3. **Loose root, downloaded** — files sitting directly at the drive root (not inside any folder) that are already local.
4. **Loose root, cloud-only** — loose root files that need downloading first.
5. **Folder-without-rules, downloaded** — files in folders that have no rules yet, already local.
6. **Folder-without-rules, cloud-only** — files in unruled folders that need downloading.

The rationale: rule-bearing folders earn their files first; folders with no rules get handled last. Once the 250/20GB cap is hit, the rest is deferred to the next batch.

Report the seven counters: `New files`, `Hash-changed`, `Exact duplicates`, `Unchanged (skip-rehash)`, `Skipped`, `Pending classify`, `Total in registry`. Scan prints more besides — a `Batch size: N GB / N GB cap` line, `Downloads triggered`, a **per-phase timing line** (`download-wait` / `hashing` / `content-peek`), an `Eligible per priority` P1–P6 block, and a final stop-state line whose content is either `→ Cap reached in priority N (<label>)` or `→ All priorities drained within cap` (the script prints it indented two spaces, `  → …`, so match the line by that arrow-text content, not as a left-anchored literal). Surface the timing (e.g. mostly download-wait → network-bound; mostly hashing → large media) and the stop-state line (the No-subcommand branch keys on which of the two it is). For non-image files, scan extracts a `content_peek` (first ~300 chars of text) stored in the registry — used during `propose` to classify ambiguous files.

**If scan reports "Folders with no rules":** root-level folders with no `.tidy-rules.json` and no matching entry in the root `.tidy-rules.json`. Their files are scanned (P5/P6) and classified — `_Inbox/` when no rule matches. Optionally create a `.tidy-rules.json` inside (and a root rule) to route them better; not a precondition for propose. (See "Handling unknown (unruled) folders".)

If the script exits with `Error: root path not found: <path>`, confirm the path exists and the drive is mounted.

---

### propose

Beyond emitting the raw file records JSON, `propose` writes a sidecar at `~/.claude/drive-organizer/project_metadata.json` listing every **folder** on disk that carries a `filename_tag` **or a `date_range`** in its `.tidy-rules.json` (date-first routing is no longer projects-only — an area, an event folder, a course-term or tax-year folder can carry a `date_range`), with that folder's `date_range`. Load this sidecar at the start of every classification pass — it's how the cascading Q routes loose dated files (bills/invoices/statements/photos) to the right destination by date. **Entities can also carry a `date_range`** (in `entities.json`): a file whose date falls in an entity's range routes to that entity's folder, exactly like a folder date_range — see `references/classify-prompt.md`. An entity's `policy` field also drives routing: the `event-group` policy files the entity's dated files into date-derived subfolders (`<entity>/YYYY/Month YY/`) rather than directly under the entity folder — see `references/classify-prompt.md` "Policy-driven routing".

```bash
python3 ~/.claude/drive-organizer/organizer.py propose --limit 250
```

**Cost & speed toggles** (set durably in `<root>/.organizer/config.json`, or per-run on the command line):

| Toggle | config.json key | Per-run flag | Effect |
|---|---|---|---|
| Auto-classify fast-path | `auto_classify` (default `true`) | `--no-auto-classify` / `--auto-classify` | W1 deterministic routing of unambiguous files before classification |
| Skip file types | `skip_types` (e.g. `[".mov", ".raw"]`) | `--skip-types .mov,.raw` | Those extensions are never opened — routed by name/path/rule only |
| Skip large files | `skip_over_mb` (e.g. `200`) | `--skip-over-mb 200` | Files over N MB are never opened — routed by name/path/rule only |
| Confidence auto-approval | `auto_approve` (default `false`) | `--auto-approve` | W5: **W1 fast-path** auto-routed files (deterministic rule match — NOT a classifier `confidence` verdict) marked `auto_approved` — orchestrator may skip the viewer (still audited in `<root>/.organizer/auto-routed.csv`) |

A toggled-off / blocked file is never dropped: the W1 matcher gives it a deterministic destination when one exists, otherwise it reaches the classifier as `route_by_name_only` (or falls to `_Inbox/`).

#### Model capabilities — graceful degradation (model-agnostic)

**The backend is model-agnostic: two capabilities — `peek` (open file contents) and `vision` (see images) — gate how classification agents inspect files, and degradation never drops a file** (a model with neither routes by name/path/rules/EXIF, reaching `_Inbox/` only when nothing matches). Both are declared in `<root>/.organizer/config.json` under `model_capabilities` (default `true`; precedence **flag > config > default**; flags `--no-peek` / `--no-vision`). `propose` resolves them and prints a `Model capabilities: peek=… vision=…` stderr line you copy into the `[CAPABILITIES]` slot (filled per "Fan out classification" below). The exact per-capability degradation behaviour is in `references/classify-prompt.md` (the agents read it).

If the script prints `"No pending files. Run 'scan' first or all files are already classified."`, this batch is fully classified — free disk and move to the next batch.

**Routing model — four cascading questions.** Each file answers questions in order, narrowing the destination one level at a time:

```
Q1: Which top-level grouping?   ENTERTAINMENT / PERSONAL / WORK / EDUCATION / RESOURCES
Q2: Which thing inside?         Music / Financial / [Company] / Research / Fonts / ...
Q3: Which functional area?      Person / Scripts / Financials / References / Admin / ...
Q4: Which leaf type?            Bills / [Person] / Contracts / [Project Name] / ...
```

Most files terminate at Q3 or Q4; some go deeper (Q5 inside a per-person Financials tree). Folders only get created when files actually need them — empty scaffolding is not pre-built.

**Load templates and root rules first:**

```bash
python3 ~/.claude/drive-organizer/organizer.py templates                   # merged templates (shipped skeleton + your override)
cat <root>/.tidy-rules.json                                                # Q1 routing
```
(`<root>` is whatever `status` prints as the active root.)

**Read the propose output — three lanes.** `propose` now pre-sorts the batch so you only classify what actually needs it:

- **`auto_routed: true`** — the deterministic fast-path (W1) already chose the destination and wrote it to **`para_subfolder`** (the canonical routing field the viewer, bubble-sort, and execute all read; `proposed_subfolder` carries the same value as a readable alias). The entry also carries `auto_reason` — the match reason (e.g. "already in ruled folder") — which is informational + mirrored to `auto-routed.csv`; you don't need to act on it. Accept the entry as-is; do **not** re-classify.
- **`needs_classification: true`** — the real work. Each carries a `classify_batch` index (groups of 25).
- **`route_by_name_only: true`** (a subset of the above) — a cost toggle blocked opening this file. `open_blocked_reason` is a **list** whose values are exactly `vision-off`, `skip-type`, and `>{N}MB` (these three are the only reasons the backend emits — a closed set; e.g. `["vision-off","skip-type"]`, or `[">200MB"]` — the MB number is fractional if the cap is, e.g. `>200.5MB`), not a single value. Classify it from `filename` + `current_path` + rules **only — never open it**; `content_peek` is deliberately null. If nothing matches, route to `_Inbox/`. (The backend never sends a blocked file to `_Inbox/` itself — it auto-routes when the W1 matcher finds a rule, else hands it to you as `route_by_name_only`; the `_Inbox/` fallback is the classifier's decision, i.e. yours.)

**Fan out classification — one sub-agent per `classify_batch` (mine-sources pattern).** Rather than classify every file inline, dispatch one Agent per batch of 25 so each works a small set with a fresh context and raw file content stays out of the orchestrator. **Use the canonical template `references/classify-prompt.md`** — "stage one filled copy per `classify_batch`" means: fill the template's slots in working memory once per batch (no temp file is written to disk, so there is nothing to name or clean up) and dispatch that filled prompt as the agent's instructions, so every batch is briefed identically. Then dispatch:

- Fill the template's slots: `[BATCH_JSON]` = that batch's records (`{id, filename, current_path, is_image, route_by_name_only, content_peek?}` — **paths, never file contents**); `[GROUPINGS]` = the active grouping names — read them from `organizer.py rules --json` → the top-level `areas` array (that is the *resolved* active set from `_active_groupings()`, which honours a `config.json "areas"` override; do NOT read `templates` `Q1_groupings` here — it misses the override and its entries may be strings or dicts); `[ROOT]`, `[TEMPLATES_CMD]`, `[PROJECT_METADATA_PATH]`, `[ENTITIES_PATH]`, `[FILE_TYPE_ROUTING_PATH]`, `[TIDY_BUILTIN_PATH]`, `[FILENAME_CONVENTIONS_PATH]`, `[GLOSSARY_PATH]` = the absolute paths/commands (the four `references/` slots are `$SKILL_DIR/references/<file>` — capture `$SKILL_DIR` at load time); `[CAPABILITIES]` = the declared model capabilities — copy them from propose's `Model capabilities: peek=… vision=…` stderr line so each agent inspects files only by permitted means (see "Model capabilities" above). The template keeps the prompt light by **pointing** the agent at those (it reads them itself) and inlining only the batch + rules + output contract.
- The agent opens each file itself (Read / vision) — subject to the declared `[CAPABILITIES]` (see "Model capabilities" above) and unless `route_by_name_only` — applies the cascading-Q logic, respects entity aliases/negatives, and returns one verdict per file: `{id, para_subfolder, new_filename, reason, signal, confidence, file_date?, vision_desc?}` — **verdicts only, not file content**. (Carry the verdict's `file_date` into the entry you write: it is how a **document's** date reaches execute's `date_range` widening — photos get their date from scan's `-PHOTO-` pattern, but a bill/statement only has the date the classifier reads from its name/content, so without it the period never widens for documents.) (`reason` is the human-readable rationale the viewer shows; `para_category` is NOT in the verdict — execute derives it from `para_subfolder`. The `signal` + `confidence` fields feed W5: shared signals become rules. Note `confidence` is **advisory** — the backend's `auto_approved` flag is set only on W1 fast-path entries (it never reads a classifier verdict's `confidence`); so a `confidence: high` verdict does not auto-approve by itself. If `auto_approve` is on and you choose to let high-confidence verdicts skip the viewer, that is *your* orchestration decision — mark them yourself and keep the CSV audit.) A **low-confidence** verdict (`low` is the only value other than `high` — the classifier emits a closed `high|low` set, never `medium`; see classify-prompt.md) needs no special handling: route the file to the `para_subfolder` the verdict gives and surface it in the viewer like any other entry for human confirmation. Confidence only ever gates **up** (high → optional auto-approve skip); it never gates down — a `low` verdict never drops a file, re-routes it, or forces `_Inbox/` on its own (use `_Inbox/` only when no destination could be decided at all).
- Merge every batch's verdicts together with the unchanged `auto_routed` entries into `~/.claude/drive-organizer/proposals_classified.json`.
- **Reliability — retry once, then route:** if a batch's agent errors or returns malformed JSON, re-dispatch it ONCE with the identical prompt (the exact same filled `classify-prompt.md` you dispatched the first time — re-send it verbatim, do not re-fill or alter it); if it still fails, route that batch's files to `_Inbox/` (surfaced in the viewer for manual placement) rather than dropping them or aborting, and log the bounced batch index.

**Inbox arbiter sweep — periodic `_Inbox/` reclamation.** When the registry's `_Inbox/` population reaches ~100 files (`organizer.py inbox-list` → `count`), run a reclamation sweep that re-judges **all** inboxed files against the now-grown rule set, dispatching one arbiter per 25 in parallel. The full trigger rationale, the dispatch + `[CAPABILITIES]` fill, and the `confirm_inbox`/`reroute_high`/`reroute_low` apply rules live in `references/arbiter-prompt.md` under **"When + how the orchestrator runs the sweep"** (same pointer-not-inline discipline as the classify fan-out).

WHY fan out: accuracy (a fresh agent on 25 files beats one context dragging 250), less orchestrator decision-fatigue, and content hygiene (each batch's context is discarded). For a tiny residual (a single batch ≤25) you may classify inline — the fan-out earns its keep at scale.

**The per-file classification logic each agent applies** (pre-bucket by Q1, lazy-load `.tidy-rules.json` + path_vocab, entity matching in `content_peek`, the per-level routing decision + templates-fallback, the both-axes file-type rules, RAW/images/photos/atomic/external/audio handling) lives in `references/classify-prompt.md` under **"Per-file classification logic"** — it is the agent's briefing, so it is documented there with the template, not inlined here. The fan-out agents read it; the orchestrator does not need it in always-loaded context.

**Build `proposals_classified.json` (orchestrator).** `propose` prints the per-file records to **stdout** in `id` order and does not write the proposals file — **you** capture those records, enrich the `needs_classification` ones with the fan-out verdicts, and write `~/.claude/drive-organizer/proposals_classified.json` yourself. (It does write two *side* files: the `project_metadata.json` sidecar always, and appends `auto-routed.csv` when anything auto-routed — not the proposals file.) Each stdout record carries the base fields (`id`, `current_path`, `filename`, `extension`, `file_size`, `file_date`, `is_image`, `content_peek`) **plus** its lane fields — `auto_routed` on every record, and per lane `para_subfolder`/`proposed_subfolder`/`auto_reason`/`auto_approved?` (auto-routed) or `needs_classification`/`classify_batch` (+`route_by_name_only`/`open_blocked_reason` when blocked). The two lanes are **disjoint by `id`** (a file is `auto_routed` OR `needs_classification`, never both), so the file is a straight union: auto-routed records keep their `para_subfolder`/`auto_reason`; classified records get the verdict's `para_subfolder`/`reason`/`signal`/`confidence`; both share the base columns. Also include any reclassified-rejected entries from the previous viewer round (see **process-return**). You don't need to sort — `generate-viewer` bubble-sorts when it serves (`_bubble_sort_proposals`).

**Filename conventions, project metadata, and the `proposals_classified.json` entry shape** live in `references/filename-conventions.md` (grouping-specific naming patterns, reading `content_peek` before naming, the `filename_tag` + `date_range` fields, period expansion, worked examples, the JSON shape).

Tell the user the proposals are ready and how many were classified. **Do not launch the viewer yet.** Wait for them to explicitly say "launch the viewer" or equivalent — they may still be reviewing, giving feedback, or making corrections. Auto-launching while they are still talking interrupts their workflow.

---

### generate-viewer

```bash
python3 ~/.claude/drive-organizer/organizer.py generate-viewer \
  --proposals ~/.claude/drive-organizer/proposals_classified.json
```

**Before launching, snapshot the served baseline.** Keep this round's `proposals_classified.json` in memory as a dict keyed by `id` (the pre-edit destinations). process-return step 2 compares the user's approved destinations against this snapshot to detect inline edits, and step 9 will overwrite the file — so capture it here, at launch, or the baseline is lost. **Fallback if the in-memory snapshot is gone** (e.g. the context was compacted between generate-viewer and process-return): re-read `~/.claude/drive-organizer/proposals_classified.json` from disk — it still holds the pre-edit destinations right up until step 9 rewrites it, so the on-disk file IS the baseline until then. Only if both are unavailable do you lose edit-detection (then learn from explicitly-edited entries the user calls out, and continue).

Opens a browser viewer at localhost:5002. **Proposals are bubble-sorted by destination before pagination** — files going to the same leaf appear together, prefixed with a `→ <destination> (N files) [Approve group]` header row. `_Inbox` items sort to the bottom and render in purple. 25 files per page; pages = ceil(total ÷ 25). If a group spans pages, each page's header shows that page's slice (consistent count-vs-content within the page).

**Cowork / headless fallback (`--static`).** The localhost server is unreachable from Cowork (the user's browser is not on this host). Pass `--static`, or set `DRIVE_ORG_HEADLESS=1` (auto-detected from Cowork env markers), and `generate-viewer` instead writes a **self-contained editable review file** (`~/.claude/drive-organizer/proposals_review.html` — no server, no localhost POST) plus a **pre-filled `proposals_approved.json`** (every file defaulted to `approved` at its proposed destination). The user reviews/edits in the HTML and clicks **Download** to produce an updated `proposals_approved.json`, or edits the pre-filled JSON directly, then you continue to process-return as normal — the approved-entry schema is identical to the served viewer's, so only the transport differs. To accept everything unattended, skip the HTML and run process-return against the pre-filled file. (`--no-open` is a third option: run the localhost server but don't auto-open a browser — for local headless testing where the port *is* reachable. Rules viewing is reachable headlessly via `rules` / `rules --json` and `rules-viewer --no-open`.)

User reviews, edits destinations and filenames inline, then uses one of five action buttons per row (note: the `?` flag is not an `action` value — it persists to the registry, so only the other four reach `proposals_approved.json`; re-clicking a set button toggles the row back to `unset`, which is dropped from the output like any unreviewed row):

| Button | Meaning | What happens |
|--------|---------|--------------|
| ✓ | Approve — move to proposed destination | `action: 'approved'` in JSON |
| ✗ | Wrong — reclassify using context | `action: 'rejected'` in JSON; the served `para_subfolder` (for a classified file, its verdict destination) is carried through for process-return to reclassify against the baseline |
| ? | No idea — Claude peeks and reproposes | File marked `status='flagged'` in registry |
| 📥 | I need to open this myself (EPS, etc.) | `action: 'inbox'` in JSON; moves to `_Inbox/` |
| 🗑 | Move to deletion staging | `action: 'delete'` in JSON; moves to `Archive/_To Delete/` (never deleted from disk) |

On submit, the server writes `~/.claude/drive-organizer/proposals_approved.json` and shuts down.

**Check the server's final log line before continuing.** Once you see `Server shutting down.`, both `proposals_approved.json` and `proposals_flagged.json` are on disk. The full interpretation of the after-submit log lines — the write-failure case (server still running, nothing saved, do NOT proceed), the flagged-line cases, the manual registry-patch recovery, and the `proposals file not found` / `port in use` errors — is in `references/subcommands.md` under **"generate-viewer (submit-response handling)"**. The one rule to keep in mind here: **no `Server shutting down.` line ⇒ the submit was NOT saved — do not run process-return.**

---

### process-return

**Run this sequence every time the user says they have submitted the viewer** — whether they say "done", "submitted", "I've reviewed X files", or similar. Each step feeds the next, so run it as one automated pipeline (don't pause to ask "what next?") — this preserves context-window state and avoids intermediate state drift. "Don't pause" governs **procedural** permission only: never stop between steps to ask whether to continue. It does **not** suppress the **substantive** questions a step explicitly calls for — e.g. step 2's "does this `[Client] Workshop Notes` pattern generalize to other projects?" is a content decision the rule-learning needs, so ask it inline as it arises and proceed; that is part of the pipeline, not a pause. (Step 10 is the exception — it does not auto-launch the viewer; that rule is stated there.)

```
1. Read proposals_approved.json
2. Learn from APPROVED files first — this must happen before any reclassification. For every approved entry, compare its final `para_subfolder` against the **baseline snapshot you captured at generate-viewer launch**, matched by `id` (never by position — bubble-sort reorders entries; do this before step 9 refills `proposals_classified.json`). Any difference is a learning signal — the user edited the destination inline before approving.

   For each new destination that didn't previously exist in `.tidy-rules.json`:

   **New top-level folder** (folder name not in root `.tidy-rules.json`):
   → Add a new rule entry to root `.tidy-rules.json`. The file's top-level shape is `{"rules": [ … ]}` — an object with a `"rules"` array; append the new rule object to that array (create the file as `{"rules": [<rule>]}` if it doesn't exist yet). Each rule's format: `{"folderName": "<folder name>", "description": "<signal terms that identify this folder> in <folder name>"}`. These are the only two fields the backend reads (`_aggregate_rules` / `_build_rules_index` key on `folderName` + `description`); the `description` must end with the `in <folderName>` suffix (see "Description format" above). (Legacy rules may also carry `id`/`createdAt` — harmless extra fields; don't add them to new rules.)

   **New subfolder within an existing project** (e.g. `[Client] Workshop Notes` appears in a `[COMPANY] [Project]/` folder):
   → Identify the proper noun(s) in the subfolder name — e.g. "[Character]" is a character name, "[Person]" is a person name, etc.
   → Abstract to a pattern: `Acme Workshop Notes` → `[Client] Workshop Notes`
   → Ask the user: *"Does `[Client] Workshop Notes` apply to other project folders too, or is this one-off for this project?"*

   Subfolder rules go in the **per-folder** `.tidy-rules.json`, never in root descriptions (that pollutes the top-level match signal). **Project-specific** → that one project's file, writing the CONCRETE folder name (expand any `[Placeholder]` to the real name — the matcher tokenises `folderName` literally). **Generalizable across a project type** → `references/subfolder-templates.json`. Full rules + worked example: `references/filename-conventions.md` "Writing a new subfolder rule".

   Either way, the pattern is named and recognized going forward — the same proper-noun slot will match future instances.

   **Routing corrections to existing folders** (e.g. the user moved `Resources/Templates` items to `[COMPANY] Admin/Templates`) → update the source folder's `.tidy-rules.json` to redirect that signal, and/or add a more specific rule to the destination folder. The next propose call will route correctly.

   Append only new facts. These files persist across sessions — if lessons aren't written back, the same misclassifications repeat.

3. Now separate the remaining entries by action field, using the now-updated rules. `proposals_approved.json` contains **only** the four action values below — flagged and unreviewed rows are never written to it (flagged go to the registry + `proposals_flagged.json`; unreviewed go nowhere), so these four cases are exhaustive:
   - action='approved'  → keep as-is for execute
   - action='inbox'     → keep as-is for execute (para_subfolder already set to '_Inbox' by viewer)
   - action='rejected'  → reclassify against the freshly-updated `.tidy-rules.json` (which now reflects everything learned in step 2). A rejection means the proposed destination was wrong — apply the updated rules to determine the correct folder. Do not send to `_Inbox/` unless no rule applies; that defeats the purpose of the rejection. **When you rewrite a rejected entry, update `para_subfolder` (and `new_filename` if needed), carry `file_date` through unchanged, and flip `action` from `'rejected'` to `'approved'`** — the entry now has a correct destination, so it must read as approved or step 4's "remove remaining rejected entries" would drop it before execute. (If that `file_date` is null and you can now read the document's date, fill it; carrying null just skips the period update.) (Leave `action='rejected'` ONLY on an entry you genuinely could not reclassify — that one is removed at step 4.) execute uses `file_date` to widen the destination project's `date_range`; dropping it silently skips that update.
   - action='delete'    → execute will route to `Archive/_To Delete/` (not deleted from disk)

4. Write the corrected list (approved + inbox + reclassified + delete) back to proposals_approved.json,
   removing any remaining rejected entries.
5. Run execute on the corrected proposals_approved.json
6. Run cleanup — **unless** execute printed `"Approved list is empty."` (every row was flagged/unreviewed, nothing moved); then skip cleanup and go to step 7
7. Run flagged — if it prints `"No flagged files."`, skip this step. Otherwise, for each flagged file, peek content/vision and classify (**same logic as propose** = the same classification step the propose fan-out uses — fill `references/classify-prompt.md` per the "Fan out classification" rules above and decide a `para_subfolder`; for the peek procedure see references/subcommands.md `flagged` step 1). These become new proposals entries, not chat resolutions.
8. Re-run propose --limit 250 to pull new pending files
   (The propose→viewer→process-return cycle terminates by the **same stop condition as the No-subcommand loop** — which is read off `scan`, not `propose`: `scan` is the command that prints `Pending classify`, `Skipped`, and the cap/`→ drained` stop-state line, so the loop ends when a fresh **`scan`** reports `Pending classify = 0` AND `Skipped = 0` AND the run did not stop at a cap — see "No subcommand" above. `propose` only pulls the next batch of pending files; it has no cap and reports none of those counters. Until the scan is clean, step 10 hands the next batch back to the user.)
   (`--limit` is a cap, not a target — over-asking is harmless; the backend returns at most that many *pending* files. The reclassified-rejected and newly-classified-flagged entries from steps 3/7 are merged in at step 9, so you don't subtract them here — and they **can't** be double-returned by propose anyway: by the time step 8's propose runs, `execute` (step 5) has already set every reclassified-rejected row to `status='organized'` and every flagged row is `status='flagged'`, and propose only returns `status='pending'` rows — so the cap and the merge never overlap. (Even if an `id` did slip through twice, step 9's id-keyed merge dedups it.))
9. Merge reclassified entries + flagged entries + new pending files into proposals_classified.json. All three sources share the **same classified-entry shape** (the base + lane fields written to `proposals_classified.json`), so the merge is a concatenation keyed by `id` — if an `id` somehow appears twice, the reclassified/flagged version (the freshly-decided one) wins over a stale pending record. Write the union back as the new `proposals_classified.json`.
10. Tell the user the new batch is ready (N files, X pages). Do NOT launch the viewer — wait for them to ask.
```

**Why learnings come before reclassification** (a rejection's correct destination often depends on a pattern the user just demonstrated by editing an approved entry — learn first, then reclassification is a lookup, not a guess), the **delete-routing note** (execute hard-codes `Archive/_To Delete/` for `action='delete'`, ignoring the entry's `para_subfolder`; the registry records the actual destination), and the **W5 learning-loop accelerators** (auto-infer the signal from common tokens, learn negative signals from rejections, aliases, proactive "make a rule?", opt-in confidence auto-approval) all live in `references/subcommands.md` under **"process-return (learning-loop accelerators + routing notes)"**.

---

### execute

```bash
python3 ~/.claude/drive-organizer/organizer.py execute \
  --approved ~/.claude/drive-organizer/proposals_approved.json
```

The execute script reads `action` for delete entries only (routes them to `Archive/_To Delete/` regardless of `para_subfolder`; full registry-recording detail in process-return's "Note on routing" above — that is the canonical statement, not duplicated logic). For all other entries, routing is determined entirely by `para_subfolder`. On each successful move execute also sets the registry `status`: **`'to_delete'`** for `action='delete'` rows, **`'organized'`** for every other moved row (these are the two terminal statuses execute writes; `duplicate`/`archived`/`flagged`/`deleted` are written by other subcommands). Before running execute, the proposals_approved.json must already have rejected entries replaced with their reclassified versions (see process-return step 3). This is a hard precondition, not advice — every entry reaching execute **must** already carry these values (process-return steps 2–4 guarantee them):
- Approved entries → `para_subfolder` set by user in viewer
- Inbox entries → `para_subfolder` = `'_Inbox'` (pre-set by viewer JS)
- Reclassified entries → `para_subfolder` updated by Claude in process-return step 3 (step 2 is the approved-files learning pass; the `action='rejected'` reclassification against the freshly-updated rules is step 3)
- Delete entries → routed by `action == 'delete'` check in script; `para_subfolder` is ignored

Report: files moved, any errors. If errors > 0, check stderr. Three error shapes (each increments the `errors` count):
- `ERROR moving <src>: <e>` — the move itself failed (e.g. permissions, long path); the file is still at `<src>` and can be re-run after investigation.
- `MISSING: <src>` — the recorded `current_path` no longer exists on disk (the file was moved, renamed, or deleted **outside** the tool since it was registered). It is NOT at its original location. Don't blindly re-run; run `reconcile` to detect/repair the registry-vs-disk drift (the `bad_registry_rows` / relocated detection), or locate the file (see "Long filenames" below) and fix the row.
- `ERROR: <empty/missing|unsafe (escapes the drive root)> destination subfolder '<sub>' for <src> — skipped.` — the entry's `para_subfolder` was blank or resolved outside the drive root, so execute skipped it (the file stays put). This means a reclassified or hand-edited entry reached execute with a bad `para_subfolder`; fix that entry's destination (process-return step 3) and re-run, don't force the move.

Then run cleanup regardless (unless execute printed `"Approved list is empty."` — see below).

**Date-range auto-expansion.** After each successful file move, execute calls `_expand_date_range` on the destination project (walking ancestors to find a folder whose `.tidy-rules.json` has a `filename_tag`). It widens `date_range` to encompass the file's date, with a one-month buffer on each side (the code's `buffer_days=30` default is authoritative — "one month" is the human description; this SKILL note is the single prose home, the reference points here). First file in a fresh project initialises the period; subsequent files only widen it if their date falls outside the existing range. Skipped for `action='delete'` and for files without a known date.

If execute exits with `"Error: approved file not found: <path>"` — the viewer didn't write the output file. Re-open the viewer with `generate-viewer` and re-submit.

**Empty approved list:** if execute prints `"Approved list is empty."`, every submitted row was flagged or left unreviewed. Run `flagged`. Skip cleanup.

**Long filenames causing MISSING errors**: Some files with very long filenames (>200 chars) or special characters (apostrophes, quotes) fail path matching. Find them with `find [root] -name "*partial_name*"` (the active root is shown by `status`) and move manually with `shutil.move` or `mv`, then update the registry directly.

---

### cleanup

```bash
python3 ~/.claude/drive-organizer/organizer.py cleanup
```

Removes empty directories left behind after execute. The root-level staging folders (`_Inbox/`, `Archive/`) and the Archive subdirs (`Archive/_To Delete/`, `Archive/_Duplicates/`, `Archive/_Merged-Originals/`) are never deleted. Report how many folders were removed, then free local disk space by evicting the organised grouping folders (e.g. `WORK/`, `PERSONAL/` — not the staging folders) to online-only. Pass **`cleanup --evict`** to automate this per-OS (best-effort; falls back to the manual recipe on failure / unsupported OS); without it, tell the user the manual per-app recipe. Full behaviour + per-OS commands + recipes in `references/subcommands.md` "cleanup".

If the script exits with `Error: root path not found: <path>`, confirm the drive is mounted and the sync app is running.

---

## Rules tools — view, edit, and bootstrap

Three commands operate on the *rules* (not files), all reading the aggregated view (`rules`) where each entity = a folder name grouped across the whole tree:

- **`rules`** — clustered one-line-per-entity summary (Areas / Projects / People / Subfolders / Policies / Atomic / Unknown). `rules --json` feeds the viewer.
- **`rules-viewer`** (`--port 5003`) — browser editor: clustered cards (250/session, 25/page), per-entity type/aliases/relation/behaviour/notes + signal, usage stats, dead-rule flag, why-routed, conflict warnings, test-a-file, coverage gaps, full CRUD + rename/merge/bulk, **rethink** (flag for re-inference, ≠ delete), area add/rename/remove, level-promotion dry-run, **Apply (keep open)** / **Preview** (per-change undo) / **Save & close**. Adapts to light/dark.
  - **⚙ Settings panel** — a collapsible panel that reads/writes the per-drive `<root>/.organizer/config.json` settings: `peek` / `vision` (model_capabilities), `auto_approve`, `skip_types`, `skip_over_mb`. "Save settings" POSTs to a separate `/config` endpoint — independent of the rule-edit Save/Apply, so changing settings never touches the rule set. This panel is the single settings surface: any new toggle/dial added later is wired in here too.
- **`bootstrap`** — reverse-engineer rules from an existing tree, for a new or partly-organised drive.

### bootstrap (setup walkthrough)

Order matters — **atomic units are approved + locked FIRST**, so the inference never wastes effort descending into them:

1. **`bootstrap --detect-atomic`** — lists atomic-unit folders (venvs, `node_modules`, `.git` repos, Zotero/photo libraries, `.app` bundles, Unity projects). Show them to the user.
2. **`bootstrap --lock <names>`** — on the user's approval, writes those units to `entities.json` as `entity_type: atomic, locked: true`. Scan/propose/bootstrap never descend into a locked unit again (it's one entity).
3. **`bootstrap --emit [--mode cold-start|audit] [--sample K] [--limit 250]`** — samples every unruled folder with files (K files each: name + content_peek + ext) and writes `<root>/.organizer/bootstrap-input.json` (candidates batched 25/group, capped at 250). *cold-start* = infer the whole taxonomy; *audit* = also flag ruled folders whose sample routes elsewhere (drift, feeds reconcile).
4. **Claude infers each candidate** — first check the file `--emit` wrote: if `bootstrap-input.json` is absent or its candidate list is empty (every folder already has rules, or the drive has no unruled folders with files), there is nothing to infer — report "nothing to bootstrap" and stop the walkthrough here. Otherwise fan out one sub-agent per batch of 25 (briefed with the folder + its sample only — never inline more than the sample), inferring a rule + a metadata guess per folder. Write the result to `<root>/.organizer/bootstrap-proposed.json` as a JSON object with `rules[]` + `entities{}` keys — exact shape (and the non-object-rejected rule) in `references/subcommands.md` "bootstrap".
5. **`bootstrap --apply <root>/.organizer/bootstrap-proposed.json`** — writes each rule into its folder's parent `.tidy-rules.json` and the metadata into `entities.json`.
6. **`rules-viewer`** — the user reviews/edits the inferred rules (pre-filled, 25/page, clustered) before relying on them. Inference is a *good guess to edit*, not a silent commit.

---

## proposals_approved.json format

The viewer writes `proposals_approved.json` on submit — the `proposals_classified.json` entry shape plus an `action` field whose **closed set** is exactly `"approved"` | `"rejected"` | `"inbox"` | `"delete"` (flagged `?` rows are NOT in this file — they go to the registry as `status='flagged'`). Full shape + the unknown-action-coercion caveat: `references/filename-conventions.md` "proposals_approved.json shape".

## Memory

`.tidy-rules.json` files are the classification memory. The root `.tidy-rules.json` defines every known project and folder; sub-folder `.tidy-rules.json` files define what goes inside. Confirmed project names, routing decisions, and naming corrections are written there as they are established — they persist across sessions automatically.

If `[root]/.organizer/config.json` defines a `memory_doc_path`, that document holds supplementary context that doesn't fit the rules format (e.g. background on a project, disambiguation notes). Read it only when classification is ambiguous and `.tidy-rules.json` doesn't resolve it.

## Tone

One line per file: path → destination → reason.
