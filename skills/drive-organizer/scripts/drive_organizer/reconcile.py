"""drive_organizer.reconcile — structure-drift detection/repair. Split from
cleanup_reconcile.py (pure structural move, no behavior change)."""
from __future__ import annotations
import json
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

from drive_organizer import paths_config
from drive_organizer.paths_config import (
    _atomic_write,
    _has_rules,
    _is_external,
)
from drive_organizer.routing import _active_groupings, _para_category
from drive_organizer.content_peek import get_db
from drive_organizer.csv_export import export_csv


def _reconcile_known_roots() -> set:
    """Root-level folder names reconcile treats as expected (not 'mangled'): the
    active groupings plus the special staging/system folders."""
    return _active_groupings() | {"_Inbox", "Archive", ".organizer"}


def _emit_organize_yaml(root: Path):
    """Generate an `organize` YAML (hand-emitted — no PyYAML dependency) from the
    .tidy-rules.json cascade. This is the synced verification artifact: a file
    whose NAME contains a destination folder's distinctive tokens should live in
    that folder. Returns (yaml_text, structural_rule_count, semantic_only_count).
    Rules whose folderName yields no usable token are semantic-only (organize
    can't verify them) and are skipped + counted."""
    blocks, semantic_only = [], 0
    for rules_file in sorted(Path(root).rglob(".tidy-rules.json")):
        parent = rules_file.parent
        try:
            data = json.loads(rules_file.read_text(encoding="utf-8"))
        except Exception:
            continue
        rule_list = data.get("rules", []) if isinstance(data, dict) else data
        if not isinstance(rule_list, list):
            continue
        for r in rule_list:
            folder = (r or {}).get("folderName")
            if not folder:
                continue
            tokens = [t for t in re.split(r"[^A-Za-z0-9]+", folder) if len(t) >= 4]
            if not tokens:
                semantic_only += 1
                continue
            dest = parent / folder
            toks = ", ".join(json.dumps(t) for t in tokens)
            blocks.append(
                f"  - name: {json.dumps(parent.name + ' -> ' + folder)}\n"
                f"    locations: {json.dumps(str(parent))}\n"
                f"    subfolders: true\n"
                f"    filters:\n"
                f"      - name:\n"
                f"          contains: [{toks}]\n"
                f"          case_sensitive: false\n"
                f"    actions:\n"
                f"      - move: {json.dumps(str(dest) + '/')}\n"
            )
    text = ("rules:\n" + "".join(blocks)) if blocks else "rules: []\n"
    return text, len(blocks), semantic_only


def _relocate_suggestion(fix_from: str, root: Path) -> str:
    """Heuristic *suggestion* (never a decision) for a file that isn't where the
    registry expects it: if it now sits inside a proper grouping folder (not
    _Inbox, not loose at the root), the move was probably intentional -> 'accept'
    the new location; if it's loose at the root or in _Inbox, probably accidental
    -> 'restore' it. The user always confirms; intent is never auto-resolved."""
    try:
        rel = Path(fix_from).resolve().relative_to(Path(root).resolve())
    except Exception:
        return "restore"
    parts = rel.parts
    if len(parts) >= 2 and parts[0] in _active_groupings() and "_Inbox" not in parts:
        return "accept"
    return "restore"


def cmd_reconcile(args):
    """Detect drift between the intended structure and the actual database + folder
    tree. Dry-run report by default. Intent is never guessed: relocated/misplaced
    files are reported with a restore-vs-accept *suggestion*, and the user decides
    per file via --restore ID (move back to recorded home) or --accept ID (keep it
    where it is, update the registry). --prune ID drops a confirmed-deleted row.
    --apply is a bulk 'restore all misplaced' convenience for when every move was
    accidental. Mangled folders are always report-only."""
    from drive_organizer.entities_rules import _locked_atomic_names, _should_prune_subdir
    root = Path(paths_config._EFFECTIVE_ROOT)
    now = datetime.now().isoformat()

    # At most one per-file decision flag may be supplied at a time (each acts on one
    # report entry; combining them is almost certainly a mistake).
    _supplied = [a for a in ("restore", "accept", "prune") if getattr(args, a, None) is not None]
    if len(_supplied) > 1:
        sys.exit("Supply at most one of --restore / --accept / --prune at a time "
                 f"(got: {', '.join('--' + a for a in _supplied)}).")

    # Per-file decision mode — driven from the prior dry-run's reconcile-report.json.
    for _act in ("restore", "accept", "prune"):
        _id = getattr(args, _act, None)
        if _id is None:
            continue
        report_path = root / ".organizer" / "reconcile-report.json"
        if not report_path.exists():
            sys.exit("No reconcile report yet — run `reconcile` (dry-run) first, then apply per-file decisions.")
        rep = json.loads(report_path.read_text(encoding="utf-8"))
        conn = get_db()
        if _act == "prune":
            entry = next((b for b in rep.get("bad_registry_rows", []) if b.get("id") == _id), None)
            if not entry:
                conn.close(); sys.exit(f"id {_id} is not a reported missing/bad row — re-run reconcile.")
            conn.execute("UPDATE files SET status='deleted', processed_at=? WHERE id=?", (now, _id))
            conn.commit(); conn.close(); export_csv()
            print(f"Pruned id {_id} (registry row marked deleted): {entry.get('filename')}")
            return
        entry = next((m for m in rep.get("misplaced_files", []) if m.get("id") == _id), None)
        if not entry:
            conn.close(); sys.exit(f"id {_id} is not a reported misplaced file — re-run reconcile.")
        # Re-query the live registry row and verify it still matches the snapshot the
        # report was computed from. If the row changed since the dry-run (path/para
        # edited, file re-scanned), the report is stale — skip and tell the user to
        # re-run reconcile rather than acting on outdated data.
        # SINGLE-USER ASSUMPTION (WHY this stale-check + the move/UPDATE below are NOT wrapped
        # in one BEGIN IMMEDIATE transaction): this is a single-user, single-process CLI — no
        # concurrent writer can slip a registry write between this check and the move+UPDATE.
        # The stale-check guards against a STALE REPORT (the user edited/re-scanned between a
        # dry-run and this apply), not against a concurrent transaction. If this ever becomes
        # multi-process, wrap check+move+UPDATE in BEGIN IMMEDIATE to close the interleave window.
        live = conn.execute(
            "SELECT current_path, para_subfolder FROM files WHERE id=?", (_id,)).fetchone()
        if live is None:
            conn.close(); sys.exit(f"id {_id} no longer exists in the registry — re-run reconcile.")
        live_cp = live["current_path"] or ""
        live_para = live["para_subfolder"] or ""
        if (live_cp != (entry.get("row_current_path") or "") or
                live_para != (entry.get("row_para") or "")):
            conn.close()
            sys.exit(f"id {_id}'s registry row changed since the report was generated "
                     f"(current_path/para no longer match) — re-run reconcile, then decide.")
        fix_from = Path(entry["fix_from"]); fix_to = Path(entry["fix_to"])
        if _act == "restore":
            if not fix_from.exists():
                conn.close(); sys.exit(f"file is no longer at {fix_from} — re-run reconcile.")
            if fix_to.exists():
                conn.close(); sys.exit(f"destination already exists: {fix_to}")
            fix_to.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(fix_from), str(fix_to))
            # Re-derive para_subfolder (+ para_category projection) from the restored
            # parent so the `para_subfolder == parent(current_path)` invariant holds and
            # the file isn't re-flagged as misplaced on the next reconcile run.
            try:
                restored_para = str(fix_to.resolve().parent.relative_to(root.resolve()))
            except Exception:
                restored_para = ""
            if restored_para == ".":
                restored_para = ""
            conn.execute(
                "UPDATE files SET current_path=?, para_subfolder=?, para_category=?, "
                "processed_at=? WHERE id=?",
                (str(fix_to), restored_para, _para_category(restored_para), now, _id))
            conn.commit(); conn.close(); export_csv()
            print(f"Restored id {_id} -> {fix_to}")
            return
        # accept: fall-through after prune and restore both returned early above.
        # Governs only _act=="accept". Keep the file where it is; update the registry.
        actual = entry["fix_from"]
        resolve_error = False
        try:
            new_para = str(Path(actual).resolve().parent.relative_to(root.resolve()))
        except Exception:
            new_para = ""
            resolve_error = True
        if new_para == ".":
            new_para = ""   # file sits directly at root — no subfolder
        # Validate the recomputed destination's FIRST segment is an active grouping. A
        # file found in Archive/.git/etc. is outside the taxonomy: recording such a path
        # as 'organized' causes a re-flag loop every run. Send those to 'pending' instead.
        first_seg = new_para.split("/")[0] if new_para else ""
        in_tree = bool(new_para) and first_seg in _active_groupings()
        if resolve_error:
            # A genuine resolve failure (couldn't compute the path) is NOT the same as a
            # correctly-placed file outside the tree — don't silently downgrade; bail.
            conn.close()
            sys.exit(f"could not resolve id {_id}'s location relative to the root "
                     f"({actual}) — re-run reconcile.")
        # An 'organized' row with an empty/non-grouping para self-flags forever
        # (reconcile reports it every run). Only mark 'organized' when the file truly
        # lands inside an active grouping; otherwise 'pending' for reclassification.
        new_status = "organized" if in_tree else "pending"
        # Re-derive para_category from the new para too — it is a pure projection of
        # para_subfolder for EVERY row (see the projection invariant), so an accept that
        # moves the file must update both or the row's category goes stale.
        conn.execute(
            "UPDATE files SET current_path=?, para_subfolder=?, para_category=?, status=?, processed_at=? WHERE id=?",
            (actual, new_para, _para_category(new_para), new_status, now, _id))
        conn.commit(); conn.close(); export_csv()
        note = "" if in_tree else "  (outside the active groupings → pending, not organized)"
        print(f"Accepted id {_id}'s location: {actual}  (registry updated → status={new_status}; file not moved){note}")
        return

    apply = getattr(args, "apply", False)
    conn = get_db()
    report = {"misplaced_files": [], "bad_registry_rows": [], "mangled_folders": [], "applied": []}

    # Ghost pending rows — status='pending' but journal was cleared (crash-recovery cleared the
    # journal without marking the row missing, old builds).  These would reappear in the next
    # propose batch and be re-classified, masking data-loss events.
    # NOTE: the journal is the JSON sidecar .move-journal.json — NOT a SQL table.  Load it
    # in Python and build an id set; do NOT query `move_journal` (no such table exists).
    _journal_path = root / ".organizer" / ".move-journal.json"
    try:
        _journal_data = json.loads(_journal_path.read_text(encoding="utf-8"))
        _journal_ids = set(_journal_data.keys()) if isinstance(_journal_data, dict) else set()
    except (OSError, json.JSONDecodeError, ValueError):
        _journal_ids = set()  # absent / unparseable — treat as empty (no journal entries)
    _pending_rows = conn.execute(
        "SELECT id, filename, current_path FROM files "
        "WHERE status = 'pending' AND current_path IS NOT NULL AND current_path != ''"
    ).fetchall()
    for row in [r for r in _pending_rows if str(r["id"]) not in _journal_ids]:
        cp_check = row["current_path"] if "current_path" in row.keys() else None
        if cp_check and not Path(cp_check).exists():
            report["bad_registry_rows"].append(
                {"id": row["id"], "issue": "ghost_pending_no_journal",
                 "filename": row["filename"],
                 "note": "status=pending but move_journal entry was cleared and file is missing — "
                         "mark as missing or reconcile manually"})

    # Reappeared-missing rows — status='missing' (execute's crash-recovery path marked the
    # row missing because neither src nor dest existed at the time) but a file now exists at
    # the row's last-known current_path. Detect-only (consistent with dry-run-then-confirm):
    # surface it so the user can restore it into the pending/organized lifecycle via
    # --accept ID, rather than leaving it permanently unreachable at status='missing'.
    for row in conn.execute(
        "SELECT id, filename, current_path FROM files WHERE status = 'missing'"
    ):
        cp = row["current_path"] if "current_path" in row.keys() else None
        if cp and Path(cp).exists():
            report["bad_registry_rows"].append(
                {"id": row["id"], "issue": "missing_row_reappeared", "current_path": cp,
                 "filename": row["filename"],
                 "note": "row is status='missing' but a file now exists at its recorded "
                         "current_path — run --accept ID to bring it back into the "
                         "pending/organized lifecycle"})

    # Misplaced files + bad registry rows (registry vs disk)
    missing_rows = []
    for row in conn.execute(
        "SELECT id, current_path, para_subfolder, status, filename, file_size FROM files "
        "WHERE status IN ('organized','duplicate')"
    ):
        cp = row["current_path"]
        if not cp:
            report["bad_registry_rows"].append(
                {"id": row["id"], "issue": "no_current_path", "filename": row["filename"]})
            continue
        if not Path(cp).exists():
            missing_rows.append(row)          # resolved below: moved away, or genuinely gone?
            continue
        para = (row["para_subfolder"] or "").strip().strip("/")
        if row["status"] == "organized" and not para:
            report["bad_registry_rows"].append(
                {"id": row["id"], "issue": "organized_without_destination", "current_path": cp})
            continue
        if not para:
            continue  # a duplicate may legitimately lack para_subfolder
        expected_dir = os.path.normpath(str(root / para))
        actual_dir = os.path.normpath(str(Path(cp).parent))
        if expected_dir != actual_dir:
            report["misplaced_files"].append(
                {"id": row["id"], "filename": Path(cp).name, "issue": "para_mismatch",
                 "fix_from": cp, "fix_to": os.path.join(expected_dir, Path(cp).name),
                 "para_subfolder": para, "suggestion": _relocate_suggestion(cp, root),
                 # snapshot of the registry row this entry was computed from — used to
                 # detect a stale report before acting on it.
                 "row_current_path": cp, "row_para": row["para_subfolder"] or ""})

    # Resolve rows whose recorded file is missing: relocated outside the tool (the common
    # "structure got ruined" case — a file dragged elsewhere in Finder), or genuinely gone?
    if missing_rows:
        # Build a name->paths index, but PRUNE external/atomic/dot/staging subtrees while
        # walking (mirror _coverage_gaps' os.walk approach) so the resolver can never pull
        # a file out of a shared/external folder and propose relocating a tool-managed row
        # into it. rglob would descend into node_modules/.git/venvs/shared mounts.
        locked_atomic = _locked_atomic_names(root)
        index = {}
        for cur, subdirs, files in os.walk(root):
            cp_dir = Path(cur)
            # Shared pruning predicate (same one _coverage_gaps + _bootstrap_candidates use)
            # so all walk sites stay in sync — no inline re-implementation to drift.
            subdirs[:] = [d for d in subdirs
                          if not _should_prune_subdir(d, cp_dir, locked_atomic, root)]
            for fn in files:
                index.setdefault(fn, []).append(cp_dir / fn)
        for row in missing_rows:
            cp = row["current_path"]
            base = Path(cp).name
            cands = [p for p in index.get(base, [])
                     if os.path.normpath(str(p)) != os.path.normpath(cp)]
            if row["file_size"]:                       # disambiguate same-named files by size
                sized = []
                for p in cands:
                    try:
                        if p.stat().st_size == row["file_size"]:
                            sized.append(p)
                    except OSError:
                        continue   # un-stattable (permission-denied / cloud placeholder) — skip
                if sized:
                    cands = sized
            if cands:
                report["misplaced_files"].append(
                    {"id": row["id"], "filename": base, "issue": "relocated_outside_tool",
                     "fix_from": str(cands[0]), "fix_to": cp,
                     "suggestion": _relocate_suggestion(str(cands[0]), root),
                     # snapshot of the registry row — fix_to IS the recorded current_path.
                     "row_current_path": cp, "row_para": row["para_subfolder"] or ""})
            else:
                report["bad_registry_rows"].append(
                    {"id": row["id"], "issue": "missing_on_disk", "current_path": cp,
                     "filename": row["filename"]})

    # Mangled folder tree — root-level folders that break the five-grouping invariant
    for child in sorted(p for p in root.iterdir() if p.is_dir()):
        name = child.name
        if name in _reconcile_known_roots():
            continue
        if _is_external(child):
            continue
        if name.upper() in _active_groupings() and name not in _active_groupings():
            report["mangled_folders"].append(
                {"folder": name, "issue": "miscased_grouping", "should_be": name.upper()})
        elif _has_rules(child, root):
            report["mangled_folders"].append(
                {"folder": name, "issue": "rule_folder_at_root",
                 "note": "legacy flat layout — has rules but sits at root, not under a grouping"})
        else:
            report["mangled_folders"].append(
                {"folder": name, "issue": "unexpected_root_folder",
                 "note": "no rules and not a grouping/staging folder"})

    # Generate the synced organize YAML artifact (for a manual keyword-level cross-check)
    yaml_text, struct_rules, semantic_only = _emit_organize_yaml(root)
    yaml_path = root / ".organizer" / "organize-rules.yaml"
    yaml_path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(yaml_path, yaml_text)

    # Apply: move each misplaced file (para-mismatch or relocated) into its correct place
    if apply:
        for m in report["misplaced_files"]:
            src = Path(m["fix_from"])
            dest = Path(m["fix_to"])
            if not src.exists():
                m["apply_result"] = "skipped — source no longer present"
                continue
            if dest.exists():
                m["apply_result"] = "skipped — destination already exists"
                continue
            try:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dest))
                # Re-derive para_subfolder (and its para_category projection) from the
                # file's NEW parent so the reconcile invariant
                # `para_subfolder == parent(current_path)` holds after --apply. Updating
                # current_path alone would leave para_subfolder stale, so the very next
                # reconcile run would re-flag this same file as misplaced on every run.
                try:
                    new_para = str(dest.resolve().parent.relative_to(root.resolve()))
                except Exception:
                    new_para = ""
                if new_para == ".":
                    new_para = ""
                conn.execute(
                    "UPDATE files SET current_path=?, para_subfolder=?, para_category=?, "
                    "processed_at=? WHERE id=?",
                    (str(dest), new_para, _para_category(new_para),
                     datetime.now().isoformat(), m["id"]))
                m["apply_result"] = f"moved -> {dest}"
                report["applied"].append(m["id"])
            except Exception as e:
                m["apply_result"] = f"error: {e}"
        conn.commit()
        export_csv()
    conn.close()

    report_path = root / ".organizer" / "reconcile-report.json"
    _atomic_write(report_path, json.dumps(report, indent=2))
    n_mis, n_bad, n_man = (len(report["misplaced_files"]), len(report["bad_registry_rows"]),
                           len(report["mangled_folders"]))
    print(f"reconcile — {'APPLIED fixes' if apply else 'DRY-RUN (report only)'}")
    print(f"  misplaced files (not at their recorded destination): {n_mis}")
    print(f"  bad registry rows (missing on disk / no destination): {n_bad}")
    print(f"  mangled root folders: {n_man}")
    if apply:
        print(f"  files moved into place: {len(report['applied'])}")
    print(f"  organize YAML (synced): {yaml_path}  [{struct_rules} structural rules, {semantic_only} semantic-only]")
    print(f"      keyword-level cross-check:  organize sim \"{yaml_path}\"")
    print(f"  full report: {report_path}")
    if not apply and report["misplaced_files"]:
        print("  → resolve these registry-backed files FIRST (per file — intent is never guessed):")
        for m in report["misplaced_files"]:
            sug = m.get("suggestion", "restore")
            print(f"      id {m['id']}  {m['filename']}  [{m['issue']}]  suggest: {sug}")
            print(f"         restore (back to recorded home):  reconcile --restore {m['id']}")
            print(f"         accept  (keep where it is now):    reconcile --accept {m['id']}")
        print("    then address bad registry rows (reconcile --prune ID for confirmed-deleted files)")
        print("    and finally the mangled / unregistered folders below (manual judgment).")
    elif not apply and (n_bad or n_man):
        print("  → no misplaced files; review bad registry rows (reconcile --prune ID to drop confirmed-deleted)")
        print("    and the mangled / unregistered folders (manual judgment).")
