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

It also closes a round: the `close-round` subcommand recomputes the round-summary comment (built in
cmd_close_round; ledger_common.SUMMARY_RE parses it back) FROM the actual rows on the ledger for that
round (not hand-counted); the separate
`verify-auditability` subcommand checks that every flag-ID appears in exactly one row of the round.

`close-round` also enforces the round-boundary precondition: a round only advances after a
genuine fix actually happened, mechanically checked (at least one FIX-kind row in the round being
closed), not left to the operator to track correctly. Pass --converged for a final close (nothing
more to fix by definition), or --strengthen-only "<reason>" when every finding this round was
a legitimate STRENGTHEN (references/how-to-fix.md "Choose STRENGTHEN when": missing WHY, list
closure marker, distant cross-reference pointer, verified edge-case branch), so no FIX row can
exist by design; the reason is the justification and must name which case applied.

The row regex, address/phase/cluster vocabulary, and parse helpers all come from
`ledger_common` (the single source of truth) — this script imports it rather than
re-hardcoding any of them, so a format change is made in exactly one place.

Pure-stdlib. Subcommands:
    begin-round — create the ledger if absent (recording `target:: <abs --target>` in its header),
                  write the round's first in-flight marker (`prepass running round-<N>`),
                  optionally persist run options (--set k=v); refuses (exit 2) a ledger whose
                  recorded target differs, and records --target on a legacy ledger that has none
    append   — validate + append one cluster row (rejects a cluster id the round already holds;
               the next free id is one above the round's highest C<n>)
    close-round — recompute + append the round-summary comment; refuses (exit 1) a round with
                  no FIX row (unless --converged / --strengthen-only), an open pause or a row still
                  PENDING. The gates run before the summary check, so a re-close of a round with no
                  FIX row is refused unless it passes --converged / --strengthen-only again; a
                  re-close that passes the gates appends no second summary comment (--converged
                  still rewrites the converged marker)
    verify-auditability — assert every flag-ID in a round appears exactly once
    check-pauses — exit 1 while any ORCHESTRATOR-PAUSE / USER-PAUSE row is unresolved
    options  — read/merge the persisted run options line (survives compaction)
    gate     — mechanical stop rule (hard round cap, --rounds budget, stall) after a closed round

Usage:
    append_ledger.py begin-round <ledger> --round N --runtime R --target <abs target> [--set rounds-budget=N --set max-rounds=N ...]
    append_ledger.py append <ledger> --runtime R --round N --phase TRACE \\
        --cluster C1 --root-cause "..." --address "FIX (file: ...)" --flags "G11,G23,P4" \\
        --blast-radius-status "clean: token X, 3 files, all touched"  # required for a FIX row
    append_ledger.py close-round <ledger> --round N  # requires a FIX row this round, or --converged / --strengthen-only "<reason>"; no PENDING row, no open pause
        # output carries a `gate` object (also on a re-close); exit 0 either way, the gate says whether to continue
    append_ledger.py verify-auditability <ledger> --round N --expect "G11,G12,G21,P1"
    append_ledger.py check-pauses <ledger>  # exit 1 = an open pause (listed in the JSON); 2 = ledger not found
    append_ledger.py options <ledger> [--set rounds-budget=N --set max-rounds=N ...]  # prints {"run_options": ...}; no --set = read only
    append_ledger.py gate <ledger> --round N  # exit 0 = continue, 1 = stop (round cap, budget or stall); 2 = ledger not found

Exit: 0 ok; 1 validation/auditability failure; 2 usage / ledger-not-found / begin-round on a
ledger that records a different target.
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path

import ledger_common as lc


def _read(ledger: Path) -> str:
    return ledger.read_text(encoding="utf-8")


def _append_line(ledger: Path, line: str) -> None:
    text = _read(ledger)
    if not text.endswith("\n"):
        text += "\n"
    ledger.write_text(text + line + "\n", encoding="utf-8")


def cmd_append(args) -> int:
    ledger = Path(args.ledger).expanduser()
    if not ledger.is_file():
        print(f"ERROR: ledger not found: {ledger}", file=sys.stderr)
        return 2

    # Validate the free-text cells that flow into the pipe-delimited row.
    errs = []
    for fname, val in (("root-cause", args.root_cause), ("address", args.address), ("flags", args.flags)):
        errs.extend(lc.reject_unsafe(fname, val))
    # Address only, as in ledger_cascade.py: a root-cause cell is quoted from the target's own text.
    errs.extend(lc.reject_banned_vocabulary("address", args.address))
    # Address kind: must begin with a known kind at a TOKEN BOUNDARY (rejects bare `FIX`,
    # `FIXED…`, `STRENGTHENING`) — the address formats are in references/how-to-fix.md "Address column formats".
    if not lc.address_kind_ok(args.address):
        errs.append(f"address must start with one of {lc.ADDRESS_KINDS} at a token boundary "
                    f"(kind followed by a space or '('): {args.address!r}")
    # Blast-radius precondition: the mandatory blast-radius check was already built (check_fix_radius.py) but was skipped for a full round
    # because invoking it was only a manually-remembered fixer step, not a hard precondition. This
    # script can't re-run check_fix_radius.py itself (it needs --token/--touched the caller alone
    # knows), so it requires the caller to state the result explicitly -- a FIX row cannot be
    # recorded without it.
    if lc.address_base_kind(args.address) == "FIX" and not args.blast_radius_status:
        errs.append(
            "a FIX row requires --blast-radius-status, stating what check_fix_radius.py found "
            "(e.g. 'clean: token X, 3 files, all touched' or 'n/a: single-site change, no shared "
            "token') -- the blast-radius check must actually run before a fix is recorded, not be "
            "left to the fixer to remember."
        )
    # Phase: must be a write-allowed phase. PORT-AUDIT is read-tolerated in old ledgers but
    # write-forbidden here (it belongs to skill-publisher).
    if args.phase not in lc.KNOWN_PHASES:
        errs.append(f"--phase must be one of {lc.KNOWN_PHASES} (SIMPLIFY/PORT-AUDIT are write-forbidden here — skill-publisher's): {args.phase!r}")
    # A pause-resolving row carries no flag ids: the pause row already holds them (unresolved_pauses matches
    # on the Address text), so repeating them would double-count each flag in the round's raw-flag total
    # (which the stall rule reads) and in verify-auditability.
    if args.flags.strip() and ("resolves ORCHESTRATOR-PAUSE" in args.address or "resolves USER-PAUSE" in args.address):
        errs.append("a row whose address says 'resolves ORCHESTRATOR-PAUSE|USER-PAUSE' must pass --flags \"\" "
                    "(the pause row already holds the flag ids)")
    # Cluster: must match the C<n> grammar ROW_RE keys on, else the written row is unparseable on read-back.
    if not lc.CLUSTER_RE.match(args.cluster):
        errs.append(f"--cluster must match ^C\\d+$ (e.g. C1, C2): {args.cluster!r}")
    # Cluster ids are unique per round: every writer numbers max+1 (lc.max_cluster_in_round) and
    # fill-address matches a PENDING row by (round, cluster), so a reused id would make two rows
    # answer to one key. The next free id is always one above the round's highest.
    elif any(r["cluster"] == args.cluster for r in lc.round_rows(_read(ledger), args.round)):
        nxt = lc.max_cluster_in_round(ledger, args.round) + 1
        errs.append(f"--cluster {args.cluster} is already used in round {args.round}; "
                    f"the next free id is C{nxt}")
    if errs:
        for e in errs:
            print(f"REJECTED: {e}", file=sys.stderr)
        return 1

    address = args.address
    if args.blast_radius_status:
        address = f"{address} [blast-radius: {args.blast_radius_status}]"
        # Re-check the composed address stays free of the two hazards lc.reject_unsafe guards —
        # a status string could itself smuggle in a '|' or newline.
        composed_errs = lc.reject_unsafe("address", address)
        if composed_errs:
            for e in composed_errs:
                print(f"REJECTED: {e}", file=sys.stderr)
            return 1

    row = lc.format_row(args.runtime, args.round, args.phase, args.cluster, args.root_cause, address, args.flags)
    _append_line(ledger, row)
    print(json.dumps({"appended": row, "ledger": str(ledger)}, indent=2))
    return 0


def _tally(rows: list[dict]) -> dict:
    raw_flags = sum(len(r["flags"]) for r in rows)
    clusters = len(rows)
    # Count by the canonical base kind (folds would- forms, uses the same token-boundary rule as the writer).
    bases = [lc.address_base_kind(r["address"]) for r in rows]
    fix = sum(1 for b in bases if b == "FIX")
    strg = sum(1 for b in bases if b == "STRENGTHEN")
    pause = sum(1 for b in bases if b == "USER-PAUSE")
    # Count ORCHESTRATOR-PAUSE rows directly (not folded into _BASE_KINDS / address_base_kind).
    orch_pause = sum(
        1 for r in rows
        if r["address"].strip().startswith("ORCHESTRATOR-PAUSE ") or r["address"].strip().startswith("ORCHESTRATOR-PAUSE(")
    )
    return {"raw_flags": raw_flags, "clusters": clusters, "fix": fix, "strengthen": strg,
            "orch_pause": orch_pause, "user_pause": pause}


def _round_already_closed(text: str, rnd: int) -> bool:
    return any(int(m.group(1)) == rnd for m in lc.SUMMARY_RE.finditer(text))


def cmd_close_round(args) -> int:
    ledger = Path(args.ledger).expanduser()
    if not ledger.is_file():
        print(f"ERROR: ledger not found: {ledger}", file=sys.stderr)
        return 2
    text = _read(ledger)

    # GATE: a round only advances after a genuine fix -- the executor once repeatedly
    # re-entered prepass under the same round label because nothing checked this mechanically.
    # Skipped for a --converged close (nothing more to fix by definition) or an explicit
    # --strengthen-only justification (every finding this round was a legitimate
    # STRENGTHEN per references/how-to-fix.md, so no FIX row can exist by design).
    if not args.converged and not args.strengthen_only:
        rows = lc.round_rows(text, args.round)
        has_fix = any(lc.address_base_kind(r["address"]) == "FIX" for r in rows)
        if not has_fix:
            print(json.dumps(
                {"error": (
                    f"cannot close round {args.round}: no FIX-kind row found in this round. "
                    "A round only advances after a genuine fix. If every finding this round "
                    "was a legitimate STRENGTHEN (references/how-to-fix.md 'Choose STRENGTHEN "
                    "when'), rerun with --strengthen-only \"<reason naming the case>\". "
                    "If this is the final round, rerun with --converged."
                )},
                indent=2
            ), file=sys.stderr)
            return 1

    # GATE: refuse to close if this round has unresolved ORCHESTRATOR-PAUSE or USER-PAUSE rows.
    all_open = lc.unresolved_pauses(text)
    open_this_round = [p for p in all_open if p["round"] == args.round]
    if open_this_round:
        print(json.dumps(
            {"error": f"cannot close round {args.round}: unresolved pauses",
             "open_pauses": open_this_round},
            indent=2
        ), file=sys.stderr)
        return 1

    # GATE: refuse to close while any row of this round is still PENDING. A PENDING row is a
    # finding with no FIX / STRENGTHEN / ORCHESTRATOR-PAUSE address yet (the fix-recording step was
    # skipped), so closing over it would drop that finding (the No-orphan-flag invariant).
    rows = lc.round_rows(text, args.round)
    pending = [{"cluster": r["cluster"], "phase": r["phase"], "flags": r["flags"]}
               for r in rows if lc.is_pending(r["address"])]
    if pending:
        print(json.dumps(
            {"error": (f"cannot close round {args.round}: {len(pending)} row(s) still PENDING. Record "
                       "the fixer's decisions with the fix-recording step (ledger_cascade.py --mode "
                       "fill-address --phase <phase>) first."),
             "pending_rows": pending},
            indent=2
        ), file=sys.stderr)
        return 1

    t = _tally(rows)
    comment = (f"<!-- Round {args.round} total: raw flags {t['raw_flags']} — clusters {t['clusters']} — "
               f"addresses: {t['fix']} FIX + {t['strengthen']} STRENGTHEN + "
               f"{t['orch_pause']} ORCHESTRATOR-PAUSE + {t['user_pause']} USER-PAUSE -->")
    # Never write a second summary comment for a round that already has one: a re-close that got
    # past the gates above must not double-count in aggregation.
    already_closed = _round_already_closed(text, args.round)
    if not already_closed:
        _append_line(ledger, comment)
    out = {"round": args.round, "summary": comment, "already_closed": already_closed, **t}
    if args.converged:
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        lc.write_marker(ledger, f"{stamp} converged round-{args.round}")
        out["converged_marker"] = f"{stamp} converged round-{args.round}"
    # The gate is attached on BOTH paths: a re-close that got past the gates above still gives the
    # stop signal (round-cap / budget-exhausted / stalled), never silently omits it.
    out["gate"] = lc.round_gate(_read(ledger), args.round)
    print(json.dumps(out, indent=2))
    return 0


def _parse_sets(pairs):
    """[ 'k=v', ... ] -> ({k: v}, error-or-None)."""
    updates = {}
    for kv in pairs or []:
        if "=" not in kv:
            return None, f"--set expects key=value, got {kv!r}"
        k, v = kv.split("=", 1)
        updates[k] = v
    return updates, None


def cmd_begin_round(args) -> int:
    """Start round N: create the ledger when absent, write the round's first in-flight marker and
    optionally persist run options. The marker is script-owned (recovery.md: scripts advance the
    marker, never hand-set), and creating the ledger here is what lets a fresh run persist
    `rounds-budget` BEFORE round 1's first fix. Idempotent: a live marker already naming this round
    is left alone (a recovery re-run must not rewind a later phase).

    Ledger identity: the new ledger's header records `target:: <absolute --target>`. An existing
    ledger recording a different target is refused (exit 2, nothing written); a legacy ledger with
    no recorded target records the --target of this first call."""
    ledger = Path(args.ledger).expanduser()
    updates, err = _parse_sets(args.set)
    if not err:
        # Validate before the ledger is created or its marker moved, so a bad --set changes nothing.
        try:
            lc.validate_run_options(updates)
        except ValueError as e:
            err = str(e)
    if err:
        print(f"ERROR: {err}", file=sys.stderr)
        return 2
    target = str(Path(args.target).expanduser().resolve())
    marker = f"{args.runtime} prepass running round-{args.round}"
    created = already_started = target_recorded = False
    if not ledger.is_file():
        ledger.parent.mkdir(parents=True, exist_ok=True)
        ledger.write_text(lc.ledger_header(ledger.stem, marker, target), encoding="utf-8")
        created = True
    else:
        text = _read(ledger)
        # Ledger identity: <ledger> is named from the target's basename only, so a second target with
        # the same directory name would otherwise share this ledger.
        recorded = lc.ledger_target(text)
        if recorded is not None and recorded != target:
            print(f"ERROR: {ledger} belongs to target {recorded}, not {target} (two targets share the "
                  f"basename {ledger.stem!r}); nothing was written. Use a ledger path of its own for "
                  f"this target.", file=sys.stderr)
            return 2
        if _round_already_closed(text, args.round):
            print(f"ERROR: round {args.round} is already closed in {ledger}; begin the next round.", file=sys.stderr)
            return 1
        if recorded is None:
            # Legacy ledger written before the target:: line existed: adopt the first target given.
            lc.write_ledger_target(ledger, target)
            target_recorded = True
            text = _read(ledger)
        cur = lc.parse_in_flight(text)
        if cur and cur.get("phase") is not None and cur.get("round") == args.round:
            already_started = True
            marker = cur["raw"]
        else:
            lc.write_marker(ledger, marker)
    try:
        opts = lc.write_run_options(ledger, updates) if updates else lc.parse_run_options(_read(ledger))
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    print(json.dumps({"ledger": str(ledger), "round": args.round, "in_flight_marker": f"in-flight:: {marker}",
                      "created": created, "already_started": already_started, "target": target,
                      "target_recorded": target_recorded, "run_options": opts}, indent=2))
    return 0


def cmd_options(args) -> int:
    """Read (no --set) or merge (--set key=value ...) the ledger's run-options:: line."""
    ledger = Path(args.ledger).expanduser()
    if not ledger.is_file():
        print(f"ERROR: ledger not found: {ledger} (a fresh run creates it with `begin-round`, "
              f"which also accepts --set k=v)", file=sys.stderr)
        return 2
    updates, err = _parse_sets(args.set)
    if err:
        print(f"ERROR: {err}", file=sys.stderr)
        return 2
    try:
        opts = lc.write_run_options(ledger, updates) if updates else lc.parse_run_options(_read(ledger))
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    print(json.dumps({"run_options": opts}, indent=2))
    return 0


def cmd_gate(args) -> int:
    """Evaluate the round gate for a closed round. Exit 0 = continue, 1 = stop (not converged)."""
    ledger = Path(args.ledger).expanduser()
    if not ledger.is_file():
        print(f"ERROR: ledger not found: {ledger}", file=sys.stderr)
        return 2
    g = lc.round_gate(_read(ledger), args.round)
    print(json.dumps(g, indent=2))
    return 0 if g["continue"] else 1


def cmd_verify_auditability(args) -> int:
    ledger = Path(args.ledger).expanduser()
    if not ledger.is_file():
        print(f"ERROR: ledger not found: {ledger}", file=sys.stderr)
        return 2
    rows = lc.round_rows(_read(ledger), args.round)
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


def cmd_check_pauses(args) -> int:
    """Exit 1 if any unresolved ORCHESTRATOR-PAUSE or USER-PAUSE exists in the ledger —
    the machine guard the handoff / convergence / done paths run so they cannot proceed
    over an open orchestrator or user decision."""
    ledger = Path(args.ledger).expanduser()
    if not ledger.is_file():
        print(f"ERROR: ledger not found: {ledger}", file=sys.stderr)
        return 2
    open_pauses = lc.unresolved_pauses(_read(ledger))
    print(json.dumps({"unresolved_pauses": open_pauses, "count": len(open_pauses)}, indent=2))
    return 1 if open_pauses else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="skill-tracer ledger row writer/validator")
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("begin-round", help="create the ledger if absent and write the round's first marker (script-owned)")
    b.add_argument("ledger")
    b.add_argument("--round", type=int, required=True)
    b.add_argument("--runtime", required=True)
    b.add_argument("--target", required=True, help="absolute path of the audited target; recorded on the ledger's target:: line, and a ledger recording a different target is refused (exit 2)")
    b.add_argument("--set", action="append", metavar="KEY=VALUE", help="persist run options (rounds-budget, max-rounds, run-start-round)")
    b.set_defaults(func=cmd_begin_round)

    a = sub.add_parser("append")
    a.add_argument("ledger")
    a.add_argument("--runtime", required=True)
    a.add_argument("--round", type=int, required=True)
    a.add_argument("--phase", default="TRACE")
    a.add_argument("--cluster", required=True)
    a.add_argument("--root-cause", required=True)
    a.add_argument("--address", required=True)
    a.add_argument("--flags", required=True)
    a.add_argument("--blast-radius-status", default="", help="required for a FIX row: what check_fix_radius.py found (e.g. 'clean: token X, 3 files, all touched' or 'n/a: single-site change')")
    a.set_defaults(func=cmd_append)

    c = sub.add_parser("close-round")
    c.add_argument("ledger")
    c.add_argument("--round", type=int, required=True)
    c.add_argument("--converged", action="store_true", default=False)
    c.add_argument("--strengthen-only", default="", help="justification for closing a round with no FIX row: every finding was a legitimate STRENGTHEN (name the how-to-fix.md case)")
    c.set_defaults(func=cmd_close_round)

    v = sub.add_parser("verify-auditability")
    v.add_argument("ledger")
    v.add_argument("--round", type=int, required=True)
    v.add_argument("--expect", default=None, help="comma-separated flag-IDs expected this round")
    v.set_defaults(func=cmd_verify_auditability)

    o = sub.add_parser("options", help="read or set the persisted run options (rounds-budget, max-rounds, run-start-round)")
    o.add_argument("ledger")
    o.add_argument("--set", action="append", metavar="KEY=VALUE")
    o.set_defaults(func=cmd_options)

    g = sub.add_parser("gate", help="mechanical stop rule after a closed round: exit 1 = stop (round cap, budget or stall)")
    g.add_argument("ledger")
    g.add_argument("--round", type=int, required=True)
    g.set_defaults(func=cmd_gate)

    cp = sub.add_parser("check-pauses")
    cp.add_argument("ledger")
    cp.set_defaults(func=cmd_check_pauses)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
