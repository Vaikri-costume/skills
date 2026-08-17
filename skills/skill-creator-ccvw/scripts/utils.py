"""Shared utilities for skill-creator scripts."""

import os
import shutil
from pathlib import Path


def claude_subprocess_env() -> dict[str, str]:
    """Environment for nesting `claude -p` inside a Claude Code session.

    Drops CLAUDECODE — the guard that exists to prevent interactive-terminal
    conflicts; programmatic subprocess use is safe. Single home for this strip
    rule so every nested-`claude -p` call site stays in sync (run_eval's
    preflight + per-query dispatch, improve_description's call).
    """
    return {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}


def claude_binary() -> str:
    """Resolve the `claude` executable for subprocess dispatch.

    Plain subprocess.Popen/run with cmd[0]="claude" doesn't consult PATHEXT
    on Windows, so the npm shim `claude.CMD` is invisible even though `claude`
    resolves fine in an interactive shell. shutil.which() does the PATHEXT
    lookup; falling back to the bare name preserves prior behavior (and the
    existing FileNotFoundError handling) everywhere shutil.which finds nothing.
    """
    return shutil.which("claude") or "claude"


def parse_skill_md(skill_path: Path) -> tuple[str, str, str]:
    """Parse a SKILL.md file, returning (name, description, full_content)."""
    # utf-8-sig transparently strips a leading UTF-8 BOM (some editors and
    # OneDrive sync flows prepend one), which would otherwise make the
    # frontmatter split on "---" fail to find the opening delimiter.
    content = (skill_path / "SKILL.md").read_text(encoding="utf-8-sig")
    lines = content.split("\n")

    if lines[0].strip() != "---":
        raise ValueError("SKILL.md missing frontmatter (no opening ---)")

    end_idx = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end_idx = i
            break

    if end_idx is None:
        raise ValueError("SKILL.md missing frontmatter (no closing ---)")

    name = ""
    description = ""
    frontmatter_lines = lines[1:end_idx]
    i = 0
    while i < len(frontmatter_lines):
        line = frontmatter_lines[i]
        if line.startswith("name:"):
            name = line[len("name:"):].strip().strip('"').strip("'")
        elif line.startswith("description:"):
            value = line[len("description:"):].strip()
            # Handle YAML multiline indicators (>, |, >-, |-)
            if value in (">", "|", ">-", "|-"):
                continuation_lines: list[str] = []
                i += 1
                while i < len(frontmatter_lines) and (frontmatter_lines[i].startswith("  ") or frontmatter_lines[i].startswith("\t")):
                    continuation_lines.append(frontmatter_lines[i].strip())
                    i += 1
                description = " ".join(continuation_lines)
                continue
            else:
                description = value.strip('"').strip("'")
        i += 1

    return name, description, content
