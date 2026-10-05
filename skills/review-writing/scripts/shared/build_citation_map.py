#!/usr/bin/env python3
"""
build_citation_map.py — Build a per-paragraph citation map from a draft.

Usage:
  python build_citation_map.py --draft-path <path>
                                --format {logseq|plain-md|author-date}
                                --output-path <path>

Output: markdown table — paragraph_number | paragraph_excerpt (40 chars) | citations_found
Exit: 0 on success, 1 on file read error
"""

import sys
import os
import re
import argparse


def read_file(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract_paragraphs import prose_paragraphs  # noqa: E402
from citelib import find_citations, split_body_and_bibliography  # noqa: E402


def split_paragraphs(text):
    """Paragraphs numbered exactly as extract_paragraphs.py numbers them (no headings,
    property lines or code fences), with the reference list excluded."""
    body, _bib = split_body_and_bibliography(text)
    return [para for _num, para in prose_paragraphs(body)]


def excerpt(text, length=40):
    """Return first `length` non-whitespace-collapsed chars of text."""
    flat = " ".join(text.split())
    if len(flat) <= length:
        return flat
    return flat[:length] + "…"


def extract_wikilinks(text):
    """Return sorted unique [[wikilink]] targets in text."""
    return sorted(set(re.findall(r"\[\[([^\]]+)\]\]", text)))


def extract_citekeys(text):
    """Return sorted unique [@citekey] patterns in text."""
    return sorted(set(re.findall(r"\[@([^\]]+)\]", text)))


def build_map(paragraphs, fmt):
    rows = []
    for i, para in enumerate(paragraphs, start=1):
        if fmt == "logseq":
            citations = extract_wikilinks(para)
        elif fmt == "author-date":
            citations = sorted({f"{c['surname']} {c['year']}".strip() for c in find_citations(para)
                                if c["kind"] in ("harvard", "narrative")})
        else:
            citations = extract_citekeys(para)
        rows.append({
            "paragraph_number": i,
            "paragraph_excerpt": excerpt(para),
            "citations_found": ", ".join(citations) if citations else "—",
        })
    return rows


def write_table(rows, output_path):
    lines = [
        "| paragraph_number | paragraph_excerpt | citations_found |",
        "|------------------|-------------------|-----------------|",
    ]
    for row in rows:
        lines.append(
            f"| {row['paragraph_number']} | {row['paragraph_excerpt']} | {row['citations_found']} |"
        )
    content = "\n".join(lines) + "\n"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--draft-path", required=True)
    parser.add_argument("--format", required=True, dest="fmt", choices=["logseq", "plain-md", "author-date"])
    parser.add_argument("--output-path", required=True)
    args = parser.parse_args()

    try:
        draft_text = read_file(args.draft_path)
    except Exception as e:
        print(f"Cannot read draft: {e}", file=sys.stderr)
        sys.exit(1)

    paragraphs = split_paragraphs(draft_text)
    rows = build_map(paragraphs, args.fmt)

    try:
        write_table(rows, args.output_path)
    except Exception as e:
        print(f"Cannot write output: {e}", file=sys.stderr)
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
