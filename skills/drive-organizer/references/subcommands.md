# Subcommand reference — lower-frequency commands

Detailed documentation for utility / final-pass subcommands that aren't part of the main batch loop. The high-frequency loop commands (`scan`, `propose`, `generate-viewer`, `process-return`, `execute`, `cleanup`) stay in `SKILL.md` because they fire every batch.

Consult this file when invoking any of the commands below, hitting their errors, or planning the final pass at the end of organising.

## Table of contents

- [status](#status)
- [download-batch](#download-batch) — legacy; `scan` does this inline now
- [flagged](#flagged) — peek-and-reclassify items the user `?`-marked
- [reconcile](#reconcile) — maintenance: detect/repair structure drift
- [duplicates](#duplicates) — final pass: SHA256 groups
- [variants](#variants) — final pass: fuzzy-name groups
- [merge](#merge) — final pass: combine PDF annotations across versions
- [csv-export](#csv-export) — refresh the registry's CSV mirror
- [exif](#exif) — image routing metadata for vision-off models
- [merge-category](#merge-category) — add one taxonomy category via a JSON diff
- [folder-tree](#folder-tree-on-demand-view) — on-demand: render the organised tree (rules ∩ disk)
- [cleanup recipes](#cleanup-per-sync-app-eviction-recipes) — per-sync-app eviction commands
- [inbox-list](#inbox-list) — list files currently in `_Inbox/` (feeds the arbiter sweep)

---

## inbox-list

```bash
python3 ~/.claude/drive-organizer/organizer.py inbox-list
```

Returns a JSON object enumerating files that have been executed into `_Inbox/` (rows with `status='organized'` and a path containing `_Inbox`). Used by the orchestrator to decide when to trigger the arbiter sweep (see SKILL.md "Inbox arbiter sweep") and to build the `[INBOX_BATCH_JSON]` slot in `references/arbiter-prompt.md`.

**Output shape:**
```json
{
  "count": 42,
  "files": [
    {
      "id": 7,
      "filename": "scan-report-2024.pdf",
      "current_path": "/abs/path/_Inbox/scan-report-2024.pdf",
      "file_date": "2024-03-15",
      "is_image": false,
      "is_raw": false
    }
  ]
}
```

Fields:
- `count` — number of files currently in `_Inbox/` (already executed; files only classified-to-`_Inbox` this round but not yet executed are NOT counted)
- `files` — array of all `_Inbox` records; each entry carries exactly the fields the arbiter template expects; fill `[INBOX_BATCH_JSON]` directly from this array
- `is_image` — true only for non-RAW images (IMAGE_EXTS only); RAW files have `is_image: false` + `is_raw: true`; this encodes vision-readability for the arbiter's capability gate

---

## status

```bash
python3 ~/.claude/drive-organizer/organizer.py status
```

Reports the active root, total files in the registry, and counts by status. The complete status set the backend writes is: `pending` (scanned, awaiting classification), `organized` (moved to its destination), `duplicate` (byte-identical to a kept copy), `flagged` (marked `?` in the viewer), `to_delete` (execute routed it to `Archive/_To Delete/`), `deleted` (reconcile `--prune` marked a confirmed-gone row), `archived` (a merged original moved to `Archive/_Merged-Originals/`), and `missing` (execute crash-recovery: the file was `pending` but the physical path no longer exists — marked so it is not re-proposed as a ghost). `cmd_status` reflects whatever status values are present in the registry (it does a GROUP BY status query); since the backend only ever writes these eight, any status in the output is one of them (no other value exists — closed set). If a hand-edited or schema-drifted row carries an unrecognised status, it will appear unflagged in the output. Run at the start of any session to confirm which drive is configured.

To switch roots, pass `--root /path/to/folder` once (the new root persists for future calls — see SKILL.md "No subcommand").

---

## download-batch

```bash
python3 ~/.claude/drive-organizer/organizer.py download-batch --limit-gb 20
```

**Legacy.** The current `scan` command triggers downloads inline as part of its priority walk (priorities P2/P4/P6 download cloud-only files automatically), so this standalone command is rarely needed. Kept for manual top-ups when you want to pre-warm a chunk of the drive before scanning.

Behaviour: detects online-only (placeholder) files via the OS's cloud-placeholder signal — macOS xattr/dataless markers (verified), Windows `FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS`/`OFFLINE` (unverified), Linux treats files as local (no reliable placeholder signal) — and triggers the cloud provider to download them locally by reading the first byte (`open().read(1)`, the universal recall mechanism), stopping at the cumulative size cap. Skips already-local files, files already organised in the registry, and system files.

Report: files queued (with total GB), already local, skipped. If triggered count is 0 — all locally available files are already downloaded; proceed directly to scan without waiting.

If the script exits with `Error: root path not found: <path>`, confirm the drive is mounted and the sync app is running.

---

## flagged

```bash
python3 ~/.claude/drive-organizer/organizer.py flagged
```

Lists all files with `status='flagged'` — marked `?` in the viewer. Flagged files are excluded from future `propose` batches until resolved.

Actual output format:
```
Flagged files (N total):
  [ID] filename  —  /path/to/file

Flagged files are excluded from propose. To reclassify: peek/classify each, add it back into the next proposals_classified.json batch, and review it in the viewer — not executed directly.
To manually clear a flag: UPDATE files SET status='pending' WHERE id=<N>;
```

When empty, prints: `"No flagged files."` — see SKILL.md process-return step 7 for what to do in that case (skip the step).

For each flagged file:
1. Peek at content: use the Read tool for images (vision); for documents, get the text the same way scan does — extract directly per the per-format procedure in `references/file-type-routing.md` (do NOT expect a re-run of `scan` to re-peek a flagged file: scan's `organized_paths` query skips any file whose registry `status` is already `flagged`, so it will not re-extract `content_peek` for it) (e.g. `.docx`/`.xlsx`/`.pptx` → read the relevant XML members from the zip; `.pdf` → PyMuPDF text; plain text → raw read). Don't invent a format-specific reader — file-type-routing.md is the source of truth for which bytes/members to read.
2. Classify it (same logic as propose: generate `para_subfolder`, `new_filename`, `reason`)
3. Add it to the `proposals_classified.json` batch alongside new pending files — it goes back through the viewer, not executed directly

---

## reconcile

**Maintenance command** — run any time the organised structure has "drifted" or "got ruined": files moved out of place, the registry out of sync with disk, or stray/miscased folders at the root.

```bash
python3 ~/.claude/drive-organizer/organizer.py reconcile              # dry-run report (default)
python3 ~/.claude/drive-organizer/organizer.py reconcile --restore ID # move one file back to its recorded home
python3 ~/.claude/drive-organizer/organizer.py reconcile --accept ID  # keep one file where it is; update the registry
python3 ~/.claude/drive-organizer/organizer.py reconcile --prune ID   # mark one confirmed-deleted row as deleted
python3 ~/.claude/drive-organizer/organizer.py reconcile --apply      # BULK: restore ALL misplaced (only if every move was accidental)
```

**Dry-run first, decide per file.** The default run **moves nothing** — it detects three kinds of drift and writes a report. **Intent is never guessed**: a file that isn't where the registry expects could have been moved *by accident* (restore it) or *on purpose* (accept the new location), and only the user knows which.

1. **Misplaced files** — files not where the registry expects, in two forms:
   - `para_mismatch` — the file exists but its folder differs from the destination the registry recorded (`para_subfolder`).
   - `relocated_outside_tool` — the recorded file is gone from its path, but a same-named, same-size copy is found elsewhere under the root (e.g. dragged in Finder). The common "structure got ruined / database out of sync" case.

   Each entry carries a **`suggestion`** (`restore` or `accept`) from a landing-spot heuristic — found inside a proper grouping folder → probably intentional → `accept`; loose at the root or in `_Inbox` → probably accidental → `restore`. **The suggestion is advisory; confirm with the user, then act per file** with `--restore ID` (move it back to its recorded home) or `--accept ID` (leave the file where it is and update the registry's `current_path` + `para_subfolder` to match). `--apply` is a bulk "restore everything" shortcut — use it only when you've confirmed *every* move was accidental.

2. **Bad registry rows** — three `issue` values: `missing_on_disk` (the `current_path` no longer exists on disk **and** no relocated copy was found — genuinely deleted), `no_current_path` (an organized/duplicate row whose `current_path` is null/empty), or `organized_without_destination` (organized rows with no destination). Once the user confirms a file was deleted on purpose, `--prune ID` marks its row `deleted` so it stops being reported every run.
3. **Mangled root folders** — root-level folders that break the **active-grouping invariant** (the configured area set — the default five `ENTERTAINMENT/PERSONAL/WORK/EDUCATION/RESOURCES`, or whatever `<root>/.organizer/config.json` `"areas"` defines; reconcile reads `_active_groupings()`, it does not hardcode five): an unexpected non-grouping folder, a miscased grouping (`work` vs `WORK` — only detectable on case-sensitive drives), or a rule-bearing project folder still sitting at the root (legacy flat layout). **Report-only** — folder renames are too risky to automate; fix by hand.

**Recommended order** (the summary prints it): resolve the **registry-backed misplaced files first** (grouped, per-file restore/accept), then prune confirmed deletions, then deal with the **unregistered / mangled folders** (manual judgment). Output: a human summary plus a full `<root>/.organizer/reconcile-report.json` (arrays `misplaced_files` with `id`/`issue`/`fix_from`/`fix_to`/`suggestion`, `bad_registry_rows`, `mangled_folders`, `applied`). The `--restore`/`--accept`/`--prune` commands read this report, so run a dry-run `reconcile` first.

`reconcile` also (re)generates `<root>/.organizer/organize-rules.yaml` — a synced [`organize`](https://github.com/tfeldmann/organize) ruleset derived from the `.tidy-rules.json` cascade. It's a **verification artifact**, not used for normal classification. For a keyword-level cross-check of structural placement (catches name-based misplacements the registry may not know about), run `organize sim "<root>/.organizer/organize-rules.yaml"` (requires `organize-tool`; the count of `semantic-only` rules it can't verify is reported). `--apply` does **not** run organize — it only moves the registry-detected misplaced files.

After `--apply`, run `cleanup` to remove any folders left empty by the moves. **Not every misplaced file is moved:** `--apply` skips a file whose source is gone or whose destination already exists, recording `apply_result: "skipped — source no longer present"` / `"skipped — destination already exists"` in `reconcile-report.json` (the printed summary reports only the moved count). After `--apply`, read the report's `applied`/`misplaced_files` entries for any `skipped` `apply_result` and resolve those by hand — they were not fixed.

---

## duplicates

**Final-pass only** — run after all batches are organised and freed.

```bash
python3 ~/.claude/drive-organizer/organizer.py duplicates
```

If the script prints `"No exact duplicates found."` — no duplicates exist; proceed to **variants**.

Otherwise outputs a JSON array of duplicate groups (same SHA256). Each group has a `sha256` field, a `keeper_id` (the copy the backend judges best-placed — organized, outside `_Inbox/`/`Archive/`, deepest path), and a `files` array with `id`, `path`, `size`, `date`, `status`. Claude formats this for display, confirming the keeper and which copies to co-locate (the keeper default is usually right; override it if a different copy is better-placed). Once confirmed, for each non-keeper copy:

```bash
python3 ~/.claude/drive-organizer/organizer.py duplicates --colocate ID
```

Moves duplicate `ID` so it sits **beside the group's keeper**, renamed `<keeper-stem>_dupN` (so the copies sort adjacent to the original for easy visual checking), and marks `status='duplicate'` in the registry (CSV mirror updates automatically). Nothing is archived or deleted — co-located in place. Nothing moves until confirmed. (The old `--archive ID` flag is a deprecated alias that now co-locates too.)

If the script exits with `"File id N is the keeper …"` — you passed the keeper's ID; co-locate a different copy. If `"File id N not found in registry."`, `"File not found on disk: <path>"`, `"File id N has no duplicates …"`, or `"Keeper id N not found on disk: <path>…"` — re-run `duplicates` (without `--colocate`) to refresh the registry and confirm the correct ID. If `"Failed to co-locate id N (<src> → <dest>): …"` — a disk/permission error during the move; fix it and retry.

---

## variants

**Final-pass only.**

```bash
python3 ~/.claude/drive-organizer/organizer.py variants
```

If the script prints `"No variant groups found."` — no variants exist; the final pass is complete.

Otherwise outputs a JSON array of probable variant groups — grouped by same extension + normalised filename stem. It deliberately does **not** gate on a size ratio: a highlighted/annotated variant can legitimately be several times the size of the plain original, and a ratio cap would split exactly the variant pairs this command exists to surface. Each group has a `group_id`, a `key` (the normalised filename used for matching), and a `files` array with `id`, `path`, `filename`, `file_size`, `file_date`. Claude formats this for display:

```
Group 1:
  A) Final payment summary.pdf         (102 KB, 2024-05-01)
  B) Final payment summary v2.pdf      (108 KB, 2024-05-03)

Merge, keep A, keep B, or skip?
```

For each group, the user picks one of: merge (combine annotations into a canonical file via the `merge` command), keep A only (B becomes duplicate), keep B only, or skip (leave both alone).

---

## merge

**Final-pass only.**

```bash
python3 ~/.claude/drive-organizer/organizer.py merge \
  --group GROUP_ID --canonical FILE_ID
```

Uses PyMuPDF to extract annotations (highlights, comments, sticky notes) from non-canonical versions and insert them into the canonical file. Originals move to `Archive/_Merged-Originals/` and are marked `status='archived'` in the registry (CSV mirror updates automatically).

**No-data-loss guard — handle the WARNINGs.** A variant is **left in place (not archived)** — so the `Merge complete: N files merged` count drops below the group size and a variant stays un-merged on purpose — in **two** cases, each printed to stderr:
- **More pages than the canonical:** `WARNING: <file> has N pages vs canonical M — trailing-page annotations cannot merge; left in place (not archived).` (the extra pages have nowhere to merge into).
- **Annotations only partially copied:** `WARNING: <file> has N annotation(s) but only K could be copied — left in place (not archived) to avoid data loss.` — fires on **any** shortfall (`K < N`, the all-failed `K=0` case included), since partial loss is loss.

Don't treat either as failure: report the warning to the user, leave the file, and (if they still want it merged) retry or merge it manually — never delete or move a warned file to reclaim the "missing" count.

If PyMuPDF is not installed: `pip install pymupdf` (or `pip3 install --user --break-system-packages pymupdf` on macOS PEP-668 systems).

If the script prints `"No other files in this variant group."` — the `group_id` from variants is stale; re-run `variants` to get fresh IDs and try again.

If the script exits with `"Canonical file id N not found."` or `"Canonical file not found: <path>"` — re-run `variants` to get fresh IDs and try again.

If it exits with `"Could not open canonical PDF <path>: …"` — the canonical file is corrupt/unreadable; nothing was changed and no originals were archived (the message says so). Pick a different canonical (another group member) or repair the file. If it exits with `"Failed to save merged canonical <path>: …"` — a disk/write error after annotations were copied in memory; the originals were NOT archived, so re-run after fixing the disk/permission problem.

---

## csv-export

```bash
python3 ~/.claude/drive-organizer/organizer.py csv-export
```

Forces a manual refresh of `<root>/.organizer/registry.csv` from the SQLite registry. Every mutation already mirrors automatically (scan, execute, duplicates --colocate, merge, etc.) so this command is rarely needed — only run it if the CSV looks out of date, has been manually edited and you want to overwrite the changes, or has been deleted.

The CSV is meant for human auditing (open in Numbers / Excel / a text editor); the SQLite `registry.db` is the authoritative source. Both live in `<root>/.organizer/`.

---

## exif

```bash
python3 ~/.claude/drive-organizer/organizer.py exif "<path to image>"
```

Prints routing-useful image metadata as a single JSON object — the **vision-off degradation path** (see SKILL.md "Model capabilities"). When the running model can't see images, a classification agent calls this to route a photo by its capture date instead of its pixels (e.g. matching a project's `date_range`).

Output fields: `path` (the input path, echoed back so a fan-out caller can match each output object to its file), `date` (`YYYY-MM-DD`), `camera` (Make + Model), `width`, `height`, plus `source` (`exif` | `filename` | `none`) and a `note`. It is deliberately **total** — it never errors and always prints an object:

- Pillow is an **optional** dependency. With it installed, `date`/`camera`/dimensions come from embedded EXIF (`source: "exif"`). Install for richer metadata: `pip3 install --user --break-system-packages pillow`.
- Without Pillow (or when the image carries no EXIF), it degrades to the filename-derived date via the same `-PHOTO-YYYY-MM-DD` pattern the image router uses (`source: "filename"`), and `note` explains the degrade.
- A missing file or unreadable image still returns the JSON object with `source: "none"` and an explanatory `note` — callers never have to handle a non-zero exit.

This subcommand only **reports** metadata; it does not move or rename anything.

---

## merge-category

```bash
python3 ~/.claude/drive-organizer/organizer.py merge-category \
  --diff '{"name":"Grants","description":"grant / funding paperwork in Grants","parent":"Financials"}'
```

Adds **one** category to the user's taxonomy from a small JSON **diff**, instead of having a model rewrite the whole nested templates file (fragile under context accumulation — the model owns the *diff*, Python owns the *merge*). Writes into the **per-user override** at `<root>/.organizer/templates.json` (atomic write), which `templates` / `_load_templates` deep-merge over the shipped skeleton — the shipped `references/subfolder-templates.json` is never touched.

`--diff` is a JSON object:

| Key | Required | Effect |
|---|---|---|
| `name` | yes | The new subfolder name; written into the override's `subfolder_definitions` |
| `description` | no | Signal-term gloss for the classifier (convention: "… in `<name>`"). Updates the existing description if the name already exists |
| `parent` | no | A compound parent type (e.g. `Financials`); appends `name` to that parent's `compound_children[parent].children` so the cascade offers it as a valid child |

Prints a JSON receipt: `{merged, override, action: "added"|"updated", linked_under}`. Invalid JSON, a non-object diff, a missing `name`, or an unparseable existing override all exit non-zero with a one-line error — so a bad diff fails loudly rather than corrupting the override. Use this when the learning loop discovers a genuinely new category that the templates don't yet define; for per-folder file→folder rules use the `.tidy-rules.json` learning loop instead.

---

## folder-tree (on-demand view)

When the user asks to see the folder tree (any wording — "show me the folder tree", "what's the structure look like", "list the folders") for the drive root or any organised folder, show the **intersection of rule-defined structure AND actual filesystem state** — what's organised, not what's possible.

**Gather the two inputs:** for the *rule-defined* half, run `organizer.py rules --json` — it aggregates every `.tidy-rules.json` across the tree (each entity's `occurrences[].dest` is a rule-defined folder path); for the *filesystem* half, `ls`/walk the actual directories. Intersect:

**Include:**
- Folders referenced in the root `.tidy-rules.json` (the canonical top-level project folders)
- Subfolders referenced in each folder's own `.tidy-rules.json` *that also physically exist on disk*

**Exclude:**
- Subfolders that exist on disk but aren't referenced in any `.tidy-rules.json` (e.g. `ENTERTAINMENT Music/`'s 1107 artist folders, season folders inside media folders, raw content subfolders)
- Subfolders referenced in rules but not yet on disk (aspirational destinations — show them only if the user asks for the rule-defined structure specifically)
- All files

**Why:** a flat list of rule-folders isn't a tree, and the full filesystem tree is dominated by media/content folders that drown out the project structure the user cares about. The intersection gives them what's both *intended* (rules) and *realised* (on disk).

**Output format:** standard tree characters (`├──`, `└──`, `│   `) with `/` suffix on folder names. Mark rule-bearing folders with a small ` [rules]` tag so the user can see which folders carry their own classification rules vs which are just destination subfolders.

---

## bootstrap (proposals-file shape)

`bootstrap --apply` reads a JSON **object** with two top-level keys (a bare list or any non-object is rejected with an error; an object missing `rules`/`entities` writes zero of that kind):

```json
{
  "rules": [ {"parent": "<rel path of the folder's PARENT, '' for root>", "folderName": "<folder name>", "description": "<inferred signal> in <folder name>"} ],
  "entities": { "<folder name>": {"entity_type": "<area|project|person|category|policy|atomic|unknown>", "notes": "<why>"} }
}
```

`--apply` writes each `rules[]` entry into its folder's parent `.tidy-rules.json` and each `entities{}` entry into `entities.json`. (See SKILL.md "bootstrap (setup walkthrough)" for the full detect→lock→emit→infer→apply→review flow.)

---

## cleanup (per-sync-app eviction recipes)

After `cleanup` removes empty folders, free local disk space by evicting the organised grouping folders (the top-level groupings — e.g. `WORK/`, `PERSONAL/` — **not** the `_Inbox/`/`Archive/` staging folders) to online-only; the cloud copies stay and re-download on demand.

**Automated — `cleanup --evict`**: dehydrates those grouping folders for you, per-OS and best-effort:
- **macOS**: `brctl evict <folder>` — works for File-Provider/iCloud-backed drives (verified path). OneDrive-on-macOS has no eviction CLI, so it fails cleanly and falls back to the manual recipe below.
- **Windows**: `attrib +U -P <folder> /s /d` — unpins OneDrive Files-On-Demand to online-only (best-effort, unverified).
- **Linux / other**: no standard eviction command → prints the manual recipe.
Per-folder failures, a missing tool, or an unsupported OS never error the run — `--evict` reports what it evicted and points to the manual recipe for the rest. Without `--evict`, `cleanup` only removes empty folders; tell the user the manual recipe.

**Manual recipe (fallback):**
- **OneDrive**: right-click folder → *Free up space*
- **iCloud Drive**: right-click folder → *Remove Download*
- **Dropbox Smart Sync**: right-click folder → Smart Sync → *Online only*
- **Google Drive (Stream mode)**: no action needed — files evict automatically once closed

## generate-viewer (submit-response handling)

<!-- SKILL.md's generate-viewer section points here for the after-submit log-line interpretation. -->

**Check the server's final log line before continuing.** The server writes `proposals_approved.json`
AND `proposals_flagged.json` to disk *before* it prints `Approved proposals written to: <path>`
followed by `Server shutting down.` (both printed, in that order, by the `do_POST` handler of the
viewer server that `cmd_generate_viewer` starts in `organizer.py` — grep those two log-line strings
to locate them). Once you see `Server shutting down.` both sidecar files are
guaranteed present (the case-3 recovery below can always read `proposals_flagged.json`). One of these cases holds:

- **Write failure — no `Server shutting down.` line at all**, instead `ERROR: could not write review
  output (…); submit NOT saved` on stderr and an HTTP 500 in the browser: the write failed, the
  server is **still running**, nothing was saved. Do NOT proceed to process-return; tell the user to
  resolve the disk/permission problem and re-submit (or re-run `generate-viewer`). The remaining
  cases all assume the submit was written (the `Server shutting down.` line printed):
- **Neither flagged line appears** (only `Approved proposals written to: …` / `Server shutting
  down.`) — no files were `?`-flagged this round; proceed normally.
- `"N files marked flagged in registry."` — `?`-flagged files were persisted; proceed normally.
- `"Warning: could not mark flagged in DB: <error>"` — the flag write failed. Patch the registry
  before running process-return:
  ```bash
  sqlite3 <root>/.organizer/registry.db "UPDATE files SET status='flagged' WHERE id IN (<comma-separated IDs>);"
  ```
  Get the exact IDs from `~/.claude/drive-organizer/proposals_flagged.json` — the viewer writes the
  precise flagged-ID set there on **every** submit (a bare JSON array, e.g. `[12,47,88]`; `[]` when
  nothing was flagged). **Do not** infer them by "IDs in `proposals_classified.json` not in
  `proposals_approved.json`": that set also contains rows the user left **unreviewed** (`unset`), and
  marking those `flagged` would wrongly drop unreviewed files from future propose batches.

If `Error: proposals file not found: <path>` or `Error: proposals JSON is empty.` — re-run propose to
regenerate `proposals_classified.json` first. If `Error: port <N> is already in use…` — re-run
`generate-viewer` with the suggested `--port`.

## process-return (learning-loop accelerators + routing notes)

<!-- SKILL.md's process-return section points here for the W5 accelerators, the ordering rationale,
     and the delete-routing note. The numbered pipeline stays in SKILL.md. -->

**Replay / crash-recovery:** If process-return is re-run after a crash (e.g. execute completed partially, then the session died), re-running execute on an already-consumed `proposals_approved.json` will produce `MISSING` errors for files already moved in the prior run. This is safe replay noise — not a real error. The files are at their correct destination; the registry row is already `status='organized'`. Skip those MISSING entries and continue; do not treat them as lost or corrupt files. Generate a fresh proposals batch for the next round as normal.

**Why learnings come before reclassification:** A rejection means the proposed destination was wrong,
but *what* the right destination is often depends on a pattern the user just demonstrated by editing
an approved entry. If you reclassify rejects before extracting learnings from approvals, you guess; if
you do it after, the rules already encode their latest preferences and reclassification becomes a
lookup.

**Routing note (delete entries):** execute reads `action == 'delete'` and hard-codes the move
destination to `Archive/_To Delete/` — the entry's `para_subfolder` is ignored. The registry row then
records that **actual** destination (`para_subfolder='Archive/_To Delete'`, `para_category` derived
→ `_Inbox`), so the registry always matches disk even if a hand-edited delete entry had a different
`para_subfolder`. (`para_category` is a pure projection of the recorded `para_subfolder` for every
row, delete included.) For all other entries (approved, inbox, reclassified), routing is via
`para_subfolder` only; inbox entries work because the viewer already sets `para_subfolder='_Inbox'`.

**Learning-loop accelerators (W5)** — use these when writing rules in step 2 and handling rejections:

- **Auto-infer the signal, not just the folder.** When several approved files routed to the same
  (possibly new) folder, derive the rule's signal from the tokens common to those filenames rather
  than the folder name alone — the backend exposes `_infer_signal_from_filenames(names)`. A
  signal-bearing rule then auto-routes the *next* similar file via W1.
- **Learn from rejections (negative signal).** A rejection says "files like this do NOT belong here."
  Record the distinguishing token(s) in that entity's `entities.json` `negative: [...]` list. The W1
  matcher then suppresses that destination for any filename carrying a negative token.
- **Aliases cut repeat corrections.** When the user keeps correcting the same misspelling/short form
  to one entity, add it to that entity's `aliases` (viewer or `entities.json`); the matcher routes
  alias spellings (down to 3 chars) straight to the entity.
- **Proactive "make a rule?"** After a batch, if N files were approved into the same new folder, offer
  to write the rule once (with the inferred signal) instead of re-classifying each next time.
- **Confidence auto-approval (opt-in).** With `auto_approve` on (config or `--auto-approve`), **W1
  fast-path** auto-routed files (the deterministic rule match — not a classifier `confidence` verdict)
  are flagged `auto_approved` — you may execute them without a viewer pass (still audited in
  `auto-routed.csv`). Default OFF: human review stays the norm unless the user opts in.

**W5 routing-note format.** When the orchestrator annotates a `proposals_classified.json` entry with a routing note (e.g. to record why a file was auto-approved or why a rule was inferred), append a `routing_note` key to that entry with a plain-text string value:
```json
{
  "id": 42,
  "para_subfolder": "WORK/[COMPANY]/Admin",
  "routing_note": "W5 auto-infer: tokens [company, admin] matched 3 approved files"
}
```
The key name is `routing_note` (singular); the value is a free-text one-line explanation. This field is informational only — `cmd_execute` and `cmd_generate_viewer` ignore it; it is for audit/debugging purposes and is NOT written to the registry or `auto-routed.csv` automatically (if audit trail is needed, append it there manually).
