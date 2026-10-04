#!/usr/bin/env python3
"""
graph-heading-extract.py — convert bold-labeled bullets with no heading:: true
ancestor into real heading:: true structure: the label becomes its own bullet
(debolded) with heading:: true on a child line, and the original same-line
content becomes a separate, further-indented child bullet.

This is a STRUCTURAL change (adds an indentation level), distinct from the
text-only safe-fixes in graph-link-audit.py — dry-run by default, always;
--apply required explicitly, and even then only touches lines this script can
confidently split (see "Skipped" below).

Usage:
  graph-heading-extract.py GRAPH_ROOT [--pages-dir DIR] [--apply] [--json]

A bullet is a CANDIDATE when:
  - it starts with **bold** (immediately after "- ", or "- " + optional list marker)
  - it has NO heading:: true ancestor already governing it (already-nested bold
    is graph-link-audit.py's bold-markdown job — plain debold, no restructuring)
  - there is non-empty text remaining on the SAME line after the closing **

When the bold span wraps to the end of the line with nothing left over, there
are two distinct cases:
  - the very next line is ALREADY a deeper-indented (child) bullet — the
    content is already correctly nested, nothing needs re-indenting; this
    converts too (debold + heading:: true added, structure untouched)
  - otherwise, the "content" most likely lives in FOLLOWING SIBLING bullets,
    which would need to be re-indented under the new heading; deciding where
    that block ends is a judgment call this script does not make — SKIPPED,
    report-only

A bullet is also SKIPPED when the bold is not at the start of the bullet
(mid-sentence emphasis — nothing to extract as a label; graph-link-audit.py's
bold-markdown already debolds it).

Label cleanup: a single trailing "." or ":" on the label is stripped (cleaner
heading title). Content cleanup: a leading em/en dash or hyphen + space
(the old inline separator) is stripped; no separator is invented if one wasn't
there (e.g. bibliography entries where content starts directly with "(1996)").
Pure stdlib.
"""
import argparse, json, os, re, sys
from collections import defaultdict

ap = argparse.ArgumentParser()
ap.add_argument("graph_root")
ap.add_argument("--pages-dir", default="pages")
ap.add_argument("--apply", action="store_true", help="write changes (default: dry-run report only)")
ap.add_argument("--json", action="store_true", dest="as_json")
args = ap.parse_args()

G = os.path.abspath(args.graph_root)
PAGES = os.path.normpath(os.path.join(G, args.pages_dir))
if not os.path.isdir(PAGES):
    sys.exit(f"error: {PAGES} not found — is this a valid graph root?")
SKIP_DIRS = (".obsidian", "assets", "copilot", "logseq", ".recycle", "bak", ".trash")

BULLET_RE = re.compile(r'^(\t*)-\s(.*)$')
BOLD_START_RE = re.compile(r'^\*\*([^*]+)\*\*(.*)$')
FENCE_RE = re.compile(r'^\s*-?\s*```')
PROP_RE = re.compile(r'^\s*[a-z][a-z.-]*:: ')

def md_files():
    out = []
    for base, dirs, files in os.walk(PAGES):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in sorted(files):
            if f.endswith(".md"):
                out.append(os.path.join(base, f))
    return out

def clean_label(label):
    label = label.strip()
    if label.endswith(('.', ':')):
        label = label[:-1].rstrip()
    return label

def clean_content(content):
    content = content.strip()
    m = re.match(r'^[—–-]\s+(.*)$', content)
    if m:
        content = m.group(1)
    return content.strip()

results = []   # {file, line, kind: "convert"|"skip-no-content"|"skip-mid-sentence", label, content, old, new}

for p in md_files():
    rel = os.path.relpath(p, G)
    try:
        raw = open(p, encoding="utf-8").read()
    except (UnicodeDecodeError, OSError):
        continue
    lines = raw.split("\n")
    in_fence = False
    edits = []   # (line_idx, [new_line(s)])
    for i, l in enumerate(lines):
        if FENCE_RE.match(l):
            in_fence = not in_fence
            continue
        if in_fence or PROP_RE.match(l):
            continue
        m = BULLET_RE.match(l)
        if not m:
            continue
        indent, body = m.group(1), m.group(2)
        bm = BOLD_START_RE.match(body)
        if not bm:
            continue  # not start-of-bullet bold — mid-sentence emphasis, graph-link-audit's job
        # check for a heading:: true ancestor
        tlevel = len(indent)
        has_heading_ancestor = False
        for j in range(i - 1, -1, -1):
            aj = BULLET_RE.match(lines[j])
            if not aj:
                continue
            if len(aj.group(1)) < tlevel:
                if j + 1 < len(lines) and "heading:: true" in lines[j + 1]:
                    has_heading_ancestor = True
                break
        if has_heading_ancestor:
            continue  # already correctly nested — bold-markdown handles the debold
        label = clean_label(bm.group(1))
        content = clean_content(bm.group(2))
        if not content:
            next_bullet = BULLET_RE.match(lines[i + 1]) if i + 1 < len(lines) else None
            has_existing_child = bool(next_bullet and len(next_bullet.group(1)) > tlevel)
            if not has_existing_child:
                results.append({"file": rel, "line": i + 1, "kind": "skip-no-content",
                                "detail": f"bold wraps to end of line, no same-line content AND "
                                          f"no existing child bullet below — content likely lives "
                                          f"in following SIBLING bullets; needs manual review, not "
                                          f"auto-converted (would require re-indenting an unknown "
                                          f"range of siblings)",
                                "old": l.strip()[:120]})
                continue
            # existing child bullet(s) already correctly nested — just debold + add heading:: true,
            # no re-indenting needed
            new_lines = [f"{indent}- {label}", f"{indent}  heading:: true"]
        else:
            new_lines = [f"{indent}- {label}", f"{indent}  heading:: true", f"{indent}\t- {content}"]
        results.append({"file": rel, "line": i + 1, "kind": "convert",
                        "label": label, "content": content[:100],
                        "old": l.strip()[:120], "new": new_lines})
        edits.append((i, new_lines))
    if args.apply and edits:
        new_all = []
        edit_map = dict(edits)
        for i, l in enumerate(lines):
            if i in edit_map:
                new_all.extend(edit_map[i])
            else:
                new_all.append(l)
        open(p, "w", encoding="utf-8").write("\n".join(new_all))

convert = [r for r in results if r["kind"] == "convert"]
skipped = [r for r in results if r["kind"] != "convert"]

if args.as_json:
    print(json.dumps({"graph_root": G, "convert_count": len(convert), "skip_count": len(skipped),
                      "applied": args.apply, "results": results}, indent=2))
else:
    by_file = defaultdict(list)
    for r in results:
        by_file[r["file"]].append(r)
    for f in sorted(by_file):
        print(f"\n{f}")
        for r in by_file[f]:
            if r["kind"] == "convert":
                tag = "[CONVERTED]" if args.apply else "[would convert]"
                print(f"  L{r['line']} {tag}")
                print(f"    old: {r['old']}")
                if not args.apply:
                    for nl in r["new"]:
                        print(f"    new: {nl}")
            else:
                print(f"  L{r['line']} [SKIPPED — needs manual review] {r['detail']}")
                print(f"    line: {r['old']}")
    print(f"\n{'CONVERTED' if args.apply else 'would convert'} {len(convert)} bullet(s) into heading:: true structure")
    print(f"SKIPPED {len(skipped)} bullet(s) — no same-line content, needs manual review")
    if not args.apply:
        print("dry-run — re-run with --apply to write")

sys.exit(0)
