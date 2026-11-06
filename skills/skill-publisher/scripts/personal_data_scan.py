#!/usr/bin/env python3
"""Personal-data scan for a skill that is about to be shipped.

Also flags gendered pronouns (he, she, him, her, his, hers, himself, herself) in markdown and piped
text: the user and anyone else without stated pronouns is "they/them", so rewrite with "they", "them",
"their", or reword. Quoted source text and LICENSE files are exempt (LICENSE is skipped).

Built in, with no profile: module codes (three capital letters + four digits) and, on the same line,
assessment labels (PS1, AS2). Looks for personal details that must not appear in a shipped skill: home-directory paths
(/Users/<name>, /home/<name>, C:\\Users\\<name>), email addresses, and any extra terms listed in
the user profile key `personal_terms` (comma separated words or phrases: names, institutions, module titles, assessment titles, field and research-focus terms) or `personal_patterns` (comma separated regexes, e.g. module codes), or passed with --term. Matches listed under the profile key `scan_allowlist` (exact match, or `path:<substring>` for a whole file) are not reported. A skill passes by
referring to "the user" / the user profile instead.

Usage:
    personal_data_scan.py <path> [<path> ...] [--term WORD ...] [--profile FILE]

<path> may be a skill folder (scanned recursively, text files only, hidden/excluded names skipped),
a single file, or `-` for stdin (use it for the staged PR diff, the PR body and the changelog
entry: pipe the text in). Allowed: generic placeholders (`/Users/<name>`, `~/`, `$HOME`,
`user@example.com`, noreply addresses).

Output JSON: {"findings": [{"file", "line", "kind", "match"}], "scanned": N, "clean": bool}
Exit 0 clean, 1 findings, 2 usage error.
"""
import argparse
import json
import re
import sys
from pathlib import Path

HOME_PATH = re.compile(r"(?:/Users/|/home/|[A-Za-z]:\\Users\\)([A-Za-z0-9._-]+)")
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PLACEHOLDER_NAMES = {"x", "claude", "priya", "marcus", "dana", "jo", "jdoe", "u", "alice", "bob", "jane", "john", "foo", "me", "name", "user", "username", "you", "me", "yourname", "your-name", "<name>", "example", "shared"}
ALLOWED_EMAIL = re.compile(r"(@example\.(com|org|net)$|noreply|no-reply|@users\.noreply\.github\.com$)", re.I)
# Built-in default (no profile needed): a module code (three capital letters + four digits, e.g. AAA0000)
# and, on the same line as one, an assessment label (PS1, AS2). Standards names that look alike are exempt.
MODULE_CODE = re.compile(r"\b(?!(?:RFC|ISO|SHA|UTF|ASN|BCP|STD|PEP|CVE|IEC|ANSI|AAA)\d)[A-Z]{3}\d{4}\b")
ASSESSMENT = re.compile(r"\b(?:PS|AS)\d\b")
GENDERED = re.compile(r"\b(he|she|him|her|hers|his|himself|herself)\b", re.I)
SKIP_DIRS = {".git", "__pycache__", "node_modules"}
TEXT_SUFFIX = {".md", ".txt", ".py", ".json", ".yaml", ".yml", ".sh", ".toml", ".cfg", ".html", ".css", ".js", ""}


def profile_values(profile, key):
    """Comma-separated values of profile bullet `key` (first profile found), else []."""
    cands = [Path(profile)] if profile else []
    p = Path.cwd()
    cands += [d / "config" / "user-profile.md" for d in [p, *p.parents]]
    for c in cands:
        if c.is_file():
            for line in c.read_text(encoding="utf-8", errors="ignore").splitlines():
                m = re.match(rf"\s*[-*]\s*`?{key}`?\s*:\s*(.+)", line)
                if m:
                    return [t.strip() for t in m.group(1).split(",") if t.strip()]
    return []


def profile_terms(profile):
    return profile_values(profile, "personal_terms")


def profile_patterns(profile):
    """Regexes from profile key `personal_patterns` (e.g. module codes, assessment titles)."""
    out = []
    for r in profile_values(profile, "personal_patterns"):
        try:
            out.append(re.compile(r))
        except re.error:
            pass
    return out


def allowlist(profile=None):
    """Exact matches or `path:<substring>` entries from profile key `scan_allowlist` (third-party emails, fixtures)."""
    return profile_values(profile, "scan_allowlist")


def allowed(f, allow):
    for a in allow:
        if a.startswith("path:") and a[5:] in f["file"]:
            return True
        if a == f["match"]:
            return True
    return False


def scan_text(text, label, terms, pronouns=None, patterns=()):
    """pronouns: scan for gendered pronouns. Default: on for stdin and markdown labels (README,
    HISTORY, PR body, changelog, references), off for code and LICENSE text."""
    if pronouns is None:
        pronouns = label.endswith(".md") or label.startswith("<")
    if label.upper().startswith("LICENSE"):
        pronouns = False
    out = []
    for i, line in enumerate(text.splitlines(), 1):
        codes = MODULE_CODE.findall(line)
        for c in codes:
            out.append({"file": label, "line": i, "kind": "module-code", "match": c})
        if codes:
            for m in ASSESSMENT.finditer(line):
                out.append({"file": label, "line": i, "kind": "module-assessment", "match": m.group(0)})
        if pronouns:
            for m in GENDERED.finditer(line):
                if m.group(0) == "HE":  # the acronym for higher education, not a pronoun
                    continue
                out.append({"file": label, "line": i, "kind": "gendered-pronoun", "match": m.group(0)})
        for m in HOME_PATH.finditer(line):
            if m.group(1).lower().strip("<>") in PLACEHOLDER_NAMES or line[m.start(1)-1:m.start(1)] == "<":
                continue
            out.append({"file": label, "line": i, "kind": "home-path", "match": m.group(0)})
        for m in EMAIL.finditer(line):
            if not ALLOWED_EMAIL.search(m.group(0)):
                out.append({"file": label, "line": i, "kind": "email", "match": m.group(0)})
        for rx in patterns:
            for m in rx.finditer(line):
                out.append({"file": label, "line": i, "kind": "profile-pattern", "match": m.group(0)})
        for t in terms:
            if re.search(rf"(?<![A-Za-z0-9]){re.escape(t)}(?![A-Za-z0-9])", line, re.I):
                out.append({"file": label, "line": i, "kind": "profile-term", "match": t})
    return out


def iter_files(root):
    if root.is_file():
        yield root, root.name
        return
    for f in sorted(root.rglob("*")):
        rel = f.relative_to(root)
        if not f.is_file() or any(p in SKIP_DIRS or p.startswith(".") for p in rel.parts):
            continue
        if "-workspace" in str(rel) or rel.as_posix().startswith("evals/fixtures") or f.suffix.lower() not in TEXT_SUFFIX:
            continue
        yield f, rel.as_posix()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--term", action="append", default=[])
    ap.add_argument("--profile")
    a = ap.parse_args()
    terms = a.term + profile_terms(a.profile)
    patterns = profile_patterns(a.profile)
    allow = allowlist(a.profile)
    findings, scanned = [], 0
    for p in a.paths:
        if p == "-":
            findings += [f for f in scan_text(sys.stdin.read(), "<stdin>", terms, None, patterns) if not allowed(f, allow)]
            scanned += 1
            continue
        root = Path(p).expanduser()
        if not root.exists():
            print(json.dumps({"error": f"not found: {p}"}), file=sys.stderr)
            sys.exit(2)
        for f, label in iter_files(root):
            try:
                findings += [x for x in scan_text(f.read_text(encoding="utf-8"), label, terms, None, patterns) if not allowed(x, allow)]
                scanned += 1
            except (UnicodeDecodeError, OSError):
                continue
    print(json.dumps({"findings": findings, "scanned": scanned, "clean": not findings}, indent=2))
    sys.exit(1 if findings else 0)


if __name__ == "__main__":
    main()
