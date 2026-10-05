#!/usr/bin/env python3
"""
synthesise_pairs.py — merge the findings of two independent agents that ran the
same check (an "A/B pair") into one list tagged with analysis confidence.

Usage:
  synthesise_pairs.py A.md B.md [--exact Check] [--substring "Current text"]
                      [--out merged.md] [--json]
  synthesise_pairs.py A.md --single       # one agent failed: everything UNVERIFIED

Match rule (same as the old SKILL.md prose): two findings match when every
--exact field is equal (case-insensitive) AND every --substring field is equal
or one contains the other (after whitespace/quote/case normalisation).

Result per finding:
  HIGH        both agents flagged it
  UNVERIFIED  only one agent flagged it, or it carries a [QUOTE-UNMATCHED]
              marker (quote not found in the draft), or one agent failed
UNVERIFIED findings are never dropped. For HIGH findings whose other fields
differ between agents, A's version is kept and a note is appended.

Exit codes: 0 ok, 1 usage or I/O error.
"""
import argparse
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from findings_lib import parse_findings, get, norm, render  # noqa: E402


def _same(a, b, exact, substring):
    for f in exact:
        if norm(get(a, f)) != norm(get(b, f)):
            return False
    for f in substring:
        x, y = norm(get(a, f)), norm(get(b, f))
        if not x or not y or not (x == y or x in y or y in x):
            return False
    return True


def synthesise(a_text, b_text, exact, substring, single=False):
    a = parse_findings(a_text)
    b = [] if single else parse_findings(b_text)
    used_b = set()
    merged = []
    for fa in a:
        match = None
        if not single:
            for i, fb in enumerate(b):
                if i not in used_b and _same(fa, fb, exact, substring):
                    match = i
                    break
        if match is not None:
            used_b.add(match)
            fb = b[match]
            conf = 'UNVERIFIED' if (fa['unmatched'] or fb['unmatched']) else 'HIGH'
            differs = [k for k in fa['order']
                       if k.casefold() not in {x.casefold() for x in exact + substring}
                       and k.casefold() not in ('location', 'severity')
                       and norm(get(fa, k)) != norm(get(fb, k))]
            note = 'description differs between agents' if differs else None
            merged.append((fa, conf, note))
        else:
            merged.append((fa, 'UNVERIFIED', None))
    for i, fb in enumerate(b):
        if i not in used_b:
            merged.append((fb, 'UNVERIFIED', None))
    return merged


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('a')
    ap.add_argument('b', nargs='?')
    ap.add_argument('--single', action='store_true', help='only A returned; tag everything UNVERIFIED')
    ap.add_argument('--exact', action='append', default=None, help='field that must match exactly (repeatable; default Check)')
    ap.add_argument('--substring', action='append', default=None, help='field matched by containment (repeatable; default "Current text")')
    ap.add_argument('--out')
    ap.add_argument('--json', action='store_true')
    args = ap.parse_args(argv)
    exact = args.exact if args.exact is not None else ['Check']
    substring = args.substring if args.substring is not None else ['Current text']
    try:
        a_text = open(args.a, encoding='utf-8').read()
        b_text = '' if (args.single or not args.b) else open(args.b, encoding='utf-8').read()
    except OSError as e:
        print(f'error: {e}', file=sys.stderr)
        return 1
    merged = synthesise(a_text, b_text, exact, substring, single=args.single or not args.b)
    if args.json:
        payload = [{'n': i, 'confidence': c, 'note': n, 'fields': f['fields']}
                   for i, (f, c, n) in enumerate(merged, 1)]
        out = json.dumps(payload, indent=2, ensure_ascii=False)
    else:
        out = '\n'.join(render(f, i, c, n) for i, (f, c, n) in enumerate(merged, 1))
        if not merged:
            out = '## No findings\n'
    if args.out:
        open(args.out, 'w', encoding='utf-8').write(out)
    else:
        sys.stdout.write(out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
