"""drive_organizer.cleanup — empty-folder removal + disk-space eviction.
Split from cleanup_reconcile.py (pure structural move, no behavior change)."""
from __future__ import annotations
import os
import sys
from pathlib import Path

from drive_organizer import paths_config
from drive_organizer.paths_config import PARA_ROOTS
from drive_organizer.routing import _active_groupings


def _evict_command(path: Path):
    """Per-OS command (argv list) to dehydrate a folder's materialised copies to online-only,
    freeing local disk while the cloud copy stays. Returns None where the platform has no
    supported command (Linux/other). macOS-verified intent; Windows best-effort/unverified."""
    if sys.platform == "darwin":
        # brctl evicts File-Provider/iCloud-backed items (verified path). OneDrive-on-macOS has
        # NO eviction CLI — brctl returns non-zero for it, so _run_eviction falls back to the
        # manual recipe. See references/subcommands.md 'cleanup'.
        return ["brctl", "evict", str(path)]
    if sys.platform == "win32":
        # OneDrive Files-On-Demand: unpin (+U) and clear the always-keep pin (-P), recursively.
        return ["attrib", "+U", "-P", str(path), "/s", "/d"]
    return None  # Linux / other: no standard eviction command


# The manual per-app eviction recipes live in references/subcommands.md 'cleanup' (single home);
# the backend only points there rather than re-listing them (avoids drift).
_EVICT_FALLBACK = ("free disk via your sync app's 'free up space' / 'online only' option "
                   "(per-app recipes in references/subcommands.md 'cleanup')")


def _run_eviction(drive: Path) -> None:
    """`cleanup --evict`: dehydrate the organised top-level grouping folders to online-only to
    free local disk (cloud copies remain, re-downloadable). Staging (_Inbox/, Archive/) is never
    evicted. Best-effort and non-destructive of data: on an unsupported platform, a missing tool,
    or a per-folder failure it degrades to the manual recipe instead of erroring."""
    import subprocess
    grouping_names = {g.upper() for g in _active_groupings()}
    targets = sorted(
        (d for d in drive.iterdir()
         if d.is_dir() and not d.name.startswith(".")
         and d.name not in PARA_ROOTS and d.name.upper() in grouping_names),
        key=lambda p: p.name,
    )
    if not targets:
        print("Evict: no organised grouping folders to evict.")
        return
    argv0 = _evict_command(targets[0])
    if argv0 is None:
        print(f"Evict: no automated eviction command for {sys.platform} — {_EVICT_FALLBACK}.")
        return
    ok, failed, tool_missing = [], [], False
    for t in targets:
        try:
            r = subprocess.run(_evict_command(t), capture_output=True, text=True, timeout=300)
            if r.returncode == 0:
                ok.append(t.name)
            else:
                last = (r.stderr or "").strip().splitlines()
                failed.append((t.name, r.returncode, last[-1] if last else ""))
        except FileNotFoundError:
            # The tool is missing for every remaining folder — stop trying, but still report
            # what already evicted/failed below (don't drop partial progress on early return).
            tool_missing = True
            break
        except Exception as e:
            failed.append((t.name, -1, str(e)[:160]))
    if ok:
        print(f"Evicted {len(ok)} grouping folder(s) to online-only: {', '.join(ok)}.")
    for n, rc, err in failed:
        print(f"  evict failed: {n} (rc={rc}) {err}", file=sys.stderr)
    if tool_missing:
        print(f"Evict: '{argv0[0]}' not found on PATH — {_EVICT_FALLBACK}.", file=sys.stderr)
    elif failed:
        print(f"Some folders did not evict — {_EVICT_FALLBACK}.", file=sys.stderr)


def cmd_cleanup(args):
    drive = Path(args.path).expanduser() if args.path else paths_config._EFFECTIVE_ROOT
    if not drive.exists():
        sys.exit(f"Error: root path not found: {drive}")

    removed = 0

    # Staging subdirs inside Archive — they hold active data and must survive empty
    # batches. Hoisted out of the walk loop (a constant set literal, not per-iteration).
    _ARCHIVE_STAGING = {"_To Delete", "_Duplicates", "_Merged-Originals"}

    # Walk bottom-up so children are processed before parents
    for root, dirs, files in os.walk(drive, topdown=False):
        root_path = Path(root)

        # Skip the root itself
        if root_path == drive:
            continue

        # Skip direct children of root that are PARA roots
        if root_path.parent == drive and root_path.name in PARA_ROOTS:
            continue

        # Skip staging subdirs inside Archive
        if root_path.parent == drive / "Archive" and root_path.name in _ARCHIVE_STAGING:
            continue

        try:
            root_path.rmdir()  # succeeds only if empty
            removed += 1
        except OSError:
            pass  # not empty, or permission error — skip silently

    print(f"Cleanup complete: {removed} empty folders removed.")

    if getattr(args, "evict", False):
        _run_eviction(drive)
