#!/usr/bin/env python3
"""
compute_metrics.py — descriptive text metrics for the ai-detection-check skill.

Usage: compute_metrics.py <draft_file> [--baseline FILE [FILE ...]]
Output: JSON on stdout, or {"error": ...}.

These are DESCRIPTIONS, not scores. There are no RED/YELLOW/GREEN ratings: no published
threshold exists for sentence-length variation, type-token ratio or hedge density, and
detectors built on such proxies misclassify formal, constrained or second-language writing
(Liang et al. 2023; Karr et al. 2026, whose false-positive rates track long-token and
Academic Word List density). A number here is only meaningful against the writer's own
baseline, so `--baseline` compares the draft with the writer's earlier texts.

Metrics
  sentences / sentence_inventory      for hedging calibration
  sentence_length: mean, stdev, cv    variation in sentence length (sample stdev)
  mattr_100                           moving-average type-token ratio (window 100); length-robust,
                                      unlike plain TTR. null when the text has < 150 words.
  hedge_count, hedge_per_100_words    context-filtered hedge markers
  features_per_1000_words             proxies for the contrasts Reinhart et al. (PNAS 2025) found
                                      between LLM and human text (LLM vs human: present-participle
                                      clauses ~2-5x, nominalisations ~1.5-2x, passives ~0.5x):
      present_participle_clauses      ", <verb>ing" clause openers (regex proxy)
      nominalisations                 words of 7+ letters ending -tion/-sion/-ment/-ness/-ity/-ance/-ence
      passives                        be-verb + past participle (regex proxy)
  guard                               {"sufficient": bool, "min_words": 300, "note": ...}: below the
                                      minimum the feature rates are unreliable and say so.
  baseline_comparison                 per feature: draft rate, baseline rate, ratio (only if the baseline
                                      has >= 1000 words; Burrows-style methods need about that much).
A ratio is not evidence of machine authorship. Population-level contrasts do not transfer to one essay.
"""
import json
import math
import re
import sys

import os as _os
sys.path.insert(0, _os.path.normpath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), 'shared')))
try:
    from citelib import split_body_and_bibliography as _split_body
except ImportError:  # shared helper missing: scan the whole text
    def _split_body(t):
        return t, ''

_SENTENCE_ABBREVS = ('Mr.', 'Mrs.', 'Ms.', 'Dr.', 'Prof.', 'vs.', 'et al.',
                     'e.g.', 'i.e.', 'etc.', 'Fig.', 'No.', 'Vol.', 'pp.', 'p.')
MIN_WORDS = 300
BASELINE_MIN_WORDS = 1000
MATTR_WINDOW = 100

_NOT_PARTICIPLES = {'including', 'according', 'regarding', 'concerning', 'following', 'during', 'pending',
                    'notwithstanding', 'considering', 'given', 'barring', 'excepting', 'owing', 'granted'}
_PASSIVE_RE = re.compile(r"\b(?:is|are|was|were|be|been|being)\s+(?:\w+ly\s+)?(\w+(?:ed|en))\b", re.I)
_NOMINAL_RE = re.compile(r"\b\w{3,}(?:tion|sion|ment|ness|ity|ance|ence)s?\b", re.I)
_PARTICIPLE_RE = re.compile(r",\s+(?:\w+ly\s+)?(\w+ing)\b", re.I)


def _strip_markup(text):
    text = _split_body(text)[0]                                       # reference list is not prose
    text = re.sub(r'^\s{0,3}#{1,6}\s.*$', '', text, flags=re.M)      # headings
    text = re.sub(r'^[A-Za-z][\w-]*::.*$', '', text, flags=re.M)     # Logseq properties
    text = re.sub(r'```.*?```', '', text, flags=re.S)
    text = re.sub(r'^\s*-\s+', '', text, flags=re.M)                 # Logseq bullets
    return text


def _split_sentences(text):
    protected = text.strip()
    for abbr in _SENTENCE_ABBREVS:
        protected = protected.replace(abbr, abbr.replace('.', '\x00'))
    parts = re.split(r'(?<=[.!?])\s+(?=[A-Z"“\'(])', protected)
    return [p.replace('\x00', '.').strip() for p in parts if p.strip()]


def _words(text):
    return re.findall(r"[A-Za-zÀ-ɏ]+(?:['’-][A-Za-zÀ-ɏ]+)*", text)


def _count_hedge(text_lower):
    simple = [r'\bcould\b', r'\bmight\b', r'\bmay\b', r'\bperhaps\b', r'\bpossibly\b', r'\bit seems\b',
              r'\bit appears\b', r'\bone might argue\b', r'\bit could be argued\b', r'\bappears to\b',
              r'\bseems to\b']
    count = sum(len(re.findall(p, text_lower)) for p in simple)
    for m in re.finditer(r'\bsuggests\b', text_lower):
        if 'that' in text_lower[m.end():m.end() + 40].split()[:3]:
            count += 1
    for m in re.finditer(r'\blikely\b', text_lower):
        prev = text_lower[max(0, m.start() - 20):m.start()].split()
        if not (prev and prev[-1] in ('most', 'very', 'more', 'highly')):
            count += 1
    return count


def mattr(words, window=MATTR_WINDOW):
    w = [x.casefold() for x in words]
    if len(w) < 150:
        return None
    window = min(window, len(w))
    seen = {}
    for x in w[:window]:
        seen[x] = seen.get(x, 0) + 1
    total, n = len(seen), 1
    for i in range(window, len(w)):
        out, inn = w[i - window], w[i]
        seen[out] -= 1
        if seen[out] == 0:
            del seen[out]
        seen[inn] = seen.get(inn, 0) + 1
        total += len(seen)
        n += 1
    return round(total / n / window, 3)


def features(text):
    """Counts per 1,000 words of the three Reinhart-style proxies, plus the word total."""
    words = _words(text)
    n = len(words) or 1
    pp = [m.group(1).casefold() for m in _PARTICIPLE_RE.finditer(text)
          if m.group(1).casefold() not in _NOT_PARTICIPLES]
    nom = _NOMINAL_RE.findall(text)
    nom = [x for x in nom if len(x) >= 7]
    pas = _PASSIVE_RE.findall(text)
    per = lambda c: round(c / n * 1000, 2)
    return {'words': len(words), 'present_participle_clauses': per(len(pp)),
            'nominalisations': per(len(nom)), 'passives': per(len(pas))}


def compute_metrics(text):
    text = _strip_markup(text)
    sentences = _split_sentences(text)
    wc = [len(_words(s)) for s in sentences]
    n = len(wc)
    if n == 0:
        return {'error': 'No sentences found'}
    mean = sum(wc) / n
    stdev = math.sqrt(sum((x - mean) ** 2 for x in wc) / (n - 1)) if n > 1 else 0.0
    words = _words(text)
    total = len(words)
    hedges = _count_hedge(text.lower())
    feats = features(text)
    return {
        'sentences': n,
        'sentence_inventory': [{'index': i + 1, 'word_count': c, 'sentence': s}
                               for i, (s, c) in enumerate(zip(sentences, wc))],
        'total_words': total,
        'sentence_length': {'mean': round(mean, 2), 'stdev': round(stdev, 2),
                            'cv': round(stdev / mean, 3) if mean else 0},
        'mattr_100': mattr(words),
        'hedge_count': hedges,
        'hedge_per_100_words': round(hedges / total * 100, 2) if total else 0,
        'features_per_1000_words': {k: v for k, v in feats.items() if k != 'words'},
        'guard': {'sufficient': total >= MIN_WORDS, 'min_words': MIN_WORDS,
                  'note': 'feature rates are unreliable below the minimum' if total < MIN_WORDS else 'ok'},
        'note': 'Descriptive only. No thresholds exist; compare with the writer\'s own baseline.',
    }


def compare_baseline(draft_text, baseline_texts):
    base = ' '.join(_strip_markup(t) for t in baseline_texts)
    bf = features(base)
    df = features(_strip_markup(draft_text))
    if bf['words'] < BASELINE_MIN_WORDS:
        return {'sufficient': False, 'baseline_words': bf['words'], 'min_words': BASELINE_MIN_WORDS,
                'note': 'baseline too short for a meaningful comparison'}
    out = {'sufficient': True, 'baseline_words': bf['words'], 'features': {}}
    for k in ('present_participle_clauses', 'nominalisations', 'passives'):
        out['features'][k] = {'draft': df[k], 'baseline': bf[k],
                              'ratio': round(df[k] / bf[k], 2) if bf[k] else None}
    out['note'] = ('Descriptive. Style changes over time and with genre; a ratio is context, not evidence '
                   'of machine authorship.')
    return out


def main(argv):
    args = list(argv)
    baseline = []
    if '--baseline' in args:
        i = args.index('--baseline')
        baseline = args[i + 1:]
        args = args[:i]
    if len(args) != 1:
        print(json.dumps({'error': 'Usage: compute_metrics.py <draft_file> [--baseline FILE ...]'}))
        return 1
    try:
        with open(args[0], encoding='utf-8') as f:
            text = f.read()
        base_texts = [open(p, encoding='utf-8').read() for p in baseline]
    except OSError as e:
        print(json.dumps({'error': str(e)}))
        return 1
    result = compute_metrics(text)
    if baseline and 'error' not in result:
        result['baseline_comparison'] = compare_baseline(text, base_texts)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
