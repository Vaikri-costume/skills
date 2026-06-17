#!/usr/bin/env python3
"""Per-direction result-validity check for skill-tracer Step 5.

After the three cold agents return, Step 5 must decide — per direction — whether
the report is USABLE or must be re-dispatched. Today that's hand-eyeballed
(PRE-FLIGHT present? trailing summary present? count matches? ABORTED?), which is
deterministic parsing the orchestrator re-improvises every round. This script
parses one direction's report and returns its state so the re-dispatch decision
is computed, not eyeballed.

CRITICAL DESIGN POINT (the substance-not-clerical rule): a mismatch between the
trailing `No of issues found:: N` and the actual number of `ISSUE` blocks is a
COUNTING error by the agent — NOT evidence the findings are wrong. The ISSUE
blocks (tag/Claim/Target) are the substance and are sitting right there to be
recounted. So this script reports BOTH `declared_count` and `actual_block_count`
and an `authoritative_count` (= actual_block_count, the one to trust), and a
`count_mismatch` flag that is INFORMATIONAL — it must NOT by itself trigger a
re-dispatch. Re-dispatch only when `usable` is false (genuine substance failure:
ABORTED, no PRE-FLIGHT at all, or no trailing summary at all).

Pure-stdlib.

Usage:
    check_results.py --file <report.txt> [--direction forward]
    cat report.txt | check_results.py

Output JSON:
    {
      "direction": "<label or null>",
      "aborted": <bool>, "aborted_detail": "<text|null>",
      "has_preflight": <bool>, "preflight_count": <int>,
      "has_trailing_summary": <bool>,
      "declared_count": <int|null>,      # from `No of issues found:: N` (null if 'No issues found' or absent)
      "actual_block_count": <int>,       # ISSUE blocks actually present — AUTHORITATIVE
      "authoritative_count": <int>,      # = actual_block_count (use THIS, recount-don't-reject)
      "count_mismatch": <bool>,          # declared != actual — INFORMATIONAL, never a re-dispatch trigger
      "usable": <bool>,                  # substance is usable; re-dispatch iff false
      "redispatch_reason": "<text|null>" # why not usable (null if usable)
    }

Exit: 0 usable (proceed; recount if count_mismatch); 1 NOT usable (re-dispatch this direction); 2 usage error.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ledger_common as lc  # noqa: E402  (single source of truth for the PRE-FLIGHT line format)

ISSUE_RE = re.compile(r"^ISSUE\s+\[", re.MULTILINE)
ABORTED_RE = re.compile(r"^ABORTED\b\s*(.*)$", re.MULTILINE)
NO_ISSUES_RE = re.compile(r"^No issues found\s*$", re.MULTILINE)
COUNT_RE = re.compile(r"^No of issues found::\s*(\d+)\s*$", re.MULTILINE)


def check(report: str, direction: str | None) -> dict:
    actual_block_count = len(ISSUE_RE.findall(report))
    authoritative_count = actual_block_count

    aborted_m = ABORTED_RE.search(report)
    # A genuine abort emits NO ISSUE blocks — the agent aborts at the pre-flight gate, before producing issues.
    # A report that HAS ISSUE blocks but merely QUOTES "ABORTED" (e.g. when tracing skill-tracer on itself, whose
    # prompt-template.md instructs agents to emit "ABORTED — missing files: ..." — a line a cold agent may quote in
    # a Target:) is NOT an abort. Treating it as one would discard the real findings and loop forever re-dispatching
    # a direction that keeps reproducing the quoted line. So require zero ISSUE blocks for a real abort.
    aborted = aborted_m is not None and actual_block_count == 0
    aborted_detail = aborted_m.group(0).strip() if aborted else None

    preflight_count = sum(1 for ln in report.splitlines() if lc.PREFLIGHT_RE.match(ln))
    has_preflight = preflight_count > 0

    # The trailing summary must be the report's LAST non-empty line (prompt-template: "conclude with exactly one
    # trailing line"). Matching anywhere (search) would let a mid-report narration like "No issues found so far" in
    # a truncated/garbled report pass as a valid summary; anchor to the tail so a real truncation is still caught.
    _nonempty = [ln for ln in report.splitlines() if ln.strip()]
    _last = _nonempty[-1] if _nonempty else ""
    no_issues = NO_ISSUES_RE.match(_last) is not None
    count_m = COUNT_RE.match(_last)
    declared_count = int(count_m.group(1)) if count_m else (0 if no_issues else None)
    has_trailing_summary = no_issues or (count_m is not None)

    # count_mismatch is informational only.
    count_mismatch = (declared_count is not None) and (declared_count != actual_block_count)

    # Usable = substance present. Re-dispatch ONLY on genuine substance failure.
    redispatch_reason = None
    if aborted:
        redispatch_reason = f"ABORTED report: {aborted_detail}"
    elif not has_preflight:
        redispatch_reason = "no PRE-FLIGHT line(s) — agent did not complete the pre-flight gate"
    elif not has_trailing_summary:
        redispatch_reason = "no trailing summary ('No issues found' / 'No of issues found:: N') — report truncated/garbled"
    usable = redispatch_reason is None

    return {
        "direction": direction,
        "aborted": aborted,
        "aborted_detail": aborted_detail,
        "has_preflight": has_preflight,
        "preflight_count": preflight_count,
        "has_trailing_summary": has_trailing_summary,
        "declared_count": declared_count,
        "actual_block_count": actual_block_count,
        "authoritative_count": authoritative_count,
        "count_mismatch": count_mismatch,
        "usable": usable,
        "redispatch_reason": redispatch_reason,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="skill-tracer per-direction result check")
    ap.add_argument("--file", help="report file (default: stdin)")
    ap.add_argument("--direction", default=None, help="label (forward/backward/executor) for the output")
    args = ap.parse_args()

    if args.file:
        p = Path(args.file).expanduser()
        if not p.is_file():
            print(f"ERROR: --file not found: {p}", file=sys.stderr)
            return 2
        report = p.read_text()
    else:
        if sys.stdin.isatty():
            print("ERROR: no input — pass --file <report> or pipe the report on stdin", file=sys.stderr)
            return 2
        report = sys.stdin.read()

    result = check(report, args.direction)
    print(json.dumps(result, indent=2))
    return 0 if result["usable"] else 1


if __name__ == "__main__":
    sys.exit(main())
