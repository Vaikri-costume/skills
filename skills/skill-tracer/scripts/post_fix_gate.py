#!/usr/bin/env python3
"""post_fix_gate.py — blocking check run after each fixer batch, before close-round.

A round cannot close while a fix left a stale or new defect. The gate compares the target with a
snapshot taken before the batch and fails on what the batch introduced, never on unrelated findings
that were already there.

Five subcommands:
  snapshot    record the hash and full text of every in-scope file (inscope.py), the list of all
              file paths, and the doc_lint.py + cascade_sweep.py findings of the pre-fix tree.
  check       compute the touched lines per file (difflib) and fail when
                (a) a lint finding is new against the baseline, or sits on a touched line;
                (b) a touched line names something that does not resolve: a path with a directory
                    or a bare script name that is not a file, a --flag no argparse in the named
                    script registers (a line inside a script that registers flags names that script;
                    otherwise any script's flags count), an exit code the named script never
                    returns, a backticked identifier no .py file mentions. Step numbers, list and
                    docstring counts, section names and script-contract exit codes are checked by
                    the lints in (a). A name that was already unresolved in the snapshot is skipped;
                (c) a touched non-test .py file has more raise / return / exit / if / for / while /
                    try / ifexp / boolop nodes (the _BEHAVIOUR kinds) than its snapshot and one of
                    them sits on a touched line; the problem reads "new-behaviour: needs
                    ORCHESTRATOR-PAUSE: <kind> count N -> M"; a touched non-test .py file that no
                    longer parses is a problem of kind "syntax" at line 0 (the whole file);
                (d) a file, --flag or defined identifier the batch removed is still named elsewhere.
                (e) a rewritten doc block (BLOCK_MIN_LINES or more lines, at least BLOCK_MIN_TOUCHED and
                    BLOCK_SHARE of them changed; a .md paragraph, table or fenced run, or a run of .py
                    comment and docstring lines) is checked as a whole: lint findings and unresolved
                    names on its untouched lines are problems too, and a `block-reread` problem stands
                    until a `Blocks:` closure line of a decision in --fixer-transcript names a
                    `file:start-end` overlapping the block (the fixer re-read it whole).
              It also prints a non-blocking `siblings` list: for each distinctive term on a touched doc
              line (a backticked span with an underscore, path, dot, dash, space, bracket, colon, equals
              sign, digit or capital, a CLI flag, a file name, a quoted phrase of two or more words;
              doc lines are .md lines and .py comment lines and lines of strings holding two words), the untouched lines that name
              the same term, at most SIBLING_CAP per term, for terms naming 1 to SIBLING_MAX untouched
              lines, the SIBLING_TERMS terms with fewest first; `siblings_omitted` counts the rest. The
              orchestrator sends it back to the fixer with the inner-pass problems. `rewritten_blocks`
              lists each block of (e).
              Limit of the flag check: it reads the argparse of the script the line is in or names,
              so an error text inside a script that registers the flag passes even when that script
              is run by a caller that never passes it.
  merge-check compare an audited copy with the source tree (ignoring __pycache__ and .pyc).
  survival    record why a flag survived a round, as a comment line under its ledger row.
  causes      print the exit-2 cause table (EXIT2), or with --write / --check FILE replace / verify the
              generated block between its markers in a doc.

Usage:
    post_fix_gate.py snapshot --target <skill-dir> --out <snapshot.json>
    post_fix_gate.py check --target <skill-dir> --snapshot <snapshot.json> [--baseline-lint <lint.json>]
                       [--accept-new-behaviour FILE:KIND ...] [--fixer-transcript PATH[,PATH...]]
    post_fix_gate.py merge-check --source <source-dir> --audited <audited-dir>
    post_fix_gate.py causes [--write FILE ...] [--check FILE ...]
    post_fix_gate.py survival --ledger <ledger.md> --row <C3 or flag id> --cause <cause> [--round N]

  --baseline-lint  lint output to diff against instead of the findings stored in the snapshot: the
                   JSON of doc_lint.py, of cascade_sweep.py --json, or {"doc_lint": .., "cascade": ..}
                   (both keys; a dict holding only one of them is malformed input, exit 2).
  --accept-new-behaviour  repeatable orchestrator waiver for a behaviour-preserving refactor: FILE is
                   the problem's file and KIND the node kind named in its problem text
                   ("<kind> count N -> M"), one of the _BEHAVIOUR kinds raise, return, exit, if, for,
                   while, try, ifexp, boolop (not the problem's "new-behaviour" kind field).
  --cause          one of never-found, badly-fixed, cascade, not-merged (when each applies:
                   references/glossary.md "survival record").
  --round          narrows --row when the same cluster or flag id appears in several rounds.

The survival record is a line `<!-- survival:: round N C3 flags G1,G2 cause=cascade -->` written
directly under the row. It is not put in the Flags cell because close-round counts every
comma-separated Flags item as a raw flag and verify-auditability reads each as a flag id.

Output is JSON on stdout. check prints {"ok": true, ...} or {"ok": false, "problems": [{file, line,
kind, problem}]}, both with "siblings": [{term, touched, others, total}]; merge-check prints {"ok": .., "differences": [{file, status, hunks}]}.
Exit 0 = pass, 1 = blocking problems (or trees differ, or `causes` listed a problem on stderr: a
--write or --check file it cannot read, a --write file with no marker block, or a --check table that
is missing or differs; `causes` never exits 2), 2 = unreadable input (snapshot, check, merge-check,
survival); stderr then holds {"ok": false, "error", "cause", "remedy"} with the cause an EXIT2 id
(the table `causes` prints is the one list of causes and remedies).
Pure stdlib. Python 3.9+.
"""
from __future__ import annotations

import argparse
import ast
import difflib
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
from inscope import inscope_files  # noqa: E402
from doc_lint import _FLAG_RE as _FLAG_TOK, _returned_codes  # noqa: E402

DOC_LINT = _HERE / "doc_lint.py"
CASCADE = _HERE.parent / "cascade_sweep.py"
CAUSES = ("never-found", "badly-fixed", "cascade", "not-merged")
PAUSE = "new-behaviour: needs ORCHESTRATOR-PAUSE"


# Every exit-2 cause, disjoint by the observable (the error text's start, or the subcommand running).
# SKILL.md and references/script-contract.md carry this table generated by `causes --write`;
# tests/test_post_fix_gate.py fails when a raise names no registered cause, a cause is never raised,
# or either doc's copy differs, so the remedy for an exit 2 cannot drift from the script.
EXIT2 = (
    ("not-a-directory", "`--target is not a directory: <path>` (`snapshot`, `check`) or `not a directory: <path>` (`merge-check`)",
     "fix the path and re-run"),
    ("unreadable-target-file", "`cannot read <path>: ...` (an in-scope target file that is not UTF-8 text)",
     "fix that file and re-run"),
    ("snapshot-unusable", "`unreadable snapshot <path>: ...` (the `--snapshot` path names no file, or the file is not a snapshot), "
     "or `lint data is not a JSON object` / `<source> lint data is not a JSON object` when the stderr JSON "
     "`cause` is this one (printed by `check`; the snapshot's stored `lint` field is malformed)",
     "the batch's baseline is lost: take no new snapshot after the batch has edited the target, report the batch "
     "as unchecked and `SendMessage` the fixer to re-emit the decision of each of its clusters as "
     "`ORCHESTRATOR-PAUSE (post-fix gate: snapshot missing or unreadable)`"),
    ("lint-run-failed", "`<script> printed no JSON ...`, `<script> exited <N>: ...` (`doc_lint.py` or `cascade_sweep.py` failed) or "
     "`lint data is not a JSON object` / `<source> lint data is not a JSON object` when the stderr JSON `cause` "
     "is this one (printed by `check` on a lint it just ran)",
     "report the batch as unchecked and `SendMessage` the fixer to re-emit the decision of each of its clusters as "
     "`ORCHESTRATOR-PAUSE (post-fix gate: lint run failed)`"),
    ("snapshot-lint-failed", "the same texts, with this stderr JSON `cause`, printed by `snapshot` (before the batch is dispatched)",
     "do not dispatch the batch: leave its transcript out of the fix-recording step so fill-address records its "
     "clusters as ORCHESTRATOR-PAUSE"),
    ("baseline-unusable", "`unreadable --baseline-lint <path>: ...` or `<source> lint data is not a JSON object` when the stderr JSON "
     "`cause` is this one (including a dict holding only one of `doc_lint` / `cascade`)",
     "fix that file and re-run (SKILL.md's commands never pass `--baseline-lint`)"),
    ("ledger-unreadable", "`unreadable ledger <path>: ...` (`survival`)", "stop (\"Broken ledger\" in `references/script-contract.md`)"),
    ("survival-row-ambiguous", "`--row <id> matches <N> ledger rows (pass --round)`, N above 1 (`survival`)",
     "re-run with the right `--round`"),
    ("survival-row-missing", "`--row <id> matches 0 ledger rows` (`survival`)", "correct `--row` or `--round` and re-run"),
)
EXIT2_IDS = tuple(c[0] for c in EXIT2)
EXIT2_BEGIN, EXIT2_END = "<!-- gate-exit2:begin -->", "<!-- gate-exit2:end -->"


def exit2_block() -> str:
    """The generated exit-2 table, between its markers, as the docs carry it."""
    rows = [f"| {cid} | {obs} | {fix} |" for cid, obs, fix in EXIT2]
    return "\n".join([EXIT2_BEGIN, "| Cause | Observable | Remedy |", "|---|---|---|", *rows, EXIT2_END])


class GateInputError(Exception):
    """Unreadable or malformed input; the CLI turns it into exit 2. *cause* is an EXIT2_IDS entry."""

    def __init__(self, message: str, cause: str):
        super().__init__(message)
        self.cause = cause


# --- token patterns on a touched line ---
_PATH_TOK = re.compile(r"(?<![\w/.$<>{}*~-])((?:[\w-]+/)*[\w-]+\.(?:md|py|json|sh|txt|ya?ml))(?![\w-])")
_EXIT_TOK = re.compile(r"\bexit(?:s|ed)?\s*(?:code\s*|status\s*)?\(?\s*(\d)\b", re.IGNORECASE)
_TICK_TOK = re.compile(r"`([A-Za-z_][A-Za-z0-9_]*)(?:\(\))?`")
_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_PLACEHOLDER_STEMS = {"x", "y", "z", "n", "foo", "bar", "baz", "qux", "name", "skill", "example", "file"}
_ALWAYS_FLAGS = {"--help", "--version"}
_BEHAVIOUR = ("raise", "return", "exit", "if", "for", "while", "try", "ifexp", "boolop")
_SPAN_TOK = re.compile(r"`([^`\n]{3,80})`")
_QUOTE_TOK = re.compile(r'"([^"\n]{6,80})"')
_TWO_WORDS = re.compile(r"[A-Za-z]{2,}[ ,;:.'-]+[A-Za-z]{2,}")
SIBLING_CAP = 5       # untouched lines shown per term
SIBLING_TERMS = 15    # terms listed per check, fewest untouched lines first
SIBLING_MAX = 12      # a term naming more untouched lines than this is too common to act on: counted, not listed
BLOCK_MIN_LINES = 3   # a paragraph or comment run shorter than this is never a rewritten block
BLOCK_MIN_TOUCHED = 2
BLOCK_SHARE = 0.3     # a block is rewritten when at least this share of its lines (and BLOCK_MIN_TOUCHED) changed
_BLOCKS_LINE = re.compile(r"([\w./-]+):(\d+)-(\d+)")


# ---------------------------------------------------------------- tree model

class Tree:
    """One version of the target: in-scope texts plus every file path, with derived name tables."""

    def __init__(self, texts: dict, paths: set):
        self.texts, self.paths = texts, set(paths)
        self.basenames = {p.rsplit("/", 1)[-1] for p in self.paths}
        self.flags_by_script: dict = {}
        self.codes_by_script: dict = {}
        self.defined: set = set()
        self.py_words: set = set()
        for rel, text in texts.items():
            if not rel.endswith(".py"):
                if rel.endswith((".json", ".yaml", ".yml", ".sh")):
                    self.py_words.update(_WORD.findall(text))
                continue
            self.py_words.update(_WORD.findall(text))
            tree = parse_py(text)
            if tree is None:
                continue
            name = rel.rsplit("/", 1)[-1]
            flags = {a.value for n in ast.walk(tree) if isinstance(n, ast.Call)
                     and getattr(n.func, "attr", "") == "add_argument"
                     for a in n.args if isinstance(a, ast.Constant) and str(a.value).startswith("--")}
            self.flags_by_script.setdefault(name, set()).update(flags)
            self.codes_by_script[name] = _returned_codes(tree) | ({2} if flags else set())
            for n in ast.walk(tree):
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    self.defined.add(n.name)
                elif isinstance(n, (ast.Assign, ast.AnnAssign)):
                    targets = n.targets if isinstance(n, ast.Assign) else [n.target]
                    self.defined.update(t.id for t in targets if isinstance(t, ast.Name))
                elif isinstance(n, (ast.Import, ast.ImportFrom)):
                    self.defined.update(a.asname or a.name.split(".")[0] for a in n.names)
        self.all_flags = set().union(*self.flags_by_script.values()) if self.flags_by_script else set()

    def has_path(self, tok: str) -> bool:
        if "/" not in tok:
            return tok in self.basenames
        return any(p == tok or p.endswith("/" + tok) for p in self.paths) or \
            any(f"{d}/{tok}" in self.paths for d in ("references", "scripts"))


def parse_py(text: str):
    try:
        return ast.parse(text)
    except SyntaxError:
        return None


def all_paths(root: Path) -> set:
    return {p.relative_to(root).as_posix() for p in root.rglob("*")
            if p.is_file() and "__pycache__" not in p.relative_to(root).parts}


def read_tree(root: Path) -> Tree:
    texts = {}
    for p in inscope_files(root):
        try:
            texts[p.relative_to(root.resolve()).as_posix()] = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            raise GateInputError(f"cannot read {p}: {e}", "unreadable-target-file") from e
    return Tree(texts, all_paths(root))


# ---------------------------------------------------------------- lint runs

def _run_json(cmd: list) -> dict:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise GateInputError(f"{Path(cmd[1]).name} printed no JSON (exit {proc.returncode}): "
                             f"{proc.stderr.strip()[:300]}", "lint-run-failed") from e
    if proc.returncode != 0:
        raise GateInputError(f"{Path(cmd[1]).name} exited {proc.returncode}: {proc.stderr.strip()[:300]}", "lint-run-failed")
    return data


def run_lints(root: Path) -> dict:
    return {"doc_lint": _run_json([sys.executable, str(DOC_LINT), "--target", str(root)]),
            "cascade": _run_json([sys.executable, str(CASCADE), str(root), "--json"])}


def normalise_lint(data, cause: str = "lint-run-failed") -> list:
    """Flatten doc_lint / cascade_sweep output (or a dict holding both) to [{source, check, file, line, detail}]."""
    if not isinstance(data, dict):
        raise GateInputError("lint data is not a JSON object", cause)
    parts = [("doc_lint", data.get("doc_lint")), ("cascade", data.get("cascade"))] \
        if "doc_lint" in data or "cascade" in data else [("lint", data)]
    out = []
    for source, part in parts:
        if not isinstance(part, dict):
            raise GateInputError(f"{source} lint data is not a JSON object", cause)
        for key in ("findings", "prepass", "advisory"):
            for f in part.get(key, []):
                out.append({"source": source, "check": f.get("check", ""), "file": f.get("file", ""),
                            "line": f.get("line") or 0, "detail": f.get("detail", "")})
        for e in part.get("detector_errors", []):
            out.append({"source": source, "check": "detector-error", "file": e.get("file", ""),
                        "line": 0, "detail": f"{e.get('detector')}: {e.get('error')}"})
    return out


def _lint_key(f: dict) -> tuple:
    detail = re.sub(r"(?:\bline\s+|:)\d+", "", f["detail"])
    return f["check"], f["file"], detail


# ---------------------------------------------------------------- snapshot

def cmd_snapshot(args) -> int:
    root = Path(args.target).expanduser().resolve()
    if not root.is_dir():
        raise GateInputError(f"--target is not a directory: {root}", "not-a-directory")
    tree = read_tree(root)
    try:
        lint = run_lints(root)
        baseline = normalise_lint(lint)
    except GateInputError as e:
        raise GateInputError(str(e), "snapshot-lint-failed") from e
    snap = {"target": str(root), "paths": sorted(tree.paths),
            "files": {rel: {"sha256": hashlib.sha256(t.encode("utf-8")).hexdigest(), "text": t}
                      for rel, t in tree.texts.items()},
            "lint": lint}
    Path(args.out).expanduser().write_text(json.dumps(snap), encoding="utf-8")
    print(json.dumps({"snapshot": str(args.out), "files": len(snap["files"]),
                      "baseline_findings": len(baseline)}, indent=2))
    return 0


def load_snapshot(path: str) -> dict:
    try:
        snap = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
        files = snap["files"]
        if not isinstance(files, dict) or not all(isinstance(v, dict) and isinstance(v["text"], str)
                                                  for v in files.values()):
            raise ValueError("files entries need a text field")
    except (OSError, UnicodeDecodeError, ValueError, KeyError, TypeError) as e:
        raise GateInputError(f"unreadable snapshot {path}: {e}", "snapshot-unusable") from e
    return snap


def baseline_lint(snap: dict, override: str | None) -> list:
    if override:
        try:
            return normalise_lint(json.loads(Path(override).expanduser().read_text(encoding="utf-8")), "baseline-unusable")
        except (OSError, ValueError) as e:
            raise GateInputError(f"unreadable --baseline-lint {override}: {e}", "baseline-unusable") from e
    if "lint" in snap:
        return normalise_lint(snap["lint"], "snapshot-unusable")
    with tempfile.TemporaryDirectory() as d:  # rebuild the pre-fix tree and lint it
        for rel, entry in snap["files"].items():
            p = Path(d, rel)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(entry["text"], encoding="utf-8")
        return normalise_lint(run_lints(Path(d)))


# ---------------------------------------------------------------- check

def touched_lines(old: str | None, new: str | None):
    """(touched new-side line numbers, removed old-side lines) for one file."""
    a = old.splitlines() if old is not None else []
    b = new.splitlines() if new is not None else []
    touched, removed = set(), []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag in ("replace", "insert"):
            touched.update(range(j1 + 1, j2 + 1))
        if tag in ("replace", "delete"):
            removed.extend(a[i1:i2])
    return touched, removed


def _scripts_named(line: str, tree: Tree) -> list:
    return [s for s in re.findall(r"[\w-]+\.py", line) if s in tree.flags_by_script]


def unresolved(rel: str, line: str, tree: Tree) -> list:
    """(kind, token, why) for each name on *line* that does not resolve against *tree*."""
    out = []
    if "://" in line:
        line = re.sub(r"\S+://\S+", "", line)
    for tok in _PATH_TOK.findall(line):
        stem = tok.rsplit("/", 1)[-1].rsplit(".", 1)[0].lower()
        if stem in _PLACEHOLDER_STEMS or ("/" not in tok and not tok.endswith(".py")):
            continue
        if not tree.has_path(tok):
            out.append(("path", tok, f"{tok} is not a file in the target"))
    in_py = rel.endswith(".py")
    own = rel.rsplit("/", 1)[-1]
    if not (in_py and "add_argument" in line):
        named = _scripts_named(line, tree)
        if not named and in_py and tree.flags_by_script.get(own):
            named = [own]
        for flag in dict.fromkeys(_FLAG_TOK.findall(line)):
            pool = set().union(*(tree.flags_by_script[s] for s in named)) if named else tree.all_flags
            if flag not in pool and flag not in _ALWAYS_FLAGS:
                where = ", ".join(named) if named else "any script"
                out.append(("flag", flag, f"{flag} is not registered by argparse in {where}"))
    named = [s for s in re.findall(r"[\w-]+\.py", line) if s in tree.codes_by_script]
    if not named and in_py and rel.rsplit("/", 1)[-1] in tree.codes_by_script:
        named = [rel.rsplit("/", 1)[-1]]
    if named:
        codes = set().union(*(tree.codes_by_script[s] for s in named)) | {0}
        for code in dict.fromkeys(_EXIT_TOK.findall(line)):
            if int(code) not in codes:
                out.append(("exit-code", f"exit {code}", f"{', '.join(named)} never exits {code}"))
    for ident in dict.fromkeys(_TICK_TOK.findall(line)):
        if ("_" in ident.strip("_") or ident[1:] != ident[1:].lower()) and len(ident) >= 3 \
                and ident not in tree.py_words:
            out.append(("identifier", ident, f"`{ident}` is not named in any .py file"))
    return out


def behaviour_nodes(tree: ast.AST) -> dict:
    """kind -> [line numbers] for the nodes that add an exit path or a branch."""
    found = {k: [] for k in _BEHAVIOUR}
    for n in ast.walk(tree):
        kind = None
        if isinstance(n, ast.Raise):
            kind = "raise"
        elif isinstance(n, ast.Return):
            kind = "return"
        elif isinstance(n, ast.Call) and (getattr(n.func, "id", "") in ("exit", "quit")
                                          or getattr(n.func, "attr", "") in ("exit", "_exit")):
            kind = "exit"
        elif isinstance(n, ast.If):
            kind = "if"
        elif isinstance(n, ast.IfExp):
            kind = "ifexp"
        elif isinstance(n, ast.BoolOp):
            kind = "boolop"
        elif isinstance(n, (ast.For, ast.AsyncFor)):
            kind = "for"
        elif isinstance(n, ast.While):
            kind = "while"
        elif isinstance(n, ast.Try) or type(n).__name__ == "TryStar":
            kind = "try"
        if kind:
            found[kind].append(n.lineno)
    return found


def _grep(new: Tree, pattern: re.Pattern) -> list:
    return [(rel, i, line) for rel, text in sorted(new.texts.items())
            for i, line in enumerate(text.splitlines(), 1) if pattern.search(line)]


def stale_siblings(old: Tree, new: Tree) -> list:
    """Problems for each removed file, flag or defined identifier still named in the new tree."""
    removed = []
    for path in sorted(old.paths - new.paths):
        base = path.rsplit("/", 1)[-1]
        if base not in new.basenames:
            removed.append(("file", base, re.compile(rf"(?<![\w-]){re.escape(base)}(?![\w-])")))
    for flag in sorted(old.all_flags - new.all_flags):
        removed.append(("flag", flag, re.compile(rf"(?<![\w-]){re.escape(flag)}(?![\w-])")))
    for ident in sorted(old.defined - new.defined):
        if len(ident) >= 4 and ("_" in ident.strip("_") or ident[1:] != ident[1:].lower()):
            removed.append(("identifier", ident, re.compile(rf"\b{re.escape(ident)}\b")))
    return [{"file": rel, "line": n, "kind": "stale-sibling",
             "problem": f"removed {kind} {tok} is still named here: {line.strip()[:160]}"}
            for kind, tok, pat in removed for rel, n, line in _grep(new, pat)]


def doc_lines(rel: str, text: str) -> set:
    """Line numbers of *text* that are prose: every line of a .md file; the comment lines and the
    lines of string constants holding two words (not a regex or a key) of a .py file; none for other
    files."""
    lines = text.splitlines()
    if rel.endswith(".md"):
        return set(range(1, len(lines) + 1))
    if not rel.endswith(".py"):
        return set()
    out = {i for i, line in enumerate(lines, 1) if line.lstrip().startswith("#")}
    tree = parse_py(text)
    for n in ast.walk(tree) if tree is not None else ():
        words = n.value if isinstance(n, ast.Constant) and isinstance(n.value, str) else \
            "".join(v.value for v in n.values if isinstance(v, ast.Constant)) if isinstance(n, ast.JoinedStr) else ""
        if _TWO_WORDS.search(words):
            out.update(range(n.lineno, (n.end_lineno or n.lineno) + 1))
    return out


def _distinctive_span(t: str) -> bool:
    """A backticked span worth matching elsewhere: holds a letter and more than one plain lowercase word
    would (an underscore, path, dot, dash, space, bracket, colon, equals sign, digit or capital), so
    `for`, `return` and `exit` are not terms."""
    return bool(re.search(r"[A-Za-z]", t) and re.search(r"[_/.\-\s()\[\]:=0-9]|(?<=.)[A-Z]", t))


def line_terms(line: str) -> list:
    """(term, pattern) for each distinctive term on *line*: backticked spans holding a letter, CLI
    flags, file names and quoted phrases of two or more words."""
    terms = [t for t in _SPAN_TOK.findall(line) if _distinctive_span(t)]
    terms += _FLAG_TOK.findall(line)
    terms += [t.rsplit("/", 1)[-1] for t in _PATH_TOK.findall(line)]
    terms += [t for t in _QUOTE_TOK.findall(line) if _TWO_WORDS.search(t)]
    out = []
    for t in dict.fromkeys(terms):
        edge_l = r"(?<![\w-])" if re.match(r"[\w-]", t) else ""
        edge_r = r"(?![\w-])" if re.search(r"[\w-]$", t) else ""
        out.append((t, re.compile(edge_l + re.escape(t) + edge_r)))
    return out


def siblings(new: Tree, touched: dict) -> tuple:
    """(entries, omitted): for each distinctive term on a touched doc line that names 1 to SIBLING_MAX
    untouched lines of *new*, those lines (SIBLING_CAP shown, `total` counts all); the SIBLING_TERMS
    terms with fewest lines are kept and *omitted* counts the terms dropped as too common or beyond the cap."""
    seen: dict = {}
    for rel in sorted(touched):
        text_lines = new.texts.get(rel, "").splitlines()
        prose = doc_lines(rel, new.texts.get(rel, ""))
        for n in sorted(touched[rel] & prose):
            for term, pat in line_terms(text_lines[n - 1]):
                seen.setdefault(term, (pat, []))[1].append(f"{rel}:{n}")
    out, omitted = [], 0
    for term, (pat, where) in seen.items():
        others = [f"{rel}:{i}" for rel, i, _ in _grep(new, pat) if i not in touched.get(rel, ())]
        if not others:
            continue
        if len(others) > SIBLING_MAX:
            omitted += 1
            continue
        out.append({"term": term, "touched": where[:SIBLING_CAP], "others": others[:SIBLING_CAP],
                    "total": len(others)})
    out.sort(key=lambda e: e["total"])
    return out[:SIBLING_TERMS], omitted + max(0, len(out) - SIBLING_TERMS)


def prose_blocks(rel: str, text: str) -> list:
    """(start, end) 1-based line ranges of the doc blocks of *text*: the paragraphs (and tables, and
    fenced runs) of a .md file, the runs of consecutive doc lines (comments, docstrings) of a .py file."""
    lines = text.splitlines()
    if rel.endswith(".md"):
        keep = {i for i, line in enumerate(lines, 1) if line.strip()}
    else:
        keep = doc_lines(rel, text)
    out, start, prev = [], None, None
    for i in sorted(keep):
        if start is None:
            start = i
        elif i != prev + 1:
            out.append((start, prev))
            start = i
        prev = i
    if start is not None:
        out.append((start, prev))
    return out


def rewritten_blocks(rel: str, text: str, touched: set) -> list:
    """The (start, end, touched_count) of each doc block of *text* of BLOCK_MIN_LINES or more lines in
    which at least BLOCK_MIN_TOUCHED lines and BLOCK_SHARE of the lines changed."""
    out = []
    for a, b in prose_blocks(rel, text):
        hit = len(touched & set(range(a, b + 1)))
        if b - a + 1 >= BLOCK_MIN_LINES and hit >= BLOCK_MIN_TOUCHED and hit / (b - a + 1) >= BLOCK_SHARE:
            out.append((a, b, hit))
    return out


def blocks_reread(transcripts: list) -> list:
    """(file, start, end) from the `Blocks:` closure lines of the FIX decisions in *transcripts*; an
    unreadable transcript or a decision without the line adds none."""
    import ledger_common as lc
    out = []
    for path in transcripts:
        try:
            decisions = lc.fixer_decisions(path)
        except (OSError, ValueError):
            continue
        for d in decisions:
            for line in d.get("closure") or [] if isinstance(d, dict) else []:
                label, _, value = str(line).partition(":")
                if label.strip() == "Blocks":
                    out += [(f, int(a), int(b)) for f, a, b in _BLOCKS_LINE.findall(value)]
    return out


def run_check(root: Path, snap: dict, base: list, accepted=(), reread=()) -> dict:
    old = Tree({rel: e["text"] for rel, e in snap["files"].items()},
               snap.get("paths") or snap["files"].keys())
    new = read_tree(root)
    touched, problems = {}, []
    for rel in sorted(set(old.texts) | set(new.texts)):
        t_old, t_new = old.texts.get(rel), new.texts.get(rel)
        if t_old == t_new:
            continue
        lines, _ = touched_lines(t_old, t_new)
        if lines:
            touched[rel] = lines

    # (a) lint: new against the baseline, or on a touched line
    after = normalise_lint(run_lints(root))
    grown = Counter(_lint_key(f) for f in after) - Counter(_lint_key(f) for f in base)
    for f in after:
        on_touched = f["line"] in touched.get(f["file"], ())
        if _lint_key(f) in grown or on_touched:
            why = "new lint finding" if _lint_key(f) in grown else "lint finding on a touched line"
            problems.append({"file": f["file"], "line": f["line"], "kind": f"lint:{f['check']}",
                             "problem": f"{why} ({f['source']} {f['check']}): {f['detail']}"})

    # (b) names on touched lines resolve
    stale_before = {(kind, tok) for rel, text in old.texts.items() for line in text.splitlines()
                    for kind, tok, _ in unresolved(rel, line, old)}
    for rel, lines in touched.items():
        text_lines = new.texts[rel].splitlines()
        for n in sorted(lines):
            for kind, tok, why in unresolved(rel, text_lines[n - 1], new):
                if (kind, tok) not in stale_before:
                    problems.append({"file": rel, "line": n, "kind": f"unresolved-{kind}", "problem": why})

    # (c) new exit paths or branches in touched python
    for rel, lines in touched.items():
        if not rel.endswith(".py") or rel.startswith("tests/"):
            continue
        t_new = parse_py(new.texts[rel])
        if t_new is None:
            problems.append({"file": rel, "line": 0, "kind": "syntax", "problem": "file no longer parses"})
            continue
        t_old = parse_py(old.texts.get(rel, ""))
        if t_old is None:
            continue
        before, after_nodes = behaviour_nodes(t_old), behaviour_nodes(t_new)
        for kind in _BEHAVIOUR:
            hits = [n for n in after_nodes[kind] if n in lines]
            if f"{rel}:{kind}" in accepted:
                continue
            if len(after_nodes[kind]) > len(before[kind]) and hits:
                problems.append({"file": rel, "line": hits[0], "kind": "new-behaviour",
                                 "problem": f"{PAUSE}: {kind} count {len(before[kind])} -> "
                                            f"{len(after_nodes[kind])} (touched lines {hits[:5]})"})

    # (d) removed names still named elsewhere
    problems.extend(stale_siblings(old, new))

    # (e) a rewritten doc block is checked as a whole: lint findings and unresolved names on its
    # untouched lines too, and its Closure `Blocks:` re-read
    blocks = []
    for rel, lines in sorted(touched.items()):
        text_lines = new.texts[rel].splitlines()
        for a, b, hit in rewritten_blocks(rel, new.texts[rel], lines):
            blocks.append({"file": rel, "start": a, "end": b})
            where = f"rewritten block {rel}:{a}-{b}"
            for f in after:
                if f["file"] == rel and a <= f["line"] <= b and f["line"] not in lines:
                    problems.append({"file": rel, "line": f["line"], "kind": f"lint:{f['check']}",
                                     "problem": f"lint finding in {where} ({f['source']} {f['check']}): {f['detail']}"})
            for n in range(a, b + 1):
                if n in lines:
                    continue
                for kind, tok, why in unresolved(rel, text_lines[n - 1], new):
                    if (kind, tok) not in stale_before:
                        problems.append({"file": rel, "line": n, "kind": f"unresolved-{kind}",
                                         "problem": f"{why} (in {where})"})
            if not any(f == rel and a <= y and x <= b for f, x, y in reread):
                problems.append({"file": rel, "line": a, "kind": "block-reread",
                                 "problem": f"{where} ({b - a + 1} lines, {hit} changed): re-read the whole block "
                                            f"against the code and its sibling sites, then list it as `{rel}:{a}-{b}` "
                                            f"in the decision's closure `Blocks:` line (each cause or case in it has "
                                            f"one remedy; causes are disjoint)"})

    near, omitted = siblings(new, touched)
    if problems:
        return {"ok": False, "problems": problems, "rewritten_blocks": blocks,
                "touched": {rel: sorted(v) for rel, v in touched.items()},
                "siblings": near, "siblings_omitted": omitted}
    return {"ok": True, "touched_files": len(touched),
            "touched_lines": sum(len(v) for v in touched.values()),
            "pre_existing_findings": len(after), "rewritten_blocks": blocks,
            "siblings": near, "siblings_omitted": omitted}


def cmd_check(args) -> int:
    root = Path(args.target).expanduser().resolve()
    if not root.is_dir():
        raise GateInputError(f"--target is not a directory: {root}", "not-a-directory")
    snap = load_snapshot(args.snapshot)
    transcripts = [x.strip() for v in args.fixer_transcript for x in v.split(",") if x.strip()]
    report = run_check(root, snap, baseline_lint(snap, args.baseline_lint), args.accept_new_behaviour,
                       blocks_reread(transcripts))
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


# ---------------------------------------------------------------- merge-check

def _tree_files(root: Path) -> dict:
    return {p.relative_to(root).as_posix(): p for p in sorted(root.rglob("*"))
            if p.is_file() and "__pycache__" not in p.relative_to(root).parts and p.suffix != ".pyc"}


def cmd_merge_check(args) -> int:
    src, aud = Path(args.source).expanduser(), Path(args.audited).expanduser()
    for p in (src, aud):
        if not p.is_dir():
            raise GateInputError(f"not a directory: {p}", "not-a-directory")
    a, b = _tree_files(src), _tree_files(aud)
    diffs = []
    for rel in sorted(set(a) | set(b)):
        if rel not in b:
            diffs.append({"file": rel, "status": "only-in-source", "hunks": []})
        elif rel not in a:
            diffs.append({"file": rel, "status": "only-in-audited", "hunks": []})
        elif a[rel].read_bytes() != b[rel].read_bytes():
            try:
                la = a[rel].read_text(encoding="utf-8").splitlines()
                lb = b[rel].read_text(encoding="utf-8").splitlines()
            except UnicodeDecodeError:
                diffs.append({"file": rel, "status": "differs (binary)", "hunks": []})
                continue
            hunks, cur = [], None
            for line in difflib.unified_diff(la, lb, "source/" + rel, "audited/" + rel, lineterm="", n=1):
                if line.startswith("@@"):
                    cur = [line]
                    hunks.append(cur)
                elif cur is not None:
                    cur.append(line)
            diffs.append({"file": rel, "status": "differs", "hunks": ["\n".join(h) for h in hunks]})
    print(json.dumps({"ok": not diffs, "differences": diffs}, indent=2))
    return 1 if diffs else 0


# ---------------------------------------------------------------- survival

def cmd_survival(args) -> int:
    import ledger_common as lc
    ledger = Path(args.ledger).expanduser()
    try:
        lines = ledger.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as e:
        raise GateInputError(f"unreadable ledger {ledger}: {e}", "ledger-unreadable") from e
    hits = []
    for i, line in enumerate(lines):
        row = lc.parse_row(line)
        if row and (args.round is None or row["round"] == args.round) \
                and (row["cluster"] == args.row or args.row in row["flags"]):
            hits.append((i, row))
    if len(hits) != 1:
        raise GateInputError(f"--row {args.row} matches {len(hits)} ledger rows"
                             + (" (pass --round)" if hits else ""),
                             "survival-row-ambiguous" if hits else "survival-row-missing")
    i, row = hits[0]
    note = (f"<!-- survival:: round {row['round']} {row['cluster']} flags {','.join(row['flags']) or '-'} "
            f"cause={args.cause} -->")
    written = not (i + 1 < len(lines) and lines[i + 1] == note)
    if written:
        lines.insert(i + 1, note)
        ledger.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"ledger": str(ledger), "line": note, "written": written}, indent=2))
    return 0


# ---------------------------------------------------------------- causes

_BLOCK_RE = re.compile(re.escape(EXIT2_BEGIN) + r".*?" + re.escape(EXIT2_END), re.DOTALL)


def cmd_causes(args) -> int:
    table, bad = exit2_block(), []
    for path in args.write:
        p = Path(path).expanduser()
        try:
            text = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            bad.append(f"{path}: cannot read ({e})")
            continue
        if not _BLOCK_RE.search(text):
            bad.append(f"{path}: no {EXIT2_BEGIN} ... {EXIT2_END} block to replace")
            continue
        p.write_text(_BLOCK_RE.sub(lambda _m: table, text, count=1), encoding="utf-8")
    for path in args.check:
        try:
            m = _BLOCK_RE.search(Path(path).expanduser().read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError) as e:
            bad.append(f"{path}: cannot read ({e})")
            continue
        if not m or m.group(0) != table:
            bad.append(f"{path}: the exit-2 table is missing or differs (run `causes --write {path}`)")
    if not args.write and not args.check:
        print(table)
    for b in bad:
        print(b, file=sys.stderr)
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Blocking post-fix gate for skill-tracer fixer batches.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("snapshot", help="record the pre-fix tree and its lint findings")
    s.add_argument("--target", required=True)
    s.add_argument("--out", required=True)
    c = sub.add_parser("check", help="fail on what the fixer batch introduced")
    c.add_argument("--target", required=True)
    c.add_argument("--snapshot", required=True)
    c.add_argument("--baseline-lint", default=None)
    c.add_argument("--accept-new-behaviour", action="append", default=[], metavar="FILE:KIND",
                   help="orchestrator waiver for a behaviour-preserving refactor; record it in the ledger")
    c.add_argument("--fixer-transcript", action="append", default=[], metavar="PATH[,PATH...]",
                   help="the batch's fixer transcript(s): their closure `Blocks:` lines clear block-reread problems")
    m = sub.add_parser("merge-check", help="fail when the audited copy differs from the source")
    m.add_argument("--source", required=True)
    m.add_argument("--audited", required=True)
    v = sub.add_parser("survival", help="record why a flag survived a round")
    v.add_argument("--ledger", required=True)
    v.add_argument("--row", required=True)
    v.add_argument("--cause", required=True, choices=CAUSES)
    v.add_argument("--round", type=int, default=None)
    k = sub.add_parser("causes", help="print the exit-2 cause table, or write or check it in docs")
    k.add_argument("--write", action="append", default=[], metavar="FILE",
                   help="replace the generated block in FILE (it must carry the begin and end markers)")
    k.add_argument("--check", action="append", default=[], metavar="FILE",
                   help="exit 1 when FILE's generated block is missing or differs from the table")
    args = ap.parse_args()
    handler = {"snapshot": cmd_snapshot, "check": cmd_check, "merge-check": cmd_merge_check,
               "survival": cmd_survival, "causes": cmd_causes}[args.cmd]
    try:
        return handler(args)
    except GateInputError as e:
        remedy = next(fix for cid, _, fix in EXIT2 if cid == e.cause)
        print(json.dumps({"ok": False, "error": str(e), "cause": e.cause, "remedy": remedy}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
