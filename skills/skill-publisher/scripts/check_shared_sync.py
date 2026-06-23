#!/usr/bin/env python3
"""DORMANT — manual drift-inspection tool. Not run anywhere in the ship flow.

The sync contract is **RETIRED** (2026-06-20). skill-creator-ccvw, skill-tracer, and
skill-publisher each carry their own INDEPENDENT copy of the scripts below and may
freely diverge — nothing requires them to match, and nothing runs this checker
automatically. It is kept only so that someone who *wants* to compare the copies (e.g.
to cherry-pick a fix from one skill into another by hand) can still see the behavioral
diff. Drift is no longer a finding; do NOT treat a non-zero exit as something to "fix".
To actually hand-port one fix from one copy into another (single direction, destination
docstring preserved), use the companion tool `sync_shared.py`.

Formerly-shared groups (now independent per-skill copies):
  - quick_validate.py, portability_lint.py, attribution_lint.py  (skill-creator-ccvw, skill-publisher)
  - render_ledger.py, append_ledger.py                            (skill-tracer, skill-publisher)

The copies differ INTENTIONALLY in exactly one place — the module docstring (each names
its own skill's context). This script compares the BEHAVIORAL content — everything after
the module docstring — and reports drift only if the actual code differs. It also reports
if a copy is missing (a sibling skill was uninstalled).

Pure-stdlib. Run with no args (uses the standard locations) or pass --groups.

Exit: 0 all groups in sync; 1 drift (or a copy missing); 2 usage error.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Single home of the AST module-docstring split lives in sync_shared.py (same
# scripts/ dir, on sys.path[0] when this runs as a script) — import it rather than
# re-implementing the same ast walk here, so the two cannot drift.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from sync_shared import split_at_docstring

SKILLS = Path.home() / ".claude" / "skills"

# Each formerly-shared script -> the list of per-skill copies it can be diffed against.
# These are now INDEPENDENT copies (sync contract retired); this map only tells the
# dormant diff tool where the sibling copies live, not which to "propagate" — there is
# no propagation anymore.
DEFAULT_GROUPS = {
    "quick_validate.py": [
        SKILLS / "skill-creator-ccvw/scripts/quick_validate.py",
        SKILLS / "skill-publisher/scripts/quick_validate.py",
    ],
    "portability_lint.py": [
        SKILLS / "skill-creator-ccvw/scripts/portability_lint.py",
        SKILLS / "skill-publisher/scripts/portability_lint.py",
    ],
    "attribution_lint.py": [
        SKILLS / "skill-creator-ccvw/scripts/attribution_lint.py",
        SKILLS / "skill-publisher/scripts/attribution_lint.py",
    ],
    "render_ledger.py": [
        SKILLS / "skill-tracer/scripts/render_ledger.py",
        SKILLS / "skill-publisher/scripts/render_ledger.py",
    ],
    "append_ledger.py": [
        SKILLS / "skill-tracer/scripts/append_ledger.py",
        SKILLS / "skill-publisher/scripts/append_ledger.py",
    ],
}


def strip_module_docstring(src: str) -> str:
    """Behavioral code only — the shebang + module docstring (the intentional
    per-copy differences) removed, so the comparison is of behavioral code. Delegates
    to sync_shared.split_at_docstring (the single home of the AST split); on a parse
    error that returns None and we fall back to the raw text (a parse error is itself
    drift-worthy)."""
    parts = split_at_docstring(src)
    if parts is None:
        return src
    return "\n".join(parts[1])


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Check shared scripts are behaviorally identical across sibling skills"
    )
    ap.add_argument("--groups", default=None,
                    help='JSON object {name: [path, path, ...]} of shared-script peer groups '
                         "(default: the standard 5)")
    args = ap.parse_args()

    if args.groups:
        try:
            groups = {name: [Path(p).expanduser() for p in paths]
                      for name, paths in json.loads(args.groups).items()}
        except (json.JSONDecodeError, ValueError, AttributeError) as e:
            print(f"ERROR: --groups must be JSON {{name:[path,...]}}: {e}", file=sys.stderr)
            return 2
    else:
        groups = DEFAULT_GROUPS

    results = []
    drift = False
    for name, paths in groups.items():
        entry = {"script": name, "copies": [str(p) for p in paths]}
        present = [p for p in paths if p.is_file()]
        missing = [str(p) for p in paths if not p.is_file()]
        if missing:
            entry["status"] = "COPY_MISSING"
            entry["detail"] = (f"missing copies (sibling skill uninstalled?): "
                               f"{', '.join(missing)}")
            drift = True
        else:
            bodies = {str(p): strip_module_docstring(p.read_text(encoding="utf-8")) for p in present}
            distinct = set(bodies.values())
            if len(distinct) == 1:
                entry["status"] = "IN_SYNC"
            else:
                entry["status"] = "DRIFT"
                entry["detail"] = ("behavioral code differs across the per-skill copies (beyond the "
                                   "per-copy docstring). This is informational only — the copies are "
                                   "INDEPENDENT (sync contract retired); divergence is expected and "
                                   "is NOT something to fix. Hand-port between copies only if you "
                                   "specifically want to.")
                drift = True
        results.append(entry)

    print(json.dumps({"in_sync": not drift, "results": results}, indent=2))
    for e in results:
        if e["status"] != "IN_SYNC":
            print(f"{e['status']}: {e['script']} — {e.get('detail','')}", file=sys.stderr)
    return 1 if drift else 0


if __name__ == "__main__":
    sys.exit(main())
