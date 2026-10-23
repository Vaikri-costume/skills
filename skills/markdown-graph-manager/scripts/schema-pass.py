#!/usr/bin/env python3
"""Full schema-canonicalization pass over a property-block markdown graph.
Dry-run by default; --apply to write. Take a backup separately before --apply.

Usage: schema-pass.py GRAPH_ROOT SCHEMA_CONFIG [--apply]

All canonicalization maps come from SCHEMA_CONFIG (JSON): type/status variant
merging, author->writer rename, drop-generic-type rules, global replacements.
It rewrites: type:: values (each comma-separated value mapped through the config,
an unmapped value Title-Cased unless it is in the schema's type vocabulary), status:: names and mapped values, `Source::` to
`source::`, a plain-writer or bracketed `author::` to `writer::` (not on a
Reading Notes or Primary Source page, where `author::` is a real property), the configured
generic-type drops, and the configured global string replacements (which run over the whole file
text, fenced code included). An item-type:: line holding a configured Zotero item type is left alone.
Pure stdlib; no vocabulary lists hardcoded (only the Reading Notes and Primary Source types, which keep
their author:: property).
"""
import argparse, json, os, re, sys
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

CANONICALIZATION = SCHEMA.get("canonicalization", {})
CANON = CANONICALIZATION.get("type", {})
STATUS = CANONICALIZATION.get("status", {})
TYPE_VOCAB = set(SCHEMA.get("type_vocab", []))   # an unmapped value that is already in the vocabulary is kept as it is
WRITERS = tuple(SCHEMA.get("writer_vocab_plain", []))
ZOTERO_IT = {t.lower() for t in SCHEMA.get("zotero_itemtypes", [])}   # compared with a lowercased page value
DROP_WHEN = SCHEMA.get("drop_type_when_specific_present", {})
GLOBAL_REPL = SCHEMA.get("global_replacements", {})
SKIP_DIRS = (".obsidian", "assets", "copilot", "logseq", ".recycle", "bak", ".trash")   # same list as graph-link-audit.py

def canon_types(val):
    """Canonicalize a type:: value; it is array-capable (comma-separated), so each part separately."""
    parts = [re.sub(r'\s+', ' ', v.strip()) for v in val.split(",") if v.strip()]
    return [CANON.get(v.lower(), v if v in TYPE_VOCAB else v.title()) for v in parts]

def process(text):
    lines = text.splitlines(keepends=True)
    page_types = set()   # canonical types of the page, so author:: handling can see them wherever type:: sits
    fence_re = FENCE_OPEN_RE   # Logseq bullets prefix fences with "- ```"
    in_fence = False
    for ln in lines:
        if fence_re.match(ln):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        mt = re.match(r'^(\s*-?\s*)(block-type|item-type|type):: (.+?)\s*$', ln.rstrip("\n"))
        if mt and not (mt.group(2) == "item-type" and mt.group(3).strip().lower() in ZOTERO_IT):
            page_types.update(canon_types(mt.group(3)))
    # pass 1: transform lines
    typed = []   # collect canonical type values present, to resolve generic-type drops
    out = []
    in_fence = False
    for ln in lines:
        nl = ln.rstrip("\n")
        if fence_re.match(nl):       # fenced code holds examples: never rewritten
            in_fence = not in_fence
            out.append(ln); continue
        if in_fence:
            out.append(ln); continue
        m = re.match(r'^(\s*-?\s*)(block-type|item-type|type):: (.+?)\s*$', nl)
        if m:
            indent, prop, val = m.groups()
            low = re.sub(r'\s+', ' ', val.strip()).lower()
            if prop == "item-type" and low in ZOTERO_IT:
                out.append(ln); continue
            canon = canon_types(val)
            if not indent:     # only a page-level type:: line decides a generic-type drop
                typed.extend(canon)
            out.append(f"{indent}type:: {', '.join(canon)}\n"); continue
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
            if (v in WRITERS or v.startswith("[[")) and not ({"Reading Notes", "Primary Source"} & page_types):
                out.append(f"{m.group(1)}writer:: {v}\n"); continue
        out.append(ln)
    text2 = "".join(out)
    # pass 2: drop a generic type when a configured specific type is also present
    for generic, specifics in DROP_WHEN.items():
        if generic in typed and any(s in typed for s in specifics):
            kept = []
            in_fence = False
            for l in text2.splitlines(keepends=True):
                if fence_re.match(l):
                    in_fence = not in_fence
                mt = re.match(r'^(\s*-?\s*)type:: (.+?)\s*$', l)
                if mt and not mt.group(1) and not in_fence:     # block-level exception types and fenced examples are left alone
                    parts = [t.strip() for t in mt.group(2).split(",")]
                    if generic in parts:
                        parts = [t for t in parts if t != generic]
                        if not parts:
                            continue
                        l = f"{mt.group(1)}type:: {', '.join(parts)}\n"
                kept.append(l)
            text2 = "".join(kept)
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
