#!/usr/bin/env python3
"""
overlap_check.py — deterministic verbatim-overlap check between a draft and source texts.
Replaces the old Tier 1 agent pair and per-source Check 1.

Usage:
  overlap_check.py <draft> --source LABEL=PATH [--source ...]    # quoted passages of a source page
                          [--plain LABEL=PATH ...]                # whole text (prior submissions, extracts)
                          [--min-words 6] [--short-words 4]
                          [--common-terms FILE]
  --source  reads only lines of the form  "quoted text" (citation)  — the writer's own annotations
            (author:: lines etc.) are NOT source material and are never compared.
  --plain   treats the whole file as source text. Use it for the writer's earlier submissions
            (self-plagiarism, SOAS REG-183-10 §2.6) or for extracted source text.

What counts as a match (heuristic constants, documented because SOAS and QAA give no numeric
threshold: SOAS defines plagiarism by behaviour and separates minor from major by amount and by
whether the material is critical to the assignment):
  verbatim-run   a run of >= --min-words (default 6) consecutive words, function words included,
                 identical in draft and source, outside quotation marks.
  short-match    a run of --short-words..min-words-1 (default 4–5) words with at least 3 content
                 words, not listed in --common-terms. Weak evidence: field-standard phrases land here.
  Runs inside quotation marks or `>` blocks are properly marked and counted as quoted_matches,
  not flagged. Whether a quotation is cited is a different check (quote_verify.py).
Output: JSON {"parameters", "matches", "quoted_matches", "coverage"}; coverage is the share of the
draft's words inside verbatim-runs, per source.
"""
import argparse
import json
import os
import re
import sys
from collections import defaultdict

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(_HERE, 'shared')))
from extract_paragraphs import prose_paragraphs  # noqa: E402
from citelib import split_body_and_bibliography  # noqa: E402

STOP = set("""the a an is are was were be been being of in on to for with by at from this that these those and or but as it its
their his her our your my which who whom whose not no so than then there here has have had do does did can could may might
will would shall should also such""".split())

_WORD = re.compile(r"[\w]+(?:['’][\w]+)*")
_QUOTED = re.compile(r'["“][^"“”]+["”]')
_SRC_QUOTE = re.compile(r'["“]([^"“”]{12,}?)["”]\s*\(([^()]*)\)')


def tokens(text):
    """[(normalised_word, start, end)]"""
    return [(m.group(0).replace('’', "'").casefold(), m.start(), m.end()) for m in _WORD.finditer(text)]


def quoted_spans(text):
    spans = [(m.start(), m.end()) for m in _QUOTED.finditer(text)]
    for m in re.finditer(r'^>.*$', text, re.MULTILINE):
        spans.append((m.start(), m.end()))
    return spans


def source_passages(text):
    """Quoted passages of a source page: lines like  "quoted text" (citekey, p. 3)."""
    return [m.group(1).strip() for m in _SRC_QUOTE.finditer(text)]


def find_blocks(d, s, k):
    """Maximal common runs of >= k tokens between word lists d and s (greedy, non-overlapping in d)."""
    if len(d) < k or len(s) < k:
        return []
    idx = defaultdict(list)
    for j in range(len(s) - k + 1):
        idx[tuple(s[j:j + k])].append(j)
    out, i = [], 0
    while i <= len(d) - k:
        best, bj = 0, None
        for j in idx.get(tuple(d[i:i + k]), ()):
            l = k
            while i + l < len(d) and j + l < len(s) and d[i + l] == s[j + l]:
                l += 1
            if l > best:
                best, bj = l, j
        if best >= k:
            out.append((i, bj, best))
            i += best
        else:
            i += 1
    return out


def check(draft_text, sources, min_words=6, short_words=4, common=()):
    """sources: [(label, [passage, ...])]. Returns the result dict."""
    body, _bib = split_body_and_bibliography(draft_text)
    paras = prose_paragraphs(body)
    total_words = sum(len(tokens(p)) for _n, p in paras) or 1
    common_norm = [' '.join(w for w, _a, _b in tokens(c)) for c in common if c.strip()]
    matches, quoted = [], 0
    covered = defaultdict(int)
    for label, passages in sources:
        src_tok = [[w for w, _a, _b in tokens(p)] for p in passages]
        src_raw = passages
        for num, para in paras:
            dt = tokens(para)
            dw = [w for w, _a, _b in dt]
            qs = quoted_spans(para)
            for pi, st in enumerate(src_tok):
                for i, j, l in find_blocks(dw, st, short_words):
                    start, end = dt[i][1], dt[i + l - 1][2]
                    in_q = any(a <= start and end <= b + 1 for a, b in qs) or any(a <= start < b for a, b in qs)
                    run = dw[i:i + l]
                    content = [w for w in run if w not in STOP]
                    if in_q:
                        quoted += 1
                        continue
                    if l >= min_words:
                        kind = 'verbatim-run'
                        covered[label] += l
                    elif len(content) >= 3 and not any(' '.join(run) in c or c in ' '.join(run) for c in common_norm):
                        kind = 'short-match'
                    else:
                        continue
                    sw = tokens(src_raw[pi])
                    matches.append({
                        'paragraph': num, 'source': label, 'kind': kind, 'words': l,
                        'content_words': len(content),
                        'draft_text': para[start:end],
                        'source_text': src_raw[pi][sw[j][1]:sw[j + l - 1][2]],
                    })
    matches.sort(key=lambda m: (m['paragraph'], -m['words']))
    return {
        'parameters': {'min_words_verbatim': min_words, 'min_words_short': short_words,
                       'note': 'heuristic constants; no SOAS or QAA numeric threshold exists'},
        'matches': matches,
        'quoted_matches': quoted,
        'coverage': {k: round(v / total_words, 4) for k, v in covered.items()},
    }


def _read(path):
    with open(path, encoding='utf-8', errors='replace') as f:
        return f.read()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('draft')
    ap.add_argument('--source', action='append', default=[], help='LABEL=PATH, quoted passages only')
    ap.add_argument('--plain', action='append', default=[], help='LABEL=PATH, whole text')
    ap.add_argument('--min-words', type=int, default=6)
    ap.add_argument('--short-words', type=int, default=4)
    ap.add_argument('--common-terms')
    args = ap.parse_args(argv)
    try:
        draft = _read(args.draft)
        srcs = []
        for s in args.source:
            label, _, path = s.partition('=')
            srcs.append((label, source_passages(_read(path))))
        for s in args.plain:
            label, _, path = s.partition('=')
            srcs.append((label, [p.strip() for p in re.split(r'\n\s*\n', _read(path)) if p.strip()]))
        common = _read(args.common_terms).splitlines() if args.common_terms else []
    except OSError as e:
        print(json.dumps({'error': str(e)}))
        return 1
    if not srcs:
        print(json.dumps({'error': 'give at least one --source or --plain'}))
        return 1
    print(json.dumps(check(draft, srcs, args.min_words, args.short_words, common), indent=2, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
