#!/usr/bin/env python3
"""Shared ledger parsing/format helpers — the single source of truth for skill-tracer's
ledger scripts (append_ledger.py, ledger_state.py) and the report scripts
(check_drift.py, check_results.py), each of which does `import ledger_common as lc`.

render_ledger.py is intentionally NOT a consumer: it is a standalone, config-driven
renderer that serves BOTH the tracer "Round" ledger and skill-publisher's "Run" ledger
via its own column-name-based parser. Keeping it independent (its own DEFAULT_VALID_ACTIONS
/ DEFAULT_PHASE_COLORS, overridable via --config) is what lets one renderer handle both
layouts; it does not import this module.

The audit ledger is a 7-column markdown table:
    | Runtime | Round | Phase | Cluster | Root cause | Address | Flags |
(Phase is optional — 6-column pre-Phase back-compat rows still parse; Phase defaults to TRACE.)

Before this module each script hand-maintained its own copy of the row regex, the
round-summary regex, the in-flight-marker parse, and the action/address/phase vocab,
kept in lockstep by comments. That duplication is now stated once here so a format
change is made in one place. Pure-stdlib; vendored to skill-publisher alongside the
scripts that import it.
"""
from __future__ import annotations

import re

# --- Vocabulary (closed sets) ---
VALID_ACTIONS = ("dispatch", "addressing", "handoff")
ADDRESS_KINDS = ("FIX", "STRENGTHEN", "USER-PAUSE", "would-FIX", "would-STRENGTHEN", "would-USER-PAUSE")
_BASE_KINDS = ("FIX", "STRENGTHEN", "USER-PAUSE")  # for the address tally; would-<base> folds into <base>
# Phase values append_ledger.py will WRITE. PORT-AUDIT is read-tolerated (any [A-Z-]+ parses) but
# write-forbidden — it belongs to skill-publisher.
KNOWN_PHASES = ("TRACE", "REVIEW", "SIMPLIFY")

# --- Regexes (compiled once) ---
# Data row, Phase column optional (group 3 None on a 6-col row → caller defaults to TRACE):
ROW_RE = re.compile(
    r"^\|\s*([0-9T:\-]+)\s*\|\s*(\d+)\s*\|\s*(?:([A-Z\-]+)\s*\|\s*)?(C\d+)\s*\|(.*)\|(.*)\|(.*)\|\s*$"
)
# Round-summary comment (its presence marks a closed round; carries the raw-flag count):
SUMMARY_RE = re.compile(r"<!--\s*Round\s+(\d+)\s+total:\s*raw flags\s+(\d+)\b")
# In-flight marker line in the ledger header:
IN_FLIGHT_RE = re.compile(r"^in-flight::\s*(.*)$", re.MULTILINE)
# PRE-FLIGHT line a cold agent emits: "PRE-FLIGHT <path>: <N> lines, last edited <yyyy-mm-dd>"
PREFLIGHT_RE = re.compile(
    r"^\s*PRE-FLIGHT\s+(?P<path>.+?):\s*(?P<lines>\d+)\s+lines,\s*last edited\s+(?P<date>\d{4}-\d{2}-\d{2})\s*$"
)
# Round token in a marker — ANCHORED, so a corrupt token like "round-3x" is NOT read as round 3:
_ROUND_TOKEN_RE = re.compile(r"^round-(\d+)$")
# Cluster-cell grammar — the same `C<n>` shape ROW_RE's group 4 embeds, named here so append_ledger.py's
# write-time --cluster guard imports it instead of re-hardcoding `^C\d+$` (render_ledger.py keeps its own
# standalone copy by design). One home for the writer + the row parser:
CLUSTER_RE = re.compile(r"^C\d+$")


def parse_row(line: str) -> dict | None:
    """Parse one ledger data row → dict, or None if the line is not a data row.
    Phase defaults to 'TRACE' on a 6-column back-compat row."""
    m = ROW_RE.match(line)
    if not m:
        return None
    return {
        "runtime": m.group(1).strip(),
        "round": int(m.group(2)),
        "phase": (m.group(3).strip() if m.group(3) else "TRACE"),
        "cluster": m.group(4).strip(),
        "root_cause": m.group(5).strip(),
        "address": m.group(6).strip(),
        "flags": [f.strip() for f in m.group(7).split(",") if f.strip()],
    }


def round_rows(text: str, rnd: int) -> list[dict]:
    """All data rows for a given round, parsed."""
    return [r for r in (parse_row(line) for line in text.splitlines()) if r and r["round"] == rnd]


def parse_in_flight(text: str) -> dict | None:
    """Parse the in-flight marker → {raw, runtime, action, round, action_valid} or None.
    `round` is None when no valid `round-<int>` token is present (truncated or corrupt marker)."""
    mf = IN_FLIGHT_RE.search(text)
    if not mf:
        return None
    raw = mf.group(1).strip()
    parts = raw.split()
    action = parts[1] if len(parts) >= 2 else None
    rnd = None
    if len(parts) >= 3:
        rm = _ROUND_TOKEN_RE.match(parts[2])
        if rm:
            rnd = int(rm.group(1))
    return {
        "raw": raw,
        "runtime": parts[0] if parts else None,
        "action": action,
        "round": rnd,
        "action_valid": action in VALID_ACTIONS,
    }


def address_kind_ok(address: str) -> bool:
    """True iff the address begins with a known kind at a TOKEN BOUNDARY (kind followed by a space
    or '('). A bare kind ('FIX' with no file/detail), or 'FIXED…'/'STRENGTHENING', is rejected."""
    addr = address.strip()
    return any(addr.startswith(k + " ") or addr.startswith(k + "(") for k in ADDRESS_KINDS)


def address_base_kind(address: str) -> str | None:
    """The base kind (FIX / STRENGTHEN / USER-PAUSE) an address counts as, folding the would- forms,
    using the same token-boundary rule as address_kind_ok. None if it matches no kind."""
    addr = address.strip()
    for base in _BASE_KINDS:
        for prefix in (base, "would-" + base):
            if addr.startswith(prefix + " ") or addr.startswith(prefix + "("):
                return base
    return None
