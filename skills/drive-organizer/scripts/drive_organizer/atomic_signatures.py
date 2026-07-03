"""drive_organizer.atomic_signatures — split from paths_config.py (pure structural move, no behavior change).

Atomic-unit signature loading (node_modules/.git/venv-style "never split this" directory
markers): shipped references/atomic-signatures.json merged with a per-drive user extension."""
from __future__ import annotations
import json
import os
import sys
from pathlib import Path

from drive_organizer.paths_config import _read_user_config, _skill_references_dir


# Hardcoded fallback — used ONLY when the shipped references/atomic-signatures.json is
# missing/unparseable, so a broken install never loses atomic-unit protection entirely.
# This matches the tool's ORIGINAL hardcoded behavior exactly (i.e. WITHOUT the two
# signatures — OSCAR_Data, Backups.backupdb — added later via the shipped JSON file).
_ATOMIC_DIR_NAMES_FALLBACK = {"node_modules", ".git", "venv", ".venv", "env", "__pycache__",
                              ".tox", "site-packages", "Pods", "vendor"}
_ATOMIC_SUFFIXES_FALLBACK = (".app", ".framework", ".bundle", ".xcodeproj", ".photoslibrary",
                             ".imovielibrary", ".tvlibrary", ".aplibrary")
# Must remain a tuple (not a set): str.endswith() requires a tuple for multi-suffix matching.
_ATOMIC_MARKER_FILES_FALLBACK = [
    {"probe": "pyvenv.cfg", "kind": "file", "marker": "venv"},
    {"probe": "zotero.sqlite", "kind": "file", "marker": "zotero"},
    {"probe": ".git", "kind": "dir", "marker": "git-repo"},
]
_ATOMIC_MARKER_PAIRS_FALLBACK = [
    {"probes": ["Assets", "ProjectSettings"], "kind": "dir", "marker": "unity"},
]


_ATOMIC_SIGNATURES_CACHE = None


def _reset_cache():
    """Clear this module's process-level cache. Called by paths_config._reset_caches()."""
    global _ATOMIC_SIGNATURES_CACHE
    _ATOMIC_SIGNATURES_CACHE = None


def _load_atomic_signatures() -> dict:
    """Load the atomic-unit signature source-of-truth from the skill's references/
    folder (references/atomic-signatures.json) — same shape/caching/degrade pattern
    as _load_templates(). Returns a dict with dir_names (list), suffixes (list),
    marker_files (list of {probe,kind,marker}), marker_pairs (list of
    {probes,kind,marker}). Degrades to the hardcoded *_FALLBACK constants above
    (today's exact original behavior, i.e. without OSCAR_Data/Backups.backupdb) if the
    shipped file is missing/unparseable — a WARNING is printed, never a crash.

    Caching: mtime-keyed on the shipped file only (unlike _load_templates there is no
    per-drive override merged in HERE — user extension is a separate, narrower surface;
    see _effective_atomic_signatures)."""
    global _ATOMIC_SIGNATURES_CACHE
    sig_path = _skill_references_dir() / "atomic-signatures.json"
    try:
        mtime = os.path.getmtime(sig_path) if sig_path.exists() else 0
    except OSError:
        mtime = 0
    if _ATOMIC_SIGNATURES_CACHE is not None and _ATOMIC_SIGNATURES_CACHE[0] == mtime:
        return _ATOMIC_SIGNATURES_CACHE[1]
    fallback = {
        "dir_names": sorted(_ATOMIC_DIR_NAMES_FALLBACK),
        "suffixes": list(_ATOMIC_SUFFIXES_FALLBACK),
        "marker_files": list(_ATOMIC_MARKER_FILES_FALLBACK),
        "marker_pairs": list(_ATOMIC_MARKER_PAIRS_FALLBACK),
    }
    data = fallback
    if sig_path.exists():
        try:
            raw = json.loads(sig_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                data = {
                    "dir_names": [x for x in raw.get("dir_names", []) if isinstance(x, str) and x],
                    "suffixes": [x for x in raw.get("suffixes", []) if isinstance(x, str) and x],
                    "marker_files": [m for m in raw.get("marker_files", [])
                                     if isinstance(m, dict) and m.get("probe") and m.get("kind") and m.get("marker")],
                    "marker_pairs": [m for m in raw.get("marker_pairs", [])
                                     if isinstance(m, dict) and isinstance(m.get("probes"), list)
                                     and len(m.get("probes")) >= 1 and m.get("kind") and m.get("marker")],
                }
            else:
                print(f"WARNING: shipped atomic signatures {sig_path} is not a JSON object; "
                      f"using hardcoded fallback signatures.", file=sys.stderr)
        except Exception as e:
            print(f"WARNING: could not parse shipped atomic signatures {sig_path} "
                  f"({e}); using hardcoded fallback signatures.", file=sys.stderr)
    _ATOMIC_SIGNATURES_CACHE = (mtime, data)
    return data


def _effective_atomic_signatures(root: "Path | None" = None) -> dict:
    """Shipped atomic-unit signatures (_load_atomic_signatures) merged with the
    per-drive user extension at <root>/.organizer/config.json's `atomic_signatures_extra`
    key (dir_names/suffixes ONLY — marker_files/marker_pairs stay shipped-file-only,
    since letting arbitrary user JSON define filesystem probe behavior is a different
    risk tier than a plain string list). Returns the same 4-key shape as
    _load_atomic_signatures; dir_names/suffixes are the union (shipped ∪ user extra),
    deduped, order not significant to callers (both are membership tests)."""
    base = _load_atomic_signatures()
    cfg = _read_user_config(root)
    extra = cfg.get("atomic_signatures_extra")
    extra_dirs, extra_suffixes = [], []
    if isinstance(extra, dict):
        raw_dirs = extra.get("dir_names")
        if isinstance(raw_dirs, list):
            extra_dirs = [x for x in raw_dirs if isinstance(x, str) and x.strip()]
        raw_suffixes = extra.get("suffixes")
        if isinstance(raw_suffixes, list):
            extra_suffixes = [x for x in raw_suffixes if isinstance(x, str) and x.strip()]
    return {
        "dir_names": sorted(set(base["dir_names"]) | set(extra_dirs)),
        "suffixes": sorted(set(base["suffixes"]) | set(extra_suffixes)),
        "marker_files": base["marker_files"],
        "marker_pairs": base["marker_pairs"],
    }
