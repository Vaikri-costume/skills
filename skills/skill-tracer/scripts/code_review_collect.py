#!/usr/bin/env python3
"""code_review_collect.py — Code-Review stage MIDDLE.

Reads the reviewer agents' transcripts (one per flag: G1,G2 for the two generalists),
verifies each one's output contract and Read coverage, assigns per-agent flags, computes the
advisory blast groups and emits the verified flags. It writes NO ledger rows and stages NO fixer:
clustering, PENDING rows and fixer staging are cluster_enforce.py's job, after the orchestrator
clusters the verified flags by root cause.

Args:
    --agent-transcripts  Comma-separated JSONL paths (one per agent, in --agent-flags order), or a
                         directory of *.jsonl files.
    --agent-flags        Comma-separated flags in the same order as --agent-transcripts
                         (default: G1,G2).
    --target             Skill directory.
    --ledger             Path to the audit ledger.
    --round              Audit round number (int).
    --runtime            Runtime tag (YYYY-MM-DDTHH:MM:SS; the minute form is also accepted).
    --out-dir            Scratch directory (holds code_review_run.py's cr-scope-<N>-<RUN_TIMESTAMP>.json).

Behavior (in order):
  (a) VERIFY — extract ISSUE blocks from each transcript, validate:
        - ISSUE-block format per ledger_common.ISSUE_RE
        - trailing sentinel: 'No issues found' (N = 0) OR 'No of issues found:: N'
        - the complete ISSUE blocks that do not open by retracting themselves ("Considered and
          rejected — …") must number EXACTLY N. Fewer is a truncation; more is ambiguous about
          which finding the agent withdrew, so no block is dropped by position: either is a
          contract violation and the agent is asked to re-emit.
      A transcript that violates the contract → print error naming the agent
      + exit non-zero so the orchestrator SendMessages that agent to reformat.
      A transcript ending in the template's `ABORTED — missing files: …` line → exit 1 with
      `aborted_agents` on stderr: a hard error, never sent to the reformat recovery.
      COVERAGE — each agent's Read calls must cover every line of every file in the review scope
        (the cr-scope record code_review_run.py wrote; every in-scope file when it is absent).
  (b) CLEAN — if ALL agents returned zero ISSUE blocks, write no rows and exit 0 with:
        full scope    → {"status":"code-review-clean","next":"converged-if-no-flags-this-sweep"}
        changed scope → {"status":"changed-scope-clean","next":"full-sweep"}: not convergence; the
                        orchestrator re-runs code_review_run.py --scope full in the same round.
  (c) FLAGS — assign per-agent flags continuing in-round:
        each agent's findings get ITS flag prefix (G1.., G2..),
        numbered from max_flag_in_round(ledger, rnd, prefix)+1.
        Independent per-prefix sequences.
  (d) ADVISORY BLAST GROUPS — compute advisory token-blast groupings over
        all verified flags (group by shared token or shared file:line region)
        with ledger_common.compute_advisory_groups. Advisory only: the orchestrator may
        merge groups; cluster_enforce.py enforces that no advisory group is split across
        orchestrator clusters.
  (e) EMIT verified-flags JSON:
        {"status":"verified-flags","round":N,"flags":[...],"blast_advisory":[...],"then":[...]}
        The "then" instructs the orchestrator to cluster by root cause, write
        cr-clusters-<N>-<RUN_TIMESTAMP>.json, and run cluster_enforce.py on this JSON (SKILL.md saves
        stdout to cr-verified-<N>-<RUN_TIMESTAMP>.json).

Pure stdlib. Python 3.9+.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import List, Dict, Any, Tuple

# ---------------------------------------------------------------------------
# Bootstrap: ensure scripts/ dir is on sys.path
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent

if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import ledger_common as lc
from coverage_check import read_coverage  # noqa: E402 — coverage enforcer

# Default agent flags in order (the two generalists code_review_run.py dispatches)
_DEFAULT_AGENT_FLAGS = ["G1", "G2"]

# ---------------------------------------------------------------------------
# ISSUE-block extraction from a single cold-agent transcript
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# ISSUE-block parser
#
# Each block MUST match:
#   ISSUE [<tag>]: <title>
#   File: <file>
#   Claim: <claim>
#   Target: <target>
#
# We parse using a multi-line regex so we can pull out all four fields.
# lc.ISSUE_RE is used for the authoritative COUNT (it is the shared single
# source of truth for issue-block counting); we extend it here for field
# extraction.
# ---------------------------------------------------------------------------

# Captures the four mandatory ISSUE-block fields.
_ISSUE_BLOCK_RE = re.compile(
    r"ISSUE\s+\[(?P<tag>[^\]]+)\]\s*:[^\n]*\n"   # ISSUE [tag]: title line
    r"(?:.*?\n)*?"                                  # optional intervening lines
    r"File:\s*(?P<file>[^\n]+)\n"
    r"(?:.*?\n)*?"
    r"Claim:\s*(?P<claim>[^\n]+)\n"
    r"(?:.*?\n)*?"
    r"Target:\s*(?P<target>[^\n]+)",
    re.MULTILINE,
)


# Self-retraction: a block whose Target:/Claim: text OPENS with a retraction phrase ("Considered and
# rejected — ... not a finding."). Anchored at the start of the field (after an optional
# `<relfile>:<line>` locus in Claim; a quote mark before the phrase means it is quoted, not asserted) so a legitimate finding that merely QUOTES one of these
# phrases (e.g. a finding about append_ledger's banned vocabulary or the reviewer template's
# "withdrawn / retracted" rule) is never dropped.
_RETRACTION_RE = re.compile(
    r"^[\s(*_]*(?:\S+:\d+(?:-\d+)?[\s:\u2014\u2013-]+)?"
    r"(?:considered and rejected|not a finding|no defect found|withdrawn|withdrawing)\b",
    re.IGNORECASE,
)


def _is_self_retracted(block: Dict[str, str]) -> bool:
    """True if a block's own Target/Claim text opens by retracting the finding.

    An agent can write a block whose Target: field explicitly says the
    finding was reconsidered and rejected ("Considered and rejected — ...
    not a finding.") without removing the block itself. Pure
    trailing-position selection (last N blocks) has no way to see this
    content, so it can keep a self-retracted block while dropping a genuine
    earlier one that falls outside the trailing window.
    """
    return any(_RETRACTION_RE.match(block.get(k, "") or "") for k in ("target", "claim"))


def _parse_issue_blocks(text: str) -> List[Dict[str, str]]:
    """Extract all ISSUE blocks from an agent report.

    Returns list of dicts with keys: tag, file, claim, target. An opener that cannot be
    parsed into all four required fields is left out of the list, not reported as an error;
    the caller detects it by comparing opener and block counts.
    """
    blocks: List[Dict[str, str]] = []
    for m in _ISSUE_BLOCK_RE.finditer(text):
        blocks.append({
            "tag":    m.group("tag").strip(),
            "file":   m.group("file").strip(),
            "claim":  m.group("claim").strip(),
            "target": m.group("target").strip(),
        })

    # An incomplete opener (an `ISSUE [` with no full File/Claim/Target) is not parsed here;
    # _verify_agent_transcript compares the raw opener count with the parsed blocks and treats
    # the difference as a malformed block.
    return blocks


class AgentAborted(Exception):
    """The agent ended with the template's pre-flight abort line
    (`ABORTED — missing files: <paths>`): files named in its staged `## Files` list do not exist.
    That is a staging/target problem, not an output-format violation, so it is reported apart from
    the malformed agents and never routed to the reformat recovery."""


_ABORTED_RE = re.compile(r"^\s*ABORTED\b")


def _verify_agent_transcript(
    transcript_path: Path,
    agent_prefix: str,
) -> Tuple[List[Dict[str, str]], int]:
    """Verify one agent transcript against the forced output contract.

    Returns (issue_blocks, surviving_count).
    Raises ValueError with an error message naming the agent if the contract
    is violated — caller must exit non-zero so the orchestrator asks the same agent
    (SendMessage its agentId) to re-emit its findings; it does not re-dispatch cold.

    Contract:
      1. The final assistant message must end with EITHER:
           'No issues found'               (N = 0)
         OR
           'No of issues found:: N'        (N findings)
      2. The complete ISSUE blocks (ISSUE / File: / Claim: / Target:) that do not open by
         retracting themselves number EXACTLY N.
    """
    agent_label = f"agent-{agent_prefix}"
    try:
        final_text = lc.extract_final_assistant_text(transcript_path)
    except ValueError as exc:
        raise ValueError(
            f"{agent_label} transcript extraction failed: {exc}\n"
            f"Path: {transcript_path}"
        )

    # Parse the sentinel (uses lc helpers — single source of truth)
    surviving = lc.surviving_issue_count(final_text)

    # Detect whether the sentinel is present at all (neither recognised form)
    nonempty_lines = [ln for ln in final_text.splitlines() if ln.strip()]
    last_line = nonempty_lines[-1] if nonempty_lines else ""
    if _ABORTED_RE.match(last_line):
        raise AgentAborted(f"{agent_label}: {last_line.strip()}")
    has_no_issues_sentinel = lc.NO_ISSUES_TAIL_RE.match(last_line) is not None
    has_count_sentinel      = lc.COUNT_TAIL_RE.match(last_line) is not None

    if not has_no_issues_sentinel and not has_count_sentinel:
        raise ValueError(
            f"{agent_label} output contract violated: missing trailing sentinel "
            f"('No issues found' or 'No of issues found:: N'). "
            f"RECOVERY: ask THIS agent to REFORMAT its existing findings to the exact label form (SendMessage the same agentId) — do NOT re-dispatch cold, which returns a different finding set and breaks the round's coherence.\n"
            f"Last line of response: {last_line!r}"
        )

    # Parse blocks (an unparseable opener is left out and counted as malformed below)
    blocks = _parse_issue_blocks(final_text)

    # The declared count is a contract (ledger_common.surviving_issue_count). A self-retracted block
    # ("Considered and rejected — …") is withdrawn by its own text, so it is not counted. Any other
    # mismatch is a violation: fewer blocks than declared is a truncation, and more is ambiguous —
    # nothing says WHICH block the agent meant to withdraw, and dropping the first ones by position
    # once lost a real finding (round 8 of the October 2026 self-run: 12 blocks, 11 declared).
    real_blocks = [b for b in blocks if not _is_self_retracted(b)]
    malformed = lc.count_issue_blocks(final_text) - len(blocks)
    if malformed > 0:
        raise ValueError(
            f"{agent_label} output contract violated: {malformed} ISSUE block(s) lack the exact "
            f"File: / Claim: / Target: lines (e.g. a parenthetical label such as `Claim (line N):`). "
            f"RECOVERY: ask THIS agent (SendMessage the same agentId) to re-emit every finding in the "
            f"exact four-line form — do NOT re-dispatch cold, which returns a different finding set."
        )
    if len(real_blocks) != surviving:
        kind = "fewer" if len(real_blocks) < surviving else "more"
        raise ValueError(
            f"{agent_label} output contract violated: the trailing line declares {surviving} "
            f"finding(s) but {len(real_blocks)} complete, non-retracted ISSUE block(s) parsed "
            f"({kind} than declared). RECOVERY: ask THIS agent (SendMessage the same agentId) to re-emit its "
            f"findings so the block count equals the trailing count — do NOT re-dispatch cold, which "
            f"returns a different finding set."
        )
    return real_blocks, surviving


# ---------------------------------------------------------------------------
# Flag numbering — delegates to lc.max_flag_in_round (shared helper)
# ---------------------------------------------------------------------------

def _assign_flags(
    blocks: List[Dict[str, str]],
    prefix: str,
    ledger_path: Path,
    rnd: int,
) -> List[Dict[str, str]]:
    """Assign per-agent flags (G11, G12… / G21…) to each block.

    Numbers continue from max already assigned for this prefix in this round
    (per lc.max_flag_in_round — shared single source of truth).

    Returns list of finding dicts, each adding 'agent_flag' key.
    """
    max_n = lc.max_flag_in_round(ledger_path, rnd, prefix)
    assigned: List[Dict[str, str]] = []
    for i, block in enumerate(blocks, start=1):
        finding = dict(block)
        finding["agent_flag"] = f"{prefix}{max_n + i}"
        assigned.append(finding)
    return assigned


# ---------------------------------------------------------------------------
# wc -l trailing-newline trap detector
#
# `wc -l` counts newline characters, so it undercounts by exactly 1 for any
# file that does not end with a trailing newline. An agent that determines
# its PRE-FLIGHT <line_count> via `wc -l` and then Reads with an explicit
# `limit` matching that count will genuinely never see the file's true final
# line — and since its own count is wrong the same way on every attempt, a
# resume that just says "read the uncovered range" doesn't fix it: the agent
# re-checks against the same wrong number and reports back "done." Detecting
# this exact shape lets the recovery message name the real cause (wc -l vs.
# no trailing newline) instead of leaving the orchestrator to grind through
# repeated blind resume cycles.
# ---------------------------------------------------------------------------

def _detect_wc_l_trap_files(
    gaps_by_file: Dict[str, List[List[int]]],
    per_file: Dict[str, Dict[str, Any]],
    skill_root: Path,
) -> List[str]:
    """Return the relpaths whose gap is exactly [linecount, linecount] on a
    file with no trailing newline — the signature of the wc -l undercount
    trap, not a genuine multi-line skip.
    """
    trapped: List[str] = []
    for rel, gaps in gaps_by_file.items():
        linecount = per_file.get(rel, {}).get("linecount")
        if linecount is None or gaps != [[linecount, linecount]]:
            continue
        try:
            text = (skill_root / rel).read_bytes()
        except OSError:
            continue
        if text and text[-1:] != b"\n":
            trapped.append(rel)
    return trapped


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Code-Review MIDDLE: verify each agent transcript (contract + Read coverage), "
            "assign flags, compute advisory blast groups, emit verified flags."
        )
    )
    ap.add_argument(
        "--agent-transcripts", required=True,
        help=(
            "Comma-separated paths to the agent JSONL transcripts (one per flag prefix), "
            "OR a directory of *.jsonl files."
        ),
    )
    ap.add_argument(
        "--agent-flags", default=",".join(_DEFAULT_AGENT_FLAGS),
        help=(
            "Comma-separated flag prefixes in the same order as --agent-transcripts "
            f"(default: {','.join(_DEFAULT_AGENT_FLAGS)})."
        ),
    )
    ap.add_argument("--target",  required=True, help="Target skill directory.")
    ap.add_argument("--ledger",  required=True, help="Path to the audit ledger.")
    ap.add_argument("--round",   required=True, type=int, help="Audit round number.")
    ap.add_argument("--runtime", required=True, help="Runtime tag (YYYY-MM-DDTHH:MM:SS; the minute form is also accepted).")
    ap.add_argument("--out-dir", required=True, help="Scratch directory (holds code_review_run.py's cr-scope-<N>-<RUN_TIMESTAMP>.json).")
    args = ap.parse_args()

    skill_root = Path(args.target).expanduser().resolve()
    ledger     = Path(args.ledger).expanduser()
    out_dir    = Path(args.out_dir).expanduser()
    rnd        = args.round
    runtime    = args.runtime

    if not skill_root.is_dir():
        print(
            json.dumps({"error": f"--target is not a directory: {skill_root}"}),
            file=sys.stderr,
        )
        return 2

    out_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Resolve transcript paths
    # ------------------------------------------------------------------
    raw_trans = args.agent_transcripts.strip()
    trans_spec = Path(raw_trans).expanduser()

    flag_prefixes = [l.strip() for l in args.agent_flags.split(",")]
    if len(flag_prefixes) < 1 or any(not f for f in flag_prefixes):
        print(
            json.dumps({
                "error": (
                    "--agent-flags must supply at least one flag (G1,G2 for the two "
                    f"generalists); got {args.agent_flags!r}"
                )
            }),
            file=sys.stderr,
        )
        return 2

    if trans_spec.is_dir():
        transcript_paths = sorted(trans_spec.glob("*.jsonl"))
    else:
        transcript_paths = [
            Path(p.strip()).expanduser() for p in raw_trans.split(",")
        ]

    # The transcript<->flag binding is positional, so the two counts must match.
    if len(transcript_paths) != len(flag_prefixes):
        print(
            json.dumps({
                "error": (
                    f"--agent-transcripts count ({len(transcript_paths)}) must equal "
                    f"--agent-flags count ({len(flag_prefixes)}); each transcript binds "
                    "positionally to one flag"
                )
            }),
            file=sys.stderr,
        )
        return 2

    for tp in transcript_paths:
        if not tp.is_file():
            print(
                json.dumps({"error": f"transcript not found: {tp}"}),
                file=sys.stderr,
            )
            return 2

    # ------------------------------------------------------------------
    # (a) VERIFY — extract and validate each agent transcript
    # ------------------------------------------------------------------
    agent_blocks: List[Tuple[str, List[Dict[str, str]]]] = []  # (prefix, blocks)
    all_malformed: List[str] = []
    aborted: List[str] = []

    for tp, prefix in zip(transcript_paths, flag_prefixes):
        try:
            blocks, _surviving = _verify_agent_transcript(tp, prefix)
            agent_blocks.append((prefix, blocks))
        except AgentAborted as exc:
            aborted.append(str(exc))
        except ValueError as exc:
            all_malformed.append(str(exc))

    # An aborted agent read nothing because its staged file list names files that do not exist.
    # No reformat or continue can repair that, so it is reported on its own, before (and instead
    # of) the contract and coverage gate: a hard unrecoverable error (SKILL.md "Stop rules", "Hard unrecoverable error").
    if aborted:
        print(json.dumps({
            "error": "One or more agents aborted at the pre-flight gate: files in the staged file "
                     "list do not exist.",
            "aborted_agents": aborted,
            "recovery": "Not a format violation: do NOT SendMessage a reformat and do NOT "
                        "re-dispatch. Stop and report the agents and the missing paths to the user "
                        "(hard unrecoverable error).",
        }, indent=2), file=sys.stderr)
        return 1

    # ------------------------------------------------------------------
    # (a2) COVERAGE — verify every agent Read-covered all in-scope lines
    #
    # Runs regardless of contract violations: coverage parsing inspects
    # Read tool-calls and is independent of the final-message output
    # format, so it is valid even on a contract-malformed transcript.
    # Both gates are collected before any return so the orchestrator can
    # fix all failures in a single recovery round.
    # ------------------------------------------------------------------
    incomplete_coverage: list[dict] = []
    # The review scope code_review_run.py staged (full or changed files); without its record the
    # gate checks every in-scope file, the strict choice.
    scope_name, scope_files = "full", None
    scope_record = lc.run_tmp_path(out_dir, f"cr-scope-{rnd}", runtime)
    if scope_record.is_file():
        try:
            rec = json.loads(scope_record.read_text(encoding="utf-8"))
            scope_name = rec.get("scope", "full")
            scope_files = [Path(f) for f in rec.get("files", [])] if scope_name == "changed" else None
        except (OSError, ValueError):
            scope_name, scope_files = "full", None

    for tp, prefix in zip(transcript_paths, flag_prefixes):
        try:
            cov = read_coverage(tp, skill_root, scope_files)
        except ValueError as exc:
            # Treat a coverage-check error as incomplete (conservative)
            incomplete_coverage.append({
                "agent": f"agent-{prefix}",
                "transcript": str(tp),
                "error": str(exc),
                "files_with_gaps": [],
                "gaps_by_file": {},
            })
            continue

        if not cov["covered"]:
            gaps_by_file: dict[str, list[list[int]]] = {
                rel: cov["per_file"][rel]["gaps"]
                for rel in cov["files_with_gaps"]
            }
            incomplete_coverage.append({
                "agent": f"agent-{prefix}",
                "transcript": str(tp),
                "files_with_gaps": cov["files_with_gaps"],
                "gaps_by_file": gaps_by_file,
                "wc_l_trap_files": _detect_wc_l_trap_files(gaps_by_file, cov["per_file"], skill_root),
            })

    # ------------------------------------------------------------------
    # Combined gate — report both contract and coverage failures together
    # so the orchestrator can fix everything in a single recovery round.
    # ------------------------------------------------------------------
    if all_malformed or incomplete_coverage:
        # Human-readable lines first
        # RECOVERY (orchestrator): for each malformed agent, ask THAT SAME
        # agent (SendMessage its agentId) to RE-EMIT its existing findings
        # reformatted to the exact label form — do NOT re-dispatch a fresh
        # cold agent. A cold re-read returns a DIFFERENT finding set
        # (cold-agent variance), which silently changes the round's coverage;
        # reformatting preserves the round's coherent finding set and only
        # fixes the contract violation.
        for msg in all_malformed:
            print(f"MALFORMED: {msg}", file=sys.stderr)

        recovery_lines: list[str] = []
        for entry in incomplete_coverage:
            agent_id = entry["agent"]
            if entry.get("error"):
                recovery_lines.append(
                    f"  {agent_id}: coverage check error — {entry['error']}"
                )
            else:
                trap_files = set(entry.get("wc_l_trap_files") or [])
                for rel, gaps in entry["gaps_by_file"].items():
                    gap_str = ", ".join(f"{s}-{e}" for s, e in gaps)
                    trap_note = (
                        " [wc -l TRAP: this file has no trailing newline, so `wc -l` "
                        "undercounts it by 1 — do not re-check by counting lines; "
                        "Read the file with NO offset/limit and re-emit]"
                        if rel in trap_files else ""
                    )
                    recovery_lines.append(
                        f"  {agent_id}: {rel} uncovered lines [{gap_str}]{trap_note}"
                    )
        for line in recovery_lines:
            print(line, file=sys.stderr)

        any_trap = any(entry.get("wc_l_trap_files") for entry in incomplete_coverage)

        # Single combined JSON error object
        print(
            json.dumps(
                {
                    "error": "One or more agent transcripts have contract violations "
                             "and/or incomplete Read coverage.",
                    "malformed_agents": all_malformed,
                    "incomplete_coverage": incomplete_coverage,
                    "recovery": (
                        "malformed_agents → ask each listed agent to REFORMAT its "
                        "existing findings to the exact label form (SendMessage the "
                        "same agentId); do NOT re-dispatch cold — that changes the "
                        "finding set. "
                        "incomplete_coverage → CONTINUE each listed agent "
                        "(SendMessage the same agentId): instruct it to Read the "
                        "uncovered ranges of the listed files, then re-emit its "
                        "COMPLETE findings — it stopped reading early and may surface "
                        "more. Do NOT re-dispatch cold."
                        + (
                            " Entries flagged 'wc -l TRAP' are the specific known "
                            "artifact where `wc -l` undercounts a file lacking a "
                            "trailing newline by 1 — the agent's own line count is "
                            "self-consistently wrong, so simply asking it to "
                            "re-verify will reproduce the identical gap. Instead, "
                            "explicitly tell it: re-Read this exact file with no "
                            "offset and no limit (do not size the call from a "
                            "wc -l count), then re-emit."
                            if any_trap else ""
                        )
                    ),
                },
                indent=2,
            ),
            file=sys.stderr,
        )
        return 1

    # ------------------------------------------------------------------
    # (b) CONVERGENCE — every agent returned zero surviving ISSUE blocks
    # ------------------------------------------------------------------
    total_findings = sum(len(blocks) for _, blocks in agent_blocks)

    if total_findings == 0:
        cleanup_step = (f"Remove this run's tmp artifacts: python3 .../scripts/cleanup_tmp_prompts.py --run-timestamp \"<RT>\" --dir <out-dir>  "
                        "(scoped to this run's <RUN_TIMESTAMP>; never --all).")
        if scope_name == "changed":
            print(json.dumps({
                "status": "changed-scope-clean",
                "next":   "full-sweep",
                "then": [
                    f"The changed-files review of round {rnd} is clean. That is NOT convergence: convergence is declared only by a clean full-sweep review.",
                    f"Run the confirming full sweep in the same round: python3 .../scripts/code_review_run.py --target <target> --ledger <ledger> --round {rnd} --runtime <RT> --out-dir <out-dir> --scope full, then dispatch and collect as before.",
                ],
            }))
            return 0
        print(json.dumps({
            "status": "code-review-clean",
            "next":   "converged-if-no-flags-this-sweep",
            "then": [
                "Run: python3 .../scripts/append_ledger.py check-pauses <ledger>; resolve any open pause first (orchestrator decides; promote to USER-PAUSE only if true user attention needed; append 'resolves ORCHESTRATOR-PAUSE <flag>').",
                cleanup_step,
                f"Then converge: python3 .../scripts/append_ledger.py close-round <ledger> --round {rnd} --converged. A clean full-sweep code-review is convergence: it is reachable only after a clean prepass in this same round (any prepass fix re-enters at prepass). The script writes the converged marker; never hand-edit it.",
            ],
        }))
        return 0

    # ------------------------------------------------------------------
    # (c) FLAGS — assign per-agent flags, independent per-prefix sequences
    # ------------------------------------------------------------------
    all_findings: List[Dict[str, str]] = []
    for prefix, blocks in agent_blocks:
        if not blocks:
            continue
        assigned = _assign_flags(blocks, prefix, ledger, rnd)
        all_findings.extend(assigned)

    # ------------------------------------------------------------------
    # (d) ADVISORY BLAST GROUPS — group verified flags by shared token
    #     (same token OR same file:line region → one advisory group).
    #     This is advisory only: the orchestrator reads this and clusters
    #     by root cause; cluster_enforce.py enforces that advisory groups
    #     are not split across orchestrator clusters.
    # ------------------------------------------------------------------
    blast_advisory = lc.compute_advisory_groups(all_findings)

    # ------------------------------------------------------------------
    # (e) EMIT verified-flags — orchestrator clusters next
    # ------------------------------------------------------------------
    result = {
        "status":        "verified-flags",
        "round":         rnd,
        "flags":         all_findings,
        "blast_advisory": blast_advisory,
        "then": [
            "Cluster these verified flags by ROOT CAUSE (merge findings that share a mechanism / must be fixed together). You MAY merge beyond the advisory groups; you may NOT split an advisory blast group. Optionally add a one-line `guidance` per cluster for the fixer.",
            f"Write your clusters to <out-dir>/cr-clusters-{rnd}-{lc.runtime_slug(runtime)}.json as {{\"clusters\":[{{\"cluster\":\"C#\",\"flags\":[...],\"guidance\":\"<optional>\"}}]}}.",
            f"Run: python3 .../scripts/cluster_enforce.py <ledger> --round {rnd} --runtime <RT> --target <target> --out-dir <out-dir> --verified-flags <out-dir>/cr-verified-{rnd}-{lc.runtime_slug(runtime)}.json (this JSON, saved by the collect command's stdout redirect) --clusters <out-dir>/cr-clusters-{rnd}-{lc.runtime_slug(runtime)}.json  (it REFUSES on dropped flags or a split blast group).",
        ],
    }
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
