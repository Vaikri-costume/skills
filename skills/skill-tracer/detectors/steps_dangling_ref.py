"""steps — dangling Step N reference in .md files (line-by-line).

A `Step N` reference is dangling when the number N is not covered by any step
sequence in the file being checked (LOCAL resolution) AND is not covered by any
step sequence in SKILL.md at the skill root.

Three cases are never reported:

  LOCAL RESOLUTION — a reference file with its OWN step headers resolves
       `Step N` refs against its OWN headers first.  Only if the number is out
       of range locally does it fall back to SKILL.md.  A reference file that
       defines `## Step 6` makes every "Step 6" ref in that file clean, even if
       SKILL.md only goes up to Step 4.

  DEFINITION NOT REF — a line that IS a step header (`## Step 6`) is a
       definition.  It is never a dangling reference.

  QUOTED / FOREIGN PHRASING — refs inside fenced code blocks, inside
       inline backtick spans, inside double-quoted strings on the same line,
       or matching the `X's Step N` / `X\\'s Step N` foreign-skill pattern
       are skipped.  These are illustrative anti-pattern examples, not live
       cross-SKILL.md citations.

ABSTAIN guards (Prepass prefers abstaining to reporting an unverifiable reference):
  - No SKILL.md found walking up from the scanned file: abstain on the file.
  - A Step N ref appears on a line that also contains a `.md` or `.py` path
    reference (likely a cross-agent/cross-file citation): skip that finding.
  - SKILL.md has multiple independent sequences (number resets after a gap):
    N is covered if it falls within the max of ANY sequence.  Beyond all
    sequence maxima it is still potentially from a sub-agent — the line-level
    file-ref guard provides a second safety net.

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
    find_skill_root_from_file as _find_skill_root_from_file,
    cross_skill_context as _common_cross_skill_context,
)

CHECK_ID = "steps"
LEVEL = "prepass"
FILE_GLOBS = ["*.md"]

# Step reference in prose: "Step 7", "Steps 5", "Step 11(a)", "Steps 1-4"
# We capture the FIRST number only (the ref target).
_STEP_REF_RE = re.compile(r"\bSteps?\s+(\d+)")

# Step DEFINITION header: "## Step N", "### Step N", "#### Step N"
_STEP_HDR_RE = re.compile(r"^#{2,4}\s*Step\s+(\d+)", re.MULTILINE)

# Fenced code block delimiter (``` or ~~~, optional language tag)
_FENCE_RE = re.compile(r"^[ \t]*(?:```|~~~)", re.MULTILINE)

# HTML comment delimiter (<!-- ... -->)
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)

# Inline `.md` or `.py` file reference on the same line (cross-file signal)
_FILE_REF_RE = re.compile(r"[\w./-]+\.(?:md|py)\b")

# Foreign-skill step phrasing: "X's Step N" or "X\\'s Step N" (apostrophe variants)
_FOREIGN_RE = re.compile(r"\w[’']s\s+Step\s+\d+|\w+'s\s+Step\s+\d+", re.I)

_CROSS_SKILL_WINDOW = 60  # chars looked back for a sibling-skill name


def _find_skill_md(path: Path) -> Path | None:
    """Walk up from `path` to find the nearest SKILL.md (the skill root marker)."""
    root = _find_skill_root_from_file(path)
    return (root / "SKILL.md") if root is not None else None


def _step_ranges(text: str) -> set[int]:
    """Return the set of all step numbers defined as headers in `text`."""
    return {int(n) for n in _STEP_HDR_RE.findall(text)}


def _fenced_intervals(text: str) -> list[tuple[int, int]]:
    """Return (start, end) character intervals that are inside fenced code blocks."""
    intervals: list[tuple[int, int]] = []
    fences = [m.start() for m in _FENCE_RE.finditer(text)]
    # Pair consecutive fences: [open, close, open, close, ...]
    for i in range(0, len(fences) - 1, 2):
        intervals.append((fences[i], fences[i + 1]))
    return intervals


def _html_comment_intervals(text: str) -> list[tuple[int, int]]:
    """Return (start, end) character intervals that are inside HTML comments."""
    return [(m.start(), m.end()) for m in _HTML_COMMENT_RE.finditer(text)]


def _in_interval(pos: int, intervals: list[tuple[int, int]]) -> bool:
    return any(start <= pos < end for start, end in intervals)


def _in_inline_code(line: str, local_pos: int) -> bool:
    """True if `local_pos` in `line` is inside a backtick-delimited inline code span."""
    return line[:local_pos].count("`") % 2 == 1


def _in_double_quote(line: str, local_pos: int) -> bool:
    """True if `local_pos` in `line` is between a pair of double-quote characters."""
    return line[:local_pos].count('"') % 2 == 1


def _cross_skill_context(text: str, start: int) -> bool:
    """True when a sibling-skill name appears within 60 chars before the match."""
    return _common_cross_skill_context(text, start, _CROSS_SKILL_WINDOW)


def detect(path: Path, src: str) -> list[dict]:
    # --- Locate SKILL.md for this file ---
    # Skip SKILL.md itself: its step HEADERS define the valid range, not refs to check.
    if path.name == "SKILL.md":
        # SKILL.md's own prose refs are resolved against itself — always in-range.
        # The only interesting case would be refs to other files' steps, which
        # cannot be statically resolved here.  Return clean to avoid FPs.
        return []

    skill_md_path = _find_skill_md(path)
    if skill_md_path is None:
        # Can't determine valid step range without SKILL.md — abstain.
        return [{"line": 0, "detail": "abstain: no SKILL.md found walking up from file",
                 "abstain": True}]

    skill_text = skill_md_path.read_text(encoding="utf-8", errors="replace")
    skill_valid = _step_ranges(skill_text)
    if not skill_valid:
        # SKILL.md has no step headers → not a stepwise skill; nothing to check.
        return []

    skill_hi = max(skill_valid)

    # --- Local step set for THIS file ---
    local_valid = _step_ranges(src)
    local_hi = max(local_valid) if local_valid else 0

    # --- Pre-compute skip intervals (fenced code blocks + HTML comments) ---
    fenced = _fenced_intervals(src)
    html_comments = _html_comment_intervals(src)

    lines = src.splitlines()
    out: list[dict] = []

    for m in _STEP_REF_RE.finditer(src):
        n = int(m.group(1))
        pos = m.start()

        # Guard FP-2: skip if this line IS a step-header definition
        line_idx = src.count("\n", 0, pos)
        line_text = lines[line_idx] if line_idx < len(lines) else ""
        if _STEP_HDR_RE.match(line_text.strip()):
            continue

        # Guard FP-3a: skip refs inside fenced code blocks or HTML comments
        if _in_interval(pos, fenced) or _in_interval(pos, html_comments):
            continue

        # Guard FP-3b: skip refs inside inline backtick code span
        local_pos = pos - (src.rfind("\n", 0, pos) + 1)
        if _in_inline_code(line_text, local_pos):
            continue

        # Guard FP-3c: skip refs inside double-quoted strings on same line
        if _in_double_quote(line_text, local_pos):
            continue

        # Guard FP-3d: skip "X's Step N" foreign-skill phrasing
        ctx_window = src[max(0, pos - 25): m.end() + 5]
        if _FOREIGN_RE.search(ctx_window):
            continue

        # Guard: cross-skill sibling context
        if _cross_skill_context(src, pos):
            continue

        # Guard FP-1: LOCAL RESOLUTION — if this file has its own step headers,
        # a ref to N within the local range resolves locally (clean).
        if local_valid and n <= local_hi:
            continue

        # At this point: n is beyond the local file's step range (or the file has
        # no local step headers). Fall back to SKILL.md's valid range.
        if n <= skill_hi:
            continue

        # n > skill_hi: potentially dangling.  Apply the file-ref abstain guard:
        # if the line also contains a .md/.py path (cross-agent citation), skip —
        # we cannot statically determine whether the ref belongs to that file.
        if _FILE_REF_RE.search(line_text):
            continue  # abstain on this finding (cross-file ref, undecidable)

        line_num = line_idx + 1
        out.append({
            "line": line_num,
            "detail": (
                f"`Step {n}` referenced but no local step header or SKILL.md step "
                f"covers it (SKILL.md valid range: 1..{skill_hi}; "
                f"local headers: {sorted(local_valid) if local_valid else 'none'})"
            ),
        })

    return out
