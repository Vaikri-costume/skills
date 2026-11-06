#!/usr/bin/env python3
"""
style_check.py — find departures from the writer's own conventions (style profile Quick Reference).

Usage: style_check.py <draft_file> <style_profile_file>
Output: JSON on stdout: {"conventions": n, "total_findings": m, "findings": [...]} or {"error": "..."}.

Convention lines are read from the profile's FIRST section (its Quick Reference: everything before
the second heading). A convention is a list item of the form

    - prefer: per cent | avoid: %, percent
    - prefer: Ms | avoid: Ms.

`avoid` forms are separated by commas. Matching is exact, whole-word where the form is a word,
case-sensitive, in the writer's own prose only (quotations, URLs, wikilinks and the reference list
are skipped), so a quoted source keeps its own style. Findings carry the shared paragraph number,
the sentence number and opening words, the form found and the preferred form. This script finds;
the consistency agents judge intent. The strict British -ise policy is not a convention and is
never overridden here.

Exit 0 on success, 1 on error.
"""
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, 'shared'))
sys.path.insert(0, _HERE)
from extract_paragraphs import prose_paragraphs  # noqa: E402
from check_british_spelling import strip_noise, cut_at_references, _sentence_index  # noqa: E402

_CONV_RE = re.compile(r'^\s*[-*]\s*prefer:\s*(.+?)\s*\|\s*avoid:\s*(.+?)\s*$', re.IGNORECASE)


def read_conventions(profile_text):
    """[(prefer, [avoid, ...])] from the Quick Reference (text before the second heading)."""
    out, headings = [], 0
    for ln in profile_text.splitlines():
        if re.match(r'^#{1,6}\s', ln):
            headings += 1
            if headings > 2:      # title line + Quick Reference heading are allowed before the cut
                break
            continue
        m = _CONV_RE.match(ln)
        if m:
            avoid = [a.strip() for a in m.group(2).split(',') if a.strip()]
            out.append((m.group(1).strip(), avoid))
    return out


def _pattern(form):
    esc = re.escape(form)
    left = r'(?<![\w])' if re.match(r'\w', form) else ''
    right = r'(?![\w])' if re.search(r'\w$', form) else ''
    return re.compile(left + esc + right)


def find_departures(draft_text, conventions):
    findings = []
    body = cut_at_references(draft_text)
    for num, para in prose_paragraphs(body):
        clean = strip_noise(para)
        for prefer, avoids in conventions:
            for form in avoids:
                for m in _pattern(form).finditer(clean):
                    s_idx, opening = _sentence_index(clean, m.start())
                    findings.append({'paragraph': num, 'sentence': s_idx, 'sentence_opening_words': opening,
                                     'found': form, 'prefer': prefer,
                                     'note': f'writer convention: prefer "{prefer}" over "{form}"'})
    return findings


def main(argv):
    if len(argv) != 3:
        print(json.dumps({'error': 'usage: style_check.py <draft_file> <style_profile_file>'}))
        return 1
    try:
        draft = open(argv[1], encoding='utf-8').read()
        profile = open(argv[2], encoding='utf-8').read()
    except OSError as e:
        print(json.dumps({'error': str(e)}))
        return 1
    conv = read_conventions(profile)
    f = find_departures(draft, conv)
    print(json.dumps({'conventions': len(conv), 'total_findings': len(f), 'findings': f}, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
