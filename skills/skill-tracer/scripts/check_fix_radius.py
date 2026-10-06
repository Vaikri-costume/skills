#!/usr/bin/env python3
"""Fix-impact-closure enforcer for skill-tracer.

A FIX that changes a shared token (a renamed step number, a flag prefix, a value,
a vocabulary keyword, a cross-reference) must land at EVERY site that token appears,
not just the one the trace flagged. Recording a FIX while leaving sibling sites stale
is the drift class the whole skill exists to catch — yet nothing forced the orchestrator
to enumerate the radius. This script does: given the token a FIX changed and the files
the FIX actually touched, it greps the token across every in-scope file and FAILS
(exit 1) if any occurrence sits in a file the FIX did not touch — i.e. an uncovered site.

It greps the token as a FIXED string (not a regex), case-sensitively by default.
"In-scope" is exactly the set `inscope.py`'s `inscope_files()` enumerates — the same
scope authority `code_review_run.py` and `coverage_check.py` use, so a FIX's blast
radius is checked against the identical file set the cold review/coverage agents see.

Usage:
    check_fix_radius.py --skill-root <root> --token "<changed token>" \\
        --touched "<file1>,<file2>,..." [--allow "<file>,..."] [--ignore-case]

  --touched : comma-separated files (absolute, or relative to --skill-root) the FIX edited.
  --allow   : comma-separated files where the token legitimately remains untouched
              (e.g. a deliberate quotation of the old value in a WHY comment). Excluded
              from the uncovered set. Use sparingly and only with a stated reason.
              README.md, HISTORY.md and LICENSE are outside inscope.py's scope, so they
              are never reported and never need --allow.
  --ignore-case : case-insensitive grep.

Output: JSON {token, occurrences:[{file,line,text}], files_with_token:[...],
              touched:[...], uncovered:[...]}. Exit 0 if uncovered is empty, 1 if not,
2 on usage error (skill-root missing, no --token). Pure-stdlib.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from inscope import inscope_files  # noqa: E402 — single source of truth for in-scope
# file enumeration, shared with code_review_run.py and coverage_check.py (one-home rule).


def in_scope_files(root: Path) -> list[Path]:
    return inscope_files(root)


def main() -> int:
    ap = argparse.ArgumentParser(description="skill-tracer fix-impact-closure enforcer")
    ap.add_argument("--skill-root", required=True)
    ap.add_argument("--token", required=True)
    ap.add_argument("--touched", default="")
    ap.add_argument("--allow", default="")
    ap.add_argument("--ignore-case", action="store_true")
    args = ap.parse_args()

    root = Path(args.skill_root).expanduser()
    if not root.is_dir():
        print(f"ERROR: skill-root not a directory: {root}", file=sys.stderr)
        return 2
    if not args.token:
        print("ERROR: --token must be non-empty", file=sys.stderr)
        return 2

    def norm(csv: str) -> set[str]:
        s = set()
        for raw in csv.split(","):
            raw = raw.strip()
            if not raw:
                continue
            pp = Path(raw).expanduser()
            pp = pp if pp.is_absolute() else (root / raw)
            s.add(str(pp.resolve()))
        return s

    touched = norm(args.touched)
    allow = norm(args.allow)
    needle = args.token.lower() if args.ignore_case else args.token

    occurrences = []
    files_with = set()
    for f in in_scope_files(root):
        try:
            text = f.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # binary/asset — not a token site
        for i, line in enumerate(text.splitlines(), 1):
            hay = line.lower() if args.ignore_case else line
            if needle in hay:
                rf = str(f.resolve())
                occurrences.append({"file": rf, "line": i, "text": line.strip()[:200]})
                files_with.add(rf)

    uncovered = sorted(files_with - touched - allow)
    result = {
        "token": args.token,
        "files_with_token": sorted(files_with),
        "touched": sorted(touched),
        "allow": sorted(allow),
        "uncovered": uncovered,
        "occurrences": occurrences,
    }
    print(json.dumps(result, indent=2))
    return 1 if uncovered else 0


if __name__ == "__main__":
    sys.exit(main())
