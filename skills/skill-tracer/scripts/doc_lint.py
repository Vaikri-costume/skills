#!/usr/bin/env python3
"""doc_lint.py — small, fixed, advisory doc lint run after a Code Review fixer.

Twelve checks, each reporting only a concrete mismatch (never one line per field or key):
  section-ref   a `<file>.md "<Section>"` reference names a heading or bold label that file has.
  ordinal-ref   "item|rule|case|criterion|rung N" in a .md file points at a numbered list with an
                item N (in the same file, or in the .md file named just before it).
  list-count    a line ending "<N> <words>:" is followed by a list of exactly N items.
  exit-codes    each references/script-contract.md row names only exit codes its script can
                return, and each literal non-zero code a script returns appears in its rows.
  usage-flags   every --flag in a script's docstring Usage block is defined by its argparse.
  glossary      detectors/missing_glossary_entry.py (the advisory glossary lint): a recurring
                backticked term or a bolded concept label with no glossary row, or an orphan row.
  retired-term  a term the target skill retired (RETIRED_TERMS, keyed by the SKILL.md `name:`) is
                still mentioned outside tests/ and outside lines that say they are legacy compatibility.
  doc-count     a docstring line that states a count ("Five checks ...:") is followed by a list of
                exactly that many items.
  dollar-var    a `$NAME` used in .md prose is defined in SKILL.md or an in-scope script (or is a
                standard environment variable).
  fix-narration a .py comment or docstring narrates a past fix event (a fix "applied", a cluster id
                followed by "fix", a fix "in round N") instead of stating what the code does.
  raises-no-raise  a function docstring says "Raises <X>" but the function body has no raise.
  unused-param  a function parameter is never read in its body (self, cls, names starting with "_"
                and functions whose body only passes or raises are skipped).
The last three read only .py files outside tests/ (usage-flags, exit-codes, doc-count and
retired-term also read scripts).

Usage:
    doc_lint.py --target <skill-dir> [--checks section-ref,ordinal-ref,...]

Prints {"findings": [{"check", "file", "line", "detail"}], "count": N}. Exit 0 whatever it finds (the
orchestrator decides which findings are real); 2 = --target is not a directory or a check is unknown.
"""
from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import re
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
from inscope import inscope_files  # noqa: E402

CHECKS = ("section-ref", "ordinal-ref", "list-count", "exit-codes", "usage-flags", "glossary",
          "retired-term", "doc-count", "dollar-var", "fix-narration", "raises-no-raise", "unused-param")
# Terms a skill retired, keyed by its SKILL.md `name:`. A hit is a leftover mention, unless the line or
# one of the 3 lines above it says "legacy" (the code that still reads old ledgers says so).
RETIRED_TERMS = {
    "skill-tracer": ("silent-fallback-handler", "column-header-mismatch", "minor-bugs", "minor bugs",
                     "minorbugs", "hunter", "doc_sync_check", "cr-mode", "verify-only", "one-round",
                     "specialist", "F/E/L/I/D"),
}
_STD_ENV = {"HOME", "XDG_DATA_HOME", "XDG_CONFIG_HOME", "PATH", "USER", "TMPDIR", "PWD", "SHELL"}
_DOLLAR_RE = re.compile(r"\$\{?([A-Z][A-Z0-9_]{2,})\b")
_DOC_COUNT_RE = re.compile(r"^\s*(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+[a-z][\w-]*\b.*:\s*$", re.IGNORECASE)
_NUM = {w: i for i, w in enumerate("zero one two three four five six seven eight nine ten".split())}
_SECTION_RE = re.compile(r"`?((?:[\w-]+/)*[\w.-]+\.md)`?,? \"([^\"\n]{3,80})\"")
_ORDINAL_RE = re.compile(r"\b(?:item|rule|case|criterion|rung)\s+(\d+)\b", re.IGNORECASE)
_COUNT_RE = re.compile(r"\b(\d+|two|three|four|five|six|seven|eight|nine|ten)\s+(?:[\w-]+\s+){0,3}?[\w-]+\)?:\s*$", re.IGNORECASE)
_ITEM_RE = re.compile(r"^(\s*)(?:[-*+]|\d+[.)])\s+\S")
_FLAG_RE = re.compile(r"(?<![\w-])(--[a-z][a-z0-9-]+)")
# Fix-event narration: a fix said to be applied, a cluster id followed by the word fix, or a fix
# dated by round number (the fix-narration check).
_NARRATION_RE = re.compile(r"\bfix(?:es)?\s+(?:was\s+|were\s+)?applied\b|\b[CG]\d+\s+fix\b"
                           r"|\bfixed\s+in\s+round\s+\d+|\bround[- ]\d+\s+fix\b", re.IGNORECASE)
_RAISES_RE = re.compile(r"\bRaises\b:?\s*`?([A-Z]\w*)?")


def _norm(t: str) -> str:
    return re.sub(r"[\s`*_—–-]+", " ", t).strip().lower()


def _unfenced(text: str):
    fence = False
    for i, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith(("```", "~~~")):
            fence = not fence
        elif not fence:
            yield i, line


def _labels(text: str) -> set:
    heads = {_norm(m.group(1)) for m in re.finditer(r"^#{1,6}\s+(.+?)\s*$", text, re.M)}
    return heads | {_norm(m.group(1).rstrip(".:")) for m in re.finditer(r"\*\*([^*\n]+)\*\*", text)}


def _find(root: Path, name: str) -> Path | None:
    for cand in (root / name, root / "references" / name):
        if cand.is_file():
            return cand
    hits = [p for p in root.rglob(Path(name).name) if p.is_file()]
    return hits[0] if len(hits) == 1 else None


def check_md(root: Path, md: Path, text: str, out: list) -> None:
    rel, lines = md.relative_to(root).as_posix(), text.splitlines()
    numbered = lambda t: {int(m.group(1)) for m in re.finditer(r"^\s*(\d+)[.)]\s", t, re.M)}  # noqa: E731
    for n, line in _unfenced(text):
        for m in _SECTION_RE.finditer(line):
            ref = _find(root, m.group(1))
            if ref is not None and not any(_norm(m.group(2)) in lab for lab in _labels(ref.read_text(encoding="utf-8"))):
                out.append(("section-ref", rel, n, f"{m.group(1)} has no heading or bold label \"{m.group(2)}\""))
        for m in _ORDINAL_RE.finditer(line):
            named = re.findall(r"([\w.-]+\.md)", line[max(0, m.start() - 80):m.start()])
            ref = _find(root, named[-1]) if named else md
            if ref is not None and int(m.group(1)) not in numbered(ref.read_text(encoding="utf-8")):
                out.append(("ordinal-ref", rel, n, f"\"{m.group(0)}\": {ref.name} has no numbered item {m.group(1)}"))
        m = _COUNT_RE.search(line)
        if m and n < len(lines) and _ITEM_RE.match(lines[n]):
            want = int(m.group(1)) if m.group(1).isdigit() else _NUM[m.group(1).lower()]
            indent, got = len(_ITEM_RE.match(lines[n]).group(1)), 0
            for nxt in lines[n:]:
                im = _ITEM_RE.match(nxt)
                if im and len(im.group(1)) == indent:
                    got += 1
                elif not nxt.strip() or (im is None and not nxt.startswith(" " * (indent + 1))):
                    break
            if got != want:
                out.append(("list-count", rel, n, f"\"{m.group(0).strip()}\" introduces {got} list item(s)"))


def _returned_codes(tree: ast.AST) -> set:
    codes = set()
    for node in ast.walk(tree):
        vals = []
        if isinstance(node, ast.Return) and node.value is not None:
            vals = [node.value]
        elif isinstance(node, ast.Call) and getattr(node.func, "attr", getattr(node.func, "id", "")) == "exit" and node.args:
            vals = [node.args[0]]
        for v in vals:
            for e in ([v.body, v.orelse] if isinstance(v, ast.IfExp) else [v]):
                if isinstance(e, ast.Constant) and type(e.value) is int and 0 <= e.value <= 9:
                    codes.add(e.value)
    return codes


def check_scripts(root: Path, out: list) -> None:
    trees, defined_by = {}, {}
    for py in (p for p in inscope_files(root) if p.suffix == ".py"):
        try:
            trees[py.name] = (py, ast.parse(py.read_text(encoding="utf-8")))
        except SyntaxError:
            continue
    for name, (py, tree) in trees.items():
        check_doc_counts(root, py, tree, out)
        if not py.relative_to(root).as_posix().startswith("tests/"):
            check_code_hygiene(root, py, tree, out)
        defined = {a.value for n in ast.walk(tree) if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "add_argument"
                   for a in n.args if isinstance(a, ast.Constant) and str(a.value).startswith("--")}
        defined_by[name] = defined
        doc, block, skip = ast.get_docstring(tree) or "", False, False
        if not defined:
            continue
        for line in doc.splitlines():
            if line.strip().startswith("Usage:"):
                block = True
                continue
            if block and line.strip() and not line.startswith(" "):
                block = False
            if not block:
                continue
            others = [s for s in re.findall(r"[\w-]+\.py", line) if s != name]
            skip = bool(others) or (skip and not re.search(re.escape(name), line) and not line.strip().startswith("--"))
            for flag in [] if skip else _FLAG_RE.findall(line):
                if flag not in defined:
                    out.append(("usage-flags", py.relative_to(root).as_posix(), 1, f"docstring Usage names {flag}, which argparse does not define"))
    contract = root / "references" / "script-contract.md"
    if not contract.is_file():
        return
    # argparse itself exits 2 on a usage error, so a script with arguments can always exit 2.
    codes_of = lambda nm: _returned_codes(trees[nm][1]) | ({2} if defined_by.get(nm) else set())  # noqa: E731
    documented: dict = {}
    for n, line in enumerate(contract.read_text(encoding="utf-8").splitlines(), 1):
        cells = [c.strip() for c in line.split("|")]
        m = re.match(r"`([\w-]+\.py)", cells[1]) if len(cells) > 3 else None
        if m and m.group(1) in trees:
            codes = {int(c) for c in re.findall(r"(?<![\w.-])([0-9])\s*=", cells[2])}
            documented.setdefault(m.group(1), set()).update(codes)
            extra = codes - codes_of(m.group(1))
            if extra:
                out.append(("exit-codes", "references/script-contract.md", n, f"{m.group(1)}: documented exit code(s) {sorted(extra)} never returned"))
    for name, codes in documented.items():
        missing = codes_of(name) - codes - {0}
        if missing:
            out.append(("exit-codes", "references/script-contract.md", 1, f"{name} returns {sorted(missing)}, which no row documents"))


def check_glossary(root: Path, out: list) -> None:
    det = Path(__file__).resolve().parent.parent / "detectors" / "missing_glossary_entry.py"
    spec = importlib.util.spec_from_file_location(det.stem, det)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    allowed = set(inscope_files(root))
    files = sorted({f for g in mod.FILE_GLOBS for f in root.glob(g) if f.resolve() in allowed})
    for f in files:
        for fd in mod.detect(f, f.read_text(encoding="utf-8")) or []:
            if not fd.get("abstain"):
                out.append(("glossary", f.relative_to(root).as_posix(), fd.get("line") or 0, fd.get("detail", "")))


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip())


def check_retired(root: Path, files: list, out: list) -> None:
    m = re.search(r"^name:\s*['\"]?([\w-]+)", (root / "SKILL.md").read_text(encoding="utf-8"), re.M) \
        if (root / "SKILL.md").is_file() else None
    terms = RETIRED_TERMS.get(m.group(1), ()) if m else ()
    if not terms:
        return
    pat = re.compile("|".join(re.escape(t) for t in terms), re.IGNORECASE)
    for f in files:
        rel = f.relative_to(root).as_posix()
        if rel.startswith("tests/"):
            continue
        lines, in_list = f.read_text(encoding="utf-8").splitlines(), False
        for n, line in enumerate(lines, 1):
            in_list = line.startswith("RETIRED_TERMS = ") or (in_list and line != "}")  # the list itself
            hit = None if in_list else pat.search(line)
            if hit and not any("legacy" in x.lower() for x in lines[max(0, n - 4):n]):
                out.append(("retired-term", rel, n, f"retired term \"{hit.group(0)}\""))


def check_doc_counts(root: Path, py: Path, tree: ast.AST, out: list) -> None:
    nodes = [tree] + [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
    for node in nodes:
        doc = ast.get_docstring(node)
        if not doc:
            continue
        start = node.body[0].lineno if node.body else 1
        lines = doc.splitlines()
        for i, line in enumerate(lines):
            m = _DOC_COUNT_RE.match(line)
            if not m or i + 1 >= len(lines) or not lines[i + 1].strip():
                continue
            nxt, bullet = lines[i + 1], _ITEM_RE.match(lines[i + 1])
            ind = _indent(nxt)
            if ind <= _indent(line) and not bullet:
                continue
            got = 0
            for x in lines[i + 1:]:
                if not x.strip() or _indent(x) < ind:
                    break
                got += _indent(x) == ind and (not bullet or bool(_ITEM_RE.match(x)))
            want = int(m.group(1)) if m.group(1).isdigit() else _NUM[m.group(1).lower()]
            if got != want:
                out.append(("doc-count", py.relative_to(root).as_posix(), start + i,
                            f"docstring \"{line.strip()[:60]}\" introduces {got} item(s)"))


def _own_nodes(fn: ast.AST):
    """The nodes of *fn*'s body, not descending into nested functions, lambdas or classes."""
    stack = list(fn.body)
    while stack:
        node = stack.pop()
        yield node
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
            stack.extend(ast.iter_child_nodes(node))


def _stub_body(fn: ast.AST) -> bool:
    """True when the body (after any docstring) only passes, raises or is `...`."""
    body = fn.body[1:] if ast.get_docstring(fn) is not None else fn.body
    return all(isinstance(b, (ast.Pass, ast.Raise)) or (isinstance(b, ast.Expr) and isinstance(b.value, ast.Constant)
                                                        and b.value.value is Ellipsis) for b in body)


def check_code_hygiene(root: Path, py: Path, tree: ast.AST, out: list) -> None:
    """fix-narration, raises-no-raise and unused-param for one parsed script."""
    import io
    import tokenize
    rel, src = py.relative_to(root).as_posix(), py.read_text(encoding="utf-8")
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type == tokenize.COMMENT and _NARRATION_RE.search(tok.string):
                out.append(("fix-narration", rel, tok.start[0], f"comment narrates a fix event: {tok.string.strip()[:80]}"))
    except (tokenize.TokenError, SyntaxError):
        pass
    for node in [tree] + [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]:
        doc = ast.get_docstring(node)
        if doc and _NARRATION_RE.search(doc):
            line = node.body[0].lineno if node.body else 1
            out.append(("fix-narration", rel, line, f"docstring narrates a fix event: \"{_NARRATION_RE.search(doc).group(0)}\""))
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        m = _RAISES_RE.search(doc or "")
        if m and not any(isinstance(n, ast.Raise) for n in _own_nodes(node)):
            out.append(("raises-no-raise", rel, node.lineno,
                        f"{node.name}() docstring says \"{m.group(0).strip()}\" but its body has no raise"))
        if _stub_body(node):
            continue
        a = node.args
        params = [x.arg for x in a.posonlyargs + a.args + a.kwonlyargs] + [x.arg for x in (a.vararg, a.kwarg) if x]
        used = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
        if any(isinstance(n, ast.Call) and getattr(n.func, "id", "") in ("locals", "vars") for n in ast.walk(node)):
            continue
        for p in params:
            if p not in used and p not in ("self", "cls") and not p.startswith("_"):
                out.append(("unused-param", rel, node.lineno, f"{node.name}() never reads its parameter '{p}'"))


def check_dollar_vars(root: Path, files: list, out: list) -> None:
    skill = (root / "SKILL.md").read_text(encoding="utf-8") if (root / "SKILL.md").is_file() else ""
    code = "\n".join(f.read_text(encoding="utf-8") for f in files if f.suffix in (".py", ".sh"))
    for md in (f for f in files if f.suffix == ".md"):
        text = md.read_text(encoding="utf-8")
        for n, line in _unfenced(text):
            for name in dict.fromkeys(_DOLLAR_RE.findall(line)):
                if name in _STD_ENV or re.search(rf"(?<![\w$]){name}\s*=|\${{?{name}}}?`?\s*(?:is|means|:|=)", skill) \
                        or re.search(rf"\b{name}\s*=|['\"]{name}['\"]", code):
                    continue
                out.append(("dollar-var", md.relative_to(root).as_posix(), n,
                            f"${name} is not defined in SKILL.md or an in-scope script"))


def main() -> int:
    ap = argparse.ArgumentParser(description="Advisory doc lint (fixed checks).")
    ap.add_argument("--target", required=True, help="Target skill directory.")
    ap.add_argument("--checks", default=",".join(CHECKS), help="Comma-separated subset of " + ",".join(CHECKS))
    args = ap.parse_args()
    root, wanted = Path(args.target).expanduser().resolve(), set(args.checks.split(","))
    if not root.is_dir() or wanted - set(CHECKS):
        print(json.dumps({"error": f"bad --target or unknown check in {sorted(wanted - set(CHECKS))}"}), file=sys.stderr)
        return 2
    out: list = []
    files = inscope_files(root)
    for md in (p for p in files if p.suffix == ".md"):
        check_md(root, md, md.read_text(encoding="utf-8"), out)
    check_scripts(root, out)
    check_retired(root, files, out)
    check_dollar_vars(root, files, out)
    if "glossary" in wanted:
        check_glossary(root, out)
    findings = [{"check": c, "file": f, "line": n, "detail": d} for c, f, n, d in out if c in wanted]
    print(json.dumps({"findings": findings, "count": len(findings)}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
