#!/usr/bin/env python3
"""Ledger row writer/validator + round-summary closer for skill-tracer.

The audit ledger is a 7-column markdown table:
    | Runtime | Round | Phase | Cluster | Root cause | Address | Flags |
`scripts/render_ledger.py` parses it by splitting on `|` and EXITS table-parsing
on any blank line. So two characters silently corrupt the ledger if hand-typed:
  - a literal `|` in any cell  -> that row is silently dropped by the renderer
  - an embedded newline (multi-line cell) -> the table is silently truncated there
Hand-writing rows every round is exactly the kind of deterministic-but-fragile
work a script should own. This script VALIDATES (rejects `|`/newlines with a
non-zero exit instead of letting the renderer drop the row), formats, and appends.

It also closes a round: the `close-round` subcommand recomputes the round-summary comment
    <!-- Round N total: raw flags A — clusters M — addresses: F FIX + S STRENGTHEN + P USER-PAUSE -->
FROM the actual rows on the ledger for that round (not hand-counted), and can
--verify-auditability (every flag-ID appears in exactly one row of the round).

Pure-stdlib. Subcommands:
    append   — validate + append one cluster row
    close-round — recompute + append the round-summary comment
    verify-auditability — assert every flag-ID in a round appears exactly once

Usage:
    append_ledger.py append <ledger> --runtime R --round N --phase TRACE \\
        --cluster C1 --root-cause "..." --address "FIX (file: ...)" --flags "F1,B3,E5"
    append_ledger.py close-round <ledger> --round N
    append_ledger.py verify-auditability <ledger> --round N --expect "F1,F2,B1,E3"

Exit: 0 ok; 1 validation/auditability failure; 2 usage / ledger-not-found.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ledger_common as lc  # noqa: E402  (single source of truth for the ledger format/vocab/parse)


def _reject_unsafe(field_name: str, value: str) -> list[str]:
    errs = []
    if "|" in value:
        errs.append(f"{field_name} contains a literal '|' (renderer splits on it -> row silently dropped). "
                    f"Use 'or' / 'vs.' / a dash instead: {value!r}")
    if "\n" in value or "\r" in value:
        errs.append(f"{field_name} contains an embedded newline (renderer exits the table -> truncation). "
                    f"Keep it single-line: {value!r}")
    return errs


def cmd_append(args) -> int:
    ledger = Path(args.ledger).expanduser()
    if not ledger.is_file():
        print(f"ERROR: ledger not found: {ledger}", file=sys.stderr)
        return 2

    # Validate the free-text cells that flow into the pipe-delimited row.
    errs = []
    for fname, val in (("root-cause", args.root_cause), ("address", args.address), ("flags", args.flags)):
        errs.extend(_reject_unsafe(fname, val))
    # Address sanity: should start with a known kind at a token boundary (cheap guard against malformed addresses).
    if not lc.address_kind_ok(args.address):
        errs.append(f"address should start with one of {lc.ADDRESS_KINDS} (at a token boundary): {args.address!r}")
    # Phase sanity: reject an out-of-set phase (typo guard) — render_ledger.py would silently fallback-color it.
    if args.phase not in lc.KNOWN_PHASES:
        errs.append(f"phase should be one of {lc.KNOWN_PHASES}: {args.phase!r}")
    # Cluster sanity: render_ledger.py requires the Cluster cell match `^C\d+$` and silently drops a row that
    # doesn't (so a typo like `c1`/`Cluster1` would append fine but vanish from the render + the renderer's
    # count). Reject it here so the typo fails loudly at write time, matching the renderer's acceptance set.
    if not lc.CLUSTER_RE.match(args.cluster):
        errs.append(f"cluster must match ^C\\d+$ (e.g. C1): {args.cluster!r}")
    if errs:
        for e in errs:
            print(f"REJECTED: {e}", file=sys.stderr)
        return 1

    row = f"| {args.runtime} | {args.round} | {args.phase} | {args.cluster} | {args.root_cause} | {args.address} | {args.flags} |"
    text = ledger.read_text(encoding="utf-8")
    if not text.endswith("\n"):
        text += "\n"
    ledger.write_text(text + row + "\n", encoding="utf-8")
    print(json.dumps({"appended": row, "ledger": str(ledger)}, indent=2))
    return 0


def _round_rows(ledger: Path, rnd: int) -> list[dict]:
    return lc.round_rows(ledger.read_text(encoding="utf-8"), rnd)


def _tally(rows: list[dict]) -> dict:
    raw_flags = sum(len(r["flags"]) for r in rows)
    clusters = len(rows)
    counts = {"fix": 0, "strengthen": 0, "user_pause": 0}
    for r in rows:
        base = lc.address_base_kind(r["address"])
        if base == "FIX":
            counts["fix"] += 1
        elif base == "STRENGTHEN":
            counts["strengthen"] += 1
        elif base == "USER-PAUSE":
            counts["user_pause"] += 1
    return {"raw_flags": raw_flags, "clusters": clusters,
            "fix": counts["fix"], "strengthen": counts["strengthen"], "user_pause": counts["user_pause"]}


def cmd_close_round(args) -> int:
    ledger = Path(args.ledger).expanduser()
    if not ledger.is_file():
        print(f"ERROR: ledger not found: {ledger}", file=sys.stderr)
        return 2
    text = ledger.read_text(encoding="utf-8")  # read once (H1): derive rows from this text, no second read
    rows = lc.round_rows(text, args.round)
    t = _tally(rows)
    comment = (f"<!-- Round {args.round} total: raw flags {t['raw_flags']} — clusters {t['clusters']} — "
               f"addresses: {t['fix']} FIX + {t['strengthen']} STRENGTHEN + {t['user_pause']} USER-PAUSE -->")
    # Idempotency (review-finding 2): close-round runs "once per round", but a rule-2 mid-addressing resume or an
    # accidental double-invocation must not append a SECOND summary for this round (a stale duplicate
    # would mask the clean/not-clean signal ledger_state.py reads). Replace an existing Round-N summary
    # in place; only append when none exists yet.
    existing_re = re.compile(rf"^<!--\s*Round\s+{re.escape(str(args.round))}\s+total:.*?-->[ \t]*$", re.MULTILINE)
    if existing_re.search(text):
        text = existing_re.sub(lambda _m: comment, text, count=1)
        ledger.write_text(text, encoding="utf-8")
    else:
        if not text.endswith("\n"):
            text += "\n"
        ledger.write_text(text + comment + "\n", encoding="utf-8")
    print(json.dumps({"round": args.round, "summary": comment, **t}, indent=2))
    return 0


def cmd_verify_auditability(args) -> int:
    ledger = Path(args.ledger).expanduser()
    if not ledger.is_file():
        print(f"ERROR: ledger not found: {ledger}", file=sys.stderr)
        return 2
    rows = _round_rows(ledger, args.round)
    seen = {}
    for r in rows:
        for f in r["flags"]:
            seen[f] = seen.get(f, 0) + 1
    dupes = {f: c for f, c in seen.items() if c > 1}
    result = {"round": args.round, "flags_seen": sorted(seen), "duplicates": dupes}
    rc = 0
    if dupes:
        result["error"] = "flag-ID(s) appear in more than one row"
        rc = 1
    if args.expect:
        expected = {f.strip() for f in args.expect.split(",") if f.strip()}
        missing = sorted(expected - set(seen))
        extra = sorted(set(seen) - expected)
        result["missing_from_ledger"] = missing
        result["unexpected_in_ledger"] = extra
        if missing or extra:
            result["error"] = result.get("error", "") + " expected-set mismatch"
            rc = 1
    print(json.dumps(result, indent=2))
    return rc


def main() -> int:
    ap = argparse.ArgumentParser(description="skill-tracer ledger row writer/validator")
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("append")
    a.add_argument("ledger")
    a.add_argument("--runtime", required=True)
    a.add_argument("--round", type=int, required=True)
    a.add_argument("--phase", default="TRACE")
    a.add_argument("--cluster", required=True)
    a.add_argument("--root-cause", required=True)
    a.add_argument("--address", required=True)
    a.add_argument("--flags", required=True)
    a.set_defaults(func=cmd_append)

    c = sub.add_parser("close-round")
    c.add_argument("ledger")
    c.add_argument("--round", type=int, required=True)
    c.set_defaults(func=cmd_close_round)

    v = sub.add_parser("verify-auditability")
    v.add_argument("ledger")
    v.add_argument("--round", type=int, required=True)
    v.add_argument("--expect", default=None, help="comma-separated flag-IDs expected this round")
    v.set_defaults(func=cmd_verify_auditability)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
