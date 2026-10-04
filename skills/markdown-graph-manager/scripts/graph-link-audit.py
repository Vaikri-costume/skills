#!/usr/bin/env python3
"""
graph-link-audit.py — link, collision, and empty-property audit for a
property-block markdown graph (Logseq-format pages that are also an Obsidian vault).

Usage:
  graph-link-audit.py GRAPH_ROOT SCHEMA_CONFIG [--pages-dir DIR] [--json] [--quiet]
  graph-link-audit.py GRAPH_ROOT SCHEMA_CONFIG --apply-safe-fixes   # write safe fixes

Categories found (safe-fixable marked *):
  should-be-linked*        plain link-property value whose target page exists -> wrap in [[...]]
  dangling-bracketed-link* [[bracketed]] link-property value whose target does not exist -> unbracket, always
  dangling-link*           [[bracketed]] link in body prose whose target does not exist -> unbracket, always
                           (same rule as dangling-bracketed-link, same location-independent rationale —
                           a dangling bracket risks the graph app creating a phantom page wherever it sits)
  empty-property-value*    a `key:: ` line with no value (an explicit blank override in Logseq) -> delete line
  bold-markdown*           any **bold** text anywhere -> strip the ** markers, keep the plain text
                           (unconditional: no bold formatting anywhere in this graph, ever — confirmed
                           2026-08-11. Distinct from schema-lint's inline-bold-heading, which is a
                           SEPARATE report-only judgment call about whether a bold-plus-dash line was
                           structurally meant as a heading; this fix never restructures, only strips **)
  title-collision          same title/filename/alias (case-insensitive) on 2+ files (report-only)
  blank-title-collision    2+ files each carrying a valueless title:: line (report-only)

The bracket rule is existence-conditional and location-independent: any [[bracketed]]
link — property value or body prose — is unbracketed when its target does not exist,
always, no exceptions, because the phantom-page-creation risk is identical either way.
A plain (unbracketed) link-property value is wrapped in [[...]] only when its target
demonstrably exists.

Default is report-only. --apply-safe-fixes writes ONLY the four starred categories.
Content inside fenced code blocks (```...```) is never scanned or modified.
Exit code = number of files with findings, capped at 255. Pure stdlib.
"""
import argparse, json, os, re, sys
from collections import defaultdict

ap = argparse.ArgumentParser()
ap.add_argument("graph_root")
ap.add_argument("schema_config", help="path to a schema JSON file, e.g. assets/example-schema.json")
ap.add_argument("--pages-dir", default="pages", help="pages directory relative to graph root (default: pages; use . for a flat vault)")
ap.add_argument("--links-only", action="store_true",
                help="dangling-link reporting only — for a graph with NO declared schema/format contract "
                     "(plain Obsidian vault): property bracket rules, empty-property checks, and title "
                     "collisions don't apply there and would be false positives")
ap.add_argument("--apply-safe-fixes", action="store_true", help="write the safe-fix subset (default: report only)")
ap.add_argument("--json", action="store_true", dest="as_json", help="machine-readable JSON output")
ap.add_argument("--quiet", action="store_true", help="suppress per-file OK lines")
args = ap.parse_args()

G = os.path.abspath(args.graph_root)
PAGES = os.path.normpath(os.path.join(G, args.pages_dir))
if not os.path.isdir(PAGES):
    sys.exit(f"error: {PAGES} not found — is this a valid graph root?")
SCHEMA = json.load(open(args.schema_config, encoding="utf-8"))
LINK_PROPS = set(SCHEMA.get("link_type_properties", []))
SKIP_DIRS = (".obsidian", "assets", "copilot", "logseq", ".recycle", "bak", ".trash")

PROP_RE = re.compile(r'^(\s*-?\s*)([a-z][a-z.-]*)::(\s*)(.*?)\s*$')
WIKI_RE = re.compile(r'\[\[([^\[\]]+)\]\]')
BOLD_RE = re.compile(r'\*\*([^*]+)\*\*')

def md_files():
    dirs_to_walk = [PAGES]
    journals = os.path.join(G, "journals")
    if os.path.isdir(journals) and os.path.normpath(journals) != PAGES:
        dirs_to_walk.append(journals)
    out = []
    for top in dirs_to_walk:
        for base, dirs, files in os.walk(top):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for f in sorted(files):
                if f.endswith(".md"):
                    out.append(os.path.join(base, f))
    return out

def mask_inline_code(line):
    """Blank out inline `code` spans while preserving length/positions, so bracket
    matches found in the masked line map to the same offsets in the real line."""
    return re.sub(r'`[^`]*`', lambda m: '`' * len(m.group(0)), line)

def split_values(s):
    """Split a comma-separated property value, ignoring commas inside [[...]]."""
    out, buf, depth = [], "", 0
    i = 0
    while i < len(s):
        two = s[i:i+2]
        if two == "[[":
            depth += 1; buf += two; i += 2; continue
        if two == "]]" and depth:
            depth -= 1; buf += two; i += 2; continue
        ch = s[i]
        if ch == "," and depth == 0:
            out.append(buf); buf = ""
        else:
            buf += ch
        i += 1
    out.append(buf)
    return [v.strip() for v in out if v.strip()]

FILES = md_files()

# ---- pass 1: build the case-insensitive title/filename/alias index ----
index = {}                       # lower name -> set of files it identifies
blank_title_files = []
for p in FILES:
    rel = os.path.relpath(p, G)
    stem = os.path.splitext(os.path.basename(p))[0]
    names = {stem}
    try:
        raw = open(p, encoding="utf-8").read()
    except (UnicodeDecodeError, OSError):
        continue
    lines = raw.split("\n")
    first_bullet = next((i for i, l in enumerate(lines) if l.startswith("- ")), len(lines))
    for l in lines[:first_bullet]:
        m = PROP_RE.match(l)
        if not m:
            continue
        key, val = m.group(2), m.group(4)
        if key == "title":
            if val == "":
                blank_title_files.append(rel)
            else:
                names.add(val)
        elif key == "alias":
            for v in split_values(val):
                names.add(v.strip("[]"))
    for n in names:
        index.setdefault(n.lower(), set()).add(rel)

def exists(name):
    return name.lower() in index

# ---- pass 2: per-file findings ----
findings = []                    # {file, line, category, detail, fixed_line or None}
files_with_findings = set()

def add(rel, lineno, cat, detail, fixed_line=None):
    findings.append({"file": rel, "line": lineno, "category": cat,
                     "detail": detail, "fixed_line": fixed_line})
    files_with_findings.add(rel)

for p in FILES:
    rel = os.path.relpath(p, G)
    try:
        raw = open(p, encoding="utf-8").read()
    except (UnicodeDecodeError, OSError):
        continue
    raw_lines = raw.split("\n")
    fixes = {}                   # lineno(0-based) -> new line text ("" sentinel means delete? no: None)
    deletes = set()
    in_fence = False
    fence_re = re.compile(r'^\s*-?\s*```')   # Logseq bullets prefix fences with "- ```"
    for i, l in enumerate(raw_lines):
        if fence_re.match(l):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = PROP_RE.match(l) if not args.links_only else None
        if m:
            indent, key, _sp, val = m.group(1), m.group(2), m.group(3), m.group(4)
            if val == "":
                add(rel, i + 1, "empty-property-value",
                    f"{key}:: line has no value (explicit blank override) — delete the line",
                    fixed_line="<delete>")
                deletes.add(i)
                continue
            prop_line_changed = False
            if BOLD_RE.search(val):
                for mm in BOLD_RE.finditer(val):
                    add(rel, i + 1, "bold-markdown",
                        f"**{mm.group(1)}** in {key}:: value — no bold formatting anywhere in this graph; strip the ** markers")
                val = BOLD_RE.sub(lambda m: m.group(1), val)
                prop_line_changed = True
            if key in LINK_PROPS:
                vals = split_values(val)
                new_vals, changed = [], False
                for v in vals:
                    mm = re.fullmatch(r'\[\[(.+)\]\]', v)
                    if mm:
                        target = mm.group(1)
                        if not exists(target) and not target.startswith("http"):
                            add(rel, i + 1, "dangling-bracketed-link",
                                f"{key}:: [[{target}]] — target does not exist; unbracket")
                            new_vals.append(target); changed = True
                        else:
                            new_vals.append(v)
                    else:
                        if exists(v):
                            add(rel, i + 1, "should-be-linked",
                                f"{key}:: {v} — target page exists; bracket it")
                            new_vals.append(f"[[{v}]]"); changed = True
                        else:
                            new_vals.append(v)
                if changed:
                    prop_line_changed = True
                    val = ", ".join(new_vals)
            if prop_line_changed:
                fixes[i] = f"{indent}{key}:: {val}"
                # record the fixed line on each finding for this line
                for fnd in findings:
                    if fnd["file"] == rel and fnd["line"] == i + 1 and fnd["fixed_line"] is None:
                        fnd["fixed_line"] = fixes[i]
            continue
        # body prose: dangling bracketed links (unbracket-always) + bold markdown (strip-always).
        # Both computed against the same masked (code-blind) line and merged into one set of
        # (start, end, replacement) edits so they compose correctly when both occur on one line.
        masked = mask_inline_code(l)
        replacements = []
        for mm in WIKI_RE.finditer(masked):
            target = mm.group(1)
            if target.startswith("http") or "/" in target:
                continue     # URLs handled elsewhere; namespaced links are schema-lint's finding
            if not exists(target):
                add(rel, i + 1, "dangling-link",
                    f"body link [[{target}]] — target does not exist; unbracket")
                replacements.append((mm.start(), mm.end(), target))
        for mm in BOLD_RE.finditer(masked):
            add(rel, i + 1, "bold-markdown",
                f"**{mm.group(1)}** — no bold formatting anywhere in this graph; strip the ** markers")
            replacements.append((mm.start(), mm.end(), mm.group(1)))
        if replacements:
            newl = l
            for start, end, repl in sorted(replacements, key=lambda r: -r[0]):
                newl = newl[:start] + repl + newl[end:]
            fixes[i] = newl
            for fnd in findings:
                if fnd["file"] == rel and fnd["line"] == i + 1 and fnd["category"] in ("dangling-link", "bold-markdown") and fnd["fixed_line"] is None:
                    fnd["fixed_line"] = newl
    # apply safe fixes for this file
    if args.apply_safe_fixes and (fixes or deletes):
        new_lines = [fixes.get(i, l) for i, l in enumerate(raw_lines) if i not in deletes]
        open(p, "w", encoding="utf-8").write("\n".join(new_lines))

# ---- pass 3: collisions (only meaningful under a global-uniqueness format contract) ----
for name, owners in (sorted(index.items()) if not args.links_only else []):
    if len(owners) > 1:
        detail = f"'{name}' identifies {len(owners)} files: " + "; ".join(sorted(owners))
        for o in sorted(owners):
            files_with_findings.add(o)
        findings.append({"file": sorted(owners)[0], "line": 0,
                         "category": "title-collision", "detail": detail, "fixed_line": None})
if len(blank_title_files) > 1 and not args.links_only:
    findings.append({"file": blank_title_files[0], "line": 0, "category": "blank-title-collision",
                     "detail": f"{len(blank_title_files)} files carry a valueless title:: line and fight "
                               f"for the same blank identity: " + "; ".join(blank_title_files),
                     "fixed_line": None})
    files_with_findings.update(blank_title_files)

# ---- report ----
SAFE = {"should-be-linked", "dangling-bracketed-link", "dangling-link", "empty-property-value", "bold-markdown"}
counts = defaultdict(int)
for f in findings:
    counts[f["category"]] += 1

if args.as_json:
    print(json.dumps({"graph_root": G, "files_scanned": len(FILES),
                      "files_with_findings": len(files_with_findings),
                      "counts": dict(counts), "applied_safe_fixes": args.apply_safe_fixes,
                      "findings": findings}, indent=2))
else:
    by_cat = defaultdict(list)
    for f in findings:
        by_cat[f["category"]].append(f)
    for cat in sorted(by_cat):
        tag = " [safe-fix]" if cat in SAFE else " [report-only]"
        print(f"\n== {cat}{tag} — {len(by_cat[cat])} finding(s) ==")
        for f in by_cat[cat]:
            loc = f"{f['file']}:{f['line']}" if f["line"] else f["file"]
            print(f"  {loc}: {f['detail']}")
            if f["fixed_line"] and not args.apply_safe_fixes and f["fixed_line"] != "<delete>":
                print(f"    -> {f['fixed_line'].strip()}")
    print(f"\nscanned {len(FILES)} files; {len(files_with_findings)} with findings")
    if args.apply_safe_fixes:
        applied = sum(counts[c] for c in SAFE)
        print(f"APPLIED {applied} safe fix(es); {sum(counts.values()) - applied} finding(s) left for judgment")
    else:
        print("report-only run — re-run with --apply-safe-fixes to write the safe subset")

if len(FILES) == 0:
    print("!! 0 files scanned — target discovery is broken", file=sys.stderr)
    sys.exit(255)
sys.exit(min(len(files_with_findings), 255))
