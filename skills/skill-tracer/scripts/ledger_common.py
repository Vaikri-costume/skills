#!/usr/bin/env python3
"""Shared helpers for the cascade scripts, imported as `import ledger_common as lc` by every script
that mutates or reads the ledger (append_ledger.py, ledger_cascade.py, cluster_enforce.py,
prepass_run.py, code_review_run.py, code_review_collect.py), by check_decisions.py (reading a fixer's
decisions), by post_fix_gate.py, and by cluster_prepass.py,
assemble_fix_prompt.py, stage_cold_prompts.py and cleanup_tmp_prompts.py for the run-identity
helpers. It holds two layers:

  - Ledger format: the row/marker/run-options grammar and its parsers and writers (vocabulary,
    regexes, parse_row, parse_in_flight, format_row, ledger_header, write_marker, run options and
    round_gate, unresolved_pauses). This is the single source of truth for the ledger's format,
    including the migration of legacy (3.0 and earlier) markers and run options.
  - Tier-script steps the tier scripts share and that act on the ledger: the repeat-count
    auto-pause (split_repeat_clusters, write_pause_rows, which runs `ledger_cascade.py --mode
    cluster` as a subprocess, never an import), fixer-prompt staging (stage_fixer_prompt, which runs
    assemble_fix_prompt.py), fixer batching (fixer_batches, fixer_model, stage_fixer_batches), reading
    a fixer's decisions (fixer_decisions) and the advisory blast groups. They import nothing beyond
    the stdlib, and their paths to templates/ and references/ are computed only when called.

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

import json
import re
import subprocess
import sys

# --- Vocabulary (closed sets) ---
VALID_ACTIONS = (
    "dispatch", "reviewing", "addressing", "handoff",
    # Terminal record `in-flight:: <timestamp> converged round-<N>` (written by close-round --converged)
    # has the legacy 3-field shape with this token in the action slot:
    "converged",
    "addressing-Prepass", "addressing-CodeReview",
)
# 4-field marker grammar: in-flight:: <runtime> <phase> <state> round-<N>. The cascade has two tiers.
VALID_PHASES = {"prepass", "code-review"}
VALID_STATES = {"running", "addressing", "orch-fixes", "dispatched"}
# Legacy compatibility (ledgers written by 3.0 and earlier, which had a tier between prepass and
# code-review): such a marker was only ever written after prepass converged, so it resumes as
# `code-review running` (parse_in_flight reports the migrated phase and `legacy_phase`).
LEGACY_PHASES = {"minor-bugs": "code-review"}
ADDRESS_KINDS = ("FIX", "STRENGTHEN", "ORCHESTRATOR-PAUSE", "USER-PAUSE")
_BASE_KINDS = ("FIX", "STRENGTHEN", "USER-PAUSE")  # for the address tally
# Legacy compatibility: rows written by a 3.0-and-earlier dry-run mode start with `would-`; they still
# parse, tally as their base kind and are never an open pause, but no writer accepts them any more.
LEGACY_WOULD_PREFIX = "would-"
# Phase values append_ledger.py and ledger_cascade.py will WRITE; any other phase is rejected at write
# time. Rows of other phases still parse (ROW_RE accepts any [A-Za-z -]+), so legacy rows (3.0 and
# earlier) and skill-publisher's SIMPLIFY / PORT-AUDIT rows still read.
KNOWN_PHASES = (
    # Legacy / skill-tracer direct phases (back-compat):
    "TRACE", "REVIEW", "CODE-REVIEW", "PREPASS",
    # The two cascade tier tags:
    "Prepass", "Code Review",
)

# --- Regexes (compiled once) ---
# Data row, Phase column optional (group 3 None on a 6-col row → caller defaults to TRACE):
# Phase group accepts mixed case ([A-Za-z -]+) so a hand-edited/legacy lowercase phase ("trace")
# still parses the whole row instead of dropping it; parse_row normalizes it to upper-case.
# The phase can contain spaces (e.g. "Code Review").
ROW_RE = re.compile(
    r"^\|\s*([0-9T:\-]+)\s*\|\s*(\d+)\s*\|\s*(?:([A-Za-z \-]+)\s*\|\s*)?(C\d+)\s*\|(.*)\|(.*)\|(.*)\|\s*$"
)
# Round-summary comment (its presence marks a closed round; carries the raw-flag count):
SUMMARY_RE = re.compile(r"<!--\s*Round\s+(\d+)\s+total:\s*raw flags\s+(\d+)\b")
# In-flight marker line in the ledger header:
# [ \t]* (not \s*) so an empty value never swallows the next line under MULTILINE.
IN_FLIGHT_RE = re.compile(r"^in-flight::[ \t]*(.*)$", re.MULTILINE)
# (A cold agent also emits "PRE-FLIGHT <path>: <N> lines, ..." lines. No script parses them: they make the
# agent state each file's length before reading, and coverage is enforced by coverage_check.py on the
# agent's Read-tool calls, so a missing PRE-FLIGHT line is not a contract violation.)
# ISSUE block opener a cold agent (direction or lens) emits: "ISSUE [<tag>]: ...". One match per finding.
# Single source of truth for issue-block counting: code_review_collect.py imports this for
# its raw-block count, so the same regex that counts a round's findings is used everywhere
# a finding needs to be counted.
ISSUE_RE = re.compile(r"^ISSUE\s+\[", re.MULTILINE)
# Round token in a marker — ANCHORED, so a corrupt token like "round-3x" is NOT read as round 3:
_ROUND_TOKEN_RE = re.compile(r"^round-(\d+)$")
# Dispatched state with an optional fan-out count: "dispatched" or "dispatched-<n>"
# (n = number of parallel agents out, so recovery knows how many transcripts to collect).
_DISPATCH_STATE_RE = re.compile(r"^dispatched(?:-(\d+))?$")
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
        "phase": (m.group(3).strip().upper() if m.group(3) else "TRACE"),
        "cluster": m.group(4).strip(),
        "root_cause": m.group(5).strip(),
        "address": m.group(6).strip(),
        "flags": [f.strip() for f in m.group(7).split(",") if f.strip()],
    }


def round_rows(text: str, rnd: int) -> list[dict]:
    """All data rows for a given round, parsed."""
    return [r for r in (parse_row(line) for line in text.splitlines()) if r and r["round"] == rnd]


def parse_in_flight(text: str) -> dict | None:
    """Parse the in-flight marker.

    Canonical 4-field form:
        in-flight:: <runtime> <phase> <state> round-<N>
    Returns {raw, runtime, phase, state, round, phase_valid, state_valid, dispatch_count,
    legacy_phase} on success. A legacy-compatibility `minor-bugs` phase is migrated (LEGACY_PHASES): `phase` is
    "code-review", `state` is "running" and `legacy_phase` names the original; else legacy_phase is None.

    Legacy 3-field form (old grammar still tolerated for back-compat):
        in-flight:: <runtime> <action> round-<N>
    Returns {raw, runtime, action, round, action_valid} with phase=None, state=None.

    In both cases `round` is None when no valid `round-<int>` token is present.
    Returns None when there is no in-flight:: line at all.
    """
    mf = IN_FLIGHT_RE.search(text)
    if not mf:
        return None
    raw = mf.group(1).strip()
    parts = raw.split()

    # Attempt canonical 4-field parse: <runtime> <phase> <state> round-<N>
    if len(parts) == 4:
        runtime, phase, state, round_tok = parts
        rm = _ROUND_TOKEN_RE.match(round_tok)
        rnd = int(rm.group(1)) if rm else None
        legacy_phase = None
        if phase in LEGACY_PHASES:
            legacy_phase, phase, state = phase, LEGACY_PHASES[phase], "running"
        # The dispatched state may carry a fan-out count: "dispatched-<n>" tells
        # recovery how many transcripts to collect. Parse it to a base
        # state + dispatch_count; bare "dispatched" → count None.
        dm = _DISPATCH_STATE_RE.match(state)
        dispatch_count = int(dm.group(1)) if (dm and dm.group(1)) else None
        state_base = "dispatched" if dm else state
        return {
            "raw": raw,
            "runtime": runtime,
            "phase": phase,
            "state": state,
            "round": rnd,
            "phase_valid": phase in VALID_PHASES,
            "state_valid": (state_base in VALID_STATES),
            "dispatch_count": dispatch_count,
            "legacy_phase": legacy_phase,
        }

    # Fallback: legacy 3-field form <runtime> <action> round-<N>
    action = parts[1] if len(parts) >= 2 else None
    rnd = None
    if len(parts) >= 3:
        rm = _ROUND_TOKEN_RE.match(parts[2])
        if rm:
            rnd = int(rm.group(1))
    return {
        "raw": raw,
        "runtime": parts[0] if parts else None,
        "phase": None,
        "state": None,
        "action": action,
        "round": rnd,
        "action_valid": action in VALID_ACTIONS,
    }


def address_kind_ok(address: str) -> bool:
    """True iff the address begins with a known kind at a TOKEN BOUNDARY (kind followed by a space
    or '('). A bare kind ('FIX' with no file/detail), or 'FIXED…'/'STRENGTHENING', is rejected."""
    addr = address.strip()
    return any(addr.startswith(k + " ") or addr.startswith(k + "(") for k in ADDRESS_KINDS)


# Banned-vocabulary lint (references/how-to-fix.md "Context: findings here are already confirmed"
# and "No-orphan-flag"): a fixer may never reject or withdraw a finding, and there is no DISMISS
# branch. This vocabulary implies the opposite (the agent was simply wrong, no edit
# needed) and is banned outright, not just the no-edit action it used to justify. This is a
# mechanical backstop on top of that standing discipline -- the same banned language recurred
# twice in one session even after being explicitly named the first time. Lives here, not in
# append_ledger.py, because BOTH writers (append and ledger_cascade fill-address) must apply it.
BANNED_PHRASES = [
    "false claim",
    "false positive",
    "verified as false",
    "already correct, no change",
    "already correct — no change",
    "already correct - no change",
    "claim is false",
    "reaffirmed, no change",
    "re-affirmed, no change",
]


def reject_unsafe(field_name: str, value: str) -> list[str]:
    """Errors for a free-text cell that would corrupt the pipe-delimited ledger row: a literal '|'
    (the renderer splits on it, silently dropping the row) or an embedded newline (the renderer
    leaves the table, truncating it). Shared by append_ledger.py and ledger_cascade.py."""
    errs = []
    if "|" in value:
        errs.append(f"{field_name} contains a literal '|' (renderer splits on it -> row silently dropped). "
                    f"Use 'or' / 'vs.' / a dash instead: {value!r}")
    if "\n" in value or "\r" in value:
        errs.append(f"{field_name} contains an embedded newline (renderer exits the table -> truncation). "
                    f"Keep it single-line: {value!r}")
    return errs


def format_row(runtime: str, rnd, phase: str, cluster: str, root_cause: str, address: str, flags: str) -> str:
    """The one place the seven-cell ledger row line is formatted."""
    return f"| {runtime} | {rnd} | {phase} | {cluster} | {root_cause} | {address} | {flags} |"


def reject_banned_vocabulary(field_name: str, value: str) -> list[str]:
    lowered = value.lower()
    hits = [p for p in BANNED_PHRASES if p in lowered]
    if not hits:
        return []
    return [
        f"{field_name} uses banned dismissal vocabulary ({', '.join(hits)}) -- findings are confirmed "
        f"defects that are never rejected or withdrawn, and there is no DISMISS branch "
        f"(references/how-to-fix.md \"No-orphan-flag\"). Locate what let a "
        f"careful cold reader end up confused, edit the skill text at that exact site to remove the "
        f"confusion vector, then describe THAT edit here instead: {value!r}"
    ]


def address_base_kind(address: str) -> str | None:
    """The base kind (FIX / STRENGTHEN / USER-PAUSE) an address counts as, folding legacy would- rows,
    using the same token-boundary rule as address_kind_ok. None if it matches no kind."""
    addr = address.strip()
    for base in _BASE_KINDS:
        for prefix in (base, LEGACY_WOULD_PREFIX + base):
            if addr.startswith(prefix + " ") or addr.startswith(prefix + "("):
                return base
    return None


NO_ISSUES_TAIL_RE = re.compile(r"^No issues found\s*$")
COUNT_TAIL_RE = re.compile(r"^No of issues found::\s*(\d+)\s*$")


def surviving_issue_count(report: str) -> int:
    """The count of findings a cold-agent report DECLARES on its trailing summary line:
      - terminal `No issues found`        -> 0
      - terminal `No of issues found:: N` -> N
      - neither (no recognized trailing line) -> the report is garbled/truncated and the caller
                                               rejects it; the raw block count is returned just
                                               so a number exists.
    The declared count is a contract, not a filter: code_review_collect.py requires the report's
    complete, non-retracted ISSUE blocks to number exactly this many, and asks the agent to
    re-emit otherwise (a block count above the declaration is ambiguous about which finding the
    agent meant to withdraw, so no block is ever dropped by position)."""
    nonempty = [ln for ln in report.splitlines() if ln.strip()]
    last = nonempty[-1] if nonempty else ""
    if NO_ISSUES_TAIL_RE.match(last):
        return 0
    m = COUNT_TAIL_RE.match(last)
    if m:
        return int(m.group(1))
    return count_issue_blocks(report)


def count_issue_blocks(report: str) -> int:
    """Number of ISSUE blocks textually present in a cold-agent report (raw `ISSUE [` count),
    including self-retracted ones; the declared count is surviving_issue_count()."""
    return len(ISSUE_RE.findall(report))


def max_flag_in_round(ledger_path: "Path", rnd: int, prefix: str) -> int:
    """Return the highest <prefix><n> integer already assigned in *ledger_path* for round *rnd*.

    Only the given prefix is examined (e.g. 'P', 'G1') — other prefixes are ignored so that
    an intervening pass's flags do not advance this counter.  Returns 0 when the ledger is
    absent, empty, or contains no matching flags for this round.

    The shared helper of cluster_prepass.py (P-flags) and code_review_collect.py (reviewer
    flags), so both read the same ledger in the same way.
    """
    from pathlib import Path as _Path
    p = _Path(ledger_path).expanduser()
    if not p.is_file():
        return 0
    text = p.read_text(encoding="utf-8")
    rows = round_rows(text, rnd)
    max_n = 0
    for row in rows:
        for flag in row.get("flags", []):
            flag = flag.strip()
            tail = flag[len(prefix):]
            if flag.startswith(prefix) and tail.isdigit():
                max_n = max(max_n, int(tail))
    return max_n


def max_cluster_in_round(ledger_path: "Path", rnd: int) -> int:
    """Return the highest C<n> cluster id already assigned in *ledger_path* for round *rnd*,
    across ALL phases of that round.

    A round spans the first prepass entry through the Code Review exit, irrespective of how many
    Prepass loops run inside it — so cluster ids must CONTINUE across every fix cycle and both
    phases of the round, never restart at C1. Each numbering source (cluster_prepass.py for Prepass
    clusters, cluster_enforce.py for Code Review clusters) starts at max+1 so successive cycles do not
    collide on (round, cluster). Returns 0 when the ledger is absent/empty or has no rows for
    this round. Rows OUTSIDE this round (older skill versions, other rounds) are ignored by
    round_rows — the caller is round-scoped and tolerant of everything else.
    """
    from pathlib import Path as _Path
    p = _Path(ledger_path).expanduser()
    if not p.is_file():
        return 0
    text = p.read_text(encoding="utf-8")
    rows = round_rows(text, rnd)
    if not rows:
        return 0
    max_c = 0
    for row in rows:
        cluster_val = row.get("cluster", "")
        if cluster_val.startswith("C"):
            try:
                n = int(cluster_val[1:])
                if n > max_c:
                    max_c = n
            except ValueError:
                pass
    return max_c


def unresolved_pauses(text: str) -> list[dict]:
    """Every ORCHESTRATOR-PAUSE or USER-PAUSE row not yet resolved by a LATER row whose
    Address says 'resolves ORCHESTRATOR-PAUSE …' or 'resolves USER-PAUSE …' and names one
    of the pause's flag-IDs (word-boundary match). The single source of truth for the
    no-unresolved-pause gate (SKILL.md's "Convergence" step + close-round guard), so a round cannot be
    closed or declared converged while an open orchestrator or user decision remains.

    Returns [{round, cluster, flags, runtime, kind}, …] in ledger order; empty = none open.
    `kind` is "ORCHESTRATOR-PAUSE" or "USER-PAUSE"."""
    _PAUSE_KINDS = ("ORCHESTRATOR-PAUSE", "USER-PAUSE")
    rows = [r for r in (parse_row(ln) for ln in text.splitlines()) if r]
    out = []
    for i, r in enumerate(rows):
        # Legacy `would-` rows (the retired verify-only mode) were hypotheticals, never open decisions.
        if r["address"].lstrip().startswith(LEGACY_WOULD_PREFIX):
            continue
        addr_stripped = r["address"].strip()
        pause_kind = None
        for k in _PAUSE_KINDS:
            if addr_stripped.startswith(k + " ") or addr_stripped.startswith(k + "("):
                pause_kind = k
                break
        if pause_kind is None:
            continue
        flags = r["flags"]
        resolved = False
        for later in rows[i + 1:]:
            later_addr = later["address"]
            # A resolving row must say 'resolves ORCHESTRATOR-PAUSE' or 'resolves USER-PAUSE'
            # AND name one of this pause's flag-IDs at a word boundary.
            if "resolves ORCHESTRATOR-PAUSE" not in later_addr and "resolves USER-PAUSE" not in later_addr:
                continue
            if any(re.search(r"(?<![A-Za-z0-9])" + re.escape(f) + r"(?![A-Za-z0-9])", later_addr) for f in flags):
                resolved = True
                break
        if not resolved:
            out.append({"round": r["round"], "cluster": r["cluster"],
                        "flags": flags, "runtime": r["runtime"], "kind": pause_kind})
    return out


# ---------------------------------------------------------------------------
# Repeat-count auto-pause (loop safety) of prepass_run.py
# ---------------------------------------------------------------------------
# WHY: the re-entering Prepass tier re-derives the same cluster when a fix did not stick. Without a
# count the loop would dispatch the same fix forever, so a cluster whose signature already has
# AUTO_PAUSE_REPEATS addressed rows of the same phase this round becomes an open ORCHESTRATOR-PAUSE
# row instead of a fixer cluster. The caller supplies the signature functions
# (cluster_prepass.row_signature / cluster_signature); counting, splitting and pause writing live here.

AUTO_PAUSE_REPEATS = 2  # addressed this many times already this round -> auto-pause


def split_repeat_clusters(ledger_path: "Path | str", rnd: int, phase: str, clusters: list,
                          row_sig, cluster_sig) -> tuple:
    """Annotate each cluster with `repeat_count` (addressed, non-PENDING rows of *phase* in round
    *rnd* whose row_sig(root_cause) equals cluster_sig(cluster)) and split them.
    Returns (fixer_clusters, paused_clusters); paused = repeat_count >= AUTO_PAUSE_REPEATS."""
    from pathlib import Path as _Path
    p = _Path(ledger_path).expanduser()
    counts: dict = {}
    if p.is_file():
        for row in round_rows(p.read_text(encoding="utf-8"), rnd):
            if row.get("phase", "").upper() != phase.strip().upper() or is_pending(row.get("address", "")):
                continue
            sig = row_sig(row.get("root_cause", ""))
            if sig is not None:
                counts[sig] = counts.get(sig, 0) + 1
    fixer, paused = [], []
    for c in clusters:
        annotated = dict(c)
        annotated["repeat_count"] = counts.get(cluster_sig(c), 0)
        (paused if annotated["repeat_count"] >= AUTO_PAUSE_REPEATS else fixer).append(annotated)
    return fixer, paused


def auto_pause_report(paused: list) -> list:
    """The `auto_pause` output entries for clusters split_repeat_clusters paused."""
    return [
        {
            "cluster":      c["cluster"],
            "flags":        c.get("flags", []),
            "repeat_count": c["repeat_count"],
            "reason":       (
                f"Cluster {c['cluster']} has been addressed "
                f"{c['repeat_count']} time(s) this round without convergence."
            ),
        }
        for c in paused
    ]


def auto_pause_then(rerun: str) -> str:
    """The `then` instruction for an auto_pause result; *rerun* names what to re-run once the pauses
    are resolved."""
    return (
        f"auto_pause lists clusters already addressed {AUTO_PAUSE_REPEATS} times this round: each is "
        "written as an open "
        "ORCHESTRATOR-PAUSE row. Resolve each by deciding a DIFFERENT intent-preserving fix from the "
        "target's README `## Intent` (a fix that is not sticking needs a different approach), apply it, "
        "and append a row whose Address says 'resolves ORCHESTRATOR-PAUSE <flag>' (append_ledger.py "
        "check-pauses must exit 0 before the round closes). No fixer is dispatched for these clusters: "
        f"once the pauses are resolved, {rerun}"
    )


def write_pause_rows(ledger_path: "Path | str", runtime: str, rnd: int, phase: str, paused: list,
                     row_sig, cluster_sig) -> None:
    """Write each paused cluster as an open ORCHESTRATOR-PAUSE row of *phase* (via ledger_cascade.py
    cluster mode), so the pause is a real ledger decision append_ledger.py check-pauses sees (the
    No-orphan-flag invariant). Idempotent on resume: a signature that already has an unresolved pause
    row of *phase* this round is not paused a second time. Raises RuntimeError on a writer failure."""
    from pathlib import Path as _Path
    p = _Path(ledger_path).expanduser()
    already_open: set = set()
    if p.is_file():
        text = p.read_text(encoding="utf-8")
        open_keys = {(q["round"], q["cluster"]) for q in unresolved_pauses(text) if q["round"] == rnd}
        for row in round_rows(text, rnd):
            if (rnd, row["cluster"]) in open_keys and row["phase"] == phase.strip().upper():
                sig = row_sig(row.get("root_cause", ""))
                if sig is not None:
                    already_open.add(sig)
    cascade = _Path(__file__).resolve().parent / "ledger_cascade.py"
    for c in paused:
        if cluster_sig(c) in already_open:
            continue
        address = (
            f"ORCHESTRATOR-PAUSE (cluster signature addressed {c['repeat_count']} time(s) this round "
            f"and re-appeared; the same fix is not sticking, decide a different approach)"
        )
        proc = subprocess.run(
            [sys.executable, str(cascade), str(p), "--runtime", runtime, "--round", str(rnd),
             "--mode", "cluster", "--phase", phase, "--address", address],
            input=json.dumps({"clusters": [c], "blast": []}), capture_output=True, text=True,
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"ledger_cascade cluster (ORCHESTRATOR-PAUSE rows) exited {proc.returncode}\n"
                f"stderr: {proc.stderr.strip()}\nstdout: {proc.stdout.strip()}"
            )


# ---------------------------------------------------------------------------
# Small shared conventions (one home each, imported by every script that needs them)
# ---------------------------------------------------------------------------

LEDGER_TABLE_HEADER = (
    "| Runtime | Round | Phase | Cluster | Root cause | Address | Flags |\n"
    "|---------|-------|-------|---------|------------|---------|-------|\n"
)


def ledger_header(skill: str, marker: str, target: "str | None" = None) -> str:
    """Text of a brand-new ledger: title, the `target::` line when *target* is given (the absolute
    path the ledger belongs to, see ledger_target), in-flight marker (without the `in-flight:: `
    prefix) and the empty 7-column table. The one place a ledger's text is built, so every creator
    writes the same header. Both creators (append_ledger.py begin-round and prepass_run.py) pass
    *target*; ledger_cascade.py never creates a ledger. A call without *target* yields the legacy
    header that begin-round later completes with write_ledger_target."""
    target_line = f"target:: {target}\n\n" if target else ""
    return f"# Audit ledger — {skill}\n\n{target_line}in-flight:: {marker}\n\n{LEDGER_TABLE_HEADER}"


# Ledger identity. The ledger file is named from the target's basename only, so two targets with the
# same directory name map to the same <ledger>. The header's `target::` line records the absolute
# target path the ledger belongs to; append_ledger.py begin-round writes it and refuses a different
# target, so one target's rows never feed another's run.
TARGET_RE = re.compile(r"^target::[ \t]*(.*?)[ \t]*$", re.MULTILINE)


def ledger_target(text: str) -> "str | None":
    """The absolute target path recorded on the ledger's `target::` line, or None (a legacy ledger
    written before the line existed)."""
    m = TARGET_RE.search(text)
    return m.group(1) if m and m.group(1) else None


def write_ledger_target(ledger_path: "Path | str", target: str) -> None:
    """Record *target* on the ledger's `target::` line (inserted after the title when absent, the
    same placement write_run_options uses). Used for a legacy ledger that has no recorded target."""
    from pathlib import Path as _Path
    p = _Path(ledger_path).expanduser()
    text = p.read_text(encoding="utf-8")
    line = f"target:: {target}"
    updated, n = TARGET_RE.subn(line, text)
    if n == 0:
        lines = text.splitlines(keepends=True)
        lines.insert(1 if lines else 0, f"\n{line}\n")
        updated = "".join(lines)
    p.write_text(updated, encoding="utf-8")


def is_pending(address: str) -> bool:
    """True iff *address* is a not-yet-filled placeholder (`PENDING` or `PENDING (considered-fix)`)."""
    a = address.strip()
    return a == "PENDING" or a.startswith("PENDING ") or a.startswith("PENDING(")


def runtime_slug(runtime: str) -> str:
    """The filename-safe form of a `<Runtime>` (`:` -> `-`). Every staged / tmp file name that carries a
    run identity uses this form, and cleanup_tmp_prompts.py normalises its argument with it, so a
    `<Runtime>` with colons and its slug both select the same files."""
    return runtime.replace(":", "-")


def run_tmp_path(out_dir, stem: str, runtime: str, suffix: str = ".json"):
    """Path of a per-run tmp file in `out_dir`: `<stem>-<RUN_TIMESTAMP><suffix>`. `<out-dir>` is shared
    by every invocation, so a tmp name without the run's slug can collide with a concurrent run's file
    and is never selected by cleanup_tmp_prompts.py's `--run-timestamp` scoping."""
    from pathlib import Path as _Path
    return _Path(out_dir) / f"{stem}-{runtime_slug(runtime)}{suffix}"


# Fixer batching (SKILL.md "Fixer dispatch"): a round of at most FIXER_BATCH_MAX_CLUSTERS clusters goes
# to one fixer; only a larger round is split into sequential fixers of at most that many clusters each.
# Observed in the October 2026 trim comparison: one fixer given 17 to 22 clusters with the interface open
# added helpers, fields and a row kind that the next round flagged; in the trim-plus comparison, splitting
# a round of 12 or fewer into a code and a doc fixer about doubled fixer tokens (both re-read the whole
# skill) with no quality gain.
FIXER_BATCH_MAX_CLUSTERS = 12


def cluster_files(cluster: dict, blast_entry: "dict | None" = None) -> list:
    """The file parts a cluster names: its `file` (Prepass), each member's `loc` (Code Review) and its
    blast entry's `radius`, `doc_sites` and (TOKEN-BLAST) `uncovered` entries, each with any `:<line>`
    suffix removed."""
    locs = [cluster.get("file") or ""] + [m.get("loc") or "" for m in cluster.get("members") or []]
    for key in ("radius", "doc_sites", "uncovered"):
        locs += [x for x in (blast_entry or {}).get(key) or [] if isinstance(x, str)]
    return [loc.split(":", 1)[0] for loc in locs if loc]


def cluster_touches_code(cluster: dict, blast_entry: "dict | None" = None) -> bool:
    """True when the cluster names a .py file (a script or detector), else it is doc-only."""
    return any(f.endswith(".py") for f in cluster_files(cluster, blast_entry))


def fixer_model(clusters: list, blast: "list | None" = None) -> str:
    """The model for one fixer batch: opus when any cluster touches a .py file, sonnet when every
    cluster is doc-only (.md / .json). Single source for the rule SKILL.md states."""
    by_id = {b.get("cluster"): b for b in blast or [] if isinstance(b, dict)}
    return "opus" if any(cluster_touches_code(c, by_id.get(c.get("cluster"))) for c in clusters) else "sonnet"


def fixer_batches(clusters: list, blast: "list | None" = None) -> list:
    """Split a round's clusters into fixer batches.

    Clusters that touch code come first and doc-only clusters after them, each group in its given
    order. A round of at most FIXER_BATCH_MAX_CLUSTERS clusters is one batch (opus when any cluster
    touches a .py file, else sonnet). Only a larger round is split, each group into batches of at
    most FIXER_BATCH_MAX_CLUSTERS, so doc-only batches can use sonnet and run after the code edits.
    Returns [{"batch": k, "clusters": [...], "blast": [...], "model": "opus"|"sonnet"}], k from 1."""
    by_id = {b.get("cluster"): b for b in blast or [] if isinstance(b, dict)}
    code = [c for c in clusters if cluster_touches_code(c, by_id.get(c.get("cluster")))]
    docs = [c for c in clusters if not cluster_touches_code(c, by_id.get(c.get("cluster")))]
    out = []
    for group in ((code + docs,) if len(clusters) <= FIXER_BATCH_MAX_CLUSTERS else (code, docs)):
        for i in range(0, len(group), FIXER_BATCH_MAX_CLUSTERS):
            part = group[i:i + FIXER_BATCH_MAX_CLUSTERS]
            part_blast = [by_id[c.get("cluster")] for c in part if c.get("cluster") in by_id]
            out.append({"batch": len(out) + 1, "clusters": part, "blast": part_blast,
                        "model": fixer_model(part, part_blast)})
    return out


# Stop-seeding rule (references/how-to-fix.md "Frozen interface"): from round 1 of a run a fix may not
# widen the interface. Observed: in the October 2026 self-run 31% of rounds 4-8's flags were about
# machinery an earlier round's fixes had added; in the trim comparison, about three of round 2's flags
# were about helpers, fields and a row kind that round 1's fixer added while the interface was open.


def run_round(ledger_path: "Path | str", rnd: int) -> int:
    """*rnd* counted within the current run (round - run-start-round + 1, at least 1)."""
    from pathlib import Path as _Path
    p = _Path(ledger_path).expanduser()
    start = 1
    if p.is_file():
        try:
            start = int(parse_run_options(p.read_text(encoding="utf-8")).get("run-start-round", 1))
        except ValueError:
            start = 1
    return max(1, rnd - start + 1)


def interface_rule(run_rnd: int) -> str:
    """The considered-fix template's [INTERFACE_RULE] text for round *run_rnd* of the run (frozen
    in every round)."""
    return (f"Round {run_rnd} of this run: the interface is FROZEN (from round 1 of every run). Do NOT "
            "add a CLI flag, mode, subcommand, file, ledger field, run-options key, row kind, shared helper module or doc section. "
            "When the deepest root fix would need one, apply no edit for that cluster and emit "
            "ORCHESTRATOR-PAUSE naming the addition and the best non-widening fix. The one exception is "
            "a real behaviour bug (wrong output, wrong exit code, crash) that cannot be fixed any other "
            "way: then make the smallest such addition and say in the FIX address why no non-widening "
            "fix exists. When the behaviour is already correct and only a comment or doc is wrong, fix "
            "the comment or doc, not the code. A fixer adds no new behaviour: a fix makes the doc match the "
            "code, or the code match its documented contract. Adding a retry, cap, branch or exit path, or "
            "removing a fallback, is new behaviour: apply no edit for that cluster and emit "
            "ORCHESTRATOR-PAUSE naming it.")


def intent_source(skill_root: "Path | str") -> "Path":
    """The file whose `## Intent` (README.md) or frontmatter `description:` (SKILL.md) states the
    target's documented intent: README.md when present, else SKILL.md. When neither exists the README
    path is returned so the fixer's unreadable-path rule (templates/considered-fix.md) names it."""
    from pathlib import Path as _Path
    root = _Path(skill_root).expanduser()
    for name in ("README.md", "SKILL.md"):
        if (root / name).is_file():
            return root / name
    return root / "README.md"


# --- Advisory blast groups (shared by code_review_collect.py and cluster_enforce.py) ---
# First `:<digits>` line-locus token in a claim/target.
_LOCUS_LINE_RE = re.compile(r":(\d+)")


def normalize_loc(file_str: str, claim_str: str, target_str: str) -> str:
    """Dedup key for a finding, so the SAME defect raised by different agents collapses together.

    PATH: agents cite files as absolute or relative paths, so key on the BASENAME.
    LOCUS: agents describe one defect in different prose, so key on basename + the first `:<line>`
    token in the claim (then the target); with no line cited fall back to basename + a short target
    signature (the reviewer template requires a `<file>:<line>` locus in Claim)."""
    import os
    base = os.path.basename(file_str.strip().rstrip("/")).lower()
    m = _LOCUS_LINE_RE.search(claim_str or "") or _LOCUS_LINE_RE.search(target_str or "")
    if m:
        return f"{base}|L{m.group(1)}"
    return f"{base}|{(target_str or '').strip().lower()[:60]}"


# A `<relfile>:<line>` (or `:<line>-<line>`) locus at the head of a Claim, past any leading
# quote/emphasis characters — the reviewer template requires Claim to lead with one.
_CLAIM_LOCUS_RE = re.compile(r"^[\s`*_(]*(?P<loc>[^\s:\"'`]+:\d+(?:-\d+)?)")
# Any `<relfile>:<line>` locus anywhere in a free-text field (fallback for a Claim without one).
_ANY_LOCUS_RE = re.compile(r"(?P<loc>[A-Za-z0-9_./\-]+\.[A-Za-z0-9]+:\d+(?:-\d+)?)")


def flag_locus(file_str: str, claim_str: str, target_str: str) -> str:
    """The `<relfile>:<line>` site of a code-review finding: the locus the Claim leads with, else the
    first locus cited in the Target, else the bare File. Never joins File with free prose, so a
    cluster's radius and root cause list file:line sites a fixer can open."""
    m = _CLAIM_LOCUS_RE.match(claim_str or "") or _ANY_LOCUS_RE.search(target_str or "")
    if m:
        return m.group("loc")
    return (file_str or "").strip() or "?"


def compute_advisory_groups(findings: list) -> list:
    """Advisory token-blast groups over verified flags: [{group: [flag_id, ...], shared: <key>}, ...]
    for every group of >= 2 flags sharing a token, or (no token) a normalised file:line locus.
    code_review_collect.py reports them; cluster_enforce.py refuses to split one."""
    from collections import defaultdict
    key_to_flags: dict = defaultdict(list)
    key_label: dict = {}
    for f in findings:
        flag_id = f.get("agent_flag", "?")
        token = f.get("token", "").strip()
        if token:
            key = f"token:{token}"
            key_label[key] = token
        else:
            norm = normalize_loc(f.get("file", ""), f.get("claim", ""), f.get("target", ""))
            key = f"loc:{norm}"
            key_label[key] = norm
        key_to_flags[key].append(flag_id)
    return [{"group": fids, "shared": key_label.get(key, key)}
            for key, fids in key_to_flags.items() if len(fids) >= 2]


# ---------------------------------------------------------------------------
# Shared helper (a): write_marker
# ---------------------------------------------------------------------------

def write_marker(ledger_path: "Path | str", marker_str: str) -> None:
    """Overwrite the in-flight:: line in *ledger_path* with *marker_str*.

    If the ledger has no in-flight:: line, inserts one after the first line (the
    header).  The marker_str should NOT include the 'in-flight:: ' prefix — this
    helper prepends it.

    Raises FileNotFoundError when the ledger does not exist: the marker is the
    resume record, so a caller must never report a phase as advanced when no
    marker was written (references/script-contract.md "Broken ledger"). The
    ledger is created by `append_ledger.py begin-round`, or by prepass_run.py
    before its first sweep when no begin-round ran; never here.

    The single implementation; every script calls it directly.
    """
    from pathlib import Path as _Path
    p = _Path(ledger_path).expanduser()
    if not p.is_file():
        raise FileNotFoundError(f"ledger not found, cannot write in-flight marker: {p}")
    text = p.read_text(encoding="utf-8")
    updated, n = IN_FLIGHT_RE.subn(f"in-flight:: {marker_str}", text)
    if n == 0:
        lines = text.splitlines(keepends=True)
        insert_at = 1 if lines else 0
        lines.insert(insert_at, f"\nin-flight:: {marker_str}\n")
        updated = "".join(lines)
    p.write_text(updated, encoding="utf-8")


# ---------------------------------------------------------------------------
# Shared helper (b): extract_final_assistant_text
# ---------------------------------------------------------------------------

def extract_final_assistant_text(transcript_path: "Path | str") -> str:
    """Extract the concatenated text of the LAST non-empty assistant message
    in a JSONL transcript.

    The transcript is a JSONL file where each line is a JSON object.  Assistant
    messages have type == "assistant" and message.role == "assistant".  The
    content field is either a plain string or a list of content blocks; blocks
    with type == "text" carry the text.  Collects all non-empty assistant text
    messages, returns the LAST one.

    Raises ValueError when no non-empty assistant text message is found.
    Each caller performs its OWN downstream parsing (fence-stripping, JSON
    array extraction, sentinel checking, etc.) after calling this helper.
    """
    from pathlib import Path as _Path
    p = _Path(transcript_path).expanduser()
    lines_raw = p.read_text(encoding="utf-8").splitlines()
    assistant_texts: list[str] = []
    for raw in lines_raw:
        raw = raw.strip()
        if not raw:
            continue
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if obj.get("type") != "assistant":
            continue
        msg = obj.get("message", {})
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content", "")
        text = ""
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text += block.get("text", "")
                # Under the Claude desktop harness a subagent often delivers its final answer by
                # calling the SubagentHandback tool, so the answer is a tool_use input, not a text
                # block (observed: 8 of 17 cold agents in the October 2026 self-run). Treat that
                # message as the agent's final text; transcript order decides which is last.
                elif (isinstance(block, dict) and block.get("type") == "tool_use"
                      and block.get("name") == "SubagentHandback"
                      and isinstance(block.get("input"), dict)):
                    handback = block["input"].get("message", "")
                    if isinstance(handback, str) and handback.strip():
                        text += handback
        if text.strip():
            assistant_texts.append(text)

    if not assistant_texts:
        raise ValueError(
            f"No non-empty assistant text messages found in transcript: {p}"
        )
    return assistant_texts[-1]


# ---------------------------------------------------------------------------
# Shared helper (c): stage_fixer_prompt
# ---------------------------------------------------------------------------

def stage_fixer_prompt(
    *,
    clusters: list,
    blast: list,
    skill_root: "Path | str",
    rnd: int,
    runtime: str,
    out_dir: "Path | str",
    label: str,
    run_rnd: "int | None" = None,
) -> str:
    """Stage the fixer prompt by invoking assemble_fix_prompt.py and return
    the staged file path.

    Parameters
    ----------
    clusters    : list of cluster dicts (passed as --cluster-json)
    blast       : list of blast dicts (passed as --blast-json)
    skill_root  : path to the target skill directory
    rnd         : audit round number
    runtime     : runtime tag string (YYYY-MM-DDTHH:MM:SS; the minute form is also accepted)
    out_dir     : scratch directory for temp + output files
    label       : fixer label, e.g. "code-review"
    run_rnd     : round number within this run (run_round); selects [INTERFACE_RULE]

    Writes cluster_tmp + blast_tmp, invokes assemble_fix_prompt.py, cleans
    up temps, and returns the staged prompt path.

    Raises RuntimeError on subprocess failure or empty output path.
    """
    from pathlib import Path as _Path
    _here = _Path(__file__).resolve().parent
    _root = _here.parent

    skill_root = _Path(skill_root).expanduser().resolve()
    out_dir    = _Path(out_dir).expanduser()

    assemble_fix = _here / "assemble_fix_prompt.py"
    template_fix = _root / "templates" / "considered-fix.md"
    how_to_fix   = _root / "references" / "how-to-fix.md"
    readme       = intent_source(skill_root)

    pfx = label.replace("-", "")  # e.g. "codereview"
    cluster_tmp = run_tmp_path(out_dir, f".{pfx}-clusters-r{rnd}", runtime)
    blast_tmp   = run_tmp_path(out_dir, f".{pfx}-blast-r{rnd}", runtime)
    cluster_tmp.write_text(json.dumps({"clusters": clusters}, indent=2), encoding="utf-8")
    blast_tmp.write_text(json.dumps({"blast_radius": blast}, indent=2), encoding="utf-8")

    cmd = [
        sys.executable, str(assemble_fix),
        "--cluster-json",  str(cluster_tmp),
        "--blast-json",    str(blast_tmp),
        "--readme-path",   str(readme),
        "--skill-root",    str(skill_root),
        "--round",         str(rnd),
        "--template",      str(template_fix),
        "--howtofix-path", str(how_to_fix),
        "--out-dir",       str(out_dir),
        "--runtime",       runtime,
        "--label",         label,
        "--run-round",     str(run_rnd or rnd),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)

    for p in (cluster_tmp, blast_tmp):
        try:
            p.unlink()
        except OSError:
            pass

    if proc.returncode != 0:
        raise RuntimeError(
            f"assemble_fix_prompt exited {proc.returncode}\n"
            f"stderr: {proc.stderr.strip()}\nstdout: {proc.stdout.strip()}"
        )

    staged = proc.stdout.strip()
    if not staged:
        raise RuntimeError("assemble_fix_prompt produced no output path.")
    return staged


def stage_fixer_batches(*, clusters: list, blast: list, label: str, **kw) -> list:
    """Split *clusters* with fixer_batches and stage one fixer prompt per batch (stage_fixer_prompt,
    label `<label>-b<k>`). Returns the batches, each with its `staged_prompt` path; the other keyword
    arguments are stage_fixer_prompt's."""
    batches = fixer_batches(clusters, blast)
    for b in batches:
        b["staged_prompt"] = stage_fixer_prompt(clusters=b["clusters"], blast=b["blast"],
                                                label=f"{label}-b{b['batch']}", **kw)
    return batches


def batch_report(batches: list) -> list:
    """The per-batch summary a tier script prints: batch number, model, cluster ids, staged prompt."""
    return [{"batch": b["batch"], "model": b["model"], "clusters": [c.get("cluster") for c in b["clusters"]],
             "staged_prompt": b.get("staged_prompt")} for b in batches]


def fixer_decisions(transcript_path: "Path | str") -> list:
    """The `decisions` list of a fixer's final message (extract_final_assistant_text), with an optional
    ```json fence stripped. Raises FileNotFoundError / OSError for an unreadable transcript and
    ValueError when the final message is missing, is not JSON, or is not an object (an object with
    no `decisions` key gives []). Shared by ledger_cascade.py fill-address and check_decisions.py."""
    stripped = extract_final_assistant_text(transcript_path).strip()
    if stripped.startswith("```"):
        lines_t = stripped.splitlines()
        inner = "\n".join(lines_t[1:-1]) if lines_t[-1].strip() == "```" else "\n".join(lines_t[1:])
        stripped = inner.strip()
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise ValueError(f"fixer transcript final message is not valid JSON: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("decisions", []), list):
        raise ValueError('fixer final message is not an object with a "decisions" list')
    return data.get("decisions", [])


# ---------------------------------------------------------------------------
# Run options (persisted in the ledger header) and the round gate
# ---------------------------------------------------------------------------
# WHY: the round budget used to live only in the orchestrator's memory, so a compaction mid-run could
# silently turn `--rounds N` into an unbounded run. It now lives on one ledger header line,
# `run-options:: key=value ...`, written at run start and re-read on every invocation. The round gate
# (`round_gate`) is the mechanical stop rule: it does NOT depend on cold agents finding nothing — a hard
# cap, the requested budget and a stall test each stop the run.
#
# Format version 2 (3.1.0-trim) has only the three keys below. Legacy compatibility: version 1 also
# carried `mode=` and `cr-mode=`; parse_run_options migrates them (LEGACY_RUN_OPTION_KEYS) and the next
# write drops them.

RUN_OPTIONS_RE = re.compile(r"^run-options::[ \t]*(.*)$", re.MULTILINE)
DEFAULT_MAX_ROUNDS = 8       # hard cap on rounds in one run; overridable with max-rounds=
STALL_WINDOW = 3             # stalled = the last 3 closed rounds never beat the best earlier count
RUN_OPTION_KEYS = ("rounds-budget", "max-rounds", "run-start-round")
# Legacy compatibility, version-1 keys: `cr-mode` (only `generalist` remains, so it carries nothing) is dropped; `mode=one-round`
# meant one round then stop, which is `rounds-budget=1`; every other `mode` value is dropped
# (`verify-only` has no successor: a run always applies its fixes).
LEGACY_RUN_OPTION_KEYS = ("mode", "cr-mode")


def parse_run_options(text: str) -> dict:
    """The ledger's run-options line as {key: str} in format version 2; {} when absent. Version-1 keys
    are migrated (see LEGACY_RUN_OPTION_KEYS) rather than returned."""
    m = RUN_OPTIONS_RE.search(text)
    if not m:
        return {}
    out = {}
    for tok in m.group(1).split():
        if "=" in tok:
            k, v = tok.split("=", 1)
            out[k] = v
    # Legacy compatibility: migrate the version-1 keys.
    legacy_mode = out.pop("mode", None)
    out.pop("cr-mode", None)
    if legacy_mode == "one-round" and "rounds-budget" not in out:
        out["rounds-budget"] = "1"
    return out


# Options round_gate() reads with int(); each must be a positive integer.
_INT_RUN_OPTION_KEYS = ("rounds-budget", "max-rounds", "run-start-round")


def validate_run_options(options: dict) -> None:
    """Raise ValueError for an unknown key or a non-positive-integer value. An empty value (key
    removal) is always valid. Validating at write time keeps round_gate() from crashing on a stored
    value it cannot parse."""
    bad = [k for k in options if k not in RUN_OPTION_KEYS]
    if bad:
        # Legacy compatibility: name the removed version-1 keys in the refusal.
        hint = (" (`mode` and `cr-mode` were removed in 3.1.0-trim: use --rounds 1 for one round)"
                if any(k in LEGACY_RUN_OPTION_KEYS for k in bad) else "")
        raise ValueError(f"unknown run option(s) {bad}; allowed {RUN_OPTION_KEYS}{hint}")
    for k, v in options.items():
        v = str(v)
        if v == "":
            continue
        if k in _INT_RUN_OPTION_KEYS and not (v.isdigit() and int(v) >= 1):
            raise ValueError(f"{k}={v!r} must be a positive integer")


def write_run_options(ledger_path: "Path | str", options: dict) -> dict:
    """Merge *options* into the ledger's run-options:: line (insert after the header when absent).
    Invalid options are rejected (validate_run_options); `key=` (empty value) removes that key.
    The line is always rewritten in format version 2. Returns the merged dict."""
    from pathlib import Path as _Path
    validate_run_options(options)
    p = _Path(ledger_path).expanduser()
    text = p.read_text(encoding="utf-8")
    merged = parse_run_options(text)
    for k, v in options.items():
        # An empty value removes the key: a fresh run on an existing ledger must be able to drop a
        # previous run's rounds-budget / max-rounds, which a merge-only update could never clear.
        if str(v) == "":
            merged.pop(k, None)
        else:
            merged[k] = str(v)
    line = "run-options:: " + " ".join(f"{k}={merged[k]}" for k in RUN_OPTION_KEYS if k in merged)
    updated, n = RUN_OPTIONS_RE.subn(line, text)
    if n == 0:
        lines = text.splitlines(keepends=True)
        lines.insert(1 if lines else 0, f"\n{line}\n")
        updated = "".join(lines)
    p.write_text(updated, encoding="utf-8")
    return merged


def closed_round_counts(text: str) -> list[tuple[int, int]]:
    """[(round, raw_flag_count)] for every closed round (summary comment), ascending, deduplicated."""
    seen = {}
    for m in SUMMARY_RE.finditer(text):
        seen[int(m.group(1))] = int(m.group(2))
    return sorted(seen.items())


def round_gate(text: str, current_round: int) -> dict:
    """Mechanical stop rule, evaluated after round *current_round* is closed without convergence.
    Returns {"continue": bool, "stop": None | "round-cap" | "budget-exhausted" | "stalled", "detail": str}.
    A stop here means NOT CONVERGED: the run ended by rule, never because the skill is verified clean."""
    opts = parse_run_options(text)
    cap = int(opts.get("max-rounds", DEFAULT_MAX_ROUNDS))
    start = int(opts.get("run-start-round", 1))
    rounds_this_run = current_round - start + 1
    # The requested budget is checked before the cap so that a `--rounds N` run whose N equals
    # max-rounds reports the more specific reason (the user's request completed) instead of round-cap.
    if "rounds-budget" in opts and rounds_this_run >= int(opts["rounds-budget"]):
        return {"continue": False, "stop": "budget-exhausted",
                "detail": f"requested --rounds {opts['rounds-budget']} completed"}
    if rounds_this_run >= cap:
        return {"continue": False, "stop": "round-cap",
                "detail": f"{rounds_this_run} rounds this run reached the hard cap of {cap}"}
    counts = [c for r, c in closed_round_counts(text) if r >= start and r <= current_round]
    if len(counts) > STALL_WINDOW and min(counts[-STALL_WINDOW:]) >= min(counts[:-STALL_WINDOW]):
        return {"continue": False, "stop": "stalled",
                "detail": f"raw flag counts {counts}: the last {STALL_WINDOW} rounds never beat the "
                          f"best earlier round ({min(counts[:-STALL_WINDOW])}); fixes are not converging"}
    return {"continue": True, "stop": None, "detail": f"raw flag counts so far {counts}"}
