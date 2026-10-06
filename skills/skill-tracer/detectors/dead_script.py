"""dead-script — scripts/*.py that no in-scope text file mentions AND no in-scope sibling .py imports.

A standalone Prepass detector.

Package-marker basenames (__init__.py, __main__.py, conftest.py) are excluded. These are
structural markers, not entry-point scripts. A package with __init__.py is "alive" by
definition — it is the importable namespace, not a dead file. Similarly, __main__.py is
the -m entry point and conftest.py is pytest infrastructure.

_collect_text_references scans .sh, .yaml, .yml, .toml, .json, Makefile, and Taskfile files
as well as .md for script name mentions, so a script invoked only from a shell script,
Makefile, or YAML/TOML config counts as alive.

Liveness rules:
  - text mention: any in-scope .md (or one of the text files above) that names the basename
    (helper.py) keeps it alive
  - import-aware: a sibling script that imports the stem (import helper / from helper import X)
    keeps it alive even when no prose names it

Abstain-on-undecidable: this check is multi-file by nature. If the skill root cannot be
determined (file not under a scripts/ directory) the file is out of scope and ignored (clean).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# The shared in-scope authority (scripts/inscope.py): README/HISTORY/LICENSE are excluded so a script
# cited only in a changelog is not read as alive, the same scope every other tier uses.
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
from inscope import inscope_files  # noqa: E402

CHECK_ID = "dead-script"
LEVEL = "prepass"
FILE_GLOBS = ["*.py"]

# Basenames that are structural / package markers — never dead by definition.
_PACKAGE_MARKERS = {"__init__.py", "__main__.py", "conftest.py"}

# Matches a .py basename anywhere in text: e.g. "helper.py"
_SCRIPT_NAME_RE = re.compile(r"\b([\w-]+\.py)\b")

# Matches import stems: `import foo` or `from foo import …` (module stem only, not dotted)
_IMPORT_STEM_RE = re.compile(r"^\s*(?:from|import)\s+([\w]+)", re.MULTILINE)


def _find_skill_root(scripts_dir: Path) -> Path:
    """The skill root is the parent of the scripts/ directory."""
    return scripts_dir.parent


_TEXT_GLOBS = (
    "*.md", "*.sh", "*.yaml", "*.yml", "*.toml", "*.json", "Makefile", "Taskfile",
)


def _collect_text_references(root: Path) -> str:
    """Concatenate all in-scope text reference files under the skill root.

    Scans .md, .sh, .yaml, .yml, .toml, .json, Makefile, and Taskfile files so that
    scripts invoked from shell scripts, Makefiles, or config files are treated as alive.
    The rglob already covers the full skill tree for each glob; files outside the shared
    in-scope set (README.md, HISTORY.md, LICENSE, ...) are skipped.
    """
    allowed = {p.resolve() for p in inscope_files(root)}
    parts = []
    for glob in _TEXT_GLOBS:
        for f in root.rglob(glob):
            if f.resolve() not in allowed:
                continue
            try:
                parts.append(f.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                pass
    return "\n".join(parts)


def _collect_py_import_stems(root: Path, exclude: Path) -> set[str]:
    """Collect all module stems imported anywhere in the skill's in-scope .py files (excluding self)."""
    stems: set[str] = set()
    allowed = {p.resolve() for p in inscope_files(root)}
    for f in root.rglob("*.py"):
        if f == exclude or f.resolve() not in allowed:
            continue
        try:
            src = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        stems.update(_IMPORT_STEM_RE.findall(src))
    return stems


def detect(path: Path, _src: str) -> list[dict]:
    """Return dead-script findings for path.

    The second argument (the file's text) is part of the shared detector interface: the
    sweep and doc_lint call every detector as detect(path, src). This check decides liveness
    from other files in the skill, not from the script's own text, so it does not read it.
    """
    # Only applies to files directly inside a `scripts/` directory.
    if path.parent.name != "scripts":
        return []

    # Package-marker basenames are always alive — exclude unconditionally.
    if path.name in _PACKAGE_MARKERS:
        return []

    scripts_dir = path.parent
    root = _find_skill_root(scripts_dir)

    # Collect all text references in the skill to check prose/config mentions.
    md_text = _collect_text_references(root)
    mentioned = set(_SCRIPT_NAME_RE.findall(md_text))

    if path.name in mentioned:
        return []  # prose names this script — alive

    # Collect import stems from all sibling .py files.
    imported = _collect_py_import_stems(root, exclude=path)

    if path.stem in imported:
        return []  # imported by a sibling — alive (shared helper pattern)

    return [{"line": 1, "detail": (
        f"`{path.name}` is not mentioned in any in-scope text file and is imported by no sibling script "
        f"— dead code, or a missing wire-up"
    )}]
