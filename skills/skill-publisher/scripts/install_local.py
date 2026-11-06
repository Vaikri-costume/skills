#!/usr/bin/env python3
"""Install a finished skill on THIS machine (its own step, before the push).

Copies <skill-path> over ~/.claude/skills/<name>/ so waiting for a PR or merge never leaves the
user on an older version. Publishing never installs; this is the only script that does, and it
runs only on the user's typed okay (the orchestrator passes --confirmed after asking).

Default is a DRY RUN: prints what would be added, changed and removed. With --confirmed:
 1. saves the current install to <backup-dir>/<name>.pre-install/ (replacing an earlier backup),
 2. copies the skill over (files the skill no longer has are removed from the install),
 3. prints the result. Python does every copy and delete, so no shell rm is needed.
Excluded names follow package_skill.should_exclude (hidden files, __pycache__, *-workspace).

Usage: install_local.py <skill-path> [--dest-root DIR] [--backup-dir DIR] [--confirmed]
Exit: 0 ok / dry run, 2 usage error, 3 I/O error.
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from package_skill import should_exclude  # noqa: E402


def files(root):
    return {f.relative_to(root) for f in root.rglob("*") if f.is_file() and not should_exclude(f.relative_to(root))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("skill_path")
    ap.add_argument("--dest-root", default="~/.claude/skills")
    ap.add_argument("--backup-dir", default="~/.claude/skill-publisher-ledger")
    ap.add_argument("--confirmed", action="store_true")
    a = ap.parse_args()
    src = Path(a.skill_path).expanduser().resolve()
    if not (src / "SKILL.md").is_file():
        print(json.dumps({"error": f"no SKILL.md in {src}"}), file=sys.stderr)
        sys.exit(2)
    name = src.name
    dest = Path(a.dest_root).expanduser() / name
    if dest.resolve() == src:
        print(json.dumps({"error": "skill is already at the install location; nothing to do"}), file=sys.stderr)
        sys.exit(2)
    s_files = files(src)
    d_files = files(dest) if dest.is_dir() else set()
    added = sorted(str(p) for p in s_files - d_files)
    removed = sorted(str(p) for p in d_files - s_files)
    changed = sorted(str(p) for p in s_files & d_files if (src / p).read_bytes() != (dest / p).read_bytes())
    plan = {"skill": name, "dest": str(dest), "added": added, "changed": changed, "removed": removed,
            "installed_before": dest.is_dir()}
    if not a.confirmed:
        print(json.dumps({"dry_run": True, **plan, "note": "Re-run with --confirmed (after the user's okay) to install."}, indent=2))
        return
    try:
        if dest.is_dir():
            backup = Path(a.backup_dir).expanduser() / f"{name}.pre-install"
            if backup.exists():
                shutil.rmtree(backup)
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(dest, backup)
            plan["backup"] = str(backup)
        for rel in removed:
            (dest / rel).unlink()
        for rel in s_files:
            t = dest / rel
            t.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src / rel, t)
    except OSError as e:
        print(json.dumps({"error": f"install failed: {e}"}), file=sys.stderr)
        sys.exit(3)
    print(json.dumps({"installed": True, **plan}, indent=2))


if __name__ == "__main__":
    main()
