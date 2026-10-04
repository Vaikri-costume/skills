#!/usr/bin/env python3
"""
schema-lint.py — check a property-block markdown graph's pages against a schema config.
Read-only; never edits.

Usage:
  schema-lint.py GRAPH_ROOT SCHEMA_CONFIG                  # lint every page in GRAPH_ROOT/pages/
  schema-lint.py GRAPH_ROOT SCHEMA_CONFIG "Some Page.md"   # lint one page (name or path)
  schema-lint.py GRAPH_ROOT SCHEMA_CONFIG --quiet          # only print files with violations
Exit code = number of files with violations, capped at 255 (0 = all clean).

All vocabulary/required-property/tolerance data comes from SCHEMA_CONFIG (JSON);
this script hardcodes no graph-specific content. Pure stdlib.
"""
import argparse, fnmatch, json, os, re, sys

ap = argparse.ArgumentParser()
ap.add_argument("graph_root")
ap.add_argument("schema_config", help="path to a schema JSON file, e.g. assets/example-schema.json")
ap.add_argument("pages", nargs="*", help="optional specific page(s) to lint")
ap.add_argument("--pages-dir", default="pages", help="pages directory relative to graph root (default: pages; use . for a flat vault)")
ap.add_argument("--quiet", action="store_true", help="only print files with violations")
args = ap.parse_args()

G = os.path.abspath(args.graph_root)
PAGES = os.path.normpath(os.path.join(G, args.pages_dir))
if not os.path.isdir(PAGES):
    sys.exit(f"error: {G}/pages not found — is this a valid graph root?")
SCHEMA = json.load(open(args.schema_config, encoding="utf-8"))

TYPE_VOCAB = set(SCHEMA["type_vocab"])
WRITER_VOCAB_PLAIN = set(SCHEMA["writer_vocab_plain"])
STATUS_VOCAB = set(SCHEMA["status_vocab"])
ZOTERO_ONLY = set(SCHEMA["zotero_only_properties"])
REQUIRED_PROPS = SCHEMA.get("required_properties", {})
TOLERATED = set(SCHEMA.get("tolerated_properties", []))
TOLERATED_PATTERNS = SCHEMA.get("tolerated_property_patterns", [])
APP_INTERNAL = set(SCHEMA.get("app_internal_properties", []))
SKIP_DIRS = (".obsidian", "assets", "copilot")

def is_tolerated(prop):
    """Property another app (e.g. Tine) or the graph app itself writes — never a violation."""
    if prop in TOLERATED or prop in APP_INTERNAL:
        return True
    return any(fnmatch.fnmatch(prop, pat) for pat in TOLERATED_PATTERNS)

def strip_code(text):
    # blank out inline `code` and fenced blocks so examples don't false-positive
    text = re.sub(r'`[^`]*`', '``', text)
    text = re.sub(r'```.*?```', '```', text, flags=re.S)
    return text

def lint(path):
    raw = open(path, encoding="utf-8").read()
    text = strip_code(raw)
    lines = text.split("\n")
    V = []
    # leading page-property block + body split
    first_bullet = next((i for i, l in enumerate(lines) if l.startswith("- ")), len(lines))
    head = lines[:first_bullet]
    page = {}
    blank_before_prop = False
    for i, l in enumerate(head):
        m = re.match(r'^([a-z][a-z.-]*):: ?(.*)$', l)
        if m:
            page[m.group(1)] = m.group(2).strip()
            if any(x.strip() == "" for x in head[:i]):
                blank_before_prop = True
    # RULES
    if raw.startswith("---\n"):
        V.append("YAML frontmatter (use property:: lines)")
    for i, l in enumerate(lines):
        if re.match(r'^#{1,6} ', l):
            V.append(f"L{i+1}: markdown # heading (use heading:: true)")
    for i, l in enumerate(lines):
        # A short label-like phrase at the start of a bullet, followed by a SINGLE
        # colon (never `::` — that's a real Logseq property, a different thing
        # entirely and never flagged here) and more content on the same line.
        # Confirmed anti-pattern 2026-08-11 ("University Affiliation: ..." should
        # be "University Affiliation - ..."): a single colon used as a pseudo-label
        # separator, mimicking property syntax without being one. Report-only,
        # always — colons are also completely ordinary in ambiguous-looking
        # positions (quote attributions, times, ratios, citations), so only a
        # human/orchestrator judgment call can tell which reading applies to a
        # given line; never auto-fixed.
        m = re.match(r"^\s*-\s*(?!(?:TODO|DOING|DONE|WAITING|CANCELLED|LATER|NOW)\b)([A-Z][A-Za-z0-9 /'&,.()-]{1,50}?):(?!:)\s+\S", l)
        if m:
            V.append(f"L{i+1}: single-colon pseudo-label {m.group(1)!r}: — "
                      f"if this is a label/property-style separator, use a hyphen "
                      f"instead (\"{m.group(1)} - ...\"); leave alone if it's "
                      f"ordinary prose (a quote attribution, a time, a citation)")
    for i, l in enumerate(lines):
        # A bold "label" immediately after the bullet dash, followed by a dash
        # and more text on the SAME line, reads as an ad-hoc inline heading —
        # confirmed anti-pattern 2026-08-11. Correct form: the label is its own
        # bullet with heading:: true on a child line, and the content is a
        # further-indented child bullet — never crammed onto one line.
        # Report-only: whether a given line was actually INTENDED as a heading
        # (needing the heading:: true + child-bullet restructure) is a
        # judgment call graph-link-audit.py's bold-markdown safe-fix does not
        # make — that fix only strips ** formatting, it never restructures.
        if re.match(r'^\s*-\s*\*\*[^*]+\*\*\s*[—–-]\s', l):
            V.append(f"L{i+1}: inline bold-heading-plus-dash on one line — "
                      f"split into a heading:: true bullet + a separate child "
                      f"bullet for the content")
    for m in re.findall(r'\[\[([^\]]+/[^\]]+)\]\]', text):
        if not m.startswith("http"):
            V.append(f"namespaced link [[{m}]] (flatten, no /)")
    if blank_before_prop:
        V.append("page property after a blank line (keep leading props contiguous)")
    # Zotero-only props on a non-Zotero page (heuristic: page not tagged as from zotero)
    is_zotero = "zotero" in page.get("source", "").lower() or page.get("type") == "" or "citekey" in raw.lower()
    for i, l in enumerate(lines):
        m = re.match(r'^\s*([a-z][a-z.-]*):: ', l)
        if m and m.group(1) in ZOTERO_ONLY and not is_zotero and not is_tolerated(m.group(1)):
            V.append(f"L{i+1}: {m.group(1)}:: reserved for Zotero pages")
    # vocab checks
    for i, l in enumerate(lines):
        m = re.match(r'^\s*type:: (.+?)\s*$', l)
        if m:
            # type:: is array-capable (comma-separated); each value must be in vocab
            for v in (x.strip() for x in m.group(1).split(",")):
                if v and v not in TYPE_VOCAB:
                    V.append(f"L{i+1}: type:: {v!r} not in vocab")
        m = re.match(r'^\s*writer:: (.+?)\s*$', l)
        if m:
            for v in (x.strip() for x in m.group(1).split(",")):
                if v and not (v in WRITER_VOCAB_PLAIN or v.startswith("[[")):
                    V.append(f"L{i+1}: writer:: {v!r} not a known writer/entity")
        m = re.match(r'^\s*status:: (.+?)\s*$', l)
        if m and m.group(1) not in STATUS_VOCAB:
            V.append(f"L{i+1}: status:: {m.group(1)!r} not in status vocab")
    # missing required properties, keyed on page-level type:: (array-capable)
    page_types = [x.strip() for x in page.get("type", "").split(",") if x.strip()]
    for pt in page_types:
        for req in REQUIRED_PROPS.get(pt, []):
            if req not in page:
                V.append(f"missing required property {req}:: (type:: {pt})")
    # redundant block value == page value (promotion rule)
    for prop in ("type", "writer"):
        pv = page.get(prop)
        if pv:
            for i, l in enumerate(lines):
                if re.match(rf'^\s+{prop}:: ' + re.escape(pv) + r'\s*$', l):
                    V.append(f"L{i+1}: block {prop}:: {pv} duplicates page value (strip)")
    return V

def target_files():
    if args.pages:
        return [a if os.path.isabs(a) else os.path.join(PAGES, a) for a in args.pages]
    order = []
    for base, dirs, files in os.walk(PAGES):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in sorted(files):
            if f.endswith(".md"):
                order.append(os.path.join(base, f))
    return order

targets = target_files()
bad = 0
linted = 0
for p in targets:
    if not os.path.exists(p):
        print(f"?? not found: {p}"); continue
    V = lint(p)
    linted += 1
    rel = os.path.relpath(p, G)
    if V:
        bad += 1
        print(f"✗ {rel}")
        for v in V:
            print(f"    {v}")
    elif not args.quiet:
        print(f"✓ {rel}")
print(f"\nlinted {linted}/{len(targets)} files")
if linted == 0 and len(targets) > 0:
    print("!! 0 files linted — target discovery is broken, results below are not trustworthy")
    sys.exit(255)
print(f"{bad} file(s) with violations")
sys.exit(min(bad, 255))
