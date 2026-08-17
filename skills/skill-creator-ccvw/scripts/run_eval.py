#!/usr/bin/env python3
"""Run trigger evaluation for a skill description.

Tests whether a skill's description causes Claude to trigger (read the skill)
for a set of queries. Outputs results as JSON.
"""

import argparse
import json
import os
import select
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from scripts.utils import claude_binary, claude_subprocess_env, parse_skill_md


def preflight_check(model: str | None = None) -> None:
    """Run a trivial claude -p call to verify credentials and environment.

    Catches missing API keys, bad auth, and broken CLI installations before
    the expensive evaluation suite starts — otherwise those failures surface
    only as every query "not triggering", which reads as a bad description
    rather than a broken environment.
    """
    cmd = [claude_binary(), "-p", "Respond with exactly: ok", "--output-format", "text"]
    if model:
        cmd.extend(["--model", model])
    env = claude_subprocess_env()
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, env=env, timeout=30,
        )
    except FileNotFoundError:
        print(
            "Error: 'claude' CLI not found on PATH. Install it or check your PATH.",
            file=sys.stderr,
        )
        sys.exit(1)
    except subprocess.TimeoutExpired:
        print(
            "Error: Pre-flight check timed out after 30 s — is the Claude CLI responsive?",
            file=sys.stderr,
        )
        sys.exit(1)

    if result.returncode != 0:
        print(
            f"Error: Pre-flight credential check failed (exit code {result.returncode}).\n"
            f"stderr: {result.stderr.strip()}\n"
            f"Fix your credentials / environment variables before running the eval suite.",
            file=sys.stderr,
        )
        sys.exit(1)


def run_single_query(
    query: str,
    skill_name: str,
    skill_description: str,
    timeout: int,
    model: str | None = None,
) -> bool:
    """Run a single query and return whether the skill was triggered.

    Creates a command file in an isolated throwaway project root so it appears
    in Claude's available_skills list for this `claude -p` subprocess only —
    never in the user's live .claude/commands/, where concurrent Claude Code
    sessions would see the synthetic variant during the parallel eval window.
    `claude -p` discovers commands from its cwd's .claude/; global auth/config
    in ~/.claude is unaffected by cwd. Uses --include-partial-messages to
    detect triggering early from stream events (content_block_start) rather
    than waiting for the full assistant message, which only arrives after tool
    execution.
    """
    # Use the original skill_name as the slash-command filename so that user
    # queries which mention the skill by name (e.g. "/skill-tracer p1-next" or
    # natural language "trace skill-tracer over p1-next") can actually trigger
    # the test description. Renaming the slash-command file to a hashed clone
    # (the prior behaviour: f"{skill_name}-skill-{unique_id}") broke this case:
    # queries that say "skill-tracer" by name don't match a slash command
    # called "skill-tracer-skill-1aaf3ccf", so every name-mentioning query
    # scored 0/N triggers regardless of description quality.
    #
    # The command file lives in a throwaway tempdir (the eval root), named
    # <skill_name>.md inside its .claude/commands/. Isolating to a tempdir —
    # rather than writing into the user's live project_root — keeps the
    # synthetic variant out of any concurrent session's registry, while the
    # <skill_name> filename preserves name-based triggering. The unique_id only
    # names the tempdir (so a tempdir stranded by a SIGKILLed worker, where the
    # finally-rmtree never runs, is attributable), not the command file.
    clean_name = skill_name
    unique_id = uuid.uuid4().hex[:8]
    eval_root = Path(tempfile.mkdtemp(prefix=f"skill-eval-{skill_name}-{unique_id}-"))
    command_file = eval_root / ".claude" / "commands" / f"{clean_name}.md"

    try:
        command_file.parent.mkdir(parents=True, exist_ok=True)
        # Use YAML block scalar to avoid breaking on quotes in description
        indented_desc = "\n  ".join(skill_description.split("\n"))
        command_content = (
            f"---\n"
            f"description: |\n"
            f"  {indented_desc}\n"
            f"---\n\n"
            f"# {skill_name}\n\n"
            f"This skill handles: {skill_description}\n"
        )
        command_file.write_text(command_content, encoding="utf-8")

        cmd = [
            claude_binary(),
            "-p", query,
            "--output-format", "stream-json",
            "--verbose",
            "--include-partial-messages",
        ]
        if model:
            cmd.extend(["--model", model])

        env = claude_subprocess_env()

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(eval_root),
            env=env,
        )

        start_time = time.time()
        buffer = ""
        stderr_buf = ""
        # Track state for stream event detection
        pending_tool_name = None
        accumulated_json = ""

        try:
            while time.time() - start_time < timeout:
                if process.poll() is not None:
                    remaining = process.stdout.read()
                    if remaining:
                        buffer += remaining.decode("utf-8", errors="replace")
                    err_remaining = process.stderr.read()
                    if err_remaining:
                        stderr_buf += err_remaining.decode("utf-8", errors="replace")
                    break

                # Drain BOTH stdout and stderr. stderr is a PIPE: leaving it unread
                # lets a chatty child fill the ~64KB pipe buffer and block on its
                # stderr write before emitting the triggering stdout event — which
                # would then time out and score a spurious "did not trigger".
                ready, _, _ = select.select([process.stdout, process.stderr], [], [], 1.0)
                if not ready:
                    continue
                if process.stderr in ready:
                    err_chunk = os.read(process.stderr.fileno(), 8192)
                    if err_chunk:
                        stderr_buf += err_chunk.decode("utf-8", errors="replace")
                if process.stdout not in ready:
                    continue

                chunk = os.read(process.stdout.fileno(), 8192)
                if not chunk:
                    break
                buffer += chunk.decode("utf-8", errors="replace")

                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    # Early detection via stream events
                    if event.get("type") == "stream_event":
                        se = event.get("event", {})
                        se_type = se.get("type", "")

                        if se_type == "content_block_start":
                            cb = se.get("content_block", {})
                            if cb.get("type") == "tool_use":
                                tool_name = cb.get("name", "")
                                if tool_name in ("Skill", "Read"):
                                    pending_tool_name = tool_name
                                    accumulated_json = ""
                                else:
                                    # A non-skill tool (AskUserQuestion, Bash, …) is NOT a
                                    # trigger — but it must NOT end detection. A global
                                    # CLAUDE.md that asks a clarifying question first, or a
                                    # model that greps before consulting, makes the FIRST
                                    # action a non-skill tool and would mask a skill consult
                                    # that lands moments later. Reset and keep scanning until
                                    # the skill IS consulted or the run reaches `result`.
                                    pending_tool_name = None

                        elif se_type == "content_block_delta" and pending_tool_name:
                            delta = se.get("delta", {})
                            if delta.get("type") == "input_json_delta":
                                accumulated_json += delta.get("partial_json", "")
                                if clean_name in accumulated_json:
                                    return True

                        elif se_type == "content_block_stop":
                            # A pending Skill/Read block ended: trigger only if it referenced
                            # THIS skill; otherwise reset and keep scanning (the skill may be
                            # consulted in a later block / message). Do NOT return here.
                            if pending_tool_name and clean_name in accumulated_json:
                                return True
                            pending_tool_name = None
                        # message_stop: intentionally no-op — keep scanning until `result`,
                        # so a skill consult after an initial non-skill action (or in a later
                        # assistant message) is still detected.

                    # Fallback: full assistant message
                    elif event.get("type") == "assistant":
                        message = event.get("message", {})
                        for content_item in message.get("content", []):
                            if content_item.get("type") != "tool_use":
                                continue
                            tool_name = content_item.get("name", "")
                            tool_input = content_item.get("input", {})
                            if tool_name == "Skill" and clean_name in tool_input.get("skill", ""):
                                return True
                            if tool_name == "Read" and clean_name in tool_input.get("file_path", ""):
                                return True
                            # Any other tool is not a trigger by itself — keep scanning the
                            # remaining content items (and later events); do NOT return.

                    elif event.get("type") == "result":
                        # Reached the run's end without a skill consult → not triggered.
                        return False
        finally:
            # Clean up process on any exit path (return, exception, timeout)
            if process.poll() is None:
                process.kill()
                process.wait()

        # Surface a genuine non-zero EXIT instead of silently returning False —
        # a credential/CLI error otherwise looks like "did not trigger" and
        # corrupts the eval data. Guard on `> 0`: our own timeout path kills the
        # process, leaving a negative (signal) returncode, which is a normal
        # "didn't trigger in time" outcome, not a CLI error — those must not abort.
        if process.returncode is not None and process.returncode > 0:
            # stderr_buf was drained during the loop; pick up any final bytes.
            try:
                err_remaining = process.stderr.read()
                if err_remaining:
                    stderr_buf += err_remaining.decode("utf-8", errors="replace")
            except (OSError, ValueError):
                pass
            stderr_output = stderr_buf.strip()
            raise RuntimeError(
                f"claude -p exited with code {process.returncode}"
                + (f": {stderr_output}" if stderr_output else "")
            )

        # Loop exited (timeout / EOF) with no skill consult seen → not triggered.
        return False
    finally:
        shutil.rmtree(eval_root, ignore_errors=True)


def run_eval(
    eval_set: list[dict],
    skill_name: str,
    description: str,
    num_workers: int,
    timeout: int,
    runs_per_query: int = 1,
    trigger_threshold: float = 0.5,
    model: str | None = None,
) -> dict:
    """Run the full eval set and return results."""
    results = []

    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        future_to_info = {}
        for item in eval_set:
            for run_idx in range(runs_per_query):
                future = executor.submit(
                    run_single_query,
                    item["query"],
                    skill_name,
                    description,
                    timeout,
                    model,
                )
                future_to_info[future] = (item, run_idx)

        query_triggers: dict[str, list[bool]] = {}
        query_items: dict[str, dict] = {}
        for future in as_completed(future_to_info):
            item, _ = future_to_info[future]
            query = item["query"]
            query_items[query] = item
            if query not in query_triggers:
                query_triggers[query] = []
            try:
                query_triggers[query].append(future.result())
            except RuntimeError as e:
                # Surface CLI/credential errors loudly — these corrupt data if
                # silently treated as "did not trigger".
                raise RuntimeError(
                    f"Evaluation query failed due to a CLI error (not a "
                    f"trigger miss). This likely indicates a credential or "
                    f"environment problem. Query: {query!r}\nError: {e}"
                ) from e
            except Exception as e:
                print(f"Warning: query failed: {e}", file=sys.stderr)
                query_triggers[query].append(False)

    for query, triggers in query_triggers.items():
        item = query_items[query]
        trigger_rate = sum(triggers) / len(triggers)
        should_trigger = item["should_trigger"]
        if should_trigger:
            did_pass = trigger_rate >= trigger_threshold
        else:
            did_pass = trigger_rate < trigger_threshold
        results.append({
            "query": query,
            "should_trigger": should_trigger,
            "trigger_rate": trigger_rate,
            "triggers": sum(triggers),
            "runs": len(triggers),
            "pass": did_pass,
        })

    passed = sum(1 for r in results if r["pass"])
    total = len(results)

    return {
        "skill_name": skill_name,
        "description": description,
        "results": results,
        "summary": {
            "total": total,
            "passed": passed,
            "failed": total - passed,
        },
    }


def main():
    parser = argparse.ArgumentParser(description="Run trigger evaluation for a skill description")
    parser.add_argument("--eval-set", required=True, help="Path to eval set JSON file")
    parser.add_argument("--skill-path", required=True, help="Path to skill directory")
    parser.add_argument("--description", default=None, help="Override description to test")
    parser.add_argument("--num-workers", type=int, default=10, help="Number of parallel workers")
    parser.add_argument("--timeout", type=int, default=30, help="Timeout per query in seconds")
    parser.add_argument("--runs-per-query", type=int, default=3, help="Number of runs per query")
    parser.add_argument("--trigger-threshold", type=float, default=0.5, help="Trigger rate threshold")
    parser.add_argument("--model", default=None, help="Model to use for claude -p (default: user's configured model)")
    parser.add_argument("--verbose", action="store_true", help="Print progress to stderr")
    args = parser.parse_args()

    preflight_check(model=args.model)

    eval_set = json.loads(Path(args.eval_set).read_text(encoding="utf-8"))
    skill_path = Path(args.skill_path)

    if not (skill_path / "SKILL.md").exists():
        print(f"Error: No SKILL.md found at {skill_path}", file=sys.stderr)
        sys.exit(1)

    name, original_description, content = parse_skill_md(skill_path)
    description = args.description or original_description

    if args.verbose:
        print(f"Evaluating: {description}", file=sys.stderr)

    output = run_eval(
        eval_set=eval_set,
        skill_name=name,
        description=description,
        num_workers=args.num_workers,
        timeout=args.timeout,
        runs_per_query=args.runs_per_query,
        trigger_threshold=args.trigger_threshold,
        model=args.model,
    )

    if args.verbose:
        summary = output["summary"]
        print(f"Results: {summary['passed']}/{summary['total']} passed", file=sys.stderr)
        for r in output["results"]:
            status = "PASS" if r["pass"] else "FAIL"
            rate_str = f"{r['triggers']}/{r['runs']}"
            print(f"  [{status}] rate={rate_str} expected={r['should_trigger']}: {r['query'][:70]}", file=sys.stderr)

    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
