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
      "last_round_clean": <bool|null>,    # from the round-summary comment 'raw flags 0'; null if unknown
      "row_count": <int>
    }

Exit: 0 ok (incl. absent ledger); 2 path is a directory / unreadable.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

VALID_ACTIONS = {"dispatch", "addressing", "handoff"}
IN_FLIGHT_RE = re.compile(r"^in-flight::\s*(.*)$", re.MULTILINE)
# Data row, Phase column optional (7-col current, or 6-col pre-Phase back-compat):
#   | <runtime> | <round> | [<PHASE> |] C<n> | ...
ROW_RE = re.compile(r"^\|\s*[0-9T:\-]+\s*\|\s*(\d+)\s*\|(?:\s*[A-Za-z\-]+\s*\|)?\s*C\d+\s*\|")
# Round-summary comment carrying the clean signal:
SUMMARY_RE = re.compile(r"<!--\s*Round\s+(\d+)\s+total:\s*raw flags\s+(\d+)\b")


def parse(text: str) -> dict:
    highest = 0
    row_count = 0
    for line in text.splitlines():
        m = ROW_RE.match(line)
        if m:
            row_count += 1
            r = int(m.group(1))
            if r > highest:
                highest = r

    in_flight = None
    mf = IN_FLIGHT_RE.search(text)
    if mf:
        raw = mf.group(1).strip()
        parts = raw.split()
        action = parts[1] if len(parts) >= 2 else None
        rnd = None
        if len(parts) >= 3:
            rm = re.match(r"round-(\d+)", parts[2])
            if rm:
                rnd = int(rm.group(1))
        in_flight = {
            "raw": raw,
            "runtime": parts[0] if parts else None,
            "action": action,
            "round": rnd,
            "action_valid": action in VALID_ACTIONS,
        }

    # last_round_clean: the round-summary comment is the authoritative clean signal.
    last_clean = None
    best_round = -1
    for sm in SUMMARY_RE.finditer(text):
        sr = int(sm.group(1))
        if sr >= best_round:
            best_round = sr
            last_clean = (int(sm.group(2)) == 0)
    # A converged round writes a `raw flags 0` summary but NO data rows (Step 6 writes one row
    # per cluster; zero clusters → zero rows). Count it so the round total isn't stuck at the
    # last cluster-bearing round — else a converged-then-marker-cleared ledger looks like it
    # stopped at round N-1 and recovery rule 5 mis-routes. The summary round can exceed the
    # highest data row.
    highest = max(highest, best_round if best_round >= 0 else 0)
    if best_round < highest:
        # highest round has data rows but no summary comment → didn't close → cleanliness unknown
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
        text = p.read_text()
    except OSError as e:
        print(f"ERROR: cannot read ledger {p}: {e}", file=sys.stderr)
        return 2

    state = parse(text)
    state = {"ledger": str(p), "exists": True, **state}
    print(json.dumps(state, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
