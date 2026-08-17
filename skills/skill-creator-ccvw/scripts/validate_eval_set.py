#!/usr/bin/env python3
"""Validate a trigger-eval set's SHAPE before run_loop.py consumes it.

The Description-Optimization flow hand-assembles a 20-item trigger-eval array
({query, should_trigger}), the user edits it in the HTML reviewer and exports
eval_set.json, then it's fed to run_loop.py. run_loop does `e["should_trigger"]`
/ q["query"] with NO shape validation — a missing key or wrong type crashes
mid-loop, AFTER the background run has started and the user has spent time
reviewing. This script fails FAST: validate the shape up front, surface every
problem at once, exit non-zero so the loop never starts on a malformed set.

Checks (shape + the SKILL.md "8-10 of each class" guidance):
  - top level is a non-empty JSON list
  - each item is an object with `query` (non-empty string) and `should_trigger` (bool)
  - no unexpected keys (warns, doesn't fail)
  - class balance: count should_trigger true/false; warn if either is outside ~8-10
    (advisory — the loop runs fine, but a lopsided set tests poorly)

Pure-stdlib. Validates SHAPE only — the QUALITY of the queries (realistic? good
near-misses?) is the model's + user's judgment, never scripted.

Usage:  validate_eval_set.py <eval_set.json>   (or '-' for stdin)
Output JSON: {valid, item_count, trigger_count, no_trigger_count, errors[], warnings[]}
Exit: 0 valid (loop may start); 1 invalid (do NOT start the loop); 2 usage / unreadable / not JSON.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

EXPECTED_KEYS = {"query", "should_trigger"}
CLASS_MIN, CLASS_MAX = 8, 10  # SKILL.md guidance: 8-10 should-trigger + 8-10 should-not-trigger


def validate(data) -> dict:
    errors, warnings = [], []
    if not isinstance(data, list):
        return {"valid": False, "errors": ["top level must be a JSON list of {query, should_trigger} objects"],
                "warnings": [], "item_count": 0, "trigger_count": 0, "no_trigger_count": 0}
    if not data:
        errors.append("eval set is empty")

    trig = notrig = 0
    for i, item in enumerate(data):
        loc = f"item[{i}]"
        if not isinstance(item, dict):
            errors.append(f"{loc}: must be an object, got {type(item).__name__}")
            continue
        # query
        q = item.get("query")
        if "query" not in item:
            errors.append(f"{loc}: missing 'query'")
        elif not isinstance(q, str) or not q.strip():
            errors.append(f"{loc}: 'query' must be a non-empty string")
        # should_trigger
        st = item.get("should_trigger")
        if "should_trigger" not in item:
            errors.append(f"{loc}: missing 'should_trigger'")
        elif not isinstance(st, bool):
            errors.append(f"{loc}: 'should_trigger' must be a boolean (true/false), got {type(st).__name__}")
        else:
            trig += 1 if st else 0
            notrig += 0 if st else 1
        # unexpected keys (advisory)
        extra = set(item.keys()) - EXPECTED_KEYS
        if extra:
            warnings.append(f"{loc}: unexpected key(s) {sorted(extra)} (ignored by run_loop)")

    # class-balance advisories (only meaningful if no hard errors on those items)
    if not any("should_trigger" in e for e in errors):
        if not (CLASS_MIN <= trig <= CLASS_MAX):
            warnings.append(f"should-trigger count is {trig}; SKILL.md suggests {CLASS_MIN}-{CLASS_MAX} for a balanced set")
        if not (CLASS_MIN <= notrig <= CLASS_MAX):
            warnings.append(f"should-NOT-trigger count is {notrig}; SKILL.md suggests {CLASS_MIN}-{CLASS_MAX} (near-misses are the valuable ones)")

    return {"valid": not errors, "item_count": len(data), "trigger_count": trig,
            "no_trigger_count": notrig, "errors": errors, "warnings": warnings}


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate a trigger-eval set's shape before run_loop")
    ap.add_argument("path", help="eval_set.json path, or '-' for stdin")
    args = ap.parse_args()

    if args.path == "-":
        raw = sys.stdin.read()
    else:
        p = Path(args.path).expanduser()
        if not p.is_file():
            print(f"ERROR: not found: {p}", file=sys.stderr)
            return 2
        raw = p.read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(json.dumps({"valid": False, "errors": [f"not valid JSON: {e}"]}, indent=2))
        return 2

    result = validate(data)
    print(json.dumps(result, indent=2))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    sys.exit(main())
