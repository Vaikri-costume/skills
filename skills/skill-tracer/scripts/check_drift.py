#!/usr/bin/env python3
"""PRE-FLIGHT drift test for skill-tracer.

Each cold trace agent emits one PRE-FLIGHT line per file it read, in the format:
    PRE-FLIGHT <path>: <line_count> lines, last edited <yyyy-mm-dd>

The cold-trace invariant requires the target files to be unchanged between
dispatch and result-collection. This script compares each reported PRE-FLIGHT
line against the file's CURRENT state (live `wc -l` line count + mtime date) and
reports drift. Per ledger-format.md "PRE-FLIGHT drift test", drift is "non-zero":
ANY line-count delta OR ANY last-edited-date difference counts as concurrent
modification — there is no fuzzy threshold.

Used at two call sites (SKILL.md Step 5 result-collection, and recovery-protocol
rule 1 before consuming recovered results). Pure-stdlib so it runs anywhere.

Input: the agents' PRE-FLIGHT lines, via --file <path> (one line per line) or
stdin. Non-PRE-FLIGHT lines are ignored, so you can pipe a whole agent report.

Output: JSON to stdout —
    {
      "checked": <int>,            # PRE-FLIGHT lines parsed
      "drift": [                   # one entry per drifted file
        {"path","reported_lines","current_lines","reported_date","current_date","reason"}
      ],
      "unparseable": ["<raw line>", ...],   # PRE-FLIGHT-looking lines we couldn't parse
      "missing": ["<path>", ...]            # reported files that no longer exist on disk
    }

Exit codes:
    0 — no drift (all reported files match current state)
    1 — drift detected (or a reported file is missing) — caller must re-dispatch cold
    2 — usage error / no PRE-FLIGHT lines found in input
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import sys
from pathlib import Path

# PRE-FLIGHT <path>: <line_count> lines, last edited <yyyy-mm-dd>
# Path may contain spaces; line_count is an int; date is yyyy-mm-dd.
PREFLIGHT_RE = re.compile(
    r"^\s*PRE-FLIGHT\s+(?P<path>.+?):\s*(?P<lines>\d+)\s+lines,\s*last edited\s+(?P<date>\d{4}-\d{2}-\d{2})\s*$"
)


def count_lines(path: Path) -> int:
    """Line count matching `wc -l` semantics (count of newline characters)."""
    n = 0
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            n += chunk.count(b"\n")
    return n


def mtime_date(path: Path) -> str:
    """File mtime as a yyyy-mm-dd local-date string (matches the PRE-FLIGHT format)."""
    ts = path.stat().st_mtime
    return _dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%d")


def check(lines: list[str]) -> dict:
    drift = []
    unparseable = []
    missing = []
    checked = 0
    for raw in lines:
        if "PRE-FLIGHT" not in raw:
            continue  # not a pre-flight line; ignore (lets callers pipe whole reports)
        m = PREFLIGHT_RE.match(raw.rstrip("\n"))
        if not m:
            unparseable.append(raw.strip())
            continue
        checked += 1
        path = Path(m.group("path").strip()).expanduser()
        reported_lines = int(m.group("lines"))
        reported_date = m.group("date")
        if not path.is_file():
            missing.append(str(path))
            drift.append({
                "path": str(path),
                "reported_lines": reported_lines,
                "current_lines": None,
                "reported_date": reported_date,
                "current_date": None,
                "reason": "file missing on disk",
            })
            continue
        cur_lines = count_lines(path)
        cur_date = mtime_date(path)
        reasons = []
        if cur_lines != reported_lines:
            reasons.append(f"line-count {reported_lines}->{cur_lines}")
        if cur_date != reported_date:
            reasons.append(f"mtime-date {reported_date}->{cur_date}")
        if reasons:
            drift.append({
                "path": str(path),
                "reported_lines": reported_lines,
                "current_lines": cur_lines,
                "reported_date": reported_date,
                "current_date": cur_date,
                "reason": "; ".join(reasons),
            })
    return {
        "checked": checked,
        "drift": drift,
        "unparseable": unparseable,
        "missing": missing,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="PRE-FLIGHT drift test (skill-tracer)")
    ap.add_argument("--file", help="file containing PRE-FLIGHT lines (default: stdin)")
    args = ap.parse_args()

    if args.file:
        p = Path(args.file).expanduser()
        if not p.is_file():
            print(f"ERROR: --file not found: {p}", file=sys.stderr)
            return 2
        lines = p.read_text().splitlines()
    else:
        if sys.stdin.isatty():
            print("ERROR: no input — pass --file <path> or pipe PRE-FLIGHT lines on stdin",
                  file=sys.stderr)
            return 2
        lines = sys.stdin.read().splitlines()

    result = check(lines)
    print(json.dumps(result, indent=2))
    if result["checked"] == 0:
        print("ERROR: no PRE-FLIGHT lines found in input", file=sys.stderr)
        return 2
    return 1 if (result["drift"] or result["missing"]) else 0


if __name__ == "__main__":
    sys.exit(main())
