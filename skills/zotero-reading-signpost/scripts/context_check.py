#!/usr/bin/env python3
"""Print the sentence before and the sentence after each planned highlight.

Usage: context_check.py PLAN_JSON PAGES_DIR
PLAN_JSON: the plan, a JSON list of objects with n, comment, page and quote (as for plan_check.py).
PAGES_DIR: the page texts as PAGES_DIR/p<page>.txt (as SKILL.md step 5 saves them).
For each highlight it prints the comment, then BEFORE: the sentence just before the quote and
AFTER: the sentence just after it, on the same page (empty at a page edge). These are the places
where the text most often gives a claim's reason or evidence, or the back-reference the claim
depends on; read each pair and decide whether the highlight, or a highlight the summary joins to
it, must carry it (Shows why, references/method.md section 3). A quote not found on its page is
listed as NOT PLACED. Exit 0 when every quote is placed, 1 when any is not, 2 on bad input.
"""
import json
import re
import sys
from pathlib import Path

# `python3 -I` keeps the scripts folder off the import path, so add it to reach anchor_check.py.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from anchor_check import normalise  # noqa: E402

SENT_END = re.compile(r"(?<=[.!?])[\"'”’)]*\s+")


def around(page_text, quote):
    """Return (before, after) sentences around the quote in the page text, or None if not found."""
    page_norm, mapping = normalise(page_text)
    part_norm = normalise(quote.strip())[0].strip()
    start = page_norm.find(part_norm)
    end = start + len(part_norm) - 1
    if start < 0:
        # As anchor_check.py and plan_check.py: ignore hyphens, dashes and spaces (a compound split at a line end).
        keep = [i for i, c in enumerate(page_norm) if not re.match(r"[-\s]", c)]
        key = re.sub(r"[-\s]", "", part_norm)
        hit = "".join(page_norm[i] for i in keep).find(key) if key else -1
        if hit < 0:
            return None
        start, end = keep[hit], keep[hit + len(key) - 1]
    s = mapping[start]
    e = mapping[end] + 1
    head, tail = " ".join(page_text[:s].split()), " ".join(page_text[e:].split())
    head_sents = [x for x in SENT_END.split(head.strip()) if x.strip()]
    before = ""
    if head_sents:
        last = head_sents[-1]
        # A quote that starts mid-sentence: show that sentence's start, and the one before it.
        before = last if head.rstrip().endswith((".", "!", "?", "\"", "”", "'", "’", ")")) else \
            (" ".join(head_sents[-2:]) if len(head_sents) > 1 else last)
    tail_sents = [x for x in SENT_END.split(tail.strip()) if x.strip()]
    after = tail_sents[0] if tail_sents else ""
    if after and not tail.lstrip()[:1].isupper() and len(tail_sents) > 1:
        after = after + " " + tail_sents[1]
    return before, after


def main(argv):
    if len(argv) != 3:
        print(__doc__)
        return 2
    try:
        plan = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
        pages = Path(argv[2])
        if not pages.is_dir():
            raise OSError(f"not a folder: {pages}")
        for h in plan:
            int(h["n"]), int(h["page"])
            if not isinstance(h["comment"], str) or not isinstance(h["quote"], str):
                raise TypeError(f"highlight {h['n']}: comment and quote must be text")
    except (OSError, ValueError, KeyError, TypeError) as e:
        print(f"bad input: {e}")
        return 2
    missing = 0
    for h in plan:
        page_file = pages / f"p{int(h['page'])}.txt"
        try:
            text = page_file.read_text(encoding="utf-8") if page_file.is_file() else ""
        except (OSError, UnicodeDecodeError) as e:
            print(f"bad input: {e}")
            return 2
        got = around(text, h["quote"]) if text else None
        print(f"[{h['n']}] {h['comment']} (page {h['page']})")
        if got is None:
            print("  NOT PLACED: the quote is not found on its page (anchor_check.py says why)")
            missing += 1
            continue
        print(f"  BEFORE: {got[0]}")
        print(f"  AFTER:  {got[1]}")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
