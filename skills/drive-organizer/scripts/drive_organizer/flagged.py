"""drive_organizer.flagged — flagged-file peek/reclassify workflow and its DB-recovery
subcommand. Split from cleanup_reconcile.py (pure structural move, no behavior change)."""
from __future__ import annotations
import json
import sys
from pathlib import Path

from drive_organizer.content_peek import get_db


def cmd_flagged(args):
    """List files marked as flagged so they can be reviewed or reclassified."""
    conn = get_db()
    rows = conn.execute(
        "SELECT id, filename, current_path, original_path FROM files WHERE status='flagged' ORDER BY id"
    ).fetchall()
    conn.close()

    if not rows:
        print("No flagged files.")
        return

    print(f"Flagged files ({len(rows)} total):")
    for r in rows:
        path = r["current_path"] or r["original_path"]
        print(f"  [{r['id']}] {r['filename']}  —  {path}")
    print()
    print("Flagged files are excluded from propose. To reclassify: peek/classify each, add it back into the next proposals_classified.json batch, and review it in the viewer — not executed directly.")
    print("To manually clear a flag: UPDATE files SET status='pending' WHERE id=<N>;")


def cmd_flag_from(args):
    """Deterministic recovery for a failed viewer flag-write: replay the same
    UPDATE files SET status='flagged' WHERE id IN (...) that viewer_propose.py's
    _persist_flagged_status runs on the success path, sourcing IDs from a
    proposals_flagged.json-shaped file (bare JSON array of ints) instead of
    hand-typed SQL. See references/subcommands.md 'generate-viewer (submit-response
    handling)' for why the IDs must come from this file rather than being inferred."""
    path = Path(args.path)
    try:
        raw = path.read_text()
    except OSError as e:
        print(f"Error: could not read {path}: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        ids = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"Error: {path} is not valid JSON: {e}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(ids, list) or not all(isinstance(i, int) and not isinstance(i, bool) for i in ids):
        print(f"Error: {path} must be a bare JSON array of integer IDs (e.g. [12,47,88]).", file=sys.stderr)
        sys.exit(1)

    if not ids:
        print("No IDs to flag (empty array) — nothing to do.")
        return

    conn = get_db()
    placeholders = ",".join("?" * len(ids))
    conn.execute(
        f"UPDATE files SET status='flagged' WHERE id IN ({placeholders})",
        ids,
    )
    conn.commit()
    conn.close()
    print(f"{len(ids)} files marked flagged in registry.", flush=True)
