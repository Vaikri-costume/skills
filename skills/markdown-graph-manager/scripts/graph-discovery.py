#!/usr/bin/env python3
"""
graph-discovery.py — resolve which graph root to operate on, from a registry file.
Never guesses: a path not in the registry is a signal the registry (and the memory
it derives from) needs updating, not license to proceed.

Usage:
  graph-discovery.py REGISTRY --list             # print all live graphs (validated)
  graph-discovery.py REGISTRY --resolve PATH     # validate a candidate graph root

REGISTRY is a JSON file: {"live": [{"id","name","root","pages_dir","schema_config"}...],
"dead": ["path", ...]}. Dead paths are HARD-REJECTED even when passed explicitly —
a retired graph folder looks exactly like a live one.

Exit codes: 0 = ok; 1 = rejected (dead path); 2 = unknown (not in registry);
3 = registry/structure problem. Output is JSON on stdout. Pure stdlib.
"""
import argparse, json, os, sys

ap = argparse.ArgumentParser()
ap.add_argument("registry", help="path to graph registry JSON")
ap.add_argument("--list", action="store_true", help="list live graphs with validation status")
ap.add_argument("--resolve", metavar="PATH", help="validate a candidate graph root")
args = ap.parse_args()

REG = json.load(open(args.registry, encoding="utf-8"))

def norm(p):
    return os.path.normcase(os.path.realpath(os.path.expanduser(p)))

DEAD = [norm(p) for p in REG.get("dead", [])]

def is_dead(path):
    n = norm(path)
    return any(n == d or n.startswith(d + os.sep) for d in DEAD)

def validate(entry):
    root = os.path.expanduser(entry["root"])
    pages = os.path.normpath(os.path.join(root, entry.get("pages_dir", "pages")))
    out = dict(entry)
    out["root_resolved"] = root
    out["pages_resolved"] = pages
    out["root_exists"] = os.path.isdir(root)
    out["pages_exists"] = os.path.isdir(pages)
    out["dead"] = is_dead(root)
    out["ok"] = out["root_exists"] and out["pages_exists"] and not out["dead"]
    return out

if args.list:
    results = [validate(e) for e in REG.get("live", [])]
    print(json.dumps({"graphs": results}, indent=2))
    sys.exit(0 if all(r["ok"] for r in results) else 3)

if args.resolve:
    if is_dead(args.resolve):
        print(json.dumps({"path": args.resolve, "status": "rejected-dead",
                          "reason": "this path is registered as a DEAD graph — never operate on it, "
                                    "even when it is passed explicitly"}))
        sys.exit(1)
    n = norm(args.resolve)
    for e in REG.get("live", []):
        if norm(e["root"]) == n:
            v = validate(e)
            v["status"] = "ok" if v["ok"] else "registered-but-invalid"
            print(json.dumps(v, indent=2))
            sys.exit(0 if v["ok"] else 3)
    print(json.dumps({"path": args.resolve, "status": "unknown",
                      "reason": "not in the registry — update the registry (and the memory it derives "
                                "from) before operating on this graph; do not guess"}))
    sys.exit(2)

ap.error("pass --list or --resolve PATH")
