"""_common — helpers the remaining detectors would otherwise duplicate.

`_`-prefixed filenames are skipped by cascade_sweep.py's detector loader, so this module is imported,
never run as a detector. Each detector loads standalone (importlib.util.spec_from_file_location), so it
adds its own directory to sys.path before `from _common import X`.

Callers:
  - find_skill_root_from_file, SIBLING_SKILL_NAMES, cross_skill_context: refs_broken_file.py and
    steps_dangling_ref.py (walk up to the nearest SKILL.md; skip a citation that names a sibling skill).
  - inscope_glob: missing_glossary_entry.py (sibling files restricted to the shared in-scope set).
  - collect_fenced_line_set, SUBSTEP_REF_RE: substep_label_mismatch.py.
  - find_skill_root_from_file: also missing_glossary_entry.py.
  - line_of: refs_broken_file.py, missing_glossary_entry.py and substep_label_mismatch.py.
"""
from __future__ import annotations

import re
import sys as _sys
from pathlib import Path

_DET_DIR = Path(__file__).resolve().parent


def find_skill_root_from_file(path: Path) -> Path | None:
    """The directory of the nearest SKILL.md above the scanned *path*, or None."""
    for parent in path.parents:
        if (parent / "SKILL.md").is_file():
            return parent
    return None


def line_of(text: str, idx: int) -> int:
    """The 1-based line number of character offset *idx* in *text*."""
    return text.count("\n", 0, idx) + 1


def inscope_glob(skill_root: Path, pattern: str) -> list[Path]:
    """Files under `skill_root` matching `pattern` that are also in the shared in-scope set
    (scripts/inscope.py `inscope_files`), so a detector reading sibling files sees the same files the
    sweep hands to `detect()`."""
    scripts_dir = str(_DET_DIR.parent / "scripts")
    if scripts_dir not in _sys.path:
        _sys.path.insert(0, scripts_dir)
    from inscope import inscope_files
    allowed = set(inscope_files(skill_root))
    return [p for p in sorted(skill_root.rglob(pattern)) if p.resolve() in allowed]


# Names that qualify a reference as belonging to ANOTHER skill, so a legitimate cross-skill citation
# is not reported as dangling or broken.
SIBLING_SKILL_NAMES = (
    "skill-creator-ccvw", "skill-creator", "skill-tracer", "skill-publisher",
    "plugin-dev", "another skill", "the creator", "the publisher", "the tracer",
)


def cross_skill_context(text: str, start: int, window: int) -> bool:
    """True when a sibling-skill name appears within `window` chars before `start`."""
    lookback = text[max(0, start - window): start].lower()
    return any(name in lookback for name in SIBLING_SKILL_NAMES)


_PLAIN_FENCE_RE = re.compile(r"^(`{3,}|~{3,})")


def collect_fenced_line_set(lines: list[str]) -> set[int]:
    """0-based indices of the lines that are fence delimiters (```/~~~) or fenced content."""
    fenced: set[int] = set()
    fence: str | None = None
    for i, raw_line in enumerate(lines):
        stripped = raw_line.strip()
        m = _PLAIN_FENCE_RE.match(stripped)
        if m and fence is None:
            fence = m.group(1)
            fenced.add(i)
        elif fence is not None:
            fenced.add(i)
            if m and stripped.startswith(fence):
                fence = None
    return fenced


# A lettered sub-step reference in body text: "Step 4(b)", "Step 4b", "Step 4(ii)", "step 4 (b)".
# Groups: 1 = step number, 2 = parenthesised label; 3 = step number, 4 = appended letter.
SUBSTEP_REF_RE = re.compile(
    r"\bStep\s+(\d+)\s*"
    r"\(([a-zA-Z](?:i{1,4}|ii?|iv|vi{0,3})?)\)"
    r"|"
    r"\bStep\s+(\d+)"
    r"([a-zA-Z])\b",
    re.IGNORECASE,
)
