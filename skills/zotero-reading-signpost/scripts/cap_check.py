#!/usr/bin/env python3
"""Check the summary against the length cap.

Usage: cap_check.py SUMMARY_FILE PAGE_TEXT_FILE [PAGE_TEXT_FILE ...] [--cap PERCENT]
SUMMARY_FILE: the summary as plain text ([n] highlight markers, if present, are not counted).
PAGE_TEXT_FILE: the text of each page summarised (for example DIR/p<page>.txt).
--cap PERCENT: the cap as a share of the pages' word count (default 15, the profile's
summary_length_cap).
Prints the summary's word count, the pages' word count, the cap in words and whether the
summary is within it. Words are runs of letters or digits, apostrophes and hyphens inside a
word kept. The cap is a guide: over it is reported, not a fail (SKILL.md step 9). Exit 0 when
within the cap, 1 when over it, 2 on bad input.
"""
import re
import sys
from pathlib import Path

WORD = re.compile(r"[^\W_]+(?:['’\-][^\W_]+)*")
MARK = re.compile(r"\[\d+\]")


def count(text):
    return len(WORD.findall(MARK.sub("", text)))


def main(argv):
    args = argv[1:]
    cap = 15.0
    if "--cap" in args:
        i = args.index("--cap")
        try:
            cap = float(args[i + 1].rstrip("%"))
        except (IndexError, ValueError):
            print("bad input: --cap needs a number")
            return 2
        del args[i:i + 2]
    if len(args) < 2 or cap <= 0:
        print(__doc__)
        return 2
    try:
        summary = count(Path(args[0]).read_text(encoding="utf-8"))
        pages = sum(count(Path(p).read_text(encoding="utf-8")) for p in args[1:])
    except (OSError, UnicodeDecodeError) as e:
        print(f"bad input: {e}")
        return 2
    if pages == 0:
        print("bad input: the page texts hold no words")
        return 2
    limit = int(pages * cap / 100)
    within = summary <= limit
    print(f"summary {summary} words; pages {pages} words; cap {cap:g}% = {limit} words; "
          f"{'within the cap' if within else f'over the cap by {summary - limit} words'}")
    return 0 if within else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
