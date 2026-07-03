"""drive_organizer.scan — split from the original organizer.py (pure structural move, no behavior change)."""
from __future__ import annotations
import concurrent.futures as _futures
import json
import os
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

from drive_organizer import paths_config
from drive_organizer.paths_config import (
    DOWNLOAD_POLL_INTERVAL,
    IMAGE_EXTS,
    PARA_ROOTS,
    _effective_download_poll_timeout,
    _effective_scan_file_limit,
    _effective_scan_gb_limit,
    _has_rules,
    _is_external,
)
from drive_organizer.content_peek import (
    _cloud_platform_note,
    _is_placeholder,
    extract_photo_date,
    get_db,
    peek_content,
    sha256_of,
    should_skip,
)
from drive_organizer.bootstrap import (
    _atomic_marker,
)
from drive_organizer.paths_config import (
    _atomic_write,
)
from drive_organizer.entities_rules import (
    _locked_atomic_names,
)
from drive_organizer.csv_export import (
    export_csv,
)


def cmd_download_batch(args):
    drive = Path(args.path).expanduser() if args.path else paths_config._EFFECTIVE_ROOT
    # Precedence: explicit --limit-gb > config.json's scan_gb_limit > hardcoded 20.0.
    cap_gb = float(args.limit_gb) if args.limit_gb is not None else _effective_scan_gb_limit(drive)
    cap_bytes = int(cap_gb * 1024 ** 3)

    if not drive.exists():
        sys.exit(f"Error: root path not found: {drive}")

    triggered = 0
    already_local = 0
    skipped = 0
    total_bytes = 0
    at_cap = False

    # Folders scan treats as opaque locked atomic units — don't download files inside
    # them, since scan will ignore those files anyway (wasted bandwidth + cloud egress).
    _locked_atomic = _locked_atomic_names(drive)

    # Skip already-organised files so we don't re-download freed-up content.
    # NB: `with sqlite3.connect(...) as conn` commits but does NOT close the
    # connection — it leaks the handle. Use an explicit try/finally close.
    organized_paths: set[str] = set()
    if paths_config.REGISTRY_DB.exists():
        conn = None
        try:
            conn = sqlite3.connect(str(paths_config.REGISTRY_DB))
            conn.row_factory = sqlite3.Row
            organized_paths = {
                r["current_path"]
                for r in conn.execute(
                    "SELECT current_path FROM files WHERE status='organized'"
                ).fetchall()
            }
        except (sqlite3.DatabaseError, OSError) as e:
            print(f"WARNING: could not read organized_paths from registry "
                  f"({type(e).__name__}: {e}); already-organised files may be "
                  f"re-scanned in this batch.", file=sys.stderr)
        finally:
            if conn is not None:
                conn.close()

    print(f"Scanning for online-only files (cap: {cap_gb:.0f} GB)...")
    print()

    # Two-phase download: folders WITH rules first, folders WITHOUT rules second
    # (matches scan's priority order — rule-bearing folders earn their downloads first).
    for phase in (1, 2):
        if at_cap:
            break

        for root, dirs, files in os.walk(drive):
            if at_cap:
                break
            root_path = Path(root)

            # Never descend external (shared) or atomic-unit folders at any depth —
            # same opacity contract as scan. Pruned first so the top-level hidden
            # filter below operates on the already-cleaned dir list.
            dirs[:] = [d for d in dirs
                       if d not in _locked_atomic
                       and not _atomic_marker(root_path / d, drive)
                       and not _is_external(root_path / d)]

            rel = root_path.relative_to(drive)
            top_level = rel.parts[0] if rel.parts else ""

            if top_level.startswith("."):
                dirs.clear()
                continue

            if not top_level:
                # At the drive root: keep only the top-level folders for THIS phase —
                # phase 1 descends rule-bearing folders, phase 2 the rest.
                dirs[:] = [d for d in dirs
                           if not d.startswith(".")
                           and _has_rules(root_path / d, drive) == (phase == 1)]
                continue

            for fname in sorted(files):
                filepath = root_path / fname
                if should_skip(filepath):
                    continue

                if str(filepath) in organized_paths:
                    skipped += 1
                    continue

                try:
                    fsize = filepath.stat().st_size
                except OSError:
                    skipped += 1
                    continue

                if not _is_placeholder(filepath):
                    # A genuinely-empty local file (fsize==0, not a placeholder) has
                    # nothing to download — it's already local. Either way, nothing
                    # to trigger here.
                    already_local += 1
                    continue

                if fsize == 0:
                    # A placeholder reporting zero logical size has no bytes to pull
                    # down; skip rather than open() a no-op.
                    skipped += 1
                    continue

                if total_bytes + fsize > cap_bytes:
                    print(f"Cap reached ({cap_gb:.0f} GB). Stopping.")
                    at_cap = True
                    break

                # Trigger download by opening the file — OneDrive downloads on first access
                try:
                    with open(filepath, "rb") as f:
                        f.read(1)
                    total_bytes += fsize
                    triggered += 1
                    size_str = (f"{fsize/1024:.0f} KB" if fsize < 1024**2
                                else f"{fsize/1024**2:.1f} MB")
                    print(f"  ↓ {fname}  ({size_str})  "
                          f"[{total_bytes/1024**3:.2f}/{cap_gb:.0f} GB]")
                except OSError as e:
                    print(f"  skip {fname}: {e}", file=sys.stderr)
                    skipped += 1

    print()
    print(f"Download batch triggered:")
    print(f"  Files queued:    {triggered:6d}  ({total_bytes/1024**3:.2f} GB)")
    print(f"  Already local:   {already_local:6d}")
    print(f"  Skipped:         {skipped:6d}")
    if triggered > 0:
        print()
        print("OneDrive is downloading in the background.")
        print("Watch the OneDrive menu-bar icon — when it stops spinning, run:")
        print("  organizer.py scan")


# ---------------------------------------------------------------------------
# scan
# ---------------------------------------------------------------------------

def _learn_dir_vocab(drive: Path, conn: sqlite3.Connection):
    """
    Walk the approved directory tree and register folder names into path_vocab
    by depth. Depth 1 = position 1 (root project/category folders), etc.
    This makes any folder the user creates manually visible to classification
    on the next scan, not only folders that went through the viewer.
    """
    for root, dirs, _ in os.walk(drive):
        root_path = Path(root)
        try:
            rel = root_path.relative_to(drive)
        except ValueError:
            continue
        parts = rel.parts
        depth = len(parts)
        if depth == 0:
            continue
        # Skip hidden top-level dirs
        if parts[0].startswith("."):
            dirs.clear()
            continue
        # Only register up to depth 3 (matches viewer's 3-segment path builder)
        if depth > 3:
            dirs.clear()
            continue
        segment = parts[-1]
        if not segment or segment.startswith("."):
            continue
        conn.execute(
            """INSERT INTO path_vocab (segment, position, use_count) VALUES (?,?,1)
               ON CONFLICT(segment, position) DO UPDATE SET use_count = use_count + 1""",
            (segment, depth),
        )
    conn.commit()


def _seed_vocab_from_rules(root: Path, conn: sqlite3.Connection):
    """Seed path_vocab position-1 entries from folderName values in root .tidy-rules.json."""
    rules_file = root / ".tidy-rules.json"
    if not rules_file.exists():
        return
    try:
        data = json.loads(rules_file.read_text(encoding="utf-8"))
        for rule in data.get("rules", []):
            top = rule.get("folderName", "").split("/")[0].strip()
            if top:
                conn.execute(
                    """INSERT INTO path_vocab (segment, position, use_count) VALUES (?,1,1)
                       ON CONFLICT(segment, position) DO UPDATE SET use_count = use_count + 1""",
                    (top,)
                )
        conn.commit()
    except (json.JSONDecodeError, OSError, sqlite3.DatabaseError) as e:
        print(f"WARNING: _seed_vocab_from_rules: could not seed path_vocab from "
              f"{rules_file} ({type(e).__name__}: {e}); proposal-path autocomplete "
              f"may be incomplete.", file=sys.stderr)


_SCAN_SKIP_STATE_NAME = ".scan_skip_state.json"


def _scan_skip_state_path(drive: Path) -> Path:
    return drive / ".organizer" / _SCAN_SKIP_STATE_NAME


def _check_and_update_skip_guard(drive: Path, skipped: int, new_pending: int) -> bool:
    """Compare this run's `skipped` count against the prior run's sidecar (if any
    and if it matches this root), then persist the current count. Returns True iff
    the permanent-skip guard has triggered: same Skipped count as last run AND no
    new pending files added this run. Mirrors the old session-log-grep semantics
    but owned entirely by `scan` itself, via a small JSON sidecar under
    <root>/.organizer/ (same directory + atomic-write convention as config.json /
    registry files — see paths_config._atomic_write)."""
    state_path = _scan_skip_state_path(drive)
    triggered = False
    prior = None
    if state_path.exists():
        try:
            prior = json.loads(state_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            prior = None
    if prior and prior.get("root") == str(drive):
        if prior.get("skipped_count") == skipped and new_pending == 0:
            triggered = True
    try:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(
            state_path,
            json.dumps(
                {
                    "root": str(drive),
                    "skipped_count": skipped,
                    "timestamp": datetime.now().isoformat(),
                },
                ensure_ascii=False,
                indent=2,
            ),
        )
    except OSError as e:
        print(f"WARNING: could not write scan-skip sidecar {state_path} "
              f"({type(e).__name__}: {e}); permanent-skip guard may misfire next run.",
              file=sys.stderr)
    return triggered


def cmd_scan(args):
    drive = Path(args.path).expanduser() if args.path else paths_config._EFFECTIVE_ROOT
    if not drive.exists():
        sys.exit(f"Error: root path not found: {drive}")
    _note = _cloud_platform_note()
    if _note:
        print(_note, file=sys.stderr)

    # Precedence: explicit CLI flag > config.json (scan_file_limit / scan_gb_limit) >
    # hardcoded default (250 / 20.0). `args.limit`/`args.limit_gb` are None when the
    # user did not pass the flag — that's what lets the config-driven default trigger.
    _arg_limit = getattr(args, "limit", None)
    file_limit = _arg_limit if _arg_limit is not None else _effective_scan_file_limit(drive)
    _arg_limit_gb = getattr(args, "limit_gb", None)
    gb_limit = float(_arg_limit_gb) if _arg_limit_gb is not None else _effective_scan_gb_limit(drive)
    byte_limit = int(gb_limit * 1024 ** 3)

    conn = get_db()
    cur = conn.execute(
        "INSERT INTO batches (started_at) VALUES (?)",
        (datetime.now().isoformat(),)
    )
    batch_id = cur.lastrowid
    conn.commit()

    new_count = updated_count = duplicate_count = skipped = 0
    triggered_count = 0
    t_download = t_hash = t_peek = 0.0   # per-phase timing (reported in the summary)
    total_bytes = 0

    # Paths the tool has already given a TERMINAL status — never re-hash or re-propose
    # them. Not just 'organized': a deletion-staged ('to_delete'), merged-original
    # ('archived'), co-located duplicate ('duplicate'), or pruned ('deleted') row sits
    # under Archive/ etc. and must NOT be re-walked as fresh content — otherwise an mtime
    # change would re-hash it and Pass 3 would flip it back to 'pending', re-proposing a
    # file the user already deleted/merged. 'flagged' is included for the same reason: a
    # flagged file is set aside for the manual peek-and-reclassify path (process-return
    # step 7) and must stay flagged — re-hashing it on a content change would flip it to
    # 'pending' and re-expose it to propose with no peek. (Genuine new content under a
    # user's own 'Archive' folder still has no row yet, so it still gets scanned.)
    organized_paths: set[str] = {
        r["current_path"]
        for r in conn.execute(
            "SELECT current_path FROM files "
            "WHERE status IN ('organized','to_delete','archived','duplicate','deleted','flagged')"
        ).fetchall()
    }

    # Seeded here (end of scan), consumed later by the viewer in a separate pass — matches
    # the documented scan -> propose -> viewer sequence, so a folder present at scan time is
    # always in path_vocab by the time the viewer opens. A folder created manually AFTER this
    # scan but BEFORE the viewer runs won't autocomplete until the next scan — expected, not a bug.
    _learn_dir_vocab(drive, conn)
    _seed_vocab_from_rules(drive, conn)

    # Locked atomic-unit folders (entities.json entity_type=atomic / locked=true) are
    # treated as a single opaque unit — scan never descends into them per-file. Matched
    # by folder basename. (W3 sets these on user approval; honoured here at scan time.)
    _locked_atomic = _locked_atomic_names(drive)

    # ------------------------------------------------------------------
    # ENUMERATION: walk the tree once, classify every eligible file into
    # one of six priority buckets. Cheap — only stat + xattr per file.
    # ------------------------------------------------------------------
    # Priority order:
    #   1 = ruled folder, downloaded     2 = ruled folder, cloud (needs download)
    #   3 = loose root, downloaded       4 = loose root, cloud
    #   5 = no-rules folder, downloaded  6 = no-rules folder, cloud
    buckets: dict[int, list[tuple[Path, int, bool]]] = {p: [] for p in range(1, 7)}

    def eligible(filepath: Path) -> tuple[bool, int]:
        """Return (eligible, size_bytes). Eligible = not skipped, not a symlink, not
        organised. A genuinely-empty REAL file (size 0, not a cloud placeholder) is
        eligible — it should be registered/organised, not silently dropped; only a
        zero-byte *placeholder* is skipped (it has no materialisable bytes)."""
        if should_skip(filepath):
            return False, 0
        # Skip symlinks: never hash/move through a link (could escape the drive or
        # double-count the target). is_symlink() does not follow the link.
        try:
            if filepath.is_symlink():
                return False, 0
        except OSError:
            return False, 0
        if str(filepath) in organized_paths:
            return False, 0
        try:
            fsize = filepath.stat().st_size
        except OSError:
            return False, 0
        if fsize == 0 and _is_placeholder(filepath):
            # Zero-byte cloud placeholder with nothing to download — defer.
            return False, 0
        return True, fsize

    for entry in drive.iterdir():
        if entry.name.startswith(".") or should_skip(entry):
            continue
        # Skip symlinked top-level entries entirely (file or dir).
        try:
            if entry.is_symlink():
                continue
        except OSError:
            continue
        if entry.is_file():
            ok, fsize = eligible(entry)
            if not ok:
                continue
            placeholder = _is_placeholder(entry)
            buckets[4 if placeholder else 3].append((entry, fsize, placeholder))
        elif entry.is_dir():
            # External folders (shared from someone else) are completely opaque —
            # never walk into them, never propose anything for files inside.
            if _is_external(entry):
                continue
            # Locked atomic units are opaque too — skip the whole folder.
            if entry.name in _locked_atomic:
                continue
            folder_has_rules = _has_rules(entry, drive)
            for root, subdirs, files in os.walk(entry):
                root_path = Path(root)
                # Prune NESTED external/atomic folders too, not just top-level ones:
                # a shared folder or a node_modules/.git/venv buried inside a known
                # folder must never be descended into. _locked_atomic catches
                # user-approved units; _atomic_marker catches un-bootstrapped drives
                # (node_modules, .git, bundles) by signature.
                subdirs[:] = [d for d in subdirs
                              if not d.startswith(".")
                              and not (root_path / d).is_symlink()
                              and d not in _locked_atomic
                              and not _atomic_marker(root_path / d, drive)
                              and not _is_external(root_path / d)]
                # Nesting levels here are inherent to the walk structure: phase →
                # os.walk → per-file. folder_has_rules is captured once per top-level
                # folder (outside os.walk) and governs the bucket for every file inside.
                for fname in files:
                    filepath = root_path / fname
                    ok, fsize = eligible(filepath)
                    if not ok:
                        continue
                    placeholder = _is_placeholder(filepath)
                    if folder_has_rules:
                        bucket = 2 if placeholder else 1
                    else:
                        bucket = 6 if placeholder else 5
                    buckets[bucket].append((filepath, fsize, placeholder))

    # ------------------------------------------------------------------
    # PROCESSING: walk priorities 1→6, hashing files (triggering
    # downloads inline for cloud-only ones) until the cap is hit.
    # ------------------------------------------------------------------
    stopped_at_priority: int | None = None
    priority_labels = {
        1: "ruled-folder downloaded",    2: "ruled-folder cloud",
        3: "loose root downloaded",      4: "loose root cloud",
        5: "no-rules folder downloaded", 6: "no-rules folder cloud",
    }

    # W4 skip-rehash: index existing rows so an unchanged file (same path + size +
    # mtime, with a stored hash) is never re-hashed or re-peeked — the big re-scan win.
    existing_index = {}
    for r in conn.execute("SELECT current_path, sha256, file_size, mtime FROM files"):
        existing_index[r["current_path"]] = (r["sha256"], r["file_size"], r["mtime"])

    unchanged = 0
    to_process = []  # (filepath, fsize, mtime) — files that genuinely need hashing

    # Pass 1a (sequential SELECTION): respect caps + skip-rehash to decide which files
    # this batch will process. No download/poll happens here — cloud-only files are only
    # SELECTED now; their bytes are kicked + awaited together in the batched pre-trigger
    # (Pass 1b) so the network waits overlap each other instead of running one file at a
    # time. The cap uses the placeholder-reported size here; the real size/mtime is
    # re-captured after materialisation.
    selected = []  # (filepath, fsize, cur_mtime, placeholder)
    for priority in range(1, 7):
        if stopped_at_priority:
            break
        files = sorted(buckets[priority], key=lambda x: str(x[0]))
        for filepath, fsize, placeholder in files:
            if len(selected) >= file_limit:
                stopped_at_priority = priority
                break
            try:
                # Full-precision mtime (nanoseconds): an int(st_mtime) truncates to
                # the second, so two edits within the same second look "unchanged"
                # and the file is never re-hashed. Stored in the same `mtime` column.
                cur_mtime = filepath.stat().st_mtime_ns
            except OSError:
                cur_mtime = 0
            ex = existing_index.get(str(filepath))
            if ex and ex[0] and ex[1] == fsize and ex[2] == cur_mtime:
                unchanged += 1
                continue  # unchanged + already registered — no work
            # First-admission exception, scoped PER SCAN CALL (the `and selected` guard):
            # admit the FIRST file of this call even if it alone exceeds the GB cap — else a
            # single file larger than the cap is rejected on every scan and never processed
            # (permanent stall). Once this call has admitted anything (`selected` non-empty),
            # the cap applies strictly. It is per-call, not per-file: a too-big file deferred
            # this call is re-considered (and again first-admitted) on the NEXT scan call.
            if total_bytes + fsize > byte_limit and selected:
                stopped_at_priority = priority
                break
            selected.append((filepath, fsize, cur_mtime, placeholder))
            total_bytes += fsize

    # Pass 1b (BATCHED cloud pre-trigger): kick EVERY selected cloud-only placeholder's
    # download up front (open+read(1) forces OneDrive/File-Provider to start materialising),
    # then poll the whole set once — so N downloads proceed concurrently (and overlap the
    # hashing in Pass 2) instead of the old one-file-at-a-time trigger→poll that serialised
    # every network wait. Tunable via DRIVE_ORG_DL_TIMEOUT.
    to_process = []           # (filepath, fsize, cur_mtime) — files ready to hash
    pending_dl = []           # placeholders we kicked and still need to confirm materialised
    for filepath, fsize, cur_mtime, placeholder in selected:
        if not placeholder:
            to_process.append((filepath, fsize, cur_mtime))
            continue
        # Trigger download — open() forces materialisation; do NOT wait here.
        try:
            with open(filepath, "rb") as f:
                f.read(1)
        except OSError as e:
            print(f"  skip {filepath}: download failed: {e}", file=sys.stderr)
            skipped += 1
            continue
        pending_dl.append(filepath)

    if pending_dl:
        # Single batch poll: one wall-clock wait for the WHOLE set to clear the
        # placeholder marker (instead of a per-file poll). A file slower than one tick
        # is no longer deferred to a future scan — but a still-online-only file after
        # the timeout is. Timeout precedence: DRIVE_ORG_DL_TIMEOUT env var (explicit
        # per-run escape hatch) > config.json's download_poll_timeout (persistent
        # per-drive default) > 30s (see paths_config._effective_download_poll_timeout).
        download_poll_timeout = _effective_download_poll_timeout(drive)
        _wstart = time.monotonic()
        waited = 0.0
        remaining = [p for p in pending_dl if _is_placeholder(p)]
        while remaining and waited < download_poll_timeout:
            time.sleep(DOWNLOAD_POLL_INTERVAL)
            waited += DOWNLOAD_POLL_INTERVAL
            remaining = [p for p in remaining if _is_placeholder(p)]
        t_download += time.monotonic() - _wstart

        # Batched stability check: stat the whole set, sleep ONCE, stat again — so the
        # byte-stable confirmation also runs as a single wait, not one interval per file.
        # Never hash a partially-downloaded file: a still-streaming file can clear the
        # dataless flag while its size is still climbing, so confirm (a) no longer
        # dataless AND (b) byte-stable across the two reads; otherwise defer.
        first_stat = {}
        for filepath in pending_dl:
            if _is_placeholder(filepath):
                print(f"  skip {filepath}: still online-only after {download_poll_timeout:.0f}s", file=sys.stderr)
                skipped += 1
                continue
            try:
                first_stat[filepath] = filepath.stat()
            except OSError as e:
                print(f"  skip {filepath}: vanished during materialise check: {e}", file=sys.stderr)
                skipped += 1
        if first_stat:
            time.sleep(DOWNLOAD_POLL_INTERVAL)
        for filepath, s1 in first_stat.items():
            try:
                s2 = filepath.stat()
            except OSError as e:
                print(f"  skip {filepath}: vanished during materialise check: {e}", file=sys.stderr)
                skipped += 1
                continue
            if _is_placeholder(filepath) or s1.st_size != s2.st_size:
                print(f"  skip {filepath}: not fully materialised (size unstable), deferring", file=sys.stderr)
                skipped += 1
                continue
            # Re-capture size/mtime now that the real bytes are present — the
            # placeholder-reported values may differ from the materialised file.
            triggered_count += 1
            to_process.append((filepath, s2.st_size, s2.st_mtime_ns))

    # Pass 2 (parallel): hash + content-peek the selected files concurrently. Hashing
    # is I/O-bound, so a small thread pool overlaps reads (flagged in Phase 4C).
    # Only HASHING is parallelised — sha256/hashlib is thread-safe. content_peek is
    # NOT: it calls PyMuPDF (fitz) for PDFs, which segfaults under concurrent use, so
    # peeking stays sequential (Pass 3). (Found via the >25GB gate: parallel peek → SIGSEGV.)
    def _hash_only(item):
        filepath, fsize, cur_mtime = item
        try:
            _h = time.monotonic()
            # Pass the admission size: sha256_of re-stats afterward and raises if the
            # file changed size mid-hash (a still-materialising download / concurrent
            # edit), so we never commit a hash of partial bytes.
            digest = sha256_of(filepath, expected_size=fsize)
            return ("ok", filepath, fsize, cur_mtime, filepath.suffix.lower(),
                    digest, time.monotonic() - _h)
        except OSError as e:
            return ("err", filepath, str(e))

    results = []
    if to_process:
        workers = min(8, (os.cpu_count() or 2) + 2)
        with _futures.ThreadPoolExecutor(max_workers=workers) as pool:
            # as_completed + per-future try/except: one worker raising an unexpected
            # error must not discard the whole batch's completed hashes (pool.map
            # re-raises the first exception and drops every result).
            futures = {pool.submit(_hash_only, item): item for item in to_process}
            for fut in _futures.as_completed(futures):
                try:
                    results.append(fut.result())
                except Exception as e:  # defensive — _hash_only already traps OSError
                    item = futures[fut]
                    results.append(("err", item[0], str(e)))

    # A candidate duplicate row only counts if its file is still real and live:
    # current_path exists on disk AND status is organized/pending. A row whose
    # original was deleted/moved (stale current_path) or already marked duplicate
    # must NOT poison a fresh file into 'duplicate' (it would then never organise).
    def _is_live_dup(digest_val: str, exclude_id: int | None = None) -> bool:
        rows = conn.execute(
            "SELECT id, current_path, status FROM files WHERE sha256 = ?",
            (digest_val,)
        ).fetchall()
        for row in rows:
            if exclude_id is not None and row["id"] == exclude_id:
                continue
            if row["status"] not in ("organized", "pending"):
                continue
            cp = row["current_path"]
            if cp and Path(cp).exists():
                return True
        return False

    # Pass 3 (sequential): content-peek (thread-unsafe) + registry writes.
    for res in results:
        if res[0] == "err":
            print(f"  skip {res[1]}: {res[2]}", file=sys.stderr)
            skipped += 1
            continue
        _, filepath, fsize, cur_mtime, ext, digest, dt = res
        t_hash += dt
        path_str = str(filepath)
        file_date = extract_photo_date(filepath.name)
        content_peek = None
        if ext not in IMAGE_EXTS:
            _p = time.monotonic()
            try:
                content_peek = peek_content(filepath)
            except Exception:
                content_peek = None
            t_peek += time.monotonic() - _p

        existing = conn.execute(
            "SELECT id, sha256, status FROM files WHERE current_path = ?", (path_str,)
        ).fetchone()
        if existing:
            if existing["sha256"] != digest:
                # Hash changed under a known path. Don't blindly reset to 'pending'
                # for a row that was a 'duplicate' — re-evaluate dedup against the new
                # hash instead of silently re-proposing it as a fresh file.
                if existing["status"] == "duplicate":
                    new_status = "duplicate" if _is_live_dup(digest, exclude_id=existing["id"]) else "pending"
                else:
                    new_status = "pending"
                conn.execute(
                    """UPDATE files SET sha256=?, file_size=?, mtime=?, content_peek=?,
                       status=?, batch_id=? WHERE id=?""",
                    (digest, fsize, cur_mtime, content_peek, new_status, batch_id, existing["id"])
                )
                updated_count += 1
            else:
                # content identical but size/mtime changed (e.g. touched) — refresh mtime
                conn.execute("UPDATE files SET mtime=? WHERE id=?", (cur_mtime, existing["id"]))
            continue

        dup = _is_live_dup(digest)
        status = "duplicate" if dup else "pending"
        conn.execute(
            """INSERT INTO files
               (original_path, current_path, filename, extension, file_size, mtime,
                sha256, file_date, content_peek, status, batch_id)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (path_str, path_str, filepath.name, ext, fsize, cur_mtime,
             digest, file_date, content_peek, status, batch_id)
        )
        if dup:
            duplicate_count += 1
        else:
            new_count += 1

    conn.execute(
        "UPDATE batches SET completed_at=? WHERE id=?",
        (datetime.now().isoformat(), batch_id)
    )
    conn.commit()

    total   = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
    pending = conn.execute("SELECT COUNT(*) FROM files WHERE status='pending'").fetchone()[0]
    conn.close()

    # Detect root-level folders that have no rules (not staging, no .tidy-rules.json).
    # These ARE still scanned — at low priority (buckets 5/6); the report just lets the
    # user add rules to prioritise/route them instead of leaving their files to _Inbox.
    unknown_folders = []
    for entry in sorted(drive.iterdir()):
        if not entry.is_dir():
            continue
        if should_skip(entry) or entry.name.startswith("."):
            continue
        if entry.name in PARA_ROOTS or _is_external(entry):
            continue
        if not _has_rules(entry, drive):
            unknown_folders.append(entry.name)

    bucket_counts = {p: len(buckets[p]) for p in range(1, 7)}
    print(f"Scan complete  (batch {batch_id})")
    print(f"  New files:         {new_count:6d}")
    print(f"  Hash-changed:      {updated_count:6d}")
    print(f"  Exact duplicates:  {duplicate_count:6d}")
    print(f"  Unchanged (skip-rehash): {unchanged:6d}")
    print(f"  Skipped:           {skipped:6d}")
    print(f"  Pending classify:  {pending:6d}")
    print(f"  Total in registry: {total:6d}")
    print(f"  Batch size:        {total_bytes/1024**3:.2f} GB / {gb_limit:.0f} GB cap")
    print(f"  Downloads triggered: {triggered_count:6d}")
    print(f"  Time — download-wait: {t_download:5.1f}s | hashing: {t_hash:5.1f}s | content-peek: {t_peek:5.1f}s")
    print(f"  Eligible per priority:")
    for p in range(1, 7):
        print(f"    P{p} ({priority_labels[p]:>25}): {bucket_counts[p]:6d}")
    if stopped_at_priority:
        print(f"  → Cap reached in priority {stopped_at_priority} ({priority_labels[stopped_at_priority]})")
    else:
        print(f"  → All priorities drained within cap")
    if unknown_folders:
        print()
        print(f"  Folders with no rules ({len(unknown_folders)}):")
        for name in unknown_folders:
            print(f"    - {name}")
        print("  → Optional: add a .tidy-rules.json to route these by rule; they're scanned at low priority (P5/6) and classified either way.")

    # Permanent-skip guard: compare this run's Skipped count against the sidecar
    # persisted by the previous scan of this same root. Triggers when Skipped is
    # unchanged AND this run added no new pending files (new_count == 0) — the same
    # two-consecutive-equal-Skipped-with-no-new-pending semantics previously tracked
    # via a session-log grep, now owned by scan itself.
    guard_triggered = _check_and_update_skip_guard(drive, skipped, new_count)
    if guard_triggered:
        print()
        print(f"PERMANENT_SKIP_GUARD_TRIGGERED: {skipped} files persistently skipped")

    export_csv()


# ---------------------------------------------------------------------------
# propose
# ---------------------------------------------------------------------------
