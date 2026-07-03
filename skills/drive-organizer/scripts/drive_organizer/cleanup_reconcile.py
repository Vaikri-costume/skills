"""drive_organizer.cleanup_reconcile — split from the original organizer.py (pure structural move, no behavior change)."""
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
    PARA_ROOTS,
    _atomic_write,
    _has_rules,
    _is_external,
    _load_templates,
    _read_user_config,
)
from drive_organizer.content_peek import (
    _cloud_platform_note,
    get_db,
)
from drive_organizer.csv_export import (
    export_csv,
)


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


# ---------------------------------------------------------------------------
# flagged
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------

# The five groupings are the DEFAULT, not a hard limit. The active area set is
# data-driven (see _active_groupings): a user may have more, fewer, or differently
# named top-level groupings, declared via templates Q1_groupings or config "areas".
DEFAULT_GROUPINGS = {"ENTERTAINMENT", "PERSONAL", "WORK", "EDUCATION", "RESOURCES"}


def _active_groupings() -> set:
    """The active set of top-level grouping (area) names, ALL-CAPS, derived in order:
      1. config.json "areas": [...]  (per-drive override — authoritative if present)
      2. merged templates' "Q1_groupings" list (shipped skeleton ⊕ user override)
      3. DEFAULT_GROUPINGS (the shipped five) as a last-resort fallback
    Not independently cached — groupings are derived from _load_templates(), which
    carries its own mtime-keyed cache. Caching groupings separately would leave a
    stale window whenever paths_config._TEMPLATES_CACHE is repopulated (e.g. after a live save
    invalidates it), so groupings are derived on every call at negligible cost."""

    def _name(entry):
        # Q1_groupings entries (and config "areas") may be plain strings or dicts
        # carrying a "name" key (the templates skeleton uses the dict form).
        if isinstance(entry, dict):
            return entry.get("name")
        return entry

    areas = None
    cfg = _read_user_config()
    if isinstance(cfg.get("areas"), list) and cfg["areas"]:
        areas = cfg["areas"]
    if areas is None:
        q1 = _load_templates().get("Q1_groupings")
        if isinstance(q1, list) and q1:
            areas = q1
    if areas is None:
        areas = DEFAULT_GROUPINGS
    names = {str(_name(a)).upper() for a in areas if _name(a)}
    return names or {g.upper() for g in DEFAULT_GROUPINGS}


def _para_category(sub_rel: str, groupings=None) -> str:
    """The PARA category for a destination subfolder: its first path segment if that is
    an active grouping, else '_Inbox'. This is the SINGLE authoritative home for the
    projection — execute and crash-recovery both call it, and the verdict contract omits
    para_category entirely so the backend always derives it here. (The viewer's client-side
    `inferCategory` is NOT a mirror: it takes the raw first segment with no grouping check,
    and is display-only — its value is never sent back or persisted, so the two need not
    and do not match for legacy-flat paths.)
    `groupings` should be pre-loaded by the caller (e.g. cmd_execute calls _active_groupings()
    once at the top and passes it here) to avoid re-reading config.json on every file."""
    if groupings is None:
        groupings = _active_groupings()
    first_seg = sub_rel.split("/")[0] if sub_rel else ""
    # Normalise case before the membership check: groupings are stored canonical ALL-CAPS
    # (_active_groupings upper-cases them), but a destination derived from an on-disk path
    # (e.g. reconcile's Path.relative_to) can carry a miscased segment like 'Personal/'.
    # Compare upper-cased and return the canonical grouping so a miscased folder projects
    # to its real category instead of falling to '_Inbox' (which caused a reconcile re-flag loop).
    return first_seg.upper() if first_seg.upper() in groupings else "_Inbox"


def _ensure_in_suffix(desc: str, leaf: str) -> str:
    """Ensure a rule description carries the required ' in <leaf>' suffix (the
    self-describing-sentence convention; see SKILL.md "Description format"). The SINGLE
    home for the append — every site that writes a rule description calls this, so the
    suffix convention can never drift between writers."""
    if desc and not desc.endswith(f" in {leaf}"):
        return f"{desc} in {leaf}"
    return desc


def _normalize_grouping(para: str) -> str:
    """Force a destination's top-level grouping segment to its canonical ALL-CAPS
    form, so a viewer edit like 'Personal/PERSONAL Financial' lands in
    'PERSONAL/PERSONAL Financial'. Only the first path segment is touched; deeper
    names keep their case. (reconcile remains the safety net for legacy miscased
    folders already on disk.)"""
    if not para:
        return para
    parts = para.split("/")
    if parts[0].upper() in _active_groupings():
        parts[0] = parts[0].upper()
    return "/".join(parts)


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


# ---------------------------------------------------------------------------
# csv-export
# ---------------------------------------------------------------------------
