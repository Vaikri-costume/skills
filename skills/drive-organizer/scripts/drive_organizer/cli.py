"""drive_organizer.cli — split from the original organizer.py (pure structural move, no behavior change)."""
from __future__ import annotations
import argparse
import shutil
import sys
from pathlib import Path

from drive_organizer import paths_config
from drive_organizer.paths_config import (
    DEFAULT_ONEDRIVE,
    _default_root,
    _finalize_runtime_paths,
    _print_optional_deps_notice,
    _save_config_root,
)
from drive_organizer.classify_propose import (
    cmd_exif,
    cmd_merge_category,
    cmd_propose,
)
from drive_organizer.scan import (
    cmd_download_batch,
    cmd_scan,
)
from drive_organizer.execute import (
    cmd_execute,
)
from drive_organizer.duplicates_variants import (
    cmd_duplicates,
    cmd_merge,
    cmd_variants,
)
from drive_organizer.viewer_propose import (
    cmd_generate_viewer,
)
from drive_organizer.cleanup_reconcile import (
    cmd_cleanup,
    cmd_flagged,
    cmd_reconcile,
    cmd_status,
)
from drive_organizer.csv_export import (
    cmd_csv_export,
)
from drive_organizer.entities_rules import (
    cmd_rules,
)
from drive_organizer.rules_viewer import (
    cmd_inbox_list,
    cmd_rules_viewer,
)
from drive_organizer.bootstrap import (
    cmd_bootstrap,
)
from drive_organizer import paths_config
from drive_organizer.paths_config import (
    cmd_templates,
)


def main():
    parser = argparse.ArgumentParser(description="Folder Organizer backend")
    parser.add_argument(
        "--root", default=None, metavar="PATH",
        help="Root folder to organise; registry lives at <root>/.organizer/ "
             "(default: this OS's OneDrive sync folder, resolved by _default_root(); see "
             "README for the per-OS paths. Pass any drive or folder path to override)"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_dl = sub.add_parser("download-batch")
    p_dl.add_argument("path", nargs="?", help="root path")
    p_dl.add_argument("--limit-gb", default=None,
                      help="Max GB to queue (default: config.json's scan_gb_limit, else 20)")

    p_scan = sub.add_parser("scan")
    p_scan.add_argument("path", nargs="?")
    p_scan.add_argument("--limit", type=int, default=None,
                        help="Max files per scan batch (default: config.json's scan_file_limit, else 250)")
    p_scan.add_argument("--limit-gb", default=None,
                        help="Max cumulative GB per batch (default: config.json's scan_gb_limit, else 20)")

    p_propose = sub.add_parser("propose")
    p_propose.add_argument("--limit", type=int, default=None,
                           help="Max pending files to propose (default: config.json's scan_file_limit, else 250)")
    p_propose.add_argument("--no-auto-classify", action="store_true", dest="no_auto_classify",
                           help="Disable the W1 deterministic fast-path; send every file to classification")
    p_propose.add_argument("--auto-classify", action="store_true", dest="auto_classify",
                           help="Force the W1 fast-path on for this run (overrides config)")
    p_propose.add_argument("--no-vision", action="store_true", dest="no_vision",
                           help="W1b cost toggle: never open images for vision; route them by name/path/rule only")
    p_propose.add_argument("--no-peek", action="store_true", dest="no_peek",
                           help="Model-agnostic: the running model cannot open file CONTENTS; agents classify from the pre-extracted content_peek + name/path only, never opening files")
    p_propose.add_argument("--skip-types", dest="skip_types", metavar="EXT,EXT",
                           help="W1b cost toggle: comma-separated extensions the classifier never opens (e.g. .mov,.raw)")
    p_propose.add_argument("--skip-over-mb", dest="skip_over_mb", type=float, metavar="N",
                           help="W1b cost toggle: files larger than N MB are never opened (routed by name/path/rule only)")
    p_propose.add_argument("--auto-approve", action="store_true", dest="auto_approve",
                           help="W5: mark ALL W1 auto-routed files auto_approved (orchestrator may skip the viewer; does not apply to classifier verdicts)")

    p_execute = sub.add_parser("execute")
    p_execute.add_argument("--approved", required=True)

    p_dupes = sub.add_parser("duplicates")
    p_dupes.add_argument("--colocate", metavar="ID", type=int,
                         help="Move this duplicate beside its group's keeper as <keeper-stem>_dupN; mark status=duplicate")
    p_dupes.add_argument("--archive", metavar="ID", type=int,
                         help="Deprecated alias for --colocate (no longer archives to Archive/_Duplicates/)")
    p_reconcile = sub.add_parser("reconcile",
                                 help="Detect drift (misplaced files, bad registry rows, mangled folders); --apply fixes misplaced files")
    p_reconcile.add_argument("--apply", action="store_true",
                             help="Bulk: move ALL misplaced files back to their recorded home (use only when every move was accidental)")
    p_reconcile.add_argument("--restore", metavar="ID", type=int,
                             help="Per-file: move one reported misplaced file back to its recorded home")
    p_reconcile.add_argument("--accept", metavar="ID", type=int,
                             help="Per-file: accept one file's new location (update the registry; do not move the file)")
    p_reconcile.add_argument("--prune", metavar="ID", type=int,
                             help="Per-file: mark one reported missing/deleted file's registry row as deleted")
    sub.add_parser("variants")
    sub.add_parser("flagged")
    sub.add_parser("status")

    p_merge = sub.add_parser("merge")
    p_merge.add_argument("--group",     required=True)
    p_merge.add_argument("--canonical", required=True)

    p_viewer = sub.add_parser("generate-viewer")
    p_viewer.add_argument("--proposals", required=True, help="Path to proposals JSON file")
    p_viewer.add_argument("--port", type=int, default=5002, help="Local port (default 5002)")
    p_viewer.add_argument("--no-open", action="store_true", dest="no_open",
                          help="Run the localhost server but do not auto-open a browser (headless testing)")
    p_viewer.add_argument("--static", action="store_true",
                          help="Cowork-reachable fallback: write an editable static review file + pre-filled proposals_approved.json instead of starting the localhost server (auto-enabled when a Cowork/headless session is detected)")

    p_cleanup = sub.add_parser("cleanup")
    p_cleanup.add_argument("path", nargs="?", help="root path")
    p_cleanup.add_argument("--evict", action="store_true",
                           help="After removing empty folders, dehydrate the organised grouping folders to online-only to free local disk (cloud copies stay, re-downloadable; staging never evicted). Best-effort per-OS — macOS brctl evict, Windows attrib +U; falls back to the manual recipe.")

    sub.add_parser("csv-export", help="Refresh <root>/.organizer/registry.csv from the SQLite registry")
    sub.add_parser("templates", help="Print merged templates (shipped skeleton + per-user override) as JSON")

    p_exif = sub.add_parser("exif",
                            help="Image metadata (date/camera/dimensions) as JSON for vision-off routing; Pillow-optional, degrades to filename date, never errors")
    p_exif.add_argument("path", help="Path to the image file")

    p_merge_cat = sub.add_parser("merge-category",
                                 help="Add a taxonomy category from a small JSON diff into the per-user templates override (Python owns the merge)")
    p_merge_cat.add_argument("--diff", required=True,
                             help='JSON: {"name": "<subfolder>", "description": "<signal terms> in <name>", "parent": "<optional compound parent>"}')

    sub.add_parser("inbox-list",
                   help="List files currently in _Inbox as JSON (count + records) for the arbiter sweep")

    p_rules = sub.add_parser("rules",
                             help="Aggregate .tidy-rules.json by entity across the tree (clustered summary; --json feeds the viewer)")
    p_rules.add_argument("--json", action="store_true",
                         help="Emit the full aggregation as JSON (consumed by the rules viewer)")

    p_rv = sub.add_parser("rules-viewer",
                          help="Launch the browser rules viewer/editor (clustered cards, CRUD, area mgmt, test-a-file)")
    p_rv.add_argument("--port", type=int, default=5003, help="Local port (default 5003)")
    p_rv.add_argument("--no-open", action="store_true", dest="no_open",
                      help="Do not auto-open a browser (for headless testing)")

    p_bs = sub.add_parser("bootstrap",
                          help="Reverse-engineer rules from an existing tree (atomic units first, then infer unruled folders)")
    p_bs.add_argument("--detect-atomic", action="store_true", dest="detect_atomic",
                      help="List atomic-unit folders to approve+lock first")
    p_bs.add_argument("--lock", metavar="NAMES", help="Comma-separated atomic-unit folder names to lock")
    p_bs.add_argument("--emit", action="store_true", help="Write bootstrap-input.json (default action)")
    p_bs.add_argument("--apply", metavar="FILE", help="Apply approved proposals (rules + entities) from FILE")
    p_bs.add_argument("--mode", choices=["cold-start", "audit"], default="cold-start")
    p_bs.add_argument("--sample", type=int, default=5, help="Files sampled per folder (default 5)")
    p_bs.add_argument("--limit", type=int, default=None,
                      help="Max candidate folders (default: config.json's scan_file_limit, else 250)")
    p_bs.add_argument("--json", action="store_true", help="JSON output (for --detect-atomic)")

    args = parser.parse_args()

    # Derive root: --root flag (saves to config) > saved config > DEFAULT_ONEDRIVE.
    # _finalize_runtime_paths is the single place paths_config.REGISTRY_DB / paths_config.CSV_EXPORT_PATH are set.
    if args.root:
        _root = Path(args.root).expanduser().resolve()
        _save_config_root(_root)
        _finalize_runtime_paths(_root)
    else:
        _finalize_runtime_paths()

    # Auto-migrate from legacy ~/.claude/drive-organizer/ location (first run only)
    _legacy_db = Path.home() / ".claude" / "drive-organizer" / "registry.db"
    if not paths_config.REGISTRY_DB.exists() and _legacy_db.exists() and paths_config._EFFECTIVE_ROOT == DEFAULT_ONEDRIVE:
        paths_config.REGISTRY_DB.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(_legacy_db), str(paths_config.REGISTRY_DB))
        print(f"Note: registry migrated from {_legacy_db} to {paths_config.REGISTRY_DB}", file=sys.stderr)
        _legacy_csv = _legacy_db.parent / "registry.csv"
        if _legacy_csv.exists() and not paths_config.CSV_EXPORT_PATH.exists():
            shutil.copy2(str(_legacy_csv), str(paths_config.CSV_EXPORT_PATH))

    # Startup probe: one-line stderr notice if any optional library is absent (silent
    # when all present). Skipped for `exif`, which emits its own Pillow-specific note.
    if args.command != "exif":
        _print_optional_deps_notice()

    dispatch = {
        "download-batch":  cmd_download_batch,
        "scan":            cmd_scan,
        "propose":         cmd_propose,
        "execute":         cmd_execute,
        "duplicates":      cmd_duplicates,
        "variants":        cmd_variants,
        "flagged":         cmd_flagged,
        "merge":           cmd_merge,
        "status":          cmd_status,
        "generate-viewer":  cmd_generate_viewer,
        "cleanup":          cmd_cleanup,
        "csv-export":       cmd_csv_export,
        "templates":        cmd_templates,
        "exif":             cmd_exif,
        "merge-category":   cmd_merge_category,
        "reconcile":        cmd_reconcile,
        "rules":            cmd_rules,
        "rules-viewer":     cmd_rules_viewer,
        "bootstrap":        cmd_bootstrap,
        "inbox-list":       cmd_inbox_list,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
