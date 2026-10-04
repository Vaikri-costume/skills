#!/usr/bin/env python3
"""
Occasional property-value cleanup for a property-block markdown graph.
- Property NAMES stay lowercase (type::, writer::, status::).
- Property VALUES are Title Case (values include name-like categories).
- Folds retired block-type:: and item-type:: values into a single type::.
- Leaves Zotero's item-type:: values (journalArticle/book...) untouched.
Dry-run by default; --apply to write. Pure stdlib.

Usage: property-normalize.py GRAPH_ROOT SCHEMA_CONFIG [--apply]
Canonical type map + Zotero item types come from SCHEMA_CONFIG (JSON).
"""
import argparse, difflib, json, os, re, sys

ap = argparse.ArgumentParser()
ap.add_argument("graph_root")
ap.add_argument("schema_config", help="path to a schema JSON file, e.g. assets/example-schema.json")
ap.add_argument("--apply", action="store_true", help="write changes (default is dry-run)")
args = ap.parse_args()

G = os.path.abspath(args.graph_root)
PAGES = os.path.join(G, "pages")
if not os.path.isdir(PAGES):
    sys.exit(f"error: {G}/pages not found — is this a valid graph root?")
SCHEMA = json.load(open(args.schema_config, encoding="utf-8"))

VAR2CANON = SCHEMA["canonicalization"]["type"]
ZOTERO_ITEMTYPES = set(SCHEMA["zotero_itemtypes"])
SKIP_DIRS = (".obsidian", "assets", "copilot")

def canon_value(val):
    key = re.sub(r'\s+', ' ', val.strip()).lower()
    if key in VAR2CANON:
        return VAR2CANON[key]
    # unknown value: Title-Case it (keeps a name-like value tidy) but don't invent merges
    return re.sub(r'\s+', ' ', val.strip()).title()

def normalize(text):
    out = []
    for line in text.splitlines(keepends=True):
        m = re.match(r'^(\s*-?\s*)(block-type|item-type|type):: (.+?)\s*$', line)
        if not m:
            out.append(line); continue
        indent, prop, val = m.groups()
        if prop == "item-type" and val.strip().lower() in ZOTERO_ITEMTYPES:
            out.append(line); continue          # Zotero's item-type — leave alone
        out.append(f"{indent}type:: {canon_value(val)}\n")
    return "".join(out)

changed = 0
for base, dirs, files in os.walk(PAGES):
    dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
    for f in files:
        if not f.endswith(".md"):
            continue
        p = os.path.join(base, f)
        s = open(p, encoding="utf-8").read()
        n = normalize(s)
        if n != s:
            changed += 1
            rel = os.path.relpath(p, G)
            if args.apply:
                open(p, "w", encoding="utf-8").write(n); print("normalized", rel)
            else:
                sys.stdout.writelines(difflib.unified_diff(
                    s.splitlines(keepends=True), n.splitlines(keepends=True),
                    fromfile=f"a/{rel}", tofile=f"b/{rel}", n=0))
print(f"\n{'APPLIED to' if args.apply else 'DRY RUN — would change'} {changed} file(s)."
      f"{'' if args.apply else '  Re-run with --apply to write.'}")
