"""drive_organizer.csv_export — split from the original organizer.py (pure structural move, no behavior change)."""
from __future__ import annotations
import json
import sys
from pathlib import Path

from drive_organizer.content_peek import (
    get_db,
)
from drive_organizer import paths_config


def export_csv():
    """Write a human-readable CSV snapshot of the registry."""
    import csv
    conn = get_db()
    rows = conn.execute(
        """SELECT id, filename, current_path, para_subfolder, status,
                  file_date, file_size, vision_desc
           FROM files ORDER BY status, para_subfolder, filename"""
    ).fetchall()
    conn.close()
    # The CSV is a best-effort human-readable MIRROR of the registry — the SQLite DB is
    # the authoritative state. export_csv is called at the tail of every mutation command
    # (scan/execute/duplicates/merge/reconcile/csv-export) AFTER its commit, so a write
    # failure here (file open in Excel, read-only dir, full disk) must NOT abort the caller
    # and lose its completion output — the mutation already durably landed in the DB.
    # Warn and continue; `csv-export` re-mirrors on demand.
    try:
        with open(paths_config.CSV_EXPORT_PATH, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["id", "filename", "current_path", "destination", "status",
                             "file_date", "file_size_bytes", "vision_desc"])
            for r in rows:
                writer.writerow([r["id"], r["filename"], r["current_path"],
                                  r["para_subfolder"] or "", r["status"],
                                  r["file_date"] or "", r["file_size"] or "",
                                  r["vision_desc"] or ""])
    except OSError as e:
        print(f"  WARNING: could not write CSV mirror {paths_config.CSV_EXPORT_PATH} ({e}) — "
              f"the SQLite registry is unaffected; re-run `csv-export` to retry.", file=sys.stderr)
        return
    print(f"Registry exported: {paths_config.CSV_EXPORT_PATH}  ({len(rows)} rows)")


def cmd_csv_export(args):
    export_csv()


# ---------------------------------------------------------------------------
# Rule aggregation + entity metadata (shared data layer for the rules viewer,
# the bootstrap builder, and the learning loop). Walks the whole .tidy-rules.json
# cascade and groups rules by entity (folder name) across the tree, so "Acme"
# in WORK and "Acme" in EDUCATION collapse to one entity with two occurrences.
# ---------------------------------------------------------------------------
