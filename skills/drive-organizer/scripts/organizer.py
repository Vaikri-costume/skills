#!/usr/bin/env python3
"""
Drive Organizer backend.

Usage:
  organizer.py download-batch [--limit-gb N] [<root_path>]
  organizer.py scan [<root_path>]
  organizer.py propose [--limit N]
  organizer.py execute --approved <json_file>
  organizer.py duplicates
  organizer.py variants
  organizer.py merge --group <group_id> --canonical <file_id>
  organizer.py status
  organizer.py generate-viewer --proposals <json_file> [--port 5002]
  organizer.py cleanup [<root_path>]
"""

from __future__ import annotations  # defer annotation eval so `X | None` works on Python 3.9
import argparse
import concurrent.futures as _futures
import copy
import hashlib
import json
import os
import re
import shutil
import sqlite3
import sys
import threading
import time
import webbrowser
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

REGISTRY_DB = Path.home() / ".claude" / "drive-organizer" / "registry.db"  # overridden at startup
DEFAULT_ONEDRIVE = Path.home() / "Library" / "CloudStorage" / "OneDrive-Personal"
CONFIG_PATH = Path.home() / ".claude" / "drive-organizer" / "config.json"
_EFFECTIVE_ROOT = DEFAULT_ONEDRIVE  # set in main() from --root / config / DEFAULT

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".heic", ".heif", ".webp", ".tiff", ".tif", ".bmp", ".jfif"}
# RAW formats are not in IMAGE_EXTS — Claude can't vision-read them, and the skill routes
# them by filename + parent folder via the Documents/RAW process instead.
SKIP_NAMES = {".DS_Store", ".localized", "desktop.ini", "thumbs.db", ".tidy-rules.json"}
SKIP_EXTS  = {".tmp", ".partial", ".lnk", ".ini"}

# Special staging folders — never cleaned up, never re-scanned as fresh content
PARA_ROOTS = {"_Inbox", "_To Delete", "_Duplicates", "_Merged-Originals", "Archive"}

PEEK_CHARS = 300   # max chars to extract for content peek

# Classification fan-out batch size: cmd_propose partitions the to-classify
# residual into batches of this size, one classification sub-agent per batch.
BATCH = 25

# Cloud-download polling. The scan used to do a single fixed 0.5s check after
# triggering a download and skip the file if it hadn't materialised yet — so any
# file slower than one tick was deferred to a future scan, which is the main
# cause of slow multi-pass cycles. Now scan polls up to a timeout so the file
# downloads within the same pass. Tunable via env (DRIVE_ORG_DL_TIMEOUT seconds).
DOWNLOAD_POLL_INTERVAL = 0.5
DOWNLOAD_POLL_TIMEOUT  = float(os.environ.get("DRIVE_ORG_DL_TIMEOUT", "30"))


# ---------------------------------------------------------------------------
# Shared safety helpers (Phase-0 baseline review: BL-A1 atomic writes, BL-A2 path containment)
# ---------------------------------------------------------------------------
def _atomic_write(path: "Path", text: str, encoding: str = "utf-8") -> None:
    """Write `text` to `path` atomically: write a temp file in the same directory
    then os.replace() it into place. A crash or full disk can never leave a
    truncated config / .tidy-rules.json / output file (BL-A1). Always UTF-8 (BL-A5)."""
    path = Path(path)
    tmp = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    try:
        tmp.write_text(text, encoding=encoding)
        os.replace(str(tmp), str(path))
    finally:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass


def _safe_dest(root: "Path", sub: str) -> "Path | None":
    """Resolve <root>/<sub> and return it ONLY if it stays inside `root`.

    Rejects absolute subpaths, '..' escapes, and symlink components that resolve
    outside root (BL-A2). Returns None when the destination would fall outside
    root — callers MUST treat None as 'reject this move/write', never fall back to
    an unchecked join. The returned path is the *resolved* path; use it for the
    actual filesystem operation so validation and write target are identical."""
    if sub is None:
        return None
    s = str(sub).strip()
    if not s:
        return None
    p = Path(s)
    if p.is_absolute():
        return None
    root_r = Path(root).resolve()
    cand = (root_r / p).resolve()
    try:
        cand.relative_to(root_r)
    except ValueError:
        return None
    return cand


# ---------------------------------------------------------------------------
# Config (saved active root)
# ---------------------------------------------------------------------------

def _read_config_root() -> "Path | None":
    # File-absent is fine (no saved root yet) -> return None silently.
    if not CONFIG_PATH.exists():
        return None
    # File present-but-corrupt/unreadable is a data-safety hazard: a silent fall
    # back to the default root could organize the WRONG drive. Warn loudly.
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        root = data.get("root")
        if root:
            return Path(root).expanduser().resolve()
    except Exception as e:
        print(f"WARNING: saved config root at {CONFIG_PATH} is corrupt/unreadable "
              f"({e}); ignoring it. Pass --root explicitly to be safe.", file=sys.stderr)
    return None


def _save_config_root(root: Path):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(CONFIG_PATH, json.dumps({"root": str(root)}, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------------------
# Approved-folder detection (rules-based, no hardcoded prefixes)
# ---------------------------------------------------------------------------

def _has_rules(folder_path: Path, root: Path) -> bool:
    """
    Return True if this root-level folder is understood:
    - has its own .tidy-rules.json, OR
    - appears as a target in the root .tidy-rules.json
    """
    if (folder_path / ".tidy-rules.json").exists():
        return True
    root_rules = root / ".tidy-rules.json"
    if root_rules.exists():
        try:
            data = json.loads(root_rules.read_text(encoding="utf-8"))
            folder_name = folder_path.name
            for rule in data.get("rules", []):
                fn = rule.get("folderName", "")
                if not fn:  # skip rules with an empty folderName
                    continue
                top = fn.split("/")[0]
                if top == folder_name:
                    return True
        except Exception as e:
            print(f"WARNING: could not parse {root_rules} ({e}); "
                  f"treating '{folder_path.name}' as having no rules.", file=sys.stderr)
    return False


def _is_external(folder_path: Path) -> bool:
    """
    Return True if this folder is marked external in its .tidy-rules.json.
    External folders are shared/owned by someone else — scan must never enter,
    propose must never target. The folder is treated as opaque.
    """
    rules_file = folder_path / ".tidy-rules.json"
    if not rules_file.exists():
        return False
    try:
        data = json.loads(rules_file.read_text(encoding="utf-8"))
    except Exception as e:
        # Fail CLOSED: if we can't read the rules we cannot prove the folder is
        # safe to enter, so treat it as external (opaque) rather than walking
        # into someone else's shared content.
        print(f"WARNING: could not parse {rules_file} ({e}); "
              f"treating '{folder_path.name}' as EXTERNAL (will not enter).", file=sys.stderr)
        return True
    if isinstance(data, dict) and data.get("external") is True:
        return True
    return False


def _merge_lists(base_list: list, override_list: list) -> list:
    """
    Merge two lists for the template override. If every element is a dict with a
    "name" key, merge by name (override replaces the same-named base entry, new
    names append) — so a user override of `ENTERTAINMENT` cleanly replaces the
    skeleton's `ENTERTAINMENT` rather than duplicating it. Otherwise concatenate
    with simple dedup.

    Dedup semantics (by-name branch): keys are the `name` values; within base or
    override, an earlier same-named entry is dropped in favour of the override's
    (or, absent an override, the base's first occurrence). If any `name` is
    unhashable (e.g. a list/dict value), we cannot build the name index, so we
    fall back to the concat+value-dedup branch rather than crash.
    """
    items = base_list + override_list
    if items and all(isinstance(x, dict) and "name" in x for x in items):
        try:
            by_name = {x["name"]: x for x in base_list}
            for x in override_list:
                by_name[x["name"]] = x  # override wins
            result, seen = [], set()
            for x in base_list + override_list:
                if x["name"] not in seen:
                    result.append(by_name[x["name"]])
                    seen.add(x["name"])
            return result
        except TypeError:
            # An unhashable "name" — can't dedup by name; fall through to concat.
            pass
    return base_list + [x for x in override_list if x not in base_list]


def _deep_merge(base: dict, override: dict) -> dict:
    """
    Recursively merge `override` into a copy of `base`. Dicts merge key-by-key;
    lists merge via _merge_lists (by "name" when present, else concat+dedup);
    scalars from the override win. Used to layer a per-user template override
    over the shipped skeleton.

    The result must NOT alias the cached base or the override: nested dict/list
    values that are NOT recursively merged are deep-copied so a caller mutating
    the returned tree can never corrupt the process-wide _TEMPLATES_CACHE base.
    """
    out = {k: copy.deepcopy(v) for k, v in base.items()}
    for k, v in override.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        elif k in out and isinstance(out[k], list) and isinstance(v, list):
            # _merge_lists returns elements aliased from base/override; deep-copy
            # so the merged list can't reach back into the cached base or override.
            out[k] = copy.deepcopy(_merge_lists(out[k], v))
        else:
            out[k] = copy.deepcopy(v)
    return out


def _read_user_config(root: "Path | None" = None) -> dict:
    """
    Per-user / per-drive settings that are NOT shipped with the skill — they live
    on the active drive at <root>/.organizer/config.json. Recognised keys:
      - memory_doc_path: absolute path to a supplementary context doc Claude reads
        when classification is ambiguous (replaces any hardcoded path)
      - profile: free-text note about the user's roles/context, fed to classification
    Returns {} when the file is absent or the root is unknown. Never raises.
    """
    root = root or _EFFECTIVE_ROOT
    # `not root` guard: _EFFECTIVE_ROOT can still be unset/empty very early in
    # startup (before main() resolves it) — with no drive there is nowhere to
    # read per-user config from, so return the empty default.
    if not root:
        return {}
    cfg = Path(root) / ".organizer" / "config.json"
    if not cfg.exists():
        return {}
    try:
        data = json.loads(cfg.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception as e:
        print(f"WARNING: could not parse user config {cfg} ({e}); "
              f"using defaults.", file=sys.stderr)
        return {}


_TEMPLATES_CACHE = None

def _load_templates() -> dict:
    """
    Load the subfolder templates source-of-truth from the skill's references folder,
    then deep-merge any per-user override at <root>/.organizer/templates.json on top.
    Returns {} if the shipped file is missing.

    Caching: a long-running viewer server can hold this process while the user
    edits their override file, so the cache is keyed on the override file's mtime
    (and existence) — if that changes, we re-read instead of serving stale data.

    The shipped file is a generic skeleton (the five Q1 groupings + universal compound
    children). Each user grows their own taxonomy lazily via .tidy-rules.json, and may
    also drop a templates.json beside their registry to extend the skeleton with their
    own projects/structure — that override is merged here so the shipped skill stays
    generic while the user's drive carries their specifics.
    """
    global _TEMPLATES_CACHE
    override_path = None
    if _EFFECTIVE_ROOT:
        override_path = Path(_EFFECTIVE_ROOT) / ".organizer" / "templates.json"
    try:
        override_mtime = override_path.stat().st_mtime if override_path and override_path.exists() else None
    except OSError:
        override_mtime = None
    if _TEMPLATES_CACHE is not None and _TEMPLATES_CACHE[0] == override_mtime:
        return _TEMPLATES_CACHE[1]
    # Templates live in the skill's references/ at the canonical Claude Code skills
    # path. First-time-setup copies ONLY organizer.py to ~/.claude/drive-organizer/;
    # references/ are NOT copied, so they are read from the install dir here. If the
    # skill is installed somewhere non-standard this file won't be found and `base`
    # stays {} (then _active_groupings falls back to DEFAULT_GROUPINGS and the taxonomy
    # is the bare skeleton) — a documented degradation, not a crash. Override with the
    # DRIVE_ORG_SKILL_DIR env var when installed elsewhere.
    skill_dir = os.environ.get("DRIVE_ORG_SKILL_DIR")
    base_dir = Path(skill_dir) if skill_dir else (Path.home() / ".claude" / "skills" / "drive-organizer")
    templates_path = base_dir / "references" / "subfolder-templates.json"
    base = {}
    if templates_path.exists():
        try:
            base = json.loads(templates_path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"WARNING: could not parse shipped templates {templates_path} "
                  f"({e}); using empty skeleton.", file=sys.stderr)
            base = {}
    # Per-user override on the active drive (never shipped with the skill).
    if override_path and override_path.exists():
        try:
            override = json.loads(override_path.read_text(encoding="utf-8"))
            if isinstance(override, dict):
                base = _deep_merge(base, override)
        except Exception as e:
            print(f"WARNING: could not parse template override {override_path} "
                  f"({e}); ignoring it.", file=sys.stderr)
    _TEMPLATES_CACHE = (override_mtime, base)
    return base


def cmd_templates(args):
    """Print the effective templates as JSON — the shipped generic skeleton
    deep-merged with the per-user <root>/.organizer/templates.json override.
    The propose flow loads THIS (not the raw shipped file) so the executor sees
    the user's full taxonomy, not just the generic skeleton."""
    print(json.dumps(_load_templates(), ensure_ascii=False, indent=2))


def _bubble_sort_proposals(proposals: list) -> list:
    """
    Sort proposals by destination so files going to the same leaf appear
    together in the viewer. (Name is historical — this uses Python's built-in
    sorted(), not a bubble sort.) Sort key: (para_subfolder, filename).
    Inbox / unrouted files sort to the end.
    """
    def sort_key(p):
        dest = p.get("para_subfolder", "") or ""
        # _Inbox / unrouted to end
        is_inbox = dest.startswith("_Inbox") or dest == ""
        return (1 if is_inbox else 0, dest.lower(), (p.get("filename") or "").lower())
    return sorted(proposals, key=sort_key)


# ---------------------------------------------------------------------------
# Project metadata (filename_tag + production_period) — read/write helpers
# ---------------------------------------------------------------------------

def _project_metadata(project_path: Path) -> dict:
    """
    Read filename_tag and production_period from a project's .tidy-rules.json.
    Returns {} if the file is missing, unparseable, or has no metadata fields.
    """
    rules_file = project_path / ".tidy-rules.json"
    if not rules_file.exists():
        return {}
    try:
        data = json.loads(rules_file.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"WARNING: could not parse {rules_file} ({e}); "
              f"treating '{project_path.name}' as having no project metadata.", file=sys.stderr)
        return {}
    if not isinstance(data, dict):
        return {}
    out = {}
    if data.get("filename_tag"):
        out["filename_tag"] = data["filename_tag"]
    if data.get("production_period"):
        out["production_period"] = data["production_period"]
    return out


def _enumerate_project_metadata(root: Path) -> list:
    """
    Walk top-level project folders under root and collect their metadata.
    Returns list of {path (relative), filename_tag, production_period} entries
    for every folder whose .tidy-rules.json carries a filename_tag.
    Used by propose to surface candidate matches by date for loose bills.
    """
    out = []
    # Top-level folders (legacy flat) and nested grouping/company/project folders
    SKIP = {".organizer", "logseq-journals", "Archive"}
    try:
        tops = sorted(root.iterdir())
    except (PermissionError, OSError) as e:
        print(f"WARNING: could not list {root} ({e}); no project metadata enumerated.",
              file=sys.stderr)
        return out
    for top in tops:
        if not top.is_dir() or top.name.startswith(('.', '_')):
            continue
        if top.name.startswith('x') or top.name in SKIP:
            continue
        if _is_external(top):
            continue
        # Direct-level project (legacy flat)
        meta = _project_metadata(top)
        if meta.get("filename_tag"):
            out.append({"path": top.name, **meta})
        # Two-level (new nested: WORK/COMPANY/PROJECT, PERSONAL/PERSONAL X)
        try:
            for mid in sorted(top.iterdir()):
                if not mid.is_dir() or mid.name.startswith(('.', '_')) or mid.name in PARA_ROOTS:
                    continue
                if _is_external(mid):
                    continue
                meta_mid = _project_metadata(mid)
                if meta_mid.get("filename_tag"):
                    out.append({"path": f"{top.name}/{mid.name}", **meta_mid})
                # Three-level (e.g. WORK/VAIKRI/VAIKRI CS Yeh Saali Naukri/)
                try:
                    for deep in sorted(mid.iterdir()):
                        if not deep.is_dir() or deep.name.startswith(('.', '_')) or deep.name in PARA_ROOTS:
                            continue
                        if _is_external(deep):
                            continue
                        meta_deep = _project_metadata(deep)
                        if meta_deep.get("filename_tag"):
                            out.append({"path": f"{top.name}/{mid.name}/{deep.name}", **meta_deep})
                except (PermissionError, OSError):
                    pass
        except (PermissionError, OSError):
            pass
    return out


def _find_project_for_destination(dest_subfolder: str, root: Path) -> "Path | None":
    """
    Given a destination subfolder path like 'WORK/VAIKRI/VAIKRI CS Yeh Saali Naukri/Scripts',
    walk up from the deepest folder until we find an ancestor whose .tidy-rules.json
    carries a filename_tag. Returns the absolute path to that project folder, or None.
    """
    if not dest_subfolder:
        return None
    # Contain the candidate inside root: reject absolute / '..' / symlink escapes
    # so we never walk arbitrary ancestors outside the configured drive.
    cur = _safe_dest(root, dest_subfolder)
    if cur is None:
        return None
    root_r = Path(root).resolve()
    # Walk up until cur is root
    while True:
        if cur == root_r or cur.parent == cur:
            return None
        if _project_metadata(cur).get("filename_tag"):
            return cur
        cur = cur.parent


def _expand_production_period(project_path: Path, file_date_iso: str, buffer_days: int = 30) -> None:
    """
    Expand the project's production_period to include file_date_iso, with a
    buffer_days padding at each end. If the project has no production_period
    yet, initialise one centred on this file's date. Writes back to .tidy-rules.json.
    """
    rules_file = project_path / ".tidy-rules.json"
    if not rules_file.exists():
        return
    try:
        data = json.loads(rules_file.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"WARNING: could not parse {rules_file} ({e}); "
              f"not expanding production_period.", file=sys.stderr)
        return
    if not isinstance(data, dict):
        return  # legacy list-format files don't carry project metadata

    try:
        file_dt = datetime.fromisoformat(file_date_iso[:10])
    except (ValueError, TypeError):
        return

    # Clamp the file date to a sane range so one mis-dated file (e.g. epoch 1970,
    # or a future timestamp from a bad clock) can't blow the period out forever.
    floor_dt = datetime(1990, 1, 1)
    ceil_dt = datetime.now() + timedelta(days=365)
    if file_dt < floor_dt or file_dt > ceil_dt:
        return  # out-of-range date: ignore rather than widen the period

    buf = timedelta(days=buffer_days)
    period = data.get("production_period")
    if not period or not isinstance(period, dict):
        new_start = (file_dt - buf).date().isoformat()
        new_end = (file_dt + buf).date().isoformat()
    else:
        # Parse the existing bounds independently. A half-open period (only start
        # OR only end set) is widened only on the side that exists — the missing
        # bound is filled from THIS file's date, never coerced to overwrite a
        # real existing bound. Non-ISO bound strings are treated as absent.
        def _parse(v):
            if not v:
                return None
            try:
                return datetime.fromisoformat(str(v)[:10])
            except (ValueError, TypeError):
                return None
        cur_start = _parse(period.get("start"))
        cur_end = _parse(period.get("end"))
        new_start_dt = min(cur_start, file_dt - buf) if cur_start is not None else (file_dt - buf)
        new_end_dt = max(cur_end, file_dt + buf) if cur_end is not None else (file_dt + buf)
        new_start = new_start_dt.date().isoformat()
        new_end = new_end_dt.date().isoformat()

    if data.get("production_period") == {"start": new_start, "end": new_end}:
        return  # nothing changed
    data["production_period"] = {"start": new_start, "end": new_end}
    _atomic_write(rules_file, json.dumps(data, ensure_ascii=False, indent=2))


def _date_matches_period(file_date_iso: str, period: dict) -> bool:
    """Return True if file_date_iso falls within period {start, end}."""
    if not period or not file_date_iso:
        return False
    try:
        d = datetime.fromisoformat(file_date_iso[:10])
        s = datetime.fromisoformat(period["start"][:10])
        e = datetime.fromisoformat(period["end"][:10])
    except (ValueError, KeyError, TypeError):
        return False
    return s <= d <= e


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    original_path  TEXT NOT NULL,
    current_path   TEXT,
    filename       TEXT,
    extension      TEXT,
    file_size      INTEGER,
    mtime          INTEGER,
    sha256         TEXT,
    file_date      TEXT,
    vision_desc    TEXT,
    content_peek   TEXT,
    para_category  TEXT,
    para_subfolder TEXT,
    variant_group  TEXT,
    batch_id       INTEGER,
    status         TEXT DEFAULT 'pending',
    processed_at   TEXT
);

CREATE TABLE IF NOT EXISTS batches (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at   TEXT,
    completed_at TEXT,
    notes        TEXT
);

CREATE TABLE IF NOT EXISTS path_vocab (
    segment   TEXT    NOT NULL,
    position  INTEGER NOT NULL,
    use_count INTEGER DEFAULT 1,
    PRIMARY KEY (segment, position)
);

CREATE INDEX IF NOT EXISTS idx_sha256       ON files(sha256);
CREATE INDEX IF NOT EXISTS idx_status       ON files(status);
CREATE INDEX IF NOT EXISTS idx_current_path ON files(current_path);
"""


def get_db() -> sqlite3.Connection:
    REGISTRY_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(REGISTRY_DB))
    conn.row_factory = sqlite3.Row
    # Overlapping connections (parallel scan workers, download-batch, viewer) must
    # wait on a busy lock rather than instantly raising "database is locked"; WAL
    # lets readers and a writer coexist.
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    # Migration: add mtime to pre-existing registries (W4 skip-rehash fast-check).
    try:
        conn.execute("ALTER TABLE files ADD COLUMN mtime INTEGER")
    except sqlite3.OperationalError:
        pass  # column already exists
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def sha256_of(path: Path, expected_size: int | None = None) -> str:
    """Hash the file. If expected_size is given (the size recorded at admission),
    re-stat after the read and raise OSError on a mismatch — a file that grew or
    shrank under us (a still-materialising cloud download, a concurrent edit) would
    otherwise yield a hash of partial bytes that we'd commit as authoritative."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    if expected_size is not None:
        post = os.stat(path).st_size
        if post != expected_size:
            raise OSError(
                f"size changed during hash ({expected_size} -> {post}); "
                f"file not stable, refusing to commit hash"
            )
    return h.hexdigest()


def extract_photo_date(filename: str) -> str | None:
    m = re.search(r"-PHOTO-(\d{4}-\d{2}-\d{2})", filename)
    return m.group(1) if m else None


def should_skip(path: Path) -> bool:
    if path.name in SKIP_NAMES:
        return True
    if path.name.startswith("."):
        return True
    if path.suffix.lower() in SKIP_EXTS:
        return True
    return False


# ---------------------------------------------------------------------------
# Content peek — extract a short text snippet for classification
# ---------------------------------------------------------------------------

def peek_content(path: Path) -> str | None:
    """
    Extract up to PEEK_CHARS of meaningful text from a file.
    Returns None for images (handled by vision), audio/video, and unreadable files.
    The snippet is used by Claude when filename heuristics are weak.
    """
    ext = path.suffix.lower()

    if ext in IMAGE_EXTS:
        return None  # images use Claude vision

    try:
        if ext == ".pdf":
            return _peek_pdf(path)
        elif ext in {".docx", ".odt"}:
            return _peek_zip_xml(path, _docx_text)
        elif ext in {".xlsx", ".ods"}:
            return _peek_zip_xml(path, _xlsx_text)
        elif ext in {".pptx", ".odp"}:
            return _peek_zip_xml(path, _pptx_text)
        elif ext == ".fdx":
            return _peek_fdx(path)
        elif ext in {".txt", ".md", ".csv", ".rtf", ".json", ".xml",
                     ".html", ".htm", ".py", ".js", ".ts"}:
            return _peek_text(path, ext)
        elif ext == ".zip":
            return _peek_zip_listing(path)
        elif ext in {".mp3", ".m4a", ".m4b", ".flac", ".aac",
                     ".aif", ".aiff", ".wav", ".ogg", ".opus", ".wma"}:
            return _peek_audio(path)
        else:
            return None
    except (OSError, ValueError, zipfile.BadZipFile, ET.ParseError,
            KeyError, UnicodeError, RuntimeError):
        # Expected, per-file failures (unreadable, malformed container, bad XML) —
        # peek is best-effort. Deliberately NOT a bare `except Exception`: a
        # MemoryError (e.g. a pathological parse) must propagate, not be masked as
        # "no peek" while the process is already in trouble.
        return None


def _peek_audio(path: Path) -> str | None:
    """
    Extract embedded audio metadata (artist, album, title, year, genre, tracknumber)
    from common audio formats: ID3 (mp3), MP4 atoms (m4a/m4b/aac), Vorbis Comment
    (flac/ogg/opus), ASF (wma), and basic RIFF/AIFF tags.

    Uses mutagen if available; degrades to None if mutagen isn't installed
    (so audio still gets classified by filename + parent folder, just without
    the metadata signal).

    Returns a single-line text blob like:
        "artist=A.R. Rahman | album=Roja | title=Chinna Chinna Aasai | year=1992 | track=2"
    that Claude can scan during cascading-Q routing.
    """
    try:
        import mutagen  # type: ignore
    except ImportError:
        return None

    try:
        audio = mutagen.File(str(path), easy=True)  # easy=True normalises tag keys
    except Exception:
        return None
    if audio is None:
        return None

    # Mutagen's easy mode returns a dict-like with list values. Pull canonical keys.
    KEYS = ["artist", "albumartist", "album", "title", "date",
            "originaldate", "tracknumber", "genre", "composer"]
    parts = []
    for k in KEYS:
        v = audio.get(k)
        if not v:
            continue
        # easy mode uses lists; flatten first value, strip whitespace
        if isinstance(v, list):
            v = v[0] if v else None
        if not v:
            continue
        val = str(v).strip()
        if val:
            parts.append(f"{k}={val}")

    # Also surface track length if available — sometimes useful to distinguish
    # a clip ("Scene 3 take 2", short) from a song (3+ min)
    try:
        length = getattr(audio.info, "length", None)
        if length:
            parts.append(f"length={int(length)}s")
    except Exception:
        pass

    if not parts:
        return None
    return " | ".join(parts)


# PyMuPDF (fitz) is NOT thread-safe — concurrent Document use segfaults. Even though
# peeking is meant to run sequentially, serialise all fitz access behind one lock so a
# future caller (or a stray parallel path) can't crash the process.
_FITZ_LOCK = threading.Lock()


def _peek_pdf(path: Path) -> str | None:
    try:
        import fitz
    except ImportError:
        return None
    # NB: a fitz Document is iterable but does NOT support slicing — `doc[:3]`
    # raises TypeError, which (before this fix) escaped the ImportError-only
    # guard and made every PDF peek silently return None. Index explicitly.
    with _FITZ_LOCK:
        doc = None
        try:
            doc = fitz.open(str(path))
            text = ""
            for i in range(min(3, doc.page_count)):
                text += doc[i].get_text()
                if len(text) >= PEEK_CHARS * 2:
                    break
            return _clean(text)
        except Exception:
            return None
        finally:
            # Always release the native handle, even on exception, or PyMuPDF leaks
            # file descriptors / mmap'd pages across a large scan.
            if doc is not None:
                try:
                    doc.close()
                except Exception:
                    pass


# Cap bytes parsed from any single zip member / XML file. Defangs zip-bombs and
# oversized XML: we read at most this much into memory and parse only that prefix.
_XML_PEEK_CAP = 5 * 1024 * 1024  # 5 MB


def _read_capped(fileobj, cap: int = _XML_PEEK_CAP) -> bytes:
    """Read at most `cap` bytes from an open binary stream. Bounds memory so a
    zip-bomb member or a multi-GB XML can't be slurped whole before parsing; we
    parse only the prefix (a truncated tail yields ET.ParseError, handled upstream)."""
    return fileobj.read(cap)


def _parse_capped_member(zf: zipfile.ZipFile, member: str) -> "ET.Element":
    """Read a bounded prefix of a zip member and parse it. Raises KeyError if the
    member is absent (handled by callers) and ET.ParseError on a truncated/invalid
    prefix (also handled by callers / _peek_zip_xml)."""
    with zf.open(member) as f:
        data = _read_capped(f)
    return ET.fromstring(data)


def _peek_zip_xml(path: Path, extractor) -> str | None:
    try:
        with zipfile.ZipFile(str(path)) as zf:
            return extractor(zf)
    except (zipfile.BadZipFile, KeyError, ET.ParseError):
        return None


def _docx_text(zf: zipfile.ZipFile) -> str | None:
    ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    root = _parse_capped_member(zf, "word/document.xml")
    texts = [el.text for el in root.iter(f"{{{ns}}}t") if el.text]
    return _clean(" ".join(texts))


def _xlsx_text(zf: zipfile.ZipFile) -> str | None:
    # Shared strings contains all cell text
    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    try:
        root = _parse_capped_member(zf, "xl/sharedStrings.xml")
        texts = [el.text for el in root.iter(f"{{{ns}}}t") if el.text]
        return _clean(" ".join(texts[:40]))
    except KeyError:
        # No shared strings → likely an empty or numbers-only sheet
        return None


def _pptx_text(zf: zipfile.ZipFile) -> str | None:
    ns = "http://schemas.openxmlformats.org/drawingml/2006/main"
    texts = []
    # Enumerate actual slide parts rather than guessing slide1..3 — decks can omit
    # or renumber slides. Sorted for deterministic ordering; first 3 slides.
    slide_names = sorted(
        n for n in zf.namelist()
        if n.startswith("ppt/slides/") and n.endswith(".xml")
        and "/" not in n[len("ppt/slides/"):]  # exclude slideLayouts/_rels subpaths
    )[:3]
    for slide_path in slide_names:
        try:
            root = _parse_capped_member(zf, slide_path)
        except (KeyError, ET.ParseError):
            continue
        texts += [el.text for el in root.iter(f"{{{ns}}}t") if el.text]
    return _clean(" ".join(texts)) if texts else None


def _peek_fdx(path: Path) -> str | None:
    # FDX is plain XML on disk (not zipped) — cap the read and guard parse failures.
    try:
        with open(path, "rb") as f:
            data = _read_capped(f)
        root = ET.fromstring(data)
    except (OSError, ET.ParseError):
        return None
    try:
        # FDX: try title page first, then first 8 paragraphs
        title_el = root.find(".//TitlePage")
        source = title_el if title_el is not None else root
        paragraphs = list(source.iter("Paragraph"))[:8]
        texts = []
        for p in paragraphs:
            for el in p.iter():
                if el.text and el.text.strip():
                    texts.append(el.text.strip())
        return _clean(" ".join(texts)) if texts else None
    except ET.ParseError:
        return None


def _peek_text(path: Path, ext: str) -> str | None:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        raw = f.read(PEEK_CHARS * 3)
    if ext == ".rtf":
        raw = re.sub(r"\{[^{}]{0,100}\}", " ", raw)
        raw = re.sub(r"\\[a-zA-Z]+\d*\s?", " ", raw)
        raw = re.sub(r"[{}\\]", " ", raw)
    return _clean(raw)


def _peek_zip_listing(path: Path) -> str | None:
    try:
        with zipfile.ZipFile(str(path)) as zf:
            names = [n for n in zf.namelist() if not n.endswith("/")][:20]
        if not names:
            return None
        return "Archive containing: " + ", ".join(names[:12])
    except zipfile.BadZipFile:
        return None


def _clean(text: str) -> str | None:
    text = re.sub(r"\s+", " ", text).strip()
    return text[:PEEK_CHARS] if text else None


# ---------------------------------------------------------------------------
# download-batch — trigger OneDrive Files On Demand downloads up to a size cap
# ---------------------------------------------------------------------------

_UF_DATALESS = 0x40000000  # macOS flag set by NSFileProvider on not-yet-downloaded files

# Windows reparse/offline attributes signalling a not-yet-materialised placeholder.
_WIN_RECALL_ON_DATA_ACCESS = 0x00400000  # FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS
_WIN_OFFLINE              = 0x00001000  # FILE_ATTRIBUTE_OFFLINE


def _listxattr_names(path: Path) -> bytes:
    """Return the file's raw extended-attribute name table (NUL-separated bytes),
    read in-process — never forks an `xattr` subprocess.

    macOS CPython does NOT expose os.listxattr (that's Linux-only), so on darwin we
    call libc listxattr(2) directly via ctypes. Returns b'' on any error. We only
    need the NAMES (the dataless marker's presence is the signal), so a substring
    search over this blob is sufficient — no per-name getxattr needed.
    """
    if hasattr(os, "listxattr"):
        # Linux (and any platform where CPython exposes it).
        try:
            names = os.listxattr(path, follow_symlinks=False)
        except OSError:
            return b""
        return b"\x00".join(
            (n.encode("utf-8", "surrogateescape") if isinstance(n, str) else n)
            for n in names
        )
    if sys.platform == "darwin":
        import ctypes
        try:
            libc = ctypes.CDLL("libc.dylib", use_errno=True)
        except OSError:
            return b""
        cpath = os.fsencode(str(path))
        XATTR_NOFOLLOW = 0x0001
        # First call with NULL buffer to get the required size.
        size = libc.listxattr(cpath, None, ctypes.c_size_t(0), XATTR_NOFOLLOW)
        if size <= 0:
            return b""
        buf = ctypes.create_string_buffer(size)
        got = libc.listxattr(cpath, buf, ctypes.c_size_t(size), XATTR_NOFOLLOW)
        if got <= 0:
            return b""
        return buf.raw[:got]
    return b""


def _is_placeholder(path: Path) -> bool:
    """
    Is this file a cloud-only placeholder (bytes not materialised locally)?

    Cross-platform, in-process — never forks a per-file `xattr` subprocess (that
    leaked processes and added a fork per file across a large drive).

      * macOS (darwin): authoritative dataless detection. We read the file's
        FileProvider xattr markers via os.listxattr/os.getxattr in-process, and
        treat UF_DATALESS in st_flags as an additional signal. st_blocks==0 is
        deliberately NOT used alone — APFS clones and transparently-compressed
        files legitimately report zero blocks while being fully local.
      * Windows (win32): placeholder when st_file_attributes has
        FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS or FILE_ATTRIBUTE_OFFLINE set.
      * Linux/other: no reliable provider signal → treat as local (False).

    Returns False on error (treat as local rather than risk a spurious download).
    """
    plat = sys.platform

    if plat == "darwin":
        try:
            st = os.stat(path)
        except OSError:
            return False
        dataless_flag = bool(getattr(st, "st_flags", 0) & _UF_DATALESS)
        # Signal 1: BSD dataless flag — authoritative on its own.
        if dataless_flag:
            return True
        # Signal 2: FileProvider provider markers in the xattr name table, read
        # in-process. The dataless/itemState markers are dispositive; OneDrive/fpfs
        # markers also appear on local files, so those only count alongside the flag
        # (which we already know is unset here, so they alone never trigger).
        names_blob = _listxattr_names(path)
        if not names_blob:
            return False
        for marker in (b"com.apple.fileprovider.dataless#N",
                       b"com.apple.cloud.itemState"):
            if marker in names_blob:
                return True
        return False

    if plat == "win32":
        import stat as _stat
        try:
            st = os.stat(path)
        except OSError:
            return False
        attrs = getattr(st, "st_file_attributes", 0)
        recall = getattr(_stat, "FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS",
                         _WIN_RECALL_ON_DATA_ACCESS)
        offline = getattr(_stat, "FILE_ATTRIBUTE_OFFLINE", _WIN_OFFLINE)
        return bool(attrs & (recall | offline))

    # Linux / other: no provider signal available — treat as local.
    return False


def cmd_download_batch(args):
    drive = Path(args.path).expanduser() if args.path else _EFFECTIVE_ROOT
    cap_gb = float(args.limit_gb) if args.limit_gb else 20.0
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
    if REGISTRY_DB.exists():
        conn = None
        try:
            conn = sqlite3.connect(str(REGISTRY_DB))
            conn.row_factory = sqlite3.Row
            organized_paths = {
                r["current_path"]
                for r in conn.execute(
                    "SELECT current_path FROM files WHERE status='organized'"
                ).fetchall()
            }
        except Exception:
            pass
        finally:
            if conn is not None:
                conn.close()

    print(f"Scanning for online-only files (cap: {cap_gb:.0f} GB)...")
    print()

    # Two-phase download: known folders first, x-folders second.
    for phase in (1, 2):
        if at_cap:
            break

        for root, dirs, files in os.walk(drive):
            if at_cap:
                break
            root_path = Path(root)

            # Never descend external (shared) or atomic-unit folders at any depth —
            # same opacity contract as scan. Pruned first so the top-level x/hidden
            # filters below operate on the already-cleaned dir list.
            dirs[:] = [d for d in dirs
                       if d not in _locked_atomic
                       and not _atomic_marker(root_path / d)
                       and not _is_external(root_path / d)]

            rel = root_path.relative_to(drive)
            top_level = rel.parts[0] if rel.parts else ""

            if top_level.startswith("."):
                dirs.clear()
                continue

            if not top_level:
                if phase == 1:
                    dirs[:] = [d for d in dirs if not d.startswith("x") and not d.startswith(".")]
                else:
                    dirs[:] = [d for d in dirs if d.startswith("x")]
                continue

            if phase == 1 and top_level.startswith("x"):
                dirs.clear()
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
    This makes any folder Vaidehi creates manually visible to classification
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
        # Skip x-prefixed top-level folders and hidden dirs
        if parts[0].startswith("x") or parts[0].startswith("."):
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
        data = json.loads(rules_file.read_text())
        for rule in data.get("rules", []):
            top = rule.get("folderName", "").split("/")[0].strip()
            if top:
                conn.execute(
                    """INSERT INTO path_vocab (segment, position, use_count) VALUES (?,1,1)
                       ON CONFLICT(segment, position) DO UPDATE SET use_count = use_count + 1""",
                    (top,)
                )
        conn.commit()
    except Exception:
        pass


def cmd_scan(args):
    drive = Path(args.path).expanduser() if args.path else _EFFECTIVE_ROOT
    if not drive.exists():
        sys.exit(f"Error: root path not found: {drive}")

    file_limit = getattr(args, "limit", None) or 250
    gb_limit = float(getattr(args, "limit_gb", None) or 20.0)
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

    organized_paths: set[str] = {
        r["current_path"]
        for r in conn.execute(
            "SELECT current_path FROM files WHERE status='organized'"
        ).fetchall()
    }

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
    #   1 = known folder, downloaded     2 = known folder, cloud (needs download)
    #   3 = loose root, downloaded       4 = loose root, cloud
    #   5 = x-folder, downloaded         6 = x-folder, cloud
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
            is_xfolder = entry.name.startswith("x")
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
                              and not _atomic_marker(root_path / d)
                              and not _is_external(root_path / d)]
                for fname in files:
                    filepath = root_path / fname
                    ok, fsize = eligible(filepath)
                    if not ok:
                        continue
                    placeholder = _is_placeholder(filepath)
                    if is_xfolder:
                        bucket = 6 if placeholder else 5
                    else:
                        bucket = 2 if placeholder else 1
                    buckets[bucket].append((filepath, fsize, placeholder))

    # ------------------------------------------------------------------
    # PROCESSING: walk priorities 1→6, hashing files (triggering
    # downloads inline for cloud-only ones) until the cap is hit.
    # ------------------------------------------------------------------
    stopped_at_priority: int | None = None
    priority_labels = {
        1: "known-folder downloaded", 2: "known-folder cloud",
        3: "loose root downloaded",   4: "loose root cloud",
        5: "x-folder downloaded",     6: "x-folder cloud",
    }

    # W4 skip-rehash: index existing rows so an unchanged file (same path + size +
    # mtime, with a stored hash) is never re-hashed or re-peeked — the big re-scan win.
    existing_index = {}
    for r in conn.execute("SELECT current_path, sha256, file_size, mtime FROM files"):
        existing_index[r["current_path"]] = (r["sha256"], r["file_size"], r["mtime"])

    unchanged = 0
    to_process = []  # (filepath, fsize, mtime) — files that genuinely need hashing

    # Pass 1 (sequential): respect caps, trigger cloud downloads, and decide which
    # files still need a fresh hash. Skip-rehash drops unchanged files here.
    for priority in range(1, 7):
        if stopped_at_priority:
            break
        files = sorted(buckets[priority], key=lambda x: str(x[0]))
        for filepath, fsize, placeholder in files:
            if len(to_process) >= file_limit:
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
            # Admit at least one file even if it alone exceeds the GB cap — otherwise a
            # single file larger than the cap is rejected on every scan and never gets
            # processed (permanent stall). Once anything is admitted, the cap applies.
            if total_bytes + fsize > byte_limit and to_process:
                stopped_at_priority = priority
                break

            # Trigger download if cloud-only — open() forces OneDrive to materialise.
            if placeholder:
                try:
                    with open(filepath, "rb") as f:
                        f.read(1)
                except OSError as e:
                    print(f"  skip {filepath}: download failed: {e}", file=sys.stderr)
                    skipped += 1
                    continue
                # Poll until the file materialises (or times out) instead of a
                # single fixed 0.5s check — a file slower than one tick used to be
                # skipped and deferred to a future scan, forcing extra passes.
                if _is_placeholder(filepath):
                    _wstart = time.monotonic()
                    waited = 0.0
                    while _is_placeholder(filepath) and waited < DOWNLOAD_POLL_TIMEOUT:
                        time.sleep(DOWNLOAD_POLL_INTERVAL)
                        waited += DOWNLOAD_POLL_INTERVAL
                    t_download += time.monotonic() - _wstart

                # Never hash a partially-downloaded file. Confirm it is (a) no longer
                # dataless AND (b) byte-stable across two reads — a still-streaming
                # OneDrive file can clear the dataless flag while its size is still
                # climbing. If unconfirmed, defer to a future scan rather than commit
                # a hash of partial bytes.
                if _is_placeholder(filepath):
                    print(f"  skip {filepath}: still online-only after {DOWNLOAD_POLL_TIMEOUT:.0f}s", file=sys.stderr)
                    skipped += 1
                    continue
                try:
                    s1 = filepath.stat()
                    time.sleep(DOWNLOAD_POLL_INTERVAL)
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
                fsize = s2.st_size
                cur_mtime = s2.st_mtime_ns
                triggered_count += 1

            to_process.append((filepath, fsize, cur_mtime))
            total_bytes += fsize

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

    # Detect root-level folders that have no rules (not x-prefixed, not staging, no .tidy-rules.json)
    unknown_folders = []
    for entry in sorted(drive.iterdir()):
        if not entry.is_dir():
            continue
        if should_skip(entry) or entry.name.startswith(".") or entry.name.startswith("x"):
            continue
        if entry.name in PARA_ROOTS:
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
        print("  → Create .tidy-rules.json for these before running propose.")
    export_csv()


# ---------------------------------------------------------------------------
# propose
# ---------------------------------------------------------------------------

def _tokens_from(text: str, minlen: int = 4) -> set:
    return {t.lower() for t in re.split(r"[^A-Za-z0-9]+", text or "") if len(t) >= minlen}


def _build_rules_index(root: Path) -> tuple:
    """Build a lightweight index of every rule destination for the auto-classify
    fast-path: a list of {dest, tokens, neg} plus the set of all known destination
    paths. tokens are distinctive lowercased terms from the folderName + the rule's
    signal (len>=4) PLUS the entity's aliases (len>=3, so short forms like 'ish'
    route) from entities.json. neg = the entity's negative tokens (learned from
    rejections) that suppress a match (W5)."""
    entities_meta = _read_entities(root)
    index, dest_set = [], set()
    for rules_file in sorted(root.rglob(".tidy-rules.json")):
        parent = rules_file.parent
        try:
            rel_parent = parent.relative_to(root)
        except Exception:
            continue
        parent_disp = "" if str(rel_parent) == "." else str(rel_parent)
        try:
            data = json.loads(rules_file.read_text())
        except Exception:
            continue
        rule_list = data.get("rules", []) if isinstance(data, dict) else data
        if not isinstance(rule_list, list):
            continue
        for r in rule_list:
            if not isinstance(r, dict):
                continue
            folder = r.get("folderName")
            if not folder:
                continue
            dest = (f"{parent_disp}/{folder}" if parent_disp else folder).strip("/")
            # Normalise the grouping (first) segment to its canonical case so two
            # rules differing only in grouping case ('Personal/...' vs 'PERSONAL/...')
            # collapse to one destination — otherwise the auto-classify matcher reads
            # them as competing destinations and (wrongly) falls through as ambiguous.
            dest = _normalize_grouping(dest)
            dest_set.add(dest)
            leaf = folder.split("/")[-1]
            meta = entities_meta.get(leaf, {}) if isinstance(entities_meta, dict) else {}
            signal = _signal_from_description(r.get("description", ""), folder)
            tokens = _tokens_from(folder + " " + signal)
            for a in meta.get("aliases", []) or []:           # aliases route too (len>=3)
                tokens |= _tokens_from(a, minlen=3)
            neg = set()
            for n in meta.get("negative", []) or []:          # learned-from-rejection (W5)
                neg |= _tokens_from(n, minlen=3)
            if tokens:
                index.append({"dest": dest, "tokens": tokens, "neg": neg})
    return index, dest_set


def _infer_signal_from_filenames(names: list, top: int = 6) -> list:
    """Auto-infer a rule's signal: the distinctive tokens common to >=2 of the
    approved files routed to a folder (W5 — so the learning loop writes a real
    signal, not just the folder name). Returns up to `top` tokens."""
    from collections import Counter
    c = Counter()
    for n in names:
        for t in _tokens_from(Path(n).stem):
            c[t] += 1
    return [t for t, k in c.most_common(top) if k >= 2]


def _auto_classify_entry(entry: dict, root: Path, index: list, dest_set: set) -> tuple:
    """Deterministically route an unambiguous pending file WITHOUT the classifier.
    Returns (dest_subfolder, reason) or (None, None) when the file is ambiguous and
    must fall through to classification. Conservative by design: only fires on a
    file already living in the organized tree, or a SINGLE unambiguous token match."""
    groupings = _active_groupings()
    cur = Path(entry["current_path"])
    try:
        rel_dir = cur.parent.relative_to(root)
    except Exception:
        rel_dir = None

    # 1. Already in the organized tree (scan priority P1): a file sitting under an
    #    active grouping, not in _Inbox / Archive / a loose root / an x-folder, is
    #    already correctly placed — auto-route it to stay (just register it).
    if rel_dir is not None and rel_dir.parts:
        parts = rel_dir.parts
        in_tree = (parts[0] in groupings
                   and "_Inbox" not in parts and "Archive" not in parts
                   and not any(p.startswith("x") for p in parts))
        if in_tree:
            return str(rel_dir), "already in ruled folder"

    # 2. Unambiguous filename token match: route only if every matching rule points
    #    to the SAME destination (competing destinations => ambiguous => classifier).
    fname = (entry.get("filename") or "").lower()
    if fname:
        # Only tokens of length>=3 (drop empty strings too) can drive an auto-route:
        # a single short/empty token must not trigger an over-confident match.
        ftok = {t for t in re.split(r"[^a-z0-9]+", fname) if len(t) >= 3}
        # match a dest when its tokens hit AND none of its negative tokens hit (W5)
        matched = {e["dest"] for e in index
                   if (e["tokens"] & ftok) and not (e.get("neg") and e["neg"] & ftok)}
        if len(matched) == 1:
            return next(iter(matched)), "unambiguous filename match"
    return None, None


def cmd_propose(args):
    limit = int(args.limit)
    conn = get_db()
    rows = conn.execute(
        """SELECT id, current_path, filename, extension, file_size, file_date, content_peek
           FROM files WHERE status = 'pending' ORDER BY id LIMIT ?""",
        (limit,)
    ).fetchall()
    conn.close()

    if not rows:
        print("No pending files. Run 'scan' first or all files are already classified.")
        return

    cfg = _read_user_config()
    # W1 — auto-classify fast-path toggle: config.json auto_classify (default True),
    # overridable per-run with --no-auto-classify / --auto-classify.
    auto_on = cfg.get("auto_classify", True)
    if getattr(args, "no_auto_classify", False):
        auto_on = False
    if getattr(args, "auto_classify", False):
        auto_on = True
    # W5 — confidence auto-approval: when opted in (config.json auto_approve, default
    # OFF for safety), high-confidence auto-routed files are marked auto_approved so
    # the orchestrator may execute them without a viewer pass (still CSV-audited).
    auto_approve = cfg.get("auto_approve", False)
    if getattr(args, "auto_approve", False):
        auto_approve = True

    # W1b — cost toggles: skip the expensive content/vision read for some files.
    # vision (default on), skip_types (extensions), skip_over_mb (size cap). Config
    # values, each overridable per-run. A "blocked-open" file is never opened: it's
    # routed deterministically by the W1 matcher, or sent to the classifier with a
    # route_by_name_only flag (filename + path only), or falls to _Inbox.
    vision_on = cfg.get("vision", True)
    if getattr(args, "no_vision", False):
        vision_on = False
    skip_types = set(str(t).lower() for t in cfg.get("skip_types", []))
    if getattr(args, "skip_types", None):
        skip_types |= {t.strip().lower() for t in args.skip_types.split(",") if t.strip()}
    skip_types = {(t if t.startswith(".") else "." + t) for t in skip_types}
    skip_over_mb = getattr(args, "skip_over_mb", None)
    if skip_over_mb is None:
        skip_over_mb = cfg.get("skip_over_mb")
    skip_over_bytes = float(skip_over_mb) * 1024 * 1024 if skip_over_mb else None

    root = Path(_EFFECTIVE_ROOT)
    need_index = auto_on or (not vision_on) or bool(skip_types) or bool(skip_over_bytes)
    index, dest_set = (_build_rules_index(root) if need_index else ([], set()))
    auto_log = []

    def _open_blocked(e: dict) -> list:
        reasons = []
        if e["is_image"] and not vision_on:
            reasons.append("vision-off")
        if e["extension"] in skip_types:
            reasons.append("skip-type")
        if skip_over_bytes and (e["file_size"] or 0) > skip_over_bytes:
            reasons.append(f">{skip_over_mb:g}MB")  # :g => 200 not 200.0
        return reasons

    result = []
    for row in rows:
        ext = (row["extension"] or "").lower()
        entry = {
            "id":           row["id"],
            "current_path": row["current_path"],
            "filename":     row["filename"],
            "extension":    ext,
            "file_size":    row["file_size"],
            "file_date":    row["file_date"],
            "is_image":     ext in IMAGE_EXTS,
            "content_peek": row["content_peek"],  # None for images; text for everything else
            "auto_routed":  False,
        }
        blocked = _open_blocked(entry)
        dest = reason = None
        if auto_on:
            dest, reason = _auto_classify_entry(entry, root, index, dest_set)
        elif blocked and index:
            # Even with the fast-path off, a file we're not allowed to OPEN still
            # gets a deterministic destination from the matcher when one exists.
            dest, reason = _auto_classify_entry(entry, root, index, dest_set)
            if reason:
                reason = "skipped-open; " + reason
        if dest:
            entry["auto_routed"] = True
            # Write the canonical routing field `para_subfolder` (the viewer, bubble-sort,
            # and execute all read THIS) so an auto-routed entry merged unchanged reaches
            # them with its destination intact. `proposed_subfolder` is kept as a readable
            # alias of the same value.
            routed = _normalize_grouping(dest)
            entry["para_subfolder"] = routed
            entry["proposed_subfolder"] = routed
            entry["auto_reason"] = reason
            if auto_approve:
                entry["auto_approved"] = True
            auto_log.append((row["id"], row["filename"], routed, reason))
        else:
            entry["needs_classification"] = True
            if blocked:
                # Respect the skip: do not hand the classifier the file content.
                entry["route_by_name_only"] = True
                entry["open_blocked_reason"] = blocked
                entry["content_peek"] = None
        result.append(entry)

    # W1b — partition the to-classify residual into batches of BATCH for the fan-out:
    # the skill dispatches one classification sub-agent per classify_batch, briefed
    # with file PATHS (not inlined content). auto_routed files carry no batch.
    to_classify = [e for e in result if e.get("needs_classification")]
    for i, e in enumerate(to_classify):
        e["classify_batch"] = i // BATCH
    n_batches = (len(to_classify) + BATCH - 1) // BATCH

    # Audit trail: every auto-route is appended to <root>/.organizer/auto-routed.csv
    # so the user can see exactly what was decided deterministically (never opaque).
    if auto_log:
        import csv as _csv
        audit = root / ".organizer" / "auto-routed.csv"
        audit.parent.mkdir(parents=True, exist_ok=True)
        new = not audit.exists()
        with open(audit, "a", newline="", encoding="utf-8") as f:
            w = _csv.writer(f)
            if new:
                w.writerow(["timestamp", "id", "filename", "destination", "reason"])
            ts = datetime.now().isoformat(timespec="seconds")
            for rid, fn, dest, reason in auto_log:
                w.writerow([ts, rid, fn, dest, reason])
        print(f"Auto-classified {len(auto_log)}/{len(rows)} files (fast-path) — "
              f"{len(rows) - len(auto_log)} need classification. Audit: {audit}", file=sys.stderr)

    name_only = sum(1 for e in to_classify if e.get("route_by_name_only"))
    print(f"To classify: {len(to_classify)} file(s) in {n_batches} batch(es) of {BATCH} "
          f"(fan-out one sub-agent per classify_batch){'; ' + str(name_only) + ' route-by-name-only (open blocked)' if name_only else ''}.",
          file=sys.stderr)

    # Write project-metadata sidecar so Claude can look up filename_tag and
    # production_period for each known project when classifying.
    metadata = _enumerate_project_metadata(_EFFECTIVE_ROOT)
    sidecar = Path.home() / ".claude" / "drive-organizer" / "project_metadata.json"
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(sidecar, json.dumps(metadata, indent=2))
    print(f"Project metadata sidecar: {sidecar} ({len(metadata)} projects)", file=sys.stderr)

    print(json.dumps(result, indent=2))


# ---------------------------------------------------------------------------
# execute
# ---------------------------------------------------------------------------

def cmd_execute(args):
    approved_path = Path(args.approved)
    if not approved_path.exists():
        sys.exit(f"Error: approved file not found: {approved_path}")

    with open(approved_path) as f:
        approved = json.load(f)

    if not approved:
        print("Approved list is empty.")
        return

    drive = _EFFECTIVE_ROOT
    conn = get_db()
    moved = errors = 0

    # --- Crash-recovery move journal (BL-A: move-then-commit crash window) ----------
    # A crash BETWEEN shutil.move and the registry UPDATE+commit would leave a file
    # at its new location but the registry pointing at the old path. To make that
    # window recoverable we keep a tiny sidecar journal: before each move we record
    # {id, src, dest}; we move; we UPDATE+commit; then we clear the journal entry.
    # On start, a non-empty journal is reconciled — if the file is already at `dest`
    # the move happened (fix the registry row); if it is still at `src` we leave it
    # for the normal pass to re-move.
    journal_path = drive / ".organizer" / ".move-journal.json"

    def _read_journal() -> dict:
        try:
            data = json.loads(journal_path.read_text())
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _write_journal_entry(jid, jsrc, jdest):
        journal_path.parent.mkdir(parents=True, exist_ok=True)
        j = _read_journal()
        j[str(jid)] = {"id": jid, "src": jsrc, "dest": jdest}
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
                # The move completed but the registry may not have been updated.
                conn.execute(
                    "UPDATE files SET current_path=?, processed_at=? WHERE id=?",
                    (str(jdest), datetime.now().isoformat(), rec.get("id"))
                )
                conn.commit()
                print(f"  RECOVERED: journal entry id {rec.get('id')} -> {jdest}", file=sys.stderr)
                _clear_journal_entry(jid)
            elif jsrc.exists():
                # File still at source — the move never happened; leave for re-move.
                _clear_journal_entry(jid)
            else:
                # Neither src nor dest present — nothing safe to do; drop the stale entry.
                _clear_journal_entry(jid)

    for entry in approved:
        file_id     = entry["id"]
        src         = Path(entry["current_path"])
        action      = entry.get("action", "approved")
        subfolder   = _normalize_grouping(entry.get("para_subfolder", ""))
        # Derive the top-level grouping from the path when the entry carries no
        # para_category (e.g. reclassified-rejected entries Claude rewrote with only
        # para_subfolder updated) — so the registry column is never stale/_Inbox.
        # Derive deterministically from the normalised subfolder's first segment, and
        # fall back to _Inbox whenever that segment is not a real active grouping.
        category    = entry.get("para_category")
        if not category:
            first_seg = _normalize_grouping(subfolder).split("/")[0] if subfolder else ""
            category = first_seg if first_seg in _active_groupings() else "_Inbox"
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
        dest_dir = _safe_dest(drive, sub_rel)
        if dest_dir is None:
            print(f"  ERROR: unsafe destination subfolder {sub_rel!r} for {src} — skipped.",
                  file=sys.stderr)
            errors += 1
            continue
        dest_dir.mkdir(parents=True, exist_ok=True)
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

        # Journal the intent BEFORE moving so a crash in the move-then-commit window
        # is recoverable on the next run.
        _write_journal_entry(file_id, str(src), str(dest))
        try:
            shutil.move(str(src), str(dest))
        except OSError as e:
            print(f"  ERROR moving {src}: {e}", file=sys.stderr)
            _clear_journal_entry(file_id)   # move never happened — drop the intent
            errors += 1
            continue

        new_status = "to_delete" if action == "delete" else "organized"
        conn.execute(
            """UPDATE files SET
               current_path=?, para_category=?, para_subfolder=?,
               vision_desc=?, file_date=COALESCE(?,file_date),
               status=?, processed_at=?
               WHERE id=?""",
            (str(dest), category, subfolder, vision_desc,
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

        # Expand the destination project's production_period to include
        # this file's date. Initialises the period on first approval; widens
        # it (with one-month buffer) on subsequent approvals. Skipped for
        # action='delete' (file went to Archive/_To Delete) or when file_date
        # is unknown.
        if action != "delete" and file_date:
            project_dir = _find_project_for_destination(subfolder, drive)
            if project_dir is not None:
                try:
                    _expand_production_period(project_dir, file_date)
                except Exception as e:
                    print(f"  WARN: could not update production_period for {project_dir.name}: {e}",
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

def _pick_keeper(files: list) -> dict:
    """Choose the 'keeper' from a duplicate group — the best-placed copy to keep
    in place. `files` is a list of dicts with at least 'id', 'path', 'status'.
    Prefer organized status, then a path outside _Inbox/Archive, then the
    most-specific (deepest) path."""
    def score(r):
        p = r.get("path") or ""
        organized = 1 if r.get("status") == "organized" else 0
        not_staging = 0 if ("/_Inbox/" in p or "/Archive/" in p) else 1
        depth = min(p.count("/"), 20)   # cap depth so a deeply-nested staging path
                                        # can never out-rank a real destination
        # Tuple ordering: prefer organized, then non-staging, then deeper, then the
        # lowest id as a deterministic final tiebreak (input order is not guaranteed
        # stable). NOTE: the keeper is chosen with max(), so the id term is NEGATED
        # (-id) — a smaller id yields a larger -id, so max() lands on the lowest id.
        return (organized, not_staging, depth, -int(r.get("id", 0)))
    return max(files, key=score)


def cmd_duplicates(args):
    conn = get_db()

    # --colocate ID (or the deprecated --archive ID): move this duplicate so it sits
    # BESIDE the group's keeper, renamed <keeper-stem>_dupN, instead of being archived.
    target = getattr(args, "colocate", None)
    if target is None:
        target = getattr(args, "archive", None)   # deprecated alias — now co-locates too
    if target is not None:
        row = conn.execute("SELECT * FROM files WHERE id=?", (target,)).fetchone()
        if not row:
            conn.close(); sys.exit(f"File id {target} not found in registry.")
        src = Path(row["current_path"])
        if not src.exists():
            conn.close(); sys.exit(f"File not found on disk: {src}")
        # Use the SAME status filter as the main keeper selection below so the keeper
        # chosen here matches the one the user reviewed in the duplicates listing —
        # an unfiltered query could include rows the listing excluded and pick a
        # different keeper, co-locating beside a copy the user never saw.
        group = conn.execute(
            "SELECT id, current_path, status FROM files "
            "WHERE sha256=? AND sha256 IS NOT NULL "
            "AND status IN ('organized','pending','duplicate')",
            (row["sha256"],)
        ).fetchall()
        if len(group) < 2:
            conn.close(); sys.exit(f"File id {target} has no duplicates in the registry.")
        group_files = [{"id": g["id"], "path": g["current_path"], "status": g["status"]} for g in group]
        keeper = _pick_keeper(group_files)
        if keeper["id"] == target:
            conn.close()
            sys.exit(f"File id {target} is the keeper (best-placed copy of this group); "
                     f"co-locate a different copy instead.")
        keeper_path = Path(keeper["path"])
        # Verify the keeper actually exists on disk before co-locating beside it —
        # if it has been moved/deleted out from under the registry, co-locating into
        # a phantom directory would strand the duplicate. Abort cleanly instead.
        if not keeper_path.exists():
            conn.close()
            sys.exit(f"Keeper id {keeper['id']} not found on disk: {keeper_path}. "
                     f"Re-run duplicates to refresh the registry before co-locating.")
        keeper_dir = keeper_path.parent
        keeper_dir.mkdir(parents=True, exist_ok=True)
        # next _dupN beside the keeper, using the keeper's stem so they sort adjacent
        n = 1
        while (keeper_dir / f"{keeper_path.stem}_dup{n}{src.suffix}").exists():
            n += 1
        dest = keeper_dir / f"{keeper_path.stem}_dup{n}{src.suffix}"
        try:
            shutil.move(str(src), str(dest))
        except OSError as e:
            conn.close()
            sys.exit(f"Failed to co-locate id {target} ({src} -> {dest}): {e}")
        conn.execute(
            "UPDATE files SET current_path=?, status='duplicate', processed_at=? WHERE id=?",
            (str(dest), datetime.now().isoformat(), target)
        )
        conn.commit()
        conn.close()
        print(f"Co-located dup id {target} → {dest}  (beside keeper id {keeper['id']}: {keeper_path})")
        export_csv()
        return

    # Group in Python rather than via parallel GROUP_CONCAT calls: SQLite's
    # GROUP_CONCAT gives no cross-column ordering guarantee AND silently omits
    # NULLs, so a single NULL file_size used to shift every later column and
    # zip() mis-paired id/path/size — co-locating the wrong file. Per-row
    # grouping is exact.
    from collections import defaultdict
    by_hash: dict = defaultdict(list)
    for row in conn.execute(
        """SELECT id, sha256, current_path, file_size, file_date, status
           FROM files
           WHERE sha256 IS NOT NULL
             AND status IN ('organized','pending','duplicate')"""
    ):
        by_hash[row["sha256"]].append({
            "id": row["id"], "path": row["current_path"],
            "size": row["file_size"], "date": row["file_date"],
            "status": row["status"],
        })
    conn.close()

    groups = []
    for sha, files in by_hash.items():
        if len(files) < 2:
            continue
        files.sort(key=lambda f: f["id"])   # stable, readable order
        keeper = _pick_keeper(files)
        groups.append({
            "sha256": sha[:16] + "...",
            "_sha_full": sha,                   # full digest, used only for a stable sort
            "keeper_id": keeper["id"],          # the copy to keep in place; co-locate the rest
            "files": files,
        })

    if not groups:
        print("No exact duplicates found.")
        return

    # Sort by the FULL sha256 — the truncated display string ('<16hex>...') collides
    # for any two groups sharing a 16-hex prefix, making the order non-deterministic.
    groups.sort(key=lambda g: g["_sha_full"])
    for g in groups:
        g.pop("_sha_full", None)
    print(json.dumps(groups, indent=2))


# ---------------------------------------------------------------------------
# variants
# ---------------------------------------------------------------------------

def cmd_variants(args):
    from collections import defaultdict

    conn = get_db()
    rows = conn.execute(
        """SELECT id, current_path, filename, extension, file_size, file_date
           FROM files WHERE status IN ('organized','pending')"""
    ).fetchall()
    conn.close()

    groups: dict[str, list] = defaultdict(list)

    for row in rows:
        fname = row["filename"] or ""
        ext   = (row["extension"] or "").lower()
        base  = Path(fname).stem                       # drop the extension FIRST, otherwise the
        base  = re.sub(r"^\d+[-_]\s*", "", base)       # $-anchored variant-token strip below can
        # Strip trailing variant tokens repeatedly — "report_final_v2" carries two,
        # and a single re.sub would leave one behind, splitting variants that should group.
        while True:
            stripped = re.sub(
                r"[\s_-]*(v\d+|final|copy|highlighted?|annotated?|marked?)$",
                "", base, flags=re.IGNORECASE
            )
            if stripped == base:
                break
            base = stripped
        base = base.lower().strip(" ._-")              # drop stray trailing separators/dots too
        key  = f"{ext}:{base}"
        groups[key].append({
            "id":        row["id"],
            "path":      row["current_path"],
            "filename":  fname,
            "file_size": row["file_size"],
            "file_date": row["file_date"],
        })

    variant_groups = []
    for key, members in groups.items():
        if len(members) < 2:
            continue
        # Do NOT drop a group because a member lacks file_size (missing => unknown
        # => include it) and do NOT gate on a size ratio: a highlighted/annotated PDF
        # can legitimately exceed 2x the plain original, so a ratio cap would split
        # exactly the variant pairs this command exists to surface.
        # Stable, content-derived id — Python's builtin hash() is salted per process
        # (PYTHONHASHSEED), so it produced a different group_id every run and could
        # collide mod 100000. A hashlib digest of the key is deterministic. (sha256,
        # not sha1 — the digest is just a grouping label, but sha256 matches the
        # file's other hashing and avoids the weak-crypto lint.)
        group_id = "grp_" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:10]
        variant_groups.append({"group_id": group_id, "key": key, "files": members})

    if not variant_groups:
        print("No variant groups found.")
        return

    conn = get_db()
    for group in variant_groups:
        for member in group["files"]:
            conn.execute(
                "UPDATE files SET variant_group=? WHERE id=?",
                (group["group_id"], member["id"])
            )
    conn.commit()
    conn.close()

    print(json.dumps(variant_groups, indent=2))


# ---------------------------------------------------------------------------
# merge
# ---------------------------------------------------------------------------

def _copy_pdf_annot(src, page_dst) -> bool:
    """Re-create a source annotation on the destination page. PyMuPDF has no direct
    cross-document annot copy (the old `page.add_annot(annot)` call is invalid and
    silently fails), so we rebuild the common markup types from the source's
    geometry + colour + content. Returns True if an annotation was created."""
    import fitz
    t = src.type[0]
    quad_types = {
        fitz.PDF_ANNOT_HIGHLIGHT: "add_highlight_annot",
        fitz.PDF_ANNOT_UNDERLINE: "add_underline_annot",
        fitz.PDF_ANNOT_STRIKE_OUT: "add_strikeout_annot",
        fitz.PDF_ANNOT_SQUIGGLY: "add_squiggly_annot",
    }
    try:
        if t in quad_types:
            # Quad-based markup must be created from QUADS, not the flat vertices
            # list. Prefer src.quads (already grouped 4 points per quad); fall back
            # to reconstructing quads from src.vertices in groups of 4. Passing the
            # flat vertices as quads= is wrong and silently drops the annotation.
            quads = getattr(src, "quads", None)
            if not quads:
                verts = list(src.vertices or [])
                quads = [verts[i:i + 4] for i in range(0, len(verts) - 3, 4)]
            if not quads:
                return False
            new = getattr(page_dst, quad_types[t])(quads=quads)
        elif t == fitz.PDF_ANNOT_TEXT:
            new = page_dst.add_text_annot(src.rect.tl, (src.info or {}).get("content", ""))
        elif t == fitz.PDF_ANNOT_FREE_TEXT:
            new = page_dst.add_freetext_annot(src.rect, (src.info or {}).get("content", ""))
        elif t == fitz.PDF_ANNOT_INK:
            new = page_dst.add_ink_annot(src.vertices)
        elif t == fitz.PDF_ANNOT_SQUARE:
            new = page_dst.add_rect_annot(src.rect)
        elif t == fitz.PDF_ANNOT_CIRCLE:
            new = page_dst.add_circle_annot(src.rect)
        else:
            return False
        try:
            colors = src.colors or {}
            if colors.get("stroke"):
                new.set_colors(stroke=colors["stroke"])
            if colors.get("fill"):
                new.set_colors(fill=colors["fill"])
            if src.opacity is not None and 0 <= src.opacity <= 1:
                new.set_opacity(src.opacity)
            content = (src.info or {}).get("content")
            if content:
                new.set_info(content=content)
            new.update()
        except Exception:
            pass
        return True
    except Exception:
        return False


def cmd_merge(args):
    try:
        import fitz
    except ImportError:
        sys.exit("PyMuPDF is not installed.\nInstall with:  pip install pymupdf")
    try:
        fitz.TOOLS.mupdf_display_errors(False)   # silence noisy non-fatal MuPDF internal warnings
    except Exception:
        pass

    group_id     = args.group
    canonical_id = int(args.canonical)
    drive     = _EFFECTIVE_ROOT
    conn         = get_db()

    canonical_row = conn.execute(
        "SELECT * FROM files WHERE id=?", (canonical_id,)
    ).fetchone()
    if not canonical_row:
        conn.close()
        sys.exit(f"Canonical file id {canonical_id} not found.")

    others = conn.execute(
        "SELECT * FROM files WHERE variant_group=? AND id != ?",
        (group_id, canonical_id)
    ).fetchall()

    if not others:
        print("No other files in this variant group.")
        conn.close()
        return

    canonical_path = Path(canonical_row["current_path"])
    if not canonical_path.exists():
        conn.close()
        sys.exit(f"Canonical file not found: {canonical_path}")

    try:
        doc_canonical = fitz.open(str(canonical_path))
    except Exception as e:
        conn.close()
        sys.exit(f"Could not open canonical PDF {canonical_path}: {e}\n"
                 f"Nothing was changed — no originals archived.")
    to_archive = []   # (id, other_path) — archived only AFTER a successful save

    for other_row in others:
        other_path = Path(other_row["current_path"])
        if not other_path.exists():
            print(f"  skip missing: {other_path}", file=sys.stderr)
            continue
        try:
            doc_other = fitz.open(str(other_path))
        except Exception as e:
            print(f"  skip {other_path}: {e}", file=sys.stderr)
            continue

        src_pages = len(doc_other)
        more_pages = src_pages > len(doc_canonical)

        src_annots = copied = 0
        for page_num in range(min(len(doc_canonical), len(doc_other))):
            page_src = doc_other[page_num]
            page_dst = doc_canonical[page_num]
            for annot in (page_src.annots() or []):
                src_annots += 1
                if _copy_pdf_annot(annot, page_dst):
                    copied += 1

        doc_other.close()

        # Safety (a): the source has MORE pages than the canonical, so any annotation
        # on its trailing pages can't be merged (those pages don't exist in canonical).
        # Archiving would silently drop them — keep the original in place instead.
        if more_pages:
            print(f"  WARNING: {other_path.name} has {src_pages} pages vs canonical "
                  f"{len(doc_canonical)} — trailing-page annotations cannot merge; "
                  f"left in place (not archived).", file=sys.stderr)
            continue

        # Safety (b): the no-data-loss guard compares COPIED to the SOURCE annotation
        # count. Any shortfall (copied < src_annots) is partial loss = loss — keep the
        # original. (Covers the all-failed case too.)
        if src_annots > 0 and copied < src_annots:
            print(f"  WARNING: {other_path.name} has {src_annots} annotation(s) but only "
                  f"{copied} could be copied — left in place (not archived) to avoid data loss.",
                  file=sys.stderr)
            continue

        to_archive.append((other_row["id"], other_path))

    # Persist the merged canonical FIRST. Never save(incremental=True) OVER the
    # canonical in place — a crash or error mid-write would corrupt the only copy.
    # Instead: save to a TEMP path, verify it re-opens, then os.replace() it over the
    # canonical atomically. Only once that succeeds do we archive the originals.
    import os as _os
    tmp_path = canonical_path.with_name(f".{canonical_path.name}.merge.tmp.{_os.getpid()}")

    def _save_to_tmp():
        # Prefer a non-incremental full save to the temp file (a temp file has no
        # existing bytes to append to, so incremental is not meaningful here).
        try:
            doc_canonical.save(str(tmp_path), incremental=False, encryption=0)
        except Exception:
            # Retry with deflate off in case the source is encrypted/linearised and
            # the first attempt raised — keep it simple, one fallback attempt.
            doc_canonical.save(str(tmp_path), incremental=False)

    try:
        _save_to_tmp()
        doc_canonical.close()
        # Verify the temp file re-opens (and has pages) before we trust it.
        _verify = fitz.open(str(tmp_path))
        if _verify.page_count < 1:
            _verify.close()
            raise RuntimeError("merged temp PDF has no pages")
        _verify.close()
        _os.replace(str(tmp_path), str(canonical_path))
    except Exception as e:
        try:
            doc_canonical.close()
        except Exception:
            pass
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass
        conn.close()
        sys.exit(f"Failed to save merged canonical {canonical_path}: {e}\n"
                 f"Canonical left untouched; no originals were archived — nothing lost.")

    archive_dir = drive / "Archive" / "_Merged-Originals"
    archive_dir.mkdir(parents=True, exist_ok=True)
    merged_count = 0
    archive_failures = 0
    for other_id, other_path in to_archive:
        dest = archive_dir / other_path.name
        n = 1
        while dest.exists():            # counter loop — a single `_dup` could clobber a prior archive
            dest = archive_dir / f"{other_path.stem}_dup{n}{other_path.suffix}"
            n += 1
        # Wrap each archive move so one failure doesn't abort the whole merge
        # mid-way (the canonical is already saved; the rest should still archive).
        try:
            shutil.move(str(other_path), str(dest))
        except OSError as e:
            print(f"  WARNING: could not archive original {other_path}: {e}", file=sys.stderr)
            archive_failures += 1
            continue
        conn.execute(
            "UPDATE files SET current_path=?, status='archived', processed_at=? WHERE id=?",
            (str(dest), datetime.now().isoformat(), other_id)
        )
        merged_count += 1

    conn.execute(
        "UPDATE files SET processed_at=? WHERE id=?",
        (datetime.now().isoformat(), canonical_id)
    )
    conn.commit()
    conn.close()

    print(f"Merge complete: {merged_count} files merged into {canonical_path.name}.")
    print(f"Originals archived to Archive/_Merged-Originals/")
    if archive_failures:
        print(f"  ({archive_failures} original(s) could not be archived — see warnings above; "
              f"left in place, not lost.)")
    export_csv()


# ---------------------------------------------------------------------------
# generate-viewer
# ---------------------------------------------------------------------------

_VIEWER_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Drive Organiser — Proposals</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
         font-size: 13px; background: #f4f5f7; color: #1a1a1a; }

  /* Header */
  #header { background: #1e2126; color: #e8e8e8; padding: 10px 20px;
            display: flex; align-items: center; gap: 16px; position: sticky;
            top: 0; z-index: 100; }
  #header h1 { font-size: 15px; font-weight: 600; flex: 1; }
  #progress-label { font-size: 13px; color: #aaa; white-space: nowrap; }
  #submit-btn { background: #2ea44f; color: #fff; border: none; border-radius: 5px;
                padding: 7px 18px; font-size: 13px; font-weight: 600; cursor: pointer; }
  #submit-btn:disabled { background: #444; color: #888; cursor: default; }
  #submit-btn:hover:not(:disabled) { background: #2c9b49; }

  /* Page tabs */
  #tabs { background: #2a2f38; padding: 6px 20px 0; display: flex; gap: 4px;
          overflow-x: auto; position: sticky; top: 44px; z-index: 99; }
  .tab { padding: 6px 14px; border-radius: 5px 5px 0 0; cursor: pointer;
         color: #aaa; background: #1e2126; font-size: 12px; white-space: nowrap;
         border: 1px solid #3a3f48; border-bottom: none; }
  .tab.active { background: #f4f5f7; color: #1a1a1a; font-weight: 600; }
  .tab:hover:not(.active) { background: #2e3440; }

  /* Page content */
  .page { display: none; padding: 16px 20px; }
  .page.active { display: block; }

  .page-actions { margin-bottom: 10px; }
  .approve-all-btn { background: #e6f4ea; border: 1px solid #34a853; color: #1a6b2e;
                     border-radius: 4px; padding: 5px 14px; cursor: pointer;
                     font-size: 12px; font-weight: 600; }
  .approve-all-btn:hover { background: #d0edda; }

  /* Table */
  table { width: 100%; border-collapse: collapse; background: #fff;
          border-radius: 7px; overflow: hidden;
          box-shadow: 0 1px 3px rgba(0,0,0,.08); }
  thead th { background: #f0f2f5; font-weight: 600; padding: 8px 10px;
             text-align: left; font-size: 12px; color: #555;
             border-bottom: 1px solid #dde1e7; }
  tbody tr { border-bottom: 1px solid #eef0f3; }
  tbody tr:last-child { border-bottom: none; }
  tbody tr.approved  { background: #e8f5e9; }
  tbody tr.rejected  { background: #fce8e6; }
  tbody tr.flagged   { background: #fff8e1; }
  tbody tr.inbox     { background: #f3e5f5; }
  tbody tr.delete    { background: #ffebee; }
  td { padding: 7px 10px; vertical-align: middle; }
  td.num  { color: #888; width: 36px; text-align: right; }
  td.from { color: #777; font-size: 11px; max-width: 120px;
            overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  td.orig { max-width: 180px; overflow: hidden; text-overflow: ellipsis;
            white-space: nowrap; font-family: monospace; font-size: 11px; }
  td.arrow { color: #bbb; width: 18px; text-align: center; }
  td.dest-cell { min-width: 270px; }
  td.newname { min-width: 180px; }
  td.actions { width: 115px; white-space: nowrap; }

  /* Path builder — 3 free-text segments with autocomplete */
  .path-builder { display: flex; align-items: center; gap: 2px; }
  .path-builder .seg { padding: 3px 5px; border: 1px solid #ccc; border-radius: 4px;
                        font-size: 12px; min-width: 0; background: #fff; }
  .path-builder .seg.seg1 { flex: 2.5; min-width: 90px; }
  .path-builder .seg.seg2 { flex: 1.8; min-width: 55px; }
  .path-builder .seg.seg3 { flex: 1.2; min-width: 40px; }
  .path-builder .sep { color: #bbb; font-size: 13px; flex-shrink: 0; padding: 0 1px; }

  /* New filename input */
  input.name-input { padding: 3px 6px; border: 1px solid #ccc; border-radius: 4px;
                     font-size: 12px; width: 100%; }

  /* Status buttons */
  .status-btn { border: 1px solid transparent; border-radius: 4px; padding: 3px 9px;
                cursor: pointer; font-size: 13px; background: #f0f0f0;
                color: #888; transition: background .1s; }
  .status-btn.approve { border-color: #34a853; }
  .status-btn.approve.active { background: #34a853; color: #fff; }
  .status-btn.reject  { border-color: #ea4335; }
  .status-btn.reject.active  { background: #ea4335; color: #fff; }
  .status-btn.flag    { border-color: #f9ab00; }
  .status-btn.flag.active    { background: #f9ab00; color: #fff; }
  .status-btn.inbox   { border-color: #9c27b0; }
  .status-btn.inbox.active   { background: #9c27b0; color: #fff; }
  .status-btn.delete  { border-color: #c62828; }
  .status-btn.delete.active  { background: #c62828; color: #fff; }
  .status-btn:hover { filter: brightness(0.95); }

  /* Post-submit banner */
  #submitted-banner { display: none; background: #e8f5e9; border: 1px solid #34a853;
                      border-radius: 7px; padding: 20px 24px; margin: 30px auto;
                      max-width: 500px; text-align: center; font-size: 15px;
                      color: #1a6b2e; font-weight: 600; }

  /* Group header rows — show destination grouping in the table */
  tr.group-header td { background: #eef3f8; color: #2c3e50; font-weight: 600;
                       padding: 8px 12px; font-size: 12px; border-top: 2px solid #c3d4e2;
                       border-bottom: 1px solid #c3d4e2; }
  tr.group-header .group-path { font-family: monospace; }
  tr.group-header .group-count { color: #6a7c91; margin-left: 8px; font-weight: 400; }
  tr.group-header.inbox td { background: #f3e5f5; color: #6a1b7a; border-top-color: #ce93d8; border-bottom-color: #ce93d8; }
  .approve-group-btn { background: #e6f4ea; border: 1px solid #34a853; color: #1a6b2e;
                       border-radius: 4px; padding: 2px 10px; cursor: pointer; font-size: 11px;
                       font-weight: 600; margin-left: 12px; }
  .approve-group-btn:hover { background: #d0edda; }
</style>
</head>
<body>

<div id="header">
  <h1 id="header-title">Drive Organiser — Proposals</h1>
  <span id="progress-label">0 / 0 approved</span>
  <button id="submit-btn" disabled onclick="submitAll()">Submit 0</button>
</div>

<datalist id="voc-1"></datalist>
<datalist id="voc-2"></datalist>
<datalist id="voc-3"></datalist>
<div id="tabs"></div>
<div id="pages"></div>
<div id="submitted-banner"></div>

<script>
// ---------- Data ----------
const VOCAB = __VOCAB_JSON__;
const PROPOSALS = __PROPOSALS_JSON__;
const PAGE_SIZE = 25;

// per-row state: { status, seg1, seg2, seg3, newName }
// status values: 'unset' | 'approved' | 'rejected' | 'inbox' | 'flagged'
// rejected = I got it wrong, reclassify using context
// inbox    = user needs to open it manually (EPS etc), confirmed _Inbox
const rowState = {};
const PROPOSAL_BY_ID = {};

PROPOSALS.forEach(p => {
  PROPOSAL_BY_ID[p.id] = p;
  rowState[p.id] = {
    status:  'unset',
    seg1:    p.seg1 || '_Inbox',
    seg2:    p.seg2 || '',
    seg3:    p.seg3 || '',
    newName: p.new_filename || p.filename,
  };
});

// ---------- Path helpers ----------
function destPath(id) {
  const st = rowState[id];
  return [st.seg1, st.seg2, st.seg3].map(slugify).filter(Boolean).join('/');
}

function isStagingPath(path) {
  // Single shared predicate for "this destination is a staging root, not a real
  // routed folder" — empty or any underscore-prefixed root (_Inbox, _To Delete,
  // _Duplicates, ...). Used by inferCategory AND the inbox row-styling so they
  // can never disagree.
  return !path || path.startsWith('_');
}

function inferCategory(path) {
  // para_category is the file's TOP-LEVEL GROUPING — the first segment of the
  // destination path (e.g. WORK/Ishan/finance -> WORK). Staging roots (_Inbox,
  // Archive) return themselves. (This is a registry column only; routing is by
  // para_subfolder. The old fixed Areas/Resources/Projects vocab was wrong.)
  if (isStagingPath(path)) return path || '_Inbox';
  return path.split('/')[0];
}

// ---------- Rendering ----------

function buildRow(p, globalIdx) {
  const st = rowState[p.id];
  const trClass = st.status === 'unset' ? '' : st.status;
  return `
<tr id="row-${p.id}" class="${trClass}">
  <td class="num">${globalIdx + 1}</td>
  <td class="from" title="${escHtml(p.current_path || '')}">${escHtml((p.current_path || '').split('/').slice(-2,-1)[0] || '')}</td>
  <td class="orig" title="${escHtml(p.filename)}">${escHtml(p.filename)}</td>
  <td class="arrow">→</td>
  <td class="dest-cell">
    <div class="path-builder">
      <input class="seg seg1" id="s1-${p.id}" type="text" list="voc-1"
             value="${escHtml(st.seg1)}" placeholder="folder"
             oninput="onSeg(${p.id})">
      <span class="sep">/</span>
      <input class="seg seg2" id="s2-${p.id}" type="text" list="voc-2"
             value="${escHtml(st.seg2)}" placeholder="sub"
             oninput="onSeg(${p.id})">
      <span class="sep">/</span>
      <input class="seg seg3" id="s3-${p.id}" type="text" list="voc-3"
             value="${escHtml(st.seg3)}" placeholder=""
             oninput="onSeg(${p.id})">
    </div>
  </td>
  <td class="newname">
    <input class="name-input" id="name-${p.id}" type="text"
           value="${escHtml(st.newName)}"
           oninput="onNameChange(${p.id}, this.value)">
  </td>
  <td class="actions">
    <button class="status-btn approve${st.status==='approved'?' active':''}"
            onclick="setStatus(${p.id},'approved')" title="Approve — move to proposed destination">✓</button>
    <button class="status-btn reject${st.status==='rejected'?' active':''}"
            onclick="setStatus(${p.id},'rejected')" title="Wrong — Claude will reclassify">✗</button>
    <button class="status-btn flag${st.status==='flagged'?' active':''}"
            onclick="setStatus(${p.id},'flagged')" title="No idea — Claude will peek and repropose">?</button>
    <button class="status-btn inbox${st.status==='inbox'?' active':''}"
            onclick="setStatus(${p.id},'inbox')" title="Inbox — I need to open this myself">📥</button>
    <button class="status-btn delete${st.status==='delete'?' active':''}"
            onclick="setStatus(${p.id},'delete')" title="Move to Archive/_To Delete (not permanently deleted)">🗑</button>
  </td>
</tr>`;
}

function buildGroupHeader(path, ids, isInbox) {
  const cls = 'group-header' + (isInbox ? ' inbox' : '');
  const safePath = escHtml(path || '(no destination)');
  const count = ids.length;
  const idsAttr = escHtml(JSON.stringify(ids));
  return `
<tr class="${cls}">
  <td colspan="7">
    → <span class="group-path">${safePath}</span>
    <span class="group-count">(${count} file${count === 1 ? '' : 's'})</span>
    <button class="approve-group-btn" onclick='approveGroup(${idsAttr})'>Approve group</button>
  </td>
</tr>`;
}

function buildPage(pageIdx) {
  const start = pageIdx * PAGE_SIZE;
  const slice = PROPOSALS.slice(start, start + PAGE_SIZE);

  // Walk the slice and emit group headers when para_subfolder changes
  let body = '';
  let i = 0;
  while (i < slice.length) {
    const groupPath = slice[i].para_subfolder || '';
    let j = i;
    while (j < slice.length && (slice[j].para_subfolder || '') === groupPath) j++;
    const isInbox = isStagingPath(groupPath);
    const groupIds = [];
    for (let k = i; k < j; k++) groupIds.push(slice[k].id);
    body += buildGroupHeader(groupPath, groupIds, isInbox);
    for (let k = i; k < j; k++) {
      body += buildRow(slice[k], start + k);
    }
    i = j;
  }

  return `
<div class="page" id="page-${pageIdx}">
  <div class="page-actions">
    <button class="approve-all-btn" onclick="approveAll(${pageIdx})">Approve all on this page</button>
  </div>
  <table>
    <thead>
      <tr>
        <th>#</th><th>From</th><th>Original filename</th><th></th>
        <th>Destination</th><th>New filename</th>
        <th title="✓ approve  ✗ reclassify  ? peek+repropose  📥 manual inbox">Action</th>
      </tr>
    </thead>
    <tbody id="tbody-${pageIdx}">${body}</tbody>
  </table>
</div>`;
}

function approveGroup(ids) {
  (ids || []).forEach(id => {
    if (rowState[id]) {
      rowState[id].status = 'approved';
      refreshRow(id);
    }
  });
  updateAll();
}

function init() {
  // Populate autocomplete datalists from vocab
  [1, 2, 3].forEach(pos => {
    const dl = document.getElementById(`voc-${pos}`);
    if (!dl) return;
    (VOCAB[String(pos)] || []).forEach(v => {
      const opt = document.createElement('option');
      opt.value = v;
      dl.appendChild(opt);
    });
  });

  const numPages = Math.ceil(PROPOSALS.length / PAGE_SIZE);
  const tabsEl   = document.getElementById('tabs');
  const pagesEl  = document.getElementById('pages');
  document.getElementById('header-title').textContent =
    `Drive Organiser — Proposals (${PROPOSALS.length} files)`;

  for (let i = 0; i < numPages; i++) {
    const tab = document.createElement('div');
    tab.className = 'tab' + (i === 0 ? ' active' : '');
    tab.id = `tab-${i}`;
    tab.onclick = () => switchPage(i);
    tabsEl.appendChild(tab);
    pagesEl.innerHTML += buildPage(i);
  }
  updateAll();
  switchPage(0);
}

let currentPage = 0;
function switchPage(idx) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.getElementById(`page-${idx}`).classList.add('active');
  document.getElementById(`tab-${idx}`).classList.add('active');
  currentPage = idx;
}

function updateAll() {
  const numPages = Math.ceil(PROPOSALS.length / PAGE_SIZE);
  let totalApproved = 0;
  for (let i = 0; i < numPages; i++) {
    const start = i * PAGE_SIZE;
    const slice = PROPOSALS.slice(start, start + PAGE_SIZE);
    const pageReviewed = slice.filter(p => ['approved','rejected','inbox','delete','flagged'].includes(rowState[p.id].status)).length;
    totalApproved += pageReviewed;
    const tab = document.getElementById(`tab-${i}`);
    if (tab) tab.textContent = `${i+1}  ${pageReviewed}/${slice.length}`;
  }
  document.getElementById('progress-label').textContent =
    `${totalApproved} / ${PROPOSALS.length} reviewed`;
  const btn = document.getElementById('submit-btn');
  btn.disabled = totalApproved === 0;
  btn.textContent = `Submit ${totalApproved}`;
}

// ---------- State mutations ----------
function setStatus(id, newStatus) {
  const st = rowState[id];
  // Toggle off if already that status
  st.status = (st.status === newStatus) ? 'unset' : newStatus;
  refreshRow(id);
  updateAll();
}

function addToDatalist(pos, val) {
  if (!val) return;
  const dl = document.getElementById(`voc-${pos}`);
  if (!dl) return;
  if (!Array.from(dl.options).some(o => o.value === val)) {
    const opt = document.createElement('option');
    opt.value = val;
    dl.appendChild(opt);
  }
}

function slugify(s) {
  // Normalise a path segment: trim, collapse internal whitespace, and strip any
  // embedded '/' so a single segment can never change the destination depth.
  return String(s == null ? '' : s)
    .replace(/\//g, ' ')
    .trim()
    .replace(/\s+/g, ' ');
}

function onSeg(id) {
  const st = rowState[id];
  st.seg1 = slugify((document.getElementById(`s1-${id}`) || {value: ''}).value);
  st.seg2 = slugify((document.getElementById(`s2-${id}`) || {value: ''}).value);
  st.seg3 = slugify((document.getElementById(`s3-${id}`) || {value: ''}).value);
  addToDatalist(1, st.seg1);
  addToDatalist(2, st.seg2);
  addToDatalist(3, st.seg3);
}
function onNameChange(id, val) {
  const trimmed = String(val == null ? '' : val).trim();
  const orig = (PROPOSAL_BY_ID[id] || {}).filename || '';
  rowState[id].newName = trimmed || orig;
}

function approveAll(pageIdx) {
  const start = pageIdx * PAGE_SIZE;
  const slice = PROPOSALS.slice(start, start + PAGE_SIZE);
  slice.forEach(p => { rowState[p.id].status = 'approved'; refreshRow(p.id); });
  updateAll();
}

function refreshRow(id) {
  const tr = document.getElementById(`row-${id}`);
  if (!tr) return;
  const st = rowState[id];
  tr.className = st.status === 'unset' ? '' : st.status;
  const approveBtn = tr.querySelector('.status-btn.approve');
  const rejectBtn  = tr.querySelector('.status-btn.reject');
  const flagBtn    = tr.querySelector('.status-btn.flag');
  if (approveBtn) approveBtn.className = 'status-btn approve' + (st.status==='approved'?' active':'');
  if (rejectBtn)  rejectBtn.className  = 'status-btn reject'  + (st.status==='rejected'?' active':'');
  if (flagBtn)    flagBtn.className    = 'status-btn flag'     + (st.status==='flagged'?' active':'');
  const inboxBtn  = tr.querySelector('.status-btn.inbox');
  if (inboxBtn)   inboxBtn.className   = 'status-btn inbox'    + (st.status==='inbox'?' active':'');
  const deleteBtn = tr.querySelector('.status-btn.delete');
  if (deleteBtn)  deleteBtn.className  = 'status-btn delete'   + (st.status==='delete'?' active':'');
}

// ---------- Submit ----------
function submitAll() {
  const output = [];
  const flaggedIds = [];
  const skippedIds = [];
  let unset = 0;
  PROPOSALS.forEach(p => {
    const st = rowState[p.id];
    if (st.status === 'approved') {
      const path = destPath(p.id);
      output.push({
        id:             p.id,
        current_path:   p.current_path,
        filename:       p.filename,
        is_image:       p.is_image,
        para_category:  inferCategory(path),
        para_subfolder: path,
        new_filename:   st.newName || p.filename,
        vision_desc:    p.vision_desc || null,
        file_date:      p.file_date || null,
        reason:         p.reason || null,
        action:         'approved',
      });
    } else if (st.status === 'rejected') {
      // Keep original proposal — Claude will reclassify before executing
      output.push({
        id:             p.id,
        current_path:   p.current_path,
        filename:       p.filename,
        is_image:       p.is_image,
        para_category:  p.para_category || null,
        para_subfolder: p.para_subfolder || null,
        new_filename:   p.new_filename || p.filename,
        vision_desc:    p.vision_desc || null,
        file_date:      p.file_date || null,
        reason:         p.reason || null,
        action:         'rejected',
      });
    } else if (st.status === 'inbox') {
      // User explicitly confirmed: needs manual review, send to _Inbox
      output.push({
        id:             p.id,
        current_path:   p.current_path,
        filename:       p.filename,
        is_image:       p.is_image,
        para_category:  '_Inbox',
        para_subfolder: '_Inbox',
        new_filename:   p.filename,
        vision_desc:    p.vision_desc || null,
        file_date:      p.file_date || null,
        reason:         'manual review',
        action:         'inbox',
      });
    } else if (st.status === 'delete') {
      output.push({
        id:             p.id,
        current_path:   p.current_path,
        filename:       p.filename,
        is_image:       p.is_image,
        para_category:  'Archive',
        para_subfolder: 'Archive/_To Delete',
        new_filename:   p.filename,
        vision_desc:    p.vision_desc || null,
        file_date:      p.file_date || null,
        reason:         'marked for deletion',
        action:         'delete',
      });
    } else if (st.status === 'flagged') {
      flaggedIds.push(p.id);
    } else {
      unset++;
      skippedIds.push(p.id);
    }
  });

  fetch('/submit', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ approved: output, flagged: flaggedIds, skipped: skippedIds }),
  })
  .then(r => r.json())
  .then(resp => {
    document.getElementById('tabs').style.display = 'none';
    document.getElementById('pages').style.display = 'none';
    const banner = document.getElementById('submitted-banner');
    banner.style.display = 'block';
    const deleteCount = output.filter(r => r.action === 'delete').length;
    let msg = `✓ Submitted ${output.length} proposals.`;
    if (deleteCount > 0) msg += ` ${deleteCount} marked for deletion (moved to Archive/_To Delete).`;
    if (flaggedIds.length > 0) msg += ` ${flaggedIds.length} flagged for later review.`;
    if (unset > 0) msg += ` ${unset} unset rows skipped.`;
    msg += ` You can close this window and return to Claude.`;
    banner.textContent = msg;
  })
  .catch(err => alert('Submit failed: ' + err));
}

function escHtml(s) {
  return String(s)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}

window.onload = init;
</script>
</body>
</html>"""

APPROVED_JSON_PATH = Path.home() / ".claude" / "drive-organizer" / "proposals_approved.json"


def _para_path_segments(para_subfolder: str) -> tuple[str, str, str]:
    """Split a stored subfolder path into up to 3 segments for the path-builder viewer."""
    parts = (para_subfolder or "").split("/", 2)
    return (
        parts[0] if len(parts) > 0 else "_Inbox",
        parts[1] if len(parts) > 1 else "",
        parts[2] if len(parts) > 2 else "",
    )


class _SilentHandler(BaseHTTPRequestHandler):
    """HTTP handler for the viewer; suppresses access logs."""

    _proposals: list = []
    _shutdown_event: threading.Event = None
    _db_path: str = None
    _vocab: dict = {}

    def log_message(self, format, *args):
        pass  # suppress access logs

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            proposals = self.__class__._proposals

            # Enrich proposals with derived keys for the viewer
            viewer_proposals = []
            for p in proposals:
                seg1, seg2, seg3 = _para_path_segments(p.get("para_subfolder", ""))
                vp = dict(p)
                vp["seg1"] = seg1
                vp["seg2"] = seg2
                vp["seg3"] = seg3
                viewer_proposals.append(vp)

            html = _VIEWER_HTML_TEMPLATE
            # Substitute the non-data placeholder first; do the proposal-data
            # replacement LAST so proposal text containing a literal placeholder
            # token can't be clobbered by a later replace().
            html = html.replace("__VOCAB_JSON__", json.dumps(self.__class__._vocab))
            html = html.replace("__PROPOSALS_JSON__", json.dumps(viewer_proposals))
            body = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == "/submit":
            # Parse Content-Length defensively: a malformed header must not crash
            # the handler, and an oversized body must not be read unbounded.
            try:
                length = int(self.headers.get("Content-Length", 0))
            except (TypeError, ValueError):
                self.send_response(400)
                self.end_headers()
                return
            if length < 0:
                self.send_response(400)
                self.end_headers()
                return
            MAX_BODY = 64 * 1024 * 1024  # 64 MB cap
            if length > MAX_BODY:
                self.send_response(413)
                self.end_headers()
                return
            raw = self.rfile.read(length)
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                self.send_response(400)
                self.end_headers()
                return

            # Support both old flat-array format and new {approved, flagged} format
            if isinstance(payload, list):
                approved = payload
                flagged_ids = []
                skipped_ids = []
            else:
                approved = payload.get("approved", [])
                flagged_ids = payload.get("flagged", [])
                skipped_ids = payload.get("skipped", [])

            # Reject an empty submission rather than overwriting prior approvals
            # with nothing — an accidental/duplicate POST must not truncate output.
            if not approved and not flagged_ids:
                resp = json.dumps({"ok": False, "error": "empty submission"}).encode()
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(resp)))
                self.end_headers()
                self.wfile.write(resp)
                return

            APPROVED_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
            if approved:
                _atomic_write(APPROVED_JSON_PATH, json.dumps(approved, indent=2))
            # Persist the EXACT flagged-ID set to a sidecar so process-return has the
            # precise flagged list if the registry write below fails — never inferred
            # by set-difference (which catches unreviewed 'unset' rows too). Only
            # written when there is content, so a flag-less submit can't clobber it.
            if flagged_ids:
                _atomic_write(
                    APPROVED_JSON_PATH.parent / "proposals_flagged.json",
                    json.dumps(flagged_ids, indent=2),
                )

            # Surface deliberately-unreviewed ('unset') rows explicitly so downstream
            # knows which files were skipped rather than silently dropping them.
            if skipped_ids:
                print(
                    f"{len(skipped_ids)} unreviewed files skipped (not written to "
                    f"proposals_approved.json): ids {skipped_ids}",
                    flush=True,
                )

            # Learn new path segments from approved destinations
            db_path = self.__class__._db_path
            if approved and db_path:
                try:
                    with sqlite3.connect(db_path) as _db:
                        for entry in approved:
                            subfolder = entry.get("para_subfolder", "")
                            if not subfolder or subfolder.startswith("_"):
                                continue
                            parts = subfolder.split("/", 2)
                            for pos, seg in enumerate(parts, 1):
                                if seg:
                                    _db.execute(
                                        """INSERT INTO path_vocab (segment, position, use_count) VALUES (?,?,1)
                                           ON CONFLICT(segment, position) DO UPDATE SET use_count = use_count + 1""",
                                        (seg, pos),
                                    )
                except Exception as e:
                    print(f"Warning: could not save vocab: {e}", flush=True)

            # Persist flagged status in the registry so these files don't reappear
            db_path = self.__class__._db_path
            if flagged_ids and db_path:
                try:
                    placeholders = ",".join("?" * len(flagged_ids))
                    with sqlite3.connect(db_path) as db:
                        db.execute(
                            f"UPDATE files SET status='flagged' WHERE id IN ({placeholders})",
                            flagged_ids,
                        )
                    # Success line printed ONLY on a successful write — so the
                    # success and warning lines are mutually exclusive (the executor
                    # can branch on exactly one).
                    print(f"{len(flagged_ids)} files marked flagged in registry.", flush=True)
                except Exception as e:
                    print(f"Warning: could not mark flagged in DB: {e}", flush=True)

            resp = json.dumps({"ok": True, "path": str(APPROVED_JSON_PATH)}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp)))
            self.end_headers()
            self.wfile.write(resp)

            print(f"\nApproved proposals written to: {APPROVED_JSON_PATH}", flush=True)
            print("Server shutting down.", flush=True)

            # Signal shutdown in a separate thread so response can be sent first
            if self.__class__._shutdown_event:
                threading.Timer(0.5, self.__class__._shutdown_event.set).start()
        else:
            self.send_response(404)
            self.end_headers()


def cmd_generate_viewer(args):
    proposals_path = Path(args.proposals)
    if not proposals_path.exists():
        sys.exit(f"Error: proposals file not found: {proposals_path}")

    with open(proposals_path) as f:
        proposals = json.load(f)

    if not proposals:
        sys.exit("Error: proposals JSON is empty.")

    # Bubble-sort by destination so files going to the same leaf appear together
    proposals = _bubble_sort_proposals(proposals)

    port = int(args.port) if args.port else 5002

    # Load path vocab from registry (+ built-in structural defaults)
    # Level 1 is seeded from .tidy-rules.json — never hardcoded here.
    # Level 2 = universal subfolder types; level 3 = common depth-3 structural names.
    # Pulled from subfolder-templates.json subfolder_definitions and parent_type_definitions
    # to keep autocomplete aligned with the canonical vocabulary.
    BUILTIN_VOCAB: dict[int, list[str]] = {
        1: [],
        2: ["Scripts", "Schedules", "Scene Breakdown", "Docs", "References",
            "Legal", "Financials", "Promotional Assets", "Film Coverage",
            "Branding Materials", "Templates", "Tasks from Notion export",
            "Planning", "Admin", "Vaidehi", "Ishan", "Joint",
            "Academic Papers", "Notes", "Digital Tools", "Lyrics Research",
            "Statements And Proposals", "Archived", "Future Planning",
            "Fonts", "Film Stills", "Game Master Guides",
            "Patterns", "Projects", "Cosplay"],
        3: ["Bills", "Invoices", "Advances", "Expense Reports",
            "Payment Summaries", "Receipts", "Bank Statements", "Tax Documents",
            "MOUs and Agreements", "Authority Letters", "Contracts",
            "Appointment and Employment Letters", "Disputes",
            "Cast Lists", "Crew Lists", "Pitch Docs", "Info Sheets",
            "Look Decks", "Mood Boards", "Locations", "Product Images",
            "Corpus", "Code", "Output", "Backups", "CPAP Data"],
    }
    vocab: dict[int, list[str]] = {1: [], 2: [], 3: []}
    if REGISTRY_DB.exists():
        try:
            with sqlite3.connect(str(REGISTRY_DB)) as _db:
                _db.row_factory = sqlite3.Row
                for row in _db.execute(
                    "SELECT segment, position FROM path_vocab ORDER BY use_count DESC"
                ).fetchall():
                    pos = row["position"]
                    if pos in vocab:
                        vocab[pos].append(row["segment"])
        except Exception:
            pass
    # Seed level-1 directly from .tidy-rules.json (source of truth for top-level names)
    rules_file = _EFFECTIVE_ROOT / ".tidy-rules.json"
    if rules_file.exists():
        try:
            _rules_data = json.loads(rules_file.read_text())
            _seen_l1 = set(vocab[1])
            for _rule in _rules_data.get("rules", []):
                _top = _rule.get("folderName", "").split("/")[0].strip()
                if _top and _top not in _seen_l1:
                    vocab[1].append(_top)
                    _seen_l1.add(_top)
        except Exception:
            pass
    for pos in [2, 3]:
        seen = set(vocab[pos])
        for v in BUILTIN_VOCAB[pos]:
            if v not in seen:
                vocab[pos].append(v)
                seen.add(v)

    shutdown_event = threading.Event()
    _SilentHandler._proposals = proposals
    _SilentHandler._shutdown_event = shutdown_event
    _SilentHandler._db_path = str(REGISTRY_DB) if REGISTRY_DB.exists() else None
    _SilentHandler._vocab = {str(k): v for k, v in vocab.items()}

    import errno as _errno
    try:
        server = HTTPServer(("127.0.0.1", port), _SilentHandler)
    except OSError as e:
        if e.errno == _errno.EADDRINUSE:
            sys.exit(
                f"Error: port {port} is already in use. "
                f"Try another --port (e.g. --port {port + 1})."
            )
        raise
    server.timeout = 1.0

    server_thread = threading.Thread(target=_serve_until, args=(server, shutdown_event), daemon=True)
    server_thread.start()

    url = f"http://localhost:{port}/"
    print(f"Viewer running at {url}")
    print(f"Proposals: {len(proposals)} files")
    print(f"Approved output will be written to: {APPROVED_JSON_PATH}")
    print("Press Ctrl+C to stop.")

    webbrowser.open(url)

    try:
        shutdown_event.wait()
    except KeyboardInterrupt:
        print("\nInterrupted — shutting down.")
    finally:
        server.shutdown()


def _serve_until(server: HTTPServer, stop_event: threading.Event):
    """Run the server, checking stop_event each timeout cycle."""
    while not stop_event.is_set():
        try:
            server.handle_request()
        except Exception as e:
            # A single handler exception must not kill the serve loop, or the
            # viewer would die mid-review and lose unsubmitted approvals.
            print(f"Warning: request handler error: {e}", flush=True)


# ---------------------------------------------------------------------------
# cleanup
# ---------------------------------------------------------------------------

def cmd_cleanup(args):
    drive = Path(args.path).expanduser() if args.path else _EFFECTIVE_ROOT
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


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------

# The five groupings are the DEFAULT, not a hard limit. The active area set is
# data-driven (see _active_groupings): a user may have more, fewer, or differently
# named top-level groupings, declared via templates Q1_groupings or config "areas".
DEFAULT_GROUPINGS = {"ENTERTAINMENT", "PERSONAL", "WORK", "EDUCATION", "RESOURCES"}
_GROUPINGS_CACHE = None


def _active_groupings() -> set:
    """The active set of top-level grouping (area) names, ALL-CAPS, derived in order:
      1. config.json "areas": [...]  (per-drive override — authoritative if present)
      2. merged templates' "Q1_groupings" list (shipped skeleton ⊕ user override)
      3. DEFAULT_GROUPINGS (the shipped five) as a last-resort fallback
    Cached for the process. This is what un-locks the area count: nothing in the
    backend hardcodes "five" — _normalize_grouping, reconcile's known-roots, and the
    grouping invariant all read THIS set."""
    global _GROUPINGS_CACHE
    if _GROUPINGS_CACHE is not None:
        return _GROUPINGS_CACHE

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
    _GROUPINGS_CACHE = names or {g.upper() for g in DEFAULT_GROUPINGS}
    return _GROUPINGS_CACHE


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
    return _active_groupings() | {"_Inbox", "Archive", "logseq-journals", ".organizer"}


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
            data = json.loads(rules_file.read_text())
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
    root = Path(_EFFECTIVE_ROOT)
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
        rep = json.loads(report_path.read_text())
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
            conn.execute("UPDATE files SET current_path=?, processed_at=? WHERE id=?", (str(fix_to), now, _id))
            conn.commit(); conn.close(); export_csv()
            print(f"Restored id {_id} -> {fix_to}")
            return
        # accept: keep the file where it is; update the registry (current_path + para) to match
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
        conn.execute(
            "UPDATE files SET current_path=?, para_subfolder=?, status=?, processed_at=? WHERE id=?",
            (actual, new_para, new_status, now, _id))
        conn.commit(); conn.close(); export_csv()
        note = "" if in_tree else "  (outside the active groupings → pending, not organized)"
        print(f"Accepted id {_id}'s location: {actual}  (registry updated → status={new_status}; file not moved){note}")
        return

    apply = getattr(args, "apply", False)
    conn = get_db()
    report = {"misplaced_files": [], "bad_registry_rows": [], "mangled_folders": [], "applied": []}

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
            subdirs[:] = [d for d in subdirs
                          if not d.startswith((".", "_", "x"))
                          and d not in locked_atomic
                          and not _atomic_marker(cp_dir / d)
                          and not _is_external(cp_dir / d)]
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
        if name in _reconcile_known_roots() or name.startswith("x"):
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
                conn.execute("UPDATE files SET current_path=?, processed_at=? WHERE id=?",
                             (str(dest), datetime.now().isoformat(), m["id"]))
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

    print(f"Root:     {_EFFECTIVE_ROOT}")
    print(f"Registry: {REGISTRY_DB}")
    print(f"Total files: {total}  |  Batches: {batches}")
    print()
    for row in rows:
        print(f"  {row['status']:15s}  {row['n']:6d}")


# ---------------------------------------------------------------------------
# mark-unapproved
# ---------------------------------------------------------------------------

def cmd_mark_unapproved(args):
    drive = Path(args.path).expanduser() if args.path else _EFFECTIVE_ROOT
    if not drive.exists():
        sys.exit(f"Error: root path not found: {drive}")

    marked = []
    skipped_known = []

    for entry in sorted(drive.iterdir()):
        if not entry.is_dir():
            continue
        if should_skip(entry) or entry.name.startswith("."):
            continue
        if entry.name.startswith("x"):
            continue  # already deferred — leave alone
        if entry.name in PARA_ROOTS:
            skipped_known.append(entry.name)
            continue
        if _has_rules(entry, drive):
            skipped_known.append(entry.name)
            continue
        # No rules → defer with x prefix
        new_name = "x" + entry.name
        new_path = drive / new_name
        if new_path.exists():
            print(f"  skip (collision): {entry.name} → {new_name} already exists")
            continue
        entry.rename(new_path)
        marked.append(entry.name)
        print(f"  marked: {entry.name!r}  →  x{entry.name!r}")

    print()
    print(f"Marked {len(marked)} folder(s) as deferred (no .tidy-rules.json found).")
    print(f"Folders with known rules left unchanged: {len(skipped_known)}")
    if marked:
        print()
        print("Deferred (x-prefixed) folders are scanned at LOW priority and proposed out")
        print("through the normal flow — the x-prefix is never removed (it stays until the")
        print("folder empties and cleanup deletes it). To process one sooner:")
        print("  1. Create a .tidy-rules.json inside it (scan then treats it as a known folder)")
        print("  2. Re-run scan; approve its files out in the viewer as usual")


# ---------------------------------------------------------------------------
# csv-export
# ---------------------------------------------------------------------------

CSV_EXPORT_PATH = Path.home() / ".claude" / "drive-organizer" / "registry.csv"  # overridden at startup

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
    with open(CSV_EXPORT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "filename", "current_path", "destination", "status",
                         "file_date", "file_size_bytes", "vision_desc"])
        for r in rows:
            writer.writerow([r["id"], r["filename"], r["current_path"],
                              r["para_subfolder"] or "", r["status"],
                              r["file_date"] or "", r["file_size"] or "",
                              r["vision_desc"] or ""])
    print(f"Registry exported: {CSV_EXPORT_PATH}  ({len(rows)} rows)")


def cmd_csv_export(args):
    export_csv()


# ---------------------------------------------------------------------------
# Rule aggregation + entity metadata (shared data layer for the rules viewer,
# the bootstrap builder, and the learning loop). Walks the whole .tidy-rules.json
# cascade and groups rules by entity (folder name) across the tree, so "Ishan"
# in WORK and "Ishan" in EDUCATION collapse to one entity with two occurrences.
# ---------------------------------------------------------------------------

def _read_entities(root: "Path | None" = None) -> dict:
    """Per-drive entity metadata at <root>/.organizer/entities.json. Optional;
    absent => today's behaviour. Maps entity name -> {entity_type, locked,
    aliases, relation, policy, notes}. Never raises."""
    root = root or _EFFECTIVE_ROOT
    if not root:
        return {}
    p = Path(root) / ".organizer" / "entities.json"
    if not p.exists():
        return {}
    try:
        d = json.loads(p.read_text())
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _locked_atomic_names(root: "Path | None" = None) -> set:
    """Names of entities that are locked atomic units (entity_type=atomic OR
    locked=true) per entities.json — folders scan/bootstrap/coverage treat as a
    single opaque leaf, never descending into them. Single source for the set."""
    return {name for name, m in _read_entities(root).items()
            if isinstance(m, dict) and (m.get("locked") is True or m.get("entity_type") == "atomic")}


def _write_entities(root: Path, data: dict) -> None:
    """Persist entity metadata. Used by the viewer/bootstrap write-back."""
    p = Path(root) / ".organizer" / "entities.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(p, json.dumps(data, ensure_ascii=False, indent=2))


def _signal_from_description(desc: str, folder: str) -> str:
    """Strip the required ' in <FolderName>' suffix to recover the rule's signal
    terms. Tolerates the (incorrect but seen) comma-before-in form."""
    if not desc:
        return ""
    leaf = folder.split("/")[-1]
    for suffix in (f" in {folder}", f" in {leaf}", f", in {folder}", f", in {leaf}"):
        if desc.endswith(suffix):
            return desc[:-len(suffix)].rstrip().rstrip(",").strip()
    return desc.strip()


def _category_names() -> set:
    """Functional-subfolder names known from the templates (Scripts, References,
    Bills, …) — used to infer entity_type=category. Data-driven, not hardcoded."""
    t = _load_templates()
    names = set()
    sd = t.get("subfolder_definitions", {})
    if isinstance(sd, dict):
        names |= set(sd.keys())
    cc = t.get("compound_children", {})
    if isinstance(cc, dict):
        names |= set(cc.keys())
        for v in cc.values():
            if isinstance(v, list):
                for x in v:
                    if isinstance(x, str):
                        names.add(x)
                    elif isinstance(x, dict) and "name" in x:
                        names.add(x["name"])
    return names


# Common functional-subfolder names (beyond whatever the templates define). Used to
# confidently infer entity_type=category so these never fall into triage. Lowercased.
_COMMON_CATEGORY_WORDS = {
    "finance", "financials", "notes", "feedback", "receipts", "invoices", "bills",
    "statements", "tax", "admin", "docs", "documents", "references", "scripts",
    "schedules", "drafts", "exports", "imports", "backups", "output", "outputs",
    "misc", "miscellaneous", "templates", "assets", "correspondence", "contracts",
    "legal", "planning", "research", "reports", "logs", "data", "code", "config",
    "scans", "attachments", "deliverables", "expenses", "payments", "agreements",
}


def _infer_entity_type(name: str, has_filename_tag: bool, is_grouping: bool,
                       categories: set) -> str:
    """Best-effort entity_type from STRUCTURAL + cheap lexical signals, when
    entities.json doesn't set one explicitly. It makes a CONFIDENT guess wherever it
    reasonably can, and reserves 'unknown' (triage) for the genuinely ambiguous —
    chiefly Capitalized proper-noun names that could be a person OR a project, and
    junk names. It never guesses 'person' from name shape (that mislabelled 'Thesis'
    / 'Incoming4'); person vs project is resolved by Claude's inference or the user."""
    if is_grouping:
        return "area"
    if has_filename_tag:
        return "project"
    nl = name.lower()
    cats_lower = {c.lower() for c in categories} | _COMMON_CATEGORY_WORDS
    if nl in cats_lower:
        return "category"
    # A single all-lowercase alphabetic word is almost always a functional subfolder
    # (people / projects are Capitalized). Confident category, not triage.
    if " " not in name and name.isalpha() and name == nl:
        return "category"
    # Otherwise truly ambiguous (proper-noun container person-vs-project, or junk) -> triage.
    return "unknown"


def _aggregate_rules(root: "Path") -> list:
    """Group every .tidy-rules.json rule by entity (leaf folder name) across the
    whole tree. Each returned entity carries its cross-folder occurrences, inferred
    or explicit entity_type (the clustering key), project metadata, registry usage
    count, and a dead-rule flag. This is the single source the viewer/bootstrap read."""
    root = Path(root)
    entities_meta = _read_entities(root)
    groupings = _active_groupings()
    categories = _category_names()
    projects = {}
    for p in _enumerate_project_metadata(root):
        projects[p["path"].split("/")[-1]] = p

    agg: dict = {}
    for rules_file in sorted(root.rglob(".tidy-rules.json")):
        parent = rules_file.parent
        try:
            rel_parent = parent.relative_to(root)
        except Exception:
            continue
        parent_disp = "" if str(rel_parent) == "." else str(rel_parent)
        try:
            data = json.loads(rules_file.read_text())
        except Exception:
            continue
        rule_list = data.get("rules", []) if isinstance(data, dict) else data
        if not isinstance(rule_list, list):
            continue
        for r in rule_list:
            if not isinstance(r, dict):
                continue
            folder = r.get("folderName")
            if not folder:
                continue
            name = folder.split("/")[-1]
            dest_rel = (f"{parent_disp}/{folder}" if parent_disp else folder).strip("/")
            desc = r.get("description", "")
            ent = agg.setdefault(name, {"entity": name, "occurrences": []})
            ent["occurrences"].append({
                "parent": parent_disp,
                "folderName": folder,
                "dest": dest_rel,
                "description": desc,
                "signal": _signal_from_description(desc, folder),
                "rules_file": str(rules_file.relative_to(root)),
            })

    # Registry usage: files actually routed to each destination.
    usage: dict = {}
    try:
        conn = get_db()
        for row in conn.execute(
            "SELECT para_subfolder AS d, COUNT(*) AS c FROM files "
            "WHERE para_subfolder IS NOT NULL AND para_subfolder != '' GROUP BY para_subfolder"):
            usage[row["d"]] = row["c"]
        conn.close()
    except Exception:
        pass

    def _prefix_usage(area: str) -> int:
        # Files routed to the area itself OR anywhere beneath it.
        return sum(c for d, c in usage.items() if d == area or d.startswith(area + "/"))

    out = []
    for name, ent in agg.items():
        dests = {o["dest"] for o in ent["occurrences"]}
        meta = entities_meta.get(name, {})
        # Area entities count usage as a PREFIX-SUM (everything routed under the area),
        # consistent with the synthetic-area card below; non-area entities count the
        # files routed to their exact destination(s).
        if name.upper() in groupings:
            ucount = _prefix_usage(name)
        else:
            ucount = sum(usage.get(d, 0) for d in dests)
        proj = projects.get(name, {})
        has_tag = bool(proj.get("filename_tag"))
        explicit = meta.get("entity_type")
        if explicit:
            etype, inferred = explicit, False
        else:
            etype = _infer_entity_type(name, has_tag, name.upper() in groupings, categories)
            inferred = True
        ent.update({
            "entity_type": etype,
            "type_inferred": inferred,
            "locked": meta.get("locked") is True,
            "aliases": meta.get("aliases", []),
            "relation": meta.get("relation"),
            "policy": meta.get("policy"),
            "notes": meta.get("notes"),
            "review": meta.get("review"),   # persisted "rethink" flag — viewer reads e.review
            "filename_tag": proj.get("filename_tag"),
            "production_period": proj.get("production_period"),
            "occurrence_count": len(ent["occurrences"]),
            "usage_count": ucount,
            "dead": ucount == 0,
        })
        out.append(ent)

    # Locked/atomic entities declared in entities.json but carrying no rules.
    for name, meta in entities_meta.items():
        if name in agg:
            continue
        if meta.get("entity_type") == "atomic" or meta.get("locked") is True:
            out.append({
                "entity": name, "occurrences": [],
                "entity_type": meta.get("entity_type", "atomic"),
                "type_inferred": False, "locked": meta.get("locked", True) is True,
                "aliases": meta.get("aliases", []), "relation": meta.get("relation"),
                "policy": meta.get("policy"), "notes": meta.get("notes"),
                "review": meta.get("review"),
                "filename_tag": None, "production_period": None,
                "occurrence_count": 0, "usage_count": 0, "dead": True,
            })

    # Synthesize a card for every active grouping (area) so areas are editable as
    # full cards (signal/details/notes), not just top-of-page chips. Areas that
    # already have a root rule produced an entity above — just force their type.
    present = {e["entity"] for e in out}
    for area in sorted(_active_groupings()):
        if area in present:
            for e in out:
                if e["entity"] == area and not entities_meta.get(area, {}).get("entity_type"):
                    e["entity_type"] = "area"
                    e["type_inferred"] = False
            continue
        m = entities_meta.get(area, {})
        area_usage = _prefix_usage(area)
        out.append({
            "entity": area,
            "occurrences": [{"parent": "", "folderName": area, "dest": area,
                             "description": "", "signal": "", "rules_file": ".tidy-rules.json"}],
            "entity_type": "area", "type_inferred": False,
            "locked": m.get("locked") is True,
            "aliases": m.get("aliases", []), "relation": m.get("relation"),
            "policy": m.get("policy"), "notes": m.get("notes"),
            "review": m.get("review"),
            "filename_tag": None, "production_period": None,
            "occurrence_count": 1, "usage_count": area_usage, "dead": area_usage == 0,
            "synthetic_area": True,
        })

    out.sort(key=lambda e: (_CLUSTER_ORDER.index(e["entity_type"]) if e["entity_type"] in _CLUSTER_ORDER else 99,
                            e["entity"].lower()))
    return out


_CLUSTER_ORDER = ["area", "project", "person", "category", "policy", "atomic", "unknown"]
_CLUSTER_LABEL = {
    "area": "Areas", "project": "Projects", "person": "People",
    "category": "Subfolders / Categories", "policy": "Policies", "atomic": "Atomic units",
    "unknown": "Unknown / triage",
}


def cmd_rules(args):
    """Aggregate the .tidy-rules.json cascade by entity across the tree. Default
    output is a human one-line-per-entity summary, semantically clustered by
    entity_type. `--json` emits the full structure consumed by the rules viewer."""
    root = Path(_EFFECTIVE_ROOT)
    agg = _aggregate_rules(root)
    if getattr(args, "json", False):
        print(json.dumps(
            {"root": str(root), "areas": sorted(_active_groupings()), "entities": agg},
            ensure_ascii=False, indent=2))
        return
    by_type: dict = {}
    for e in agg:
        by_type.setdefault(e["entity_type"], []).append(e)
    areas = sorted(_active_groupings())
    print(f"Rules aggregated from {root}")
    print(f"Active areas ({len(areas)}): {', '.join(areas)}")
    print(f"{len(agg)} entities across {sum(len(e['occurrences']) for e in agg)} rule occurrences\n")
    for t in _CLUSTER_ORDER + [x for x in by_type if x not in _CLUSTER_ORDER]:
        ents = by_type.get(t)
        if not ents:
            continue
        print(f"== {_CLUSTER_LABEL.get(t, t.title())} ({len(ents)}) ==")
        for e in sorted(ents, key=lambda x: x["entity"].lower()):
            locs = len(e["occurrences"])
            flags = []
            if e["locked"]:
                flags.append("locked")
            if e["dead"] and e["occurrences"]:
                flags.append("DEAD 0-routed")
            if e["type_inferred"]:
                flags.append("type?")
            if e.get("aliases"):
                flags.append("aka " + "/".join(e["aliases"]))
            tag = f"  [{', '.join(flags)}]" if flags else ""
            where = ""
            if locs:
                ps = sorted({o["parent"] or "(root)" for o in e["occurrences"]})
                where = " @ " + ", ".join(ps[:4]) + (f" +{len(ps) - 4}" if len(ps) > 4 else "")
            print(f"  - {e['entity']} - {locs} folder(s), {e['usage_count']} files routed{where}{tag}")
        print()


# ---------------------------------------------------------------------------
# W2 — Rules viewer/editor: aggregated, clustered, editable rules in a browser.
# Mirrors cmd_generate_viewer (do_GET serves, do_POST writes back, then shuts
# down). Safe edits (metadata, signal text, delete-rule, area add/rename) apply
# directly; structural moves (folder rename, level promotion) return a dry-run
# plan the user confirms — never a silent move.
# ---------------------------------------------------------------------------

def _conflicts_for(index: list) -> dict:
    """Map entity-destination -> list of other destinations whose token set overlaps
    (a filename could match both). Surfaced as per-card conflict warnings."""
    out = {}
    for i, a in enumerate(index):
        clashes = []
        for j, b in enumerate(index):
            if i == j or a["dest"] == b["dest"]:
                continue
            if a["tokens"] & b["tokens"]:
                clashes.append({"with": b["dest"], "shared": sorted(a["tokens"] & b["tokens"])[:5]})
        if clashes:
            out[a["dest"]] = clashes
    return out


def _coverage_gaps(root: Path, dest_set: set) -> list:
    """Folders that physically hold files but have no rule routing into them —
    candidates for 'create a rule' (feeds reconcile)."""
    gaps = []
    groupings = _active_groupings()
    locked_atomic = _locked_atomic_names(root)
    skip = {".organizer", "logseq-journals", "Archive", "_Inbox"}
    # Normalise destinations (forward-slash, case-folded) so a real folder isn't
    # reported as a gap merely because of separator/case differences vs the rule dest.
    norm_dest_set = {str(d).replace(os.sep, "/").strip("/").casefold() for d in dest_set}
    for top in sorted(p for p in root.iterdir() if p.is_dir()):
        if top.name in skip or top.name.startswith("x") or top.name not in groupings:
            continue
        # os.walk (not rglob) so external/atomic subtrees can be pruned before descent —
        # rglob would walk into shared folders and node_modules/.git/venvs.
        for cur, subdirs, files in os.walk(top):
            cp = Path(cur)
            subdirs[:] = [d for d in subdirs
                          if not d.startswith((".", "_", "x"))
                          and d not in locked_atomic
                          and not _atomic_marker(cp / d)
                          and not _is_external(cp / d)]
            if cp == top:
                continue   # the grouping root itself isn't a "gap"
            try:
                rel = str(cp.relative_to(root))
            except Exception:
                continue
            if rel.replace(os.sep, "/").strip("/").casefold() in norm_dest_set:
                continue
            try:
                has_files = any(f.is_file() and not should_skip(f) for f in cp.iterdir())
            except OSError:
                continue   # unreadable (cloud/permission) folder — skip, don't crash
            if has_files and not (cp / ".tidy-rules.json").exists():
                gaps.append(rel)
                if len(gaps) >= 100:
                    return gaps
    return gaps[:100]


def _edit_rule_across_occurrences(root: Path, entity: str, occurrences: list,
                                  new_description: str = None, delete: bool = False,
                                  create_if_missing: bool = False) -> int:
    """Apply a signal/description edit (or delete the rule) to every occurrence of an
    entity across the tree. Returns the number of rule files changed. Folder names
    and files on disk are NOT touched — this edits routing rules only.
    create_if_missing: when a folderName isn't present in its rules file (e.g. a
    synthesized area card with no root rule yet), append a new rule for it."""
    changed = 0
    by_file = {}
    for occ in occurrences:
        by_file.setdefault(occ["rules_file"], []).append(occ["folderName"])
    for rel_file, folder_names in by_file.items():
        path = root / rel_file
        if path.exists():
            try:
                data = json.loads(path.read_text())
            except Exception:
                continue
        elif create_if_missing and new_description is not None:
            data = {"rules": []}
        else:
            continue
        rules = data.get("rules", []) if isinstance(data, dict) else data
        if not isinstance(rules, list):
            continue
        touched = False
        seen = set()
        new_rules = []
        for r in rules:
            if isinstance(r, dict) and r.get("folderName") in folder_names:
                seen.add(r["folderName"])
                if delete:
                    touched = True
                    continue  # drop the rule
                if new_description is not None:
                    leaf = r["folderName"].split("/")[-1]
                    desc = new_description.strip()
                    if not desc.endswith(f" in {leaf}"):
                        desc = f"{desc} in {leaf}"
                    r["description"] = desc
                    touched = True
            new_rules.append(r)
        if create_if_missing and new_description is not None and not delete:
            for fn in folder_names:
                if fn not in seen:
                    leaf = fn.split("/")[-1]
                    desc = new_description.strip()
                    if not desc.endswith(f" in {leaf}"):
                        desc = f"{desc} in {leaf}"
                    new_rules.append({"folderName": fn, "description": desc})
                    touched = True
        if touched:
            if isinstance(data, dict):
                data["rules"] = new_rules
            else:
                data = new_rules
            path.parent.mkdir(parents=True, exist_ok=True)
            _atomic_write(path, json.dumps(data, indent=2, ensure_ascii=False))
            changed += 1
    return changed


def _rename_entity(root: Path, entity: str, occurrences: list, new_name: str,
                   apply: bool = False) -> dict:
    """Rename an entity (rule folderName leaf) across all its occurrences, and rename
    the on-disk folder + update the registry. dry-run unless apply=True."""
    plan, did = [], {"rules": 0, "folders": 0, "rows": 0}
    # Build the per-occurrence plan first (dry-run is just this).
    for occ in occurrences:
        old_dest = occ["dest"]
        parent = occ["parent"]
        new_dest = (f"{parent}/{new_name}" if parent else new_name).strip("/")
        plan.append({"from": old_dest, "to": new_dest, "rules_file": occ["rules_file"],
                     "folderName": occ["folderName"]})
    if not apply:
        return {"entity": entity, "new_name": new_name, "apply": apply, "plan": plan,
                "applied": did}

    # PRE-SCAN: refuse the whole rename if ANY target already exists on disk or in the
    # registry, before mutating anything (no partial renames, no collisions).
    conn = get_db()
    try:
        for step in plan:
            new_dest = step["to"]
            dst = root / new_dest
            if dst.exists():
                return {"entity": entity, "new_name": new_name, "apply": apply,
                        "plan": plan, "applied": did,
                        "error": f"target already exists on disk: {dst} — aborted (no changes made)"}
            clash = conn.execute(
                "SELECT COUNT(*) FROM files WHERE para_subfolder = ? OR para_subfolder LIKE ?",
                (new_dest, new_dest + "/%")).fetchone()[0]
            if clash:
                return {"entity": entity, "new_name": new_name, "apply": apply,
                        "plan": plan, "applied": did,
                        "error": f"target destination already in registry: {new_dest} "
                                 f"({clash} row(s)) — aborted (no changes made)"}

        for step in plan:
            old_dest, new_dest = step["from"], step["to"]
            rules_file, folder_name = step["rules_file"], step["folderName"]
            # rule rewrite
            rf = root / rules_file
            if rf.exists():
                try:
                    data = json.loads(rf.read_text())
                    rules = data.get("rules", []) if isinstance(data, dict) else data
                    for r in rules:
                        if isinstance(r, dict) and r.get("folderName") == folder_name:
                            r["folderName"] = new_name
                            d = r.get("description", "")
                            old_leaf = folder_name.split("/")[-1]
                            if d.endswith(f" in {old_leaf}"):
                                r["description"] = d[: -len(f" in {old_leaf}")] + f" in {new_name}"
                            did["rules"] += 1
                    if isinstance(data, dict):
                        data["rules"] = rules
                    _atomic_write(rf, json.dumps(data, indent=2, ensure_ascii=False))
                except Exception:
                    pass
            # folder move on disk — if the destination already exists (a collision the
            # pre-scan can't catch if it appeared mid-run), ABORT this occurrence: do
            # NOT rewrite the registry to point at a folder files were never moved into.
            src, dst = root / old_dest, root / new_dest
            if src.exists():
                if dst.exists():
                    conn.rollback(); conn.close()
                    return {"entity": entity, "new_name": new_name, "apply": apply,
                            "plan": plan, "applied": did,
                            "error": f"collision: {dst} appeared before the move — "
                                     f"aborted and rolled back (no changes committed)"}
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dst))
                did["folders"] += 1
            # registry update — rewrite the PREFIX exactly, in Python. SQL REPLACE
            # substitutes every substring occurrence, so a short/common old_dest
            # (e.g. "A") would corrupt unrelated path segments ("A/A Files" →
            # "B/B Files"). Match rows whose para_subfolder is exactly old_dest or a
            # child of it, and replace only the leading old_dest segment.
            src_str, dst_str = str(src), str(dst)
            rows = conn.execute(
                "SELECT id, para_subfolder, current_path FROM files "
                "WHERE para_subfolder = ? OR para_subfolder LIKE ?",
                (old_dest, old_dest + "/%")).fetchall()
            for row in rows:
                para = row["para_subfolder"] or ""
                if para == old_dest:
                    new_para = new_dest
                elif para.startswith(old_dest + "/"):
                    new_para = new_dest + para[len(old_dest):]
                else:
                    continue
                cp = row["current_path"] or ""
                # Only rewrite current_path when it is exactly src or a child of src
                # (boundary-anchored), so a sibling sharing the prefix — "WORK/Acme"
                # vs "WORK/Acme Corp" — is never corrupted.
                if cp == src_str or cp.startswith(src_str + os.sep):
                    new_cp = dst_str + cp[len(src_str):]
                else:
                    new_cp = cp
                conn.execute(
                    "UPDATE files SET para_subfolder=?, current_path=? WHERE id=?",
                    (new_para, new_cp, row["id"]))
                did["rows"] += 1
        # Commit once, atomically, after ALL occurrences succeed.
        conn.commit()
    except Exception as e:
        conn.rollback()
        conn.close()
        return {"entity": entity, "new_name": new_name, "apply": apply, "plan": plan,
                "applied": did, "error": f"rename failed, rolled back: {e}"}
    finally:
        try:
            conn.close()
        except Exception:
            pass
    return {"entity": entity, "new_name": new_name, "apply": apply, "plan": plan, "applied": did}


def _merge_entities(root: Path, src_entity: dict, dst_name: str) -> dict:
    """Fold a (misspelled/duplicate) entity into another: add the source name + its
    aliases as aliases of the destination, then delete the source's routing rules so
    future files route to the destination. REFUSED (no-op, returns an error) while the
    source still holds files on disk or registry rows route to it — deleting its rules
    then would orphan those files; the user must reconcile/promote them first."""
    # SAFETY: deleting the source's rules without moving its on-disk files would orphan
    # those files (no rule routes into the source folder any more, yet the files still
    # sit there). Refuse the merge while any source occurrence still holds files on disk
    # OR still has registry rows routed to it — the user must reconcile/promote first.
    occ_dests = [o["dest"] for o in src_entity["occurrences"]]
    holding = []
    for dest in occ_dests:
        folder = root / dest
        try:
            if folder.is_dir() and any(f.is_file() for f in folder.rglob("*")):
                holding.append(dest)
                continue
        except OSError:
            holding.append(dest)   # unreadable → treat as holding (refuse safely)
            continue
    routed = 0
    if occ_dests:
        try:
            conn = get_db()
            for dest in occ_dests:
                routed += conn.execute(
                    "SELECT COUNT(*) FROM files WHERE para_subfolder = ? OR para_subfolder LIKE ?",
                    (dest, dest + "/%")).fetchone()[0]
            conn.close()
        except Exception:
            pass
    if holding or routed:
        return {"merged": None, "into": dst_name, "error": (
            f"REFUSED merge of '{src_entity['entity']}' into '{dst_name}': source still "
            f"holds files"
            + (f" on disk ({', '.join(holding)})" if holding else "")
            + (f" and {routed} registry row(s) route to it" if routed else "")
            + ". Reconcile or promote those files first, then merge.")}

    ents = _read_entities(root)
    dst = ents.setdefault(dst_name, {})
    aliases = set(dst.get("aliases", []))
    aliases.add(src_entity["entity"])
    aliases |= set(src_entity.get("aliases", []))
    dst["aliases"] = sorted(aliases)
    if src_entity["entity"] in ents:
        del ents[src_entity["entity"]]
    _write_entities(root, ents)
    deleted = _edit_rule_across_occurrences(root, src_entity["entity"],
                                            src_entity["occurrences"], delete=True)
    return {"merged": src_entity["entity"], "into": dst_name, "rules_deleted": deleted,
            "alias_added": True,
            "note": "Future routing folds in (source held no files; safe to drop rules)."}


def _apply_area_changes(root: Path, add: list, rename: list, remove: list) -> dict:
    """Add / rename / remove top-level groupings in the per-drive config.json "areas"
    list (ALL-CAPS enforced). Removal is refused while files still live under the area
    (guard). On-disk folder renames for a renamed area are reported as a structural
    follow-up, not performed silently."""
    cfg_path = root / ".organizer" / "config.json"
    cfg = {}
    if cfg_path.exists():
        try:
            cfg = json.loads(cfg_path.read_text())
        except Exception:
            cfg = {}

    def _area_has_files(au: str) -> bool:
        """True if the on-disk folder for area `au` has any contents. Unreadable
        (permission/cloud) folders are treated as HAS-contents so removal/rename is
        refused safely rather than proceeding on an unverifiable empty assumption."""
        folder = root / au
        if not folder.exists():
            return False
        try:
            return any(folder.iterdir())
        except OSError:
            return True

    def _registry_rows_under(au: str) -> int:
        try:
            conn = get_db()
            n = conn.execute(
                "SELECT COUNT(*) FROM files WHERE para_subfolder = ? OR para_subfolder LIKE ?",
                (au, au + "/%")).fetchone()[0]
            conn.close()
            return n
        except Exception:
            return 0

    # CONFIG-FREEZING CAVEAT: the very first area edit persists the *current* derived
    # _active_groupings() set into config.json "areas". Only the keys the user actually
    # changed are mutated below, but writing the "areas" list at all freezes the set
    # (subsequent template changes won't flow through). This is intentional: an explicit
    # area edit is the user taking ownership of the set.
    areas = [a.upper() for a in (cfg.get("areas") or sorted(_active_groupings()))]
    notes = []
    for a in add or []:
        au = str(a).upper()
        if au not in areas:
            areas.append(au)
            notes.append(f"added area {au}")
    for r in rename or []:
        old, new = str(r.get("old", "")).upper(), str(r.get("new", "")).upper()
        if old not in areas or not new:
            continue
        if new in areas:
            notes.append(f"REFUSED rename {old} -> {new}: target area name already exists")
            continue
        # Like remove, refuse the rename while files/rules/the OLD folder still exist
        # under the old name — the config would then point at a name with no folder
        # while real files remain under the old folder (orphaning them).
        if _area_has_files(old):
            notes.append(f"REFUSED rename {old} -> {new}: old folder still has contents "
                         f"(move/reconcile its files first)")
            continue
        rows = _registry_rows_under(old)
        if rows:
            notes.append(f"REFUSED rename {old} -> {new}: {rows} registry row(s) still route under {old}")
            continue
        if _has_rules(root / old, root):
            notes.append(f"REFUSED rename {old} -> {new}: old folder still has a .tidy-rules.json")
            continue
        areas[areas.index(old)] = new
        notes.append(f"renamed area {old} -> {new} (on-disk folder rename is a separate structural step)")
    for a in remove or []:
        au = str(a).upper()
        if _area_has_files(au):
            notes.append(f"REFUSED remove {au}: folder still has contents")
            continue
        # Also refuse while the registry still routes files under the area, even if
        # the on-disk folder is empty/absent (e.g. files classified but not yet
        # executed) — removing the area would strand those rows with a dead destination.
        n = _registry_rows_under(au)
        if n:
            notes.append(f"REFUSED remove {au}: {n} registry row(s) still route under it")
            continue
        if au in areas:
            areas.remove(au)
            notes.append(f"removed area {au}")
    cfg["areas"] = areas
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(cfg_path, json.dumps(cfg, indent=2, ensure_ascii=False))
    return {"areas": areas, "notes": notes}


def _promotion_plan(root: Path, entity: str, occurrences: list, target_parent: str) -> dict:
    """Dry-run plan for moving a folder up/down a level (e.g. a Q2 thing -> its own Q1
    area). Describes the folder move, the rule rewrites, and the registry path updates
    that --apply would perform. Never moves anything here (the user confirms)."""
    steps = []
    target_parent = _normalize_grouping(target_parent.strip("/")) if target_parent else ""
    for occ in occurrences:
        src_rel = occ["dest"]
        new_rel = (f"{target_parent}/{entity}" if target_parent else entity).strip("/")
        if src_rel == new_rel:
            continue
        n_files = 0
        try:
            conn = get_db()
            n_files = conn.execute(
                "SELECT COUNT(*) c FROM files WHERE para_subfolder = ? OR para_subfolder LIKE ?",
                (src_rel, src_rel + "/%")).fetchone()[0]
            conn.close()
        except Exception:
            pass
        steps.append({
            "move_folder": {"from": src_rel, "to": new_rel},
            "rewrite_rule_in": occ["rules_file"],
            "registry_rows_to_update": n_files,
        })
    return {"entity": entity, "target_parent": target_parent or "(root)",
            "steps": steps, "note": "DRY-RUN — confirm to apply (uses reconcile move machinery)."}


_RULES_VIEWER_HTML = r"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>Drive Organizer — Rules</title>
<style>
 :root{--bg:#0f1115;--card:#1a1d24;--mut:#8b93a7;--fg:#e7ebf3;--acc:#6ea8fe;--warn:#f0a35e;--bad:#e06c75;--ok:#7ec699;--line:#2a2f3a;--input:#11141b;--bar:#0f1115f2;--chip:#232735;--tagbg:#272c38}
 @media (prefers-color-scheme: light){:root{--bg:#f6f7f9;--card:#ffffff;--mut:#5c6473;--fg:#1a1d24;--acc:#2563eb;--warn:#b4690e;--bad:#c0392b;--ok:#2e7d52;--line:#dfe3ea;--input:#ffffff;--bar:#f6f7f9f2;--chip:#eceff3;--tagbg:#e7ebf2}}
 *{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif}
 header{position:sticky;top:0;background:var(--bar);backdrop-filter:blur(6px);border-bottom:1px solid var(--line);padding:12px 18px;z-index:5}
 h1{font-size:16px;margin:0 0 6px} .sub{color:var(--mut);font-size:12px}
 .areas{display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin-top:8px}
 .chip{background:var(--chip);border:1px solid var(--line);border-radius:14px;padding:2px 10px;font-size:12px;display:flex;gap:6px;align-items:center}
 .chip button{background:none;border:none;color:var(--mut);cursor:pointer;font-size:12px}
 button{cursor:pointer} .btn{background:var(--acc);color:#06101f;border:none;border-radius:6px;padding:6px 12px;font-weight:600}
 .btn.ghost{background:var(--chip);color:var(--fg);border:1px solid var(--line)} .btn.sm{padding:3px 8px;font-size:12px} .btn.warn{color:var(--warn)} .btn.bad{color:var(--bad)}
 main{padding:14px 18px;max-width:1100px;margin:0 auto}
 .cluster{margin:18px 0 6px;font-size:13px;letter-spacing:.04em;text-transform:uppercase;color:var(--acc);border-bottom:1px solid var(--line);padding-bottom:4px}
 .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:10px}
 .card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:11px 12px}
 .card h3{margin:0;font-size:15px;display:flex;align-items:center;gap:8px;flex-wrap:wrap}
 .tag{font-size:10px;border-radius:10px;padding:1px 7px;background:var(--tagbg);color:var(--mut)} .tag.rethink{background:color-mix(in srgb,var(--warn) 18%,transparent);color:var(--warn)}
 .tag.dead{background:color-mix(in srgb,var(--bad) 16%,transparent);color:var(--bad)} .tag.lock{background:color-mix(in srgb,var(--ok) 18%,transparent);color:var(--ok)} .tag.inf{background:color-mix(in srgb,var(--warn) 18%,transparent);color:var(--warn)}
 .meta{margin:7px 0;display:grid;grid-template-columns:auto 1fr;gap:4px 8px;align-items:center;font-size:12px}
 .meta label{color:var(--mut)} input,select,textarea{background:var(--input);border:1px solid var(--line);color:var(--fg);border-radius:5px;padding:4px 6px;font:inherit;width:100%}
 textarea{resize:vertical;min-height:34px} .occ{font-size:11px;color:var(--mut);margin:6px 0;border-left:2px solid var(--line);padding-left:8px}
 .occ b{color:var(--fg);font-weight:600} .conflict{font-size:11px;color:var(--warn);margin-top:5px} .row{display:flex;gap:6px;margin-top:7px;flex-wrap:wrap}
 .pager{display:flex;gap:6px;align-items:center;justify-content:center;margin:16px 0} .pager span{color:var(--mut)}
 .tools{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-top:8px}
 .tools input{width:auto;min-width:220px} #testout,#planout{font-size:12px;color:var(--ok);margin-left:6px}
 .gaps{margin-top:8px;font-size:12px;color:var(--warn)} dialog{background:var(--card);color:var(--fg);border:1px solid var(--line);border-radius:10px}
 .legend{margin-top:8px;font-size:12px} .legend summary{cursor:pointer;color:var(--acc)} .legendbody{color:var(--mut);margin-top:6px;padding:8px 10px;background:var(--input);border:1px solid var(--line);border-radius:8px} .legendbody ul{margin:4px 0 8px 0;padding-left:18px} .legendbody b{color:var(--fg)} .legendbody i{color:var(--acc)}
 .savebar{position:sticky;bottom:0;background:var(--bar);border-top:1px solid var(--line);padding:10px 18px;display:flex;gap:12px;align-items:center;justify-content:flex-end}
 .pill{font-size:11px;background:var(--tagbg);border-radius:10px;padding:1px 8px;color:var(--mut)}
 .bulkbar{position:sticky;top:0;z-index:6;background:var(--bar);border-bottom:1px solid var(--line);padding:8px 18px;display:flex;gap:10px;align-items:center}
 .planline{font-size:11px;color:var(--warn)} h3 .bulk{accent-color:var(--acc);margin-right:2px}
 #diff{max-width:560px;width:90%} #diffbody{max-height:50vh;overflow:auto} .diffrow{display:flex;justify-content:space-between;gap:10px;align-items:center;padding:4px 0;border-bottom:1px solid var(--line);font-size:13px}
</style></head><body>
<header>
 <h1>Drive Organizer — Rules viewer / editor</h1>
 <div class="sub" id="sub"></div>
 <div class="areas" id="areas"></div>
 <div class="tools">
   <span class="pill">Test a file</span><input id="testfile" placeholder="paste a filename, e.g. invoice_acme.pdf">
   <button class="btn sm ghost" onclick="testFile()">where would it go?</button><span id="testout"></span>
 </div>
 <div class="gaps" id="gaps"></div>
 <details class="legend"><summary>What goes where?</summary>
  <div class="legendbody">
   <b>type</b> — which cluster an entity belongs to:
   <ul>
    <li><b>area</b> — a top-level grouping (WORK, PERSONAL…)</li>
    <li><b>project</b> — a project folder (carries a filename tag / production period)</li>
    <li><b>person</b> — a person or name (give their other names under <i>aliases</i>)</li>
    <li><b>category</b> — a functional subfolder reused across the tree (Bills, Docs, Scripts…)</li>
    <li><b>policy</b> — an entity whose rule is a <i>behaviour</i> (e.g. group files by event/date)</li>
    <li><b>atomic</b> — a whole folder treated as one locked unit, never opened file-by-file</li>
   </ul>
   <b>aliases</b> — other spellings/names that should route to this same entity (e.g. <i>Ishu</i> → Ishan).<br>
   <b>relation</b> — how it relates to you or another entity, free text (collaborator, client, spouse…).<br>
   <b>behaviour</b> — the specific routing behaviour, if any (e.g. <i>event-group</i>). This is different from the <i>policy</i> type: type says "this entity is a behaviour rule", behaviour says "what the rule does".<br>
   <b>notes</b> — anything else worth recording about the rule.
  </div>
 </details>
</header>
<div id="bulkbar" class="bulkbar" style="display:none">
 <span id="bulkn" class="pill">0 selected</span>
 <select onchange="bulkType(this.value);this.value=''"><option value="">set type…</option><option>area</option><option>project</option><option>person</option><option>category</option><option>policy</option><option>atomic</option><option>unknown</option></select>
 <button class="btn sm ghost warn" onclick="bulkRethink()">rethink selected</button>
 <button class="btn sm ghost bad" onclick="bulkDelete()">delete selected</button>
 <button class="btn sm ghost" onclick="bulkClear()">clear selection</button>
</div>
<main id="main"></main>
<dialog id="diff"><h3>Pending changes</h3><div id="diffbody"></div><div style="text-align:right;margin-top:10px"><button class="btn ghost" onclick="document.getElementById('diff').close()">close</button></div></dialog>
<div class="savebar">
 <span class="pill" id="dirty">0 unsaved changes</span>
 <button class="btn ghost" onclick="preview()">Preview changes</button>
 <button class="btn ghost" onclick="location.reload()">Discard all</button>
 <button class="btn ghost" onclick="apply()" title="write changes now and keep the editor open">Apply (keep open)</button>
 <button class="btn" onclick="save()">Save &amp; close</button>
</div>
<script>
let DATA = __DATA__;   // reassigned by apply() on keep-open refresh — must be `let`, not `const`
const PAGE = 25, CAP = 250;
const TYPE_HELP={area:'top-level grouping',project:'a project (has a filename tag/period)',person:'a person / name',category:'a functional subfolder (Bills, Docs…)',policy:'a behaviour rule (e.g. event-grouping)',atomic:'a locked whole-folder unit (never descended)',unknown:'not yet classified — please set'};
let changes = {entities:{}, rule_edits:{}, deletes:{}, rethink:{}, renames:{}, merges:{}, areas:{add:[],rename:[],remove:[]}};
let pages = {}; // cluster -> current page
function dirtyCount(){return Object.keys(changes.entities).length+Object.keys(changes.rule_edits).length+Object.keys(changes.deletes).length+Object.keys(changes.rethink).length+Object.keys(changes.renames).length+Object.keys(changes.merges).length+changes.areas.add.length+changes.areas.rename.length+changes.areas.remove.length;}
function markDirty(){document.getElementById('dirty').textContent=dirtyCount()+' unsaved change(s)';}
function byType(){const m={};for(const e of DATA.entities){(m[e.entity_type]=m[e.entity_type]||[]).push(e);}return m;}
function esc(s){return (s||'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
// For values dropped INTO a single-quoted JS string inside an onclick="..." attribute:
// backslash-escape \ and ' for the JS-string layer FIRST, then HTML-escape for the
// attribute layer. Plain esc() would emit &#39; which the HTML parser decodes back to
// a bare ' before the JS runs — breaking the call (or allowing injection) on names
// like "O'Brien". jsq() survives both layers.
function jsq(s){return esc(String(s==null?'':s).replace(/\\/g,'\\\\').replace(/'/g,"\\'"));}

function renderAreas(){
 const el=document.getElementById('areas');el.innerHTML='<span class="pill">Areas</span>';
 DATA.areas.forEach(a=>{const c=document.createElement('span');c.className='chip';
   c.innerHTML=`${esc(a)} <button title="rename" onclick="renameArea('${jsq(a)}')">✎</button><button title="remove" onclick="removeArea('${jsq(a)}')">✕</button>`;el.appendChild(c);});
 const add=document.createElement('button');add.className='btn sm ghost';add.textContent='+ area';add.onclick=addArea;el.appendChild(add);
}
function addArea(){const n=prompt('New area name (will be ALL-CAPS):');if(n){const u=n.toUpperCase();if(DATA.areas.indexOf(u)>=0)return;changes.areas.add.push(u);DATA.areas.push(u);renderAreas();markDirty();}}
function renameArea(a){const n=prompt('Rename '+a+' to:',a);if(n){const i=DATA.areas.indexOf(a);if(i<0)return;changes.areas.rename.push({old:a,new:n.toUpperCase()});DATA.areas[i]=n.toUpperCase();renderAreas();markDirty();}}
function removeArea(a){if(confirm('Remove area '+a+'? (refused if it still has files)')){changes.areas.remove.push(a);DATA.areas=DATA.areas.filter(x=>x!=a);renderAreas();markDirty();}}

let selected=new Set();
function card(e){
 const conf=DATA.conflicts[e.occurrences[0]?.dest]||[];
 const occ=e.occurrences.map(o=>`<div class="occ"><b>${esc(o.parent||'(root)')}/${esc(o.folderName)}</b> — ${esc(o.signal||'(no signal)')}</div>`).join('');
 const tags=[]; if(e.locked)tags.push('<span class="tag lock">locked</span>');
 if(e.dead&&e.occurrences.length)tags.push('<span class="tag dead">0 routed</span>');
 if(e.type_inferred)tags.push('<span class="tag inf">type?</span>');
 if(e.review||changes.rethink[e.entity])tags.push('<span class="tag rethink">rethink</span>');
 const types=['area','project','person','category','policy','atomic','unknown'];
 const ck=selected.has(e.entity)?'checked':'';
 return `<div class="card" data-e="${esc(e.entity)}">
  <h3><input type="checkbox" class="bulk" ${ck} onchange="toggleSel('${jsq(e.entity)}',this.checked)" title="select for bulk action"> ${esc(e.entity)} ${tags.join(' ')} <span class="tag">${e.usage_count} files</span></h3>
  <div class="meta">
   <label title="Which cluster this entity belongs to. See the 'What goes where' legend at the top.">type</label><select onchange="metaEdit('${jsq(e.entity)}','entity_type',this.value)">${types.map(t=>`<option value="${t}" ${t==e.entity_type?'selected':''}>${t} — ${TYPE_HELP[t]}</option>`).join('')}</select>
   <label title="Other names this same thing is known by, so they auto-route to it.">aliases</label><input value="${esc((e.aliases||[]).join(', '))}" placeholder="other names, e.g. Ishu, I.K." onchange="metaEdit('${jsq(e.entity)}','aliases',this.value.split(',').map(s=>s.trim()).filter(Boolean))">
   <label title="How this entity relates to you or to another entity (free text).">relation</label><input value="${esc(e.relation||'')}" placeholder="e.g. collaborator, client, spouse, employer" onchange="metaEdit('${jsq(e.entity)}','relation',this.value)">
   <label title="A routing behaviour for this entity's files (optional). Distinct from the 'policy' type: this is the specific rule.">behaviour</label><input value="${esc(e.policy||'')}" placeholder="e.g. event-group (group photos by date/event)" onchange="metaEdit('${jsq(e.entity)}','policy',this.value)">
   <label title="Free notes — what this rule is for, or why it exists.">notes</label><input value="${esc(e.notes||'')}" placeholder="free notes, e.g. 'thesis supervisor — files go under EDUCATION'" onchange="metaEdit('${jsq(e.entity)}','notes',this.value)">
  </div>
  ${occ}
  ${conf.length?`<div class="conflict">⚠ overlaps: ${conf.map(c=>esc(c.with)+' ['+c.shared.join(',')+']').join('; ')}</div>`:''}
  ${e.occurrences.length?`<label class="sub">signal (applies to all ${e.occurrences.length} folder(s))</label>
  <textarea onchange="signalEdit('${jsq(e.entity)}',this.value)">${esc(e.occurrences[0]?.signal||'')}</textarea>`:''}
  <div class="row">
   <button class="btn sm ghost" onclick="planMove('${jsq(e.entity)}')" title="dry-run a move up/down a level">move a level…</button>
   <button class="btn sm ghost" onclick="renameEntity('${jsq(e.entity)}')" title="rename this entity (rule + folder + registry)">rename</button>
   <button class="btn sm ghost" onclick="mergeEntity('${jsq(e.entity)}')" title="fold this into another entity as an alias">merge…</button>
   <button class="btn sm ghost warn" onclick="rethinkEntity('${jsq(e.entity)}')" title="flag for re-inference — keeps the rule, marks it to reconsider (≠ delete)">rethink</button>
   <button class="btn sm ghost bad" onclick="delEntity('${jsq(e.entity)}')" title="remove the routing rule (files/folders are NOT deleted)">delete</button>
   <span id="plan-${esc(e.entity)}" class="planline"></span>
  </div>
 </div>`;
}
function render(){
 document.getElementById('sub').textContent=`${DATA.root} — ${DATA.entities.length} entities (showing up to ${CAP}), ${PAGE}/page`;
 renderAreas();
 const gaps=DATA.coverage_gaps||[]; document.getElementById('gaps').innerHTML=gaps.length?`coverage gaps (folders with files, no rule): ${gaps.slice(0,12).map(esc).join(', ')}${gaps.length>12?' …':''}`:'';
 const m=byType();const main=document.getElementById('main');main.innerHTML='';
 for(const t of DATA.cluster_order){const ents=(m[t]||[]).slice(0,CAP);if(!ents.length)continue;
   pages[t]=pages[t]||0;const start=pages[t]*PAGE;const show=ents.slice(start,start+PAGE);
   const h=document.createElement('div');h.className='cluster';h.textContent=`${DATA.cluster_label[t]||t} (${ents.length})`;main.appendChild(h);
   const g=document.createElement('div');g.className='grid';g.innerHTML=show.map(card).join('');main.appendChild(g);
   if(ents.length>PAGE){const p=document.createElement('div');p.className='pager';
     p.innerHTML=`<button class="btn sm ghost" onclick="flip('${t}',-1)">‹</button><span>page ${pages[t]+1}/${Math.ceil(ents.length/PAGE)}</span><button class="btn sm ghost" onclick="flip('${t}',1)">›</button>`;main.appendChild(p);}
 }
 renderBulk();markDirty();
}
function flip(t,d){const m=byType();const n=Math.ceil(Math.min(m[t].length,CAP)/PAGE);pages[t]=Math.max(0,Math.min(n-1,pages[t]+d));render();}
function metaEdit(e,k,v){changes.entities[e]=changes.entities[e]||{};changes.entities[e][k]=v;markDirty();}
function signalEdit(e,v){changes.rule_edits[e]={entity:e,description:v};markDirty();}
function delEntity(e){if(confirm('Delete the routing rule for "'+e+'" everywhere? (files/folders are NOT deleted)')){changes.deletes[e]=true;markDirty();render();}}
function rethinkEntity(e){changes.rethink[e]=true;markDirty();render();}
function renameEntity(e){const n=prompt('Rename "'+e+'" to (renames the rule, the on-disk folder, and registry rows):',e);if(n&&n!=e){changes.renames[e]={entity:e,new_name:n};markDirty();render();}}
function mergeEntity(e){const d=prompt('Fold "'+e+'" INTO which entity? (its name becomes an alias of that one, its rule is removed)');if(d&&d!==e){changes.merges[e]={src:e,dst:d};markDirty();render();}}
// bulk
function toggleSel(e,on){on?selected.add(e):selected.delete(e);renderBulk();}
function renderBulk(){const b=document.getElementById('bulkbar');if(!selected.size){b.style.display='none';return;}
 b.style.display='flex';b.querySelector('#bulkn').textContent=selected.size+' selected';}
function bulkType(v){if(!v)return;selected.forEach(e=>metaEdit(e,'entity_type',v));render();}
function bulkRethink(){selected.forEach(e=>changes.rethink[e]=true);markDirty();render();}
function bulkDelete(){if(confirm('Delete rules for '+selected.size+' selected entities?')){selected.forEach(e=>changes.deletes[e]=true);selected.clear();markDirty();render();}}
function bulkClear(){selected.clear();render();}
async function testFile(){const fn=document.getElementById('testfile').value;if(!fn)return;
 const r=await fetch('/test',{method:'POST',body:JSON.stringify({filename:fn})});const j=await r.json();
 document.getElementById('testout').textContent=j.dest?`→ ${j.dest} (${j.reason})`:j.reason;}
async function planMove(e){const tgt=prompt('Promote/move "'+e+'" under which parent? (blank = top-level area)');if(tgt===null)return;
 const r=await fetch('/plan',{method:'POST',body:JSON.stringify({entity:e,target_parent:tgt})});const j=await r.json();
 document.getElementById('plan-'+e).textContent='DRY-RUN: '+(j.steps||[]).map(s=>`${s.move_folder.from}→${s.move_folder.to} (${s.registry_rows_to_update} rows)`).join('; ')+' — confirm via Apply/Save';}
// preview / diff + per-change undo
function pendingList(){const out=[];
 for(const[e,m]of Object.entries(changes.entities))out.push({k:'entities',e,label:`${e}: set ${Object.keys(m).join(', ')}`});
 for(const e of Object.keys(changes.rule_edits))out.push({k:'rule_edits',e,label:`${e}: edit signal`});
 for(const e of Object.keys(changes.deletes))out.push({k:'deletes',e,label:`${e}: DELETE rule`});
 for(const e of Object.keys(changes.rethink))out.push({k:'rethink',e,label:`${e}: rethink (re-infer)`});
 for(const e of Object.keys(changes.renames))out.push({k:'renames',e,label:`${e} → ${changes.renames[e].new_name}`});
 for(const e of Object.keys(changes.merges))out.push({k:'merges',e,label:`${e} ⤳ merge into ${changes.merges[e].dst}`});
 changes.areas.add.forEach((a,i)=>out.push({k:'areas.add',e:i,label:`area + ${a}`}));
 changes.areas.rename.forEach((a,i)=>out.push({k:'areas.rename',e:i,label:`area ${a.old} → ${a.new}`}));
 changes.areas.remove.forEach((a,i)=>out.push({k:'areas.remove',e:i,label:`area − ${a}`}));
 return out;}
function undo(k,e){if(k.startsWith('areas.')){const sub=k.split('.')[1];changes.areas[sub].splice(e,1);}else{delete changes[k][e];}preview();render();}
function preview(){const l=pendingList();const dlg=document.getElementById('diff');
 dlg.querySelector('#diffbody').innerHTML=l.length?l.map(x=>`<div class="diffrow"><span>${esc(x.label)}</span><button class="btn sm ghost" onclick="undo('${jsq(x.k)}','${jsq(x.e)}')">undo</button></div>`).join(''):'<i>no pending changes</i>';
 if(!dlg.open)dlg.showModal();}
function payload(extra){return Object.assign({entities:changes.entities,rule_edits:Object.values(changes.rule_edits),deletes:Object.keys(changes.deletes),rethink:Object.keys(changes.rethink),renames:Object.values(changes.renames),merges:Object.values(changes.merges),areas:changes.areas},extra||{});}
function clearChanges(){changes={entities:{},rule_edits:{},deletes:{},rethink:{},renames:{},merges:{},areas:{add:[],rename:[],remove:[]}};selected.clear();}
async function apply(){const r=await fetch('/apply',{method:'POST',body:JSON.stringify(payload())});const j=await r.json();
 if(r.ok&&j.ok){const d=document.getElementById('diff');if(d.open)d.close();
   if(j.data)DATA=j.data;
   clearChanges();render();
   document.getElementById('dirty').textContent='applied ✓ — kept open';}
 else{document.getElementById('dirty').textContent='apply failed: '+((j&&j.error)||('HTTP '+r.status));}}
async function save(){const r=await fetch('/save',{method:'POST',body:JSON.stringify(payload())});const j=await r.json();
 document.body.innerHTML='<main style="padding:20px"><h1>Saved</h1><pre>'+esc(JSON.stringify(j.results,null,2))+'</pre><p>You can close this tab.</p></main>';}
render();
</script></body></html>"""


def _reset_caches():
    """Clear the process-level template/grouping caches so a live (keepalive) save
    re-reads config + templates and the refreshed view reflects area changes."""
    global _TEMPLATES_CACHE, _GROUPINGS_CACHE
    _TEMPLATES_CACHE = None
    _GROUPINGS_CACHE = None


class _RulesHandler(BaseHTTPRequestHandler):
    """Serves the rules viewer/editor and applies edits on submit."""
    _root: Path = None

    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path not in ("/", "/index.html"):
            self._send(404, {"error": "not found"})
            return
        root = self.__class__._root
        agg = _aggregate_rules(root)
        index, dest_set = _build_rules_index(root)
        payload = {
            "root": str(root),
            "areas": sorted(_active_groupings()),
            "entities": agg,
            "conflicts": _conflicts_for(index),
            "coverage_gaps": _coverage_gaps(root, dest_set),
            "cluster_order": _CLUSTER_ORDER,
            "cluster_label": _CLUSTER_LABEL,
        }
        data_js = json.dumps(payload).replace("</", "<\\/")
        html = _RULES_VIEWER_HTML.replace("__DATA__", data_js)
        self._send(200, html, "text/html; charset=utf-8")

    _MAX_BODY = 8 * 1024 * 1024  # cap request body at 8 MiB

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
        except (TypeError, ValueError):
            self._send(400, {"error": "bad content-length"}); return
        if length < 0 or length > self._MAX_BODY:
            self._send(400, {"error": "body too large"}); return
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._send(400, {"error": "bad json"}); return
        root = self.__class__._root

        if self.path == "/test":
            # test-a-file: run the W1 matcher on a pasted filename (read-only)
            index, dest_set = _build_rules_index(root)
            entry = {"filename": payload.get("filename", ""),
                     "current_path": str(root / payload.get("filename", "")),
                     "is_image": False, "extension": ""}
            dest, reason = _auto_classify_entry(entry, root, index, dest_set)
            self._send(200, {"dest": dest, "reason": reason or "no deterministic match — would go to the classifier"})
            return

        if self.path == "/plan":
            agg = {e["entity"]: e for e in _aggregate_rules(root)}
            ent = agg.get(payload.get("entity"))
            if not ent:
                self._send(404, {"error": "unknown entity"}); return
            self._send(200, _promotion_plan(root, ent["entity"], ent["occurrences"],
                                            payload.get("target_parent", "")))
            return

        if self.path in ("/save", "/apply"):
            keepalive = (self.path == "/apply") or bool(payload.get("keepalive"))
            META_KEYS = ("entity_type", "locked", "aliases", "relation", "policy", "notes", "review")
            agg = {e["entity"]: e for e in _aggregate_rules(root)}
            results = {"meta": 0, "rule_edits": 0, "deletes": 0, "rethink": 0,
                       "renames": [], "merges": [], "areas": None}
            cur = _read_entities(root)
            # entity metadata -> entities.json (merge per-key; clear emptied keys)
            meta_in = payload.get("entities") or {}
            for name, m in meta_in.items():
                base = dict(cur.get(name, {}))
                for k in META_KEYS:
                    if k not in m:
                        continue
                    v = m[k]
                    if v in (None, "", [], {}):
                        base.pop(k, None)
                    else:
                        base[k] = v
                if base:
                    cur[name] = base
                elif name in cur:
                    del cur[name]
                results["meta"] += 1
            # rethink: flag an entity for re-inference (distinct from delete)
            for name in payload.get("rethink") or []:
                cur.setdefault(name, {})["review"] = True
                results["rethink"] += 1
            if meta_in or payload.get("rethink"):
                _write_entities(root, cur)
            # signal/description edits across occurrences (areas may need rule creation)
            for ed in payload.get("rule_edits") or []:
                ent = agg.get(ed.get("entity"))
                if ent:
                    is_area = ent.get("entity_type") == "area" or ent.get("synthetic_area")
                    results["rule_edits"] += _edit_rule_across_occurrences(
                        root, ent["entity"], ent["occurrences"],
                        new_description=ed.get("description"), create_if_missing=is_area)
            # delete a rule everywhere
            for name in payload.get("deletes") or []:
                ent = agg.get(name)
                if ent:
                    results["deletes"] += _edit_rule_across_occurrences(
                        root, ent["entity"], ent["occurrences"], delete=True)
            # rename an entity (rule + on-disk folder + registry)
            for rn in payload.get("renames") or []:
                ent = agg.get(rn.get("entity"))
                if ent and rn.get("new_name"):
                    results["renames"].append(_rename_entity(
                        root, ent["entity"], ent["occurrences"], rn["new_name"], apply=True))
            # merge an entity into another (fold as alias + delete its rules)
            for mg in payload.get("merges") or []:
                ent = agg.get(mg.get("src"))
                if ent and mg.get("dst"):
                    results["merges"].append(_merge_entities(root, ent, mg["dst"]))
            # area changes
            ac = payload.get("areas")
            if ac and (ac.get("add") or ac.get("rename") or ac.get("remove")):
                results["areas"] = _apply_area_changes(
                    root, ac.get("add"), ac.get("rename"), ac.get("remove"))

            resp = {"ok": True, "results": results}
            if keepalive:
                _reset_caches()
                index, dest_set = _build_rules_index(root)
                resp["data"] = {
                    "root": str(root), "areas": sorted(_active_groupings()),
                    "entities": _aggregate_rules(root), "conflicts": _conflicts_for(index),
                    "coverage_gaps": _coverage_gaps(root, dest_set),
                    "cluster_order": _CLUSTER_ORDER, "cluster_label": _CLUSTER_LABEL,
                }
            self._send(200, resp)
            if not keepalive and self.server is not None:
                # Flush the response to the client BEFORE signalling shutdown, so the
                # stop event can't race the client's read of the save confirmation.
                try:
                    self.wfile.flush()
                except (OSError, ValueError):
                    pass
                self.server._stop_event.set()
            return

        self._send(404, {"error": "not found"})


def cmd_inbox_list(args):
    """List every file currently sitting in _Inbox (organized there, awaiting a real home)
    as JSON: {count, files:[{id, filename, current_path}]}. Feeds the periodic arbiter
    sweep (SKILL.md: when count reaches ~100, re-judge ALL of them against the now-larger
    rule set — files inboxed in earlier rounds may now be placeable)."""
    conn = get_db()
    rows = conn.execute(
        "SELECT id, filename, current_path FROM files "
        "WHERE status='organized' AND (para_subfolder='_Inbox' OR para_subfolder LIKE '_Inbox/%') "
        "ORDER BY id"
    ).fetchall()
    conn.close()
    out = {"count": len(rows),
           "files": [{"id": r["id"], "filename": r["filename"], "current_path": r["current_path"]}
                     for r in rows]}
    print(json.dumps(out, indent=2))


def cmd_rules_viewer(args):
    """Launch the browser rules viewer/editor on the aggregated rule set."""
    root = Path(_EFFECTIVE_ROOT)
    port = int(getattr(args, "port", None) or 5003)
    _RulesHandler._root = root
    server = HTTPServer(("127.0.0.1", port), _RulesHandler)
    server.timeout = 1.0
    server._stop_event = threading.Event()
    t = threading.Thread(target=_serve_until, args=(server, server._stop_event), daemon=True)
    t.start()
    url = f"http://localhost:{port}/"
    n = len(_aggregate_rules(root))
    print(f"Rules viewer running at {url}")
    print(f"{n} entities across {len(_active_groupings())} areas. Submit in the browser to save + stop.")
    if not getattr(args, "no_open", False):
        webbrowser.open(url)
    try:
        server._stop_event.wait()
    except KeyboardInterrupt:
        print("\nInterrupted — shutting down.")
    finally:
        server.shutdown()


# ---------------------------------------------------------------------------
# W3 — Bootstrap rules-builder: reverse-engineer rules from a drive's existing
# organisation. Atomic-units are detected + approved + LOCKED first (never
# descended). Then every unruled folder with files is sampled and emitted for
# Claude's inference; the proposals are reviewed in the W2 viewer and written
# back. Two modes: cold-start (whole taxonomy) and audit (unruled + drift).
# ---------------------------------------------------------------------------

_ATOMIC_DIR_NAMES = {"node_modules", ".git", "venv", ".venv", "env", "__pycache__",
                     ".tox", "site-packages", "Pods", "vendor"}
_ATOMIC_SUFFIXES = (".app", ".framework", ".bundle", ".xcodeproj", ".photoslibrary",
                    ".imovielibrary", ".tvlibrary", ".aplibrary")


def _atomic_marker(p: Path) -> "str | None":
    """Return a short marker string if folder p is an atomic unit, else None."""
    n = p.name
    if n in _ATOMIC_DIR_NAMES:
        return n
    if n.endswith(_ATOMIC_SUFFIXES):
        return "bundle"
    try:
        if (p / "pyvenv.cfg").exists():
            return "venv"
        if (p / "zotero.sqlite").exists():
            return "zotero"
        if (p / "Assets").is_dir() and (p / "ProjectSettings").is_dir():
            return "unity"
        if (p / ".git").is_dir():
            return "git-repo"
    except (PermissionError, OSError):
        pass
    return None


def _detect_atomic_units(root: Path) -> list:
    """Walk the tree and flag atomic-unit folders (without descending into them).
    Returns {folder, name, marker, file_count, locked}. The user approves these in
    the bootstrap walkthrough; on approval they're written locked to entities.json."""
    root = Path(root)
    locked = _locked_atomic_names(root)
    out, skip = [], {".organizer", "logseq-journals"}
    for cur, dirs, files in os.walk(root):
        cp = Path(cur)
        keep = []
        for d in dirs:
            if d in skip:
                continue
            dp = cp / d
            marker = _atomic_marker(dp)
            if marker:
                try:
                    rel = str(dp.relative_to(root))
                    # Count direct children only — a full rglob would recurse huge
                    # node_modules/.git trees of a locked unit just to report a count.
                    fc = sum(1 for c in dp.iterdir() if c.is_file())
                except (PermissionError, OSError):
                    rel, fc = str(dp), 0
                out.append({"folder": rel, "name": d, "marker": marker,
                            "file_count": fc, "locked": d in locked})
                # do NOT descend into an atomic unit
            else:
                keep.append(d)
        dirs[:] = keep
    return out


def _bootstrap_candidates(root: Path, mode: str = "cold-start",
                          sample_k: int = 5, limit: int = 250) -> dict:
    """Enumerate folders to infer rules for. Candidates = folders that hold files
    but have no rule, excluding locked-atomic / external / staging. Each carries a
    sample of K files (name + content_peek + ext) for Claude to infer from. In audit
    mode, additionally flag ruled folders whose sampled file routes elsewhere (drift)."""
    root = Path(root)
    index, dest_set = _build_rules_index(root)
    locked_atomic = _locked_atomic_names(root)
    skip = {".organizer", "logseq-journals", "Archive", "_Inbox"}
    candidates, drift = [], []
    for cur, dirs, files in os.walk(root):
        cp = Path(cur)
        # prune: hidden, staging, x-folders, locked atomic, external, atomic units
        keep = []
        for d in dirs:
            dp = cp / d
            if (d in skip or d.startswith("x") or d in locked_atomic
                    or _atomic_marker(dp) or _is_external(dp)):
                continue
            keep.append(d)
        dirs[:] = keep
        try:
            rel = "" if cp == root else str(cp.relative_to(root))
        except Exception:
            continue
        if rel == "" or any(part in skip or part.startswith("x") for part in Path(rel).parts):
            continue
        real_files = [f for f in files if not should_skip(cp / f)]
        if not real_files:
            continue
        has_rule = (cp / ".tidy-rules.json").exists() or rel in dest_set
        # sample
        sample = []
        for fn in real_files[:sample_k]:
            fp = cp / fn
            peek = None
            try:
                peek = peek_content(fp)
            except Exception:
                pass
            sample.append({"name": fn, "ext": fp.suffix.lower(), "peek": (peek or "")[:200]})
        if not has_rule:
            candidates.append({
                "folder": rel, "name": cp.name, "parent": str(Path(rel).parent) if Path(rel).parent != Path(".") else "",
                "file_count": len(real_files), "sample": sample,
            })
        elif mode == "audit" and sample:
            # quick drift flag: does a sampled file route somewhere other than here?
            e = {"filename": sample[0]["name"], "current_path": str(cp / sample[0]["name"]),
                 "is_image": False, "extension": sample[0]["ext"]}
            dest, _r = _auto_classify_entry(e, root, index, dest_set)
            if dest and dest != rel and dest != "already in ruled folder":
                drift.append({"folder": rel, "sampled": sample[0]["name"], "matches_instead": dest})
    capped = candidates[:limit]
    for i, c in enumerate(capped):
        c["batch"] = i // 25
    return {"mode": mode, "n_candidates": len(candidates), "emitted": len(capped),
            "n_batches": (len(capped) + 24) // 25, "candidates": capped,
            "drift": drift, "dropped": max(0, len(candidates) - len(capped))}


def _bootstrap_apply(root: Path, proposed: dict) -> dict:
    """Write approved bootstrap proposals: rules into each folder's PARENT
    .tidy-rules.json (folderName=leaf), and entity metadata into entities.json."""
    root = Path(root)
    res = {"rules_written": 0, "entities": 0}
    for rule in proposed.get("rules", []):
        parent_rel = rule.get("parent", "") or ""
        folder = rule.get("folderName")
        desc = rule.get("description", "")
        if not folder:
            continue
        # Reject path-traversal / absolute parents — the proposals file is Claude-authored
        # and untrusted; a `../`, absolute, or symlink-escaping `parent` would write a rules
        # file outside the drive root. _safe_dest validates AND returns the resolved write
        # target, so the validation target is identical to the write target.
        if os.path.isabs(folder):
            res.setdefault("rejected", []).append({"parent": parent_rel, "folderName": folder, "why": "absolute path"})
            continue
        sub = os.path.join(parent_rel, ".tidy-rules.json") if parent_rel else ".tidy-rules.json"
        pf = _safe_dest(root, sub)
        if pf is None:
            res.setdefault("rejected", []).append({"parent": parent_rel, "folderName": folder, "why": "escapes root"})
            continue
        leaf = folder.split("/")[-1]
        if desc and not desc.endswith(f"in {leaf}"):
            desc = f"{desc} in {leaf}"
        data = {"rules": []}
        if pf.exists():
            try:
                data = json.loads(pf.read_text())
            except Exception:
                data = {"rules": []}
        rules = data.get("rules", []) if isinstance(data, dict) else data
        existing = next((r for r in rules if isinstance(r, dict) and r.get("folderName") == folder), None)
        if existing:
            existing["description"] = desc or existing.get("description", "")
        else:
            rules.append({"folderName": folder, "description": desc})
        # Always normalise to {"rules": [...]} on write — a previously bare-list file
        # would otherwise be rewritten as a bare list, dropping any sibling keys.
        if isinstance(data, dict):
            data["rules"] = rules
        else:
            data = {"rules": rules}
        pf.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(pf, json.dumps(data, indent=2, ensure_ascii=False))
        res["rules_written"] += 1
    ent = proposed.get("entities") or {}
    if ent:
        cur = _read_entities(root)
        for name, m in ent.items():
            base = dict(cur.get(name, {}))
            base.update({k: v for k, v in m.items() if v not in (None, "", [], {})})
            cur[name] = base
        _write_entities(root, cur)
        res["entities"] = len(ent)
    return res


def cmd_bootstrap(args):
    """Bootstrap rules from an existing tree. Steps:
      --detect-atomic         list atomic-unit folders (approve these first)
      --lock NAMES            write named atomic units locked to entities.json
      --emit [--mode M]       sample unruled folders -> <root>/.organizer/bootstrap-input.json
      --apply FILE            write approved proposals (rules + entities)
    The inference between --emit and --apply is Claude's (see SKILL.md); the result
    is reviewed in `rules-viewer` before/after apply."""
    root = Path(_EFFECTIVE_ROOT)
    if getattr(args, "detect_atomic", False):
        units = _detect_atomic_units(root)
        if getattr(args, "json", False):
            print(json.dumps(units, indent=2)); return
        print(f"Atomic-unit folders ({len(units)}) — approve to lock (never descended again):")
        for u in units:
            print(f"  [{'LOCKED' if u['locked'] else 'new'}] {u['folder']}  ({u['marker']}, {u['file_count']} files)")
        if units:
            print("\nLock all new ones:  bootstrap --lock " + ",".join(u["name"] for u in units if not u["locked"]))
        return
    if getattr(args, "lock", None):
        names = [n.strip() for n in args.lock.split(",") if n.strip()]
        cur = _read_entities(root)
        for n in names:
            base = dict(cur.get(n, {}))
            base["entity_type"] = "atomic"; base["locked"] = True
            cur[n] = base
        _write_entities(root, cur)
        print(f"Locked {len(names)} atomic unit(s): {', '.join(names)}")
        return
    if getattr(args, "apply", None):
        path = Path(args.apply)
        if not path.exists():
            sys.exit(f"Error: proposals file not found: {path}")
        try:
            proposed = json.loads(path.read_text())
        except (ValueError, OSError) as e:
            sys.exit(f"Error: could not parse proposals file {path}: {e}. It must be a JSON "
                     f"object with 'rules'/'entities' keys. See SKILL.md bootstrap step 4 for the shape.")
        if not isinstance(proposed, dict):
            sys.exit(f"Error: proposals file must be a JSON object with 'rules'/'entities' keys, "
                     f"got a {type(proposed).__name__}. See SKILL.md bootstrap step 4 for the shape.")
        res = _bootstrap_apply(root, proposed)
        print(f"Bootstrap applied: {res['rules_written']} rules, {res['entities']} entity metadata entries.")
        print("Review/edit with:  rules-viewer")
        return
    # default / --emit
    mode = getattr(args, "mode", None) or "cold-start"
    sample_k = int(getattr(args, "sample", None) or 5)
    limit = int(getattr(args, "limit", None) or 250)
    atomic = _detect_atomic_units(root)
    cand = _bootstrap_candidates(root, mode=mode, sample_k=sample_k, limit=limit)
    out = {"root": str(root), "mode": mode, "atomic_units": atomic, **cand}
    dest = root / ".organizer" / "bootstrap-input.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    unlocked = [u for u in atomic if not u["locked"]]
    print(f"Bootstrap input written: {dest}")
    print(f"  mode: {mode}")
    print(f"  atomic units: {len(atomic)} ({len(unlocked)} not yet locked)")
    print(f"  inference candidates: {cand['emitted']} folder(s) in {cand['n_batches']} batch(es) of 25"
          + (f" ({cand['dropped']} over the {limit} cap, deferred)" if cand["dropped"] else ""))
    if mode == "audit" and cand["drift"]:
        print(f"  drift flagged: {len(cand['drift'])} ruled folder(s) whose sample routes elsewhere")
    if unlocked:
        print("\nNext: approve atomic units →  bootstrap --lock " + ",".join(u["name"] for u in unlocked))
    print("Then Claude infers each candidate's rule/type from its sample (fan-out, 25/batch),"
          " writes a proposals file, and you run:  bootstrap --apply <file>  →  rules-viewer")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Folder Organizer backend")
    parser.add_argument(
        "--root", default=None, metavar="PATH",
        help="Root folder to organise; registry lives at <root>/.organizer/ "
             "(default: ~/Library/CloudStorage/OneDrive-Personal)"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_dl = sub.add_parser("download-batch")
    p_dl.add_argument("path", nargs="?", help="root path")
    p_dl.add_argument("--limit-gb", default="20", help="Max GB to queue (default 20)")

    p_scan = sub.add_parser("scan")
    p_scan.add_argument("path", nargs="?")
    p_scan.add_argument("--limit", type=int, default=250, help="Max files per scan batch (default 250)")
    p_scan.add_argument("--limit-gb", default="20", help="Max cumulative GB per batch (default 20)")

    p_propose = sub.add_parser("propose")
    p_propose.add_argument("--limit", type=int, default=250)
    p_propose.add_argument("--no-auto-classify", action="store_true", dest="no_auto_classify",
                           help="Disable the W1 deterministic fast-path; send every file to classification")
    p_propose.add_argument("--auto-classify", action="store_true", dest="auto_classify",
                           help="Force the W1 fast-path on for this run (overrides config)")
    p_propose.add_argument("--no-vision", action="store_true", dest="no_vision",
                           help="W1b cost toggle: never open images for vision; route them by name/path/rule only")
    p_propose.add_argument("--skip-types", dest="skip_types", metavar="EXT,EXT",
                           help="W1b cost toggle: comma-separated extensions the classifier never opens (e.g. .mov,.raw)")
    p_propose.add_argument("--skip-over-mb", dest="skip_over_mb", type=float, metavar="N",
                           help="W1b cost toggle: files larger than N MB are never opened (routed by name/path/rule only)")
    p_propose.add_argument("--auto-approve", action="store_true", dest="auto_approve",
                           help="W5: mark high-confidence auto-routed files auto_approved (orchestrator may skip the viewer)")

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

    p_cleanup = sub.add_parser("cleanup")
    p_cleanup.add_argument("path", nargs="?", help="root path")

    sub.add_parser("csv-export", help="Refresh <root>/.organizer/registry.csv from the SQLite registry")
    sub.add_parser("templates", help="Print merged templates (shipped skeleton + per-user override) as JSON")

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
    p_bs.add_argument("--limit", type=int, default=250, help="Max candidate folders (default 250)")
    p_bs.add_argument("--json", action="store_true", help="JSON output (for --detect-atomic)")

    p_mark = sub.add_parser("mark-unapproved",
                             help="Prefix non-approved root folders with 'x' to defer them")
    p_mark.add_argument("path", nargs="?", help="root path")

    args = parser.parse_args()

    # Derive root: --root flag (saves to config) > saved config > DEFAULT_ONEDRIVE
    global REGISTRY_DB, CSV_EXPORT_PATH, _EFFECTIVE_ROOT
    if args.root:
        _EFFECTIVE_ROOT = Path(args.root).expanduser().resolve()
        _save_config_root(_EFFECTIVE_ROOT)
    else:
        _EFFECTIVE_ROOT = _read_config_root() or DEFAULT_ONEDRIVE

    REGISTRY_DB     = _EFFECTIVE_ROOT / ".organizer" / "registry.db"
    CSV_EXPORT_PATH = _EFFECTIVE_ROOT / ".organizer" / "registry.csv"

    # Auto-migrate from legacy ~/.claude/drive-organizer/ location (first run only)
    _legacy_db = Path.home() / ".claude" / "drive-organizer" / "registry.db"
    if not REGISTRY_DB.exists() and _legacy_db.exists() and _EFFECTIVE_ROOT == DEFAULT_ONEDRIVE:
        REGISTRY_DB.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(_legacy_db), str(REGISTRY_DB))
        print(f"Note: registry migrated from {_legacy_db} to {REGISTRY_DB}", file=sys.stderr)
        _legacy_csv = _legacy_db.parent / "registry.csv"
        if _legacy_csv.exists() and not CSV_EXPORT_PATH.exists():
            shutil.copy2(str(_legacy_csv), str(CSV_EXPORT_PATH))

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
        "mark-unapproved":  cmd_mark_unapproved,
        "templates":        cmd_templates,
        "reconcile":        cmd_reconcile,
        "rules":            cmd_rules,
        "rules-viewer":     cmd_rules_viewer,
        "bootstrap":        cmd_bootstrap,
        "inbox-list":       cmd_inbox_list,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
