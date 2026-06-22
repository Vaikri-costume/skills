#!/usr/bin/env python3
"""CCVW attribution lint — static scan of a skill against the attribution-spec.

INDEPENDENT COPY — skill-publisher's own copy of a script skill-creator-ccvw also
has, so the publisher runs standalone (without skill-creator-ccvw installed). The
sync contract is RETIRED (2026-06-20): the two copies are no longer kept in sync
and may freely diverge — edit this one for skill-publisher's needs without touching
the other. (check_shared_sync.py remains only as a dormant manual drift-inspection
tool; it is not run anywhere and nothing requires the copies to match.)

Sibling to portability_lint.py:
- portability_lint: tier portability (paths, Claude extensions, mandatory fields) — reads SKILL.md
- attribution_lint: lineage credit (history chain, inspirations, LICENSE file) — reads HISTORY.md

A skill can be portable but missing attribution, or correctly attributed but
tier-violating. These are independent.

Reads <skill>/HISTORY.md YAML frontmatter (where attribution lives as of the
three-skill ecosystem refactor — it used to be in SKILL.md's `metadata`). Checks
the four attribution categories (A: fork, B: derivative, C: inspiration, D:
independent) for the category-specific required fields. The see-also advisory
check reads SKILL.md's body (the References section lives there).

In HISTORY.md frontmatter the attribution fields are TOP-LEVEL (not nested under
`metadata`): `version`, `category`, `parent-version`, `author` (with `.primary`
and `.history[]`), `inspirations[]`.

Usage:
    python3 attribution_lint.py <skill-path>

The category is read from the explicit `category` field in HISTORY.md if present;
otherwise inferred from shape (history present → A; only inspirations → B; none → D).

Frontmatter parsing: tries PyYAML first (handles arbitrary nesting reliably),
falls back to a bespoke indent-aware parser for environments without yaml
installed. Both produce the same dict shape.
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

try:
    import yaml
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False


REQUIRED_AUTHOR_FIELDS = ["primary"]
REQUIRED_HISTORY_ENTRY_FIELDS = ["role", "name"]
REQUIRED_HISTORY_FIRST_ENTRY_FIELDS = ["role", "name", "skill", "license"]
REQUIRED_INSPIRATION_FIELDS = ["skill", "by", "pattern"]
VALID_HISTORY_ROLES = {"original", "fork-adapter", "heavy-revision"}


def _strip_quotes(s):
    s = s.strip()
    if len(s) >= 2 and ((s[0] == '"' and s[-1] == '"') or (s[0] == "'" and s[-1] == "'")):
        return s[1:-1]
    return s


def _parse_scalar(val):
    """Parse a YAML scalar value (string, int, float, bool, null, JSON)."""
    val = _strip_quotes(val)
    if val == "" or val.lower() == "null":
        return None
    if val.lower() == "true":
        return True
    if val.lower() == "false":
        return False
    if val.startswith("{") and val.endswith("}"):
        try:
            return json.loads(val)
        except json.JSONDecodeError:
            return val
    if val.startswith("[") and val.endswith("]"):
        try:
            return json.loads(val)
        except json.JSONDecodeError:
            return val
    try:
        if "." in val:
            return float(val)
        return int(val)
    except ValueError:
        return val


def _indent_of(line):
    return len(line) - len(line.lstrip(" "))


def _bespoke_parse(raw):
    """Indent-aware YAML-subset parser. Handles arbitrary nesting of dicts and
    arrays-of-dicts, scalar lists (single-line `- value`), and standard scalars.
    Sufficient for CCVW skill frontmatter."""

    lines = [ln for ln in raw.split("\n") if ln.strip()]

    def parse_block(idx, base_indent):
        """Parse a block starting at lines[idx]; returns (value, next_idx)."""
        if idx >= len(lines):
            return None, idx

        first = lines[idx]
        first_indent = _indent_of(first)
        stripped = first.lstrip(" ")

        # List? Block starts with `- `
        if stripped.startswith("- "):
            items = []
            while idx < len(lines):
                ln = lines[idx]
                ln_indent = _indent_of(ln)
                if ln_indent < first_indent:
                    break
                if ln_indent != first_indent or not ln.lstrip(" ").startswith("- "):
                    break
                # List item — body after "- " is either a scalar or the start of a dict
                body_raw = ln.lstrip(" ")[2:]
                m = re.match(r"^([a-zA-Z][a-zA-Z0-9_-]*)\s*:\s*(.*)$", body_raw)
                if m:
                    # Dict entry — collect this kv + any indented continuations
                    key, val = m.group(1), m.group(2)
                    entry = {}
                    if val.strip() == "":
                        # Nested dict for this list-entry-key
                        sub, idx2 = parse_block(idx + 1, first_indent + 4)
                        entry[key] = sub
                        idx = idx2
                    else:
                        entry[key] = _parse_scalar(val)
                        idx += 1
                    # Continuation lines at first_indent + 2 are more keys of this entry
                    while idx < len(lines) and _indent_of(lines[idx]) > first_indent:
                        cont = lines[idx].lstrip(" ")
                        cont_indent = _indent_of(lines[idx])
                        if cont.startswith("- "):
                            break
                        m2 = re.match(r"^([a-zA-Z][a-zA-Z0-9_-]*)\s*:\s*(.*)$", cont)
                        if not m2:
                            break
                        ck, cv = m2.group(1), m2.group(2)
                        if cv.strip() == "":
                            sub, idx2 = parse_block(idx + 1, cont_indent + 2)
                            entry[ck] = sub
                            idx = idx2
                        else:
                            entry[ck] = _parse_scalar(cv)
                            idx += 1
                    items.append(entry)
                else:
                    items.append(_parse_scalar(body_raw))
                    idx += 1
            return items, idx

        # Dict otherwise
        result = {}
        while idx < len(lines):
            ln = lines[idx]
            ln_indent = _indent_of(ln)
            if ln_indent < first_indent:
                break
            if ln_indent > first_indent:
                # Shouldn't happen here — should have been consumed below
                idx += 1
                continue
            m = re.match(r"^([a-zA-Z][a-zA-Z0-9_-]*)\s*:\s*(.*)$", ln.lstrip(" "))
            if not m:
                idx += 1
                continue
            key, val = m.group(1), m.group(2)
            if val.strip() == "":
                # Lookahead: next non-empty line is either deeper (nested dict/list) or same/less (empty value)
                if idx + 1 < len(lines) and _indent_of(lines[idx + 1]) > ln_indent:
                    sub, idx2 = parse_block(idx + 1, _indent_of(lines[idx + 1]))
                    result[key] = sub
                    idx = idx2
                else:
                    result[key] = None
                    idx += 1
            else:
                result[key] = _parse_scalar(val)
                idx += 1
        return result, idx

    parsed, _ = parse_block(0, _indent_of(lines[0]) if lines else 0)
    return parsed if isinstance(parsed, dict) else {}


def parse_frontmatter(text):
    """YAML frontmatter parser. Tries PyYAML first; falls back to bespoke
    indent-aware parser. Returns (frontmatter_dict, body_text).
    """
    if not text.startswith("---\n"):
        return {}, text

    end = text.find("\n---\n", 4)
    if end < 0:
        return {}, text

    raw = text[4:end]
    body = text[end + 5:]

    if _HAS_YAML:
        try:
            fm = yaml.safe_load(raw) or {}
            if not isinstance(fm, dict):
                fm = {}
            return fm, body
        except yaml.YAMLError:
            pass  # Fall through to bespoke

    return _bespoke_parse(raw), body


def infer_category(fm):
    """Infer attribution category from HISTORY.md frontmatter shape.

    Prefers the explicit top-level `category` field if present and valid.
    Falls back to shape inference (history → A; inspirations → B; none → D).

    Returns one of: 'A', 'B', 'C', 'D', 'unknown'.
    """
    explicit = fm.get("category")
    if isinstance(explicit, str) and explicit.strip().upper() in {"A", "B", "C", "D"}:
        return explicit.strip().upper()

    author = fm.get("author", {})
    if not isinstance(author, dict):
        return "unknown"

    history = author.get("history", [])
    inspirations = fm.get("inspirations", [])

    has_history = isinstance(history, list) and len(history) > 0
    has_inspirations = isinstance(inspirations, list) and len(inspirations) > 0

    if has_history:
        return "A"
    if has_inspirations:
        return "B"
    # Category C (see-also references in body) cannot be detected from
    # frontmatter alone; lint reports D and notes that any C-category
    # see-also references must be checked in SKILL.md's References section.
    return "D"


def lint_author(fm):
    """Check that author.primary is present (top-level in HISTORY.md frontmatter)."""
    violations = []
    author = fm.get("author", {})
    if not isinstance(author, dict):
        violations.append({
            "type": "author-not-dict",
            "message": "HISTORY.md `author` field is not a parseable object",
            "severity": "blocking",
        })
        return violations, "missing"

    primary = author.get("primary")
    if not primary or not isinstance(primary, str):
        violations.append({
            "type": "missing-primary-author",
            "message": "HISTORY.md `author.primary` is required and must be a string",
            "severity": "blocking",
        })
        return violations, "missing"

    return violations, primary


def lint_history(fm):
    """Check that author.history entries are well-formed if present."""
    violations = []
    author = fm.get("author", {})
    if not isinstance(author, dict):
        return violations, []

    history = author.get("history", [])
    if not isinstance(history, list):
        violations.append({
            "type": "history-not-list",
            "message": "HISTORY.md `author.history` must be a list of entries",
            "severity": "blocking",
        })
        return violations, []

    for idx, entry in enumerate(history):
        if not isinstance(entry, dict):
            violations.append({
                "type": "history-entry-not-dict",
                "message": f"author.history[{idx}] is not a parseable object",
                "severity": "blocking",
            })
            continue

        required = REQUIRED_HISTORY_FIRST_ENTRY_FIELDS if idx == 0 else REQUIRED_HISTORY_ENTRY_FIELDS
        for field in required:
            if field not in entry or not entry[field]:
                violations.append({
                    "type": "history-entry-missing-field",
                    "message": f"author.history[{idx}] is missing required field `{field}`",
                    "severity": "blocking",
                })

        role = entry.get("role", "")
        if role and role not in VALID_HISTORY_ROLES:
            violations.append({
                "type": "history-entry-invalid-role",
                "message": f"author.history[{idx}].role is `{role}`; must be one of {sorted(VALID_HISTORY_ROLES)}",
                "severity": "blocking",
            })

        # First entry must be role=original
        if idx == 0 and role and role != "original":
            violations.append({
                "type": "history-first-not-original",
                "message": f"author.history[0].role must be `original`; got `{role}`",
                "severity": "blocking",
            })

    return violations, history


def lint_inspirations(fm):
    """Check that inspirations entries are well-formed if present (top-level in HISTORY.md)."""
    violations = []
    inspirations = fm.get("inspirations", [])
    if inspirations is None:
        return violations, []
    if not isinstance(inspirations, list):
        violations.append({
            "type": "inspirations-not-list",
            "message": "HISTORY.md `inspirations` must be a list of entries",
            "severity": "blocking",
        })
        return violations, []

    for idx, entry in enumerate(inspirations):
        if not isinstance(entry, dict):
            violations.append({
                "type": "inspiration-entry-not-dict",
                "message": f"inspirations[{idx}] is not a parseable object",
                "severity": "blocking",
            })
            continue

        for field in REQUIRED_INSPIRATION_FIELDS:
            if field not in entry or not entry[field]:
                violations.append({
                    "type": "inspiration-incomplete",
                    "message": f"inspirations[{idx}] is missing required field `{field}`",
                    "severity": "blocking",
                })

    return violations, inspirations


def lint_license_file(skill_path, history):
    """If history declares an `original` entry, LICENSE file must be present at skill root."""
    violations = []
    if not history:
        return violations, False

    license_path = Path(skill_path) / "LICENSE"
    license_txt_path = Path(skill_path) / "LICENSE.txt"
    license_md_path = Path(skill_path) / "LICENSE.md"
    license_present = license_path.exists() or license_txt_path.exists() or license_md_path.exists()

    if not license_present:
        violations.append({
            "type": "missing-license-file",
            "message": "HISTORY.md author.history declares an original entry but LICENSE file is absent at skill root. Required for Category A (direct fork) per the attribution spec.",
            "severity": "blocking",
        })

    return violations, license_present


def lint_see_also_advisory(skill_path, body, category):
    """Advisory check: if the skill body mentions known CCVW pattern names but
    has no see-also references in a References section, flag advisory.

    This is a best-effort textual check — it can't reliably detect all pattern
    adoptions, but it catches obvious cases of recognizable pattern use without
    corresponding attribution.
    """
    violations = []
    if category in ("A", "B"):
        # A/B already cover attribution explicitly; advisory not needed
        return violations

    # Heuristic: look for recognizable CCVW skill names mentioned in the body
    # without a corresponding `## References` or `## See also` section entry.
    recognizable_skill_names = [
        "deep-research",
        "ralph-loop",
        "pr-review-toolkit",
        "skill-tracer",
        "claude-md-improver",
        "marketplace-discover",
        "skill-creator-ccvw",
    ]

    body_lower = body.lower()
    _ref_idx = body_lower.find("## references")
    _see_idx = body_lower.find("## see also")
    # Use the EARLIER section so both ## References and ## See also content is searched.
    # max() would select the later section, causing false advisories when ## References
    # appears before ## See also and the skill name is only in the earlier block.
    if _ref_idx >= 0 and _see_idx >= 0:
        references_section_idx = min(_ref_idx, _see_idx)
    elif _ref_idx >= 0:
        references_section_idx = _ref_idx
    elif _see_idx >= 0:
        references_section_idx = _see_idx
    else:
        references_section_idx = -1
    references_section = body[references_section_idx:] if references_section_idx >= 0 else ""

    # Determine the current skill's own name from its directory; exclude
    # self-references from the see-also check (a skill mentioning itself is
    # not pattern-borrowing).
    own_skill_name = Path(skill_path).name.lower()

    for skill_name in recognizable_skill_names:
        if skill_name == own_skill_name:
            continue  # skill mentioning itself is not pattern attribution
        if skill_name in body_lower and skill_name not in references_section.lower():
            violations.append({
                "type": "see-also-without-reference",
                "message": f"Skill body mentions recognizable CCVW skill `{skill_name}` without a see-also reference in the References section. If you adopted a pattern from `{skill_name}`, add a see-also reference (Category C) or an inspirations entry in frontmatter (Category B).",
                "severity": "advisory",
            })

    return violations


def main():
    parser = argparse.ArgumentParser(description="CCVW attribution lint")
    parser.add_argument("skill_path", help="Path to skill directory")
    args = parser.parse_args()

    skill_path = Path(args.skill_path).expanduser()

    # Attribution lives in HISTORY.md as of the three-skill ecosystem refactor.
    history_md = skill_path / "HISTORY.md"
    if not history_md.is_file():
        print(json.dumps({
            "error": f"HISTORY.md not found at {history_md}",
            "note": "Attribution moved from SKILL.md frontmatter to HISTORY.md. Run skill-creator-ccvw to scaffold HISTORY.md, or skill-publisher to backfill it.",
        }, indent=2))
        sys.exit(1)

    hist_fm, _ = parse_frontmatter(history_md.read_text(encoding="utf-8"))

    # The see-also advisory check reads SKILL.md's body (References section is there).
    skill_md = skill_path / "SKILL.md"
    skill_body = ""
    if skill_md.is_file():
        _, skill_body = parse_frontmatter(skill_md.read_text(encoding="utf-8"))

    category = infer_category(hist_fm)
    author_violations, primary_author = lint_author(hist_fm)
    history_violations, history = lint_history(hist_fm)
    inspirations_violations, inspirations = lint_inspirations(hist_fm)
    license_violations, license_present = lint_license_file(skill_path, history)
    advisory_violations = lint_see_also_advisory(skill_path, skill_body, category)

    all_violations = (
        author_violations
        + history_violations
        + inspirations_violations
        + license_violations
        + advisory_violations
    )

    blocking_violations = [v for v in all_violations if v.get("severity") == "blocking"]

    result = {
        "skill_path": str(skill_path),
        "declared_category": category,
        "primary_author": primary_author,
        "history_chain_length": len(history),
        "inspirations_count": len(inspirations),
        "license_file_present": license_present,
        "violations": all_violations,
        "would_fail_attribution_check": len(blocking_violations) > 0,
    }

    print(json.dumps(result, indent=2))
    sys.exit(1 if blocking_violations else 0)


if __name__ == "__main__":
    main()
