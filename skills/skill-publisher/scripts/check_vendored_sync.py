#!/usr/bin/env python3
"""Verify skill-publisher's VENDORED scripts are behaviorally in sync with canonical.

skill-publisher carries behavioral copies of scripts owned by sibling skills (each identical
to canonical except for the vendor-header docstring) so it runs
standalone (no skill-creator-ccvw / skill-tracer install required):
  - quick_validate.py, portability_lint.py, attribution_lint.py  (canonical: skill-creator-ccvw)
  - render_ledger.py, append_ledger.py                            (canonical: skill-tracer)
Each vendored copy carries a sync-contract header that says "keep in sync; re-copy
when canonical changes." That contract was only enforceable by remembering to run
`diff` by hand. This script makes it executable.

The catch: the vendored copies INTENTIONALLY differ from canonical in exactly one
place — the module docstring (the vendor-contract note). So a raw byte-diff always
"fails." This script compares the BEHAVIORAL content — everything after the module
docstring — and reports drift only if the actual code differs. (It also reports if
a canonical source is missing, which would mean the sibling skill was uninstalled.)

Pure-stdlib. Run with no args (uses the standard locations) or pass --pairs.

Exit: 0 all in sync; 1 drift (or a canonical source missing); 2 usage error.
"""
from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

SKILLS = Path.home() / ".claude" / "skills"

# (canonical, vendored) pairs — canonical is the source of truth.
DEFAULT_PAIRS = [
    (SKILLS / "skill-creator-ccvw/scripts/quick_validate.py",   SKILLS / "skill-publisher/scripts/quick_validate.py"),
    (SKILLS / "skill-creator-ccvw/scripts/portability_lint.py", SKILLS / "skill-publisher/scripts/portability_lint.py"),
    (SKILLS / "skill-creator-ccvw/scripts/attribution_lint.py", SKILLS / "skill-publisher/scripts/attribution_lint.py"),
    (SKILLS / "skill-tracer/scripts/render_ledger.py",          SKILLS / "skill-publisher/scripts/render_ledger.py"),
    (SKILLS / "skill-tracer/scripts/append_ledger.py",          SKILLS / "skill-publisher/scripts/append_ledger.py"),
]


def strip_module_docstring(src: str) -> str:
    """Return source with the leading module docstring removed (the one intentional
    vendor difference), so the comparison is of behavioral code only."""
    try:
        tree = ast.parse(src)
    except SyntaxError:
        # If it doesn't parse, fall back to raw text — a parse error is itself drift-worthy.
        return src
    body = tree.body
    if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant) \
            and isinstance(body[0].value.value, str):
        doc = body[0]
        end = getattr(doc, "end_lineno", None)
        if end is not None:
            lines = src.splitlines()
            return "\n".join(lines[end:])
    return src


def main() -> int:
    ap = argparse.ArgumentParser(description="Check skill-publisher vendored scripts vs canonical")
    ap.add_argument("--pairs", default=None,
                    help="JSON list of [canonical, vendored] path pairs (default: the standard 5)")
    args = ap.parse_args()

    if args.pairs:
        try:
            pairs = [(Path(c).expanduser(), Path(v).expanduser()) for c, v in json.loads(args.pairs)]
        except (json.JSONDecodeError, ValueError) as e:
            print(f"ERROR: --pairs must be JSON [[canonical,vendored],...]: {e}", file=sys.stderr)
            return 2
    else:
        pairs = DEFAULT_PAIRS

    results = []
    drift = False
    for canonical, vendored in pairs:
        entry = {"canonical": str(canonical), "vendored": str(vendored)}
        if not canonical.is_file():
            entry["status"] = "CANONICAL_MISSING"
            entry["detail"] = "canonical source not found — sibling skill uninstalled?"
            drift = True
        elif not vendored.is_file():
            entry["status"] = "VENDORED_MISSING"
            entry["detail"] = "vendored copy not found"
            drift = True
        else:
            cbody = strip_module_docstring(canonical.read_text())
            vbody = strip_module_docstring(vendored.read_text())
            if cbody == vbody:
                entry["status"] = "IN_SYNC"
            else:
                entry["status"] = "DRIFT"
                entry["detail"] = "behavioral code differs (beyond the vendor-header docstring) — re-copy from canonical"
                drift = True
        results.append(entry)

    print(json.dumps({"in_sync": not drift, "results": results}, indent=2))
    for e in results:
        if e["status"] != "IN_SYNC":
            print(f"{e['status']}: {Path(e['vendored']).name} — {e.get('detail','')}", file=sys.stderr)
    return 1 if drift else 0


if __name__ == "__main__":
    sys.exit(main())
