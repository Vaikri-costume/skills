#!/usr/bin/env python3
"""Canonical YAML-frontmatter block + scalar-field extraction for CCVW skills.

The single home for the `---\\n … \\n---\\n` frontmatter scan, imported by every
publisher script that reads frontmatter (readiness_report.py, package_skill.py) so
they cannot drift. Tolerates a leading BOM, CRLF/CR line endings, and a closing
`---` at EOF with no trailing newline — edge cases that previously only one copy
handled, so a BOM/CRLF SKILL.md parsed differently depending on which script read it.

Not a full YAML parser: `field()` reads flat scalar values (name, tier,
compatibility, intended-audience) — the only frontmatter shape these gates need.
"""
from __future__ import annotations

import re


def block(text: str) -> str:
    """Return the raw frontmatter block (the text between the opening and closing
    `---`), or "" if there is no well-formed frontmatter."""
    text = text.lstrip("﻿")                              # leading BOM
    text = text.replace("\r\n", "\n").replace("\r", "\n")     # CRLF / CR → LF
    if not text.startswith("---\n"):
        return ""
    end = text.find("\n---\n", 4)
    if end >= 0:
        return text[4:end]
    # Accept a closing `---` at EOF with no trailing newline.
    trail = text.find("\n---", 4)
    if trail >= 0 and not text[trail + 4:].strip():
        return text[4:trail]
    return ""


def field(fm: str, key: str) -> str | None:
    """Return the scalar value of `key` in a frontmatter block, or None. Strips one
    matching pair of surrounding quotes. `fm` is the string returned by block()."""
    for line in fm.split("\n"):
        m = re.match(rf"^\s*{re.escape(key)}\s*:\s*(.+)$", line)
        if m:
            return m.group(1).strip().strip('"').strip("'") or None
    return None
