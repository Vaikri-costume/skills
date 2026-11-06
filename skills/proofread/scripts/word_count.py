#!/usr/bin/env python3
"""
word_count.py — word count and deletion-only cut candidates for the proofread cut log.

Usage: word_count.py <draft_file> [--limit N]
Output: JSON on stdout, or {"error": "..."}.

  counted               plain statement of what the count includes and excludes
  words                 body words: prose paragraphs, reference list excluded,
                        quoted text included (quotations count towards a limit)
  words_with_references body words plus the reference list
  limit / over_by       the stated limit and how far over it the body is (null when no limit)
  per_paragraph         [{"paragraph": n, "words": w}] numbered by the shared paragraph map
  cut_candidates        deletion-only suggestions: a filler word or phrase whose removal
                        leaves the sentence grammatical, with the words saved. Candidates
                        inside quotations are never listed. This script finds; the writer
                        decides, and nothing is rewritten.
  candidate_words_saved sum of the words saved by every listed candidate
  words_after_all_candidates   body words if every candidate were deleted
  meets_limit_if_all_applied   true/false against the limit (null when no limit)

Exit 0 on success, 1 on error.
"""
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, 'shared'))
from extract_paragraphs import prose_paragraphs  # noqa: E402
from check_british_spelling import cut_at_references, strip_noise  # noqa: E402

# Fillers that can be deleted outright. Longer phrases first.
FILLERS = [
    'it should be noted that', 'it is important to note that', 'it is worth noting that',
    'needless to say', 'as a matter of fact', 'for all intents and purposes',
    'in fact', 'of course', 'basically', 'essentially', 'actually', 'really',
    'very', 'quite', 'simply', 'just',
]
_FILLER_RE = re.compile(r'\b(' + '|'.join(re.escape(f) for f in FILLERS) + r')\b', re.IGNORECASE)
_QUOTE_RE = re.compile(r'"[^"]*"|“[^”]*”')


def count_words(text):
    return len(re.findall(r"[A-Za-z0-9À-ɏ]+(?:['’\-][A-Za-z0-9À-ɏ]+)*", text))


def analyse(text, limit=None):
    body_text = cut_at_references(text)
    body = prose_paragraphs(body_text)
    per = [{'paragraph': n, 'words': count_words(p)} for n, p in body]
    words = sum(x['words'] for x in per)
    full = sum(count_words(p) for _, p in prose_paragraphs(text))
    cands = []
    for n, p in body:
        masked = _QUOTE_RE.sub(lambda m: ' ' * len(m.group()), p)
        for m in _FILLER_RE.finditer(masked):
            cands.append({'paragraph': n, 'delete': p[m.start():m.end()],
                          'words_saved': count_words(m.group()),
                          'context': p[max(0, m.start() - 25):m.end() + 25].replace('\n', ' ')})
    out = {'counted': 'body prose; headings, property lines and the reference list excluded; quotations included',
           'words': words, 'words_with_references': full, 'limit': limit,
           'over_by': (max(0, words - limit) if limit is not None else None),
           'per_paragraph': per, 'cut_candidates': cands,
           'candidate_words_saved': sum(c['words_saved'] for c in cands)}
    out['words_after_all_candidates'] = words - out['candidate_words_saved']
    out['meets_limit_if_all_applied'] = (None if limit is None else out['words_after_all_candidates'] <= limit)
    return out


def main(argv):
    if len(argv) < 2:
        print(json.dumps({'error': 'usage: word_count.py <draft_file> [--limit N]'}))
        return 1
    limit = None
    if '--limit' in argv:
        try:
            limit = int(argv[argv.index('--limit') + 1])
        except (ValueError, IndexError):
            print(json.dumps({'error': '--limit needs a whole number'}))
            return 1
    try:
        with open(argv[1], encoding='utf-8') as fh:
            text = fh.read()
    except OSError as e:
        print(json.dumps({'error': f'cannot read {argv[1]}: {e}'}))
        return 1
    print(json.dumps(analyse(text, limit), indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
