#!/usr/bin/env python3
"""
quote_verify.py — check that every quotation in a draft exists in the source it cites
(UK misconduct procedures list "quotations that do not exist and are not taken from the
referenced sources" as an indicator of generative-AI use).

Usage: quote_verify.py <draft_file> --source LABEL=PATH [--source LABEL=PATH ...]
                       [--all-sources-fallback]
  LABEL   author surname (any case) the file stands for, e.g. `jones`, or a citekey
  PATH    plain text of the source (a Logseq source page, a Zotero full-text export, a txt
          extraction of a PDF). Anything in the file counts as source text.

For each quotation of 4+ words (inline "…" or `>` block) the result is one of:
  verified          found (ignoring case, quote style, dashes, ellipses, [editorial] words)
  not-found         the cited source was supplied and the passage is not in it
  no-source-supplied  the citation names an author for whom no --source was given
  uncited           no citation follows the quotation
With --all-sources-fallback a not-found/no-source quote is also searched in every supplied source
(reported as verified-elsewhere) — useful when citations are footnotes.

Output: JSON {"results": [...], "summary": {...}}.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from citelib import quotations, normalise_for_match, split_body_and_bibliography  # noqa: E402
from extract_paragraphs import prose_paragraphs  # noqa: E402


def verify(draft_text, sources, fallback=False):
    body, _bib = split_body_and_bibliography(draft_text)
    norm_src = {k.casefold(): normalise_for_match(v) for k, v in sources.items()}
    results = []
    for num, para in prose_paragraphs(body):
        for q in quotations(para):
            nq = normalise_for_match(q['quote'])
            cite = q['cite']
            status, where = 'uncited', None
            if cite and cite.get('surname'):
                key = cite['surname'].casefold()
                cands = [k for k in norm_src if k == key or key in k or k in key]
                if cands:
                    status = 'verified' if any(nq in norm_src[k] for k in cands) else 'not-found'
                    where = cands[0]
                else:
                    status = 'no-source-supplied'
            elif cite:
                status = 'no-source-supplied'
            if fallback and status in ('not-found', 'no-source-supplied', 'uncited'):
                hit = [k for k, v in norm_src.items() if nq in v]
                if hit:
                    status, where = 'verified-elsewhere', hit[0]
            results.append({'paragraph': num, 'quote': q['quote'][:200], 'status': status,
                            'source': where, 'citation': (cite or {}).get('raw')})
    summary = {}
    for r in results:
        summary[r['status']] = summary.get(r['status'], 0) + 1
    return {'results': results, 'summary': summary}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('draft')
    ap.add_argument('--source', action='append', default=[], help='LABEL=PATH')
    ap.add_argument('--all-sources-fallback', action='store_true')
    args = ap.parse_args(argv)
    try:
        draft = open(args.draft, encoding='utf-8').read()
        sources = {}
        for s in args.source:
            label, _, path = s.partition('=')
            if not path:
                print(json.dumps({'error': f'--source needs LABEL=PATH, got {s!r}'}))
                return 1
            sources[label] = open(path, encoding='utf-8', errors='replace').read()
    except OSError as e:
        print(json.dumps({'error': str(e)}))
        return 1
    print(json.dumps(verify(draft, sources, args.all_sources_fallback), indent=2, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
