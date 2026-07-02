"""drive_organizer.content_peek — split from the original organizer.py (pure structural move, no behavior change)."""
from __future__ import annotations
import hashlib
import json
import os
import re
import sqlite3
import sys
import threading
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

from drive_organizer import paths_config
from drive_organizer.paths_config import (
    IMAGE_EXTS,
    SKIP_EXTS,
    SKIP_NAMES,
    _FITZ_LOCK,
    _UF_DATALESS,
    _WIN_OFFLINE,
    _WIN_RECALL_ON_DATA_ACCESS,
    _XML_PEEK_CAP,
    _effective_peek_chars,
    _finalize_runtime_paths,
)


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
    if not paths_config._PATHS_FINALIZED:
        _finalize_runtime_paths()  # lazy: honour saved config even if main() hasn't run
    paths_config.REGISTRY_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(paths_config.REGISTRY_DB))
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
    Extract up to the effective peek-chars cap (config.json's `content_peek_chars`,
    else PEEK_CHARS=300 — see paths_config._effective_peek_chars) of meaningful text
    from a file. Returns None for images (handled by vision), audio/video, and
    unreadable files. The snippet is used by Claude when filename heuristics are weak.
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
        "artist=Example Artist | album=Example Album | title=Example Song | date=2001 | tracknumber=2"
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
            peek_chars = _effective_peek_chars()
            text = ""
            for i in range(min(3, doc.page_count)):
                text += doc[i].get_text()
                if len(text) >= peek_chars * 2:
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
        raw = f.read(_effective_peek_chars() * 3)
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
    return text[:_effective_peek_chars()] if text else None


# ---------------------------------------------------------------------------
# download-batch — trigger OneDrive Files On Demand downloads up to a size cap
# ---------------------------------------------------------------------------

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
            for n in sorted(names)
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

    # Linux / other: no reliable provider signal — treat as local (False). A size-vs-blocks
    # heuristic (st_blocks==0) was considered and rejected: it is the exact signal the macOS
    # branch above documents as unsafe — sparse, reflinked, and transparently-compressed
    # (btrfs/ZFS) files legitimately report zero blocks while fully local. The false positive
    # is NOT benign: the scan poll loop re-checks _is_placeholder, so a local zero-block file
    # never clears, stalls the full download timeout, and is then skipped (dropped from the
    # batch). The dominant Linux OneDrive client (abraunegg/onedrive) full-syncs, so always-
    # local is correct for it; FUSE placeholder clients (onedriver) can be added with a test box.
    return False


def _cloud_platform_note() -> str:
    """One-line best-effort/unverified notice for non-macOS platforms — cloud-placeholder
    detection is verified only on macOS (the >25GB gate runs there). Empty on macOS."""
    if sys.platform == "darwin":
        return ""
    plat = "Windows" if sys.platform == "win32" else "Linux/other"
    return (f"Note: cloud-placeholder detection on {plat} is best-effort and unverified. "
            f"If files aren't materialising, pass --root <your synced folder> and make sure "
            f"your sync client downloads on read.")

