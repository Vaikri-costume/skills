"""drive_organizer.execute — split from the original organizer.py (pure structural move, no behavior change)."""
from __future__ import annotations
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

from drive_organizer import paths_config
from drive_organizer.paths_config import (
    _atomic_write,
    _effective_period_buffer_days,
    _safe_dest,
)
from drive_organizer.content_peek import (
    get_db,
)
from drive_organizer.date_range import (
    _expand_date_range,
    _find_project_for_destination,
)
from drive_organizer.csv_export import (
    export_csv,
)


def cmd_execute(args):
    from drive_organizer.cleanup_reconcile import _active_groupings, _normalize_grouping, _para_category
    from drive_organizer.viewer_propose import _persist_flagged_status
    approved_path = Path(args.approved)
    if not approved_path.exists():
        sys.exit(f"Error: approved file not found: {approved_path}")

    with open(approved_path, encoding="utf-8") as f:
        _raw = json.load(f)

    # Normalise both formats: the static viewer's dl() writes a dict
    # {approved:[…], flagged:[…], skipped:[…]}; the localhost server's /submit
    # endpoint normalises on receipt and writes the flat list.  Load both here
    # so static-path execute no longer crashes with AttributeError when iterating
    # dict keys instead of entry dicts.
    if isinstance(_raw, dict):
        approved = _raw.get("approved", [])
        # The static-viewer path carries flagged entries in this same dict but, unlike
        # the localhost /submit handler (which calls _persist_flagged_status before the
        # user runs execute), nothing had persisted them — so files flagged via the
        # static viewer silently stayed status='pending', reappeared next propose, and
        # `flagged` (process-return step 7) found none. Persist them here so the static
        # path produces the SAME registry side-effect as the localhost path.
        _flagged_raw = _raw.get("flagged", []) or []
        _flagged_ids = [(e.get("id") if isinstance(e, dict) else e) for e in _flagged_raw]
        _flagged_ids = [fid for fid in _flagged_ids if fid is not None]
        if _flagged_ids:
            if not _persist_flagged_status(str(paths_config.REGISTRY_DB), _flagged_ids):
                print("Warning: flagged-status write failed during execute — "
                      "patch status='flagged' manually from proposals_flagged.json.", flush=True)
    else:
        approved = _raw

    if not approved:
        print("Approved list is empty.")
        return

    drive = paths_config._EFFECTIVE_ROOT
    conn = get_db()
    moved = errors = 0
    # Load groupings once here so _para_category does not re-read config.json per file.
    groupings = _active_groupings()

    # --- Crash-recovery move journal (BL-A: move-then-commit crash window) ----------
    # A crash BETWEEN shutil.move and the registry UPDATE+commit would leave a file
    # at its new location but the registry pointing at the old path. To make that
    # window recoverable we keep a tiny sidecar journal: before each move we record
    # {id, src, dest}; we move; we UPDATE+commit; then we clear the journal entry.
    # On start, a non-empty journal is reconciled — if the file is already at `dest`
    # the move happened (fix the registry row); if it is still at `src` we leave it
    # for the normal pass to re-move.
    #
    # The per-move read-modify-write of this file (in _write_journal_entry /
    # _clear_journal_entry below) is DELIBERATE and must NOT be optimised into an
    # in-memory dict flushed once per batch: the whole point is that the {id,src,dest}
    # record is durable on disk BEFORE the move and removed only AFTER the commit, so a
    # crash at any instant leaves a recoverable on-disk trail. Holding it in memory and
    # writing once would reopen exactly the crash window this journal closes — the I/O
    # is the feature, not waste. (Batch size is bounded by the propose cap, so the cost
    # is bounded too.)
    journal_path = drive / ".organizer" / ".move-journal.json"

    def _read_journal() -> dict:
        try:
            raw = journal_path.read_text(encoding="utf-8")
        except OSError:
            return {}  # absent / unreadable — normal: no journal yet, nothing to recover
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, ValueError):
            # The file EXISTS but won't parse — the exact corruption the journal guards
            # against. Surface it (a crash-stranded move may not auto-recover) instead of
            # silently treating it as empty and skipping recovery with no diagnostic.
            print(f"  WARNING: move-journal {journal_path} is unparseable — a "
                  f"crash-stranded move may not be auto-recovered; run `reconcile` to "
                  f"check for files whose registry path is stale.", file=sys.stderr)
            return {}

    def _write_journal_entry(jid, jsrc, jdest, jstatus):
        journal_path.parent.mkdir(parents=True, exist_ok=True)
        j = _read_journal()
        # Record the intended terminal status (to_delete / organized) so recovery reads
        # the move's INTENT directly instead of re-deriving delete-vs-organized by
        # string-matching the dest path — robust even if the delete staging path changes.
        j[str(jid)] = {"id": jid, "src": jsrc, "dest": jdest, "status": jstatus}
        _atomic_write(journal_path, json.dumps(j, indent=2))

    def _clear_journal_entry(jid):
        j = _read_journal()
        if str(jid) in j:
            del j[str(jid)]
            _atomic_write(journal_path, json.dumps(j, indent=2))

    # Reconcile any leftover journal from a previous crashed run BEFORE processing.
    pending_journal = _read_journal()
    if pending_journal:
        for jid, rec in list(pending_journal.items()):
            try:
                jdest = Path(rec["dest"]); jsrc = Path(rec["src"])
            except Exception:
                _clear_journal_entry(jid)
                continue
            if jdest.exists() and not (jsrc.exists() and jsrc.samefile(jdest)):
                # The move completed but the registry may not have been updated. Reconstruct
                # the FULL organised-row state from the destination so the row is complete —
                # not left status='pending' with stale para_* (which the next scan would
                # wrongly re-process as unorganised). para_subfolder = the dest's folder
                # relative to root; para_category = its first segment projected onto the
                # active groupings (mirrors the normal execute write below).
                try:
                    rec_sub = str(Path(jdest).parent.relative_to(drive)).replace(os.sep, "/")
                except ValueError:
                    rec_sub = ""
                rec_cat = _para_category(rec_sub, groupings)
                # Prefer the intent journaled at move time; fall back to the path compare
                # for entries written by an older build that didn't record `status`.
                rec_status = rec.get("status") or ("to_delete" if rec_sub == "Archive/_To Delete" else "organized")
                conn.execute(
                    "UPDATE files SET current_path=?, para_subfolder=?, para_category=?, "
                    "status=?, processed_at=? WHERE id=?",
                    (str(jdest), rec_sub, rec_cat, rec_status,
                     datetime.now().isoformat(), rec.get("id"))
                )
                conn.commit()
                # Also widen the destination project's date_range, exactly as the
                # normal move path does — otherwise a crash-recovered file would silently
                # skip that update (it is never re-processed: it is now status='organized'),
                # making recovery non-idempotent vs a clean run. file_date persists on the
                # registry row from scan time, so read it back and apply it.
                # Nesting levels here are each independently required.
                # Outer governing conditions (see `if jdest.exists() and not
                # (jsrc.exists() and jsrc.samefile(jdest))` above): this entire
                # block runs ONLY when the move completed but the registry may not
                # have been updated (jdest present, src absent or different from dest).
                # Inner guards:
                # rec_status=="organized" → only widen for organized moves (not deletes);
                # rec_date truthy → only if the row has a recorded date;
                # proj is not None → only if the destination maps to a known project.
                if rec_status == "organized":
                    try:
                        _r = conn.execute("SELECT file_date FROM files WHERE id=?", (rec.get("id"),)).fetchone()
                        rec_date = _r["file_date"] if _r else None
                        if rec_date:
                            proj = _find_project_for_destination(rec_sub, drive)
                            if proj is not None:
                                _expand_date_range(proj, rec_date,
                                                    buffer_days=_effective_period_buffer_days(drive),
                                                    root=drive)
                    except Exception as e:
                        print(f"  WARN: could not update date_range on recovery for id {rec.get('id')}: {e}",
                              file=sys.stderr)
                print(f"  RECOVERED: journal entry id {rec.get('id')} -> {jdest} (status={rec_status})", file=sys.stderr)
                _clear_journal_entry(jid)
            elif jsrc.exists():
                # File still at source — the move never happened; leave for re-move.
                _clear_journal_entry(jid)
            else:
                # Neither src nor dest present — the file vanished mid-move (moved or
                # deleted out-of-band between the journal write and the crash). Nothing is
                # safe to auto-recover, but DON'T drop it silently: surface it so the user
                # knows a move was lost and can reconcile, then clear the stale entry.
                print(f"  WARNING: journal entry id {rec.get('id')} points at a file that is "
                      f"at neither {jsrc} nor {jdest} — a move was lost (file relocated/deleted "
                      f"outside the tool mid-move). Run `reconcile` to repair the registry row.",
                      file=sys.stderr)
                _clear_journal_entry(jid)
                # Mark the registry row as 'missing' so it is not re-proposed — a ghost
                # pending row would reappear in the next propose batch and be classified again,
                # masking the actual data-loss event.
                try:
                    conn.execute(
                        "UPDATE files SET status='missing' WHERE id=?",
                        (rec.get("id"),)
                    )
                    conn.commit()
                except Exception as _e:
                    print(f"  WARN: could not mark id {rec.get('id')} as missing: {_e}",
                          file=sys.stderr)

    for entry in approved:
        file_id     = entry["id"]
        src         = Path(entry["current_path"])
        action      = entry.get("action", "approved")
        subfolder   = _normalize_grouping(entry.get("para_subfolder", ""))
        new_filename = entry.get("new_filename")
        vision_desc  = entry.get("vision_desc")
        file_date    = entry.get("file_date")

        if not src.exists():
            print(f"  MISSING: {src}", file=sys.stderr)
            errors += 1
            continue

        # Build the destination dir via _safe_dest so a JSON-supplied subfolder can
        # never escape the drive (path traversal: '..' / absolute / symlink escape).
        # _safe_dest returning None means 'reject' — record an error and SKIP the
        # move; NEVER fall back to an unchecked drive / subfolder join.
        sub_rel = "Archive/_To Delete" if action == "delete" else subfolder
        # para_category is a PURE PROJECTION of the actual destination (sub_rel): its first
        # path segment when that is an active grouping, else _Inbox. Derived unconditionally
        # (never from a caller-supplied para_category — the verdict contract excludes it), so
        # the registry column can never drift from para_subfolder. For a delete the destination
        # is Archive/_To Delete, so it resolves to _Inbox (the file is in staging, not a
        # grouping) — consistent with where the file actually lands.
        category = _para_category(sub_rel, groupings)
        dest_dir = _safe_dest(drive, sub_rel)
        if dest_dir is None:
            why = "empty/missing" if not (sub_rel or "").strip() else "unsafe (escapes the drive root)"
            print(f"  ERROR: {why} destination subfolder {sub_rel!r} for {src} — skipped.",
                  file=sys.stderr)
            errors += 1
            continue
        dest_dir.mkdir(parents=True, exist_ok=True)
        if not new_filename and src.name != entry.get("filename", src.name):
            print(f"WARNING: src.name ({src.name!r}) differs from entry['filename'] "
                  f"({entry.get('filename')!r}) — current_path may be stale from a prior "
                  f"partial execute. Proceeding with src.name.", file=sys.stderr)
        dest_name = new_filename if new_filename else src.name
        dest      = dest_dir / dest_name

        # Collision loop. Treat a case-insensitive same-file (dest IS src on a
        # case-insensitive FS, or via samefile) as identity so we don't needlessly
        # rename a file onto itself; only suffix-bump for a genuinely different file.
        if dest.exists() and not (src.exists() and dest.samefile(src)):
            stem, suffix = dest.stem, dest.suffix
            counter = 2
            while dest.exists() and not (src.exists() and dest.samefile(src)):
                dest = dest_dir / f"{stem}_{counter}{suffix}"
                counter += 1

        new_status = "to_delete" if action == "delete" else "organized"
        # Effective date for date_range widening: the verdict's file_date if the
        # classifier/arbiter supplied one, else the scan-time date already in the registry
        # (which the UPDATE below preserves via COALESCE(?,file_date)). Reading it here means
        # a verdict that omits file_date — permitted by classify-prompt.md "omit when
        # unknown" — still widens the project period from the scan-time date instead of
        # silently leaving it un-widened.
        effective_date = file_date
        if not effective_date:
            _row = conn.execute(
                "SELECT file_date FROM files WHERE id=?", (file_id,)).fetchone()
            if _row is not None:
                effective_date = _row["file_date"]
        # Journal the intent BEFORE moving so a crash in the move-then-commit window
        # is recoverable on the next run (status included so recovery reads the intent).
        _write_journal_entry(file_id, str(src), str(dest), new_status)
        src_path = Path(entry["current_path"])
        if not src_path.exists():
            if dest.exists():
                # C1 fix: src gone + dest exists → file was moved in a prior run.
                # Skip this entry — do NOT fall through to shutil.move (src is gone; move
                # would raise FileNotFoundError on every crash-recovery replay).
                # The genuine-collision case (dest exists AND src still exists) is handled
                # by the dest-rename loop above, before we reach this check.
                continue  # already moved in prior run — skip
            else:
                print(f"  recovery skip: {src_path} missing and not at dest", file=sys.stderr)
                continue
        try:
            shutil.move(str(src), str(dest))
        except OSError as e:
            print(f"  ERROR moving {src}: {e}", file=sys.stderr)
            _clear_journal_entry(file_id)   # move never happened — drop the intent
            errors += 1
            continue

        conn.execute(
            """UPDATE files SET
               current_path=?, para_category=?, para_subfolder=?,
               vision_desc=?, file_date=COALESCE(?,file_date),
               status=?, processed_at=?
               WHERE id=?""",
            (str(dest), category, sub_rel, vision_desc,
             file_date, new_status, datetime.now().isoformat(), file_id)
        )
        # Commit per file: the move has already happened on disk, so the registry
        # row must be durable immediately. A single end-of-loop commit would lose
        # every move's record if execute crashed mid-batch — leaving files relocated
        # but the registry still pointing at their old paths.
        conn.commit()
        # Registry now durable for this file — clear the journal intent.
        _clear_journal_entry(file_id)
        moved += 1

        # Expand the destination project's date_range to include
        # this file's date. Initialises the period on first approval; widens
        # it (with the effective buffer-days padding — config.json's
        # `period_buffer_days`, else 30) on subsequent approvals. Skipped for
        # action='delete' (file went to Archive/_To Delete) or when no date is known
        # (neither the verdict nor the registry has one).
        if action != "delete" and effective_date:
            project_dir = _find_project_for_destination(subfolder, drive)
            if project_dir is not None:
                try:
                    _expand_date_range(project_dir, effective_date,
                                        buffer_days=_effective_period_buffer_days(drive),
                                        root=drive)
                except Exception as e:
                    print(f"  WARN: could not update date_range for {project_dir.name}: {e}",
                          file=sys.stderr)

    conn.commit()
    conn.close()

    print(f"Execute complete: {moved} moved, {errors} errors.")
    if errors:
        print("  (errors written to stderr)")
    export_csv()


# ---------------------------------------------------------------------------
# duplicates
# ---------------------------------------------------------------------------
