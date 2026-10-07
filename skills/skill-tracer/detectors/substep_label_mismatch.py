"""substep-label-mismatch — lettered substep label mismatch (Prepass check for lettered sub-step labels).

Fires ONLY when ALL of the following hold:
  1. A `Step N(x)` reference (or `Step Nx` bare form) exists in the file on a line outside
     a code fence. Only fences exempt a reference: one inside inline backticks or double
     quotes, in "<other-skill>'s Step 3(b)" phrasing, or on a line citing another file
     ("references/x.md Step 3(b)") is still checked against THIS file's own Step N body
     (steps_dangling_ref.py skips those cases; this check does not).
  2. Step N's body exists and contains at least one EXPLICIT lettered sub-marker at
     line-start — i.e. a line that starts (after optional indent / list-bullet) with
     `(a)`, `(b)`, `(ii)`, `### (b)`, `- (c)`, `* (b)`.
  3. The referenced label `x` is NOT among the explicit markers found in Step N's body.

This is a purely mechanical membership check — no semantic judgment needed.

Why this is Prepass (a mechanical check; the one reference shape it can misjudge is a quoted
or other-file citation of a Step N this file also defines, listed under condition 1):
  - If the body has explicit `(a)` / `(b)` / ... markers, the enumeration is structured
    and presence/absence of a given label is unambiguous.
  - If the body uses implicit/prose enumeration ("first ... then ...") with no
    line-start `(x)` markers, condition 2 fails and the detector returns clean.
    That prose case is not covered by any active detector.
  - Code fences are excluded so `(b)` inside a code example does not count as
    a real sub-label marker.

ABSTAIN cases:
  - File has no recognisable Step headers at all but does contain `Step N(x)` refs.
  - Syntax/encoding issues (handled by the harness, not here).
"""
from __future__ import annotations

import re
import sys as _sys
from pathlib import Path

_DET_DIR = Path(__file__).resolve().parent
if str(_DET_DIR) not in _sys.path:
    _sys.path.insert(0, str(_DET_DIR))
from _common import (
    collect_fenced_line_set as _collect_fenced_line_set,
    line_of as _line_of,
    SUBSTEP_REF_RE as _REF_RE,
)

CHECK_ID   = "substep-label-mismatch"
LEVEL      = "prepass"
FILE_GLOBS = ["*.md"]

# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

# Matches a step header line like (the number may end the line):
#   ## Step 3   /  **Step 3**  /  Step 3:  /  ### Step 3.
_STEP_HEADER_LINE_RE = re.compile(
    r"^(?:#+\s+|\*{1,2})?Step\s+(\d+)(?:\*{1,2})?(?:[:.\s]|$)",
    re.IGNORECASE,
)

# Explicit lettered sub-label at the START of a line (after optional indent / list bullet).
# Matches:  (a)  /  (b)  /  (ii)  /  ### (b)  /  - (c)  /  * (b)
# Does NOT match mid-sentence "(b)" or code-fence content.
_EXPLICIT_LABEL_RE = re.compile(
    r"^[ \t]*"               # optional leading whitespace
    r"(?:#{1,6}\s+)?"        # optional heading markers
    r"(?:[-*+]\s+)?"         # optional list bullet
    r"\(([a-zA-Z](?:i{1,4}|ii?|iv|vi{0,3})?)\)"  # the label: (a), (b), (ii), ... (the shape `_common.SUBSTEP_REF_RE` captures)
    ,
    re.MULTILINE,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fenced_line_indices(lines: list[str]) -> set[int]:
    """0-based indices of fence delimiter lines and fenced content (shared `_common.collect_fenced_line_set`)."""
    return _collect_fenced_line_set(lines)


def _split_into_steps(lines: list[str], fenced: set[int]) -> dict[int, tuple[int, str]]:
    """Return {step_num: (header_line_1based, body_text)} for each step header.

    Body = lines after the header up to (but not including) the next step header.
    Only header lines that are NOT inside fenced blocks are considered.
    """
    header_positions: list[tuple[int, int]] = []  # (0-based line index, step_num)
    for i, line in enumerate(lines):
        if i in fenced:
            continue
        m = _STEP_HEADER_LINE_RE.match(line)
        if m:
            header_positions.append((i, int(m.group(1))))

    steps: dict[int, tuple[int, str]] = {}
    for idx, (line_idx, step_num) in enumerate(header_positions):
        start = line_idx + 1
        end = header_positions[idx + 1][0] if idx + 1 < len(header_positions) else len(lines)
        body = "\n".join(lines[start:end])
        steps[step_num] = (line_idx + 1, body)  # 1-based header line
    return steps


def _explicit_labels_in_body(body: str) -> set[str]:
    """Return the set of explicitly-marked sub-labels found in body, excluding fenced content.

    Fencing is recomputed over the body's own lines so labels inside code blocks are excluded.
    """
    body_lines = body.splitlines()
    body_fenced = _fenced_line_indices(body_lines)

    labels: set[str] = set()
    for i, line in enumerate(body_lines):
        if i in body_fenced:
            continue
        m = _EXPLICIT_LABEL_RE.match(line)
        if m:
            labels.add(m.group(1).lower())
    return labels


# ---------------------------------------------------------------------------
# Detector
# ---------------------------------------------------------------------------

def detect(_path: Path, src: str) -> list[dict]:
    """Return substep-label-mismatch findings for src.

    The first argument (the file path) is part of the shared detector interface: the sweep
    and doc_lint call every detector as detect(path, src). This check works on the text alone.
    """
    lines = src.splitlines(keepends=True)
    fenced = _fenced_line_indices([l.rstrip("\n") for l in lines])
    steps = _split_into_steps([l.rstrip("\n") for l in lines], fenced)

    # Collect all Step N(x) references from non-fenced lines
    refs_exist = False
    for m in _REF_RE.finditer(src):
        char_start = m.start()
        ref_line_0 = src[:char_start].count("\n")
        if ref_line_0 not in fenced:
            refs_exist = True
            break

    if not steps:
        if refs_exist:
            return [{
                "line": 0,
                "detail": (
                    "abstain: file contains Step N(x) references but no recognisable "
                    "Step N headers — cannot locate bodies to probe"
                ),
                "abstain": True,
            }]
        return []

    findings: list[dict] = []

    for m in _REF_RE.finditer(src):
        # Determine which alternative matched
        if m.group(1) is not None:
            step_num = int(m.group(1))
            label    = m.group(2).lower()
        else:
            step_num = int(m.group(3))
            label    = m.group(4).lower()

        ref_line = _line_of(src, m.start())
        ref_line_0 = ref_line - 1

        # Skip refs inside fenced blocks
        if ref_line_0 in fenced:
            continue

        if step_num not in steps:
            # Referenced step doesn't exist — not our job (integer-step check handles this).
            # Return clean for this reference (don't abstain: it is a different check's concern).
            continue

        _header_line, body = steps[step_num]

        explicit_labels = _explicit_labels_in_body(body)

        if not explicit_labels:
            # Body has no explicit lettered sub-markers → prose/implicit enumeration.
            # Prose/implicit enumeration is outside this check; substep-label-mismatch does not fire.
            continue

        if label in explicit_labels:
            # Label is explicitly present — clean.
            continue

        # Label absent from explicit enumeration → mechanical miss.
        label_display = f"({label})"
        findings.append({
            "line": ref_line,
            "detail": (
                f"Step {step_num}{label_display} referenced at line {ref_line}: "
                f"Step {step_num}'s body has explicit sub-labels "
                f"{sorted('(' + l + ')' for l in explicit_labels)} "
                f"but {label_display} is not among them"
            ),
        })

    return findings
