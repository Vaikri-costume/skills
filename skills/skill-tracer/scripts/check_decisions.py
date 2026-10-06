#!/usr/bin/env python3
"""check_decisions.py — check a fixer's decisions before fill-address records them.

Reads the final message of each fixer transcript (ledger_common.fixer_decisions) and reports every
decision with an empty address, an unknown decision word, an address whose kind prefix differs from
its decision, banned dismissal vocabulary (ledger_common.BANNED_PHRASES), a FIX without a complete
Closure block (a `closure` list holding one non-empty `Siblings:`, `Bound:`, `Claims:` and `Blocks:` line,
CLOSURE_LABELS; how-to-fix.md "Closure block"), a cluster decided twice, and, with --expect, a cluster
that is missing or was not given to this fixer. On any problem,
SendMessage the same fixer with the problems and ask it to re-emit, then check again.

Usage:
    check_decisions.py --fixer-transcript <path>[,<path>...] [--expect C1,C2,...]

Prints {"ok": bool, "decisions": N, "problems": [{"cluster", "problem", "detail"}]}.
Exit: 0 no problem; 1 a problem was found (including a final message that is not decisions JSON);
2 usage or an unreadable transcript.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ledger_common as lc  # noqa: E402

DECISION_KINDS = ("FIX", "STRENGTHEN", "ORCHESTRATOR-PAUSE")
CLOSURE_LABELS = ("Siblings", "Bound", "Claims", "Blocks")


def closure_gaps(closure) -> list:
    """The CLOSURE_LABELS that *closure* (a FIX's `closure` list of "Label: value" strings) lacks or
    leaves empty, in label order."""
    lines = closure if isinstance(closure, list) else []
    values = {}
    for line in lines:
        label, sep, value = str(line).partition(":")
        if sep and label.strip() in CLOSURE_LABELS:
            values[label.strip()] = values.get(label.strip(), "") + value.strip()
    return [lab for lab in CLOSURE_LABELS if not values.get(lab)]


def problems_in(decisions: list, expect: "list | None" = None) -> list:
    """Every problem in *decisions* as {"cluster", "problem", "detail"} (empty list when clean)."""
    out, seen = [], {}
    for d in decisions:
        if not isinstance(d, dict):
            out.append({"cluster": "", "problem": "not-an-object", "detail": repr(d)})
            continue
        cid, kind = str(d.get("cluster", "")), str(d.get("decision", "")).strip().upper()
        address = str(d.get("address") or "").strip()
        seen[cid] = seen.get(cid, 0) + 1
        if kind not in DECISION_KINDS:
            out.append({"cluster": cid, "problem": "bad-decision", "detail": f"decision {kind!r} is not one of {DECISION_KINDS}"})
        if not address:
            out.append({"cluster": cid, "problem": "empty-address", "detail": "address is empty"})
            continue
        prefix = next((k for k in lc.ADDRESS_KINDS if address.startswith(k + " ") or address.startswith(k + "(")), None)
        if kind in ("FIX", "STRENGTHEN") and prefix != kind:
            out.append({"cluster": cid, "problem": "wrong-kind-prefix",
                        "detail": f"a {kind} address must start with '{kind} (': {address[:80]!r}"})
        elif kind == "ORCHESTRATOR-PAUSE" and prefix not in (None, kind):
            out.append({"cluster": cid, "problem": "wrong-kind-prefix",
                        "detail": f"an ORCHESTRATOR-PAUSE address starts with {prefix}: {address[:80]!r}"})
        gaps = closure_gaps(d.get("closure")) if kind == "FIX" else []
        if gaps:
            out.append({"cluster": cid, "problem": "missing-closure",
                        "detail": f"a FIX needs a closure list with non-empty {', '.join(g + ':' for g in gaps)} line(s)"})
        for err in lc.reject_banned_vocabulary(f"address for {cid}", address):
            out.append({"cluster": cid, "problem": "banned-vocabulary", "detail": err.split(" -- ")[0]})
    out += [{"cluster": c, "problem": "duplicate-cluster", "detail": f"{n} decisions"} for c, n in seen.items() if n > 1]
    if expect is not None:
        out += [{"cluster": c, "problem": "missing-cluster", "detail": "no decision for this cluster"}
                for c in expect if c not in seen]
        out += [{"cluster": c, "problem": "unknown-cluster", "detail": "not one of this fixer's clusters"}
                for c in seen if c not in expect]
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Check fixer decisions before fill-address.")
    ap.add_argument("--fixer-transcript", action="append", required=True, metavar="PATH[,PATH...]",
                    help="Fixer transcript(s); repeat or give a comma list.")
    ap.add_argument("--expect", default=None, metavar="C1,C2",
                    help="The cluster ids these fixers were given (a batch's \"clusters\").")
    args = ap.parse_args()
    paths = [x.strip() for v in args.fixer_transcript for x in v.split(",") if x.strip()]
    decisions, problems = [], []
    for tp in paths:
        try:
            decisions += lc.fixer_decisions(tp)
        except ValueError as exc:
            problems.append({"cluster": "", "problem": "not-decisions-json", "detail": f"{tp}: {exc}"})
        except OSError as exc:
            print(json.dumps({"error": f"cannot read transcript {tp}: {exc}"}), file=sys.stderr)
            return 2
    expect = [c.strip() for c in args.expect.split(",") if c.strip()] if args.expect is not None else None
    problems += problems_in(decisions, expect)
    print(json.dumps({"ok": not problems, "decisions": len(decisions), "problems": problems}, indent=2))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
