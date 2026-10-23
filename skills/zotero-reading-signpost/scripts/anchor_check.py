#!/usr/bin/env python3
"""Check that each planned highlight part exists verbatim in the page text.

Usage: anchor_check.py PAGE_TEXT_FILE PARTS_FILE [--allow-repeat]
--allow-repeat: a phrase over 100 characters that the text repeats (abstract and body) is accepted,
with a note (the highlight lands on its first copy); a repeated phrase of 100 characters or fewer stays AMBIGUOUS;
without it a repeated phrase is AMBIGUOUS and must be lengthened. This holds for a phrase
found exactly and for one found only ignoring hyphens, dashes and spaces.
PAGE_TEXT_FILE: text of the pages read (any plain text).
Spans are printed in quoted form (Python string literals): the highlight tool gets the text a span
denotes (a \\n is a line break; escapes are not typed).
PARTS_FILE: one planned part per line (blank lines ignored).
Matching ignores differences that PDF extraction introduces: soft hyphens,
line-end hyphenation, ligatures, curly versus straight quotes, dash variants and
line breaks or repeated spaces. A part matched this way is "found"; the original
page text span is printed so the exact text can be copied for the highlight (on a plain "found:" line as well as on a loose match).
For a part over 100 characters, the highlight tool starts at the first place on the page where its opening words appear and
ends at the first place after that where its closing words appear. Such a part whose first 30
characters appear earlier on the page, or whose last 30 appear again before its own end, is
flagged EDGE REPEATS: the tool would span from the other copy (a wall of highlight). With --allow-repeat, a sentence
over 100 characters that the page repeats (an abstract and the body) passes when the part is its first copy.
A part must also match the page's own letter case.
Exit 0 when every part is found exactly once, 1 when any part is missing, ambiguous
(found more than once), has a repeating edge (EDGE REPEATS) or differs from the page
in letter case (CASE DIFFERS), 2 on bad input. With --allow-repeat the case check still
applies; the edge check still runs for a phrase that matches once (the flag only accepts a phrase that matches more than once).
"""
import re
import sys
import unicodedata
from pathlib import Path

# The highlight tool highlights a quote of this many characters or fewer at every copy on its page
# (an exact search); a longer one runs from the first copy of its opening words.
SHORT_QUOTE = 100

LIGATURES = {"ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl"}
QUOTES = {"‘": "'", "’": "'", "“": '"', "”": '"'}
DASHES = {"‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-"}


def normalise(text, lower=True):
    """Return (normalised text, list mapping each normalised index to an original index)."""
    out, idx = [], []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == "­":
            i += 1
            while i < n and text[i] in "\n\r" and i + 1 <= n:
                i += 1
            continue
        if ch == "-" and i + 1 < n and text[i + 1] in "\n\r" and out and out[-1].isalpha():
            j = i + 1
            while j < n and text[j] in "\n\r \t":
                j += 1
            if j < n and text[j].islower():
                i = j
                continue
            if j < n:
                # genuine hyphen at a line end (before a capital or digit): keep it, drop the break
                out.append("-")
                idx.append(i)
                i = j
                continue
        for table in (LIGATURES, QUOTES, DASHES):
            if ch in table:
                rep = table[ch]
                break
        else:
            rep = unicodedata.normalize("NFKC", ch)
        if rep.isspace():
            if out and out[-1] == " ":
                i += 1
                continue
            rep = " "
        for r in rep:
            # One entry per output character: a lowercase form can be two (U+0130 becomes "i" plus a dot).
            for c in (r.lower() if lower else r):
                out.append(c)
                idx.append(i)
        i += 1
    return "".join(out), idx


def find_part(page_norm, idx, page_raw, part):
    pn, _ = normalise(part.strip())
    pn = pn.strip()
    if not pn:
        return None
    hits = [m.start() for m in re.finditer(re.escape(pn), page_norm)]
    spans = []
    for h in hits:
        start = idx[h]
        end = idx[h + len(pn) - 1] + 1
        spans.append(page_raw[start:end])
    return spans


def find_part_loose(page_norm, idx, page_raw, part):
    """Fallback: ignore hyphens, dashes and spaces on both sides (a compound split at a line end)."""
    strip = lambda t: re.sub(r"[-\s]", "", t)
    pn, _ = normalise(part.strip())
    key = strip(pn)
    if not key:
        return []
    # map stripped positions back to normalised indices
    pos = [i for i, c in enumerate(page_norm) if not re.match(r"[-\s]", c)]
    flat = "".join(page_norm[i] for i in pos)
    spans = []
    for m in re.finditer(re.escape(key), flat):
        start, end = idx[pos[m.start()]], idx[pos[m.end() - 1]] + 1
        spans.append(page_raw[start:end])
    return spans


def edge_repeat(page_norm, part, width=30, loose=False, span=None):
    """Return 'start' or 'end' when the highlight tool would not land on the part itself.
    The tool starts at the first place on the page where the part's opening words appear and ends at
    the first place after that where its closing words appear. So an edge that repeats is harmless
    when the part's own copy is that first place (a sentence an abstract repeats, highlighted in the
    abstract), and fails when an earlier copy would be taken instead.
    loose=True compares with hyphens, dashes and spaces removed from both sides.
    A quote of SHORT_QUOTE characters or fewer is found by exact search, not from its opening words, so it has no edge to repeat.
    The length is that of span, the printed page text given to the tool, where the caller has it."""
    if len((part if span is None else span).strip()) <= SHORT_QUOTE:
        return ""
    pn, _ = normalise(part.strip())
    pn = pn.strip()
    if loose:
        strip = lambda t: re.sub(r"[-\s]", "", t)
        pn, page_norm = strip(pn), strip(page_norm)
    if len(pn) <= width:
        return ""
    own = page_norm.find(pn)
    if own < 0:
        return ""
    if page_norm.find(pn[:width]) != own:
        return "start"
    # Search for the closing words from just past the opening ones, but never past the part's own copy of them.
    if page_norm.find(pn[-width:], own + min(width // 2, len(pn) - width)) != own + len(pn) - width:
        return "end"
    return ""


def report_edge_repeat(n, edge, part):
    print(f"{n}: EDGE REPEATS ({edge} of this part also appears earlier on the page, and the highlight tool takes the first copy, a wall of highlight; highlight the first copy of a repeated sentence, or start or end the part on words that occur once): {part}")


def check_loose_hit(n, part, loose, page_norm, allow_repeat=False):
    """Report on a part found only when hyphens, dashes and spaces are ignored. Return 1 if it is a problem, else 0.
    With allow_repeat a phrase the text repeats is accepted with a note, as on the exact path (case still checked)."""
    if len(loose) > 1 and allow_repeat and len(loose[0].strip()) <= SHORT_QUOTE:
        print(f"{n}: AMBIGUOUS ({len(loose)} matches ignoring hyphens, dashes and spaces; a quote of {SHORT_QUOTE} characters or fewer is highlighted at every copy, lengthen it past {SHORT_QUOTE}): {part}")
        return 1
    if len(loose) >= 1 and (len(loose) == 1 or allow_repeat):
        strip = lambda t: re.sub(r"[-\s]", "", t)
        raw = strip(normalise(loose[0], lower=False)[0])
        want = strip(normalise(part.strip(), lower=False)[0])
        if raw != want:
            print(f"{n}: CASE DIFFERS from the page (copy the page's own letters): page {loose[0]!r} vs part {part.strip()!r}")
            return 1
        if len(loose) > 1:
            print(f"{n}: found ({len(loose)} matches ignoring hyphens, dashes and spaces; the text repeats this phrase, the highlight lands on the first, check it): {loose[0]!r}")
            return 0
        edge = edge_repeat(page_norm, part, loose=True, span=loose[0])
        if edge:
            report_edge_repeat(n, edge, part)
            return 1
        print(f"{n}: found (ignoring hyphens, dashes and spaces; check the highlight tool accepts it): {loose[0]!r}")
        return 0
    if len(loose) > 1:
        print(f"{n}: AMBIGUOUS ({len(loose)} matches ignoring hyphens, dashes and spaces, lengthen the part): {part}")
    else:
        print(f"{n}: NOT FOUND: {part}")
    return 1


def check_exact_hit(n, part, spans, page_norm, allow_repeat):
    """Report on a part with at least one exact (normalised) match. Return 1 if it is a problem, else 0."""
    if len(spans) > 1 and allow_repeat and len(spans[0].strip()) <= SHORT_QUOTE:
        print(f"{n}: AMBIGUOUS ({len(spans)} matches; a quote of {SHORT_QUOTE} characters or fewer is highlighted at every copy, lengthen it past {SHORT_QUOTE}): {part}")
        return 1
    if len(spans) > 1 and not allow_repeat:
        print(f"{n}: AMBIGUOUS ({len(spans)} matches, lengthen the part): {part}")
        return 1
    want = normalise(part.strip(), lower=False)[0].strip()
    raw = normalise(spans[0], lower=False)[0].strip()
    if raw != want:
        print(f"{n}: CASE DIFFERS from the page (copy the page's own letters): page {raw!r} vs part {want!r}")
        return 1
    if len(spans) > 1:
        print(f"{n}: found ({len(spans)} matches; the text repeats this phrase, the highlight lands on the first, check it): {spans[0]!r}")
        return 0
    edge = edge_repeat(page_norm, part, span=spans[0])
    if edge:
        report_edge_repeat(n, edge, part)
        return 1
    print(f"{n}: found: {spans[0]!r}")
    return 0


def main(argv):
    allow_repeat = "--allow-repeat" in argv
    argv = [a for a in argv if a != "--allow-repeat"]
    if len(argv) != 3:
        print(__doc__)
        return 2
    page_path, parts_path = Path(argv[1]), Path(argv[2])
    if not page_path.is_file() or not parts_path.is_file():
        print("missing input file")
        return 2
    try:
        page_raw = page_path.read_text(encoding="utf-8")
        parts = [p for p in parts_path.read_text(encoding="utf-8").splitlines() if p.strip()]
    except (OSError, UnicodeDecodeError) as e:
        print(f"bad input: {e}")
        return 2
    if not parts:
        print("no parts")
        return 2
    page_norm, idx = normalise(page_raw)
    bad = 0
    for n, part in enumerate(parts, 1):
        spans = find_part(page_norm, idx, page_raw, part)
        if spans:
            bad += check_exact_hit(n, part, spans, page_norm, allow_repeat)
        else:
            loose = find_part_loose(page_norm, idx, page_raw, part)
            bad += check_loose_hit(n, part, loose, page_norm, allow_repeat)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
