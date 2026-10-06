"""refs — cited references/scripts/assets paths that don't exist on disk.

A cited in-tree path of the form `references/X.md`, `scripts/Y.py`,
`assets/Z.md`, etc. is flagged when it does NOT exist under the skill root
AND is not a cross-skill reference (see below).

Exclusions:
  - Placeholder stems: x, y, z, n, foo, bar, baz, qux, name, skill, example
    (and placeholder basenames X.md, foo.md — stems are lowercased before check)
  - Skip-basenames: README.md, HISTORY.md, LICENSE (and LICENSE.* variants)
  - Cross-skill refs: a sibling-skill name appears in the 45 chars before the match AND the
    path exists under THAT skill's directory (when that skill is installed; if it is not
    installed the citation cannot be verified and is left alone). A path that merely exists
    under some unrelated sibling skill does not excuse an unqualified citation.

ABSTAIN cases: a file with no SKILL.md found walking up from it (the skill root, which every
reference resolves against, is unknown). Otherwise none: after the exclusions every remaining match
is a path that does not exist.

Level: Prepass.
"""
from __future__ import annotations

import re
from pathlib import Path
import sys as _sys

_DET_DIR = Path(__file__).resolve().parent
if str(_DET_DIR) not in _sys.path:
    _sys.path.insert(0, str(_DET_DIR))
from _common import (
    find_skill_root_from_file as _find_skill_root,
    line_of as _line_of,
    SIBLING_SKILL_NAMES as _SIBLING_SKILL_NAMES,
)

CHECK_ID = "refs"
LEVEL = "prepass"
FILE_GLOBS = ["*.md"]

# A cited in-tree path: references/x.md, scripts/y.py, assets/z.md, eval-viewer/w.py …
_PATH_RE = re.compile(
    r"(?<![\w./-])((?:references|scripts|assets|eval-viewer)/[\w./-]+\.(?:md|py|json|txt))"
)

_CROSS_SKILL_WINDOW = 45  # chars looked back for a sibling-skill name

# Metasyntactic / single-letter stems are illustrative placeholders, never real citations.
_PLACEHOLDER_STEMS = {"x", "y", "z", "n", "foo", "bar", "baz", "qux", "name", "skill", "example"}
_SKIP_REF_BASENAMES = {"README.md", "HISTORY.md", "LICENSE"}


def _is_placeholder_path(rel: str) -> bool:
    stem = Path(rel).stem.lower()
    base = Path(rel).name
    return stem in _PLACEHOLDER_STEMS or base in _SKIP_REF_BASENAMES or base.startswith("LICENSE.")


def _cited_sibling_verdict(text: str, start: int, rel: str, skills_root: Path) -> bool:
    """True when the citation is a QUALIFIED cross-skill reference that checks out: a sibling-skill
    name appears just before the match and either that skill is not installed here (unverifiable,
    left alone) or `rel` exists under it."""
    lookback = text[max(0, start - _CROSS_SKILL_WINDOW): start].lower()
    for name in _SIBLING_SKILL_NAMES:
        if name not in lookback:
            continue
        sibling = skills_root / name
        if not sibling.is_dir() or (sibling / rel).exists():
            return True
    return False


def detect(path: Path, src: str) -> list[dict]:
    root = _find_skill_root(path)
    if root is None:
        # Can't determine skill root — abstain rather than guess.
        return [{"line": 0, "detail": "abstain: no SKILL.md found walking up from file",
                 "abstain": True}]

    # Derive skills root from the skill's own location — environment-independent.
    skill_root = root
    skills_root = skill_root.parent

    out: list[dict] = []
    for m in _PATH_RE.finditer(src):
        rel = m.group(1)
        if (root / rel).exists() or _is_placeholder_path(rel):
            continue
        if _cited_sibling_verdict(src, m.start(), rel, skills_root):
            continue  # a qualified reference to another skill's file
        out.append({
            "line": _line_of(src, m.start()),
            "detail": (
                f"cited `{rel}` does not exist under the skill root (nor under a sibling skill the citation names)"
            ),
        })
    return out
