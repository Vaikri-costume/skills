---
name: drive-organizer
description: "Cascading-Q file organiser that sorts any drive (cloud-synced, external, or local) into five top-level groupings — ENTERTAINMENT, PERSONAL, WORK, EDUCATION, RESOURCES. Invoke whenever the user runs /drive-organizer or a subcommand (status, scan, propose, generate-viewer, process-return, execute, cleanup, reconcile, duplicates, variants, merge, mark-unapproved, flagged, csv-export), or asks to organise, sort, or tidy files, process a batch into folders, detect duplicates or variant files (e.g. plain vs highlighted PDF), reconcile a drifted folder structure, or run a rolling download-and-organise workflow. Routing follows four cascading questions — top-level grouping, thing inside, functional area, leaf type — driven by per-folder .tidy-rules.json rules that grow lazily via a learning loop. Works on any drive via a configured root (set once per machine); a Python backend keeps a SQLite registry plus an auto-mirrored CSV so duplicates are caught across batches and state stays auditable."
license: MIT
compatibility: "Python 3.9+ (standard library). Optional: mutagen (audio metadata), PyMuPDF (PDF annotation merge), organize-tool (reconcile drift-check + dedup cross-check). macOS-oriented — uses xattr for cloud-placeholder detection; the browser approval viewer needs a local display. Runs in Claude Code and Cowork."
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
metadata:
  tier: claude-users
  created: "2026-05-18"
  created-by: Vaikri-costume
  parent-version: "1.1.0"
  intended-audience: claude-users
---

# Folder Organiser

Organises the user's files into a five-grouping nested structure (`ENTERTAINMENT/`, `PERSONAL/`, `WORK/`, `EDUCATION/`, `RESOURCES/`) with prefix-propagation one level deep — see "Naming conventions" below. The Python backend (`organizer.py`) handles all file I/O and database work; the registry lives at `<root>/.organizer/` as `registry.db` (SQLite, authoritative) plus `registry.csv` (auto-mirrored by the backend after every mutation — the user can open it in Numbers/Excel to audit state). This skill handles vision analysis, classification decisions, and the interactive approval loop.

**User profile (optional)**: if `[root]/.organizer/config.json` defines a `profile` (a note on the user's roles/context), let it guide edge-case classification. With no profile set, classify from file content and folder context alone.

## First-time setup

Before any command, verify the backend exists:
```bash
ls ~/.claude/drive-organizer/organizer.py 2>/dev/null || echo "MISSING"
```
If missing, install it:
```bash
mkdir -p ~/.claude/drive-organizer
# SKILL_DIR is the directory containing this SKILL.md file
cp "$SKILL_DIR/scripts/organizer.py" ~/.claude/drive-organizer/organizer.py
chmod +x ~/.claude/drive-organizer/organizer.py
```
`$SKILL_DIR` is the base directory reported at skill load time (e.g. `~/.claude/skills/drive-organizer`).

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
   - **`<root>/[Grouping]/[Thing]/.tidy-rules.json`** — Q3 routing inside a thing (project, person, etc.)
   - **`<root>/[Grouping]/[Thing]/[Compound]/.tidy-rules.json`** — Q4 routing inside compound subfolders

Each level's `.tidy-rules.json` answers **one question's worth of choices** — typically 5–10 rules, not 30+. The on-disk rules grow lazily: when a file is routed to a subfolder that exists in the template but not yet in the parent's rules, propose creates the subfolder AND adds the rule (learning loop in process-return).

**At the start of every propose session:** load `references/subfolder-templates.json` once. Then for each pending file, walk the on-disk rules cascade-style (root → grouping → thing → compound), consulting the template only when an on-disk rule for the matched signal is missing.

**Description format — required convention.** Every rule's `description` field must end with `in <FolderName>` where `<FolderName>` is the value of that rule's `folderName` field. The suffix is preceded by a space, **not a comma** — `… signal terms in <FolderName>`. This is not redundant: the `folderName` field tells the executor *where* to route; the `in <FolderName>` suffix on the description makes the rule self-describing as a sentence — readable in isolation, parseable by humans skimming a rules file, and unambiguous about destination. When you add or edit any rule (in templates or in any `.tidy-rules.json`), the description must include this suffix.

Examples:
- ✅ `"Vendor bills, laundry bills, costume expenses, supplier bills in Bills"` (folderName: `Bills`)
- ✅ `"[Character] Costume Trials photos for [Project] in [Character] Costume Trials"` (folderName: `[Character] Costume Trials`)
- ❌ `"Vendor bills, laundry bills, costume expenses, supplier bills, in Bills"` (comma before `in` — incorrect punctuation)
- ❌ `"Vendor bills, laundry bills, costume expenses"` (missing `in <folder>` — incomplete)
- ❌ `"Vendor bills... in Finance/Bills"` (sub-sub path — descriptions only name the direct destination this rule routes to)

New rules are extracted from **approvals**, not rejections — when the user approves a file with an edited destination, that's the signal a new rule belongs in `.tidy-rules.json` (see process-return step 2). Rejections downstream of that get reclassified against the now-updated rules.

Scan auto-learns folder names from the existing directory tree, so folders created manually are picked up on the next scan.

**Naming conventions:**
- Top-level grouping folders: ALL CAPS — `ENTERTAINMENT`, `PERSONAL`, `WORK`, `EDUCATION`, `RESOURCES`. Always, even if the user writes lowercase.
- Production companies / top-level WORK entities: ALL CAPS — e.g. `[COMPANY A]`, `[COMPANY B]`
- All other folder names: standard Title Case — lowercase short function words (`a`, `an`, `the`, `and`, `or`, `but`, `for`, `of`, `to`, `in`, `on`, `at`, `by`) unless first or last word. So: `Bills for Reimbursement`, `Bank Statements`, `Statements and Proposals`, `Tales of the City`.
- Personal-tree person subfolders: one per person (e.g. `[Person]`) plus `Joint` — siblings to each other inside any PERSONAL or EDUCATION subfolder
- Scripts, Schedules, Scene Breakdown live at the project root — not inside `Docs/`

**Prefix propagation rule.** Names propagate one level down so the path tells you what you're looking at:

| Layout | Example |
|---|---|
| `PERSONAL/` Q2 children carry the PERSONAL prefix | `PERSONAL/PERSONAL Financial/`, `PERSONAL/PERSONAL Medical/`, `PERSONAL/PERSONAL Photos/` |
| `ENTERTAINMENT/` Q2 children carry the ENTERTAINMENT prefix | `ENTERTAINMENT/ENTERTAINMENT Music/`, `ENTERTAINMENT/ENTERTAINMENT Movies and TV Shows/` |
| `EDUCATION/` Q2 children carry the EDUCATION prefix | `EDUCATION/EDUCATION Research/`, `EDUCATION/EDUCATION Masters Applications/` |
| `RESOURCES/` Q2 children carry the RESOURCES prefix | `RESOURCES/RESOURCES Fonts/`, `RESOURCES/RESOURCES Templates/` |
| `WORK/` does NOT propagate to its company children — companies are already specific enough | `WORK/[COMPANY A]/`, `WORK/[COMPANY B]/` |
| Production-company names DO propagate to their project children | `WORK/[COMPANY]/[COMPANY] [Project]/`, `WORK/[COMPANY]/[COMPANY] CLIENT [Person]/` |
| Beyond the project level, generic subfolder names carry no prefix | `WORK/[COMPANY]/[COMPANY] [Project]/Scripts/`, `PERSONAL/PERSONAL Financial/[Person]/Bills/` |

The legacy flat naming (everything at the root level) is being migrated into this nested structure. During the migration, both styles may coexist.

## Folder tree output

When the user asks to see the folder tree (any wording — "show me the folder tree", "what's the structure look like", "list the folders", etc.) for the drive root or any organised folder, show the **intersection of rule-defined structure AND actual filesystem state**. The tree shows what's organised, not what's possible.

**Include:**
- Folders referenced in the root `.tidy-rules.json` (these are the canonical top-level project folders)
- Subfolders referenced in each folder's own `.tidy-rules.json` *that also physically exist on disk*

**Exclude:**
- Subfolders that exist on disk but aren't referenced in any `.tidy-rules.json` (e.g. `ENTERTAINMENT Music/`'s 1107 artist folders, season folders inside media folders, raw content subfolders)
- Subfolders that are referenced in rules but don't exist yet on disk (these are aspirational destinations — show them only if she asks for the rule-defined structure specifically)
- All files

**Why:** A flat list of rule-folders isn't a tree, and the full filesystem tree is dominated by media/content folders that drown out the project structure she actually cares about. The intersection gives her what's both *intended* (rules) and *realised* (on disk) — the diff between intended and realised is a separate question worth answering separately.

**Output format:** Standard tree characters (`├──`, `└──`, `│   `) with `/` suffix on folder names. Mark the rule-bearing folders with a small ` [rules]` tag so she can see which folders have their own classification rules vs which are just destination subfolders.

## Full batch cycle

```
0. mark-unapproved  — (first time only) x-prefix every existing unknown root folder
                       to quarantine legacy chaos before the batch loop starts
1. scan             — fill 250-file / 20GB batch by priority order:
                       P1  downloaded files in known folders
                       P2  cloud-only files in known folders (trigger downloads to local)
                       P3  loose downloaded files at the drive root (no parent folder)
                       P4  loose cloud-only files at the drive root (trigger downloads)
                       P5  downloaded files in x-folders
                       P6  cloud-only files in x-folders (trigger downloads)
                       Stop once cumulative size hits 20GB OR file count hits 250.
2. propose          — classify pending files; write proposals_classified.json
3. generate-viewer  — serve browser UI; user reviews and submits
4. process-return   — handle approved/rejected/inbox/flagged; reclassify rejected; peek flagged
5. execute          — move files, update registry (which auto-mirrors to registry.csv)
6. cleanup          — remove empty folders (including emptied x-folders); free disk via sync app
7. repeat from 1
8. (after all batches done) duplicates → variants → merge
```

`scan` now does its own downloading inline — there's no separate `download-batch` step in the cycle. The legacy `download-batch` subcommand still exists for manual top-ups but isn't part of the loop. Each scan fills the batch by walking priorities 1→6 until the budget is hit; priorities lower than where the cap landed are skipped this round.

The registry remembers everything across batches — original names, paths, hashes, content previews — so duplicates and variants are caught even if they appeared in different batches. Every mutation to `registry.db` also writes to `registry.csv` in the same folder so the user can audit the state in Numbers/Excel.

**Important:** `duplicates`, `variants`, and `merge` are **final-pass commands only**. During the batch loop, scan flags duplicates in the registry but nothing is moved or deleted.

**x-folders:** Folders prefixed with `x` are deferred staging areas containing badly-classified or unsorted files. Once a folder has the `x` prefix it is **never renamed again** — the prefix sticks until cleanup deletes the folder for being empty. (The `mark-unapproved` step ADDS the prefix; that's the one moment renaming is allowed.) Scan includes x-folder files as lower priority — known folders fill the batch first, x-folders fill any remaining capacity. Files are proposed out through the normal flow.

**Handling unknown folders (two flows):**
- **Pre-scan, bulk:** Run `mark-unapproved` once before the first scan. Every legacy root folder without rules gets `x`-prefixed. This is the bulk-deferral move.
- **Mid-batch, case-by-case:** If `scan` later reports `Folders with no rules` (a new folder appeared since `mark-unapproved` ran), ask the user about that specific folder and create a `.tidy-rules.json` for it before continuing to propose.

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

Read the output:
- `Pending classify > 0` → go to **propose**
- `Pending classify = 0` → scan already triggers cloud downloads inline; if the registry shows no further pending files anywhere, all batches are done — move to the final pass (`duplicates` → `variants` → `merge`).

---

### Lower-frequency subcommands → `references/subcommands.md`

Detailed documentation for `status`, `download-batch`, `mark-unapproved`, `flagged`, `duplicates`, `variants`, `merge`, and `csv-export` lives in **`references/subcommands.md`**. Consult that reference when invoking any of them. One-line summaries:

| Subcommand | What it does |
|---|---|
| `status` | Show active root + registry counts by status. Run at session start to confirm which drive is configured |
| `download-batch` | Legacy — `scan` does this inline. Manual top-up for pre-warming a chunk of the drive |
| `mark-unapproved` | Run once at the start: x-prefix every unknown root folder to quarantine legacy chaos |
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

1. **Known-folder, downloaded** — files already on local disk in folders that have a `.tidy-rules.json` or appear in the root `.tidy-rules.json`. No download needed.
2. **Known-folder, cloud-only** — placeholder (online-only) files in known folders. Scan triggers the sync app to download each, then **polls until it materialises** (up to a 30s timeout, configurable via the `DRIVE_ORG_DL_TIMEOUT` env var) before hashing — so a slow download completes in this pass instead of being deferred to a re-scan.
3. **Loose root, downloaded** — files sitting directly at the drive root (not inside any folder) that are already local.
4. **Loose root, cloud-only** — loose root files that need downloading first.
5. **x-folder, downloaded** — files in x-prefixed quarantined folders that are already local.
6. **x-folder, cloud-only** — files in x-folders that need downloading.

The rationale: organised folders earn their files first; the unknown chaos gets handled last. Once the 250/20GB cap is hit, the rest is deferred to the next batch.

Report all six counters: `New files`, `Hash-changed`, `Exact duplicates`, `Skipped`, `Pending classify`, `Total in registry`. Scan also prints a **per-phase timing line** (`download-wait` / `hashing` / `content-peek`) — surface it so the user can see where a slow scan's time actually went (e.g. mostly download-wait → network-bound; mostly hashing → large media). Also report which priority level the batch stopped at (e.g. "Stopped in priority 2 — known-folder downloads filled the batch"). For non-image files, scan extracts a `content_peek` (first ~300 chars of text) stored in the registry — used during `propose` to classify ambiguous files.

**If scan reports "Folders with no rules":** these are root-level folders that have no `.tidy-rules.json` and no matching entry in the root `.tidy-rules.json`. For each one, ask the user what belongs in it. Then create a `.tidy-rules.json` inside the folder (and optionally add a rule to the root `.tidy-rules.json`). Do this before running propose — files in unknown folders will be classified as `_Inbox/` without rules to guide them.

If the script exits with `Error: root path not found: <path>`, confirm the path exists and the drive is mounted.

---

### propose

Beyond emitting the raw file records JSON, `propose` writes a sidecar at `~/.claude/drive-organizer/project_metadata.json` listing every project on disk that carries a `filename_tag` in its `.tidy-rules.json`, with that project's `production_period`. Load this sidecar at the start of every classification pass — it's how the cascading Q routes loose bills/invoices to the right project by date.

```bash
python3 ~/.claude/drive-organizer/organizer.py propose --limit 250
```

If the script prints `"No pending files. Run 'scan' first or all files are already classified."`, this batch is fully classified — free disk and move to the next batch.

**Routing model — four cascading questions.** Each file answers questions in order, narrowing the destination one level at a time:

```
Q1: Which top-level grouping?   ENTERTAINMENT / PERSONAL / WORK / EDUCATION / RESOURCES
Q2: Which thing inside?         Music / Financial / [Company] / Research / Fonts / ...
Q3: Which functional area?      Person / Scripts / Financials / References / Admin / ...
Q4: Which leaf type?            Bills / [Character Name] / MOUs and Agreements / [Film Title] / ...
```

Most files terminate at Q3 or Q4; some go deeper (Q5 inside a per-person Financials tree). Folders only get created when files actually need them — empty scaffolding is not pre-built.

**Load templates and root rules first:**

```bash
python3 ~/.claude/drive-organizer/organizer.py templates                   # merged templates (shipped skeleton + your override)
cat <root>/.tidy-rules.json                                                # Q1 routing
```
(`<root>` is shown by `status` — typically `~/Library/CloudStorage/OneDrive-Personal`.)

**Pre-bucket the batch by likely Q1 grouping.** For each pending file in the JSON, do a fast match against the templates' `Q1_groupings` using `filename` + `content_peek` + parent of `current_path`. You're not classifying yet — just bucketing each file under the grouping it most likely belongs to. A 250-file batch typically resolves to 3–5 groupings + 15–25 Q2-level destinations.

**Load on-disk `.tidy-rules.json` lazily** — only the groupings and Q2-level folders this batch actually touches. Skip the rest. If a file's pre-grouping was wrong, fall back: load that one folder's rules on demand.

Also query the path vocabulary to catch approved names from previous batches:
```bash
sqlite3 <root>/.organizer/registry.db \
  "SELECT segment, position, use_count FROM path_vocab ORDER BY position, use_count DESC"
```
Prefer exact spellings already in `.tidy-rules.json` or path_vocab — proposing novel names when approved ones exist is how drift occurs.

**Entity matching in content_peek**: actively scan `content_peek` for any project name, person name, production title, or cast name that appears in the rules. A name match in content should override a weak filename signal. Example: content_peek contains a cast member's name → match the project folder whose Q3 rule description mentions that name (e.g. `WORK/[COMPANY]/[Project]`), even if the filename is generic.

**At each level, the routing decision:**

1. **On-disk rule matches** → route into the matched child. If the child has its own `.tidy-rules.json`, descend and ask the next question.
2. **No on-disk rule matches, but the templates file lists a valid child for this parent's type** → propose creating that subfolder AND propose adding the rule to the parent's `.tidy-rules.json`. This is the lazy-growth learning loop.
3. **Templates have no match either** → route to `_Inbox/` at the current level. Note the missing signal with `?`. Don't invent new categories.

**Templates fallback example:** A tax document arrives at `WORK/[COMPANY]/[Project]/Financials/`. The Financials/.tidy-rules.json on disk doesn't yet have a "Tax Documents" rule (no tax docs have lived here before). The templates file says `compound_children.Financials.children` includes "Tax Documents" — so propose creates `WORK/[COMPANY]/[Project]/Financials/Tax Documents/` AND queues a rule update to add Tax Documents to Financials/.tidy-rules.json on process-return.

**Bubble-sort by destination.** Before writing `proposals_classified.json`, group files by their final destination path. Files going to the same leaf appear together in the viewer — easier to spot misclassifications and approve in bulk. The backend's `propose` subcommand bubble-sorts automatically when writing the output.

Classify every file in the JSON output. The script emits a raw record per file (`id`, `current_path`, `filename`, `extension`, `file_size`, `file_date`, `is_image`, `content_peek`). Claude enriches each record with classification fields and writes the result to `~/.claude/drive-organizer/proposals_classified.json`. Also include any reclassified-rejected entries from the previous viewer round (see **process-return**).

**Two references are consulted in parallel for every file**, not one as fallback for the other:

1. **The cascading-Q model** (this file, "Routing model" section above) answers *where the file goes* — which grouping, which thing, which functional area, which leaf.
2. **`references/file-type-routing.md`** answers *how to handle this file type* — whether to use vision or read embedded metadata, whether the parent is an atomic-unit folder, whether a sidecar should travel with its parent, how to strip corrupted extensions, what to do with lock files / installers / legacy formats.

For every file: walk the cascade for destination, and read the file-type rules for handling. Neither replaces the other. Even a perfectly-classified destination needs the right filename, the right metadata extraction, the right sidecar parenting — which only the file-type rules supply.

The most common file-type touchpoints are summarised below — full detail in the reference.

**Images** (`.jpg`, `.jpeg`, `.png`, `.gif`, `.heic`, `.heif`, `.webp`, `.tiff`, `.tif`, `.bmp`, `.jfif`) and **Camera RAW** (`.nef` Nikon, `.raf` Fuji, `.arw` Sony, `.cr2`/`.cr3` Canon, `.dng`, `.orf` Olympus, `.rw2` Panasonic):

RAW files can't be vision-read. Skip the Read tool for RAW always — classify by parent folder + filename alone. For non-RAW images:

**Decide whether vision is needed before reading.** Most images can be classified from path + filename alone — vision (Read tool on the image) is expensive. Group images by `current_path` parent folder and inspect filenames first. **Skip vision when the path is a known project, the filename is descriptive, or the folder is a character-name reference container.** See `references/file-type-routing.md` for the full decision table and when-vision-is-needed criteria. When vision IS needed: Read the image, write a 1-sentence `vision_desc`. Either way: extract date from filename, generate the grouping-appropriate filename per the convention below, and route through the cascading-Q model.

**Preserve event folders for personal photos**: if a photo's current path already lives inside a named event subfolder (e.g. `[Person] Photos/Holi 2024/`), keep that event folder under `PERSONAL/PERSONAL Photos/<event>/`. Only loose photos get bucketed into `PERSONAL/PERSONAL Photos/YYYY/Month YY/`.

**Documents** (`.pdf`, `.docx`, `.doc`, `.xlsx`, `.fdx`, etc.): apply the cascading-Q model. The content_peek is the strongest project-ID signal — actively scan it for project/character/cast/company names from the rules. If on-disk rules don't match but the templates file lists a valid child for the parent type, propose the new subfolder and queue a rule addition (lazy-growth learning). Fall through to `references/tidy-builtin-categories.json` only when no Q*n* match is found anywhere.

**External folders** — folders with `"external": true` in their `.tidy-rules.json` are never scanned, never proposed into. Example: `logseq-journals/`. When the user says a folder is "shared from someone else", create `.tidy-rules.json` inside it with `{"external": true, "note": "...", "rules": []}`.

**Atomic-unit folders** (Python venvs, OSCAR CPAP backups, Zotero stores, Unity projects, node_modules, .app/.framework bundles, Time Machine snapshots): before classifying any file, check whether its parent or ancestor is an atomic unit. If so, **propose the whole folder as one entity** rather than per file. Detection markers and destinations: see `references/file-type-routing.md`.

**Audio** has embedded metadata: the backend uses `mutagen` to extract artist/album/title/year/track from ID3, MP4 atoms, Vorbis Comment, etc. The metadata surfaces in `content_peek` as `artist=… | album=… | title=… | date=… | length=…`. Use it alongside filename + parent folder when routing music to `ENTERTAINMENT/ENTERTAINMENT Music/(YYYY) AlbumName/`. (`pip3 install --user --break-system-packages mutagen` on PEP-668 systems if not present; without it audio still routes via filename/parent only.)

**Everything else** — video, design source, archives, eBooks, web links, markdown, code/config, installers, sidecars, lock files, OneDrive conflict-suffixed extensions, compound-corruption filenames, legacy formats, Procreate, scientific time-series data: see `references/file-type-routing.md`. The reference file lists extensions, signals, and destinations for each type.

---

**Filename conventions, project metadata, and the `proposals_classified.json` shape** live in `references/filename-conventions.md`. Consult it for: grouping-specific naming patterns (WORK projects vs admin, PERSONAL Issuer+Type, EDUCATION Entity, ENTERTAINMENT album-song-artist, RESOURCES), the rules for reading `content_peek` before generating a filename, worked examples, the `filename_tag` + `production_period` fields each project's `.tidy-rules.json` carries, learn-as-you-go period expansion, and the JSON entry shape Claude writes.

Tell the user the proposals are ready and how many were classified. **Do not launch the viewer yet.** Wait for them to explicitly say "launch the viewer" or equivalent — they may still be reviewing, giving feedback, or making corrections. Auto-launching while they are still talking interrupts their workflow.

---

### generate-viewer

```bash
python3 ~/.claude/drive-organizer/organizer.py generate-viewer \
  --proposals ~/.claude/drive-organizer/proposals_classified.json
```

Opens a browser viewer at localhost:5002. **Proposals are bubble-sorted by destination before pagination** — files going to the same leaf appear together, prefixed with a `→ <destination> (N files) [Approve group]` header row. `_Inbox` items sort to the bottom and render in purple. 25 files per page; pages = ceil(total ÷ 25). If a group spans pages, each page's header shows that page's slice (consistent count-vs-content within the page).

User reviews, edits destinations and filenames inline, then uses one of five action buttons per row:

| Button | Meaning | What happens |
|--------|---------|--------------|
| ✓ | Approve — move to proposed destination | `action: 'approved'` in JSON |
| ✗ | Wrong — reclassify using context | `action: 'rejected'` in JSON; original proposal preserved |
| ? | No idea — Claude peeks and reproposes | File marked `status='flagged'` in registry |
| 📥 | I need to open this myself (EPS, etc.) | `action: 'inbox'` in JSON; moves to `_Inbox/` |
| 🗑 | Move to deletion staging | `action: 'delete'` in JSON; moves to `Archive/_To Delete/` (never deleted from disk) |

On submit, the server writes `~/.claude/drive-organizer/proposals_approved.json` and shuts down.

**Check the server's final log line before continuing.** Look for either:
- `"N files marked flagged in registry."` — `?`-flagged files were persisted; proceed normally.
- `"Warning: could not mark flagged in DB: <error>"` — the flag write failed. Patch the registry yourself before running process-return:
  ```bash
  sqlite3 <root>/.organizer/registry.db "UPDATE files SET status='flagged' WHERE id IN (<comma-separated IDs>);"
  ```
  Get the IDs from `proposals_classified.json` (entries whose `id` doesn't appear in `proposals_approved.json` — those are the flagged ones; flagged entries are written to the registry, not the approved JSON).

If `Error: proposals file not found: <path>` or `Error: proposals JSON is empty.` — re-run the propose step to regenerate `proposals_classified.json` first.

---

### process-return

**Run this sequence every time the user says they have submitted the viewer** — whether they say "done", "submitted", "I've reviewed X files", or similar. Each step feeds the next, so running this as a single automated pipeline (without pausing to ask "what next?") preserves the context window state and avoids intermediate state drift. The only exception is step 10 — do NOT auto-launch the viewer; wait for the user to ask.

```
1. Read proposals_approved.json
2. Learn from APPROVED files first — this must happen before any reclassification. For every approved entry, compare its final `para_subfolder` against the original proposal in proposals_classified.json. Any difference is a learning signal — the user edited the destination inline before approving.

   For each new destination that didn't previously exist in `.tidy-rules.json`:

   **New top-level folder** (folder name not in root `.tidy-rules.json`):
   → Add a new rule entry to root `.tidy-rules.json`. Format: `{"id": "<UUID>", "description": "<signal that identifies this folder>", "folderName": "<folder name>", "createdAt": <Apple Core Data timestamp>}`.

   **New subfolder within an existing project** (e.g. `[Character] Costume Trials` appears in a `[COMPANY] [Project]/` folder):
   → Identify the proper noun(s) in the subfolder name — e.g. "[Character]" is a character name, "[Person]" is a person name, etc.
   → Abstract to a pattern: `ZARA Costume Trials` → `[Character] Costume Trials`
   → Ask the user: *"Does `[Character] Costume Trials` apply to other show folders too, or is this one-off for this project?"*

   Subfolder rules always go in the **per-folder** `.tidy-rules.json`, not in root descriptions. The root's `description` field is for matching files to a top-level folder — stuffing subfolder patterns into it pollutes the match signal. Where you write depends on scope:
     - **Project-specific** → append the rule to that one project's `.tidy-rules.json` (e.g. `WORK/[COMPANY]/[COMPANY] [Project]/.tidy-rules.json` only). Format: a new rule entry with `description: "[Character] Costume Trials photos for [Project] in [Character] Costume Trials"` and `folderName: "[Character] Costume Trials"`. **The `in <FolderName>` suffix on the description is required** — it's part of the match signal, not redundant decoration. No comma before `in`. The folderName field alone does not satisfy the convention; the description must terminate with `in <FolderName>` so the rule is self-describing when read in isolation.
     - **Generalizable across a project type** → add or update the entry in `references/subfolder-templates.json` (the source of truth for cross-project patterns). For example, if `[Character] Costume Trials` should apply to all production folders, add it under `compound_children.References` (or wherever it belongs in the cascade). The templates file is the canonical place for shared structure — that's what it exists for. Per-folder rules files only need entries for project-specific patterns that don't generalise.

   Either way, the pattern is named and recognized going forward — the same proper-noun slot will match future instances.

   **Routing corrections to existing folders** (e.g. the user moved `Resources/Templates` items to `[COMPANY] Admin/Templates`) → update the source folder's `.tidy-rules.json` to redirect that signal, and/or add a more specific rule to the destination folder. The next propose call will route correctly.

   Append only new facts. These files persist across sessions — if lessons aren't written back, the same misclassifications repeat.

3. Now separate the remaining entries by action field, using the now-updated rules:
   - action='approved'  → keep as-is for execute
   - action='inbox'     → keep as-is for execute (para_subfolder already set to '_Inbox' by viewer)
   - action='rejected'  → reclassify against the freshly-updated `.tidy-rules.json` (which now reflects everything learned in step 2). A rejection means the proposed destination was wrong — apply the updated rules to determine the correct folder. Do not send to `_Inbox/` unless no rule applies; that defeats the purpose of the rejection.
   - action='delete'    → execute will route to `Archive/_To Delete/` (not deleted from disk)

4. Write the corrected list (approved + inbox + reclassified + delete) back to proposals_approved.json,
   removing any remaining rejected entries.
5. Run execute on the corrected proposals_approved.json
6. Run cleanup
7. Run flagged — for each flagged file, peek content/vision and classify (same logic as propose).
   These become new proposals entries, not chat resolutions.
8. Re-run propose --limit N to pull new pending files
   (N = 250 minus count of reclassified-rejected entries minus count of newly-classified flagged entries)
9. Merge reclassified entries + flagged entries + new pending files into proposals_classified.json
10. Tell the user the new batch is ready (N files, X pages). Do NOT launch the viewer — wait for them to ask.
```

**Why learnings come before reclassification:** A rejection means the proposed destination was wrong, but *what* the right destination is often depends on a pattern the user just demonstrated by editing an approved entry. If you reclassify rejects before extracting learnings from approvals, you have to guess; if you do it after, the rules already encode their latest preferences and reclassification becomes a lookup. Same loop, fewer guesses.

**Note on routing**: For delete entries, execute reads `action == 'delete'` and hard-codes the destination to `Archive/_To Delete/` — `para_subfolder` is ignored. For all other entries (approved, inbox, reclassified), routing is via `para_subfolder` only. Inbox entries work because the viewer already sets `para_subfolder='_Inbox'`. The write-back step (step 4) ensures rejected entries have their `para_subfolder` corrected before execute runs (step 5).

**Refilling to 250**: After processing a submission, always pull new pending files to keep the viewer batch close to 250. This keeps review sessions efficient.

---

### execute

```bash
python3 ~/.claude/drive-organizer/organizer.py execute \
  --approved ~/.claude/drive-organizer/proposals_approved.json
```

The execute script reads `action` for delete entries only (routes them to `Archive/_To Delete/` regardless of `para_subfolder`). For all other entries, routing is determined entirely by `para_subfolder`. Before running execute, the proposals_approved.json must already have rejected entries replaced with their reclassified versions (see process-return step 3). Entries reaching execute should have correct values:
- Approved entries → `para_subfolder` set by user in viewer
- Inbox entries → `para_subfolder` = `'_Inbox'` (pre-set by viewer JS)
- Reclassified entries → `para_subfolder` updated by Claude in process-return step 2
- Delete entries → routed by `action == 'delete'` check in script; `para_subfolder` is ignored

Report: files moved, any errors. If errors > 0, check stderr — affected files remain at their original location and can be re-run after investigation. Then run cleanup regardless.

**Production-period auto-expansion.** After each successful file move, execute calls `_expand_production_period` on the destination project (walking ancestors to find a folder whose `.tidy-rules.json` has a `filename_tag`). It widens `production_period` to encompass the file's date, with a one-month buffer on each side. First file in a fresh project initialises the period; subsequent files only widen it if their date falls outside the existing range. Skipped for `action='delete'` and for files without a known date.

If execute exits with `"Error: approved file not found: <path>"` — the viewer didn't write the output file. Re-open the viewer with `generate-viewer` and re-submit.

**Empty approved list:** if execute prints `"Approved list is empty."`, every submitted row was flagged or left unreviewed. Run `flagged`. Skip cleanup.

**Long filenames causing MISSING errors**: Some files with very long filenames (>200 chars) or special characters (apostrophes, quotes) fail path matching. Find them with `find [root] -name "*partial_name*"` (the active root is shown by `status`) and move manually with `shutil.move` or `mv`, then update the registry directly.

---

### cleanup

```bash
python3 ~/.claude/drive-organizer/organizer.py cleanup
```

Removes empty directories left behind after execute. The root-level staging folders (`_Inbox/`, `Archive/`) and the Archive subdirs (`Archive/_To Delete/`, `Archive/_Duplicates/`, `Archive/_Merged-Originals/`) are never deleted. Report how many folders were removed. Then tell the user:
> "Done. To free up local disk space, evict the organised folders using your sync app:
> - **OneDrive**: right-click folder → *Free up space*
> - **iCloud Drive**: right-click folder → *Remove Download*
> - **Dropbox Smart Sync**: right-click folder → Smart Sync → *Online only*
> - **Google Drive (Stream mode)**: no action needed — files evict automatically once closed"

If the script exits with `Error: root path not found: <path>`, confirm the drive is mounted and the sync app is running.

---

## proposals_approved.json format

```json
[
  {
    "id": 1,
    "current_path": "/absolute/path/to/file.jpg",
    "filename": "original_filename.jpg",
    "is_image": true,
    "para_subfolder": "PERSONAL/PERSONAL Photos/2024/April 24",
    "new_filename": "20240417_outdoor_dinner_group.jpg",
    "vision_desc": "Group of people at an outdoor dinner celebration",
    "file_date": "2024-04-17",
    "reason": "personal photo",
    "action": "approved"
  }
]
```

`action` values: `"approved"` | `"rejected"` | `"inbox"` | `"delete"`. Flagged entries (`?`) are **not** in this file — they go directly to the registry as `status='flagged'`. Rejected entries must have their `para_subfolder` corrected and be written back before passing to execute. `new_filename` is always populated.

## Memory

`.tidy-rules.json` files are the classification memory. The root `.tidy-rules.json` defines every known project and folder; sub-folder `.tidy-rules.json` files define what goes inside. Confirmed project names, routing decisions, and naming corrections are written there as they are established — they persist across sessions automatically.

If `[root]/.organizer/config.json` defines a `memory_doc_path`, that document holds supplementary context that doesn't fit the rules format (e.g. background on a project, disambiguation notes). Read it only when classification is ambiguous and `.tidy-rules.json` doesn't resolve it.

## Tone

One line per file: path → destination → reason.
