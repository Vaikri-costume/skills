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

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
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

# Cloud-download polling. The scan used to do a single fixed 0.5s check after
# triggering a download and skip the file if it hadn't materialised yet — so any
# file slower than one tick was deferred to a future scan, which is the main
# cause of slow multi-pass cycles. Now scan polls up to a timeout so the file
# downloads within the same pass. Tunable via env (DRIVE_ORG_DL_TIMEOUT seconds).
DOWNLOAD_POLL_INTERVAL = 0.5
DOWNLOAD_POLL_TIMEOUT  = float(os.environ.get("DRIVE_ORG_DL_TIMEOUT", "30"))


# ---------------------------------------------------------------------------
# Config (saved active root)
# ---------------------------------------------------------------------------

def _read_config_root() -> "Path | None":
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text())
            root = data.get("root")
            if root:
                return Path(root).expanduser().resolve()
        except Exception:
            pass
    return None


def _save_config_root(root: Path):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps({"root": str(root)}, indent=2))


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
            data = json.loads(root_rules.read_text())
            folder_name = folder_path.name
            for rule in data.get("rules", []):
                top = rule.get("folderName", "").split("/")[0]
                if top == folder_name:
                    return True
        except Exception:
            pass
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
        data = json.loads(rules_file.read_text())
    except Exception:
        return False
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
    """
    items = base_list + override_list
    if items and all(isinstance(x, dict) and "name" in x for x in items):
        by_name = {x["name"]: x for x in base_list}
        for x in override_list:
            by_name[x["name"]] = x  # override wins
        result, seen = [], set()
        for x in base_list + override_list:
            if x["name"] not in seen:
                result.append(by_name[x["name"]])
                seen.add(x["name"])
        return result
    return base_list + [x for x in override_list if x not in base_list]


def _deep_merge(base: dict, override: dict) -> dict:
    """
    Recursively merge `override` into a copy of `base`. Dicts merge key-by-key;
    lists merge via _merge_lists (by "name" when present, else concat+dedup);
    scalars from the override win. Used to layer a per-user template override
    over the shipped skeleton.
    """
    out = dict(base)
    for k, v in override.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        elif k in out and isinstance(out[k], list) and isinstance(v, list):
            out[k] = _merge_lists(out[k], v)
        else:
            out[k] = v
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
    if not root:
        return {}
    cfg = Path(root) / ".organizer" / "config.json"
    if not cfg.exists():
        return {}
    try:
        data = json.loads(cfg.read_text())
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


_TEMPLATES_CACHE = None

def _load_templates() -> dict:
    """
    Load the subfolder templates source-of-truth from the skill's references folder,
    then deep-merge any per-user override at <root>/.organizer/templates.json on top.
    Cached for the lifetime of the process. Returns {} if the shipped file is missing.

    The shipped file is a generic skeleton (the five Q1 groupings + universal compound
    children). Each user grows their own taxonomy lazily via .tidy-rules.json, and may
    also drop a templates.json beside their registry to extend the skeleton with their
    own projects/structure — that override is merged here so the shipped skill stays
    generic while the user's drive carries their specifics.
    """
    global _TEMPLATES_CACHE
    if _TEMPLATES_CACHE is not None:
        return _TEMPLATES_CACHE
    templates_path = Path.home() / ".claude" / "skills" / "drive-organizer" / "references" / "subfolder-templates.json"
    base = {}
    if templates_path.exists():
        try:
            base = json.loads(templates_path.read_text())
        except Exception:
            base = {}
    # Per-user override on the active drive (never shipped with the skill).
    if _EFFECTIVE_ROOT:
        override_path = Path(_EFFECTIVE_ROOT) / ".organizer" / "templates.json"
        if override_path.exists():
            try:
                override = json.loads(override_path.read_text())
                if isinstance(override, dict):
                    base = _deep_merge(base, override)
            except Exception:
                pass
    _TEMPLATES_CACHE = base
    return _TEMPLATES_CACHE


def cmd_templates(args):
    """Print the effective templates as JSON — the shipped generic skeleton
    deep-merged with the per-user <root>/.organizer/templates.json override.
    The propose flow loads THIS (not the raw shipped file) so the executor sees
    the user's full taxonomy, not just the generic skeleton."""
    print(json.dumps(_load_templates(), ensure_ascii=False, indent=2))


def _bubble_sort_proposals(proposals: list) -> list:
    """
    Bubble-sort proposals by destination so files going to the same leaf
    appear together in the viewer. Sort key: (para_subfolder, filename).
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
        data = json.loads(rules_file.read_text())
    except Exception:
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
    for top in sorted(root.iterdir()):
        if not top.is_dir() or top.name.startswith(('.', '_')):
            continue
        if top.name.startswith('x') or top.name in SKIP:
            continue
        # Direct-level project (legacy flat)
        meta = _project_metadata(top)
        if meta.get("filename_tag"):
            out.append({"path": top.name, **meta})
        # Two-level (new nested: WORK/COMPANY/PROJECT, PERSONAL/PERSONAL X)
        try:
            for mid in sorted(top.iterdir()):
                if not mid.is_dir() or mid.name.startswith('.'):
                    continue
                meta_mid = _project_metadata(mid)
                if meta_mid.get("filename_tag"):
                    out.append({"path": f"{top.name}/{mid.name}", **meta_mid})
                # Three-level (e.g. WORK/VAIKRI/VAIKRI CS Yeh Saali Naukri/)
                try:
                    for deep in sorted(mid.iterdir()):
                        if not deep.is_dir() or deep.name.startswith('.'):
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
    cur = root / dest_subfolder
    # Walk up until cur is root
    while True:
        if cur == root or cur.parent == cur:
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
        data = json.loads(rules_file.read_text())
    except Exception:
        return
    if not isinstance(data, dict):
        return  # legacy list-format files don't carry project metadata

    try:
        file_dt = datetime.fromisoformat(file_date_iso[:10])
    except (ValueError, TypeError):
        return

    buf = timedelta(days=buffer_days)
    period = data.get("production_period")
    if not period or not isinstance(period, dict):
        new_start = (file_dt - buf).date().isoformat()
        new_end = (file_dt + buf).date().isoformat()
    else:
        try:
            cur_start = datetime.fromisoformat(period["start"][:10]) if period.get("start") else file_dt
            cur_end = datetime.fromisoformat(period["end"][:10]) if period.get("end") else file_dt
        except (ValueError, KeyError, TypeError):
            cur_start = file_dt
            cur_end = file_dt
        new_start_dt = min(cur_start, file_dt - buf)
        new_end_dt = max(cur_end, file_dt + buf)
        new_start = new_start_dt.date().isoformat()
        new_end = new_end_dt.date().isoformat()

    if data.get("production_period") == {"start": new_start, "end": new_end}:
        return  # nothing changed
    data["production_period"] = {"start": new_start, "end": new_end}
    rules_file.write_text(json.dumps(data, indent=2))


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
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
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
    except Exception:
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


def _peek_pdf(path: Path) -> str | None:
    try:
        import fitz
        doc = fitz.open(str(path))
        text = ""
        for page in doc[:3]:
            text += page.get_text()
            if len(text) >= PEEK_CHARS * 2:
                break
        doc.close()
        return _clean(text)
    except ImportError:
        return None


def _peek_zip_xml(path: Path, extractor) -> str | None:
    try:
        with zipfile.ZipFile(str(path)) as zf:
            return extractor(zf)
    except (zipfile.BadZipFile, KeyError):
        return None


def _docx_text(zf: zipfile.ZipFile) -> str | None:
    ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    with zf.open("word/document.xml") as f:
        root = ET.parse(f).getroot()
    texts = [el.text for el in root.iter(f"{{{ns}}}t") if el.text]
    return _clean(" ".join(texts))


def _xlsx_text(zf: zipfile.ZipFile) -> str | None:
    # Shared strings contains all cell text
    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    try:
        with zf.open("xl/sharedStrings.xml") as f:
            root = ET.parse(f).getroot()
        texts = [el.text for el in root.iter(f"{{{ns}}}t") if el.text]
        return _clean(" ".join(texts[:40]))
    except KeyError:
        # No shared strings → likely an empty or numbers-only sheet
        return None


def _pptx_text(zf: zipfile.ZipFile) -> str | None:
    ns = "http://schemas.openxmlformats.org/drawingml/2006/main"
    texts = []
    # Read first 3 slides
    for i in range(1, 4):
        slide_path = f"ppt/slides/slide{i}.xml"
        try:
            with zf.open(slide_path) as f:
                root = ET.parse(f).getroot()
            texts += [el.text for el in root.iter(f"{{{ns}}}t") if el.text]
        except KeyError:
            break
    return _clean(" ".join(texts)) if texts else None


def _peek_fdx(path: Path) -> str | None:
    root = ET.parse(str(path)).getroot()
    # FDX: try title page first, then first 5 paragraphs
    title_el = root.find(".//TitlePage")
    source = title_el if title_el is not None else root
    paragraphs = list(source.iter("Paragraph"))[:8]
    texts = []
    for p in paragraphs:
        for el in p.iter():
            if el.text and el.text.strip():
                texts.append(el.text.strip())
    return _clean(" ".join(texts)) if texts else None


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

def _is_placeholder(path: Path) -> bool:
    """
    Is this file a cloud-only placeholder (not downloaded locally)?

    Primary signal: the macOS dataless flag (UF_DATALESS), which modern
    FileProvider-based clients — OneDrive's ~/Library/CloudStorage mount, iCloud
    Drive, etc. — set on files whose bytes live only in the cloud. Equivalently,
    such a file reports a real logical size but ZERO allocated blocks. (The old
    xattr-marker heuristic missed these entirely — a dataless OneDrive file
    carries only com.apple.FinderInfo, none of the provider markers — so the
    whole cloud-download path silently never fired.) Legacy xattr markers are
    kept as a fallback for older sync clients. Returns False on error (treat as
    local rather than risk a spurious download).
    """
    try:
        st = os.stat(path)
        if getattr(st, "st_flags", 0) & _UF_DATALESS:
            return True
        if st.st_size > 0 and getattr(st, "st_blocks", 1) == 0:
            return True
    except OSError:
        return False
    try:
        result = subprocess.run(
            ["xattr", str(path)],
            capture_output=True, text=True, timeout=1
        )
        return any(m in result.stdout for m in [
            "com.microsoft.OneDrive",
            "com.apple.cloud.itemState",
            "com.apple.fileprovider",
        ])
    except Exception:
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

    # Skip already-organised files so we don't re-download freed-up content
    organized_paths: set[str] = set()
    if REGISTRY_DB.exists():
        try:
            with sqlite3.connect(str(REGISTRY_DB)) as _db:
                _db.row_factory = sqlite3.Row
                organized_paths = {
                    r["current_path"]
                    for r in _db.execute(
                        "SELECT current_path FROM files WHERE status='organized'"
                    ).fetchall()
                }
        except Exception:
            pass

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

                if fsize == 0:
                    # Zero-byte: might be a placeholder, skip — scan won't process 0-byte files anyway
                    skipped += 1
                    continue

                if not _is_placeholder(filepath):
                    already_local += 1
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
        """Return (eligible, size_bytes). Eligible = not skipped, not zero-byte, not organised."""
        if should_skip(filepath):
            return False, 0
        if str(filepath) in organized_paths:
            return False, 0
        try:
            fsize = filepath.stat().st_size
        except OSError:
            return False, 0
        if fsize == 0:
            return False, 0
        return True, fsize

    for entry in drive.iterdir():
        if entry.name.startswith(".") or should_skip(entry):
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
            is_xfolder = entry.name.startswith("x")
            for root, subdirs, files in os.walk(entry):
                subdirs[:] = [d for d in subdirs if not d.startswith(".")]
                root_path = Path(root)
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

    for priority in range(1, 7):
        if stopped_at_priority:
            break
        files = sorted(buckets[priority], key=lambda x: str(x[0]))
        for filepath, fsize, placeholder in files:
            if (new_count + updated_count) >= file_limit:
                stopped_at_priority = priority
                break
            if total_bytes + fsize > byte_limit:
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
                    if _is_placeholder(filepath):
                        print(f"  skip {filepath}: still online-only after {DOWNLOAD_POLL_TIMEOUT:.0f}s", file=sys.stderr)
                        skipped += 1
                        continue
                triggered_count += 1

            try:
                _hstart = time.monotonic()
                digest = sha256_of(filepath)
                t_hash += time.monotonic() - _hstart
            except OSError as e:
                print(f"  skip {filepath}: {e}", file=sys.stderr)
                skipped += 1
                continue

            path_str = str(filepath)
            ext = filepath.suffix.lower()
            file_date = extract_photo_date(filepath.name)
            content_peek = None
            if ext not in IMAGE_EXTS:
                _pstart = time.monotonic()
                content_peek = peek_content(filepath)
                t_peek += time.monotonic() - _pstart

            existing = conn.execute(
                "SELECT id, sha256 FROM files WHERE current_path = ?",
                (path_str,)
            ).fetchone()

            if existing:
                if existing["sha256"] != digest:
                    conn.execute(
                        """UPDATE files SET sha256=?, file_size=?, content_peek=?,
                           status='pending', batch_id=? WHERE id=?""",
                        (digest, fsize, content_peek, batch_id, existing["id"])
                    )
                    updated_count += 1
                    total_bytes += fsize
                continue

            dup = conn.execute(
                "SELECT id FROM files WHERE sha256 = ? AND status != 'duplicate' LIMIT 1",
                (digest,)
            ).fetchone()

            if dup:
                conn.execute(
                    """INSERT INTO files
                       (original_path, current_path, filename, extension, file_size,
                        sha256, file_date, content_peek, status, batch_id)
                       VALUES (?,?,?,?,?,?,?,?,'duplicate',?)""",
                    (path_str, path_str, filepath.name, ext, fsize,
                     digest, file_date, content_peek, batch_id)
                )
                duplicate_count += 1
            else:
                conn.execute(
                    """INSERT INTO files
                       (original_path, current_path, filename, extension, file_size,
                        sha256, file_date, content_peek, status, batch_id)
                       VALUES (?,?,?,?,?,?,?,?,'pending',?)""",
                    (path_str, path_str, filepath.name, ext, fsize,
                     digest, file_date, content_peek, batch_id)
                )
                new_count += 1
            total_bytes += fsize

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

def cmd_propose(args):
    limit = int(args.limit)
    conn = get_db()
    rows = conn.execute(
        """SELECT id, current_path, filename, extension, file_size, file_date, content_peek
           FROM files WHERE status = 'pending' LIMIT ?""",
        (limit,)
    ).fetchall()
    conn.close()

    if not rows:
        print("No pending files. Run 'scan' first or all files are already classified.")
        return

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
        }
        result.append(entry)

    # Write project-metadata sidecar so Claude can look up filename_tag and
    # production_period for each known project when classifying.
    metadata = _enumerate_project_metadata(_EFFECTIVE_ROOT)
    sidecar = Path.home() / ".claude" / "drive-organizer" / "project_metadata.json"
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    sidecar.write_text(json.dumps(metadata, indent=2))
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

    for entry in approved:
        file_id     = entry["id"]
        src         = Path(entry["current_path"])
        action      = entry.get("action", "approved")
        category    = entry.get("para_category", "_Inbox")
        subfolder   = _normalize_grouping(entry.get("para_subfolder", ""))
        new_filename = entry.get("new_filename")
        vision_desc  = entry.get("vision_desc")
        file_date    = entry.get("file_date")

        if not src.exists():
            print(f"  MISSING: {src}", file=sys.stderr)
            errors += 1
            continue

        if action == "delete":
            dest_dir = drive / "Archive" / "_To Delete"
        else:
            dest_dir = drive / subfolder
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_name = new_filename if new_filename else src.name
        dest      = dest_dir / dest_name

        if dest.exists() and dest != src:
            stem, suffix = dest.stem, dest.suffix
            counter = 2
            while dest.exists():
                dest = dest_dir / f"{stem}_{counter}{suffix}"
                counter += 1

        try:
            shutil.move(str(src), str(dest))
        except OSError as e:
            print(f"  ERROR moving {src}: {e}", file=sys.stderr)
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
        s = 0.0
        if r.get("status") == "organized":
            s += 100
        if "/_Inbox/" not in p and "/Archive/" not in p:
            s += 10
        s += p.count("/")          # deeper path = more specific destination
        return s
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
        group = conn.execute(
            "SELECT id, current_path, status FROM files WHERE sha256=? AND sha256 IS NOT NULL",
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
        keeper_dir = keeper_path.parent
        keeper_dir.mkdir(parents=True, exist_ok=True)
        # next _dupN beside the keeper, using the keeper's stem so they sort adjacent
        n = 1
        while (keeper_dir / f"{keeper_path.stem}_dup{n}{src.suffix}").exists():
            n += 1
        dest = keeper_dir / f"{keeper_path.stem}_dup{n}{src.suffix}"
        shutil.move(str(src), str(dest))
        conn.execute(
            "UPDATE files SET current_path=?, status='duplicate', processed_at=? WHERE id=?",
            (str(dest), datetime.now().isoformat(), target)
        )
        conn.commit()
        conn.close()
        print(f"Co-located dup id {target} → {dest}  (beside keeper id {keeper['id']}: {keeper_path})")
        export_csv()
        return

    rows = conn.execute(
        """SELECT sha256,
                  GROUP_CONCAT(id)                      AS ids,
                  GROUP_CONCAT(current_path, '|||')     AS paths,
                  GROUP_CONCAT(file_size)               AS sizes,
                  GROUP_CONCAT(COALESCE(file_date,'?')) AS dates,
                  GROUP_CONCAT(COALESCE(status,'?'))    AS statuses
           FROM files
           WHERE status IN ('organized','pending','duplicate')
           GROUP BY sha256
           HAVING COUNT(*) > 1"""
    ).fetchall()
    conn.close()

    if not rows:
        print("No exact duplicates found.")
        return

    groups = []
    for row in rows:
        ids      = row["ids"].split(",")
        paths    = row["paths"].split("|||")
        sizes    = row["sizes"].split(",")
        dates    = row["dates"].split(",")
        statuses = row["statuses"].split(",")
        files = [
            {"id": int(i), "path": p, "size": int(s), "date": d, "status": st}
            for i, p, s, d, st in zip(ids, paths, sizes, dates, statuses)
        ]
        keeper = _pick_keeper(files)
        groups.append({
            "sha256": row["sha256"][:16] + "...",
            "keeper_id": keeper["id"],          # the copy to keep in place; co-locate the rest
            "files": files,
        })

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
        base  = re.sub(r"^\d+-", "", base)             # $-anchored variant-token strip below can
        base  = re.sub(                                # never match (the extension is in the way)
            r"[\s_-]*(v\d+|final|copy|highlighted?|annotated?|marked?)$",
            "", base, flags=re.IGNORECASE
        )
        base = base.lower().strip()
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
        sizes = [m["file_size"] for m in members if m["file_size"]]
        if not sizes:
            continue
        min_s, max_s = min(sizes), max(sizes)
        if min_s == 0 or (max_s / min_s) > 2.0:
            continue
        group_id = f"grp_{abs(hash(key)) % 100000:05d}"
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
            new = getattr(page_dst, quad_types[t])(quads=src.vertices)
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

    doc_canonical = fitz.open(str(canonical_path))
    merged_count  = 0

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

        src_annots = copied = 0
        for page_num in range(min(len(doc_canonical), len(doc_other))):
            page_src = doc_other[page_num]
            page_dst = doc_canonical[page_num]
            for annot in (page_src.annots() or []):
                src_annots += 1
                if _copy_pdf_annot(annot, page_dst):
                    copied += 1

        doc_other.close()

        # Safety: never archive a variant that carried annotations none of which
        # transferred — archiving an un-merged original would silently lose them.
        if src_annots > 0 and copied == 0:
            print(f"  WARNING: {other_path.name} has {src_annots} annotation(s) but none could be "
                  f"copied — left in place (not archived) to avoid data loss.", file=sys.stderr)
            continue

        archive_dir = drive / "Archive" / "_Merged-Originals"
        archive_dir.mkdir(parents=True, exist_ok=True)
        dest = archive_dir / other_path.name
        if dest.exists():
            dest = archive_dir / f"{other_path.stem}_dup{other_path.suffix}"

        shutil.move(str(other_path), str(dest))
        conn.execute(
            "UPDATE files SET current_path=?, status='archived', processed_at=? WHERE id=?",
            (str(dest), datetime.now().isoformat(), other_row["id"])
        )
        merged_count += 1

    doc_canonical.save(str(canonical_path), incremental=True, encryption=0)
    doc_canonical.close()

    conn.execute(
        "UPDATE files SET processed_at=? WHERE id=?",
        (datetime.now().isoformat(), canonical_id)
    )
    conn.commit()
    conn.close()

    print(f"Merge complete: {merged_count} files merged into {canonical_path.name}.")
    print(f"Originals archived to Archive/_Merged-Originals/")
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
const PROPOSALS = __PROPOSALS_JSON__;
const VOCAB = __VOCAB_JSON__;
const APPROVED_PATH = "__APPROVED_PATH__";
const PAGE_SIZE = 25;

// per-row state: { status, seg1, seg2, seg3, newName }
// status values: 'unset' | 'approved' | 'rejected' | 'inbox' | 'flagged'
// rejected = I got it wrong, reclassify using context
// inbox    = user needs to open it manually (EPS etc), confirmed _Inbox
const rowState = {};

PROPOSALS.forEach(p => {
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
  return [st.seg1, st.seg2, st.seg3].filter(Boolean).join('/');
}

function inferCategory(path) {
  if (!path || path.startsWith('_')) return path || '_Inbox';
  if (path === 'Personal' || path.startsWith('Personal/')) return 'Areas';
  const refs = ['Creative References', 'Study Notes', 'Articles', 'Templates'];
  if (refs.some(r => path === r || path.startsWith(r + '/'))) return 'Resources';
  const old = ['Old Projects', 'Old Coursework'];
  if (old.some(r => path === r || path.startsWith(r + '/'))) return 'Archive';
  return 'Projects';
}

// ---------- Rendering ----------

function buildRow(p, globalIdx) {
  const st = rowState[p.id];
  const trClass = st.status === 'unset' ? '' : st.status;
  return `
<tr id="row-${p.id}" class="${trClass}">
  <td class="num">${globalIdx + 1}</td>
  <td class="from" title="${escHtml(p.current_path)}">${escHtml(p.current_path.split('/').slice(-2,-1)[0] || '')}</td>
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

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c =>
    ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

function buildGroupHeader(path, count, firstIdx, isInbox) {
  const cls = 'group-header' + (isInbox ? ' inbox' : '');
  const safePath = escapeHtml(path || '(no destination)');
  return `
<tr class="${cls}">
  <td colspan="7">
    → <span class="group-path">${safePath}</span>
    <span class="group-count">(${count} file${count === 1 ? '' : 's'})</span>
    <button class="approve-group-btn" onclick="approveGroup(${firstIdx}, ${count})">Approve group</button>
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
    const groupCount = j - i;
    const isInbox = !groupPath || groupPath.startsWith('_Inbox');
    body += buildGroupHeader(groupPath, groupCount, start + i, groupCount);
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

function approveGroup(startIdx, count) {
  for (let k = 0; k < count; k++) {
    const p = PROPOSALS[startIdx + k];
    if (p) setStatus(p.id, 'approved');
  }
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
    const pageReviewed = slice.filter(p => ['approved','rejected','inbox','delete'].includes(rowState[p.id].status)).length;
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
  return s.trim().toLowerCase().replace(/\s+/g, '_').replace(/[^a-z0-9_]/g, '');
}

function onSeg(id) {
  const st = rowState[id];
  const oldSeg1 = st.seg1 || '';
  st.seg1 = (document.getElementById(`s1-${id}`) || {value: ''}).value.trim();
  st.seg2 = (document.getElementById(`s2-${id}`) || {value: ''}).value.trim();
  st.seg3 = (document.getElementById(`s3-${id}`) || {value: ''}).value.trim();
  addToDatalist(1, st.seg1);
  addToDatalist(2, st.seg2);
  addToDatalist(3, st.seg3);
}
function onNameChange(id, val) { rowState[id].newName = val; }

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
    }
  });

  fetch('/submit', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ approved: output, flagged: flaggedIds }),
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
            approved_path_str = str(APPROVED_JSON_PATH).replace("\\", "\\\\")

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
            html = html.replace("__PROPOSALS_JSON__", json.dumps(viewer_proposals))
            html = html.replace("__VOCAB_JSON__", json.dumps(self.__class__._vocab))
            html = html.replace("__APPROVED_PATH__", approved_path_str)
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
            length = int(self.headers.get("Content-Length", 0))
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
            else:
                approved = payload.get("approved", [])
                flagged_ids = payload.get("flagged", [])

            APPROVED_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(APPROVED_JSON_PATH, "w") as f:
                json.dump(approved, f, indent=2)

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
                except Exception as e:
                    print(f"Warning: could not mark flagged in DB: {e}", flush=True)

            resp = json.dumps({"ok": True, "path": str(APPROVED_JSON_PATH)}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp)))
            self.end_headers()
            self.wfile.write(resp)

            print(f"\nApproved proposals written to: {APPROVED_JSON_PATH}", flush=True)
            if flagged_ids:
                print(f"{len(flagged_ids)} files marked flagged in registry.", flush=True)
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

    server = HTTPServer(("127.0.0.1", port), _SilentHandler)
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
        server.handle_request()


# ---------------------------------------------------------------------------
# cleanup
# ---------------------------------------------------------------------------

def cmd_cleanup(args):
    drive = Path(args.path).expanduser() if args.path else _EFFECTIVE_ROOT
    if not drive.exists():
        sys.exit(f"Error: root path not found: {drive}")

    removed = 0

    # Walk bottom-up so children are processed before parents
    for root, dirs, files in os.walk(drive, topdown=False):
        root_path = Path(root)

        # Skip the root itself
        if root_path == drive:
            continue

        # Skip direct children of root that are PARA roots
        if root_path.parent == drive and root_path.name in PARA_ROOTS:
            continue

        # Skip staging subdirs inside Archive — they hold active data and must survive empty batches
        _ARCHIVE_STAGING = {"_To Delete", "_Duplicates", "_Merged-Originals"}
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
    print("Flagged files are excluded from propose. To reclassify: classify directly and run execute.")
    print("To manually clear a flag: UPDATE files SET status='pending' WHERE id=<N>;")


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------

GROUPINGS = {"ENTERTAINMENT", "PERSONAL", "WORK", "EDUCATION", "RESOURCES"}


def _normalize_grouping(para: str) -> str:
    """Force a destination's top-level grouping segment to its canonical ALL-CAPS
    form, so a viewer edit like 'Personal/PERSONAL Financial' lands in
    'PERSONAL/PERSONAL Financial'. Only the first path segment is touched; deeper
    names keep their case. (reconcile remains the safety net for legacy miscased
    folders already on disk.)"""
    if not para:
        return para
    parts = para.split("/")
    if parts[0].upper() in GROUPINGS:
        parts[0] = parts[0].upper()
    return "/".join(parts)
_RECONCILE_KNOWN_ROOTS = GROUPINGS | {"_Inbox", "Archive", "logseq-journals", ".organizer"}


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
    if len(parts) >= 2 and parts[0] in GROUPINGS and "_Inbox" not in parts:
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
        try:
            new_para = str(Path(actual).resolve().parent.relative_to(root.resolve()))
        except Exception:
            new_para = entry.get("para_subfolder", "")
        conn.execute("UPDATE files SET current_path=?, para_subfolder=?, processed_at=? WHERE id=?",
                     (actual, new_para, now, _id))
        conn.commit(); conn.close(); export_csv()
        print(f"Accepted id {_id}'s location: {actual}  (registry updated; file not moved)")
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
                 "para_subfolder": para, "suggestion": _relocate_suggestion(cp, root)})

    # Resolve rows whose recorded file is missing: relocated outside the tool (the common
    # "structure got ruined" case — a file dragged elsewhere in Finder), or genuinely gone?
    if missing_rows:
        index = {}
        for p in root.rglob("*"):
            if p.is_file():
                index.setdefault(p.name, []).append(p)
        for row in missing_rows:
            cp = row["current_path"]
            base = Path(cp).name
            cands = [p for p in index.get(base, [])
                     if os.path.normpath(str(p)) != os.path.normpath(cp)]
            if row["file_size"]:                       # disambiguate same-named files by size
                sized = [p for p in cands if p.stat().st_size == row["file_size"]]
                if sized:
                    cands = sized
            if cands:
                report["misplaced_files"].append(
                    {"id": row["id"], "filename": base, "issue": "relocated_outside_tool",
                     "fix_from": str(cands[0]), "fix_to": cp,
                     "suggestion": _relocate_suggestion(str(cands[0]), root)})
            else:
                report["bad_registry_rows"].append(
                    {"id": row["id"], "issue": "missing_on_disk", "current_path": cp,
                     "filename": row["filename"]})

    # Mangled folder tree — root-level folders that break the five-grouping invariant
    for child in sorted(p for p in root.iterdir() if p.is_dir()):
        name = child.name
        if name in _RECONCILE_KNOWN_ROOTS or name.startswith("x"):
            continue
        if _is_external(child):
            continue
        if name.upper() in GROUPINGS and name not in GROUPINGS:
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
    yaml_path.write_text(yaml_text)

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
    report_path.write_text(json.dumps(report, indent=2))
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
        print("Deferred folders are skipped by scan. To process one later:")
        print("  1. Rename it (remove the 'x' prefix)")
        print("  2. Create a .tidy-rules.json inside it")
        print("  3. Re-run scan")


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
    p_propose.add_argument("--limit", default="250")

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
    p_viewer.add_argument("--port", default="5002", help="Local port (default 5002)")

    p_cleanup = sub.add_parser("cleanup")
    p_cleanup.add_argument("path", nargs="?", help="root path")

    sub.add_parser("csv-export", help="Refresh <root>/.organizer/registry.csv from the SQLite registry")
    sub.add_parser("templates", help="Print merged templates (shipped skeleton + per-user override) as JSON")

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
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
