#!/usr/bin/env python3
"""Dead-reference / broken-link detector for a CCVW skill.

Pure-stdlib (argparse + json + re + pathlib). Two checks over the skill tree:

  1. BROKEN LINKS (blocking) — every INTERNAL path cited in SKILL.md or any
     references/*.md (`references/<f>.md`, `scripts/<f>.py`, `assets/<...>`)
     must resolve to a file on disk. The skill's own polish pattern (move a
     section to references/foo.md, leave a pointer) can orphan a link; nothing
     else verifies the target exists. An unresolved citation is a real defect —
     the executor would try to load a missing file.

  2. DEAD SCRIPTS (advisory) — every scripts/*.py that NOTHING references
     (no doc citation, no Python import from a sibling script) is dead code
     shipped to users. Advisory, not blocking.

Cross-skill suppression: CCVW skills routinely cite a SIBLING skill's files
(e.g. skill-creator-ccvw's `references/portability-spec.md`, skill-tracer's
`scripts/stage_cold_prompts.py`) — written either as the install-absolute form
`~/.claude/skills/<other>/references/foo.md` or as a bare relative path in prose
that names the other skill. Those are NOT this skill's broken links. A citation
is skipped when its surrounding PARAGRAPH (text block between blank lines) names
another skill — any `skill-<name>` token that is not this skill's own folder
name. Limitation (accepted): a genuinely orphaned internal link that happens to
sit in a paragraph also mentioning a sibling skill is a false negative; the
target case (a stale pointer in a self-only paragraph) is still caught.

Usage:
    python3 link_check.py <skill-path> [--json]
    --json: emit JSON (default: human-readable report)

Exit: 0 = clean (all links resolve, no dead scripts, all files readable);
      1 = findings — broken links and/or dead scripts and/or unreadable files;
      2 = usage/path error (SKILL.md not found).
Exit 1 intentionally covers all three finding kinds with one code: callers
discriminate by the `broken_links` / `dead_scripts` / `unreadable` arrays in
`--json` (a broken link is a hard ship-blocker; a dead script is advisory; an
unreadable file means the scan is incomplete). The exit code is the run-level
signal; the JSON is the per-kind detail.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Cited internal paths. Each captures the repo-relative suffix, so the
# install-absolute form (.../skills/<skill>/scripts/foo.py) matches too.
_CITATION_RE = re.compile(
    r"(?:references/[\w.\-]+\.md"
    r"|scripts/[\w.\-]+\.py"
    r"|assets/[\w.\-/]+)"
)
# Trailing punctuation that regularly abuts a cited path in prose/markdown
# (close-paren, backtick, comma, etc.) — stripped before the on-disk check.
_TRAILING = "`)],.;:\"'"

# A `skill-<name>` token — used to detect when a paragraph references a SIBLING
# skill (any such token whose value isn't this skill's own folder name).
_SKILL_TOKEN_RE = re.compile(r"skill-[a-z0-9-]+")
# An install-absolute path naming a skill, ending just before a cited suffix:
# `…/skills/<skill-name>/`. Used to classify an absolute citation by the skill it
# names directly (precise), instead of relying on the surrounding paragraph.
_ABS_SKILL_RE = re.compile(r"(?:^|/)skills/(skill-[a-z0-9.\-]+)/$")


def _paragraphs(text: str) -> list[str]:
    """Split into text blocks delimited by blank lines (markdown paragraphs)."""
    return re.split(r"\n[ \t]*\n", text)


def _is_cross_skill(paragraph: str, self_name: str) -> bool:
    """True if the paragraph names a SIBLING skill — a `skill-<name>` token that is
    neither this skill's own folder name NOR one of its own sub-paths
    (`skill-publisher-tests`, `skill-publisher-ledger`, which start with
    `<self_name>-`). Exact-equality on the self name (not a bare prefix test) so a
    genuinely distinct sibling whose name merely shares a prefix is still caught."""
    for tok in _SKILL_TOKEN_RE.findall(paragraph):
        if tok != self_name and not tok.startswith(self_name + "-"):
            return True
    return False


def _docs(skill_root: Path) -> list[Path]:
    """SKILL.md + every references/*.md — the files that cite internal paths."""
    docs = []
    sm = skill_root / "SKILL.md"
    if sm.is_file():
        docs.append(sm)
    ref_dir = skill_root / "references"
    if ref_dir.is_dir():
        docs.extend(sorted(ref_dir.glob("*.md")))
    return docs


def _read_cache(paths: list[Path]) -> tuple[dict, list[str]]:
    """Read each path ONCE. Returns ({path: text}, unreadable_rel_or_abs_names).
    An OSError is recorded (not silently swallowed) so the caller can report an
    unreadable file rather than mistaking it for 'no citations / clean'."""
    cache: dict = {}
    unreadable: list[str] = []
    for p in paths:
        try:
            cache[p] = p.read_text(encoding="utf-8")
        except OSError as e:
            unreadable.append(f"{p}: {e}")
    return cache, unreadable


def _mentions(text: str, fname: str, stem: str) -> bool:
    """Whether `text` references the script — as a path citation (`scripts/foo.py`
    or a bare `foo.py` at a token boundary) or a Python import (`import foo` /
    `from foo`). Boundary-anchored so `check.py` does NOT match inside
    `double-check.py`, and `foo.py` does NOT match inside `foo.pyc`."""
    if re.search(rf"(?<![\w.\-]){re.escape(fname)}(?![\w])", text):
        return True
    if re.search(rf"\b(?:import|from)\s+{re.escape(stem)}\b", text):
        return True
    return False


def find_broken_links(skill_root: Path, doc_cache: dict) -> list[dict]:
    """Cited INTERNAL paths that do not resolve on disk. An absolute citation
    `…/skills/<x>/…` is classified by `<x>` directly (cross-skill iff x != self);
    a bare-relative citation falls back to the paragraph cross-skill heuristic."""
    self_name = skill_root.name
    broken = []
    seen = set()  # dedupe (source, cited) pairs
    for doc in _docs(skill_root):
        text = doc_cache.get(doc)
        if text is None:  # unreadable — recorded separately, skip citation scan
            continue
        src = doc.relative_to(skill_root).as_posix()
        for para in _paragraphs(text):
            para_cross = _is_cross_skill(para, self_name)
            for m in _CITATION_RE.finditer(para):
                cited = m.group(0).rstrip(_TRAILING)
                # Precise absolute-path classification: is the match the suffix of
                # a `…/skills/<x>/…` path? If so, <x> decides internal vs cross-skill.
                am = _ABS_SKILL_RE.search(para[:m.start()])
                if am:
                    if am.group(1) != self_name:
                        continue  # absolute path into another skill's tree
                    # else: absolute path into THIS skill — check resolution below
                elif para_cross:
                    continue  # bare-relative citation in a sibling-naming paragraph
                # A `..` segment can resolve outside the cited dir (a stale
                # `assets/../references/x.md` would spuriously "exist") — never let
                # path traversal validate a citation.
                traversal = ".." in cited.split("/")
                if (not traversal) and (skill_root / cited).exists():
                    continue
                key = (src, cited)
                if key in seen:
                    continue
                seen.add(key)
                broken.append({"source": src, "cited": cited})
    return broken


def find_dead_scripts(skill_root: Path, doc_cache: dict,
                      script_cache: dict) -> list[str]:
    """scripts/*.py that nothing cites (doc) or imports (sibling script). Reads
    come from the pre-built caches (no per-script re-reads)."""
    scripts_dir = skill_root / "scripts"
    if not scripts_dir.is_dir():
        return []
    scripts = sorted(p for p in script_cache if p.parent == scripts_dir
                     and p.name != "__init__.py")
    docs_text = "\n".join(t for t in doc_cache.values())

    dead = []
    for script in scripts:
        stem = script.stem
        fname = script.name
        if _mentions(docs_text, fname, stem):
            continue
        # A script referenced/imported by any OTHER script is not dead.
        if any(_mentions(script_cache[p], fname, stem)
               for p in scripts if p != script):
            continue
        dead.append(fname)
    return dead


def main() -> int:
    ap = argparse.ArgumentParser(description="Dead-reference / broken-link detector")
    ap.add_argument("skill_path", help="skill directory or path to SKILL.md")
    ap.add_argument("--json", dest="json_out", action="store_true",
                    help="emit JSON instead of human-readable report")
    args = ap.parse_args()

    p = Path(args.skill_path).expanduser()
    skill_root = p.parent if p.name == "SKILL.md" else p
    if not (skill_root / "SKILL.md").is_file():
        print(f"ERROR: SKILL.md not found at {skill_root / 'SKILL.md'}", file=sys.stderr)
        return 2

    # Read every doc + script ONCE; unreadable files are recorded, not swallowed.
    docs = _docs(skill_root)
    scripts_dir = skill_root / "scripts"
    script_paths = (sorted(p for p in scripts_dir.glob("*.py") if p.name != "__init__.py")
                    if scripts_dir.is_dir() else [])
    doc_cache, doc_unreadable = _read_cache(docs)
    script_cache, script_unreadable = _read_cache(script_paths)
    unreadable = doc_unreadable + script_unreadable

    broken = find_broken_links(skill_root, doc_cache)
    dead = find_dead_scripts(skill_root, doc_cache, script_cache)
    # An unreadable file is a real finding: the scan over it is incomplete, so a
    # clean result would be a false negative.
    has_findings = bool(broken or dead or unreadable)

    if args.json_out:
        print(json.dumps({
            "skill": str(skill_root),
            "broken_links": broken,
            "dead_scripts": dead,
            "unreadable": unreadable,
            "clean": not has_findings,
        }, indent=2))
    else:
        if not has_findings:
            print(f"link_check: {skill_root.name} — clean (all links resolve, no dead scripts)")
        else:
            print(f"link_check: {skill_root.name}")
            if broken:
                print(f"  BROKEN LINKS ({len(broken)}) — cited path does not resolve:")
                for b in broken:
                    print(f"    ✗ {b['source']} → {b['cited']}")
            if dead:
                print(f"  DEAD SCRIPTS ({len(dead)}) — nothing references these (advisory):")
                for d in dead:
                    print(f"    · scripts/{d}")
            if unreadable:
                print(f"  UNREADABLE ({len(unreadable)}) — scan incomplete over these files:")
                for u in unreadable:
                    print(f"    ! {u}")

    return 1 if has_findings else 0


if __name__ == "__main__":
    sys.exit(main())
