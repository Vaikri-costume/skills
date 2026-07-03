"""drive_organizer.status — registry status reporting. Split from cleanup_reconcile.py
(pure structural move, no behavior change)."""
from __future__ import annotations
import sys

from drive_organizer import paths_config
from drive_organizer.content_peek import _cloud_platform_note, get_db


def cmd_status(args):
    conn = get_db()
    rows  = conn.execute(
        "SELECT status, COUNT(*) AS n FROM files GROUP BY status ORDER BY n DESC"
    ).fetchall()
    total   = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
    batches = conn.execute("SELECT COUNT(*) FROM batches").fetchone()[0]
    conn.close()

    print(f"Root:     {paths_config._EFFECTIVE_ROOT}")
    print(f"Registry: {paths_config.REGISTRY_DB}")
    _note = _cloud_platform_note()
    if _note:
        print(_note, file=sys.stderr)
    print(f"Total files: {total}  |  Batches: {batches}")
    print()
    for row in rows:
        print(f"  {row['status']:15s}  {row['n']:6d}")
