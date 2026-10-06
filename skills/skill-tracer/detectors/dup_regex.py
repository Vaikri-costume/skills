"""dup-regex — duplicate re.compile pattern across sibling scripts (reuse-drift class).

For the file under analysis:
  1. Collect all `re.compile("<pattern>", flags=...)` calls (at any scope: a
     duplicated literal is reuse drift whether it sits at module level or inside a function) where the
     pattern is a string literal with length > 15 (trivial patterns like r"\\d+" are
     below the bar). The flags argument (positional or `flags=` keyword) is captured
     alongside the pattern text.
  2. Read every SIBLING .py file in the same directory.
  3. For each long pattern found in the current file, scan each sibling for the same
     (pattern, flags) pair.
  4. Flag iff NEITHER file imports the other (mutual import = the duplication is intentional
     re-export, not drift).

Two distinct finding classes:
  - "exact-duplicate": the same pattern text AND the same flags appear in a sibling —
     a true behavior-identical duplicate.
  - "flag-divergence": the same pattern TEXT appears in a sibling but with DIFFERENT
     flags (e.g. one copy carries re.IGNORECASE, the other doesn't) — same-looking
     source, different runtime behavior. This is a distinct, likely-unintentional
     drift class from exact-duplicate and is reported separately so downstream
     consumers (and the fixer) can tell the two apart; it is NOT folded
     into the exact-duplicate finding.

Cross-file import check: a file A "imports" file B if any `import <name>` or
`from <name> import …` statement in A references B's stem name.  If either A→B or B→A
import exists, the pair is suppressed.

ABSTAIN conditions:
  - SyntaxError in the current file (cannot parse it at all).
  - Sibling parse errors are silently skipped (partial data only — current file still analysed).

Each finding carries a "token" field holding the pattern text itself, so the TOKEN-BLAST closure
check (cluster_prepass.py, fix_blast.py) greps the regex even when the pattern contains a backtick
that would break the backtick-quoted name in "detail".

Level: prepass — deterministic; a finding goes straight to the prepass fixer (it was one of the two
detectors with real hits in the October 2026 self-run).
"""
from __future__ import annotations

import ast
from pathlib import Path

CHECK_ID = "dup-regex"
LEVEL = "prepass"
FILE_GLOBS = ["*.py"]

_MIN_PATTERN_LEN = 16  # a pattern shorter than this is trivial (r"\d+"); length >= 16 means length > 15

FlagKey = tuple  # sorted tuple of flag-name strings (or fallback ast.dump() strings)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_safe(src: str, path: Path):
    """Return ast.Module or None on SyntaxError."""
    try:
        return ast.parse(src, filename=str(path))
    except SyntaxError:
        return None


def _flag_expr_names(node: ast.AST) -> list[str]:
    """Recursively decompose a flags expression into readable name fragments.

    Handles the common shapes:
      re.IGNORECASE                        -> ["IGNORECASE"]
      re.IGNORECASE | re.MULTILINE         -> ["IGNORECASE", "MULTILINE"]
      IGNORECASE (bare name, e.g. aliased) -> ["IGNORECASE"]
      0 / 2 (int literal)                  -> ["0"] / ["2"]

    Anything else (a variable, a call, an f-string, etc.) falls back to
    ast.dump() so two unresolvable flag expressions are still string-comparable
    rather than being silently treated as identical.
    """
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return _flag_expr_names(node.left) + _flag_expr_names(node.right)
    if isinstance(node, ast.Attribute):
        return [node.attr]
    if isinstance(node, ast.Name):
        return [node.id]
    if isinstance(node, ast.Constant):
        return [repr(node.value)]
    return [ast.dump(node)]


def _extract_flags(node: ast.Call) -> FlagKey:
    """Return a normalised, order-independent flags key for a re.compile() call.

    Looks at the second positional argument, then a `flags=` keyword argument.
    No flags argument at all normalises to an empty tuple (re's default, flags=0).
    """
    flags_node: ast.AST | None = None
    if len(node.args) > 1:
        flags_node = node.args[1]
    else:
        for kw in node.keywords:
            if kw.arg == "flags":
                flags_node = kw.value
                break
    if flags_node is None:
        return ()
    return tuple(sorted(_flag_expr_names(flags_node)))


def _format_flags(flags: FlagKey) -> str:
    return "no flags" if not flags else "|".join(flags)


def _collect_re_patterns(tree: ast.Module) -> list[tuple[str, int, FlagKey]]:
    """Return [(pattern_str, line_no, flags)] for every re.compile(literal) call (any scope)
    whose pattern is a string literal of at least _MIN_PATTERN_LEN characters.

    `flags` is a normalised, order-independent key derived from the flags argument
    (positional or `flags=` keyword); a call with no flags argument gets `()`.
    """
    results: list[tuple[str, int, FlagKey]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute)
                and func.attr == "compile"
                and isinstance(func.value, ast.Name)
                and func.value.id == "re"):
            continue
        if not node.args:
            continue
        first = node.args[0]
        if not (isinstance(first, ast.Constant) and isinstance(first.value, str)):
            continue
        pat = first.value
        if len(pat) >= _MIN_PATTERN_LEN:
            results.append((pat, node.lineno, _extract_flags(node)))
    return results


def _collect_imports(tree: ast.Module) -> set[str]:
    """Return the set of module stem names imported by this file.

    Covers:
      import foo              → "foo"
      import foo.bar          → "foo"
      from foo import ...     → "foo"
      from .foo import ...    → "foo"  (relative)
    """
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                # Take only the top-level stem (e.g. "os" from "os.path")
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module.split(".")[0])
            # relative imports: `from .foo import bar` — module may be None
    return names


def _mutual_import(stem_a: str, imports_a: set[str],
                   stem_b: str, imports_b: set[str]) -> bool:
    """True iff A imports B or B imports A."""
    return stem_b in imports_a or stem_a in imports_b


# ---------------------------------------------------------------------------
# Main detect
# ---------------------------------------------------------------------------

def detect(path: Path, src: str) -> list[dict]:
    # Parse the current file — abstain on SyntaxError.
    tree = _parse_safe(src, path)
    if tree is None:
        return [{"line": 0,
                 "detail": "abstain: syntax error — cannot parse file",
                 "abstain": True}]

    # Collect long re.compile patterns in this file (pattern, line, flags).
    patterns_here = _collect_re_patterns(tree)
    if not patterns_here:
        return []

    imports_here = _collect_imports(tree)
    stem_here = path.stem

    # Gather sibling .py files (same directory, excluding self).
    siblings = [p for p in path.parent.glob("*.py")
                if p != path and p.suffix == ".py"]

    # Build a cache per sibling: exact (pattern, flags) keys present, PLUS a
    # pattern-text -> set-of-flags-seen index (used for the flag-divergence check).
    sibling_data: list[tuple[Path, set[tuple[str, FlagKey]], dict[str, set[FlagKey]], set[str], str]] = []
    for sib in siblings:
        try:
            sib_src = sib.read_text(encoding="utf-8")
        except OSError:
            continue
        sib_tree = _parse_safe(sib_src, sib)
        if sib_tree is None:
            continue  # skip unparseable siblings
        sib_records = _collect_re_patterns(sib_tree)
        sib_exact_keys = {(p, f) for p, _, f in sib_records}
        sib_flags_by_text: dict[str, set[FlagKey]] = {}
        for p, _, f in sib_records:
            sib_flags_by_text.setdefault(p, set()).add(f)
        sib_imports = _collect_imports(sib_tree)
        sibling_data.append((sib, sib_exact_keys, sib_flags_by_text, sib_imports, sib.stem))

    # For each long pattern in this file, check for duplication in siblings —
    # exact (pattern, flags) match first, then same-text-different-flags.
    findings: list[dict] = []
    already_flagged_exact: set[tuple[str, FlagKey]] = set()
    already_flagged_drift: set[tuple[str, FlagKey]] = set()

    for pat, lineno, flags in patterns_here:
        key = (pat, flags)

        exact_sib: Path | None = None
        drift_sib: Path | None = None
        drift_other_flags: set[FlagKey] = set()

        for sib_path, sib_exact_keys, sib_flags_by_text, sib_imports, sib_stem in sibling_data:
            if _mutual_import(stem_here, imports_here, sib_stem, sib_imports):
                continue  # intentional re-export; not drift

            if key in sib_exact_keys:
                exact_sib = sib_path
                break  # exact match found — stop looking, report this class only

            if drift_sib is None:
                variants = sib_flags_by_text.get(pat)
                if variants and flags not in variants:
                    drift_sib = sib_path
                    drift_other_flags = variants

        if exact_sib is not None:
            if key in already_flagged_exact:
                continue
            already_flagged_exact.add(key)
            findings.append({
                "line": lineno,
                "detail": (
                    f"re.compile pattern `{pat}` also declared in {exact_sib.name} "
                    f"and neither script imports the other "
                    f"(reuse-drift — extract to a shared module)"
                ),
                "class": "exact-duplicate",
                "token": pat,
            })
            continue

        if drift_sib is not None and key not in already_flagged_drift:
            already_flagged_drift.add(key)
            other_desc = ", ".join(sorted(_format_flags(f) for f in drift_other_flags))
            findings.append({
                "line": lineno,
                "detail": (
                    f"[flag-divergence] re.compile pattern text `{pat}` also declared in {drift_sib.name} "
                    f"but with DIFFERENT flags ({_format_flags(flags)} here vs {other_desc} there) "
                    f"and neither script imports the other — same source text, different runtime "
                    f"behavior; likely-unintentional divergence, not a same-behavior duplicate"
                ),
                "class": "flag-divergence",
                "token": pat,
            })

    return findings
