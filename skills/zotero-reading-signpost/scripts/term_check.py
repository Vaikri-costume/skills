#!/usr/bin/env python3
"""List summary words that the source text never uses (candidate synonym swaps).

Usage: term_check.py SOURCE_TEXT SUMMARY_FILE [--comments COMMENTS_FILE] [--plan PLAN_JSON]
SOURCE_TEXT: text of the pages summarised. SUMMARY_FILE: the summary (plain text).
The text's own wording is kept (the Text's own words check), so a content word in the
summary that is absent from the text (no word with the same first five letters) may be a
swap of the text's wording. Comment phrases are skipped (they are the text's words
by construction). With --plan (a JSON list of objects with comment and quote), also prints each comment word
that its own quote does not use (a swap inside the comment). Prints each such word with its sentence. Exit 0 when none, 1 when any,
2 on bad input. Linking words of your own are fine; the list is for you to read: replace
each word that stands in for the text's wording with that wording.
"""
import re
import sys
import unicodedata
from pathlib import Path

# `python3 -I` keeps the scripts folder off the import path, so add it to reach copy_check.py, which defines
# the line-end hyphen pattern once.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from copy_check import LINE_END_HYPHEN, cut_pattern  # noqa: E402

# Stop words specific to this script; the other check scripts keep their own sets.
STOP = set("""about above after again against also among and are because been before being between both but can
cannot could does doing down during each either even from further have having here how into its itself just
like more most much must none nor not only other otherwise our out over same should some such than that the
their theirs them then there these they this those through thus too under until very was were what when where
which while who whom why will with within without would yet you your""".split())


def words(text):
    # split hyphenated compounds, as copy_check.py does: "market-driven" gives "market" and "driven"
    text = unicodedata.normalize("NFKC", text)  # ligatures such as the fi ligature read as letters, as in copy_check.py
    return re.findall(r"[a-z]+(?:'[a-z]+)?", text.lower().replace("’", "'"))


def source_words(text):
    """Words of the source with a line-end hyphen read both ways (copy_check.py's LINE_END_HYPHEN, which,
    unlike anchor_check.py, also allows spaces or tabs between the hyphen and the line break):
    before a lowercase letter it may be a soft hyphen (gov-/ernment joins) or a compound's hyphen
    (market-/driven keeps two words); before a capital or digit it is a genuine hyphen. Both readings count as the text's words."""
    def fix(soft):
        return lambda m: m.group(1) if soft and m.group(1).islower() else "-" + m.group(1)
    out = set()
    for soft in (True, False):
        out |= set(words(LINE_END_HYPHEN.sub(fix(soft), text)))
    return out


def main(argv):
    args = argv[1:]
    comments_path = None
    plan_path = None
    if "--plan" in args:
        i = args.index("--plan")
        if i + 1 >= len(args):
            print(__doc__)
            return 2
        plan_path = Path(args[i + 1])
        del args[i:i + 2]
    if "--comments" in args:
        i = args.index("--comments")
        if i + 1 >= len(args):
            print(__doc__)
            return 2
        comments_path = Path(args[i + 1])
        del args[i:i + 2]
    if len(args) != 2:
        print(__doc__)
        return 2
    src_p, sum_p = Path(args[0]), Path(args[1])
    if not src_p.is_file() or not sum_p.is_file() or (comments_path and not comments_path.is_file()):
        print("missing input file")
        return 2
    plan = []
    if plan_path:
        import json
        if not plan_path.is_file():
            print("missing input file")
            return 2
        try:
            plan = json.loads(plan_path.read_text())
            for h in plan:
                if not isinstance(h["comment"], str) or not isinstance(h["quote"], str):
                    raise TypeError("comment and quote must be text")
        except (ValueError, KeyError, TypeError):
            print("bad plan file")
            return 2
    try:
        source_text = src_p.read_text(encoding="utf-8")
        summary = sum_p.read_text(encoding="utf-8")
        comment_lines = comments_path.read_text(encoding="utf-8").splitlines() if comments_path else []
    except (OSError, UnicodeDecodeError) as e:
        print(f"bad input: {e}")
        return 2
    source = source_words(source_text)
    stems = {w[:5] for w in source}
    if comments_path:
        for c in comment_lines:
            c = c.strip()
            if c:
                summary = re.sub(cut_pattern(c), " ", summary, flags=re.I)
    flagged = 0
    for sent in re.split(r"(?<=[.!?])\s+", summary):
        bad = []
        for w in words(sent):
            if len(w) < 4 or w in STOP or w in source or w[:5] in stems:
                continue
            bad.append(w)
        if bad:
            flagged += len(bad)
            print(f"NOT IN TEXT: {', '.join(bad)} | {sent.strip()[:140]}")
    if plan_path:
        # The parts of a page-split passage share one n; a comment's words may sit in either part.
        joined = {}
        for h in plan:
            joined[h.get("n")] = joined.get(h.get("n"), "") + " " + h["quote"]
        for h in plan:
            q = {w for w in words(joined[h.get("n")])}
            qs = {w[:5] for w in q}
            bad = [w for w in words(h["comment"]) if len(w) >= 4 and w not in STOP and w not in q and w[:5] not in qs]
            if bad:
                flagged += len(bad)
                print(f"COMMENT WORD NOT IN ITS QUOTE: #{h.get('n')} {h['comment']} | {', '.join(bad)}")
    print(f"{flagged} words not used by the text or by their quote")
    return 1 if flagged else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
