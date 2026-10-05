#!/usr/bin/env python3
"""
detect_sources.py — Discover citation sources referenced in a draft.

Usage:
  python detect_sources.py --mode {citation-check|full-scan}
                            --draft-path <path>
                            --format {logseq|plain-md|author-date}
                            [--bib-path <path>]
                            [--manifest-path <path>]
                            [--pages-dir <logseq pages folder>]
                            [--sources-dir <folder of source text files>]

author-date (Harvard) and footnote drafts: citations are parsed from the text, matched to the
draft's own bibliography, and each cited work is looked up in --sources-dir by surname/year in
the file name. Unresolved works come back with "path": null and "resolved": false so the caller
can look them up in Zotero (zotero_search_items / zotero_get_item_fulltext).

Output: JSON array to stdout, each item: {"id": str, "path": str, "title": str}
Exit: 0 on success, 1 on error (human-readable message to stderr)
"""

import sys
import os
import re
import json
import argparse


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from citelib import (find_citations, split_body_and_bibliography, parse_bibliography,  # noqa: E402
                     keys_match, footnote_definitions, citation_from_note)

# Default Logseq pages folder: ./pages under the current directory. Override with --pages-dir.
PAGES_DIR = os.path.join(os.getcwd(), "pages")


def read_file(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


# ── Logseq helpers ──────────────────────────────────────────────────────────

def extract_wikilinks(text):
    """Return sorted unique list of [[wikilink]] targets."""
    return sorted(set(re.findall(r"\[\[([^\]]+)\]\]", text)))


def find_source_pages_by_titles(titles, pages_dir):
    """Given wikilink titles, find matching type::source pages in pages_dir."""
    results = []
    for title in titles:
        # Logseq filename: title with spaces→underscores (triple-lowbar scheme)
        filename_candidate = title.replace("/", "___").replace(" ", "_") + ".md"
        path = os.path.join(pages_dir, filename_candidate)
        if os.path.isfile(path):
            text = read_file(path)
            if re.search(r"^type::\s*source", text, re.MULTILINE):
                results.append({"id": title, "path": path, "title": title})
    return results


def find_all_source_pages(pages_dir):
    """Return all type::source pages in pages_dir."""
    results = []
    if not os.path.isdir(pages_dir):
        return results
    for fname in os.listdir(pages_dir):
        if not fname.endswith(".md"):
            continue
        path = os.path.join(pages_dir, fname)
        try:
            text = read_file(path)
        except Exception:
            continue
        if re.search(r"^type::\s*source", text, re.MULTILINE):
            title_match = re.search(r"^title::\s*(.+)", text, re.MULTILINE)
            title = title_match.group(1).strip() if title_match else fname[:-3]
            results.append({"id": title, "path": path, "title": title})
    return results


# ── Plain-md helpers ─────────────────────────────────────────────────────────

def extract_citekeys(text):
    """Return sorted unique list of [@citekey] patterns."""
    return sorted(set(re.findall(r"\[@([^\]]+)\]", text)))


def find_sources_in_bib(citekeys, bib_path):
    """Look up citekeys in a .bib file; return found entries."""
    results = []
    try:
        bib_text = read_file(bib_path)
    except Exception as e:
        print(f"Cannot read bib file {bib_path}: {e}", file=sys.stderr)
        sys.exit(1)
    for key in citekeys:
        pattern = re.compile(r"@\w+\{" + re.escape(key) + r"\b", re.IGNORECASE)
        if pattern.search(bib_text):
            results.append({"id": key, "path": bib_path, "title": key})
    return results


def find_sources_in_manifest(manifest_path):
    """Read sources-manifest.md; return list of {id, path, title}."""
    results = []
    try:
        text = read_file(manifest_path)
    except Exception as e:
        print(f"Cannot read manifest {manifest_path}: {e}", file=sys.stderr)
        sys.exit(1)
    for line in text.splitlines():
        line = line.strip().lstrip("- ").strip()
        if not line or line.startswith("#"):
            continue
        results.append({"id": line, "path": line, "title": os.path.basename(line)})
    return results


# ── Author-date / footnote helpers ──────────────────────────────────────────

def author_date_sources(draft_text, sources_dir):
    """Cited works (surname + year) with their bibliography entry and, if found, a source file."""
    body, bib_text = split_body_and_bibliography(draft_text)
    bib = parse_bibliography(bib_text) if bib_text else []
    cites = [c for c in find_citations(body) if c["kind"] in ("harvard", "narrative")]
    defs = footnote_definitions(body)
    for note in defs.values():
        c = citation_from_note(note)
        if c:
            cites.append(c)
    files = []
    if sources_dir and os.path.isdir(sources_dir):
        files = [os.path.join(sources_dir, f) for f in sorted(os.listdir(sources_dir))
                 if os.path.isfile(os.path.join(sources_dir, f))]
    out, seen = [], set()
    for c in cites:
        key = (c["surname"], c["year"].rstrip("abcdefghijklmnopqrstuvwxyz"))
        if key in seen:
            continue
        seen.add(key)
        entry = next((e for e in bib if keys_match(c, e)), None)
        path = next((f for f in files
                     if c["surname"] in os.path.basename(f).casefold()
                     and key[1] in os.path.basename(f)), None) or \
               next((f for f in files if c["surname"] in os.path.basename(f).casefold()), None)
        out.append({"id": f"{c['surname']} {c['year']}", "path": path,
                    "title": entry["raw"] if entry else None,
                    "in_bibliography": entry is not None, "resolved": path is not None})
    return out


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["citation-check", "full-scan"], required=True)
    parser.add_argument("--draft-path", required=True)
    parser.add_argument("--format", required=True, dest="fmt")
    parser.add_argument("--bib-path", default=None)
    parser.add_argument("--manifest-path", default=None)
    parser.add_argument("--pages-dir", default=PAGES_DIR)
    parser.add_argument("--sources-dir", default=None)
    args = parser.parse_args()
    pages_dir = args.pages_dir

    try:
        draft_text = read_file(args.draft_path)
    except Exception as e:
        print(f"Cannot read draft: {e}", file=sys.stderr)
        sys.exit(1)

    results = []

    if args.fmt == "logseq":
        if args.mode == "citation-check":
            titles = extract_wikilinks(draft_text)
            results = find_source_pages_by_titles(titles, pages_dir)
        else:
            results = find_all_source_pages(pages_dir)

    elif args.fmt == "author-date":
        results = author_date_sources(draft_text, args.sources_dir)

    else:  # plain-md or other
        if args.mode == "citation-check":
            if not args.bib_path:
                print("--bib-path required for citation-check mode with plain-md", file=sys.stderr)
                sys.exit(1)
            citekeys = extract_citekeys(draft_text)
            results = find_sources_in_bib(citekeys, args.bib_path)
        else:
            manifest = args.manifest_path
            if not manifest:
                print(
                    "full-scan mode requires --manifest-path (sources-manifest.md) for plain-md format. "
                    "Create sources-manifest.md with one source path or citekey per line.",
                    file=sys.stderr
                )
                sys.exit(1)
            results = find_sources_in_manifest(manifest)

    print(json.dumps(results, ensure_ascii=False))
    sys.exit(0)


if __name__ == "__main__":
    main()
