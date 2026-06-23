#!/usr/bin/env python3
"""Description-triggering signal for skill-publisher (Step 3 / readiness).

Two layers, mode-gated:

  1. ALWAYS (cheap, no subprocess) — a deterministic **description-quality
     heuristic** over the target SKILL.md `description` frontmatter:
       - negative-trigger boundary present? (the P1b "Do NOT use …" signal that
         lets the router de-trigger this skill on a sibling's job)
       - WHEN stated? (trigger phrases / "use when …")
       - length within the quick_validate ceiling (≤1024)
     It emits a coarse `confidence` (high|medium|low). This is the confidence
     field the readiness report surfaces — advisory, never a ship-blocker.

  2. OPT-IN `--run-eval` (slow, spawns `claude -p` subprocesses) — measures the
     ACTUAL trigger accuracy by calling skill-creator-ccvw's EXISTING triggering-
     eval harness (`scripts/run_eval.py`). It does NOT reimplement that engine —
     it locates ccvw, validates the eval-set SHAPE (a guard, not the engine),
     shells out, and parses the harness's JSON summary. Below the accuracy
     threshold → the caller raises an AUDIT cluster and FIXes the description
     (e.g. via ccvw's run_loop.py / improve_description.py, or a manual rewrite).
     Protects ship latency by being off by default.

The triggering eval set is a `{query, should_trigger}` LIST (the shape
run_eval.py / validate_eval_set.py consume) — distinct from a skill's behavioral
`evals/evals.json` ({skill_name, evals:[…]}). It rarely lives in the skill source
tree (ccvw exports it to a workspace as eval_set.json), so `--run-eval` REQUIRES
an explicit `--eval-set <path>`; absent that (or absent ccvw / a harness error)
the eval degrades to "could not run" (exit 3) — never a false "passed", never a
false "below threshold" (a broken environment must not read as a bad description).

Usage:
    triggering_eval.py <skill-path> [--json]
    triggering_eval.py <skill-path> --run-eval --eval-set <queries.json>
        [--accuracy-threshold 0.8] [--trigger-threshold 0.5]
        [--runs-per-query 3] [--timeout 30] [--num-workers 10]
        [--model MODEL] [--ccvw-dir <dir>] [--json]

Exit:
    0  ran cleanly; no below-threshold finding
    1  triggering accuracy below threshold (only under --run-eval) — AUDIT cluster
    2  usage / path error (SKILL.md not found, bad args)
    3  --run-eval requested but the harness could not run (ccvw missing,
       eval-set missing/malformed, or run_eval errored) — degrade to the heuristic
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).parent
sys.path.insert(0, str(SCRIPTS))
from frontmatter_util import block as _fm_block, field as _fm_field

DEFAULT_CCVW = Path.home() / ".claude" / "skills" / "skill-creator-ccvw"
DESC_MAX = 1024  # mirrors quick_validate.py's description ceiling

# Negative-trigger boundary: "Do NOT use …", "Don't use …", "never use …",
# "not for …", "not to …". Case-insensitive; the canonical sibling form is
# "Do NOT use to find bugs … or to build …".
_BOUNDARY_RE = re.compile(r"\b(do\s+not|don'?t|never)\s+use\b|\bnot\s+(for|to)\b", re.I)
# WHEN signal: an explicit "use when/whenever/to/for …" clause, OR ≥2 quoted
# trigger examples ('ship skill X', 'publish X', …).
_WHEN_RE = re.compile(r"\buse\s+(it\s+|this\s+)?(when|whenever|to|for)\b", re.I)
_QUOTED_RE = re.compile(r"'[^']+'")


# ── description-quality heuristic (always) ──────────────────────────────────────

def description_quality(description: str) -> dict:
    boundary = bool(_BOUNDARY_RE.search(description))
    has_when = bool(_WHEN_RE.search(description)) or len(_QUOTED_RE.findall(description)) >= 2
    length = len(description)
    length_ok = 0 < length <= DESC_MAX

    notes = []
    if not boundary:
        notes.append("no negative-trigger boundary ('Do NOT use …') — router may over-trigger")
    if not has_when:
        notes.append("no clear WHEN signal (trigger phrases / 'use when …')")
    if length == 0:
        notes.append("empty description")
    elif not length_ok:
        notes.append(f"description over the {DESC_MAX}-char ceiling ({length})")

    missing = (not boundary) + (not has_when) + (not length_ok)
    confidence = "high" if missing == 0 else "medium" if missing == 1 else "low"

    return {
        "boundary_present": boundary,
        "has_when": has_when,
        "length": length,
        "length_ok": length_ok,
        "confidence": confidence,
        "notes": notes,
    }


# ── opt-in triggering eval — delegates to ccvw's run_eval.py ─────────────────────

def _validate_eval_set(path: Path) -> str | None:
    """Minimal SHAPE guard (not the eval engine): a non-empty JSON list of
    {query: non-empty str, should_trigger: bool}. Returns an error string, or
    None when the shape is acceptable."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return f"eval set not found: {path}"
    except OSError as e:
        return f"eval set unreadable: {e}"
    except json.JSONDecodeError as e:
        return f"eval set is not valid JSON: {e}"
    if not isinstance(data, list) or not data:
        return "eval set must be a non-empty JSON list of {query, should_trigger} objects"
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            return f"item {i} is not an object"
        q = item.get("query")
        if not isinstance(q, str) or not q.strip():
            return f"item {i}: 'query' must be a non-empty string"
        if not isinstance(item.get("should_trigger"), bool):
            return f"item {i}: 'should_trigger' must be a boolean"
    return None


def run_triggering_eval(skill_root: Path, eval_set: Path, ccvw_dir: Path,
                        accuracy_threshold: float, trigger_threshold: float,
                        runs_per_query: int, timeout: int, num_workers: int,
                        model: str | None) -> dict:
    """Shell out to ccvw's run_eval.py. Returns a result dict with `ran` and,
    when ran, the accuracy verdict. Never raises on a harness failure — reports
    `ran: false` with a reason so the caller degrades to the heuristic."""
    run_eval = ccvw_dir / "scripts" / "run_eval.py"
    if not run_eval.is_file():
        return {"ran": False,
                "reason": f"skill-creator-ccvw harness not found at {run_eval} "
                          "(pass --ccvw-dir if installed elsewhere)"}

    shape_err = _validate_eval_set(eval_set)
    if shape_err:
        return {"ran": False, "reason": shape_err}

    # run_eval.py imports `scripts.utils`, so it must run as a module from the
    # ccvw skill dir (cwd=ccvw_dir), not by file path.
    cmd = [sys.executable, "-m", "scripts.run_eval",
           "--eval-set", str(eval_set),
           "--skill-path", str(skill_root),
           "--trigger-threshold", str(trigger_threshold),
           "--runs-per-query", str(runs_per_query),
           "--timeout", str(timeout),
           "--num-workers", str(num_workers)]
    if model:
        cmd += ["--model", model]

    try:
        proc = subprocess.run(cmd, cwd=str(ccvw_dir), capture_output=True,
                              text=True, encoding="utf-8")
    except OSError as e:
        return {"ran": False, "reason": f"could not launch run_eval.py: {e}"}

    if proc.returncode != 0:
        # A non-zero exit is an environment/credential/path failure inside the
        # harness — NOT a description verdict. Surface it as "could not run".
        reason = (proc.stderr or proc.stdout or "").strip().splitlines()
        return {"ran": False,
                "reason": f"run_eval.py exited {proc.returncode}: "
                          + (reason[-1] if reason else "no output")}

    try:
        out = json.loads(proc.stdout)
    except json.JSONDecodeError:
        tail = (proc.stderr or "").strip().splitlines()
        return {"ran": False,
                "reason": "run_eval.py produced no parseable JSON summary"
                          + (f"; stderr: {tail[-1]}" if tail else "")}

    summary = out.get("summary", {})
    total = summary.get("total", 0)
    passed = summary.get("passed", 0)
    if not total:
        # run_eval exited 0 but evaluated zero queries (empty/degenerate run — a
        # harness/eval-set anomaly, NOT a description fault). Report could-not-run
        # (exit 3), never below-threshold (exit 1) — a broken environment must not
        # read as a bad description.
        return {"ran": False, "reason": "run_eval.py reported zero queries (empty or degenerate eval run)"}
    accuracy = passed / total
    below = accuracy < accuracy_threshold
    failed = [
        {"query": r.get("query"), "trigger_rate": r.get("trigger_rate"),
         "should_trigger": r.get("should_trigger")}
        for r in out.get("results", []) if not r.get("pass", False)
    ]
    return {
        "ran": True,
        "accuracy": round(accuracy, 4),
        "passed": passed,
        "total": total,
        "accuracy_threshold": accuracy_threshold,
        "trigger_threshold": trigger_threshold,
        "below_threshold": below,
        "failed_queries": failed,
    }


# ── main ────────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="skill-publisher description-triggering signal")
    ap.add_argument("skill_path", help="skill directory or path to SKILL.md")
    ap.add_argument("--run-eval", action="store_true",
                    help="also measure trigger accuracy via skill-creator-ccvw's run_eval.py (slow; requires --eval-set)")
    ap.add_argument("--eval-set", default=None,
                    help="path to the {query, should_trigger} query set (required with --run-eval)")
    ap.add_argument("--accuracy-threshold", type=float, default=0.8,
                    help="aggregate pass-rate gate (passed/total); below → exit 1 (default 0.8)")
    ap.add_argument("--trigger-threshold", type=float, default=0.5,
                    help="per-query trigger-rate threshold passed through to run_eval.py (default 0.5)")
    ap.add_argument("--runs-per-query", type=int, default=3)
    ap.add_argument("--timeout", type=int, default=30)
    ap.add_argument("--num-workers", type=int, default=10)
    ap.add_argument("--model", default=None, help="model for claude -p (default: user's configured model)")
    ap.add_argument("--ccvw-dir", default=str(DEFAULT_CCVW),
                    help=f"skill-creator-ccvw install dir (default: {DEFAULT_CCVW})")
    ap.add_argument("--json", dest="json_out", action="store_true", help="emit JSON")
    args = ap.parse_args()

    p = Path(args.skill_path).expanduser()
    skill_md = p if p.name == "SKILL.md" else p / "SKILL.md"
    if not skill_md.is_file():
        print(f"ERROR: SKILL.md not found at {skill_md}", file=sys.stderr)
        return 2
    skill_root = skill_md.resolve().parent

    try:
        description = _fm_field(_fm_block(skill_md.read_text(encoding="utf-8")), "description") or ""
    except OSError as e:
        print(f"ERROR: cannot read {skill_md}: {e}", file=sys.stderr)
        return 2

    dq = description_quality(description)
    result = {"skill": str(skill_root), "description": description, "description_quality": dq}

    rc = 0
    if args.run_eval:
        if not args.eval_set:
            print("ERROR: --run-eval requires --eval-set <query-set.json>", file=sys.stderr)
            return 2
        te = run_triggering_eval(
            skill_root, Path(args.eval_set).expanduser(), Path(args.ccvw_dir).expanduser(),
            args.accuracy_threshold, args.trigger_threshold,
            args.runs_per_query, args.timeout, args.num_workers, args.model,
        )
        result["triggering_eval"] = te
        if not te["ran"]:
            rc = 3
        elif te["below_threshold"]:
            rc = 1

    if args.json_out:
        print(json.dumps(result, indent=2))
    else:
        print(_format_report(result))
    return rc


def _format_report(result: dict) -> str:
    dq = result["description_quality"]
    lines = [
        f"Triggering signal: {Path(result['skill']).name}",
        "─" * 60,
        f"  negative-trigger boundary : {'yes' if dq['boundary_present'] else 'NO'}",
        f"  WHEN signal               : {'yes' if dq['has_when'] else 'NO'}",
        f"  length                    : {dq['length']} ({'ok' if dq['length_ok'] else 'OVER'})",
        f"  description confidence    : {dq['confidence'].upper()}",
    ]
    for n in dq["notes"]:
        lines.append(f"    · {n}")
    te = result.get("triggering_eval")
    if te is not None:
        lines.append("─" * 60)
        if not te["ran"]:
            lines.append(f"  triggering eval           : could not run — {te['reason']}")
        else:
            lines.append(f"  triggering accuracy       : {te['accuracy']:.0%} "
                         f"({te['passed']}/{te['total']}, threshold {te['accuracy_threshold']:.0%}) "
                         f"— {'BELOW THRESHOLD' if te['below_threshold'] else 'ok'}")
            for f in te["failed_queries"][:5]:
                rate = f["trigger_rate"]
                rate_s = f"{rate:.0%}" if isinstance(rate, (int, float)) else "?"
                lines.append(f"    · failed (rate {rate_s}, should_trigger={f['should_trigger']}): {str(f['query'])[:60]}")
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
