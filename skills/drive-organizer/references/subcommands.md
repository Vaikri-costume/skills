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

---

## status

```bash
python3 ~/.claude/drive-organizer/organizer.py status
```

Reports the active root, total files in the registry, and counts by status. The complete status set the backend writes is: `pending` (scanned, awaiting classification), `organized` (moved to its destination), `duplicate` (byte-identical to a kept copy), `flagged` (marked `?` in the viewer), `to_delete` (execute routed it to `Archive/_To Delete/`), `deleted` (reconcile `--prune` marked a confirmed-gone row), and `archived` (a merged original moved to `Archive/_Merged-Originals/`). `cmd_status` prints whatever statuses are present; since the backend only ever writes these seven, any status in the output is one of them (no other value exists — closed set). Run at the start of any session to confirm which drive is configured.

To switch roots, pass `--root /path/to/folder` once (the new root persists for future calls — see SKILL.md "No subcommand").

---

## download-batch

```bash
python3 ~/.claude/drive-organizer/organizer.py download-batch --limit-gb 20
```

**Legacy.** The current `scan` command triggers downloads inline as part of its priority walk (priorities P2/P4/P6 download cloud-only files automatically), so this standalone command is rarely needed. Kept for manual top-ups when you want to pre-warm a chunk of the drive before scanning.

Behaviour: detects online-only (placeholder) files via xattr and triggers the cloud provider to download them locally, stopping at the cumulative size cap. Skips already-local files, files already organised in the registry, and system files.

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

When empty, prints: `"No flagged files."` — skip this step in the process-return flow.

For each flagged file:
1. Peek at content: use the Read tool for images (vision); for documents, get the text the same way scan does — the simplest path is to re-run `scan` (it re-extracts `content_peek` for the file into the registry, then read it back), or extract directly per the per-format procedure in `references/file-type-routing.md` (e.g. `.docx`/`.xlsx`/`.pptx` → read the relevant XML members from the zip; `.pdf` → PyMuPDF text; plain text → raw read). Don't invent a format-specific reader — file-type-routing.md is the source of truth for which bytes/members to read.
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

If the script exits with `"File id N is the keeper …"` — you passed the keeper's ID; co-locate a different copy. If `"File id N not found in registry."`, `"File not found on disk: <path>"`, or `"File id N has no duplicates …"` — re-run `duplicates` (without `--colocate`) to refresh the list and confirm the correct ID.

---

## variants

**Final-pass only.**

```bash
python3 ~/.claude/drive-organizer/organizer.py variants
```

If the script prints `"No variant groups found."` — no variants exist; the final pass is complete.

Otherwise outputs a JSON array of probable variant groups — similar names, same extension, size ratio ≤ 2×. Each group has a `group_id`, a `key` (the normalised filename used for matching), and a `files` array with `id`, `path`, `filename`, `file_size`, `file_date`. Claude formats this for display:

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

**No-data-loss guard — handle the WARNING.** If a variant carried annotations that could not be copied, the script prints `WARNING: <file> has N annotation(s) but none could be copied — left in place (not archived) to avoid data loss.` to stderr and **leaves that file where it is** (not archived). So the `Merge complete: N files merged` count can be lower than the group size, and a variant remains un-merged on purpose. Don't treat that as failure: report the warning to the user, leave the file, and (if they still want it merged) retry or merge it manually — never delete or move a warned file to reclaim the "missing" count.

If PyMuPDF is not installed: `pip install pymupdf` (or `pip3 install --user --break-system-packages pymupdf` on macOS PEP-668 systems).

If the script prints `"No other files in this variant group."` — the `group_id` from variants is stale; re-run `variants` to get fresh IDs and try again.

If the script exits with `"Canonical file id N not found."` or `"Canonical file not found: <path>"` — re-run `variants` to get fresh IDs and try again.

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

Prints routing-useful image metadata as a single JSON object — the **vision-off degradation path** (see SKILL.md "Model capabilities"). When the running model can't see images, a classification agent calls this to route a photo by its capture date instead of its pixels (e.g. matching a project's `production_period`).

Output fields: `date` (`YYYY-MM-DD`), `camera` (Make + Model), `width`, `height`, plus `source` (`exif` | `filename` | `none`) and a `note`. It is deliberately **total** — it never errors and always prints an object:

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
- Subfolders referenced in rules but not yet on disk (aspirational destinations — show them only if she asks for the rule-defined structure specifically)
- All files

**Why:** a flat list of rule-folders isn't a tree, and the full filesystem tree is dominated by media/content folders that drown out the project structure she cares about. The intersection gives her what's both *intended* (rules) and *realised* (on disk).

**Output format:** standard tree characters (`├──`, `└──`, `│   `) with `/` suffix on folder names. Mark rule-bearing folders with a small ` [rules]` tag so she can see which folders carry their own classification rules vs which are just destination subfolders.

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

After `cleanup` removes empty folders, tell the user how to free local disk space by evicting the grouping folders this batch wrote to (the top-level groupings — e.g. `WORK/`, `PERSONAL/` — **not** the `_Inbox/`/`Archive/` staging folders), using their sync app:
- **OneDrive**: right-click folder → *Free up space*
- **iCloud Drive**: right-click folder → *Remove Download*
- **Dropbox Smart Sync**: right-click folder → Smart Sync → *Online only*
- **Google Drive (Stream mode)**: no action needed — files evict automatically once closed
