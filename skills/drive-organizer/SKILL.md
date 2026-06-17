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
  parent-version: "1.2.0"
  intended-audience: claude-users
---

# Drive Organizer

Organises the user's files into a top-level grouping nested structure with prefix-propagation one level deep — see "Naming conventions" below. The **default** five groupings are `ENTERTAINMENT/`, `PERSONAL/`, `WORK/`, `EDUCATION/`, `RESOURCES/`, but the active set is **data-driven, not fixed at five**: the backend reads it via `_active_groupings()` from the merged templates' `Q1_groupings` or an optional `<root>/.organizer/config.json` `"areas": [...]` override (a user may have more, fewer, or differently-named areas). Everything that depends on the grouping set — `_normalize_grouping`, reconcile's known-roots, the grouping invariant — reads that same dynamic set. The Python backend (`organizer.py`) handles all file I/O and database work; the registry lives at `<root>/.organizer/` as `registry.db` (SQLite, authoritative) plus `registry.csv` (auto-mirrored by the backend after every mutation — the user can open it in Numbers/Excel to audit state). This skill handles vision analysis, classification decisions, and the interactive approval loop.

**Placeholders in commands**: `<root>` and `[root]` in any command below stand for the **active configured root** — the absolute path `status` prints as the active root (set once via `--root`, typically `~/Library/CloudStorage/OneDrive-Personal`). Run `status` once at session start, capture that path, and substitute it everywhere `<root>`/`[root]` appears before running a command. Likewise `$SKILL_DIR` = the skill's install dir (see First-time setup).

**User profile (optional)**: if `[root]/.organizer/config.json` defines a `profile` (a note on the user's roles/context), let it guide edge-case classification. With no profile set, classify from file content and folder context alone.

**Terminology**: unfamiliar terms below — x-folder, cascading-Q, atomic-unit folder, `content_peek`, `.tidy-rules.json`, per-user override, active-groupings — are defined in `references/glossary.md`. Read it first if any term is unclear.

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
Only `organizer.py` is copied to the runtime location; the `references/` (templates, glossary, routing tables) stay in `$SKILL_DIR` and are read from there — see "templates" below. The backend looks for `references/` at the standard skills path by default; **if the skill is installed elsewhere, also `export DRIVE_ORG_SKILL_DIR=<that dir>`** so `organizer.py` finds the references (otherwise templates load empty and the taxonomy silently degrades to the bare defaults).

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

The grouping set is data-driven (not fixed at five). The default: **`WORK` is the one grouping whose Q2 children do NOT inherit the prefix** (companies are already specific); **every other grouping — including any user-defined area — DOES propagate its prefix to its Q2 children** (e.g. a custom `HEALTH` area → `HEALTH/HEALTH Records/`). When in doubt for a new area, propagate.

The legacy flat naming (everything at the root level) is being migrated into this nested structure. During the migration, both styles may coexist.

## Folder tree output

When the user asks to see the folder tree ("show me the folder tree", "what's the structure look like", "list the folders"), show the **intersection of rule-defined structure AND actual filesystem state** (what's organised, not what's possible). Full procedure — how to gather the two inputs via `rules --json` + a filesystem walk, the include/exclude rules, the WHY, and the output format — is in `references/subcommands.md` "folder-tree".

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
2. propose          — backend prints raw pending-file records to stdout; Claude classifies + writes proposals_classified.json
3. generate-viewer  — serve browser UI; user reviews and submits
4. process-return   — handle approved/rejected/inbox/flagged; reclassify rejected; peek flagged
5. execute          — move files, update registry (which auto-mirrors to registry.csv)
6. cleanup          — remove empty folders (including emptied x-folders); free disk via sync app
7. repeat from 1
8. (after all batches done) duplicates → variants → merge
```

`scan` now does its own downloading inline — there's no separate `download-batch` step in the cycle. The legacy `download-batch` subcommand still exists for manual top-ups but isn't part of the loop. Each scan fills the batch by walking priorities 1→6 until the budget is hit; priorities lower than where the cap landed are skipped this round.

The registry remembers everything across batches — original names, paths, hashes, content previews — so duplicates and variants are caught even if they appeared in different batches. (Every mutation also mirrors to `registry.csv` — see the intro.)

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

Read the output (check in this order):
- **If scan reported `Folders with no rules`** → resolve those first (ask the user, create each folder's `.tidy-rules.json`) **before** propose — see the scan section. Don't skip to propose with unruled folders present.
- `Pending classify > 0` → go to **propose**.
- `Pending classify = 0` **AND `Skipped` = 0 AND the run did not stop at a cap** ("→ All priorities drained within cap") → all batches are done; move to the final pass (`duplicates` → `variants` → `merge`).
- `Pending classify = 0` **but `Skipped` > 0 or the run hit a cap** → work remains (downloads that failed, or files past the cap). Run `scan` again to pick them up. **Permanent-skip guard:** if two consecutive scans report the *same* `Skipped` count and add no new pending files, those files are persistently unavailable (online-only with no connectivity, zero-byte, or unreadable) — they will never drain. Stop re-scanning, tell the user which files keep skipping (the `skip <path>: …` stderr lines name them), and treat the drive as done *excluding* them.

---

### Lower-frequency subcommands → `references/subcommands.md`

Detailed documentation for `status`, `download-batch`, `mark-unapproved`, `flagged`, `reconcile`, `duplicates`, `variants`, `merge`, and `csv-export` lives in **`references/subcommands.md`**. Consult that reference when invoking any of them. One-line summaries:

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

Report the seven counters: `New files`, `Hash-changed`, `Exact duplicates`, `Unchanged (skip-rehash)`, `Skipped`, `Pending classify`, `Total in registry`. Scan prints more besides — a `Batch size: N GB / N GB cap` line, `Downloads triggered`, a **per-phase timing line** (`download-wait` / `hashing` / `content-peek`), an `Eligible per priority` P1–P6 block, and a final stop-state line that is **literally** either `→ Cap reached in priority N (<label>)` or `→ All priorities drained within cap`. Surface the timing (e.g. mostly download-wait → network-bound; mostly hashing → large media) and the stop-state line (match those exact strings — the No-subcommand branch keys on them). For non-image files, scan extracts a `content_peek` (first ~300 chars of text) stored in the registry — used during `propose` to classify ambiguous files.

**If scan reports "Folders with no rules":** these are root-level folders that have no `.tidy-rules.json` and no matching entry in the root `.tidy-rules.json`. For each one, ask the user what belongs in it. Then create a `.tidy-rules.json` inside the folder (and optionally add a rule to the root `.tidy-rules.json`). Do this before running propose — files in unknown folders will be classified as `_Inbox/` without rules to guide them.

If the script exits with `Error: root path not found: <path>`, confirm the path exists and the drive is mounted.

---

### propose

Beyond emitting the raw file records JSON, `propose` writes a sidecar at `~/.claude/drive-organizer/project_metadata.json` listing every project on disk that carries a `filename_tag` in its `.tidy-rules.json`, with that project's `production_period`. Load this sidecar at the start of every classification pass — it's how the cascading Q routes loose bills/invoices to the right project by date.

```bash
python3 ~/.claude/drive-organizer/organizer.py propose --limit 250
```

**Cost & speed toggles** (set durably in `<root>/.organizer/config.json`, or per-run on the command line):

| Toggle | config.json key | Per-run flag | Effect |
|---|---|---|---|
| Auto-classify fast-path | `auto_classify` (default `true`) | `--no-auto-classify` / `--auto-classify` | W1 deterministic routing of unambiguous files before classification |
| Vision | `vision` (default `true`) | `--no-vision` | Off ⇒ images are routed by name/path/rule only, never opened (vision is the slow part) |
| Skip file types | `skip_types` (e.g. `[".mov", ".raw"]`) | `--skip-types .mov,.raw` | Those extensions are never opened — routed by name/path/rule only |
| Skip large files | `skip_over_mb` (e.g. `200`) | `--skip-over-mb 200` | Files over N MB are never opened — routed by name/path/rule only |
| Confidence auto-approval | `auto_approve` (default `false`) | `--auto-approve` | W5: high-confidence auto-routed files marked `auto_approved` — orchestrator may skip the viewer (still audited in `<root>/.organizer/auto-routed.csv`) |

A toggled-off / blocked file is never dropped: the W1 matcher gives it a deterministic destination when one exists, otherwise it reaches the classifier as `route_by_name_only` (or falls to `_Inbox/`).

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

**Read the propose output — three lanes.** `propose` now pre-sorts the batch so you only classify what actually needs it:

- **`auto_routed: true`** — the deterministic fast-path (W1) already chose the destination and wrote it to **`para_subfolder`** (the canonical routing field the viewer, bubble-sort, and execute all read; `proposed_subfolder` carries the same value as a readable alias). The entry also carries `auto_reason` — the match reason (e.g. "already in ruled folder") — which is informational + mirrored to `auto-routed.csv`; you don't need to act on it. Accept the entry as-is; do **not** re-classify.
- **`needs_classification: true`** — the real work. Each carries a `classify_batch` index (groups of 25).
- **`route_by_name_only: true`** (a subset of the above) — a cost toggle blocked opening this file. `open_blocked_reason` is a **list** whose values are exactly `vision-off`, `skip-type`, and `>{N}MB` (these three are the only reasons the backend emits — a closed set; e.g. `["vision-off","skip-type"]`, or `[">200MB"]`), not a single value. Classify it from `filename` + `current_path` + rules **only — never open it**; `content_peek` is deliberately null. If nothing matches, route to `_Inbox/`. (The backend never sends a blocked file to `_Inbox/` itself — it auto-routes when the W1 matcher finds a rule, else hands it to you as `route_by_name_only`; the `_Inbox/` fallback is the classifier's decision, i.e. yours.)

**Fan out classification — one sub-agent per `classify_batch` (mine-sources pattern).** Rather than classify every file inline, dispatch one Agent per batch of 25 so each works a small set with a fresh context and raw file content stays out of the orchestrator. **Use the canonical template `references/classify-prompt.md`** — stage one filled copy per `classify_batch` so every batch is briefed identically, then dispatch:

- Fill the template's slots: `[BATCH_JSON]` = that batch's records (`{id, filename, current_path, is_image, route_by_name_only, content_peek?}` — **paths, never file contents**); `[GROUPINGS]` = the active grouping names — read them from `organizer.py rules --json` → the top-level `areas` array (that is the *resolved* active set from `_active_groupings()`, which honours a `config.json "areas"` override; do NOT read `templates` `Q1_groupings` here — it misses the override and its entries may be strings or dicts); `[ROOT]`, `[TEMPLATES_CMD]`, `[PROJECT_METADATA_PATH]`, `[ENTITIES_PATH]`, `[FILE_TYPE_ROUTING_PATH]`, `[TIDY_BUILTIN_PATH]`, `[FILENAME_CONVENTIONS_PATH]`, `[GLOSSARY_PATH]` = the absolute paths/commands. The template keeps the prompt light by **pointing** the agent at those (it reads them itself) and inlining only the batch + rules + output contract.
- The agent opens each file itself (Read / vision) unless `route_by_name_only`, applies the cascading-Q logic, respects entity aliases/negatives, and returns one verdict per file: `{id, para_subfolder, new_filename, reason, signal, confidence, vision_desc?}` — **verdicts only, not file content**. (`reason` is the human-readable rationale the viewer shows; `para_category` is NOT in the verdict — execute derives it from `para_subfolder`. The `signal` + `confidence` fields feed W5: shared signals become rules. Note `confidence` is **advisory** — the backend's `auto_approved` flag is set only on W1 fast-path entries (it never reads a classifier verdict's `confidence`); so a `confidence: high` verdict does not auto-approve by itself. If `auto_approve` is on and you choose to let high-confidence verdicts skip the viewer, that is *your* orchestration decision — mark them yourself and keep the CSV audit.)
- Merge every batch's verdicts together with the unchanged `auto_routed` entries into `~/.claude/drive-organizer/proposals_classified.json`.

**Inbox arbiter sweep — periodic `_Inbox/` reclamation (one arbiter per 25, ~4 at the trigger).** `_Inbox/` is where files with no fit land. Because the rule set grows as you organise, files inboxed earlier often become placeable later. **When the registry's `_Inbox/` population reaches ~100 files** (check `organizer.py inbox-list` → `count`), run a reclamation sweep over **all** of them (not just this round's):

- Get the list: `organizer.py inbox-list` → `{count, files:[{id, filename, current_path}]}`. (`count` is the number of files already **executed** into `_Inbox/` — registry rows with `status='organized'` and a `_Inbox` path; files merely classified-to-`_Inbox` this round but not yet executed don't count until execute moves them.) Fill the arbiter batch directly from those records — `inbox-list` already emits exactly the fields `arbiter-prompt.md` expects. Split `files` into batches of ≤25 (so ~4 arbiters at 100) and dispatch one arbiter per batch **in parallel**, each filled from `references/arbiter-prompt.md` (same pointer-not-inline discipline).
- Each arbiter re-judges its files against the *current* taxonomy and returns `{id, verdict, para_subfolder, new_filename?, reason}` where `verdict` ∈ `confirm_inbox` / `reroute_high` / `reroute_low`.
- Apply: `confirm_inbox` → leave in `_Inbox/`; `reroute_high` → build an approved entry (`para_subfolder` = the new destination) and `execute` it directly; `reroute_low` → add it to the next `proposals_classified.json` so it surfaces in the **viewer** for the user to confirm — never moved silently. Re-run `inbox-list` after to confirm the count dropped.

WHY fan out: accuracy (a fresh agent on 25 files beats one context dragging 250), less orchestrator decision-fatigue, and content hygiene (each batch's context is discarded). For a tiny residual (a single batch ≤25) you may classify inline — the fan-out earns its keep at scale.

**The per-file classification logic each agent applies** is the remainder of this section:

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

**Bubble-sort by destination.** `propose` prints the per-file records to **stdout** in `id` order and does not write the *proposals* file — **you** capture those records, enrich them, and write `proposals_classified.json` yourself. (It does write two *side* files: the `project_metadata.json` sidecar always, and appends `auto-routed.csv` when anything auto-routed — see above; just not the proposals file.) The stdout records are **not bare DB columns**: each carries the base fields (`id`, `current_path`, `filename`, `extension`, `file_size`, `file_date`, `is_image`, `content_peek`) **plus** its lane fields — `auto_routed` on every record, and per lane `para_subfolder`/`proposed_subfolder`/`auto_reason`/`auto_approved?` (auto-routed) or `needs_classification`/`classify_batch` (+`route_by_name_only`/`open_blocked_reason` when blocked). Grouping the entries you write by final destination makes the viewer easier to eyeball, but you don't have to: `generate-viewer` bubble-sorts when it serves them (`_bubble_sort_proposals`).

Classify every file in the JSON output — each record carries the base + lane fields described above. Claude enriches each record with classification fields and writes the result to `~/.claude/drive-organizer/proposals_classified.json`. Also include any reclassified-rejected entries from the previous viewer round (see **process-return**).

**Every file needs both axes, in parallel — neither replaces the other:** the cascading-Q model (above) answers *where it goes* (grouping → thing → area → leaf); `references/file-type-routing.md` answers *how to handle this type* (vision vs metadata, atomic-unit parent, sidecar parenting, corrupted/lock/legacy handling). A perfectly-placed file still needs the right filename + metadata extraction + sidecar parenting, which only the file-type rules supply.

**`references/file-type-routing.md` is the authoritative per-type spec** (extensions, signals, destinations, sidecar parenting, lock files, legacy/corrupted formats, the vision decision table). Read it for any file whose handling isn't obvious. The load-bearing rules you must not miss inline:

- **Camera RAW** (`.nef`/`.raf`/`.arw`/`.cr2`/`.cr3`/`.dng`/`.orf`/`.rw2`) **can't be vision-read — never Read them**; classify by parent folder + filename alone.
- **Images: vision is expensive — decide before Reading.** Skip vision when the path is a known project, the filename is descriptive, or the folder is a character-name container; use it only when needed, then write a 1-sentence `vision_desc`. Full decision table in the reference.
- **Preserve event folders for photos**: a photo already inside a named event subfolder (e.g. `[Person] Photos/Holi 2024/`) keeps that event folder under `PERSONAL/PERSONAL Photos/<event>/`; only loose photos bucket into `PERSONAL/PERSONAL Photos/YYYY/Month YY/`.
- **Documents**: `content_peek` is the strongest project-ID signal — scan it for project/character/cast/company names. Fall through to `references/tidy-builtin-categories.json` only when no Q*n* match exists anywhere.
- **Atomic-unit folders** (venvs, `node_modules`, Zotero/OSCAR stores, Unity projects, `.app`/`.framework` bundles, Time Machine): if a file's parent/ancestor is an atomic unit, **propose the whole folder as one entity**, never per-file.
- **External folders** (`"external": true` in their `.tidy-rules.json`, e.g. `logseq-journals/`): never scanned or proposed into.
- **Audio**: `mutagen` surfaces `artist=… | album=… | title=… | date=…` in `content_peek` — use it to route music to `ENTERTAINMENT/ENTERTAINMENT Music/(YYYY) AlbumName/`.

---

**Filename conventions, project metadata, and the `proposals_classified.json` shape** live in `references/filename-conventions.md`. Consult it for: grouping-specific naming patterns (WORK projects vs admin, PERSONAL Issuer+Type, EDUCATION Entity, ENTERTAINMENT album-song-artist, RESOURCES), the rules for reading `content_peek` before generating a filename, worked examples, the `filename_tag` + `production_period` fields each project's `.tidy-rules.json` carries, learn-as-you-go period expansion, and the JSON entry shape Claude writes.

Tell the user the proposals are ready and how many were classified. **Do not launch the viewer yet.** Wait for them to explicitly say "launch the viewer" or equivalent — they may still be reviewing, giving feedback, or making corrections. Auto-launching while they are still talking interrupts their workflow.

---

### generate-viewer

```bash
python3 ~/.claude/drive-organizer/organizer.py generate-viewer \
  --proposals ~/.claude/drive-organizer/proposals_classified.json
```

**Before launching, snapshot the served baseline.** Keep this round's `proposals_classified.json` in memory as a dict keyed by `id` (the pre-edit destinations). process-return step 2 compares the user's approved destinations against this snapshot to detect inline edits, and step 9 will overwrite the file — so capture it here, at launch, or the baseline is lost.

Opens a browser viewer at localhost:5002. **Proposals are bubble-sorted by destination before pagination** — files going to the same leaf appear together, prefixed with a `→ <destination> (N files) [Approve group]` header row. `_Inbox` items sort to the bottom and render in purple. 25 files per page; pages = ceil(total ÷ 25). If a group spans pages, each page's header shows that page's slice (consistent count-vs-content within the page).

User reviews, edits destinations and filenames inline, then uses one of five action buttons per row (note: the `?` flag is not an `action` value — it persists to the registry, so only the other four reach `proposals_approved.json`):

| Button | Meaning | What happens |
|--------|---------|--------------|
| ✓ | Approve — move to proposed destination | `action: 'approved'` in JSON |
| ✗ | Wrong — reclassify using context | `action: 'rejected'` in JSON; original proposal preserved |
| ? | No idea — Claude peeks and reproposes | File marked `status='flagged'` in registry |
| 📥 | I need to open this myself (EPS, etc.) | `action: 'inbox'` in JSON; moves to `_Inbox/` |
| 🗑 | Move to deletion staging | `action: 'delete'` in JSON; moves to `Archive/_To Delete/` (never deleted from disk) |

On submit, the server writes `~/.claude/drive-organizer/proposals_approved.json` and shuts down.

**Check the server's final log line before continuing.** Exactly one of these three cases holds:
- **Neither flagged line appears** (only `Approved proposals written to: …` / `Server shutting down.`) — no files were `?`-flagged this round; proceed normally.
- `"N files marked flagged in registry."` — `?`-flagged files were persisted; proceed normally.
- `"Warning: could not mark flagged in DB: <error>"` — the flag write failed. Patch the registry yourself before running process-return:
  ```bash
  sqlite3 <root>/.organizer/registry.db "UPDATE files SET status='flagged' WHERE id IN (<comma-separated IDs>);"
  ```
  Get the exact IDs from `~/.claude/drive-organizer/proposals_flagged.json` — the viewer always writes the precise flagged-ID set there on submit. It's a bare JSON array of integers (e.g. `[12, 47, 88]`); join them comma-separated (`12,47,88`) to fill the `IN (...)` clause. **Do not** infer them by "IDs in `proposals_classified.json` not in `proposals_approved.json`": that set also contains rows the user left **unreviewed** (`unset`), and marking those `status='flagged'` would wrongly drop unreviewed files from future propose batches.

If `Error: proposals file not found: <path>` or `Error: proposals JSON is empty.` — re-run the propose step to regenerate `proposals_classified.json` first.

---

### process-return

**Run this sequence every time the user says they have submitted the viewer** — whether they say "done", "submitted", "I've reviewed X files", or similar. Each step feeds the next, so run it as one automated pipeline (don't pause to ask "what next?") — this preserves context-window state and avoids intermediate state drift. (Step 10 is the exception — it does not auto-launch the viewer; that rule is stated there.)

```
1. Read proposals_approved.json
2. Learn from APPROVED files first — this must happen before any reclassification. For every approved entry, compare its final `para_subfolder` against the **baseline snapshot you captured at generate-viewer launch**, matched by `id` (never by position — bubble-sort reorders entries; do this before step 9 refills `proposals_classified.json`). Any difference is a learning signal — the user edited the destination inline before approving.

   For each new destination that didn't previously exist in `.tidy-rules.json`:

   **New top-level folder** (folder name not in root `.tidy-rules.json`):
   → Add a new rule entry to root `.tidy-rules.json`. Format: `{"folderName": "<folder name>", "description": "<signal terms that identify this folder> in <folder name>"}`. These are the only two fields the backend reads (`_aggregate_rules` / `_build_rules_index` key on `folderName` + `description`); the `description` must end with the `in <folderName>` suffix (see "Description format" above). (Legacy rules may also carry `id`/`createdAt` — harmless extra fields; don't add them to new rules.)

   **New subfolder within an existing project** (e.g. `[Character] Costume Trials` appears in a `[COMPANY] [Project]/` folder):
   → Identify the proper noun(s) in the subfolder name — e.g. "[Character]" is a character name, "[Person]" is a person name, etc.
   → Abstract to a pattern: `ZARA Costume Trials` → `[Character] Costume Trials`
   → Ask the user: *"Does `[Character] Costume Trials` apply to other show folders too, or is this one-off for this project?"*

   Subfolder rules go in the **per-folder** `.tidy-rules.json`, never in root descriptions (that pollutes the top-level match signal). **Project-specific** → that one project's file, writing the CONCRETE folder name (expand any `[Placeholder]` to the real name — the matcher tokenises `folderName` literally). **Generalizable across a project type** → `references/subfolder-templates.json`. Full rules + worked example: `references/filename-conventions.md` "Writing a new subfolder rule".

   Either way, the pattern is named and recognized going forward — the same proper-noun slot will match future instances.

   **Routing corrections to existing folders** (e.g. the user moved `Resources/Templates` items to `[COMPANY] Admin/Templates`) → update the source folder's `.tidy-rules.json` to redirect that signal, and/or add a more specific rule to the destination folder. The next propose call will route correctly.

   Append only new facts. These files persist across sessions — if lessons aren't written back, the same misclassifications repeat.

3. Now separate the remaining entries by action field, using the now-updated rules. `proposals_approved.json` contains **only** the four action values below — flagged and unreviewed rows are never written to it (flagged go to the registry + `proposals_flagged.json`; unreviewed go nowhere), so these four cases are exhaustive:
   - action='approved'  → keep as-is for execute
   - action='inbox'     → keep as-is for execute (para_subfolder already set to '_Inbox' by viewer)
   - action='rejected'  → reclassify against the freshly-updated `.tidy-rules.json` (which now reflects everything learned in step 2). A rejection means the proposed destination was wrong — apply the updated rules to determine the correct folder. Do not send to `_Inbox/` unless no rule applies; that defeats the purpose of the rejection. **When you rewrite a rejected entry, change only `para_subfolder` (and `new_filename` if needed) — carry `file_date` through unchanged.** execute uses `file_date` to widen the destination project's `production_period`; dropping it silently skips that update.
   - action='delete'    → execute will route to `Archive/_To Delete/` (not deleted from disk)

4. Write the corrected list (approved + inbox + reclassified + delete) back to proposals_approved.json,
   removing any remaining rejected entries.
5. Run execute on the corrected proposals_approved.json
6. Run cleanup — **unless** execute printed `"Approved list is empty."` (every row was flagged/unreviewed, nothing moved); then skip cleanup and go to step 7
7. Run flagged — if it prints `"No flagged files."`, skip this step. Otherwise, for each flagged file, peek content/vision and classify (same logic as propose; for the peek procedure see references/subcommands.md `flagged` step 1). These become new proposals entries, not chat resolutions.
8. Re-run propose --limit 250 to pull new pending files
   (`--limit` is a cap, not a target — over-asking is harmless; the backend returns at most that many *pending* files. The reclassified-rejected and newly-classified-flagged entries from steps 3/7 are merged in at step 9, so you don't subtract them here.)
9. Merge reclassified entries + flagged entries + new pending files into proposals_classified.json
10. Tell the user the new batch is ready (N files, X pages). Do NOT launch the viewer — wait for them to ask.
```

**Why learnings come before reclassification:** A rejection means the proposed destination was wrong, but *what* the right destination is often depends on a pattern the user just demonstrated by editing an approved entry. If you reclassify rejects before extracting learnings from approvals, you have to guess; if you do it after, the rules already encode their latest preferences and reclassification becomes a lookup. Same loop, fewer guesses.

**Note on routing**: For delete entries, execute reads `action == 'delete'` and hard-codes the **move destination** to `Archive/_To Delete/` — `para_subfolder` is ignored *for the move*. (It is still written to the registry row: the viewer sets delete rows to `para_subfolder='Archive/_To Delete'` and execute records `para_category`/`para_subfolder` for every row, delete included.) For all other entries (approved, inbox, reclassified), routing is via `para_subfolder` only. Inbox entries work because the viewer already sets `para_subfolder='_Inbox'`. The write-back step (step 4) ensures rejected entries have their `para_subfolder` corrected before execute runs (step 5).

**Refilling to 250**: After processing a submission, always pull new pending files to keep the viewer batch close to 250. This keeps review sessions efficient.

**Learning-loop accelerators (W5)** — use these when writing rules in step 2 and handling rejections:

- **Auto-infer the signal, not just the folder.** When several approved files routed to the same (possibly new) folder, derive the rule's signal from the tokens common to those filenames rather than the folder name alone — the backend exposes this as `_infer_signal_from_filenames(names)`. A signal-bearing rule then auto-routes the *next* similar file via W1.
- **Learn from rejections (negative signal).** A rejection says "files like this do NOT belong here." Record the distinguishing token(s) in that entity's `entities.json` `negative: [...]` list. The W1 matcher then suppresses that destination for any filename carrying a negative token (so a rejected pattern doesn't keep re-proposing). This is the rejection-side complement to approval-driven learning.
- **Aliases cut repeat corrections.** When the user keeps correcting the same misspelling/short form to one entity, add it to that entity's `aliases` (viewer or `entities.json`); the matcher routes alias spellings (down to 3 chars) straight to the entity.
- **Proactive "make a rule?"** After a batch, if N files were approved into the same new folder, offer to write the rule once (with the inferred signal) instead of re-classifying each next time.
- **Confidence auto-approval (opt-in).** With `auto_approve` on (config or `--auto-approve`), high-confidence auto-routed files are flagged `auto_approved` — you may execute them without a viewer pass (still audited in `auto-routed.csv`). Default OFF: human review stays the norm unless the user opts in.

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

Report: files moved, any errors. If errors > 0, check stderr. Two error shapes:
- `ERROR moving <src>: <e>` — the move itself failed (e.g. permissions, long path); the file is still at `<src>` and can be re-run after investigation.
- `MISSING: <src>` — the recorded `current_path` no longer exists on disk (the file was moved, renamed, or deleted **outside** the tool since it was registered). It is NOT at its original location. Don't blindly re-run; run `reconcile` to detect/repair the registry-vs-disk drift (the `bad_registry_rows` / relocated detection), or locate the file (see "Long filenames" below) and fix the row.

Then run cleanup regardless (unless execute printed `"Approved list is empty."` — see below).

**Production-period auto-expansion.** After each successful file move, execute calls `_expand_production_period` on the destination project (walking ancestors to find a folder whose `.tidy-rules.json` has a `filename_tag`). It widens `production_period` to encompass the file's date, with a one-month buffer on each side. First file in a fresh project initialises the period; subsequent files only widen it if their date falls outside the existing range. Skipped for `action='delete'` and for files without a known date.

If execute exits with `"Error: approved file not found: <path>"` — the viewer didn't write the output file. Re-open the viewer with `generate-viewer` and re-submit.

**Empty approved list:** if execute prints `"Approved list is empty."`, every submitted row was flagged or left unreviewed. Run `flagged`. Skip cleanup.

**Long filenames causing MISSING errors**: Some files with very long filenames (>200 chars) or special characters (apostrophes, quotes) fail path matching. Find them with `find [root] -name "*partial_name*"` (the active root is shown by `status`) and move manually with `shutil.move` or `mv`, then update the registry directly.

---

### cleanup

```bash
python3 ~/.claude/drive-organizer/organizer.py cleanup
```

Removes empty directories left behind after execute. The root-level staging folders (`_Inbox/`, `Archive/`) and the Archive subdirs (`Archive/_To Delete/`, `Archive/_Duplicates/`, `Archive/_Merged-Originals/`) are never deleted. Report how many folders were removed, then tell the user how to free local disk space by evicting the grouping folders this batch wrote to (e.g. `WORK/`, `PERSONAL/` — not the staging folders) via their sync app — the per-app eviction recipes (OneDrive / iCloud / Dropbox / Google Drive) are in `references/subcommands.md` "cleanup".

If the script exits with `Error: root path not found: <path>`, confirm the drive is mounted and the sync app is running.

---

## Rules tools — view, edit, and bootstrap

Three commands operate on the *rules* (not files), all reading the aggregated view (`rules`) where each entity = a folder name grouped across the whole tree:

- **`rules`** — clustered one-line-per-entity summary (Areas / Projects / People / Subfolders / Policies / Atomic / Unknown). `rules --json` feeds the viewer.
- **`rules-viewer`** (`--port 5003`) — browser editor: clustered cards (250/session, 25/page), per-entity type/aliases/relation/behaviour/notes + signal, usage stats, dead-rule flag, why-routed, conflict warnings, test-a-file, coverage gaps, full CRUD + rename/merge/bulk, **rethink** (flag for re-inference, ≠ delete), area add/rename/remove, level-promotion dry-run, **Apply (keep open)** / **Preview** (per-change undo) / **Save & close**. Adapts to light/dark.
- **`bootstrap`** — reverse-engineer rules from an existing tree, for a new or partly-organised drive.

### bootstrap (setup walkthrough)

Order matters — **atomic units are approved + locked FIRST**, so the inference never wastes effort descending into them:

1. **`bootstrap --detect-atomic`** — lists atomic-unit folders (venvs, `node_modules`, `.git` repos, Zotero/photo libraries, `.app` bundles, Unity projects). Show them to the user.
2. **`bootstrap --lock <names>`** — on the user's approval, writes those units to `entities.json` as `entity_type: atomic, locked: true`. Scan/propose/bootstrap never descend into a locked unit again (it's one entity).
3. **`bootstrap --emit [--mode cold-start|audit] [--sample K] [--limit 250]`** — samples every unruled folder with files (K files each: name + content_peek + ext) and writes `<root>/.organizer/bootstrap-input.json` (candidates batched 25/group, capped at 250). *cold-start* = infer the whole taxonomy; *audit* = also flag ruled folders whose sample routes elsewhere (drift, feeds reconcile).
4. **Claude infers each candidate** — fan out one sub-agent per batch of 25 (briefed with the folder + its sample only — never inline more than the sample), inferring a rule + a metadata guess per folder. Write the result to `<root>/.organizer/bootstrap-proposed.json` as a JSON object with `rules[]` + `entities{}` keys — exact shape (and the non-object-rejected rule) in `references/subcommands.md` "bootstrap".
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
