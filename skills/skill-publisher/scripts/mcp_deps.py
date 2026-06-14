#!/usr/bin/env python3
"""Check that a skill declares the MCP server(s) it depends on (publisher Step 4, the MCP-dependency check / 5th tier check).

A Category-2/3 skill that calls `mcp__<server>__<tool>` depends on that MCP server
being connected before it works. If the skill never tells the installer "connect
the <server> MCP," it ships broken-on-arrival for everyone but the author — the
guide's "users connect your MCP but don't know what to do / blame your connector"
failure. This check extracts the servers the skill actually calls and confirms each
is declared where the installer will see it.

Replaces the inline grep/sed one-liner (which had a `[a-z0-9_]+` vs `[a-z0-9]+`
mismatch that mishandled server names containing underscores).

A server `<s>` is "declared" if EITHER:
  - frontmatter `metadata.mcp-server` mentions it (the machine-readable signal), OR
  - the README's install/what-it-does prose mentions it (the human signal).
Both-absent for a called server = an undeclared dependency = a TIER finding.

Pure-stdlib.

Usage:  mcp_deps.py <skill-path>   (expects <skill>/SKILL.md, optional <skill>/README.md)
Output JSON: {"skill":"<path>", "servers_called":[...], "declared":{srv:bool}, "undeclared":[...], "note":"...",
              "metadata_mcp_server":"<value|null>", "readme_present":bool}
Exit: 0 = no MCP calls, or every called server declared; 1 = undeclared server(s); 2 = SKILL.md not found at the given path, or argparse usage error — check the argument and re-run.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# mcp__<server>__<tool> — server and tool segments are [a-z0-9_]+ (underscores allowed).
MCP_CALL_RE = re.compile(r"\bmcp__([a-z0-9_]+)__[a-z0-9_]+\b", re.IGNORECASE)


def frontmatter_block(text: str) -> str:
    if not text.startswith("---\n"):
        return ""
    end = text.find("\n---\n", 4)
    return text[4:end] if end >= 0 else ""


def metadata_mcp_server(fm: str) -> str | None:
    # Matches any `mcp-server:` line at any indentation level — covers both a flat
    # top-level `mcp-server: value` and the conventional nested form
    # `metadata:\n  mcp-server: value`. Does NOT validate nesting depth; any
    # `mcp-server:` key anywhere in the frontmatter is treated as the declaration.
    for line in fm.split("\n"):
        m = re.match(r"^\s*mcp-server\s*:\s*(.*)$", line)
        if m:
            return m.group(1).strip().strip('"').strip("'") or None
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="MCP-dependency declaration check (publisher)")
    ap.add_argument("skill_path")
    args = ap.parse_args()
    root = Path(args.skill_path).expanduser()
    skill_md = root if root.name == "SKILL.md" else root / "SKILL.md"
    if not skill_md.is_file():
        print(f"ERROR: SKILL.md not found at {skill_md}", file=sys.stderr)
        return 2
    skill_root = skill_md.parent

    text = skill_md.read_text()
    fm = frontmatter_block(text)

    # Servers called anywhere in SKILL.md (frontmatter included — a documented
    # allowed-tools or mcp-server entry with an mcp__*__* pattern is counted;
    # this is intentional since both frontmatter and body are part of the calling contract).
    called = sorted(set(m.group(1).lower() for m in MCP_CALL_RE.finditer(text)))

    mcp_server_val = metadata_mcp_server(fm)
    readme = skill_root / "README.md"
    readme_text = readme.read_text().lower() if readme.is_file() else ""

    declared = {}
    for srv in called:
        in_meta = bool(mcp_server_val and srv in mcp_server_val.lower())
        # Word-boundary match, not a bare substring: a short server name like
        # `db`/`gh`/`fs` would otherwise be falsely "declared" by an unrelated
        # word in the README that happens to contain it.
        in_readme = bool(re.search(rf"\b{re.escape(srv)}\b", readme_text))
        declared[srv] = in_meta or in_readme
    undeclared = [s for s in called if not declared[s]]

    result = {
        "skill": str(skill_root),
        "servers_called": called,
        "metadata_mcp_server": mcp_server_val,
        "readme_present": readme.is_file(),
        "declared": declared,
        "undeclared": undeclared,
        "note": ("no mcp__*__* calls — MCP-dependency check N/A" if not called else
                 ("all called servers declared" if not undeclared else
                  "undeclared MCP server(s) — add to README install section + metadata.mcp-server (TIER finding)")),
    }
    print(json.dumps(result, indent=2))
    return 1 if undeclared else 0


if __name__ == "__main__":
    sys.exit(main())
