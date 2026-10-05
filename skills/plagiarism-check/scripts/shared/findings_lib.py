#!/usr/bin/env python3
"""
findings_lib.py — parse and render the `## Finding [n]` blocks that every
writing-skill agent returns. Shared by synthesise_pairs.py and
synthesise_verdicts.py.

A block starts at `## Finding <n>` (optionally prefixed `[QUOTE-UNMATCHED]`) and
ends at the next `## ` heading. Inside it, `Field: value` lines are fields.
"""
import re

BLOCK_RE = re.compile(r'^##\s*(\[QUOTE-UNMATCHED\]\s*)?Finding\s+(\d+)[^\n]*\n(.*?)(?=^##\s|\Z)',
                      re.DOTALL | re.MULTILINE | re.IGNORECASE)
FIELD_RE = re.compile(r'^([A-Za-z][A-Za-z0-9 _:\-]*?):\s*(.*)$')


def norm(s):
    """Case-fold, strip quotes and collapse whitespace for comparison."""
    s = (s or '').strip().strip('"“”').strip()
    return re.sub(r'\s+', ' ', s).casefold()


def parse_findings(text):
    """Return a list of dicts: {n, unmatched, fields{name: value}, raw}.
    Field names keep their original capitalisation; lookup helpers are case-insensitive."""
    out = []
    for m in BLOCK_RE.finditer(text or ''):
        fields = {}
        order = []
        for line in m.group(3).splitlines():
            fm = FIELD_RE.match(line.strip())
            if fm and fm.group(1) not in fields:
                fields[fm.group(1)] = fm.group(2).strip()
                order.append(fm.group(1))
        out.append({'n': int(m.group(2)), 'unmatched': bool(m.group(1)),
                    'fields': fields, 'order': order})
    return out


def get(finding, name, default=''):
    for k, v in finding['fields'].items():
        if k.casefold() == name.casefold():
            return v
    return default


def render(finding, number, confidence=None, note=None):
    """Render one finding back into the canonical block, renumbered."""
    prefix = '[QUOTE-UNMATCHED] ' if finding.get('unmatched') else ''
    lines = [f'## {prefix}Finding {number}']
    for k in finding['order']:
        lines.append(f'{k}: {finding["fields"][k]}')
    if confidence:
        lines.append(f'Analysis confidence: {confidence}')
    if note:
        lines.append(f'Note: {note}')
    return '\n'.join(lines) + '\n'
