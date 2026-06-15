# Subcommand reference — lower-frequency commands

Detailed documentation for utility / final-pass subcommands that aren't part of the main batch loop. The high-frequency loop commands (`scan`, `propose`, `generate-viewer`, `process-return`, `execute`, `cleanup`) stay in `SKILL.md` because they fire every batch.

Consult this file when invoking any of the commands below, hitting their errors, or planning the final pass at the end of organising.

## Table of contents

- [status](#status)
- [download-batch](#download-batch) — legacy; `scan` does this inline now
- [mark-unapproved](#mark-unapproved) — run once at the start of organising a new drive
- [flagged](#flagged) — peek-and-reclassify items the user `?`-marked
- [reconcile](#reconcile) — maintenance: detect/repair structure drift
- [duplicates](#duplicates) — final pass: SHA256 groups
- [variants](#variants) — final pass: fuzzy-name groups
- [merge](#merge) — final pass: combine PDF annotations across versions
- [csv-export](#csv-export) — refresh the registry's CSV mirror

---

## status

```bash
python3 ~/.claude/drive-organizer/organizer.py status
```

Reports the active root, total files in the registry, and counts by status (pending / organized / flagged / duplicate / archived). Run at the start of any session to confirm which drive is configured.

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

## mark-unapproved

```bash
python3 ~/.claude/drive-organizer/organizer.py mark-unapproved
```

Prefixes every root-level folder that has no known rules with `x`, deferring it from scan. A folder is "known" if it has a `.tidy-rules.json` file inside it, or if it appears as a destination in the root `.tidy-rules.json`. Staging folders (`_Inbox`, `Archive`) are always left untouched. Already x-prefixed folders are left alone.

Run this **once before the first scan** to quarantine all legacy/unknown folders — they will be skipped until you're ready to process them (see x-folder transition in the batch cycle section of SKILL.md).

Post-migration to the nested grouping structure (ENTERTAINMENT/PERSONAL/WORK/EDUCATION/RESOURCES), the utility shrinks: only the five groupings + Archive + _Inbox + logseq-journals should exist at root, so unknown root folders become anomalies worth flagging individually rather than batch-quarantining.

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

Flagged files are excluded from propose. To reclassify: classify directly and run execute.
To manually clear a flag: UPDATE files SET status='pending' WHERE id=<N>;
```

When empty, prints: `"No flagged files."` — skip this step in the process-return flow.

For each flagged file:
1. Peek at content: use the Read tool for images (vision); for documents, extract text via zipfile/raw byte read
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

2. **Bad registry rows** — rows whose `current_path` no longer exists on disk **and no relocated copy was found** (`missing_on_disk` — genuinely deleted), or organized rows with no destination (`organized_without_destination`). Once the user confirms a file was deleted on purpose, `--prune ID` marks its row `deleted` so it stops being reported every run.
3. **Mangled root folders** — root-level folders that break the five-grouping invariant: an unexpected non-grouping folder, a miscased grouping (`work` vs `WORK` — only detectable on case-sensitive drives), or a rule-bearing project folder still sitting at the root (legacy flat layout). **Report-only** — folder renames are too risky to automate; fix by hand.

**Recommended order** (the summary prints it): resolve the **registry-backed misplaced files first** (grouped, per-file restore/accept), then prune confirmed deletions, then deal with the **unregistered / mangled folders** (manual judgment). Output: a human summary plus a full `<root>/.organizer/reconcile-report.json` (arrays `misplaced_files` with `id`/`issue`/`fix_from`/`fix_to`/`suggestion`, `bad_registry_rows`, `mangled_folders`, `applied`). The `--restore`/`--accept`/`--prune` commands read this report, so run a dry-run `reconcile` first.

`reconcile` also (re)generates `<root>/.organizer/organize-rules.yaml` — a synced [`organize`](https://github.com/tfeldmann/organize) ruleset derived from the `.tidy-rules.json` cascade. It's a **verification artifact**, not used for normal classification. For a keyword-level cross-check of structural placement (catches name-based misplacements the registry may not know about), run `organize sim "<root>/.organizer/organize-rules.yaml"` (requires `organize-tool`; the count of `semantic-only` rules it can't verify is reported). `--apply` does **not** run organize — it only moves the registry-detected misplaced files.

After `--apply`, run `cleanup` to remove any folders left empty by the moves.

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
