#!/usr/bin/env python3
"""
citation_audit.py — deterministic citation and source-reliance audit of a draft.

Usage: citation_audit.py <draft_file>
Output: JSON on stdout (or {"error": ...}).

Covers the typical UK misconduct-procedure indicators that can be checked by machine
(REG-183-10: repeated introductions of authors, repeated bibliography entries, an
extensive bibliography not cited in the text) plus source-reliance patterns and
citation artefacts typical of machine-written text.

Fields
  citations                    in-text citations found (harvard, narrative, footnote, wikilink, citekey)
  unmatched_citations          cited in text, no bibliography entry (only when a bibliography exists)
  uncited_bibliography         bibliography entries never cited in the body
  duplicate_bibliography       the same author+year(+title start) listed more than once
  sources_per_paragraph        {paragraph_number: [source keys]} (paragraph numbers match the shared map)
  dominance                    sources that are the only source cited across >= 4 consecutive cited paragraphs
  final_quarter                {"single_source": key|null} — one source only in the last quarter of the essay by words
  author_reintroductions       authors introduced narratively (Name (year) …) 3 or more times
  artefacts                    broken/odd references: utm_ parameters, invalid ISBN checksum, malformed DOI,
                               placeholder markers such as oaicite / contentReference
Constants (judgement calls, not published thresholds): 4 consecutive paragraphs, 3 introductions.
"""
import json
import os
import re
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from citelib import (find_citations, split_body_and_bibliography, parse_bibliography,  # noqa: E402
                     keys_match, footnote_definitions, citation_from_note)
from extract_paragraphs import prose_paragraphs  # noqa: E402

DOMINANCE_RUN = 4
REINTRO_COUNT = 3


def _isbn_ok(digits):
    d = digits.replace('-', '').replace(' ', '').upper()
    if len(d) == 10 and re.fullmatch(r'\d{9}[\dX]', d):
        s = sum((10 - i) * (10 if c == 'X' else int(c)) for i, c in enumerate(d))
        return s % 11 == 0
    if len(d) == 13 and d.isdigit():
        s = sum(int(c) * (1 if i % 2 == 0 else 3) for i, c in enumerate(d))
        return s % 10 == 0
    return False


def find_artefacts(text):
    out = []
    for m in re.finditer(r'[?&]utm_[a-z]+=\S*', text):
        out.append({'kind': 'utm-parameter', 'text': m.group(0)[:80]})
    for m in re.finditer(r'\b(?:oaicite|contentReference)\b[^\s]*', text):
        out.append({'kind': 'placeholder-marker', 'text': m.group(0)[:80]})
    for m in re.finditer(r'\bdoi:?\s*(10\.\S+)', text, re.IGNORECASE):
        doi = m.group(1).rstrip('.,;)')
        if not re.fullmatch(r'10\.\d{4,9}/\S+', doi):
            out.append({'kind': 'malformed-doi', 'text': doi})
    for m in re.finditer(r'https?://(?:dx\.)?doi\.org/(\S+)', text):
        doi = m.group(1).rstrip('.,;)')
        if not re.fullmatch(r'10\.\d{4,9}/\S+', doi):
            out.append({'kind': 'malformed-doi', 'text': doi})
    for m in re.finditer(r'ISBN(?:-1[03])?:?\s*([\d][\d\- ]{8,16}[\dXx])', text):
        if not _isbn_ok(m.group(1)):
            out.append({'kind': 'invalid-isbn-checksum', 'text': m.group(1).strip()})
    return out


def source_key(c):
    if c['kind'] in ('harvard', 'narrative', 'footnote-note'):
        return f"{c['surname']} {c['year']}".strip()
    return c['authors'] or c['raw']


def audit(text):
    body, bib_text = split_body_and_bibliography(text)
    bib = parse_bibliography(bib_text) if bib_text else []
    defs = footnote_definitions(body)
    paras = prose_paragraphs(body)

    per_para = {}
    all_cites = []
    for num, para in paras:
        cs = [c for c in find_citations(para) if c['kind'] != 'footnote']
        # footnote markers: resolve to the citation inside the definition, if parseable
        for fm in re.finditer(r'\[\^([^\]\s]+)\](?!:)', para):
            note = defs.get(fm.group(1))
            cc = citation_from_note(note) if note else None
            if cc:
                cs.append(cc)
        per_para[num] = [source_key(c) for c in cs]
        all_cites += [dict(c, paragraph=num) for c in cs]

    unmatched, cited_entries = [], set()
    if bib:
        for c in all_cites:
            if c['kind'] in ('harvard', 'narrative', 'footnote-note'):
                hit = [i for i, e in enumerate(bib) if keys_match(c, e)]
                if hit:
                    cited_entries.update(hit)
                else:
                    unmatched.append({'paragraph': c['paragraph'], 'citation': c['raw'][:100]})
    uncited = [e['raw'] for i, e in enumerate(bib) if i not in cited_entries]

    seen, dups = Counter(), []
    for e in bib:
        seen[(e['surname'], e['year'], e['raw'][:60].casefold())] += 1
    dups = [{'entry': k[2], 'times': n} for k, n in seen.items() if n > 1]

    # dominance: a single distinct source cited across >= DOMINANCE_RUN consecutive paragraphs
    dominance = []
    run_src, run_start, run_len = None, None, 0
    for num in sorted(per_para):
        keys = set(per_para[num])
        src = next(iter(keys)) if len(keys) == 1 else None
        if src is not None and src == run_src:
            run_len += 1
        else:
            if run_src is not None and run_len >= DOMINANCE_RUN:
                dominance.append({'source': run_src, 'from_paragraph': run_start, 'paragraphs': run_len})
            run_src, run_start, run_len = (src, num, 1) if src else (None, None, 0)
    if run_src is not None and run_len >= DOMINANCE_RUN:
        dominance.append({'source': run_src, 'from_paragraph': run_start, 'paragraphs': run_len})

    total_words = sum(len(p.split()) for _, p in paras) or 1
    acc, last_q = 0, set()
    for num, para in paras:
        acc += len(para.split())
        if acc > total_words * 0.75:
            last_q |= set(per_para.get(num, []))
    final = {'single_source': next(iter(last_q)) if len(last_q) == 1 else None}

    intro = Counter(c['surname'] for c in all_cites if c['kind'] == 'narrative')
    reintro = [{'author': a, 'times': n} for a, n in intro.items() if n >= REINTRO_COUNT]

    return {
        'citations': len(all_cites),
        'unmatched_citations': unmatched,
        'uncited_bibliography': uncited,
        'duplicate_bibliography': dups,
        'sources_per_paragraph': {str(k): v for k, v in per_para.items()},
        'dominance': dominance,
        'final_quarter': final,
        'author_reintroductions': reintro,
        'artefacts': find_artefacts(text),
        'bibliography_entries': len(bib),
    }


def main(argv):
    if len(argv) != 1:
        print(json.dumps({'error': 'Usage: citation_audit.py <draft_file>'}))
        return 1
    try:
        text = open(argv[0], encoding='utf-8').read()
    except OSError as e:
        print(json.dumps({'error': str(e)}))
        return 1
    print(json.dumps(audit(text), indent=2, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
