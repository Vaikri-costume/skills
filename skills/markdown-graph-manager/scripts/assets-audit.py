#!/usr/bin/env python3
"""Assets audit/repair for a markdown graph whose pages/ folder doubles as an
Obsidian vault. Verifies the GRAPH_ROOT/assets -> pages/assets symlink, moves any
stray files if the symlink was ever replaced by a real folder, and rewrites
../../assets/ links to ../assets/ in pages/journals. Safe to run any time;
prints what it does. Pure stdlib; no schema config needed (pure filesystem check).

Usage: assets-audit.py GRAPH_ROOT
"""
import argparse, os, shutil, sys

ap = argparse.ArgumentParser()
ap.add_argument("graph_root")
args = ap.parse_args()

G = os.path.abspath(args.graph_root)
if not os.path.isdir(os.path.join(G, "pages")):
    sys.exit(f"error: {G}/pages not found — is this a valid graph root?")

root_assets, pages_assets = os.path.join(G, "assets"), os.path.join(G, "pages", "assets")
os.makedirs(pages_assets, exist_ok=True)

if os.path.islink(root_assets):
    print("symlink OK:", os.readlink(root_assets))
elif os.path.isdir(root_assets):
    moved = 0
    for f in os.listdir(root_assets):
        shutil.move(os.path.join(root_assets, f), os.path.join(pages_assets, f)); moved += 1
    os.rmdir(root_assets)
    os.symlink("pages/assets", root_assets)
    print(f"symlink was a real folder — moved {moved} files, re-created symlink")
else:
    os.symlink("pages/assets", root_assets)
    print("symlink was missing — created")

fixed = 0
for base, _, files in os.walk(os.path.join(G, "pages")):
    for f in files:
        if not f.endswith(".md"):
            continue
        p = os.path.join(base, f)
        s = open(p, encoding="utf-8").read()
        if "../../assets/" in s:
            open(p, "w", encoding="utf-8").write(s.replace("../../assets/", "../assets/"))
            fixed += 1; print("fixed links in", os.path.relpath(p, G))
print(f"done — {fixed} file(s) link-fixed")
