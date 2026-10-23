#!/usr/bin/env python3
"""
Occasional property-value cleanup for a property-block markdown graph.
- Property NAMES stay lowercase (type::, writer::, status::).
- type:: VALUES are mapped through SCHEMA_CONFIG's canonicalization.type; an unmapped value
  is Title-Cased unless it is already in the schema's type vocabulary (values include name-like categories); other properties are untouched.
- A comma-separated type:: value is canonicalized part by part.
- Renames each retired block-type:: and item-type:: line to a type:: line (it does not merge
  two lines into one; a page left with two type:: lines is for the user to merge).
- Leaves Zotero's item-type:: values (journalArticle/book...) untouched.
Dry-run by default; --apply to write. Pure stdlib.

Usage: property-normalize.py GRAPH_ROOT SCHEMA_CONFIG [--apply]
Canonical type map + Zotero item types come from SCHEMA_CONFIG (JSON).
"""
import argparse, difflib, json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # also runs under python3 -I, which leaves the script folder off the path
from _common import FENCE_OPEN_RE

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

TYPE_VOCAB = set(SCHEMA.get("type_vocab", []))   # an unmapped value that is already in the vocabulary is kept as it is
VAR2CANON = SCHEMA.get("canonicalization", {}).get("type", {})
ZOTERO_ITEMTYPES = {t.lower() for t in SCHEMA.get("zotero_itemtypes", [])}   # compared with a lowercased page value
SKIP_DIRS = (".obsidian", "assets", "copilot", "logseq", ".recycle", "bak", ".trash")   # same list as graph-link-audit.py

def canon_value(val):
    # type:: is array-capable (comma-separated): canonicalize each part on its own
    out = []
    for part in val.split(","):
        if not part.strip():
            continue
        clean = re.sub(r'\s+', ' ', part.strip())
        # unknown value: Title-Case it (keeps a name-like value tidy) but don't invent merges
        out.append(VAR2CANON.get(clean.lower(), clean if clean in TYPE_VOCAB else clean.title()))
    return ", ".join(out)

def normalize(text):
    out = []
    in_fence = False
    for line in text.splitlines(keepends=True):
        if FENCE_OPEN_RE.match(line):   # fenced code holds examples: never rewritten
            in_fence = not in_fence
            out.append(line); continue
        if in_fence:
            out.append(line); continue
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
