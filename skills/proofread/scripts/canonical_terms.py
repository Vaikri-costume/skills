#!/usr/bin/env python3
"""
canonical_terms.py — deterministic canonical-vocabulary lookup for the proofread skill.
Replaces the old Canonical-1 / Canonical-2 agent pairs: matching a word against a
list of opted-in terms is a lookup, not a judgement.

A terms file is markdown. Every list item (`- term`) is a canonical term; headings
are ignored. Terms are only ever added by `add` after the writer confirms them.

Subcommands
  collect A.md [B.md ...]        union the `## Unrecognised terms` sections of surface agents
                                 -> one term per line on stdout
  check --terms CUR.md [--other OTHER.md ...] [--global GLOBAL.md] --words FILE
                                 classify each word (one per line in FILE) -> JSON
  add --terms FILE term [term ...]
                                 append confirmed terms under `## Canonical terms`

Classification of each word against CUR first, then OTHER files, then GLOBAL:
  matched-correct     identical spelling is listed
  matched-incorrect   same word after ignoring case, diacritics and hyphens, but spelt
                      differently (draft form -> canonical form)
  near-matched        one or two characters away (words of 5+ letters) — a likely variant
  unresolved          nothing close anywhere
`source` says where the match came from: current | other:<file> | global. A match in
other/global is a migration suggestion (add to the current list).
"""
import argparse
import difflib
import json
import os
import re
import sys
import unicodedata


def _fold(s):
    s = unicodedata.normalize('NFKD', s)
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[-‐‑‒–\s'’]", '', s).casefold()


def load_terms(path):
    terms = []
    try:
        with open(path, encoding='utf-8') as f:
            for line in f:
                m = re.match(r'^\s*[-*]\s+(.*\S)\s*$', line)
                if m:
                    terms.append(m.group(1).strip())
    except FileNotFoundError:
        pass
    return terms


def _near(word, term):
    a, b = _fold(word), _fold(term)
    if min(len(a), len(b)) < 5:
        return False
    return difflib.SequenceMatcher(None, a, b).ratio() >= 0.84 and abs(len(a) - len(b)) <= 2


def classify(word, term_sets):
    """term_sets: ordered list of (source_label, [terms])."""
    best_near = None
    for source, terms in term_sets:
        for t in terms:
            if t == word:
                return {'word': word, 'class': 'matched-correct', 'canonical': t, 'source': source}
        for t in terms:
            if _fold(t) == _fold(word):
                return {'word': word, 'class': 'matched-incorrect', 'canonical': t, 'source': source}
        if best_near is None:
            for t in terms:
                if _near(word, t):
                    best_near = {'word': word, 'class': 'near-matched', 'canonical': t, 'source': source}
                    break
    return best_near or {'word': word, 'class': 'unresolved', 'canonical': None, 'source': None}


def collect(paths):
    seen, out = set(), []
    for p in paths:
        text = open(p, encoding='utf-8').read()
        m = re.search(r'^##\s*Unrecognised terms\s*\n(.*?)(?=^##\s|\Z)', text, re.S | re.M | re.I)
        if not m:
            continue
        for line in m.group(1).splitlines():
            term = line.strip().lstrip('-*').strip().strip('"')
            if term and not re.match(r'^(none identified\.?|none\.?)$', term, re.I) and term.casefold() not in seen:
                seen.add(term.casefold())
                out.append(term)
    return out


def add_terms(path, terms):
    existing = {_fold(t) for t in load_terms(path)}
    new = [t for t in terms if _fold(t) not in existing]
    if not new:
        return []
    body = ''
    if os.path.exists(path):
        body = open(path, encoding='utf-8').read()
        if not re.search(r'^##\s*Canonical terms', body, re.M | re.I):
            body = body.rstrip('\n') + '\n\n## Canonical terms\n'
        elif not body.endswith('\n'):
            body += '\n'
    else:
        body = '# Canonical terms\n\n## Canonical terms\n'
    body += ''.join(f'- {t}\n' for t in new)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(body)
    return new


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    c = sub.add_parser('collect')
    c.add_argument('files', nargs='+')
    k = sub.add_parser('check')
    k.add_argument('--terms', required=True)
    k.add_argument('--other', action='append', default=[])
    k.add_argument('--global', dest='glob')
    k.add_argument('--words', required=True)
    a = sub.add_parser('add')
    a.add_argument('--terms', required=True)
    a.add_argument('new', nargs='+')
    args = ap.parse_args(argv)
    try:
        if args.cmd == 'collect':
            sys.stdout.write('\n'.join(collect(args.files)) + '\n')
        elif args.cmd == 'check':
            sets = [('current', load_terms(args.terms))]
            sets += [(f'other:{os.path.basename(p)}', load_terms(p)) for p in args.other]
            if args.glob:
                sets.append(('global', load_terms(args.glob)))
            words = [w.strip() for w in open(args.words, encoding='utf-8') if w.strip()]
            res = [classify(w, sets) for w in words]
            print(json.dumps({'results': res,
                              'migration': [r for r in res if r['source'] not in (None, 'current')]},
                             indent=2, ensure_ascii=False))
        else:
            added = add_terms(args.terms, args.new)
            print(json.dumps({'added': added}))
    except OSError as e:
        print(json.dumps({'error': str(e)}))
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
