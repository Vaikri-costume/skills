#!/usr/bin/env python3
"""
count_citations.py — Count Logseq page links and footnote citations per paragraph in a draft.

Usage: python3 count_citations.py <draft_file_path> [--pages-dir <path>]
Output: JSON to stdout with per-paragraph citation inventory.

--pages-dir: path to the Logseq pages folder (default: 'pages/'). When provided,
  [[PageName]] links are only counted as citations if the linked page file contains
  'type:: source'. Links to non-source pages (concepts, utility, etc.) are excluded.
  If the pages dir is not found or the file is missing, the link is included
  (fail-open: unknown pages are counted rather than silently dropped).

This is for research essays only. The Evidence agents receive this inventory
and focus on judgment (which paragraph claims need support) rather than counting,
which agents do unreliably over long texts.
"""
import sys
import re
import json
import os
import argparse


def _is_source_page(page_name, pages_dir):
    """Return True if the page file in pages_dir contains 'type:: source'.
    Fail-open: returns True (count the link) if the file is not found or unreadable.
    """
    if not pages_dir:
        return True
    # Logseq filenames use triple-lowbar for spaces in 0.10.15
    filename = page_name.replace(' ', '___') + '.md'
    filepath = os.path.join(pages_dir, filename)
    if not os.path.isfile(filepath):
        # Also try space-preserved name for compatibility
        filepath_space = os.path.join(pages_dir, page_name + '.md')
        if not os.path.isfile(filepath_space):
            return True  # Unknown page — include it (fail-open)
        filepath = filepath_space
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read(2000)  # Only need the front-matter
        return 'type:: source' in content
    except (IOError, OSError):
        return True  # Unreadable — include it (fail-open)


def count_citations_per_paragraph(text, pages_dir=None):
    paragraphs = re.split(r'\n\s*\n', text.strip())
    inventory = []
    for i, para in enumerate(paragraphs, 1):
        if not para.strip():
            continue
        # Logseq page links: [[Some Page]] or [[citekey]]
        # Only count if the linked page has type:: source (when pages_dir given)
        raw_page_links = re.findall(r'\[\[([^\]]+)\]\]', para)
        page_links = [p for p in raw_page_links if _is_source_page(p, pages_dir)]
        excluded_page_links = [p for p in raw_page_links if p not in page_links]
        # Footnote markers: [^1], [^citekey]
        footnote_refs = re.findall(r'\[\^([^\]]+)\]', para)
        # Markdown links to source files: [text](path)
        md_links = re.findall(r'\[[^\]]+\]\(([^)]+)\)', para)
        # Inline citations like (Author 2020) or (Author, 2020)
        inline_cites = re.findall(r'\(([A-Z][a-zA-Z]+(?:\s+(?:and|&)\s+[A-Z][a-zA-Z]+)?(?:\s+et\s+al\.?)?,?\s+\d{4}[a-z]?)\)', para)

        words = para.strip().split()
        opening = ' '.join(words[:6]) + ('...' if len(words) > 6 else '')

        total_citations = len(page_links) + len(footnote_refs) + len(md_links) + len(inline_cites)

        entry = {
            'paragraph': i,
            'opening_words': opening,
            'word_count': len(words),
            'citation_count': total_citations,
            'page_links': page_links,
            'footnote_refs': footnote_refs,
            'md_links': md_links,
            'inline_cites': inline_cites,
        }
        if excluded_page_links:
            entry['excluded_non_source_links'] = excluded_page_links
        inventory.append(entry)

    return {
        'total_paragraphs': len(inventory),
        'total_citations': sum(p['citation_count'] for p in inventory),
        'paragraphs_with_zero_citations': sum(1 for p in inventory if p['citation_count'] == 0),
        'pages_dir_used': pages_dir,
        'inventory': inventory,
    }


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description='Count citations per paragraph in a draft essay.')
    ap.add_argument('draft_file', help='Path to the draft file')
    ap.add_argument('--pages-dir', default=None,
                    help='Path to Logseq pages directory (default: pages/). '
                         'Used to filter [[PageName]] links to source pages only.')
    args = ap.parse_args()

    pages_dir = args.pages_dir
    if pages_dir is None and os.path.isdir('pages'):
        pages_dir = 'pages'

    try:
        with open(args.draft_file, 'r', encoding='utf-8') as f:
            text = f.read()
    except (IOError, OSError) as e:
        print(json.dumps({'error': f'Could not read file: {e}'}))
        sys.exit(1)
    print(json.dumps(count_citations_per_paragraph(text, pages_dir=pages_dir), indent=2))
