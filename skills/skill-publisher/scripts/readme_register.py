#!/usr/bin/env python3
"""Keep the upstream repo-root README's skill listing current when a skill ships.

Pure-stdlib. Imported by github_pr.py (so the row lands in the SAME commit as the
skill copy and the dry-run shows it); also runnable standalone to inspect a clone:

    python3 readme_register.py <clone-dir> --repo-path skills/<name>

Why: a skill folder that the repo's front-page README never mentions is invisible to
anyone browsing the repo — the same "shipped but undiscoverable" failure that
marketplace_register.py prevents for `claude plugins install`.

A skill is "listed" when the repo-root README.md links its folder anywhere
(`(skills/<name>/)` with or without a leading "./" or trailing "/").

States returned by plan():
  absent        no README.md at the repo root — nothing to do
  listed        already linked (no change; idempotent on re-ships)
  needs_row     README exists, skill not linked — the orchestrator must pick a section
                (an existing heading) and supply a description, or opt out
"""

import argparse
import json
import re
import sys
from pathlib import Path


def _norm(p: str) -> str:
    p = p.strip().replace("\\", "/")
    if p.startswith("./"):
        p = p[2:]
    return p.strip("/")


def _headings(lines):
    out = []
    for i, l in enumerate(lines):
        m = re.match(r"^(#{1,6})\s+(.*?)\s*#*\s*$", l)
        if m:
            out.append((i, len(m.group(1)), m.group(2)))
    return out


def _section_bounds(lines, heading):
    """(start_line_after_heading, end_line_exclusive) of the section named `heading`."""
    hs = _headings(lines)
    for k, (i, lvl, text) in enumerate(hs):
        if text.strip().lower() == heading.strip().lower():
            end = len(lines)
            for (j, lvl2, _t) in hs[k + 1:]:
                if lvl2 <= lvl:
                    end = j
                    break
            return i + 1, end
    return None


def _table_in(lines, start, end):
    """First pipe table in lines[start:end]: (first, last_inclusive, ncols) or None."""
    i = start
    while i < end:
        if lines[i].lstrip().startswith("|"):
            j = i
            while j + 1 < end and lines[j + 1].lstrip().startswith("|"):
                j += 1
            ncols = len([c for c in lines[i].strip().strip("|").split("|")])
            return i, j, ncols
        i += 1
    return None


def plan(clone_dir: Path, repo_path: str) -> dict:
    path = clone_dir / "README.md"
    if not path.is_file():
        return {"state": "absent", "detail": "no README.md at the repo root"}
    text = path.read_text(encoding="utf-8")
    want = _norm(repo_path)
    if re.search(r"\]\(\s*(?:\./)?" + re.escape(want) + r"/?\s*\)", text):
        return {"state": "listed", "entry": want}
    lines = text.split("\n")
    sections = []
    for (i, lvl, title) in _headings(lines):
        b = _section_bounds(lines, title)
        tbl = _table_in(lines, *b) if b else None
        sections.append({"heading": title, "table_columns": tbl[2] if tbl else None})
    return {"state": "needs_row", "entry": want, "sections": sections,
            "detail": "skill is not linked in the repo README; choose a section (and give a description) or opt out"}


def apply(clone_dir: Path, repo_path: str, section: str, description: str,
          phase: str | None = None) -> dict:
    """Append a row for the skill under `section`. Raises ValueError on a bad choice."""
    path = clone_dir / "README.md"
    lines = path.read_text(encoding="utf-8").split("\n")
    b = _section_bounds(lines, section)
    if b is None:
        raise ValueError(f"no heading named {section!r} in the repo README "
                         f"(have: {[t for (_i, _l, t) in _headings(lines)]})")
    start, end = b
    name = _norm(repo_path).split("/")[-1]
    link = f"[**{name}**]({_norm(repo_path)}/)"
    tbl = _table_in(lines, start, end)
    if tbl:
        first, last, ncols = tbl
        if ncols == 3:
            row = f"| {link} | {phase or '—'} | {description} |"
        elif ncols == 2:
            row = f"| {link} | {description} |"
        else:
            raise ValueError(f"the table under {section!r} has {ncols} columns; only 2- or 3-column skill tables are supported")
        lines.insert(last + 1, row)
        created = False
    else:
        # No table yet: add a minimal one at the end of the section's text.
        ins = end
        while ins > start and lines[ins - 1].strip() == "":
            ins -= 1
        block = ["", "| Skill | What it does |", "|---|---|", f"| {link} | {description} |"]
        lines[ins:ins] = block
        created = True
    path.write_text("\n".join(lines), encoding="utf-8")
    return {"state": "added", "section": section, "entry": _norm(repo_path), "created_table": created}


def main():
    ap = argparse.ArgumentParser(description="Inspect a clone's README skill listing for a skill")
    ap.add_argument("clone_dir")
    ap.add_argument("--repo-path", required=True)
    args = ap.parse_args()
    print(json.dumps(plan(Path(args.clone_dir), args.repo_path), indent=2))
    sys.exit(0)


if __name__ == "__main__":
    main()
