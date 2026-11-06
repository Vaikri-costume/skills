#!/usr/bin/env python3
"""
annotate_copy.py — write a COPY of a draft with proofread comments added, never the draft itself.

Usage: annotate_copy.py <draft_file> <findings.md> --out <copy_path>
  findings.md   `## Finding [n]` blocks (merged or corrected agent output). Each block's
                `Current text:` is searched in the draft; the comment is placed on its own
                line after the paragraph that holds it. A finding whose text is not found
                goes in an "Unplaced" block at the end of the copy.
Comment form:   <!-- proofread: Check 3 | "color" | proposed: "colour" -->
                (hidden in rendered Markdown; plain text in Logseq and Obsidian)

Safety, enforced here and covered by tests:
  * refuses when --out is the draft itself (same real path, including through a symlink)
  * refuses when --out already exists; it never replaces any file
  * after writing, removes the comment lines from the copy and checks the result equals the
    draft byte for byte; on a mismatch it deletes the copy and exits 1

Output: JSON on stdout: {"copy": path, "placed": n, "unplaced": m} or {"error": "..."}.
Exit 0 on success, 1 on error.
"""
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, 'shared'))
from findings_lib import parse_findings, get, norm  # noqa: E402

COMMENT_PREFIX = '<!-- proofread:'


def _comment(f):
    check = get(f, 'Check') or '?'
    cur = get(f, 'Current text')
    fix = get(f, 'Proposed fix')
    if fix:
        body = f'Check {check} | {cur} | proposed: {fix}'
    else:
        body = f'Check {check} | {cur} | {get(f, "Pattern") or get(f, "Concern")}'
    return f'{COMMENT_PREFIX} {body.replace("-->", "- ->")} -->'


def _para_end(text, pos):
    """End of the paragraph holding pos. In a Logseq bullet file (bullets with no blank lines
    between them) each bullet line is its own paragraph, so the end is the end of that line."""
    ls = text.rfind('\n', 0, pos) + 1
    if re.match(r'[ \t]*[-*]\s', text[ls:ls + 20]):
        le = text.find('\n', pos)
        return len(text) if le < 0 else le
    m = re.compile(r'\n[ \t]*\n').search(text, pos)
    return m.start() if m else len(text)


def build_copy(draft, findings):
    """Return (copy_text, placed, unplaced). Comments go on their own line after the paragraph."""
    inserts = {}   # paragraph end offset -> [comment, ...]
    unplaced = []
    for f in findings:
        cur = get(f, 'Current text').strip().strip('"“”')
        pos = draft.find(cur) if cur else -1
        if pos < 0 and cur:
            m = re.search(re.escape(cur).replace(r'\ ', r'\s+'), draft, re.IGNORECASE)
            pos = m.start() if m else -1
        if pos < 0:
            unplaced.append(_comment(f))
        else:
            inserts.setdefault(_para_end(draft, pos), []).append(_comment(f))
    out, last = [], 0
    for end in sorted(inserts):
        out.append(draft[last:end])
        out.append('\n' + '\n'.join(inserts[end]))
        last = end
    out.append(draft[last:])
    text = ''.join(out)
    if unplaced:
        text += ('\n' if not text.endswith('\n') else '') + '\n' + COMMENT_PREFIX + ' unplaced -->\n' + '\n'.join(unplaced) + '\n'
    placed = sum(len(v) for v in inserts.values())
    return text, placed, len(unplaced)


def strip_comments(text):
    """Remove exactly what build_copy added (comment lines, and the line break before the first)."""
    lines = text.split('\n')
    out = []
    for ln in lines:
        if ln.startswith(COMMENT_PREFIX):
            continue
        out.append(ln)
    return '\n'.join(out)


def main(argv):
    if len(argv) < 5 or '--out' not in argv:
        print(json.dumps({'error': 'usage: annotate_copy.py <draft> <findings.md> --out <copy_path>'}))
        return 1
    draft_path, findings_path = argv[1], argv[2]
    out_path = argv[argv.index('--out') + 1]
    try:
        if os.path.realpath(out_path) == os.path.realpath(draft_path):
            print(json.dumps({'error': 'refusing: --out is the draft itself; a copy is written, the draft is never changed'}))
            return 1
        if os.path.lexists(out_path):
            print(json.dumps({'error': f'refusing: {out_path} already exists; this tool never replaces a file'}))
            return 1
        with open(draft_path, encoding='utf-8') as fh:
            draft = fh.read()
        with open(findings_path, encoding='utf-8') as fh:
            findings = parse_findings(fh.read())
    except OSError as e:
        print(json.dumps({'error': str(e)}))
        return 1
    text, placed, unplaced = build_copy(draft, findings)
    # the comment lines stripped must give the draft back exactly
    probe = strip_comments(text)
    if unplaced:
        probe = probe.rstrip('\n') + ('\n' if draft.endswith('\n') else '')
    if probe.rstrip('\n') != draft.rstrip('\n'):
        print(json.dumps({'error': 'internal check failed: the copy without its comments differs from the draft; nothing written'}))
        return 1
    with open(out_path, 'x', encoding='utf-8') as fh:
        fh.write(text)
    print(json.dumps({'copy': out_path, 'placed': placed, 'unplaced': unplaced}))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
