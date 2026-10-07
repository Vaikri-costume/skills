#!/usr/bin/env python3
"""cluster_prepass.py — MECHANICAL root-cause clustering for the Prepass tier.

Hypothesis under test: Prepass findings are deterministic, so their root-cause
grouping is mechanical — no prose judgment needed. The cluster key is
(check_id, file, handler_shape): every finding from the same detector in the
same file with the same handler shape shares one root cause (one systemic
pattern in that file → one considered-fix decision). Clusters are numbered
C1, C2, … in stable order (by check, then file, then handler_shape). Prepass-
phase leads the round so the C-sequence starts here.

handler_shape is populated only for exception-handler checks (_EXCEPT_CHECKS: detectors whose
findings point at a handler whose body is exactly one `return` with no `raise` in it). No kept
prepass detector is one, so the set is empty and handler_shape is None; the values it can take are:
  - log-and-continue: the returned expression contains a stderr/stdout print/logging Call.
  - other:            the handler returns a plain fallback value (no logging call).
  - unknown:          file unreadable or handler not found; do not crash.
  None: check is not an exception-handler check.

This is the clustering STAGE only — it consumes cascade_sweep.py --level prepass
--json and emits clusters. Considered-fix / fix-blast / ledger are separate
stages. Pure stdlib.

Usage:
    cascade_sweep.py <target> --level prepass --json | cluster_prepass.py [--json] [--target <dir>]
    cascade_sweep.py <target> --level prepass --json | cluster_prepass.py [--json] [--target <dir>] \\
        --ledger <path> --round <N>

When --ledger and --round are given, cluster_prepass reads the ledger to find the
maximum C<n> number already assigned in round N (across ANY phase), then
numbers this pass's clusters from maxC+1. This makes C-numbering
per-round-continuing so a second prepass pass (re-entered after a prepass fix)
does not restart at C1 and collide with earlier clusters in the same round.
Without --ledger / --round, numbering starts at C1 (original behaviour).
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
from collections import OrderedDict
from pathlib import Path
from typing import Optional

# Bootstrap: ensure scripts/ dir is importable so ledger_common can be imported
# when --ledger is supplied.  We locate scripts/ relative to THIS file.
_HERE = Path(__file__).resolve().parent
_SCRIPTS = _HERE / "scripts"
for _p in (_SCRIPTS, _HERE):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

# Checks treated as exception-handler checks (CHECK_IDs of active prepass detectors whose
# findings point at an `except` handler). None of the six prepass detectors is one; add the
# CHECK_ID here when such a detector is added.
_EXCEPT_CHECKS: frozenset = frozenset()

# P-flag prefix used by this stage.
_P_PREFIX = "P"


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------

def _is_stderr_stdout_call(node: ast.expr) -> bool:
    """Return True if *node* is a Call that writes to stderr or stdout."""
    if not isinstance(node, ast.Call):
        return False
    # Check for print(..., file=sys.stderr) or print(..., file=sys.stdout)
    for kw in node.keywords:
        if kw.arg == "file":
            v = kw.value
            if isinstance(v, ast.Attribute) and v.attr in ("stderr", "stdout"):
                return True
    # Also accept bare print() calls (go to stdout).
    func = node.func
    if isinstance(func, ast.Name) and func.id == "print":
        return True
    if isinstance(func, ast.Attribute) and func.attr in ("write", "error", "warning", "info", "debug", "critical"):
        return True
    return False


def _body_has_logging_call(stmts: list[ast.stmt]) -> bool:
    """Walk all statements recursively looking for a stderr/stdout call."""
    for node in ast.walk(ast.Module(body=stmts, type_ignores=[])):
        if isinstance(node, ast.Expr) and _is_stderr_stdout_call(node.value):
            return True
        if isinstance(node, ast.Call) and _is_stderr_stdout_call(node):
            return True
    return False


def _handler_shape(handler: ast.ExceptHandler) -> str:
    # Only single-`return` handlers reach here (see the module docstring), so the one distinction
    # left is whether the returned expression makes a logging call or is a plain fallback value.
    if _body_has_logging_call(handler.body):
        return "log-and-continue"
    return "other"


def _find_handler_for_line(tree: ast.AST, lineno: int) -> Optional[ast.ExceptHandler]:
    """Return the innermost ExceptHandler whose span covers *lineno*."""
    best: Optional[ast.ExceptHandler] = None
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        start = node.lineno
        # end_lineno available in Python 3.8+
        end = getattr(node, "end_lineno", None)
        if end is None:
            # Fall back: handler covers start to start of last body stmt
            if node.body:
                end = getattr(node.body[-1], "end_lineno", node.body[-1].lineno)
            else:
                end = start
        if start <= lineno <= end:
            # Pick most specific (latest start line)
            if best is None or node.lineno > best.lineno:
                best = node
    return best


# ---------------------------------------------------------------------------
# Source resolver
# ---------------------------------------------------------------------------

def _make_source_resolver(target_dir: Optional[str]):
    """Return a callable (rel_path) -> source str | None."""
    if not target_dir:
        return lambda _: None

    _cache: dict[str, Optional[str]] = {}

    def resolve(rel_path: str) -> Optional[str]:
        if rel_path in _cache:
            return _cache[rel_path]
        full = os.path.join(target_dir, rel_path)
        try:
            with open(full, "r", encoding="utf-8", errors="replace") as fh:
                src = fh.read()
        except OSError:
            src = None
        _cache[rel_path] = src
        return src

    return resolve


def _compute_handler_shape(
    check: str,
    file: str,
    line: Optional[int],
    source_resolver,
) -> Optional[str]:
    """Return handler_shape string or None if check is not an except-check."""
    if check not in _EXCEPT_CHECKS:
        return None
    if source_resolver is None or line is None:
        return "unknown"
    src = source_resolver(file)
    if src is None:
        return "unknown"
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return "unknown"
    handler = _find_handler_for_line(tree, line)
    if handler is None:
        return "unknown"
    return _handler_shape(handler)


# ---------------------------------------------------------------------------
# Ledger helpers — C-offset for per-round-continuing numbering
# ---------------------------------------------------------------------------

def _max_p_in_round(ledger_path: str, rnd: int) -> int:
    """Return the highest P<n> integer already assigned for *rnd* in the ledger.

    Delegates to ledger_common.max_flag_in_round (shared helper, single source of truth).
    Returns 0 when the ledger is absent or has no P-flags for this round.
    """
    try:
        import ledger_common as lc
    except ImportError:
        return 0
    return lc.max_flag_in_round(ledger_path, rnd, _P_PREFIX)


def _max_cluster_in_round(ledger_path: str, rnd: int) -> int:
    """Return the highest C<n> cluster id already assigned for *rnd* across ALL phases.

    Delegates to ledger_common.max_cluster_in_round (shared helper, single source of
    truth — the same continuation logic cluster_enforce.py uses for Code Review clusters), so
    both phases number clusters identically within a round. Returns 0 when the ledger is
    absent/empty or has no round-N rows.
    """
    try:
        import ledger_common as lc
    except ImportError:
        return 0
    return lc.max_cluster_in_round(ledger_path, rnd)


# ---------------------------------------------------------------------------
# Finding signature (repeat-count identity)
# ---------------------------------------------------------------------------

# A ledger row's Root cause is `<check>[<shape>] ×<n> in <file>` (see cluster() below), with
# ledger_cascade appending ` [blast: ...]`. The signature is what stays the same when the same
# defect re-appears: (check, file, handler_shape). prepass_run.py counts prior addressed rows
# by it, so row and cluster must agree on this one definition.
_ROOT_CAUSE_RE = re.compile(
    r"^(?P<check>[^\s\[]+)(?:\[(?P<shape>[^\]]*)\])? ×\d+ in (?P<file>.+?)(?: \[blast: .*\])?$"
)


def row_signature(root_cause: str) -> Optional[tuple]:
    """(check, file, handler_shape-or-"") parsed from a ledger Root cause cell, or None when it is
    not a Prepass-shaped root cause."""
    m = _ROOT_CAUSE_RE.match((root_cause or "").strip())
    if not m:
        return None
    return (m.group("check"), m.group("file"), m.group("shape") or "")


def cluster_signature(c: dict) -> tuple:
    """The same (check, file, handler_shape-or-"") for a cluster dict emitted by cluster()."""
    return (c.get("check", ""), c.get("file", ""), c.get("handler_shape") or "")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def cluster(
    prepass_findings: list[dict],
    source_resolver=None,
    c_offset: int = 0,
    p_offset: int = 0,
) -> list[dict]:
    """Group findings into clusters and return them as a list of dicts.

    *source_resolver* is an optional callable (rel_path: str) -> source_str | None
    used to resolve handler_shape for exception-handler checks.

    *c_offset* is the number of C-slots already consumed in the current round
    (from a prior pass).  Pass ``_max_cluster_in_round(ledger, rnd)`` here when
    --ledger/--round are given; leave at 0 for standalone use.

    *p_offset* is the highest P<n> already assigned in this round (from the ledger).
    Pass ``_max_p_in_round(ledger, rnd)`` here when --ledger/--round are given;
    leave at 0 for standalone use (flags then start at P1).

    Each emitted cluster carries a "flags" list — one P-flag per member line —
    numbered continuously across all clusters in cluster order, continuing from
    p_offset+1.  The ledger writes these verbatim; it never renumbers them.
    """
    groups: "OrderedDict[tuple, list]" = OrderedDict()
    shapes: dict[tuple, Optional[str]] = {}

    for fd in prepass_findings:
        check = fd.get("check", "?")
        file = fd.get("file", "?")
        line = fd.get("line")
        shape = _compute_handler_shape(check, file, line, source_resolver)
        key = (check, file, shape)
        groups.setdefault(key, []).append(fd)
        shapes[key] = shape

    # stable order: by check, then file, then handler_shape (None sorts first)
    ordered = sorted(
        groups.items(),
        key=lambda kv: (kv[0][0], kv[0][1], kv[0][2] or ""),
    )

    clusters = []
    # P-flag counter runs globally across all clusters (cluster order), continuing from p_offset+1.
    p_counter = 1 + p_offset
    for i, ((check, file, shape), members) in enumerate(ordered, start=1 + c_offset):
        lines = sorted(m.get("line") for m in members if m.get("line"))
        shape_suffix = f"[{shape}]" if shape is not None else ""
        root_cause = f"{check}{shape_suffix} ×{len(members)} in {file}"

        # The shared token of each member is its explicit "token" field when the detector sets one
        # (dup-regex: the pattern text), else the FIRST backtick-quoted name in its detail (the
        # convention fix_blast.py's docstring states for TOKEN-BLAST checks). Later backticked names
        # are context, not the token a fix changes: a detail may also quote a script name, and
        # treating that as a token would demand that every file naming the script be edited
        # although the fix changes only the first name.
        tokens: list[str] = []
        seen_tokens: set[str] = set()
        rep_detail: Optional[str] = None
        for m in members:
            detail = m.get("detail") or m.get("message") or ""
            if detail and rep_detail is None:
                rep_detail = detail
            first = re.search(r"`([^`]+)`", detail)
            token = m.get("token") or (first.group(1) if first else "")
            if token and token not in seen_tokens:
                seen_tokens.add(token)
                tokens.append(token)

        # Assign one P-flag per member line, continuing globally from p_counter.
        count = len(members) or 1
        flags = [f"{_P_PREFIX}{p_counter + j}" for j in range(count)]
        p_counter += count

        entry: dict = {
            "cluster": f"C{i}",
            "phase": "Prepass",
            "check": check,
            "file": file,
            "count": len(members),
            "lines": lines,
            "root_cause": root_cause,
            "flags": flags,
        }
        if shape is not None:
            entry["handler_shape"] = shape
        if tokens:
            entry["tokens"] = tokens
        if rep_detail is not None:
            entry["detail"] = rep_detail
        clusters.append(entry)

    return clusters


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(
        description="Mechanical Prepass root-cause clusterer."
    )
    ap.add_argument("--json", action="store_true", help="Emit JSON output.")
    ap.add_argument(
        "--target",
        metavar="DIR",
        default=None,
        help=(
            "Root directory of the audit target, read to compute handler_shape. handler_shape "
            "is computed only for checks in _EXCEPT_CHECKS, which is empty, so --target does "
            "not change the clusters."
        ),
    )
    ap.add_argument(
        "--ledger",
        metavar="PATH",
        default=None,
        help=(
            "Path to the audit ledger.  When given (together with --round), "
            "C-numbering continues from the highest C<n> already in the ledger "
            "for that round, so a second prepass pass in the same round does not "
            "restart at C1."
        ),
    )
    ap.add_argument(
        "--round",
        type=int,
        default=None,
        metavar="N",
        help="Audit round number; required when --ledger is given.",
    )
    args = ap.parse_args()

    if args.ledger and args.round is None:
        ap.error("--ledger requires --round")
    if args.round is not None and not args.ledger:
        ap.error("--round requires --ledger")

    data = json.load(sys.stdin)
    resolver = _make_source_resolver(args.target)

    c_offset = 0
    p_offset = 0
    if args.ledger is not None:
        c_offset = _max_cluster_in_round(args.ledger, args.round)
        p_offset = _max_p_in_round(args.ledger, args.round)

    clusters = cluster(data.get("prepass", []), source_resolver=resolver, c_offset=c_offset, p_offset=p_offset)

    if args.json:
        print(json.dumps({"clusters": clusters}, indent=2))
    else:
        key_desc = (
            "check × file × handler_shape"
            if any("handler_shape" in c for c in clusters)
            else "check × file"
        )
        print(f"=== Prepass mechanical clusters: {len(clusters)} (key = {key_desc}) ===")
        for c in clusters:
            ln = ",".join(str(x) for x in c["lines"][:8]) + ("…" if len(c["lines"]) > 8 else "")
            shape_tag = f"  shape={c['handler_shape']}" if "handler_shape" in c else ""
            print(f"  {c['cluster']:4} [{c['phase']}] {c['root_cause']}{shape_tag}  @ {ln}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
