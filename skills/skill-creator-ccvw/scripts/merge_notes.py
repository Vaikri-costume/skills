#!/usr/bin/env python3
"""Merge the analyst's notes into benchmark.json's top-level `notes`.

Input: --iteration-dir DIR holding benchmark.json (from aggregate_benchmark) and analyst-notes.json
(a JSON array of strings). Output: benchmark.json rewritten with `notes` set to that array.
Exit 0 merged (an empty array is valid only when benchmark.json has a non-empty runs[]);
exit 1 when a file is missing or unparseable, the notes are not an array of strings, or the
array is empty while runs[] is empty/absent (the analyst or aggregation did not really run:
re-run aggregate_benchmark, re-dispatch the analyst, merge again). The message says which.
"""
import argparse
import json
import sys
from pathlib import Path


def merge(iteration_dir):
    d = Path(iteration_dir)
    bpath, npath = d / "benchmark.json", d / "analyst-notes.json"
    for p in (bpath, npath):
        if not p.is_file():
            return False, f"missing {p}"
    try:
        bench = json.loads(bpath.read_text())
        notes = json.loads(npath.read_text())
    except ValueError as exc:
        return False, f"unparseable JSON: {exc}"
    if not isinstance(bench, dict):
        return False, "benchmark.json is not an object"
    if not isinstance(notes, list) or not all(isinstance(n, str) for n in notes):
        return False, "analyst-notes.json is not an array of strings: re-dispatch the analyst"
    if not notes and not bench.get("runs"):
        return False, "empty notes and no runs[] in benchmark.json: re-run aggregate_benchmark and the analyst"
    bench["notes"] = notes
    bpath.write_text(json.dumps(bench, indent=2) + "\n")
    return True, f"merged {len(notes)} notes"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--iteration-dir", required=True)
    a = ap.parse_args(argv)
    ok, msg = merge(a.iteration_dir)
    print(msg, file=sys.stdout if ok else sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
