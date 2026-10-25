#!/usr/bin/env python3
"""Write timing.json for one run from the harness's task-completion numbers.

Input: --run-dir DIR (the <config>/run-1/ directory) and optionally --total-tokens N and
--duration-ms N. A value you cannot find is left out and written as 0. Output: DIR/timing.json
with the three fixed keys total_tokens, duration_ms, total_duration_seconds (= duration_ms / 1000,
rounded to 3 places). Exit 1 if DIR does not exist or a value is negative; exit 2 (argparse
usage error) if --run-dir is missing or a value is not a number.
"""
import argparse
import json
import sys
from pathlib import Path


def build(total_tokens=None, duration_ms=None):
    t = 0 if total_tokens is None else total_tokens
    d = 0 if duration_ms is None else duration_ms
    if t < 0 or d < 0:
        raise ValueError("values must not be negative")
    return {"total_tokens": int(t), "duration_ms": int(d), "total_duration_seconds": round(d / 1000, 3)}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--total-tokens", type=float)
    ap.add_argument("--duration-ms", type=float)
    a = ap.parse_args(argv)
    d = Path(a.run_dir)
    if not d.is_dir():
        print(f"run directory not found: {d}", file=sys.stderr)
        return 1
    try:
        data = build(a.total_tokens, a.duration_ms)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    (d / "timing.json").write_text(json.dumps(data, indent=2) + "\n")
    print(json.dumps(data))
    return 0


if __name__ == "__main__":
    sys.exit(main())
