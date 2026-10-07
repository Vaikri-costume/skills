#!/usr/bin/env python3
"""inscope.py — Single canonical source of truth for in-scope skill file enumeration.

Used by code_review_run.py (to build [SKILL_FILES]) and coverage_check.py (to
verify Read coverage against exactly the same file set).

Skip rules:
  - dotfiles and files inside dotdirectories
  - __pycache__ directories
  - _archive directories (a target may keep removed-but-restorable material there)
  - .pyc / .pyo suffixes
  - binary suffixes in _BINARY_SUFFIXES (images, archives, fonts, ...; matched case-insensitively)
  - files whose name contains .bak
  - files inside any path segment ending with -workspace
  - files inside evals/iteration-* directories
  - README.md, HISTORY.md, LICENSE, LICENSE.* names

Pure stdlib. Python 3.9+.
"""
from __future__ import annotations

from pathlib import Path

_SKIP_NAMES: frozenset[str] = frozenset({"README.md", "HISTORY.md", "LICENSE"})
_SKIP_SUFFIXES: frozenset[str] = frozenset({".pyc", ".pyo"})
# Binary / non-text assets are NOT line-reviewable — a cold agent cannot Read a
# PNG, and coverage can never close on one. A binary file left in scope is
# reported by line count like any text file (e.g. a PNG can show as a
# thousand-plus-"line" file) and becomes a permanent, unclosable coverage gap
# for every agent. Exclude them from scope entirely.
_BINARY_SUFFIXES: frozenset[str] = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".tif", ".webp", ".heic",
    ".heif", ".ico", ".svg", ".pdf", ".zip", ".gz", ".tar", ".tgz", ".woff",
    ".woff2", ".ttf", ".otf", ".eot", ".mp3", ".mp4", ".mov", ".wav", ".so",
    ".dylib", ".bin", ".db", ".sqlite", ".sqlite3", ".pickle", ".pkl", ".npy",
})


def inscope_files(target_dir: Path) -> list[Path]:
    """Return a sorted list of in-scope skill files as resolved absolute Paths.

    Args:
        target_dir: Root of the skill directory to enumerate.

    Returns:
        Sorted list of absolute, resolved Path objects for every in-scope file.

    Example:
        >>> from pathlib import Path
        >>> files = inscope_files(Path("/path/to/my-skill"))
        >>> for f in files:
        ...     print(f)
    """
    out: list[Path] = []
    for p in sorted(target_dir.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(target_dir)
        parts = rel.parts
        name = p.name

        if name.startswith("."):
            continue
        if any(seg.startswith(".") for seg in parts):
            continue
        if "__pycache__" in parts:
            continue
        if "_archive" in parts:  # a target's removed-but-restorable material, not live content
            continue
        if p.suffix in _SKIP_SUFFIXES:
            continue
        if p.suffix.lower() in _BINARY_SUFFIXES:
            continue
        if ".bak" in name:
            continue
        if any(seg.endswith("-workspace") for seg in parts):
            continue
        if any(
            seg.startswith("iteration-") and i > 0 and parts[i - 1] == "evals"
            for i, seg in enumerate(parts)
        ):
            continue
        if name in _SKIP_NAMES or name.startswith("LICENSE."):
            continue

        out.append(p.resolve())
    return out
