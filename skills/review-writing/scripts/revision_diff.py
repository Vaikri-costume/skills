#!/usr/bin/env python3
"""revision_diff.py - locate earlier feedback quotes in a revised draft.

Usage: revision_diff.py <earlier_feedback.md> <revised_draft>

Input contract: the earlier feedback holds finding blocks with a line
`Current text: "<exact quote>"` (the field every review-writing report uses).
Output: JSON on stdout, one entry per earlier quote:
  {"n": <finding number or index>, "quote": str,
   "state": "unchanged" | "reworded" | "absent",
   "paragraph": <paragraph number in the revised draft, or null>,
   "ratio": <best similarity 0-1>, "closest": <closest sentence or null>}
`unchanged` = the quote is still in the draft word for word (case and space
folded). `reworded` = a sentence is at least 0.6 similar but not equal.
`absent` = nothing close. This only locates text; whether the change
addressed the comment is the reviewer's judgement, never the script's.
Exit 2 and {"error": ...} on bad input.
"""
import difflib
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "shared"))
from extract_paragraphs import prose_paragraphs  # noqa: E402

QUOTE_RE = re.compile(r'^\s*Current text:\s*["“](.+?)["”]\s*$', re.M)
FINDING_RE = re.compile(r'^##\s*(?:\[QUOTE-UNMATCHED\]\s*)?Finding\s+(\d+)', re.M | re.I)


def fold(s):
    s = s.replace("‘", "'").replace("’", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", s).strip().casefold()


def sentences(text):
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [p.strip() for p in parts if p.strip()]


def earlier_quotes(text):
    out = []
    marks = [(m.start(), int(m.group(1))) for m in FINDING_RE.finditer(text)]
    for i, m in enumerate(QUOTE_RE.finditer(text)):
        n = i + 1
        for pos, num in marks:
            if pos <= m.start():
                n = num
        out.append((n, m.group(1)))
    return out


def diff(feedback_text, draft_text):
    paras = prose_paragraphs(draft_text)
    sents = []
    for num, ptext in paras:
        for s in sentences(ptext):
            sents.append((num, s))
    results = []
    for n, quote in earlier_quotes(feedback_text):
        fq = fold(quote)
        entry = {"n": n, "quote": quote, "state": "absent", "paragraph": None,
                 "ratio": 0.0, "closest": None}
        hit = next((num for num, ptext in paras if fq in fold(ptext)), None)
        if hit is not None:
            entry.update(state="unchanged", paragraph=hit, ratio=1.0, closest=quote)
        else:
            best, bs, bp = 0.0, None, None
            for num, s in sents:
                r = difflib.SequenceMatcher(None, fq, fold(s)).ratio()
                if r > best:
                    best, bs, bp = r, s, num
            entry["ratio"] = round(best, 3)
            if best >= 0.6:
                entry.update(state="reworded", paragraph=bp, closest=bs)
        results.append(entry)
    return results


def main(argv):
    if len(argv) != 3:
        print(json.dumps({"error": "Usage: revision_diff.py <earlier_feedback.md> <revised_draft>"}))
        return 2
    try:
        fb = open(argv[1], encoding="utf-8").read()
        dr = open(argv[2], encoding="utf-8").read()
    except OSError as e:
        print(json.dumps({"error": str(e)}))
        return 2
    res = diff(fb, dr)
    if not res:
        print(json.dumps({"error": "no 'Current text:' quotes found in the earlier feedback"}))
        return 2
    print(json.dumps(res, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
