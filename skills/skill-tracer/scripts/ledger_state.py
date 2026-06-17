#!/usr/bin/env python3
"""Read skill-tracer ledger state in one call: highest Round + in-flight marker.

Step 1 (the mandatory first action of every invocation, including post-compaction
resume) must determine two things from the ledger: the highest Round present
(round numbering is cumulative-per-skill) and the in-flight marker (which recovery
rule applies). Both are deterministic parses the orchestrator otherwise re-does by
hand every invocation — and the round-scan has an easy-to-miss edge case (the
round-summary HTML comments contain "Round N" and must NOT be counted).

This script does both parses and returns JSON, so Step 1 calls it instead of
hand-scanning. It does NOT select the recovery rule — that's the orchestrator's
judgment over the returned state (marker presence/keyword + clean-vs-not).

Handles the documented back-compat: pre-Phase-column ledgers have 6 columns
(Runtime|Round|Cluster|...) instead of 7 (Runtime|Round|Phase|Cluster|...). The
row regex matches both by allowing an optional Phase column.

Pure-stdlib.

Usage:  ledger_state.py <ledger-path>
        (a missing/empty ledger is valid — returns highest_round 0, no marker)

Output JSON:
    {
      "ledger": "<path>", "exists": <bool>,
      "highest_round": <int>,             # 0 if no data rows
      "next_fresh_round": <int>,          # highest_round + 1
      "in_flight": {                      # null if no marker
          "raw": "...", "runtime": "...", "action": "dispatch|addressing|handoff|<unknown>",
          "round": <int>, "action_valid": <bool>
      } | null,
      "last_round_clean": <bool|null>,    # phase-aware: true iff the highest (closed) round has zero TRACE-phase rows (cold trace clean); REVIEW (CR*) rows don't count; null if that round has no summary (didn't close)
      "row_count": <int>
    }

Exit: 0 ok (incl. absent ledger); 2 path is a directory / unreadable.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ledger_common as lc  # noqa: E402  (single source of truth for the ledger format/vocab/parse)


def parse(text: str) -> dict:
    highest = 0
    row_count = 0
    trace_rows = {}  # round -> count of TRACE-phase data rows (REVIEW/SIMPLIFY rows excluded)
    for line in text.splitlines():
        row = lc.parse_row(line)
        if row:
            row_count += 1
            r = row["round"]
            if r > highest:
                highest = r
            if row["phase"] == "TRACE":
                trace_rows[r] = trace_rows.get(r, 0) + 1

    in_flight = lc.parse_in_flight(text)

    # last_round_clean is PHASE-AWARE: a round is "clean" (converged) when its cold trace returned
    # zero TRACE clusters — i.e. zero TRACE-phase rows — which matches Condition A. It must NOT key
    # on the summary's total raw-flag count, because a round-1 that converges WITH a code-review
    # phase carries REVIEW (CR*) rows, so its raw-flag count is > 0 even though the cold trace was
    # clean. Counting only TRACE rows fixes that mis-classification.
    best_round = -1
    for sm in lc.SUMMARY_RE.finditer(text):
        sr = int(sm.group(1))
        if sr >= best_round:
            best_round = sr
    # A converged round writes a summary but may have NO TRACE data rows (zero TRACE clusters), and
    # for round 1 only REVIEW rows. The summary round can exceed the highest data row.
    highest = max(highest, best_round if best_round >= 0 else 0)
    if best_round == highest and best_round >= 0:
        # highest round closed (has a summary) → clean iff it raised zero TRACE clusters.
        last_clean = (trace_rows.get(highest, 0) == 0)
    else:
        # highest round has data rows but no summary comment → didn't close → cleanliness unknown.
        last_clean = None

    return {
        "highest_round": highest,
        "next_fresh_round": highest + 1,
        "in_flight": in_flight,
        "last_round_clean": last_clean,
        "row_count": row_count,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="skill-tracer ledger state reader")
    ap.add_argument("ledger")
    args = ap.parse_args()
    p = Path(args.ledger).expanduser()

    if p.is_dir():
        print(f"ERROR: ledger path is a directory: {p}", file=sys.stderr)
        return 2
    if not p.exists():
        print(json.dumps({
            "ledger": str(p), "exists": False, "highest_round": 0, "next_fresh_round": 1,
            "in_flight": None, "last_round_clean": None, "row_count": 0,
        }, indent=2))
        return 0
    try:
        text = p.read_text(encoding="utf-8")
    except OSError as e:
        print(f"ERROR: cannot read ledger {p}: {e}", file=sys.stderr)
        return 2

    state = parse(text)
    state = {"ledger": str(p), "exists": True, **state}
    print(json.dumps(state, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
