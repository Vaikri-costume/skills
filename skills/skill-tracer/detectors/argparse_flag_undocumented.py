"""argparse-flag-undocumented — argparse flag mismatch: .md documents a --flag (or -f) for a script that does not register it.

Reads *.md files to find `<name>.py ... --flag` / `<name>.py ... -f` invocations of two shapes: an
explicit `python[3] [<dir>/]<name>.py` invocation on any line (a directory prefix such as `scripts/` or
`.../scripts/` is allowed), and a shell-style command start inside a fenced block. Other mentions of a
flag (prose without `python`, inline code without the script name) are not checked.
For the referenced script (looked up by basename under <skill_root>/scripts/), AST-walks every
`add_argument(...)` call to collect the declared flags.

ABSTAIN (per spec) on any script that has NO ArgumentParser / add_argument at all —
it may hand-parse sys.argv, so static analysis cannot be authoritative.

Direction: doc → script only. A flag a script registers that no .md cites is NOT reported:
script-only flags (back-compat aliases, an argparse-help-only option) are legitimate, so the
reverse direction cannot meet Prepass's zero-false-positive bar. An undocumented registered flag
is left to the code-review tier.

Prepass = MUST be 0 false positives.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

CHECK_ID = "argparse-flag-undocumented"
LEVEL = "prepass"
FILE_GLOBS = ["*.py", "*.md"]


# ---------------------------------------------------------------------------
# Helpers — script analysis
# ---------------------------------------------------------------------------

def _collect_argparse_flags(script_src: str) -> tuple[set[str], bool]:
    """Return (registered_flags, has_argparse).

    registered_flags: every --long and -s flag string registered via add_argument, plus -h/--help:
    argparse registers those itself, so a doc citing `script.py --help` is not a mismatch.
    has_argparse: True iff the script contains at least one add_argument call.
    """
    try:
        tree = ast.parse(script_src)
    except SyntaxError:
        return set(), False

    flags: set[str] = set()
    has_add_argument = False

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        # Match foo.add_argument(...) or add_argument(...)
        func = node.func
        is_add_arg = False
        if isinstance(func, ast.Attribute) and func.attr == "add_argument":
            is_add_arg = True
        elif isinstance(func, ast.Name) and func.id == "add_argument":
            is_add_arg = True

        if not is_add_arg:
            continue

        has_add_argument = True
        # Every positional string arg that starts with '-' is a flag name
        for arg in node.args:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                val = arg.value.strip()
                if val.startswith("-"):
                    flags.add(val)

    if has_add_argument:
        flags.update({"-h", "--help"})
    return flags, has_add_argument


# ---------------------------------------------------------------------------
# Helpers — .md parsing
# ---------------------------------------------------------------------------

# Matches shell command invocations of a Python script.
# Strategy to avoid false positives on prose text:
#   1. In code-fence blocks (``` ... ```) — allow any shell-like invocation
#   2. In prose lines — only trust explicit `python[3]? <name>.py` pattern
#
# Within each context we look for flags after the script name.

# Flags: --long-flag or -s (single char, not preceded by word char). Both forms are captured
# wherever a command was recognised; prose is kept conservative by only recognising an explicit
# `python[3] <name>.py` invocation (Pattern A below), not by dropping short flags.
_FLAG_RE = re.compile(r"(--[\w][\w\-]*)|((?<!\w)-[a-zA-Z])\b")

# Capture everything after script token up to end of "command" (newline/backtick/quote)
_REST_RE = re.compile(r"([^\n`\"']*)")

# Pattern A: explicit python/python3 invocation (works in prose and code)
# python3? (optional interpreter flags like -W, -u, -c, -m <module>) [<dir>/...]<name>.py
_PYTHON_INVOKE_RE = re.compile(
    r"python3?\s+(?:-[a-zA-Z]\S*\s+)*"
    r"((?:[\w.~\-]+/)*[\w.\-]+\.py)\b",
    re.IGNORECASE,
)

# Pattern B: script at start of line or after shell separator — only used inside code fences
# Covers:  ./script.py, script.py, $ script.py, | script.py, && script.py, ; script.py
_CMD_START_RE = re.compile(
    r"(?:^|(?<=[\|&;`])\s*|(?<=\$)\s*)\s*"
    r"([\w./\-]+\.py)\b",
    re.IGNORECASE | re.MULTILINE,
)


def _extract_cited_flags(md_src: str) -> list[tuple[int, str, list[str]]]:
    """Return list of (line_no, script_name, [flags_cited]) from a Markdown source.

    Only considers:
    - Lines inside fenced code blocks (``` or ~~~): any shell-like invocation
    - All lines: explicit `python[3] <name>.py` pattern
    """
    results: list[tuple[int, str, list[str]]] = []
    lines = md_src.splitlines()
    in_fence = False
    fence_marker = ""

    for lineno, line in enumerate(lines, start=1):
        # Track fenced code blocks
        stripped = line.strip()
        if not in_fence:
            if stripped.startswith("```") or stripped.startswith("~~~"):
                in_fence = True
                fence_marker = stripped[:3]
                continue
        else:
            if stripped.startswith(fence_marker):
                in_fence = False
                continue

        # Pattern A: python3? <name>.py — valid in any line
        for m in _PYTHON_INVOKE_RE.finditer(line):
            script_name = Path(m.group(1)).name
            rest_m = _REST_RE.match(line, m.end())
            rest = rest_m.group(1) if rest_m else ""
            flags = _FLAG_RE.findall(rest)
            flat = [f for pair in flags for f in pair if f]
            if flat:
                results.append((lineno, script_name, flat))

        # Pattern B: command-start — only inside fenced code blocks, non-comment lines
        if in_fence and not stripped.lstrip().startswith("#"):
            # Avoid double-counting lines already matched by pattern A
            already = {name for (ln, name, _flags) in results if ln == lineno}
            for m in _CMD_START_RE.finditer(line):
                # Look the script up by basename (strips ./ and any directory prefix)
                script_name = Path(m.group(1)).name
                if script_name in already:
                    continue
                rest_m = _REST_RE.match(line, m.end())
                rest = rest_m.group(1) if rest_m else ""
                flags = _FLAG_RE.findall(rest)
                flat = [f for pair in flags for f in pair if f]
                if flat:
                    results.append((lineno, script_name, flat))

    return results


# ---------------------------------------------------------------------------
# Script lookup — find the script file relative to the md file
# ---------------------------------------------------------------------------

def _find_script(md_path: Path, script_name: str) -> Path | None:
    """Search for script_name in the skill tree rooted above md_path.

    Strategy (in order):
    1. <skill_root>/scripts/<script_name>   (canonical location)
    2. Any ancestor directory that contains a scripts/ subdir
    3. A sibling scripts/ dir next to the .md file
    4. The same directory as the .md file

    We define "skill root" as the nearest ancestor that has a scripts/ subdir
    OR a SKILL.md / README.md / skill.yaml (common skill markers).
    """
    # Walk up to find skill root
    for parent in [md_path.parent] + list(md_path.parents):
        scripts_dir = parent / "scripts"
        if scripts_dir.is_dir():
            candidate = scripts_dir / script_name
            if candidate.exists():
                return candidate

    # Fallback: same directory as the .md
    same_dir = md_path.parent / script_name
    if same_dir.exists():
        return same_dir

    return None


# ---------------------------------------------------------------------------
# Main detect
# ---------------------------------------------------------------------------

def detect(path: Path, src: str) -> list[dict]:
    # This detector only does work on .md files (reads the cited .py externally).
    # When called on a .py file we return clean — the actual check is driven by .md.
    if path.suffix.lower() != ".md":
        return []

    cited = _extract_cited_flags(src)
    if not cited:
        return []

    findings: list[dict] = []
    abstained: set[str] = set()
    # Cache script analysis to avoid re-reading the same file multiple times
    script_cache: dict[Path, tuple[set[str], bool] | None] = {}

    for lineno, script_name, flags in cited:
        script_path = _find_script(path, script_name)
        if script_path is None:
            # Can't find the script, so this reference cannot be verified: skip it (clean).
            # Per spec an abstain is only for a script that exists but has no ArgumentParser.
            continue

        if script_path not in script_cache:
            try:
                script_src = script_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                script_cache[script_path] = None
                continue
            script_cache[script_path] = _collect_argparse_flags(script_src)

        result = script_cache[script_path]
        if result is None:
            continue

        registered_flags, has_add_argument = result

        if not has_add_argument:
            # Script hand-parses sys.argv — abstain per spec. cascade_sweep treats each returned
            # record on its own (an abstain record only increments the abstain count), so the
            # abstain covers just this script's references; findings about other scripts cited in
            # the same file are kept.
            if script_name not in abstained:
                abstained.add(script_name)
                findings.append({"line": 0,
                                 "detail": f"abstain: {script_name} has no add_argument calls (may hand-parse sys.argv)",
                                 "abstain": True})
            continue

        for flag in flags:
            if flag not in registered_flags:
                findings.append({
                    "line": lineno,
                    "detail": (
                        f"`{flag}` cited for `{script_name}` in docs but not registered "
                        f"in argparse (registered: {sorted(registered_flags) or 'none'})"
                    ),
                })

    return findings
