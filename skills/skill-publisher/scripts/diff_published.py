#!/usr/bin/env python3
"""Structured diff of a local skill against its published (upstream) state.

Step 7a feeds this to the cold changelog agent: a machine-readable
added/removed/modified breakdown plus a per-file unified diff, so the changelog is
grounded in what ACTUALLY changed since the last ship — not only this run's ledger
rows (which miss out-of-ledger manual edits) and not only a git tag (which may be
absent). The agent reconciles this diff with the ledger rows at equal weight.

The published state is a checkout of the upstream repo at the skill's in-repo path
(github_pr.py --diff-only produces it). Scope mirrors what actually ships: it
reuses package_skill.should_exclude() by import so the same files the package
omits (.bak, __pycache__, hidden, eval run-outputs, -workspace) never appear as
churn. HISTORY.md is additionally excluded — it is the changelog target itself, so
diffing it would feed the agent its own prior output as a "change".

Usage:
    diff_published.py <local-skill-path> --published <published-skill-path> [--json]

Exit: 0 = diff computed (printed; `changed` may be false if identical);
      1 = no published state to diff against (the --published path is absent or has
          no in-scope files → caller falls back to ledger-only / local-tag sourcing);
      2 = usage/path error (local path missing SKILL.md, etc.).
"""
from __future__ import annotations

import argparse
import difflib
import json
import sys
from pathlib import Path

# Reuse the packaging exclusion so the diff scope == the shipped scope (one home).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from package_skill import should_exclude

# Excluded from the DIFF (beyond should_exclude): HISTORY.md is the changelog file
# the agent is about to write — feeding its diff back would be circular.
_DIFF_EXTRA_EXCLUDE = {"HISTORY.md"}


def _in_scope_files(root: Path) -> dict:
    """{posix-rel-path: abs Path} of every in-scope file under root."""
    out = {}
    for f in sorted(root.rglob("*")):
        if not f.is_file():
            continue
        rel = f.relative_to(root)
        if should_exclude(rel) or rel.name in _DIFF_EXTRA_EXCLUDE:
            continue
        out[rel.as_posix()] = f
    return out


def _read_text(p: Path):
    """Return file text, or None if it is binary (can't be unified-diffed)."""
    try:
        return p.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None


def compute_diff(local: Path, published: Path, local_files: dict | None = None,
                 pub_files: dict | None = None) -> dict:
    # Callers may pass a pre-walked file map (main() walks `published` once for the
    # emptiness check and hands it in here) to avoid re-walking the tree.
    if local_files is None:
        local_files = _in_scope_files(local)
    if pub_files is None:
        pub_files = _in_scope_files(published)

    added = sorted(set(local_files) - set(pub_files))
    removed = sorted(set(pub_files) - set(local_files))
    modified = []
    for rel in sorted(set(local_files) & set(pub_files)):
        lp, pp = local_files[rel], pub_files[rel]
        lt, pt = _read_text(lp), _read_text(pp)
        if lt is None or pt is None:
            # Binary (or unreadable) — compare bytes, no unified diff.
            try:
                if lp.read_bytes() != pp.read_bytes():
                    modified.append({"path": rel, "binary": True, "diff": ""})
            except OSError:
                modified.append({"path": rel, "binary": True, "diff": "",
                                 "note": "unreadable"})
            continue
        if lt != pt:
            diff = "\n".join(difflib.unified_diff(
                pt.splitlines(), lt.splitlines(),
                fromfile=f"published/{rel}", tofile=f"local/{rel}", lineterm=""))
            modified.append({"path": rel, "binary": False, "diff": diff})

    changed = bool(added or removed or modified)
    return {
        "local": str(local),
        "published": str(published),
        "changed": changed,
        "added": added,
        "removed": removed,
        "modified": modified,
        "summary": {
            "added": len(added),
            "removed": len(removed),
            "modified": len(modified),
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Structured diff of a local skill vs its published state")
    ap.add_argument("local", help="local skill directory (the one being shipped)")
    ap.add_argument("--published", required=True,
                    help="published skill directory (checkout of the upstream at the in-repo path)")
    ap.add_argument("--json", dest="json_out", action="store_true",
                    help="emit JSON (default: also JSON — this flag is accepted for symmetry)")
    args = ap.parse_args()

    local = Path(args.local).expanduser()
    if not (local / "SKILL.md").is_file():
        print(f"ERROR: no SKILL.md under local path {local}", file=sys.stderr)
        return 2

    published = Path(args.published).expanduser()
    # Walk `published` ONCE for the in-scope file map, and decide "no published
    # state" from THAT — not a raw `any(rglob("*"))`, which counts excluded files
    # (a `.git`/`__pycache__` left in the clone) as content and would make an
    # un-published path report every local file as `added` instead of falling back.
    pub_files = _in_scope_files(published) if published.is_dir() else {}
    if not pub_files:
        print(json.dumps({
            "local": str(local),
            "published": str(published),
            "no_published_state": True,
            "detail": "published path absent or has no in-scope files — "
                      "fall back to ledger-only changelog sourcing",
        }, indent=2), file=sys.stderr)
        return 1

    print(json.dumps(compute_diff(local, published, pub_files=pub_files), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
