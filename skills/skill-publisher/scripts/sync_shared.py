#!/usr/bin/env python3
"""Manual single-direction port helper for the formerly-shared scripts.

The sync contract is RETIRED (2026-06-20): skill-creator-ccvw, skill-tracer, and
skill-publisher each own an INDEPENDENT copy of the scripts below and may freely
diverge. There is NO auto-converge, no "latest-and-better propagate to all peers,"
and nothing here runs in the ship flow. `check_shared_sync.py` is the dormant
*drift-inspector* (where do copies differ?); THIS is its deliberate hand-port
companion: when a developer decides to carry one specific fix from skill A's copy
into skill B's copy, this previews and performs that single copy — opt-in, one
script, one direction.

Key behavior — the destination's module docstring is PRESERVED. Each copy names
its own skill's context in its docstring (the one intentional per-copy
difference); a port should bring the behavioral code over WITHOUT clobbering that.
So a confirmed port writes: the destination's existing header (shebang + module
docstring) + the SOURCE's behavioral body (everything after the source docstring).

Usage:
    # Preview (default — shows the unified diff of what would change, nothing written):
    python3 sync_shared.py <script.py> --from <skill> --to <skill>
    # Perform the port (writes a .bak of the destination first):
    python3 sync_shared.py <script.py> --from <skill> --to <skill> --confirm

    <skill> is a skill folder name under ~/.claude/skills/ (e.g. skill-tracer).

Exit: 0 = preview shown / port done / already identical;
      2 = usage or path error (script missing in source, same --from/--to, etc.).
Exit 0 covers preview, performed-port, and no-op-identical by design — this is a
developer-interactive tool, not an automation step, so it discriminates by its
human-readable stdout ("[dry-run] Re-run with --confirm…" vs "Ported …" vs
"already matches …"), not by exit code. The `.bak` is the destination's prior
state; a repeated --confirm NEVER overwrites an existing `.bak` — the first one
is preserved as the true pre-port original, so the path back to the original is
never clobbered by a second port (an existing `.bak` is kept, not refreshed).
"""
from __future__ import annotations

import argparse
import ast
import difflib
import shutil
import sys
from pathlib import Path

SKILLS = Path.home() / ".claude" / "skills"


def _script_path(skill: str, script: str) -> Path:
    return SKILLS / skill / "scripts" / script


def split_at_docstring(src: str) -> tuple[list[str], list[str]] | None:
    """Return (header_lines, body_lines). The header is the file PREAMBLE that a
    port must not carry across — the shebang line (if any) plus the module
    docstring (if any); the body is the behavioral code after it. So:
      - docstring present  → header = [shebang?..docstring], body = lines after it
      - no docstring       → header = [shebang] (or []), body = everything after the shebang
    Always separating the shebang means the body never re-introduces a second
    shebang when concatenated under another file's header. Returns None if src does
    not parse (refuse the port rather than corrupt the file). This is the single
    home of the AST docstring split — check_shared_sync.py imports it."""
    lines = src.splitlines()
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return None
    body = tree.body
    if (body and isinstance(body[0], ast.Expr)
            and isinstance(getattr(body[0], "value", None), ast.Constant)
            and isinstance(body[0].value.value, str)
            and body[0].end_lineno is not None):
        end = body[0].end_lineno  # 1-based last line of the docstring
        return lines[:end], lines[end:]
    # No module docstring — split off only a leading shebang, if present.
    if lines and lines[0].startswith("#!"):
        return lines[:1], lines[1:]
    return [], lines


def build_merged(source_src: str, dest_src: str | None) -> str | None:
    """Destination header (shebang + docstring, preserved) + source behavioral body.
    If the destination does not exist yet, fall back to a verbatim copy of the
    source (there is no destination header to preserve). Returns None if either
    file fails to parse OR the source has no behavioral body (an empty / docstring-
    only source would otherwise port "nothing" over the destination, destroying its
    code). Output is normalized to exactly one trailing newline so a no-op port
    (identical behavioral code) never shows a spurious newline-only diff and
    --confirm never silently adds/strips the destination's trailing newline."""
    src_split = split_at_docstring(source_src)
    if src_split is None:
        return None
    _, source_body = src_split
    # Refuse a source with no behavioral content — porting it would wipe the
    # destination's body. (A genuinely empty source is never a real port.)
    if not any(line.strip() for line in source_body):
        return None

    if dest_src is None:
        # New file — no destination header to preserve; copy verbatim (but still
        # normalize the trailing newline below).
        dest_header: list[str] = []
        merged_lines = source_src.splitlines()
    else:
        dest_split = split_at_docstring(dest_src)
        if dest_split is None:
            return None
        dest_header, _ = dest_split
        merged_lines = dest_header + source_body

    merged = "\n".join(merged_lines)
    if merged and not merged.endswith("\n"):
        merged += "\n"
    return merged


def main() -> int:
    ap = argparse.ArgumentParser(description="Manual single-direction port helper for shared scripts")
    ap.add_argument("script", help="script filename, e.g. append_ledger.py")
    ap.add_argument("--from", dest="from_skill", required=True,
                    help="source skill folder name (carry the fix FROM here)")
    ap.add_argument("--to", dest="to_skill", required=True,
                    help="destination skill folder name (port the fix INTO here)")
    ap.add_argument("--confirm", action="store_true",
                    help="perform the port (default is a dry-run preview)")
    args = ap.parse_args()

    if args.from_skill == args.to_skill:
        print("ERROR: --from and --to are the same skill; nothing to port", file=sys.stderr)
        return 2

    src_path = _script_path(args.from_skill, args.script)
    dst_path = _script_path(args.to_skill, args.script)

    if not src_path.is_file():
        print(f"ERROR: source script not found: {src_path}", file=sys.stderr)
        return 2

    source_src = src_path.read_text(encoding="utf-8")
    dest_src = dst_path.read_text(encoding="utf-8") if dst_path.is_file() else None

    merged = build_merged(source_src, dest_src)
    if merged is None:
        print(f"ERROR: cannot port {args.script} — source or destination does not "
              "parse, or the source has no behavioral body (refusing rather than "
              "wiping the destination)", file=sys.stderr)
        return 2

    current = dest_src if dest_src is not None else ""
    if merged == current:
        print(f"{args.script}: {args.to_skill} already matches {args.from_skill}'s "
              "behavioral code (docstring preserved) — nothing to port.")
        return 0

    # Show the unified diff of what the port would change (current dest -> merged).
    diff = difflib.unified_diff(
        current.splitlines(keepends=False),
        merged.splitlines(keepends=False),
        fromfile=f"{args.to_skill}/scripts/{args.script} (current)",
        tofile=f"{args.to_skill}/scripts/{args.script} (after port from {args.from_skill})",
        lineterm="",
    )
    diff_text = "\n".join(diff)
    print(diff_text)

    if not args.confirm:
        new_note = " (destination does not exist yet — would be created)" if dest_src is None else ""
        print(f"\n[dry-run] Re-run with --confirm to port {args.script} "
              f"{args.from_skill} -> {args.to_skill}{new_note}. "
              "The destination's module docstring is preserved.")
        return 0

    # Perform the port. Back up the destination first (if it exists) — but NEVER
    # overwrite an existing .bak: it holds the true pre-port original, and a second
    # --confirm would otherwise clobber it with the already-ported content, losing
    # the only path back to the original. The original is preserved; the user can
    # restore from it or remove it to re-baseline.
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    if dst_path.is_file():
        backup = dst_path.with_suffix(dst_path.suffix + ".bak")
        if backup.exists():
            print(f"\nExisting backup kept (true pre-port original) -> {backup}")
        else:
            shutil.copy2(dst_path, backup)
            print(f"\nBacked up destination -> {backup}")
    dst_path.write_text(merged, encoding="utf-8")
    print(f"Ported {args.script}: {args.from_skill} -> {args.to_skill} "
          "(behavioral code copied; destination docstring preserved).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
