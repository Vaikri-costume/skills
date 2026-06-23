#!/usr/bin/env python3
"""Ship-manifest writer for skill-publisher Step 10.

Records the durable facts of a completed ship to
`~/.claude/skill-publisher-ledger/<skill>.manifest.json` so a later session can
answer "what shipped, where, at what version, and is the artifact intact?" without
re-deriving it from the audit ledger. Phase 4 (ship_status / rollback) reads it.

Written on EVERY ship path — full PR ship, no-upstream hosting branch, and
degraded (no HISTORY.md) — so the lifecycle record is never missing. Fields that
don't apply to a path are omitted (no pr_url / branch / tag on a local-only or
personal ship; no archive_sha256 on a personal ship with no artifact). The file is
the LATEST ship's record (overwritten each ship); rollback restores from a Step-1
pre-ship snapshot, not from manifest history, so a single object is sufficient.

Usage:
    ship_manifest.py write <skill-name> --version X.Y.Z --tier <tier> --timestamp <ISO>
        [--artifact <path>] [--digest <sha256>] [--pr-url <url>] [--branch <branch>]
        [--tag <tag>] [--merge-strategy-unknown]
    ship_manifest.py read <skill-name>        # print the manifest (exit 1 if absent)

Exit: 0 ok; 1 read: manifest absent; 2 usage error (argparse); 3 I/O error
(write/read failed — error JSON on stderr; distinct from the argparse usage exit 2
so a caller can tell a bad invocation from a disk/permission failure).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

LEDGER_DIR = Path.home() / ".claude" / "skill-publisher-ledger"


def _manifest_path(skill: str) -> Path:
    return LEDGER_DIR / f"{skill}.manifest.json"


def cmd_write(args) -> int:
    manifest: dict = {
        "skill": args.skill,
        "version": args.version,
        "tier": args.tier,
        "timestamp": args.timestamp,
    }
    # Optional fields — present only on the paths that produce them.
    if args.artifact:
        manifest["artifact"] = args.artifact
    if args.digest:
        manifest["archive_sha256"] = args.digest
    if args.pr_url:
        manifest["pr_url"] = args.pr_url
    if args.branch:
        manifest["branch"] = args.branch
    if args.tag:
        manifest["tag"] = args.tag
    # Always recorded (even False) so Phase 4 status can distinguish "known
    # merge-commit upstream" from "unknown — re-point the tag after merge".
    manifest["merge_strategy_unknown"] = bool(args.merge_strategy_unknown)

    path = _manifest_path(args.skill)
    try:
        LEDGER_DIR.mkdir(parents=True, exist_ok=True)
        # Atomic write: a durable record must never be left truncated by a crash
        # mid-write (a later reader would silently get a corrupt/empty manifest).
        # Write to a temp file in the same dir, then os.replace (atomic rename).
        fd, tmp_name = tempfile.mkstemp(prefix=f"{args.skill}.manifest-", suffix=".tmp", dir=str(LEDGER_DIR))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(json.dumps(manifest, indent=2) + "\n")
            os.replace(tmp_name, path)
        except OSError:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
    except OSError as e:
        print(json.dumps({"error": f"could not write manifest: {e}"}), file=sys.stderr)
        return 3
    print(json.dumps({"written": str(path), "manifest": manifest}, indent=2))
    return 0


def cmd_read(args) -> int:
    path = _manifest_path(args.skill)
    if not path.is_file():
        print(json.dumps({"error": f"no manifest for {args.skill} at {path}"}), file=sys.stderr)
        return 1
    try:
        print(path.read_text(encoding="utf-8"), end="")
    except OSError as e:
        print(json.dumps({"error": f"could not read manifest: {e}"}), file=sys.stderr)
        return 3
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="skill-publisher ship-manifest writer/reader")
    sub = ap.add_subparsers(dest="cmd", required=True)

    w = sub.add_parser("write", help="write/overwrite the ship manifest")
    w.add_argument("skill", help="skill folder name (the manifest is keyed by it)")
    w.add_argument("--version", required=True)
    w.add_argument("--tier", required=True)
    w.add_argument("--timestamp", required=True, help="ISO-8601 ship time")
    w.add_argument("--artifact", default=None)
    w.add_argument("--digest", default=None, help="archive_sha256 from package_skill.py")
    w.add_argument("--pr-url", default=None)
    w.add_argument("--branch", default=None)
    w.add_argument("--tag", default=None)
    w.add_argument("--merge-strategy-unknown", action="store_true",
                   help="set when the upstream may squash/rebase (the ship tag may dangle)")
    w.set_defaults(func=cmd_write)

    r = sub.add_parser("read", help="print the ship manifest")
    r.add_argument("skill")
    r.set_defaults(func=cmd_read)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
