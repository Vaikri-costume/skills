#!/usr/bin/env python3
"""
graph-colon-label-fix.py — convert confirmed single-colon pseudo-labels to
hyphen-separated form ("Label: value" -> "Label - value") at an EXPLICIT list
of (file, line) locations, never by blind pattern-match across the whole graph.

schema-lint.py's single-colon-pseudo-label check is report-only because the
same textual shape is also ordinary prose (citations, quote attributions,
sentence fragments) — only per-instance judgment (orchestrator or human)
separates a genuine pseudo-label from prose that merely looks like one. This
script is the write mechanism for whichever subset judgment has confirmed;
it is not itself a classifier.

Usage:
  graph-colon-label-fix.py GRAPH_ROOT INCLUDE_LIST.json [--apply]

INCLUDE_LIST.json: [{"file": "pages/X.md", "line": 12}, ...] (line = 1-based,
matching schema-lint.py's L<N> reporting). Each location is re-validated
against the current file content before writing (still matches the
single-colon-label shape, not already fixed) — mismatches are skipped and
reported, never forced.

Dry-run by default; --apply writes. Pure stdlib.
"""
import argparse, json, os, re, sys

ap = argparse.ArgumentParser()
ap.add_argument("graph_root")
ap.add_argument("include_list")
ap.add_argument("--apply", action="store_true")
args = ap.parse_args()

G = os.path.abspath(args.graph_root)
include = json.load(open(args.include_list, encoding="utf-8"))

LABEL_RE = re.compile(r"^(\s*-\s*)([A-Z][A-Za-z0-9 /'&,.()-]{1,50}?):(?!:)(\s+)(\S.*)$")

by_file = {}
for item in include:
    by_file.setdefault(item["file"], []).append(item["line"])

converted, skipped = [], []
for relfile, linenos in by_file.items():
    path = os.path.join(G, relfile)
    try:
        lines = open(path, encoding="utf-8").read().split("\n")
    except (UnicodeDecodeError, OSError, FileNotFoundError):
        for ln in linenos:
            skipped.append((relfile, ln, "file not readable"))
        continue
    changed = False
    for lineno in linenos:
        idx = lineno - 1
        if idx >= len(lines):
            skipped.append((relfile, lineno, "line out of range — file changed since analysis"))
            continue
        m = LABEL_RE.match(lines[idx])
        if not m:
            skipped.append((relfile, lineno, "no longer matches the pseudo-label shape — "
                                              "file changed since analysis, skipped for safety"))
            continue
        prefix, label, sep, rest = m.groups()
        lines[idx] = f"{prefix}{label} -{sep}{rest}"
        converted.append((relfile, lineno, label))
        changed = True
    if changed and args.apply:
        open(path, "w", encoding="utf-8").write("\n".join(lines))

print(f"{'CONVERTED' if args.apply else 'would convert'} {len(converted)} line(s)")
print(f"SKIPPED {len(skipped)} (re-validation failed — file changed since analysis)")
for f, ln, reason in skipped:
    print(f"  {f}:{ln}: {reason}")
if not args.apply:
    print("dry-run — re-run with --apply to write")
sys.exit(0)
