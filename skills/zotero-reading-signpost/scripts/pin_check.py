#!/usr/bin/env python3
"""List summary stretches with no highlight comment behind them.

Usage: pin_check.py SUMMARY_FILE COMMENTS_FILE [--max-run N]
Cuts every comment phrase out of the summary and prints each remaining stretch (between
comments or sentence ends) that holds N or more content words (default 4; N is the smallest stretch
listed, not the largest allowed): a claim of the
summary that no highlight pins (the Every claim backed check). A tool, called by no step: read
each stretch listed; connecting prose that says what a point does is the writer's own and stays
(Aids understanding), and only a claim with no passage behind it comes out or gets a highlight.
Short linking stretches are not listed. Exit 0 when none, 1 when any, 2 on bad input.
"""
import re
import sys
from pathlib import Path

# `python3 -I` keeps the scripts folder off the import path, so add it to reach copy_check.py, which defines
# the cut rule once.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from copy_check import cut_pattern  # noqa: E402

# Stop words specific to this script; the other check scripts keep their own sets.
STOP = set("""about after also and are because been before between both but can does each from have here how into
its more most much must not only other over same should some such than that the their them then there these
they this those through thus too under until very was were what when where which while who will with within
without would yet""".split())


def main(argv):
    args = argv[1:]
    n = 4
    if "--max-run" in args:
        i = args.index("--max-run")
        try:
            n = int(args[i + 1])
        except (IndexError, ValueError):
            print(__doc__)
            return 2
        del args[i:i + 2]
    if len(args) != 2:
        print(__doc__)
        return 2
    s_p, c_p = Path(args[0]), Path(args[1])
    if not s_p.is_file() or not c_p.is_file():
        print("missing input file")
        return 2
    try:
        summary = s_p.read_text(encoding="utf-8").replace("’", "'")
        comment_lines = c_p.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as e:
        print(f"bad input: {e}")
        return 2
    comments = sorted((c.strip().replace("’", "'") for c in comment_lines if c.strip()), key=len, reverse=True)
    if not comments:
        print("no comments")
        return 2
    for c in comments:
        summary = re.sub(cut_pattern(c), "|", summary, flags=re.I)
    flagged = 0
    for stretch in re.split(r"[|.!?;:\n]", summary):
        ws = [w for w in re.findall(r"[a-z]+(?:['-][a-z]+)*", stretch.lower()) if len(w) > 3 and w not in STOP]
        if len(ws) >= n:
            flagged += 1
            print(f"UNPINNED: {stretch.strip()}")
    print(f"{flagged} unpinned stretches")
    return 1 if flagged else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
