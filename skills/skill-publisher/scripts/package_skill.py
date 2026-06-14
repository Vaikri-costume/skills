#!/usr/bin/env python3
"""Package a CCVW skill for distribution as a .skill archive.

Pure-stdlib (tarfile + argparse + re + json). Per-tier packaging:
- personal: refuses (personal skills aren't packaged for distribution)
- claude-users: .skill tarball installable on Claude Code + Cowork
- model-agnostic: same tarball + an agentskills.io conformance gate

Exit codes: 0 success; 1 SKILL.md absent (error JSON on stderr); 2 personal-tier
refusal (error JSON on stderr) or argparse usage error (usage text, no JSON);
3 model-agnostic conformance failure; 4 archive write failure.

Usage:
    python3 package_skill.py <skill-path> --tier <tier> [--format skill|zip] [--output <path>]

Excludes: *.bak*, hidden files, *-workspace/, evals/iteration-*/, the ship ledger.
Includes: SKILL.md, README.md, HISTORY.md, LICENSE, references/, scripts/, assets/.
Note: evals/evals.json and evals/eval_set.json (eval definition files) ARE included
if present; only evals/iteration-*/ runtime outputs are excluded. Per CCVW convention,
eval outputs live in ~/.claude/skill-creator-evals-ledger/, not the skill tree —
the evals/iteration-* exclusion is defensive for stray outputs.
"""

import argparse
import json
import re
import sys
import tarfile
import zipfile
from pathlib import Path


EXCLUDE_NAME_PATTERNS = [
    re.compile(r"\.bak"),        # *.bak* pre-edit snapshots
    re.compile(r"\.orig$"),      # *.orig patch/merge backups
    re.compile(r"^\."),          # hidden files (.DS_Store, .gitignore, ...)
]
EXCLUDE_PATH_SUBSTRINGS = [
    "-workspace/",
    "/evals/iteration-",
]


def should_exclude(rel_path: Path) -> bool:
    name = rel_path.name
    for pat in EXCLUDE_NAME_PATTERNS:
        if pat.search(name):
            return True
    s = str(rel_path)
    for sub in EXCLUDE_PATH_SUBSTRINGS:
        if sub in s:
            return True
    return False


def read_frontmatter_compat(skill_md: Path) -> str:
    """Best-effort read of the `compatibility:` frontmatter value (flat scalar).
    Normalizes BOM, CRLF, and a closing --- at EOF without a trailing newline before
    parsing. On the model-agnostic path an empty return degrades gracefully (empty
    compat = conformance fails, which is the correct behavior for malformed frontmatter)."""
    try:
        text = skill_md.read_text()
    except OSError:
        return ""
    text = text.lstrip("﻿")                          # strip leading BOM
    text = text.replace("\r\n", "\n").replace("\r", "\n") # normalize CRLF/CR → LF
    if not text.startswith("---\n"):
        return ""
    end = text.find("\n---\n", 4)
    if end < 0:
        # Accept closing --- at EOF without trailing newline
        trail = text.find("\n---", 4)
        if trail >= 0 and not text[trail + 4:].strip():
            end = trail
        else:
            return ""
    for line in text[4:end].split("\n"):
        m = re.match(r"^compatibility\s*:\s*(.*)$", line)
        if m:
            return m.group(1).strip().strip('"').strip("'")
    return ""


def has_claude_extensions(skill_md: Path) -> list:
    """Cheap scan for Claude-only patterns that block model-agnostic packaging.
    This is an independent inline copy of the four most-blocking patterns, NOT an
    import of portability_lint's CLAUDE_BODY_PATTERNS. Intentionally omits patterns
    that are informational at step 4 but not packaging-blocking (e.g. $XDG paths).
    If portability_lint's blocking list changes, review whether this function needs
    updating too — it is a FINAL gate after step 4 already ran the full lint."""
    try:
        body = skill_md.read_text()
    except OSError:
        return []
    patterns = [
        (r"\bAgent\s+tool\b", "Agent tool dispatch"),
        (r"\$ARGUMENTS\[\d+\]", "$ARGUMENTS[N]"),
        (r"!\s*`[^`]+`", "dynamic shell injection"),
        (r"\bmcp__[a-zA-Z_]+__[a-zA-Z_]+\b", "mcp__*__* tool name"),
    ]
    found = []
    for pat, label in patterns:
        if re.search(pat, body):
            found.append(label)
    return found


def main():
    parser = argparse.ArgumentParser(description="Package a CCVW skill as a .skill archive")
    parser.add_argument("skill_path", help="Path to skill directory")
    parser.add_argument("--tier", required=True, choices=["personal", "claude-users", "model-agnostic"])
    parser.add_argument("--format", default="skill", choices=["skill", "zip"],
                        help="skill = .skill gzipped tarball for Claude Code/Cowork (default); "
                             "zip = plain .zip for the Claude.ai web upload route")
    parser.add_argument("--output", default=None, help="Output path (default: <skill>/../<name>.<ext>)")
    args = parser.parse_args()

    skill_path = Path(args.skill_path).expanduser().resolve()
    skill_md = skill_path / "SKILL.md"
    if not skill_md.is_file():
        print(json.dumps({"error": f"SKILL.md not found at {skill_md}"}), file=sys.stderr)
        sys.exit(1)

    if args.tier == "personal":
        print(json.dumps({
            "error": "personal-tier skills are not packaged for distribution. "
                     "Re-run at --tier claude-users or model-agnostic to package.",
        }), file=sys.stderr)
        sys.exit(2)

    name = skill_path.name

    # model-agnostic conformance gate
    if args.tier == "model-agnostic":
        compat = read_frontmatter_compat(skill_md)
        problems = []
        if not compat.startswith("agentskills.io@"):
            problems.append("frontmatter `compatibility` must be `agentskills.io@<version>`")
        exts = has_claude_extensions(skill_md)
        if exts:
            problems.append(f"Claude-only extensions present: {', '.join(exts)}")
        if problems:
            print(json.dumps({
                "error": "model-agnostic conformance failed; cannot package",
                "problems": problems,
                "fix": "Resolve via Step 4's model-agnostic portability fixes, then re-package.",
            }, indent=2), file=sys.stderr)
            sys.exit(3)

    ext = "zip" if args.format == "zip" else "skill"
    output = Path(args.output).expanduser() if args.output else skill_path.parent / f"{name}.{ext}"

    # Collect the included files once (same exclude rules for both formats) so the
    # tarball and the zip carry byte-identical contents — only the container differs.
    members = []
    for f in sorted(skill_path.rglob("*")):
        if not f.is_file():
            continue
        rel = f.relative_to(skill_path)
        if should_exclude(rel):
            continue
        members.append((f, str(Path(name) / rel)))

    included = [arc for _, arc in members]
    try:
        if args.format == "zip":
            with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
                for src, arc in members:
                    zf.write(src, arcname=arc)
        else:
            with tarfile.open(output, "w:gz") as tar:
                for src, arc in members:
                    tar.add(src, arcname=arc)
    except OSError as e:
        print(json.dumps({"error": f"failed to write archive {output}: {e}"}), file=sys.stderr)
        sys.exit(4)

    print(json.dumps({
        "packaged": str(output),
        "tier": args.tier,
        "format": args.format,
        "files_included": len(included),
        "manifest": included,
    }, indent=2))


if __name__ == "__main__":
    main()
