#!/usr/bin/env python3
"""cascade_sweep.py — the deterministic detector sweep of the cascade.

Runs every ACTIVE detector (detectors/*.py; `_`-prefixed modules are helpers, never detectors) over ONE
target and groups the findings by the detector's LEVEL:
  - prepass   → findings that gate the Prepass tier (prepass_run.py clusters and fixes them).
  - advisory  → lint output that never gates a tier (missing-glossary-entry; scripts/doc_lint.py
                reports it to the orchestrator).

A detector that cannot load, or that raises on a file, is never silently treated as "found
nothing": it is recorded under `detector_errors` (JSON) / reported on stderr, because a crashed
detector would otherwise let a tier read as clean. prepass_run.py refuses to declare Prepass
converged while `detector_errors` is non-empty.

Usage:
    cascade_sweep.py <target-skill-dir> [--level prepass|advisory] [--json]
        --level  run only that level and exit 1 when it has findings (the gate signal prepass_run.py
                 uses); without it, exit 0 always once the target is a directory.
        Exit 2 when <target-skill-dir> is not a directory.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DET = ROOT / "detectors"

# A finding's `detail` must not be clipped by a small cap (the longest detail any detector emits is
# ~600 chars). A detail
# over this cap is cut and ends with an explicit marker so the consumer can tell a cut happened.
DETAIL_MAX_CHARS = 2000
_TRUNC_MARK = " ...[detail truncated]"


def _clip_detail(detail: str) -> str:
    detail = detail or ""
    if len(detail) <= DETAIL_MAX_CHARS:
        return detail
    return detail[:DETAIL_MAX_CHARS] + _TRUNC_MARK

# Single in-scope authority shared with the Code Review path (code_review_run / coverage_check):
# excludes HISTORY.md / README.md / LICENSE (provenance, not the runtime contract) and binary assets, so
# the sweep and the reviewers agree on what "the skill" is.
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))
from inscope import inscope_files  # noqa: E402


def load(p: Path):
    spec = importlib.util.spec_from_file_location(p.stem, p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("target", help="target skill directory")
    ap.add_argument("--level", choices=["prepass", "advisory"], default=None,
                    help="run ONLY this level (prepass findings gate the Prepass tier; advisory never gates)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    target = Path(args.target).expanduser()
    if not target.is_dir():
        print(f"ERROR: not a directory: {target}", file=sys.stderr)
        return 2

    mods = []
    detector_errors: list[dict] = []
    for p in sorted(DET.glob("*.py")):
        if p.name.startswith("_"):
            continue
        try:
            m = load(p)
        except Exception as e:
            print(f"WARN: skip un-loadable {p.name}: {e}", file=sys.stderr)
            detector_errors.append({"detector": p.name, "file": "", "error": f"cannot load: {type(e).__name__}: {e}"})
            continue
        if not all(hasattr(m, a) for a in ("CHECK_ID", "FILE_GLOBS", "detect")):
            continue
        if args.level and getattr(m, "LEVEL", "?") != args.level:
            continue
        mods.append(m)

    out = {"target": str(target), "prepass": [], "advisory": [], "abstains": 0,
           "detector_errors": detector_errors}
    # The shared in-scope set — provenance (HISTORY/README/LICENSE) + binaries excluded.
    allowed = set(inscope_files(target))
    for m in mods:
        lvl = getattr(m, "LEVEL", "?")
        files = []
        for g in m.FILE_GLOBS:
            files += [f for f in target.rglob(g) if f.resolve() in allowed]
        for f in sorted(set(files)):
            try:
                src = f.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            try:
                findings = m.detect(f, src) or []
            except Exception as e:
                rel = str(f.relative_to(target))
                print(f"WARN: detector {m.CHECK_ID} raised on {rel}: {type(e).__name__}: {e}", file=sys.stderr)
                detector_errors.append({"detector": m.CHECK_ID, "file": rel, "error": f"{type(e).__name__}: {e}"})
                continue
            for fd in findings:
                if fd.get("abstain"):
                    out["abstains"] += 1
                    continue
                rec = {"check": m.CHECK_ID, "level": lvl,
                       "file": str(f.relative_to(target)), "line": fd.get("line"),
                       "detail": _clip_detail(fd.get("detail", "")),
                       "token": fd.get("token", "")}
                (out["prepass"] if lvl == "prepass" else out["advisory"]).append(rec)

    if args.json:
        print(json.dumps(out, indent=2))
    else:
        print(f"=== cascade sweep: {target.name} ({len(mods)} active detectors) ===")
        print(f"Prepass findings (auto-surface): {len(out['prepass'])}")
        print(f"Advisory lint findings (never gate): {len(out['advisory'])}")
        print(f"abstains: {out['abstains']}")
        if detector_errors:
            print(f"DETECTOR ERRORS: {len(detector_errors)} (a crashed detector is not a clean result)")
        for lvl_key, label in (("prepass", "Prepass by check"), ("advisory", "Advisory by check")):
            c = Counter(r["check"] for r in out[lvl_key])
            if c:
                print(f"  {label}: " + ", ".join(f"{k}={v}" for k, v in c.most_common()))
    # Gate signal: when one level was requested, non-zero exit means it has findings (for prepass: the
    # tier is NOT clean, so the orchestrator must fix and re-run before code-review).
    if args.level:
        return 1 if out[args.level] else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
