#!/usr/bin/env python3
"""Shared hashing helper for skill-publisher scripts.

Single home for the streaming SHA-256 file digest, imported by package_skill.py
(SHA256SUMS + archive digest) and verify_ship.py (artifact re-hash) so the two
cannot drift on chunk size / encoding / error handling. Same shared-helper pattern
as frontmatter_util.py.
"""
from __future__ import annotations

import hashlib
from pathlib import Path


def sha256_file(path: Path) -> str:
    """SHA-256 hex digest of a file, streamed (constant memory on large archives)."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()
