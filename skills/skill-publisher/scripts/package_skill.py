#!/usr/bin/env python3
"""Package a CCVW skill for distribution as a .skill archive.

Pure-stdlib (tarfile + argparse + re + json). Per-tier packaging:
- personal: refuses (personal skills aren't packaged for distribution)
- claude-users: .skill tarball installable on Claude Code + Cowork
- model-agnostic: same tarball + an agentskills.io conformance gate

Exit codes: 0 success; 1 SKILL.md absent (error JSON on stderr); 2 personal-tier
refusal (error JSON on stderr) or argparse usage error (usage text, no JSON);
3 model-agnostic conformance failure; 4 package write failure (SHA256SUMS temp
write, archive write, or a tar/zip error — error JSON on stderr; any partial
artifact is removed so a later verify_ship can't mistake it for a good ship).

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
import os
import re
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

# Streaming SHA-256 lives in one place (hashutil) so package_skill and verify_ship
# cannot drift on the digest implementation.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from hashutil import sha256_file as _sha256_file


EXCLUDE_NAME_PATTERNS = [
    re.compile(r"\.bak"),        # *.bak* pre-edit snapshots
    re.compile(r"\.orig$"),      # *.orig patch/merge backups
    re.compile(r"^\."),          # hidden files/dirs (.DS_Store, .gitignore, .git/, ...)
    re.compile(r"^__pycache__$"),# Python bytecode cache dirs
    re.compile(r"\.py[co]$"),    # compiled .pyc/.pyo bytecode
]
EXCLUDE_PATH_SUBSTRINGS = [
    "-workspace/",
]


def should_exclude(rel_path: Path) -> bool:
    # Check EVERY path component, not just the basename, so an excluded directory
    # (.git/, __pycache__/) drops its whole subtree — the leaf files' own names
    # aren't dotted/patterned, so a basename-only check would let them through.
    parts = rel_path.parts
    for part in parts:
        for pat in EXCLUDE_NAME_PATTERNS:
            if pat.search(part):
                return True
    # eval run-outputs: an `evals` component immediately followed by `iteration-*`,
    # at ANY depth INCLUDING top-level. A substring like "/evals/iteration-" misses
    # the top-level `evals/iteration-…` case (no leading slash in a relative path),
    # so match on path components instead.
    for a, b in zip(parts, parts[1:]):
        if a == "evals" and b.startswith("iteration-"):
            return True
    s = str(rel_path)
    for sub in EXCLUDE_PATH_SUBSTRINGS:
        if sub in s:
            return True
    return False


def read_frontmatter_compat(skill_md: Path) -> str:
    """Best-effort read of the `compatibility:` frontmatter value (flat scalar).
    Delegates to frontmatter_util (the single home of the BOM/CRLF/trailing-newline-
    tolerant frontmatter scan, shared with readiness_report). On the model-agnostic
    path an empty return degrades gracefully (empty compat = conformance fails)."""
    try:
        text = skill_md.read_text(encoding="utf-8")
    except OSError:
        return ""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from frontmatter_util import block, field
    return field(block(text), "compatibility") or ""


def has_claude_extensions(skill_md: Path) -> list:
    """Cheap scan for Claude-only patterns that block model-agnostic packaging.
    This is an independent inline copy of the four most-blocking patterns, NOT an
    import of portability_lint's CLAUDE_BODY_PATTERNS. Intentionally omits patterns
    that are informational at step 4 but not packaging-blocking (e.g. $XDG paths).
    If portability_lint's blocking list changes, review whether this function needs
    updating too — it is a FINAL gate after step 4 already ran the full lint."""
    try:
        body = skill_md.read_text(encoding="utf-8")
    except OSError:
        return []
    patterns = [
        (r"\bAgent\s+tool\b", "Agent tool dispatch"),
        (r"\$ARGUMENTS\[\d+\]", "$ARGUMENTS[N]"),
        (r"!\s*`[^`]+`", "dynamic shell injection"),
        (r"\bmcp__[a-zA-Z0-9_]+__[a-zA-Z0-9_]+\b", "mcp__*__* tool name"),
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

    # Per-file SHA-256 digests → a SHA256SUMS manifest shipped INSIDE the package,
    # keyed by the path relative to the package root (the <name>/ dir) so a
    # `sha256sum -c SHA256SUMS` from inside the unpacked skill validates each file.
    # The whole-archive digest cannot live inside the archive (it would hash
    # itself) — it is emitted in the JSON below and recorded in the ship manifest.
    sums_lines = []
    for src, arc in members:
        rel_in_pkg = Path(arc).relative_to(name).as_posix()
        sums_lines.append(f"{_sha256_file(src)}  {rel_in_pkg}")
    sums_text = "\n".join(sums_lines) + "\n"
    # Unique temp file (pid + counter via mkstemp) so two concurrent packagings of
    # the SAME skill don't race on a fixed path. Closed immediately; written below.
    _fd, _sums_name = tempfile.mkstemp(prefix=f"skill-publisher-SHA256SUMS-{name}-", suffix=".txt")
    os.close(_fd)
    sums_tmp = Path(_sums_name)

    included = None
    try:
        # One handler for EVERY package-write failure — the SHA256SUMS temp write,
        # the archive write, and the archive-specific tar/zip errors (which are NOT
        # OSError subclasses) — so all of them exit 4 with a JSON error (never an
        # uncaught traceback / exit 1) and leave no partial artifact behind.
        try:
            sums_tmp.write_text(sums_text, encoding="utf-8")
            # Append SHA256SUMS itself to the archive (it is not in its own sums list).
            members.append((sums_tmp, str(Path(name) / "SHA256SUMS")))
            included = [arc for _, arc in members]
            if args.format == "zip":
                with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
                    for src, arc in members:
                        zf.write(src, arcname=arc)
            else:
                with tarfile.open(output, "w:gz") as tar:
                    for src, arc in members:
                        tar.add(src, arcname=arc)
        except (OSError, tarfile.TarError, zipfile.BadZipFile, zipfile.LargeZipFile) as e:
            # Remove any partially-written artifact so a later verify_ship can't
            # mistake a truncated file for a good ship.
            try:
                if output.exists():
                    output.unlink()
            except OSError:
                pass
            print(json.dumps({"error": f"failed to write package {output}: {e}"}), file=sys.stderr)
            sys.exit(4)
    finally:
        try:
            sums_tmp.unlink()
        except OSError:
            pass

    # Digest of the final archive bytes — lets verify_ship.py (Step 10) confirm the
    # artifact on disk is byte-for-byte the one packaged here, and the ship manifest
    # record it for later integrity checks (Phase 4 rollback / status).
    archive_sha256 = _sha256_file(output)

    print(json.dumps({
        "packaged": str(output),
        "tier": args.tier,
        "format": args.format,
        "files_included": len(included),
        "archive_sha256": archive_sha256,
        "sha256sums_included": True,
        "manifest": included,
    }, indent=2))


if __name__ == "__main__":
    main()
