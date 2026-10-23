#!/usr/bin/env python3
"""
graph-link-audit.py — link, collision, and empty-property audit for a
property-block markdown graph (Logseq-format pages that are also an Obsidian vault).

Usage:
  graph-link-audit.py GRAPH_ROOT SCHEMA_CONFIG [--pages-dir DIR] [--links-only] [--json] [--quiet]
  graph-link-audit.py GRAPH_ROOT SCHEMA_CONFIG --apply-safe-fixes   # write safe fixes

Categories found (safe-fixable marked *):
  should-be-linked*        plain link-property value whose target page exists -> wrap in [[...]]
  dangling-bracketed-link* [[bracketed]] link-property value whose target does not exist -> unbracket
  dangling-link*           [[bracketed]] link in body prose, in a property value whose key is not a
                           link-type property, or inside one comma-separated element of a link-type property
                           value that holds more than one link or other text, whose target does not exist -> unbracket
                           (same rule as dangling-bracketed-link, same location-independent rationale —
                           a dangling bracket risks the graph app creating a phantom page wherever it sits)
  empty-property-value*    a `key:: ` line with no value (an explicit blank override in Logseq) -> delete line
                           (except a blank writer::, kept because graph_audit.py reports it as a template placeholder, and
                           every blank property line on a template page)
  bold-markdown*           any **bold** text anywhere -> strip the ** markers, keep the plain text
                           (unconditional: no bold formatting anywhere in this graph, ever — confirmed
                           2026-08-11. Distinct from schema-lint's inline-bold-heading, which is a
                           SEPARATE report-only judgment call about whether a bold-plus-dash line was
                           structurally meant as a heading; this fix never restructures, only strips **)
  title-collision          same title/filename/alias (case-insensitive) on 2+ files (report-only)
  blank-title-collision    2+ files each carrying a valueless title:: line (report-only; an --apply-safe-fixes run
                           deletes those lines, so it reports only those left on template pages)

The bracket rule is existence-conditional and location-independent: any [[bracketed]]
link — property value or body prose — is unbracketed when its target does not exist,
whichever location it is in, because the phantom-page-creation risk is identical either way.
The links this script leaves alone are listed in references/rules.md, rule Bracket rule.
A plain (unbracketed) link-property value is wrapped in [[...]] only when its target
demonstrably exists.

Default is report-only. --apply-safe-fixes writes ONLY the five starred categories.
Content inside fenced code blocks (```...```) is never scanned or modified.
Exit code = number of files with findings, capped at 255; also 255 when no file was scanned
(a stderr line says so). Pure stdlib.
"""
import argparse, json, os, re, sys
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # also runs under python3 -I, which leaves the script folder off the path
from _common import FENCE_OPEN_RE

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
ap.add_argument("--quiet", action="store_true", help="accepted for symmetry with schema-lint.py; this script prints no per-file OK lines")
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
    # a journals folder inside PAGES (e.g. pages_dir "." for a flat vault) is walked with PAGES already
    if os.path.isdir(journals) and os.path.commonpath([os.path.normpath(journals), PAGES]) != PAGES:
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
                names.add(val.strip('"'))     # same reading as graph_audit.py
        elif key == "alias":
            for v in split_values(val):
                names.add(v.strip("[]"))
    for n in names:
        index.setdefault(n.lower(), set()).add(rel)

# attachment names ([[photo.png]]): every file name under the pages folder and the graph's assets folders
file_names = set()
for top in {PAGES, os.path.join(G, "assets")}:
    for _base, _dirs, _files in os.walk(top):
        file_names.update(f.lower() for f in _files)

def template_path(path):
    """A template page: under a Templates folder of the pages folder, or named "... Template"."""
    return "Templates" in os.path.relpath(path, PAGES).split(os.sep)[:-1] or os.path.splitext(os.path.basename(path))[0].endswith(" Template")

TEMPLATE_PAGE = False   # set per page: a template's links are placeholders, so none of them is dangling

def exists(name):
    # an Obsidian link may carry a display alias ([[Page|alias]]) or a heading ([[Page#Heading]]);
    # [[#Heading]] points into the same page, and [[file.ext]] may name an attachment
    page = name.split("|")[0].split("#")[0].strip().lower()
    return TEMPLATE_PAGE or page == "" or page in index or page in file_names

def unbracket_dangling(text, rel, lineno, where):
    """Unbracket every [[link]] in text whose target does not exist (a URL or a namespaced "/" link
    is left alone) and report each as a dangling-link finding; returns the new text."""
    edits = []
    for mm in WIKI_RE.finditer(mask_inline_code(text)):
        target = mm.group(1)
        if target.startswith("http") or "/" in target:
            continue
        if not exists(target):
            add(rel, lineno, "dangling-link", f"{where} link [[{target}]] — target does not exist; unbracket")
            edits.append((mm.start(), mm.end(), plain_text(target)))
    for start, end, repl in sorted(edits, key=lambda r: -r[0]):
        text = text[:start] + repl + text[end:]
    return text

def plain_text(target):
    """What an unbracketed [[target|alias]] reads as: the alias if there is one, else the target."""
    return target.split("|", 1)[1].strip() if "|" in target else target

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
    is_template_page = template_path(p)
    TEMPLATE_PAGE = is_template_page
    fixes = {}                   # lineno(0-based) -> replacement line text (deleted lines are in `deletes`)
    deletes = set()
    in_fence = False
    fence_re = FENCE_OPEN_RE   # Logseq bullets prefix fences with "- ```"
    for i, l in enumerate(raw_lines):
        if fence_re.match(l):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = PROP_RE.match(l) if not args.links_only else None
        if m:
            indent, key, _sp, val = m.group(1), m.group(2), m.group(3), m.group(4)
            if val == "" and (key == "writer" or is_template_page):
                # a blank writer:: is the template placeholder graph_audit.py reports (blank-writer), and a
                # template page keeps all its blank property lines; never delete them
                continue
            if val == "":
                add(rel, i + 1, "empty-property-value",
                    f"{key}:: line has no value (explicit blank override) — delete the line",
                    fixed_line="<delete>")
                deletes.add(i)
                continue
            prop_line_changed = False
            masked_val = mask_inline_code(val)   # bold inside inline code is example text, as in body prose
            bold_spans = list(BOLD_RE.finditer(masked_val))
            if bold_spans:
                pieces, prev = [], 0
                for mm in bold_spans:
                    inner = val[mm.start(1):mm.end(1)]
                    add(rel, i + 1, "bold-markdown",
                        f"**{inner}** in {key}:: value — no bold formatting anywhere in this graph; strip the ** markers")
                    pieces.append(val[prev:mm.start()] + inner)
                    prev = mm.end()
                val = "".join(pieces) + val[prev:]
                prop_line_changed = True
            if key in LINK_PROPS:
                vals = split_values(val)
                new_vals, changed = [], False
                for v in vals:
                    mm = re.fullmatch(r'\[\[([^\[\]]+)\]\]', v)   # one link only: "[[A]] [[B]]" is not a single target
                    if mm:
                        target = mm.group(1)
                        if not exists(target) and not target.startswith("http") and "/" not in target:
                            add(rel, i + 1, "dangling-bracketed-link",
                                f"{key}:: [[{target}]] — target does not exist; unbracket")
                            new_vals.append(plain_text(target)); changed = True
                        else:
                            new_vals.append(v)
                    else:
                        if v.lower() in index:   # plain text: exact name match only
                            add(rel, i + 1, "should-be-linked",
                                f"{key}:: {v} — target page exists; bracket it")
                            new_vals.append(f"[[{v}]]"); changed = True
                        else:
                            # a compound element such as "[[A]] [[B]]" or "[[A]] (draft)": unbracket its dangling links
                            fixed_v = unbracket_dangling(v, rel, i + 1, f"{key}:: value")
                            new_vals.append(fixed_v); changed = changed or fixed_v != v
                if changed:
                    prop_line_changed = True
                    val = ", ".join(new_vals)
            else:
                # not a link-type property: the dangling-bracket rule is location-independent, so
                # it applies to this value exactly as it does to body prose
                new_val = unbracket_dangling(val, rel, i + 1, f"{key}:: value")
                if new_val != val:
                    val, prop_line_changed = new_val, True
            if prop_line_changed:
                fixes[i] = f"{indent}{key}:: {val}"
                # record the fixed line on each finding for this line
                for fnd in findings:
                    if fnd["file"] == rel and fnd["line"] == i + 1 and fnd["fixed_line"] is None:
                        fnd["fixed_line"] = fixes[i]
            continue
        # body prose: bold markdown (strip-always), then dangling bracketed links (unbracket-always).
        # Two passes, each against its own masked (code-blind) line, so a link inside bold
        # (**[[Gone]]**) is first unbolded and then found and unbracketed at its new offsets.
        newl = l
        bold_edits = []
        # bold is a format-contract rule of a declared-schema graph; a plain vault (--links-only) has none
        for mm in (BOLD_RE.finditer(mask_inline_code(newl)) if not args.links_only else []):
            add(rel, i + 1, "bold-markdown",
                f"**{mm.group(1)}** — no bold formatting anywhere in this graph; strip the ** markers")
            bold_edits.append((mm.start(), mm.end(), newl[mm.start(1):mm.end(1)]))   # text from the real line, not the masked one
        for start, end, repl in sorted(bold_edits, key=lambda r: -r[0]):
            newl = newl[:start] + repl + newl[end:]
        newl = unbracket_dangling(newl, rel, i + 1, "body")
        if newl != l:
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
if args.apply_safe_fixes:      # an apply run deletes the blank title:: lines, except on template pages
    blank_title_files = [f for f in blank_title_files if template_path(os.path.join(G, f))]
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
