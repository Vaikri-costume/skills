#!/usr/bin/env python3
"""
change_table.py — build the two end-of-report tables from the synthesised findings.

Usage: change_table.py <findings.md> [--verdicts verdicts.txt]
  findings.md    the combined, renumbered `## Finding [n]` blocks (after pair synthesis)
  verdicts.txt   `Finding n: label` lines from synthesise_verdicts.py (nine two-challenger labels or the plain --single labels upheld, disputed, ambiguous, unaddressed) (omit when the
                 challenger step was skipped: every finding then counts as unadjudicated)

Output (markdown on stdout):
  ## Change table (was, now, why)
      one row for each Check 1-3 finding that carries a Proposed fix and whose verdict is
      confirmed, partial-upheld or unverified-challenger (or has no verdict). Columns:
      Para | Was | Now | Why. `Why` is the finding's Reason field, else the check's name.
      A row is a PROPOSED change; nothing in the draft is edited.
  ## Flagged, not changed
      every other finding: Check 4 and 5 (diagnostic, no replacement text), findings the
      challengers split on, left ambiguous or disputed, and any finding without a Proposed
      fix. Columns: Para | Text | Check | Why flagged | Status.

  ## Register audit
      one row for each register type tagged at the start of a Check 5 finding's Pattern
      (`[colloquialism]`, `[contraction]`, `[vague-quantifier]`, `[abbreviation]`,
      `[uncited-claim]`, `[register-shift]`): count and paragraphs. Omitted when there are
      no Check 5 findings.

Deterministic: same input, same output. Exit 0, or 1 with {"error": ...} on stdout.
"""
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, 'shared'))
from findings_lib import parse_findings, get  # noqa: E402

CHECK_NAMES = {'1': 'grammar', '2': 'typo', '3': 'British spelling',
               '4': 'consistency', '5': 'register'}
CHANGE_LABELS = {'confirmed', 'partial-upheld', 'unverified-challenger', 'upheld', ''}
STATUS = {'disputed': 'disputed by the single challenger',
          'ambiguous': 'challenger asked a question',
          'unaddressed': 'not adjudicated',
          'confirmed-disputed': 'disputed by both challengers',
          'partial-disputed': 'disputed by the one challenger that returned',
          'split': 'challengers disagreed',
          'partial-ambiguous': 'challenger asked a question',
          'partial-unaddressed': 'not adjudicated'}


def _cell(s):
    return (s or '').replace('|', '\\|').replace('\n', ' ').strip()


def _para(f):
    m = re.search(r'paragraph\s+(\d+)', get(f, 'Location'), re.IGNORECASE)
    return m.group(1) if m else '?'


def _check(f):
    m = re.search(r'\d', get(f, 'Check'))
    return m.group(0) if m else '?'


def read_verdicts(text):
    out = {}
    for m in re.finditer(r'^Finding\s+(\d+):\s*([a-z\-]+)\s*$', text or '', re.MULTILINE):
        out[int(m.group(1))] = m.group(2)
    return out


REGISTER_TYPES = ('colloquialism', 'contraction', 'vague-quantifier', 'abbreviation',
                  'uncited-claim', 'register-shift')


def register_audit(findings):
    """Markdown table of Check 5 findings by tagged type; '' when there are none."""
    rows = {}
    for f in findings:
        if _check(f) != '5':
            continue
        m = re.match(r'\s*\[([a-z\-]+)\]', get(f, 'Pattern'))
        kind = m.group(1) if m and m.group(1) in REGISTER_TYPES else 'other'
        rows.setdefault(kind, []).append(_para(f))
    if not rows:
        return ''
    order = [k for k in REGISTER_TYPES if k in rows] + (['other'] if 'other' in rows else [])
    out = ['', '## Register audit', '', '| Type | Count | Paragraphs |', '|---|---|---|']
    for k in order:
        paras = sorted(set(rows[k]), key=lambda x: (not x.isdigit(), int(x) if x.isdigit() else 0))
        out.append(f'| {k} | {len(rows[k])} | {", ".join(paras)} |')
    return '\n'.join(out) + '\n'


def _overlaps(findings):
    """{finding number: [numbers of findings in the same paragraph whose Current text it contains]}."""
    from findings_lib import norm
    out = {}
    for f in findings:
        a = norm(get(f, 'Current text'))
        for g in findings:
            if g is f:
                continue
            b = norm(get(g, 'Current text'))
            if a and b and _para(f) == _para(g) and a != b and b in a:
                out.setdefault(f['n'], []).append(g['n'])
    return out


def build(findings, verdicts):
    ov = _overlaps(findings)
    changes, flagged = [], []
    for f in findings:
        label = verdicts.get(f['n'], '')
        fix = get(f, 'Proposed fix')
        chk = _check(f)
        if chk in '123' and fix and label in CHANGE_LABELS:
            why = get(f, 'Reason') or CHECK_NAMES.get(chk, '')
            if f['n'] in ov:
                why += '; overlaps finding ' + ', '.join(str(n) for n in ov[f['n']]) + ' (apply one edit, not both)'
            changes.append((_para(f), get(f, 'Current text'), fix, why))
        else:
            if not fix and chk in '123':
                status = 'no replacement text proposed'
            elif chk in '45':
                status = 'diagnostic; the writer decides'
            else:
                status = STATUS.get(label, 'not adjudicated')
            if chk in '45' and label in STATUS:
                status += '; ' + STATUS[label]
            why = '; '.join(x for x in (get(f, 'Pattern'), get(f, 'Concern')) if x) or get(f, 'Reason') or CHECK_NAMES.get(chk, '')
            if f['n'] in ov:
                status += '; overlaps finding ' + ', '.join(str(n) for n in ov[f['n']])
            flagged.append((_para(f), get(f, 'Current text'), CHECK_NAMES.get(chk, chk), why, status))
    out = ['## Change table (was, now, why)', '']
    if changes:
        out += ['| Para | Was | Now | Why |', '|---|---|---|---|']
        out += [f'| {_cell(p)} | {_cell(w)} | {_cell(n)} | {_cell(y)} |' for p, w, n, y in changes]
    else:
        out.append('No changes proposed.')
    out += ['', '## Flagged, not changed', '']
    if flagged:
        out += ['| Para | Text | Check | Why flagged | Status |', '|---|---|---|---|---|']
        out += [f'| {_cell(p)} | {_cell(t)} | {_cell(c)} | {_cell(y)} | {_cell(s)} |' for p, t, c, y, s in flagged]
    else:
        out.append('Nothing flagged without a proposed change.')
    return '\n'.join(out) + '\n' + register_audit(findings)


def main(argv):
    if len(argv) < 2:
        print(json.dumps({'error': 'usage: change_table.py <findings.md> [--verdicts verdicts.txt]'}))
        return 1
    verdicts = {}
    try:
        if '--verdicts' in argv:
            with open(argv[argv.index('--verdicts') + 1], encoding='utf-8') as fh:
                verdicts = read_verdicts(fh.read())
        with open(argv[1], encoding='utf-8') as fh:
            findings = parse_findings(fh.read())
    except (OSError, IndexError) as e:
        print(json.dumps({'error': str(e)}))
        return 1
    sys.stdout.write(build(findings, verdicts))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
