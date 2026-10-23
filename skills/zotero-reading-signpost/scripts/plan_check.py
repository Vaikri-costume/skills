#!/usr/bin/env python3
"""Check a highlight plan and its summary against each other in one pass.

Usage: plan_check.py PLAN_JSON SUMMARY_FILE [--pages DIR]
PLAN_JSON: a JSON list of objects with n, comment, page, quote and, for a word the text
defines, "term": true. SUMMARY_FILE: the summary as plain text, each comment followed by its
highlight number in square brackets, e.g. "informed by peacetime inequalities [1]".
--pages DIR: the page texts as DIR/p<page>.txt (as SKILL.md step 5 saves them); with it the highlights
are also placed on their pages, so text order and overlaps are checked by position.

On the plan:
  NOT PLACED    (with --pages) a quote not found on its page (letters compared without case; letter
                case and repeats on the page are anchor_check.py's checks); anchor_check.py says why
  ORDER        a highlight number out of text order (by page, and by position with --pages)
  INSIDE        a highlight that sits inside, or overlaps, another highlight on the same page
  TERM          a term whose own words are not in its highlight (no defining passage)
  LONG COMMENT  a comment over five words
  SAME CLAIM    a comment that is most of its quote (the quote adds almost nothing)
  NEGATION      a comment that drops a "not", "no", "never", "nor" or "cannot" its quote puts before it
On the summary:
  MISSING       a highlight number that does not appear once in the summary
  TANDEM        a comment that is not word for word just before its number
  WORDING       a sentence that makes a claim with no highlight behind it (it cites none);
                the wording of a sentence that cites a highlight is left free, and swaps and
                dropped hedges are graded under Text's own words, not flagged here
  LINK          a "because", "so", "therefore" (and the like) in a sentence whose highlights
                make no such link
A sentence of linking and function words only is not listed under WORDING. The lists are for
reading: each flag line names the check it serves; that check's Fix line in
references/method.md section 3, Pass 3: the understanding check and the tests (section 2,
Anchoring a quote, for NOT PLACED) says how to fix it; none is kept as a false alarm.
Exit 0 when nothing is flagged, 1 when anything is, 2 on bad input.
"""
import json
import re
import sys
import unicodedata
from pathlib import Path

# `python3 -I` keeps the scripts folder off the import path, so add it to reach anchor_check.py,
# which defines the page-text normalisation once.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from anchor_check import normalise  # noqa: E402

# Linking and function words; a sentence of these only makes no claim, so it is never listed under WORDING.
OWN = set("""a an the and or but nor so yet for of to in on at by with from into onto as than then
that this these those it its they them their there here is are was were be been being has have had
do does did can could may might must should would will shall not no never also too very more most
less least only even still just both either neither each every all any some such what which who whom
whose when where while why how because since therefore thus hence however although though if
whether one ones own other others""".split())
CAUSAL_SUMMARY = ("because", "so", "therefore", "thus", "hence", "since", "consequently", "by design")
# "as" and "means" stay: in the texts they often make the link ("as the Internet is ...", "This means");
# a false LINK flag cannot be kept, so the script errs towards passing, and pass 3's Nothing added grade checks the rest.
CAUSAL_TEXT = ("because", "so", "therefore", "thus", "hence", "since", "consequently", "as",
               "means", "indicate", "indicates", "why", "in order to", "by design")
NEGATIONS = ("not", "no", "never", "nor", "cannot")
MARK = re.compile(r"\[(\d+)\]")
# The check in references/method.md section 3 (Pass 3: the understanding check and the tests) each flag serves; its Fix line is there.
CHECK = {"NOT PLACED": "anchoring", "ORDER": "order of work, step 3 (write the summary)", "INSIDE": "whole passage / drop what repeats",
         "TERM": "every defined word gets its definition", "LONG COMMENT": "short label",
         "SAME CLAIM": "not a copy", "NEGATION": "comment in summary", "MISSING": "comment in summary",
         "TANDEM": "comment in summary", "WORDING": "every claim backed",
         "LINK": "nothing added"}


def words(text):
    text = unicodedata.normalize("NFKC", text).lower().replace("’", "'")
    return re.findall(r"[a-z0-9]+(?:'[a-z]+)?", text)


def summary_words(text):
    """Words of a summary sentence, a hyphenated compound counted as one word."""
    text = unicodedata.normalize("NFKC", text).lower().replace("’", "'")
    return re.findall(r"[a-z]+(?:['-][a-z]+)*", text)


def comment_length(text):
    """Words of a comment as method.md counts them: a hyphenated compound or a number is one word."""
    joiner = r"(?:['’‐‑–-]|(?<=\d)[.,](?=\d))"  # 'long-term', "1,000" and "3.5" are one word each
    return len(re.findall(rf"[^\W_]+(?:{joiner}[^\W_]+)*", unicodedata.normalize("NFKC", text)))


# Not "no" or "ed": both are ordinary words that end sentences ("they were told no.").
ABBREV = re.compile(r"\b(e\.g|i\.e|et al|cf|vs|pp?|ch|vol|eds)\.$", re.I)


def sentences(summary):
    """Split the summary into sentences: a full stop, question or exclamation mark (and any closing
    quote mark or bracket after it) before a space and a capital, except after a common abbreviation
    ("e.g.", "et al.", "p.")."""
    flat = re.sub(r"\s+", " ", summary).strip()
    marked = re.sub(r"([.!?][\"'”’)]*)\s+(?=[\"'“‘A-Z])", "\\1\x00", flat)
    parts = [s for s in marked.split("\x00") if s]
    out = []
    for p in parts:
        if out and ABBREV.search(out[-1]):
            out[-1] += " " + p
        else:
            out.append(p)
    return out


def place(item, pages):
    """Return (start, end) of the quote in its page's normalised text, or None."""
    page_file = pages / f"p{item['page']}.txt"
    if not page_file.is_file():
        return None
    page_norm, _ = normalise(page_file.read_text(encoding="utf-8"))
    part_norm = normalise(item["quote"].strip())[0].strip()  # stripped as anchor_check.py strips it
    start = page_norm.find(part_norm)
    if start >= 0:
        return (start, start + len(part_norm))
    # As anchor_check.py's fallback: ignore hyphens, dashes and spaces (a compound split at a line end).
    keep = [i for i, c in enumerate(page_norm) if not re.match(r"[-\s]", c)]
    flat, key = "".join(page_norm[i] for i in keep), re.sub(r"[-\s]", "", part_norm)
    hit = flat.find(key) if key else -1
    return None if hit < 0 else (keep[hit], keep[hit + len(key) - 1] + 1)


def check_plan(plan, pages):
    flags = []
    # Keyed by row, not by n: the parts of a page-split passage share one n (method.md section 2).
    spans = {}
    if pages:
        for h in plan:
            spans[id(h)] = place(h, pages)
            if spans[id(h)] is None:
                flags.append(f"NOT PLACED: {h['n']} is not found on page {h['page']} "
                             f"(check it with anchor_check.py); its order and position overlaps are not checked, only "
                             f"whether its text sits inside another quote")
    placed = [h for h in plan if not pages or spans.get(id(h))]
    keyed = sorted(placed, key=lambda h: (h["page"], spans.get(id(h)) or (0, 0)))
    if [h["n"] for h in keyed] != sorted(h["n"] for h in placed):
        flags.append(f"ORDER: by page{' and position' if pages else ''} the highlights run "
                     f"{[h['n'] for h in keyed]}")
    for a in plan:
        for b in plan:
            if a is b or a["page"] != b["page"]:
                continue
            sa, sb = spans.get(id(a)), spans.get(id(b))
            if sa and sb:
                if a["n"] < b["n"] and sa[0] < sb[1] and sb[0] < sa[1]:
                    # A highlight wholly inside another gets the "sits inside" fix (drop it), an overlap the other.
                    # Tested in this order so a repeated quote is reported on the later number, as without --pages.
                    if sa[0] <= sb[0] and sb[1] <= sa[1]:
                        flags.append(f"INSIDE: {b['n']} sits inside {a['n']}")
                    elif sb[0] <= sa[0] and sa[1] <= sb[1]:
                        flags.append(f"INSIDE: {a['n']} sits inside {b['n']}")
                    else:
                        flags.append(f"INSIDE: {a['n']} and {b['n']} overlap on page {a['page']}")
            # Two highlights with the same quote are reported once, as with --pages.
            elif (a["n"] != b["n"] and normalise(a["quote"].strip())[0].strip() in normalise(b["quote"])[0]
                  and (a["quote"] != b["quote"] or a["n"] > b["n"])):
                flags.append(f"INSIDE: {a['n']} sits inside {b['n']}")
    # The parts of a page-split passage share one n; a term's words may sit in either part.
    quote_of = {n: " ".join(x["quote"] for x in plan if x["n"] == n) for n in {x["n"] for x in plan}}
    for h in plan:
        cw, qw = words(h["comment"]), words(h["quote"])
        if h.get("term") and not set(cw) <= set(words(quote_of[h["n"]])):
            flags.append(f"TERM: {h['n']} '{h['comment']}' is not in its own highlight")
        if comment_length(h["comment"]) > 5:
            flags.append(f"LONG COMMENT: {h['n']} '{h['comment']}' has {comment_length(h['comment'])} words")
        # A page-split passage is judged whole: a short part holding only the comment's words is not a copy.
        content_q = [w for w in words(quote_of[h["n"]]) if w not in OWN]
        if content_q and len([w for w in content_q if w in set(cw)]) / len(content_q) >= 0.7:
            flags.append(f"SAME CLAIM: {h['n']} '{h['comment']}' is most of its quote")
        # A contraction ("isn't", "can't") negates as "not" does.
        negates = lambda w: w in NEGATIONS or w.endswith("n't")
        if cw and not any(negates(w) for w in cw):
            for i in range(len(qw)):
                if qw[i:i + len(cw)] == cw and any(negates(w) for w in qw[max(0, i - 3):i]):
                    flags.append(f"NEGATION: {h['n']} '{h['comment']}' drops the quote's "
                                 f"'{' '.join(qw[max(0, i - 3):i])}' before it")
                    break
    return flags


def check_summary(plan, summary):
    flags = []
    by_n = {h["n"]: h for h in plan}
    # The parts of a page-split passage share one n; their quotes are read together.
    quote_of = {n: " ".join(h["quote"] for h in plan if h["n"] == n) for n in by_n}
    found = MARK.findall(summary)
    for n in by_n:
        if found.count(str(n)) != 1:
            flags.append(f"MISSING: highlight {n} appears {found.count(str(n))} times in the summary")
    for s in sentences(summary):
        cited = [int(x) for x in MARK.findall(s) if int(x) in by_n]
        for n in cited:
            before = re.split(rf"\[{n}\]", s)[0]
            cw = words(by_n[n]["comment"])  # whole words: "man" is not the end of "woman"
            if not cw or words(before)[-len(cw):] != cw:
                flags.append(f"TANDEM: {n} '{by_n[n]['comment']}' is not word for word before [{n}]")
        # Only a claim with no highlight behind it is flagged; a sentence that cites one is free in its wording.
        own = [w for w in summary_words(MARK.sub("", s)) if w not in OWN]
        if own and not cited:
            flags.append(f"WORDING: no highlight behind this sentence | {s[:90]}")
        # "so" and "since" count only where they open a clause (sentence start, or after a comma,
        # semicolon, colon or "and"), not "so common", "so-called", "so that" or "ever since"; a false LINK
        # flag cannot be kept, so the script errs towards passing, and Nothing added grades the rest.
        def links(c, t):
            if c in ("so", "since"):
                return re.search(rf"(?:^|[,;:]\s*|\band\s+){c}\b(?![-\s]+(?:that|called|\d))", t)
            return re.search(rf"\b{c}\b", t)
        said = [c for c in CAUSAL_SUMMARY if links(c, s.lower())]
        quotes = " ".join(quote_of[n].lower() for n in cited)
        if said and not any(re.search(rf"\b{c}\b", quotes) for c in CAUSAL_TEXT):
            flags.append(f"LINK: '{said[0]}' in a sentence whose highlights make no such link | {s[:90]}")
    return flags


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    pages = None
    if "--pages" in argv:
        i = argv.index("--pages")
        if i + 1 >= len(argv) or not Path(argv[i + 1]).is_dir():
            print("bad input: --pages needs a folder")
            return 2
        pages = Path(argv[i + 1])
        args = [a for a in args if a != argv[i + 1]]
    if len(args) != 2:
        print(__doc__)
        return 2
    try:
        plan = json.loads(Path(args[0]).read_text(encoding="utf-8"))
        summary = Path(args[1]).read_text(encoding="utf-8")
        for h in plan:
            h["n"], h["page"] = int(h["n"]), int(h["page"])
            if not isinstance(h["comment"], str) or not isinstance(h["quote"], str):
                raise TypeError(f"highlight {h['n']}: comment and quote must be text")
    except (OSError, ValueError, KeyError, TypeError) as e:
        print(f"bad input: {e}")
        return 2
    try:
        flags = list(dict.fromkeys(check_plan(plan, pages) + check_summary(plan, summary)))
    except (OSError, UnicodeDecodeError) as e:  # a page file under --pages that cannot be read
        print(f"bad input: {e}")
        return 2
    for f in flags:
        print(f"{f}  [check: {CHECK[f.split(':')[0]]}]")
    print(f"{len(flags)} flagged" if flags else "nothing flagged")
    return 1 if flags else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
