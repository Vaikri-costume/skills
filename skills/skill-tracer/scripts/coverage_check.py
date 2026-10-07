#!/usr/bin/env python3
"""coverage_check.py — Read-coverage enforcer for Code Review cold agents.

Verifies that an agent's transcript contains Read tool calls that cover every
line of every in-scope file before the agent emitted its findings.

Only the Read tool counts as coverage — Bash cat/sed/head do NOT.  Under-counting
is intentional (conservative): a false gap just forces more reading; silently
passing incomplete coverage is the worse failure.  Three rules keep credit honest:
  - a Read whose paired tool_result is an error (e.g. the max-tokens error on a large
    offset/limit call) returned no file content, so it earns NO credit;
  - a Read the tool truncated ("showing lines A-B of N total") earns credit only for the lines it
    actually showed, not the whole requested window;
  - a Read earns credit only for the in-scope file it actually named: the resolved
    absolute path, or a relative path resolved against the target directory — never
    merely a file with the same basename elsewhere.

Read semantics (mirrors the actual Read tool contract):
  - no offset, no limit  → covers lines 1 .. min(2000, linecount)
  - offset O (1-based), limit L → covers O .. min(O + L - 1, linecount)
  - offset O, no limit   → covers O .. min(O + 2000 - 1, linecount)

Usage:
    coverage_check.py --transcript <path.jsonl> --target <skill-dir> [--json]

Self-test: `coverage_check.py --self-test` runs the built-in range-math self-test instead of a
check (read from sys.argv before argparse runs, so it is not an argparse option; exit 0 on pass).

Exit:
    0  — all in-scope files fully covered
    1  — one or more files have uncovered line ranges (gaps)
    2  — usage error

Example (programmatic):
    from pathlib import Path
    from coverage_check import read_coverage
    result = read_coverage(Path("agent.jsonl"), Path("/path/to/skill"))
    if not result["covered"]:
        for rel in result["files_with_gaps"]:
            print(rel, result["per_file"][rel]["gaps"])

Pure stdlib. Python 3.9+.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from inscope import inscope_files  # noqa: E402 — shared enumeration (one-home rule)

_DEFAULT_READ_LIMIT = 2000  # lines per Read call when no limit is specified
# The Read tool's own refusals (no file content returned), for transcripts whose tool_result lacks is_error.
_READ_REFUSAL_RE = re.compile(r"exceeds maximum allowed (?:tokens|size)|<tool_use_error>|^Error\b", re.IGNORECASE)
# A Read the tool truncated: it returned content, but only the stated line range ("showing lines 1-697
# of 1293 total ..."), so credit is limited to that range, not the requested offset/limit window.
_READ_PARTIAL_RE = re.compile(r"showing lines (\d+)-(\d+) of \d+ total", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Line-count helper
# ---------------------------------------------------------------------------

def _line_count(path: Path) -> int:
    """Count lines in *path*. Returns 0 for an unreadable / empty file."""
    try:
        text = path.read_bytes()
    except OSError:
        return 0
    if not text:
        return 0
    count = text.count(b"\n")
    # If the file does not end with a newline, the last line is still a line.
    if text[-1:] != b"\n":
        count += 1
    return count


# ---------------------------------------------------------------------------
# Range union / gap computation
# ---------------------------------------------------------------------------

def _union_ranges(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Merge a list of (start, end) inclusive integer ranges into sorted, non-overlapping ones."""
    if not ranges:
        return []
    sorted_ranges = sorted(ranges)
    merged: list[tuple[int, int]] = [sorted_ranges[0]]
    for s, e in sorted_ranges[1:]:
        ms, me = merged[-1]
        if s <= me + 1:
            merged[-1] = (ms, max(me, e))
        else:
            merged.append((s, e))
    return merged


def _gaps(covered: list[tuple[int, int]], total_lines: int) -> list[list[int]]:
    """Return the uncovered ranges in 1..total_lines as [[start, end], ...] pairs.

    Args:
        covered: Merged, sorted list of (start, end) inclusive covered ranges.
        total_lines: Total line count of the file.

    Returns:
        List of [start, end] pairs (inclusive, 1-based) representing uncovered lines.
    """
    if total_lines == 0:
        return []
    result: list[list[int]] = []
    cursor = 1
    for s, e in covered:
        if cursor < s:
            result.append([cursor, s - 1])
        cursor = max(cursor, e + 1)
    if cursor <= total_lines:
        result.append([cursor, total_lines])
    return result


# ---------------------------------------------------------------------------
# Path matching helper
# ---------------------------------------------------------------------------

def _match_path(file_path_str: str, inscope_map: dict[str, Path], target_dir: Path | None = None) -> str | None:
    """Match a Read call's file_path to a key in inscope_map.

    The path is resolved to an absolute path (a relative path is resolved against *target_dir*,
    the skill root the agent was reading) and must equal an in-scope file exactly. There is no
    basename fallback: a same-named file in another directory is a different file.

    Returns the matching key (resolved absolute path string) or None.
    """
    try:
        p = Path(file_path_str).expanduser()
        if not p.is_absolute() and target_dir is not None:
            p = target_dir / p
        resolved = str(p.resolve())
    except (ValueError, OSError):
        return None
    return resolved if resolved in inscope_map else None


def _partial_read_ranges(objs: list[dict]) -> dict[str, tuple[int, int]]:
    """tool_use_id -> (first, last) line actually shown, for Reads whose result says it was truncated."""
    partial: dict[str, tuple[int, int]] = {}
    for obj in objs:
        msg = obj.get("message", {}) if isinstance(obj.get("message"), dict) else {}
        content = msg.get("content", obj.get("content", []))
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_result":
                continue
            body = block.get("content", "")
            if isinstance(body, list):
                body = " ".join(b.get("text", "") for b in body if isinstance(b, dict))
            m = _READ_PARTIAL_RE.search(body if isinstance(body, str) else "")
            if m:
                partial[block.get("tool_use_id", "")] = (int(m.group(1)), int(m.group(2)))
    return partial


def _tool_result_error_ids(objs: list[dict]) -> set[str]:
    """tool_use_ids whose paired tool_result is an error (is_error true, or the Read tool's
    size/token-limit refusal text). Such a Read returned no content, so it earns no coverage."""
    errored: set[str] = set()
    for obj in objs:
        msg = obj.get("message", {}) if isinstance(obj.get("message"), dict) else {}
        content = msg.get("content", obj.get("content", []))
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_result":
                continue
            body = block.get("content", "")
            if isinstance(body, list):
                body = " ".join(b.get("text", "") for b in body if isinstance(b, dict))
            text = body if isinstance(body, str) else ""
            if block.get("is_error") is True or _READ_REFUSAL_RE.search(text[:400]):
                errored.add(block.get("tool_use_id", ""))
    return errored


# ---------------------------------------------------------------------------
# Main public API
# ---------------------------------------------------------------------------

def read_coverage(transcript_path: Path, target_dir: Path,
                  files: "list[Path] | None" = None) -> dict[str, Any]:
    """Compute Read-tool coverage of the reviewed files from an agent transcript.

    Args:
        transcript_path: Path to the agent's JSONL transcript.
        target_dir: Root of the skill being reviewed (passed to inscope_files).
        files: The files the agent was staged with (code_review_run.py's scope record); None means
            every in-scope file (a full-sweep review).

    Returns:
        {
          "covered": bool,           # True iff every line of every in-scope file is covered
          "per_file": {
            "<relpath>": {
              "linecount": int,
              "covered_lines": int,  # number of lines covered (may exceed linecount if ranges overlap — use gaps)
              "gaps": [[s, e], ...]  # uncovered ranges (empty list means fully covered)
            },
            ...
          },
          "files_with_gaps": ["relpath", ...]  # files that have at least one gap
        }

    Example:
        >>> result = read_coverage(Path("agent.jsonl"), Path("/my-skill"))
        >>> result["covered"]
        True
    """
    # ------------------------------------------------------------------
    # 1. Enumerate in-scope files
    # ------------------------------------------------------------------
    abs_files = [Path(f).resolve() for f in files] if files is not None else inscope_files(target_dir)

    # Build: resolved-abs-str → Path
    inscope_map: dict[str, Path] = {str(p): p for p in abs_files}

    # Track covered ranges per abs-path key
    covered_ranges: dict[str, list[tuple[int, int]]] = {k: [] for k in inscope_map}

    # Pre-compute line counts
    line_counts: dict[str, int] = {k: _line_count(p) for k, p in inscope_map.items()}

    # ------------------------------------------------------------------
    # 2. Parse transcript for Read tool_use entries
    # ------------------------------------------------------------------
    try:
        raw_lines = transcript_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        raise ValueError(f"Cannot read transcript {transcript_path}: {exc}") from exc

    objs: list[dict] = []
    for raw in raw_lines:
        raw = raw.strip()
        if not raw:
            continue
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            objs.append(obj)
    errored_reads = _tool_result_error_ids(objs)
    partial_reads = _partial_read_ranges(objs)

    for obj in objs:
        # We look for tool_use blocks inside assistant messages
        msg_type = obj.get("type")
        if msg_type == "assistant":
            msg = obj.get("message", {})
            content = msg.get("content", [])
        elif msg_type == "tool_use":
            # Some transcript formats emit tool_use at top level
            content = [obj]
        else:
            continue

        if not isinstance(content, list):
            continue

        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") != "tool_use":
                continue
            tool_name = block.get("name", "")
            if tool_name != "Read":
                continue

            inp = block.get("input", {})
            if not isinstance(inp, dict):
                continue
            file_path_str = inp.get("file_path", "")
            if not file_path_str:
                continue

            if block.get("id") in errored_reads:
                continue  # the Read failed: no content was returned, so no coverage is earned
            key = _match_path(file_path_str, inscope_map, target_dir.resolve())
            if key is None:
                continue  # Not an in-scope file — skip

            lc = line_counts[key]
            if lc == 0:
                continue

            # Determine offset (1-based) and limit
            raw_offset = inp.get("offset")
            raw_limit = inp.get("limit")

            if raw_offset is None:
                # No offset: starts at line 1
                offset = 1
            else:
                try:
                    offset = int(raw_offset)
                except (TypeError, ValueError):
                    offset = 1

            if raw_limit is None:
                limit = _DEFAULT_READ_LIMIT
            else:
                try:
                    limit = int(raw_limit)
                except (TypeError, ValueError):
                    limit = _DEFAULT_READ_LIMIT

            start = max(1, offset)
            end = min(start + limit - 1, lc)
            if block.get("id") in partial_reads:
                shown_first, shown_last = partial_reads[block.get("id")]
                start, end = max(start, shown_first), min(end, shown_last)

            if start <= end:
                covered_ranges[key].append((start, end))

    # ------------------------------------------------------------------
    # 3. Compute per-file coverage and gaps
    # ------------------------------------------------------------------
    per_file: dict[str, dict[str, Any]] = {}
    files_with_gaps: list[str] = []

    for key, p in inscope_map.items():
        relpath = str(p.relative_to(target_dir.resolve()))
        lc = line_counts[key]
        merged = _union_ranges(covered_ranges[key])
        gaps = _gaps(merged, lc)

        covered_line_count = sum(e - s + 1 for s, e in merged)

        per_file[relpath] = {
            "linecount": lc,
            "covered_lines": covered_line_count,
            "gaps": gaps,
        }

        if gaps:
            files_with_gaps.append(relpath)

    return {
        "covered": len(files_with_gaps) == 0,
        "per_file": per_file,
        "files_with_gaps": files_with_gaps,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Check that an agent transcript's Read calls cover every line of every "
            "in-scope skill file. Exit 0 = fully covered; exit 1 = gaps found."
        )
    )
    ap.add_argument("--transcript", required=True, help="Path to agent JSONL transcript.")
    ap.add_argument("--target", required=True, help="Skill directory (in-scope root).")
    ap.add_argument("--json", action="store_true", dest="json_out",
                    help="Print full JSON report instead of human-readable summary.")
    args = ap.parse_args()

    transcript_path = Path(args.transcript).expanduser().resolve()
    target_dir = Path(args.target).expanduser().resolve()

    if not transcript_path.is_file():
        print(f"ERROR: --transcript not found: {transcript_path}", file=sys.stderr)
        return 2
    if not target_dir.is_dir():
        print(f"ERROR: --target is not a directory: {target_dir}", file=sys.stderr)
        return 2

    try:
        result = read_coverage(transcript_path, target_dir)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.json_out:
        print(json.dumps(result, indent=2))
    else:
        if result["covered"]:
            print("COVERAGE OK — all in-scope lines covered.")
        else:
            print(f"COVERAGE INCOMPLETE — {len(result['files_with_gaps'])} file(s) with gaps:")
            for rel in result["files_with_gaps"]:
                info = result["per_file"][rel]
                print(f"  {rel}: {info['linecount']} lines, gaps: {info['gaps']}")

    return 0 if result["covered"] else 1


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def _self_test() -> None:
    """Verify range math for read_coverage internals.

    Test 1: Two Reads covering [1..2000] + [2001..3500] over a 3500-line file → covered.
    Test 2: Only first Read [1..2000] → gap [2001, 3500].
    """
    print("Running coverage_check self-test...")

    # --- helpers (inline to avoid needing a real filesystem) ---
    def _fake_coverage(reads: list[tuple[int | None, int | None]], lc: int) -> list[list[int]]:
        """Simulate coverage of a single file given (offset, limit) pairs and linecount."""
        ranges: list[tuple[int, int]] = []
        for (offset, limit) in reads:
            if offset is None:
                start = 1
            else:
                start = max(1, offset)
            if limit is None:
                eff_limit = _DEFAULT_READ_LIMIT
            else:
                eff_limit = limit
            end = min(start + eff_limit - 1, lc)
            if start <= end:
                ranges.append((start, end))
        merged = _union_ranges(ranges)
        return _gaps(merged, lc)

    # Test 1: full coverage [1..2000] + [2001..3500]
    gaps1 = _fake_coverage([(1, 2000), (2001, 2000)], 3500)
    assert gaps1 == [], f"Test 1 FAILED — expected no gaps, got {gaps1}"
    print("  Test 1 PASSED: [1..2000] + [2001..3500] over 3500 lines → no gaps")

    # Test 2: only [1..2000], missing [2001..3500]
    gaps2 = _fake_coverage([(1, 2000)], 3500)
    assert gaps2 == [[2001, 3500]], f"Test 2 FAILED — expected [[2001, 3500]], got {gaps2}"
    print("  Test 2 PASSED: [1..2000] only over 3500 lines → gap [2001, 3500]")

    # Test 3: no offset (defaults to 1..2000)
    gaps3 = _fake_coverage([(None, None)], 1500)
    assert gaps3 == [], f"Test 3 FAILED — expected no gaps for 1500-line file, got {gaps3}"
    print("  Test 3 PASSED: no-offset Read over 1500-line file → no gaps")

    # Test 4: overlap reads still produce correct result
    gaps4 = _fake_coverage([(1, 1000), (500, 2000)], 2500)
    assert gaps4 == [[2500, 2500]], f"Test 4 FAILED — expected [[2500, 2500]], got {gaps4}"
    print("  Test 4 PASSED: overlapping reads [1..1000]+[500..2499] over 2500 lines → gap [2500, 2500]")

    print("All self-tests PASSED.")


if __name__ == "__main__":
    import sys as _sys
    if "--self-test" in _sys.argv:
        _self_test()
        _sys.exit(0)
    _sys.exit(main())
