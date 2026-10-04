#!/usr/bin/env python3
"""Full schema-canonicalization pass over a property-block markdown graph.
Dry-run by default; --apply to write. Take a backup separately before --apply.

Usage: schema-pass.py GRAPH_ROOT SCHEMA_CONFIG [--apply]

All canonicalization maps come from SCHEMA_CONFIG (JSON): type/status variant
merging, author->writer rename, drop-generic-type rules, global replacements.
Pure stdlib; no graph-specific content hardcoded.
"""
import argparse, json, os, re, sys

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

CANONICALIZATION = SCHEMA.get("canonicalization", {})
CANON = CANONICALIZATION.get("type", {})
STATUS = CANONICALIZATION.get("status", {})
WRITERS = tuple(SCHEMA.get("writer_vocab_plain", []))
ZOTERO_IT = set(SCHEMA.get("zotero_itemtypes", []))
DROP_WHEN = SCHEMA.get("drop_type_when_specific_present", {})
GLOBAL_REPL = SCHEMA.get("global_replacements", {})
SKIP_DIRS = (".obsidian", "assets", "copilot")

def process(text):
    lines = text.splitlines(keepends=True)
    # pass 1: transform lines
    typed = []   # collect canonical type values present, to resolve generic-type drops
    out = []
    for ln in lines:
        nl = ln.rstrip("\n")
        m = re.match(r'^(\s*-?\s*)(?:[0-9]*)(block-type|item-type|type):: (.+?)\s*$', nl)
        if m:
            indent, prop, val = m.groups()
            low = re.sub(r'\s+', ' ', val.strip()).lower()
            if prop == "item-type" and low in ZOTERO_IT:
                out.append(ln); continue
            canon = CANON.get(low, re.sub(r'\s+', ' ', val.strip()).title())
            typed.append(canon)
            out.append(f"{indent}type:: {canon}\n"); continue
        m = re.match(r'^(\s*-?\s*)([Ss]tatus):: (.+?)\s*$', nl)
        if m:
            indent, _, val = m.groups()
            low = val.strip().lower()
            if low in STATUS:
                out.append(f"{indent}status:: {STATUS[low]}\n"); continue
            out.append(f"{indent}status:: {val.strip()}\n"); continue  # leave odd values, fix name case
        m = re.match(r'^(\s*-?\s*)([Ss]ource):: (.+)$', nl)
        if m and m.group(2) == "Source":
            out.append(f"{m.group(1)}source:: {m.group(3)}\n"); continue
        m = re.match(r'^(\s*-?\s*)author:: (.+?)\s*$', nl)
        if m:
            v = m.group(2).strip()
            if v in WRITERS or v.startswith("[["):
                out.append(f"{m.group(1)}writer:: {v}\n"); continue
        out.append(ln)
    text2 = "".join(out)
    # pass 2: drop a generic type when a configured specific type is also present
    for generic, specifics in DROP_WHEN.items():
        if generic in typed and any(s in typed for s in specifics):
            text2 = "".join(l for l in text2.splitlines(keepends=True)
                            if not re.match(rf'^\s*-?\s*type:: {re.escape(generic)}\s*$', l))
    # global replacements (e.g. project-name unification)
    for old, new in GLOBAL_REPL.items():
        text2 = text2.replace(old, new)
    return text2

stats = {"files": 0}
for base, dirs, files in os.walk(PAGES):
    dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
    for f in files:
        if not f.endswith(".md"):
            continue
        p = os.path.join(base, f)
        s = open(p, encoding="utf-8").read()
        n = process(s)
        if n != s:
            stats["files"] += 1
            if args.apply:
                open(p, "w", encoding="utf-8").write(n)
            print(("normalized " if args.apply else "would change ") + os.path.relpath(p, G))
print(f"{'APPLIED to' if args.apply else 'DRY: would change'} {stats['files']} files")
