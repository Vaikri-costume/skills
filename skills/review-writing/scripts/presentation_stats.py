#!/usr/bin/env python3
"""presentation_stats.py - counts for a slide outline, notes or transcript.

Usage: presentation_stats.py <file> [--minutes N] [--wpm LOW-HIGH]

Input contract: slides are separated by a line of three or more dashes (---),
or by a heading line starting `# ` / `## Slide` / `Slide N`. A transcript with
no separators is one block.
Output: JSON on stdout:
  {"slides": n, "words_total": n, "per_slide": [{"slide": i, "words": n,
   "first_words": str}], "reference_slide": [slide numbers whose text starts
   with a References/Bibliography/Sources/Works cited heading],
   "pace": {"minutes": N, "wpm_range": [lo, hi], "min_minutes": x,
   "max_minutes": y, "fits": "within" | "short" | "long"} (only with --minutes),
   "longest_slides": [slide numbers over twice the median words]}
The speaking-rate range (default 120-160 words per minute) is an assumption the
reviewer states; the script only does the arithmetic. Exit 2 on bad input.
"""
import json
import re
import statistics
import sys

SEP = re.compile(r"^\s*(?:-{3,}|#{1,2}\s+slide\b.*|slide\s+\d+\b.*|#\s+.*)$", re.I)
REF = re.compile(r"^\W*(references?|bibliography|sources|works cited)\b", re.I)


def split_slides(text):
    blocks, cur = [], []
    for line in text.splitlines():
        if SEP.match(line):
            if "".join(cur).strip():
                blocks.append("\n".join(cur).strip())
            cur = [] if re.match(r"^\s*-{3,}\s*$", line) else [line]
        else:
            cur.append(line)
    if "".join(cur).strip():
        blocks.append("\n".join(cur).strip())
    return blocks


def words(s):
    return len(re.findall(r"[\w'’-]+", s))


def stats(text, minutes=None, wpm=(120, 160)):
    blocks = split_slides(text)
    per = [{"slide": i + 1, "words": words(b), "first_words": " ".join(b.split()[:6])}
           for i, b in enumerate(blocks)]
    total = sum(p["words"] for p in per)
    out = {"slides": len(per), "words_total": total, "per_slide": per,
           "reference_slide": [i + 1 for i, b in enumerate(blocks)
                               if REF.match(re.sub(r"^#+\s*", "", b.lstrip()))]}
    if per:
        med = statistics.median(p["words"] for p in per)
        out["longest_slides"] = [p["slide"] for p in per if med and p["words"] > 2 * med]
    if minutes:
        lo, hi = wpm
        mn, mx = total / hi, total / lo
        fits = "within" if mn <= minutes <= mx else ("short" if minutes > mx else "long")
        out["pace"] = {"minutes": minutes, "wpm_range": [lo, hi],
                       "min_minutes": round(mn, 1), "max_minutes": round(mx, 1), "fits": fits}
    return out


def main(argv):
    args = argv[1:]
    minutes, wpm, path = None, (120, 160), None
    i = 0
    try:
        while i < len(args):
            if args[i] == "--minutes":
                minutes = float(args[i + 1]); i += 2
            elif args[i] == "--wpm":
                lo, hi = args[i + 1].split("-"); wpm = (int(lo), int(hi)); i += 2
            else:
                path = args[i]; i += 1
        text = open(path, encoding="utf-8").read()
    except (IndexError, ValueError, OSError, TypeError) as e:
        print(json.dumps({"error": f"bad input: {e}. Usage: presentation_stats.py <file> [--minutes N] [--wpm LOW-HIGH]"}))
        return 2
    print(json.dumps(stats(text, minutes, wpm), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
