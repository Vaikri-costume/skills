#!/usr/bin/env python3
"""Stage cold-agent dispatch prompts to scratchpad files (shared stager).

Both skill-tracer (3 direction prompts per round) and skill-publisher (1 audit
prompt) build a cold-Agent prompt by SLOT-substituting a template, then write it
to a scratchpad file so the actual Agent dispatch is a tiny "read this file"
call (keeping all N dispatches same-turn / pre-committed — the cold-parallel
anti-bias property). That staging is identical mechanics across both skills;
this script owns it once so neither hand-rolls the substitution + the
RUN_TIMESTAMP derivation + the all-files-present / no-unsubstituted-slot checks.

Pure-stdlib.

Inputs:
  --template <path>     the prompt template containing [SLOT] placeholders
  --out-dir <dir>       scratchpad dir (created if absent)
  --runtime <Runtime>   the invocation Runtime (YYYY-MM-DDTHH:MM[:SS]); the script
                        derives RUN_TIMESTAMP by replacing every ':' with '-'
                        (filesystem-safe), per dispatch-protocol "RUN_TIMESTAMP format"
  --spec <path|->       JSON: a list of {"label": "...", "slots": {"[SLOT]": "value", ...}}
                        one entry per agent to stage. '-' reads spec from stdin.
  --filename-template   default "{label}-{run_timestamp}.txt"; {label} and
                        {run_timestamp} are substituted per entry.
  --allow-unfilled      do not fail if a [SLOT]-looking token remains after
                        substitution (default: fail — a leftover slot is a bug)

For each spec entry: substitute every slot key→value in the template, write to
out-dir/<filename>, and verify no unsubstituted [UPPER_SNAKE] slot remains.

Output JSON: {"run_timestamp","staged":[{"label","path","chars"}],"missing":[...],"unfilled":[...]}
Prints a human one-liner per staged file to stderr (the inline ls cross-check).

Exit: 0 all staged + verified; 1 a file is missing after write OR an unfilled
slot remains (unless --allow-unfilled); 2 usage / template or spec not found.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SLOT_RE = re.compile(r"\[[A-Z][A-Z0-9_]*\]")  # [DIRECTION], [SKILL_NAME], [INLINED_TRACE_DEFINITION], ...


def main() -> int:
    ap = argparse.ArgumentParser(description="Stage cold-agent dispatch prompts")
    ap.add_argument("--template", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--runtime", required=True, help="Runtime YYYY-MM-DDTHH:MM[:SS]; ':' -> '-' for filenames")
    ap.add_argument("--spec", required=True, help="JSON list of {label, slots}; '-' for stdin")
    ap.add_argument("--filename-template", default="{label}-{run_timestamp}.txt")
    ap.add_argument("--allow-unfilled", action="store_true")
    args = ap.parse_args()

    tpl_path = Path(args.template).expanduser()
    if not tpl_path.is_file():
        print(f"ERROR: template not found: {tpl_path}", file=sys.stderr)
        return 2
    template = tpl_path.read_text()

    if args.spec == "-":
        spec_raw = sys.stdin.read()
    else:
        sp = Path(args.spec).expanduser()
        if not sp.is_file():
            print(f"ERROR: spec not found: {sp}", file=sys.stderr)
            return 2
        spec_raw = sp.read_text()
    try:
        spec = json.loads(spec_raw)
    except json.JSONDecodeError as e:
        print(f"ERROR: spec is not valid JSON: {e}", file=sys.stderr)
        return 2
    if not isinstance(spec, list) or not spec:
        print("ERROR: spec must be a non-empty JSON list of {label, slots}", file=sys.stderr)
        return 2

    # RUN_TIMESTAMP: every ':' -> '-' (handles both YYYY-MM-DDTHH:MM and ...:SS)
    run_timestamp = args.runtime.replace(":", "-")

    out_dir = Path(args.out_dir).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)

    staged = []
    missing = []
    unfilled = []
    for entry in spec:
        label = entry.get("label")
        slots = entry.get("slots", {})
        if not label or not isinstance(slots, dict):
            print(f"ERROR: each spec entry needs a 'label' and a 'slots' object: {entry!r}", file=sys.stderr)
            return 2
        # SINGLE-PASS substitution (B8): replace all placeholders in one regex pass so a slot VALUE
        # that happens to contain another slot's [TOKEN] (e.g. an inlined trace definition that quotes
        # a slot name) is NOT re-substituted, and the result is independent of slot insertion order.
        # Longest key first so e.g. [SKILL_NAME] is matched before [SKILL].
        if slots:
            keys = sorted(slots, key=len, reverse=True)
            pattern = re.compile("|".join(re.escape(k) for k in keys))
            prompt = pattern.sub(lambda m: str(slots[m.group(0)]), template)
        else:
            prompt = template
        # Unfilled = a [SLOT] in the TEMPLATE the spec gave no value for. Computed from the template,
        # NOT the substituted prompt, so a [TOKEN] that legitimately appears inside a slot's VALUE
        # (left literal by the single-pass substitution) is not mis-flagged as an unfilled slot.
        leftover = sorted(s for s in set(SLOT_RE.findall(template)) if s not in slots)
        fname = args.filename_template.format(label=label, run_timestamp=run_timestamp)
        out_path = out_dir / fname
        try:
            out_path.write_text(prompt, encoding="utf-8")
        except OSError as e:
            # makes the "missing file after write" exit-1 reachable: a write that
            # raises (permission/disk) lands here instead of crashing the script.
            missing.append(f"{out_path}: {e}")
            continue
        if not out_path.is_file():
            missing.append(str(out_path))
        if leftover:
            unfilled.append({"label": label, "slots": leftover})
        staged.append({"label": label, "path": str(out_path), "chars": len(prompt)})
        print(f"Staged {fname} ({len(prompt)} chars)" + (f"  ⚠ unfilled {leftover}" if leftover else ""),
              file=sys.stderr)

    result = {"run_timestamp": run_timestamp, "staged": staged, "missing": missing, "unfilled": unfilled}
    print(json.dumps(result, indent=2))
    if missing:
        return 1
    if unfilled and not args.allow_unfilled:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
