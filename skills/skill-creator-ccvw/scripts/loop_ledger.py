#!/usr/bin/env python3
"""Ledger and stopping rule for loop-until-dry (evaluate and improve until a pass finds nothing new).

Commands, all on --ledger FILE (JSON):
  record --round N --findings FILE   FILE is a JSON array of {"text": ..., "where": ..., "id": optional}.
                                     Adds the round, then prints the decision.
  decide                             Prints the decision for the rounds recorded so far.
  resolve --round N --ids a,b        Marks finding ids fixed in round N (they count as resolved).
Optional on every command: --cap N sets the round cap stored in the ledger (default 3).
Every command, decide included, writes the ledger file, so decide on a missing path creates an empty
ledger there. A round that reported nothing is recorded with a findings file holding []. The round's
designated likely-to-fail assertion is reported by the caller but is not put in the findings file, so it
never blocks clean_pass (SKILL.md "Loop-until-dry (opt-in)").

Stable ids: id = first 8 hex of sha1(lowercased "where|text" with whitespace collapsed) unless given,
so the same finding seen in two rounds keeps one id. A finding that was resolved and then reported
again is marked "regressed" (counted as new work). Decision JSON:
  {"stop": bool, "reason": "clean_pass"|"cap"|"no_progress"|null, "round": N,
   "new": [...], "regressed": [...], "open": [...], "resolved": [...]}
Stopping rule, checked in this order after each round: a round that reports no findings ->
clean_pass (findings still open from earlier rounds do not block it); number of rounds recorded
in the ledger >= cap (default 3; the --round values are not compared, so a ledger numbered from 1
stops after round 3) -> cap; two consecutive rounds whose open set is identical and non-empty
with nothing new or regressed -> no_progress.
The decision printed by `record` for the round just recorded governs whether another round starts;
the one `resolve` prints reflects the state after that round's fixes (resolving can empty the open
set, which hides a no_progress stop) and never overrides a stop printed by `record`.
When a ledger counts as finished, and what a resumed executor does: SKILL.md "Loop-until-dry (opt-in)".
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

CAP = 3


def finding_id(f):
    if f.get("id"):
        return str(f["id"])
    key = re.sub(r"\s+", " ", f"{f.get('where', '')}|{f.get('text', '')}".lower()).strip()
    # Not security-relevant: an 8-character stable label for a finding, never an integrity or auth check.
    return hashlib.sha1(key.encode()).hexdigest()[:8]


def load(path):
    p = Path(path)
    if p.is_file():
        return json.loads(p.read_text())
    return {"cap": CAP, "rounds": []}


def replay(led):
    """Return per-round new/regressed ids and the open set after each round."""
    state, history = {}, []
    for r in led["rounds"]:
        new, regressed = [], []
        reported = {finding_id(f) for f in r["findings"]}
        for fid in reported:
            if fid not in state:
                new.append(fid)
            elif state[fid] == "resolved":
                regressed.append(fid)
            state[fid] = "open"
        resolved_now = [i for i in r.get("resolved", []) if i in state]
        for i in resolved_now:
            state[i] = "resolved"
        history.append({"new": sorted(new), "regressed": sorted(regressed),
                        "open": sorted(i for i, s in state.items() if s == "open"),
                        "resolved": sorted(i for i, s in state.items() if s == "resolved")})
    return history


def decide(led):
    hist = replay(led)
    if not hist:
        return {"stop": False, "reason": None, "round": 0, "new": [], "regressed": [], "open": [], "resolved": []}
    last, n = hist[-1], len(hist)
    reported_last = {finding_id(f) for f in led["rounds"][-1]["findings"]}
    reason = None
    if not last["new"] and not last["regressed"] and not reported_last:
        reason = "clean_pass"
    elif n >= led.get("cap", CAP):
        reason = "cap"
    elif n >= 2 and hist[-2]["open"] == last["open"] and last["open"] and not last["new"] and not last["regressed"]:
        reason = "no_progress"
    return {"stop": reason is not None, "reason": reason, "round": n, **last}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["record", "decide", "resolve"])
    ap.add_argument("--ledger", required=True)
    ap.add_argument("--round", type=int)
    ap.add_argument("--findings")
    ap.add_argument("--ids")
    ap.add_argument("--cap", type=int)
    a = ap.parse_args(argv)
    led = load(a.ledger)
    if a.cap:
        led["cap"] = a.cap
    if a.command == "record":
        if a.round is None or not a.findings:
            ap.error("record needs --round and --findings")
        if any(r["round"] == a.round for r in led["rounds"]):
            print(f"round {a.round} already recorded", file=sys.stderr)
            return 1
        findings = json.loads(Path(a.findings).read_text())
        if not isinstance(findings, list):
            print("findings file must be a JSON array", file=sys.stderr)
            return 1
        led["rounds"].append({"round": a.round, "findings": findings, "resolved": []})
    elif a.command == "resolve":
        rnd = next((r for r in led["rounds"] if r["round"] == a.round), None)
        if rnd is None or not a.ids:
            print("resolve needs an existing --round and --ids", file=sys.stderr)
            return 1
        rnd["resolved"] = sorted(set(rnd["resolved"]) | set(a.ids.split(",")))
    Path(a.ledger).write_text(json.dumps(led, indent=2) + "\n")
    print(json.dumps(decide(led), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
