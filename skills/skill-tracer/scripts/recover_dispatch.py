#!/usr/bin/env python3
"""Recover skill-tracer cold-dispatch results from a session JSONL after compaction.

skill-tracer recovery rule 1: when a session was interrupted mid-dispatch, the
prior session's Agent dispatches + their results live in the harness session
JSONL. This script finds them so the orchestrator doesn't hand-parse raw JSONL
by eye (error-prone, and the failure is silent — easy to grab a stale dispatch
or a backgrounded agent's "launched" ack instead of its real result).

Per-skill COPY of the ecosystem's cold-dispatch JSONL-recovery pattern (the proven
q1-next/p1-next house pattern: q1_recovery.py + find_agent_results.py). skill-publisher
carries its own copy (skill-publisher/scripts/recover_dispatch.py) for its single audit
dispatch. DELIBERATELY NOT sync-contracted — each dispatching skill owns its copy and
may diverge, because the dispatch SHAPE differs (here: three trace directions; publisher:
one audit). Do NOT add this to any check_vendored_sync.py pairing. The shared, proven
part is the scan core (most-recent-wins tool_use→tool_result pairing + the background-Agent
task-notification edge case); only the description match + expected count are skill-specific.

Adapted to skill-tracer:
  - The three cold directions use CONSTANT description strings:
      "Forward trace of <skill>", "Backward trace of <skill>", "Executor trace of <skill>"
    (skill-name match filters out dispatches against other skills).
  - Expected count is always 3 (the dispatch-set is the constant
    [forward, backward, executor]).
  - MOST-RECENT WINS: a discard-and-retry leaves BOTH the discarded dispatch's
    tool_uses and the retry's in the JSONL. Scanning the whole file and keeping
    the LAST matching tool_use per direction selects the retry, not the stale one
    (dispatch-protocol.md "Self-check + discard-and-retry").
  - Background-Agent case: if the immediate tool_result is just an async-launch
    ack, the real output arrives later as a <task-notification> user message
    embedding <tool-use-id>TUID</tool-use-id>; that line is preferred.

Pure-stdlib. The orchestrator still owns the JUDGMENT this script does NOT do:
(a) the PRE-FLIGHT drift test on the recovered results (use check_drift.py), and
(b) deciding discard-vs-trust and which directions to re-dispatch. This script
only LOCATES and PAIRS.

Usage:
    recover_dispatch.py --skill <skill-name> [--project-dir <dir>] [--jsonl <path>]
        --project-dir defaults to $HOME/.claude/projects/<encoded-cwd> (encoded
        from the current working directory: '/'->'-', leading '-').
        --jsonl overrides auto-location (else newest *.jsonl in project-dir).

Output: JSON —
    {
      "jsonl": "<path>",
      "found":   {"forward": {"tuid","dispatch_line","result_line"}, ...},
      "missing": ["backward", ...],          # of {forward,backward,executor}
      "result_text": {"forward": "<recovered report text>", ...}
    }

Exit: 0 all three found; 1 one or more missing; 2 usage / no JSONL found.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

DIRECTIONS = ("forward", "backward", "executor")
# "Forward trace of <skill>" / "Backward trace of <skill>" / "Executor trace of <skill>"
DESC_RE = re.compile(r"^(Forward|Backward|Executor)\s+trace\s+of\s+(.+)$")


def encoded_cwd() -> str:
    cwd = os.getcwd()
    return "-" + cwd.lstrip("/").replace("/", "-")


def newest_jsonl(project_dir: Path) -> Path | None:
    cands = sorted(project_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    return cands[0] if cands else None


def recover(jsonl_path: Path, skill: str) -> dict:
    # most-recent-wins: overwrite as we scan top→bottom so the LAST match per direction stays.
    found: dict[str, dict] = {}
    tuid_to_dir: dict[str, str] = {}
    result_line: dict[str, int] = {}
    result_text: dict[str, str] = {}
    tasknotif_line: dict[str, int] = {}
    tasknotif_text: dict[str, str] = {}

    with jsonl_path.open() as fh:
        for lineno, line in enumerate(fh, start=1):
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            otype = obj.get("type")

            if otype == "assistant":
                content = obj.get("message", {}).get("content", [])
                if isinstance(content, list):
                    for block in content:
                        if not isinstance(block, dict):
                            continue
                        if block.get("type") == "tool_use" and block.get("name") in ("Agent", "Task"):
                            desc = (block.get("input") or {}).get("description", "") or ""
                            m = DESC_RE.match(desc.strip())
                            if m and m.group(2).strip() == skill:
                                d = m.group(1).lower()  # forward/backward/executor
                                tuid = block.get("id")
                                # most-recent-wins: replace any earlier (discarded) dispatch
                                found[d] = {"tuid": tuid, "dispatch_line": lineno, "result_line": None}
                                tuid_to_dir[tuid] = d

            elif otype == "user":
                content = obj.get("message", {}).get("content")
                # Background-agent task-notification (content is a string)
                if isinstance(content, str):
                    if "<task-notification>" in content and "<tool-use-id>" in content:
                        for tuid, d in tuid_to_dir.items():
                            if f"<tool-use-id>{tuid}</tool-use-id>" in content:
                                tasknotif_line[d] = lineno
                                tasknotif_text[d] = content
                    continue
                if isinstance(content, list):
                    for block in content:
                        if not isinstance(block, dict):
                            continue
                        if block.get("type") == "tool_result":
                            tuid = block.get("tool_use_id")
                            d = tuid_to_dir.get(tuid)
                            if d is not None:
                                result_line[d] = lineno
                                c = block.get("content")
                                if isinstance(c, str):
                                    result_text[d] = c
                                elif isinstance(c, list):
                                    result_text[d] = "\n".join(
                                        b.get("text", "") for b in c
                                        if isinstance(b, dict) and b.get("type") == "text"
                                    )
                        elif block.get("type") == "text":
                            t = block.get("text", "") or ""
                            if "<task-notification>" in t and "<tool-use-id>" in t:
                                for tuid, d in tuid_to_dir.items():
                                    if f"<tool-use-id>{tuid}</tool-use-id>" in t:
                                        tasknotif_line[d] = lineno
                                        tasknotif_text[d] = t

    out_found = {}
    out_text = {}
    missing = []
    for d in DIRECTIONS:
        if d not in found:
            missing.append(d)
            continue
        # prefer task-notification (real async output) over the tool_result ack
        rline = tasknotif_line.get(d) if tasknotif_line.get(d) is not None else result_line.get(d)
        info = dict(found[d])
        info["result_line"] = rline
        out_found[d] = info
        if rline is None:
            missing.append(d)  # dispatched but no result yet
        else:
            out_text[d] = tasknotif_text.get(d) or result_text.get(d, "")
    # dedupe missing (a direction with a dispatch-but-no-result is "missing" too)
    missing = sorted(set(missing), key=lambda x: DIRECTIONS.index(x))
    return {"jsonl": str(jsonl_path), "found": out_found, "missing": missing, "result_text": out_text}


def main() -> int:
    ap = argparse.ArgumentParser(description="Recover skill-tracer cold dispatches from session JSONL")
    ap.add_argument("--skill", required=True, help="target skill name (matches '<Dir> trace of <skill>')")
    ap.add_argument("--project-dir", default=None, help="harness project dir (default: $HOME/.claude/projects/<encoded-cwd>)")
    ap.add_argument("--jsonl", default=None, help="explicit JSONL path (default: newest in project-dir)")
    args = ap.parse_args()

    if args.jsonl:
        jsonl_path = Path(args.jsonl).expanduser()
        if not jsonl_path.is_file():
            print(f"ERROR: --jsonl not found: {jsonl_path}", file=sys.stderr)
            return 2
    else:
        pdir = Path(args.project_dir).expanduser() if args.project_dir \
            else Path.home() / ".claude" / "projects" / encoded_cwd()
        if not pdir.is_dir():
            print(f"ERROR: project dir not found: {pdir}", file=sys.stderr)
            return 2
        jsonl_path = newest_jsonl(pdir)
        if jsonl_path is None:
            print(f"ERROR: no *.jsonl in {pdir}", file=sys.stderr)
            return 2

    result = recover(jsonl_path, args.skill)
    print(json.dumps(result, indent=2))
    return 1 if result["missing"] else 0


if __name__ == "__main__":
    sys.exit(main())
