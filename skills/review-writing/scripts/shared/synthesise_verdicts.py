#!/usr/bin/env python3
"""
synthesise_verdicts.py — combine two challenger agents' verdicts into the nine
verdict-confidence labels (confirmed, confirmed-disputed, split, ambiguous,
partial-upheld, partial-disputed, partial-ambiguous, partial-unaddressed,
unverified-challenger).

Usage:
  synthesise_verdicts.py CHALLENGER_A.md CHALLENGER_B.md --findings N
  synthesise_verdicts.py CHALLENGER_A.md --single --findings N   # one challenger

Challenger output blocks look like:
  ## Challenger assessment: Finding 3
  ...reasoning...
  Verdict: UPHELD | DISPUTED: reason | AMBIGUOUS: question | NOT ASSESSED — reason

Output: one line per finding, `Finding n: label`, then (after a blank line) a
detail section carrying each challenger's reasoning-free verdict text so the
presentation step can show disputed reasons and ambiguous questions verbatim.

With --single (the plagiarism-check design, one verifying challenger) the label
is the plain verdict word: upheld | disputed | ambiguous | unaddressed.
"""
import argparse
import re
import sys

BLOCK_RE = re.compile(r'^##\s*Challenger assessment:\s*Finding\s+(\d+)[^\n]*\n(.*?)(?=^##\s*Challenger assessment:|\Z)',
                      re.DOTALL | re.MULTILINE | re.IGNORECASE)
VERDICT_RE = re.compile(r'^\s*\**Verdict:?\**\s*\[?\s*(UPHELD|DISPUTED|AMBIGUOUS|NOT ASSESSED)\b[:\s—\-]*(.*?)\]?\s*$',
                        re.IGNORECASE | re.MULTILINE)


def parse(text):
    """Return {finding_number: (kind, detail)} using the LAST Verdict line in each block."""
    out = {}
    for m in BLOCK_RE.finditer(text or ''):
        verdicts = VERDICT_RE.findall(m.group(2))
        if not verdicts:
            continue
        kind, detail = verdicts[-1]
        kind = kind.upper().replace('NOT ASSESSED', 'NONE')
        out[int(m.group(1))] = (kind, detail.strip())
    return out


def label(a, b):
    """Two-challenger label. a/b are a verdict kind or None."""
    if a is None and b is None:
        return 'unverified-challenger'
    if a is None or b is None:
        k = a or b
        return {'UPHELD': 'partial-upheld', 'DISPUTED': 'partial-disputed',
                'AMBIGUOUS': 'partial-ambiguous', 'NONE': 'partial-unaddressed'}[k]
    if 'AMBIGUOUS' in (a, b):
        return 'ambiguous'
    if a == b == 'UPHELD':
        return 'confirmed'
    if a == b == 'DISPUTED':
        return 'confirmed-disputed'
    if 'NONE' in (a, b):
        other = a if b == 'NONE' else b
        return {'UPHELD': 'partial-upheld', 'DISPUTED': 'partial-disputed'}.get(other, 'partial-unaddressed')
    return 'split'


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('a')
    ap.add_argument('b', nargs='?')
    ap.add_argument('--single', action='store_true')
    ap.add_argument('--findings', type=int, required=True, help='number of findings sent to the challenger(s)')
    args = ap.parse_args(argv)
    try:
        va = parse(open(args.a, encoding='utf-8').read())
        vb = {} if (args.single or not args.b) else parse(open(args.b, encoding='utf-8').read())
    except OSError as e:
        print(f'error: {e}', file=sys.stderr)
        return 1
    single = args.single or not args.b
    lines, detail = [], []
    for n in range(1, args.findings + 1):
        ka = va.get(n, (None, ''))
        kb = vb.get(n, (None, ''))
        if single:
            k = ka[0]
            lab = {'UPHELD': 'upheld', 'DISPUTED': 'disputed', 'AMBIGUOUS': 'ambiguous'}.get(k, 'unaddressed')
        else:
            lab = label(ka[0], kb[0])
        lines.append(f'Finding {n}: {lab}')
        if ka[0] and ka[1]:
            detail.append(f'Finding {n} challenger A {ka[0]}: {ka[1]}')
        if kb[0] and kb[1]:
            detail.append(f'Finding {n} challenger B {kb[0]}: {kb[1]}')
    sys.stdout.write('\n'.join(lines) + '\n')
    if detail:
        sys.stdout.write('\n' + '\n'.join(detail) + '\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
