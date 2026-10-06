#!/usr/bin/env python3
"""Tmp-prompt cleanup for skill-tracer.

Dispatch staging writes /tmp/skill-tracer-prompts/<name>-<RUN_TIMESTAMP>.* files (staged prompts,
manifests, blast / cluster json). RUN_TIMESTAMP is the `<Runtime>` with ':' replaced by '-'
(ledger_common.runtime_slug); every file the scripts name for a run carries it. Over many rounds
and many traces these accumulate without bound. Must be
deleted at every terminal state (convergence, a round-gate stop, a USER-PAUSE or hard-error stop; SKILL.md "Stop rules") -- not just at convergence -- except a
hard-error stop whose marker is still a `dispatched` state, whose dispatch manifest the resume reads
(references/recovery.md "Stale-tmp cleanup"). At every other terminal state the next session
restages from scratch (re-running the front-half script re-stages every tmp file, including the
dispatch manifests), so tmp is not load-bearing for resume there and is safe to delete.

Usage:
    cleanup_tmp_prompts.py --run-timestamp <Runtime or RUN_TIMESTAMP> [--dir /tmp/skill-tracer-prompts]
        (either spelling selects the same files: the argument is normalised with runtime_slug)
    cleanup_tmp_prompts.py --all [--dir /tmp/skill-tracer-prompts]   # every run, any timestamp

Deletes matching files, never anything else in --dir. Missing directory is not
an error (nothing to clean). Prints JSON {"deleted": [...], "dir": "..."}.
Exit: 0 (best-effort cleanup, not a gate: a failed delete is a warning, never a failure); 2 only when
neither --run-timestamp nor --all was given.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ledger_common as lc  # noqa: E402

DEFAULT_DIR = "/tmp/skill-tracer-prompts"


def main() -> int:
    ap = argparse.ArgumentParser(description="skill-tracer tmp-prompt cleanup")
    ap.add_argument("--run-timestamp", default="", help="delete only files for this RUN_TIMESTAMP")
    ap.add_argument("--all", action="store_true", help="delete every staged file in --dir, any run")
    ap.add_argument("--dir", default=DEFAULT_DIR)
    args = ap.parse_args()

    if not args.run_timestamp and not args.all:
        print("ERROR: pass --run-timestamp <ts> or --all", file=sys.stderr)
        return 2

    target = Path(args.dir).expanduser()
    if not target.is_dir():
        print(json.dumps({"deleted": [], "dir": str(target), "note": "directory does not exist, nothing to clean"}))
        return 0

    run_slug = lc.runtime_slug(args.run_timestamp) if args.run_timestamp else ""
    deleted = []
    for f in target.iterdir():
        if not f.is_file():
            continue
        if args.all or (run_slug and run_slug in f.name):
            try:
                f.unlink()
                deleted.append(f.name)
            except OSError as e:
                print(f"WARNING: could not delete {f}: {e}", file=sys.stderr)

    print(json.dumps({"deleted": sorted(deleted), "dir": str(target)}))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(0)
