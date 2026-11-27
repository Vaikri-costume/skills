#!/usr/bin/env python3
"""Flag summary clauses that copy the source with words swapped.

Usage: copy_check.py SOURCE_TEXT_FILE SUMMARY_FILE [--comments COMMENTS_FILE] [--ratio 0.6] [--run 4]
SOURCE_TEXT_FILE: text of the pages summarised (plain text, e.g. pdftotext output).
SUMMARY_FILE: the summary (plain text or Markdown). Lines starting with #, --- or "- " (a bullet) and
count lines of the form "Word count:", "Status:" or "Sentences:" (the word, then a colon, any case) are skipped; a paragraph that merely begins with one of those words is checked. Text inside quotation marks (double quotes, straight or curly, and curly single quotes; a
straight single quote is read as an apostrophe) (the allowed short quoted terms) is ignored whatever its length; keeping quoted terms short is the writer's job.
COMMENTS_FILE (optional): the highlight comments, one per line. A comment is the text's own
wording kept word for word (the user's Text's own words check), so each comment phrase is cut out
of the summary before checking; only the connecting prose around them is checked.
For each summary clause of 4 or more words (split at . ; : , and 'and/but/because/so/which/while/whereas'; a clause of 3 or fewer words is not checked, whatever --run is):
  RUN  = the clause shares an exact run of --run or more consecutive words with the source.
  NEAR = at least --ratio of the clause's content words (stemmed) occur together in one
         source window of twice the clause's length (at least 12 words), and the clause has 4+ content words.
A hyphen at a source line end is read both ways (a soft hyphen joins the word, a compound keeps its two words), much as anchor_check.py distinguishes them (unlike anchor_check.py, a space or tab between the hyphen and the line break is allowed).
Exit 0 when nothing is flagged, 1 when any clause is flagged, 2 on bad input.
A tool, called by no step: a flag points to a clause to read, not a fail. The text's own wording is
kept where the text says something plainly (Text's own words, references/method.md section 3).
"""
import re
import sys
import unicodedata
from pathlib import Path

# Stop words specific to this script; the other check scripts keep their own sets.
STOP = set("""a an the and or but if then so because as of in on at to for from by with without about
into onto over under between through is are was were be been being it its this that these those there
which who whom whose what when where while not no nor than too very can could may might will would
shall should must do does did done has have had he she they them their his her we you i our your one
also only such more most some any each every both either neither just even still yet how why""".split())


# term_check.py imports this pattern from here, so it is defined once.
LINE_END_HYPHEN = re.compile(r"(?<=[^\W\d_])-[ \t]*\r?\n\s*(\S)")


def join_line_hyphens(text, soft):
    """Resolve a hyphen at a line end (spaces or tabs before the break allowed, which anchor_check.py does not allow): before a lowercase letter it may be a
    soft hyphen (gov-/ernment) and, when soft is true, is dropped; before a capital or digit it is a
    genuine hyphen and is kept. soft=False keeps every such hyphen, which reads a compound broken at a
    line end (market-/driven) as two words. Only the page text can tell which reading is right, so
    callers compare against both."""
    def fix(m):
        c = m.group(1)
        return c if soft and c.islower() else "-" + c
    return LINE_END_HYPHEN.sub(fix, text)


def norm(text, soft=True):
    text = unicodedata.normalize("NFKC", text)
    text = join_line_hyphens(text, soft).lower()
    return text.replace("’", "'").replace("‘", "'")


def words(text, soft=True):
    return re.findall(r"[a-z]+(?:'[a-z]+)?", norm(text, soft))


def stem(w):
    for suf in ("ations", "ation", "ingly", "ings", "ing", "edly", "ed", "ies", "es", "s", "ly"):
        if w.endswith(suf) and len(w) - len(suf) >= 4:
            return w[: -len(suf)]
    return w


# The cut rule, defined once here and imported by pin_check.py and term_check.py; norm() in tandem_check.py follows the same rule: change both together.
def cut_pattern(comment):
    """Regex matching the comment as tandem_check does: any case, any whitespace or line break
    between words, curly or straight quotes."""
    parts = []
    for w in comment.split():
        s = ""
        for ch in w:
            if ch in "'\u2018\u2019":
                s += "['\u2018\u2019]"
            elif ch in '"\u201c\u201d':
                s += '["\u201c\u201d]'
            else:
                s += re.escape(ch)
        parts.append(s)
    return r"(?<!\w)" + r"\s+".join(parts) + r"(?!\w)"

COUNT_LINE = re.compile(r"(word count|status|sentences)\s*:", re.I)


def clauses(text, comments=()):
    # Comments are cut first: a comment may itself contain quotation marks, which the quoted-span strip would remove.
    for c in sorted((c.strip() for c in comments if c.strip()), key=len, reverse=True):
        text = re.sub(cut_pattern(c), " ¦ ", text, flags=re.I)
    text = re.sub(r"[“\"][^”\"]*[”\"]", " ", text)
    # British single quotes too, curly only: a straight ' is also an apostrophe ("women's").
    text = re.sub(r"‘[^’]*’(?![a-z])", " ", text)
    out = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or s.startswith("---") or s.startswith("- ") or COUNT_LINE.match(s):
            continue
        for sent in re.split(r"(?<=[.;:!?])\s+", s):
            for part in re.split(r",\s*|¦|\s+(?:and|but|because|so|which|while|whereas)\s+", sent):
                if part and len(words(part)) >= 4:
                    out.append((sent.strip(), part.strip()))
    return out


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    opts = {}
    for i, a in enumerate(argv):
        if a in ("--ratio", "--run", "--comments"):
            try:
                v = argv[i + 1]
                opts[a] = v if a == "--comments" else float(v)
                if a == "--run":
                    int(v)
            except (IndexError, ValueError):
                print("missing --comments file" if a == "--comments" else "bad %s value" % a)
                return 2
            args = [x for x in args if x != v]
    if len(args) != 2:
        print(__doc__)
        return 2
    try:
        src_text = Path(args[0]).read_text(encoding="utf-8")
        srcs = [words(src_text, True), words(src_text, False)]
        summ = Path(args[1]).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        print(f"bad input: {e}")
        return 2
    ratio, run = opts.get("--ratio", 0.6), int(opts.get("--run", 4))
    comments = []
    if "--comments" in opts:
        try:
            comments = Path(opts["--comments"]).read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError) as e:
            print(f"bad input: {e}")
            return 2
    # Both readings of a line-end hyphen are searched; a clause matching either is flagged.
    srcs = [srcs[0]] + ([srcs[1]] if srcs[1] != srcs[0] else [])
    src_contents = [[(i, stem(w)) for i, w in enumerate(sw) if w not in STOP] for sw in srcs]
    grams = {}
    for sw in srcs:
        for i in range(len(sw) - run + 1):
            grams.setdefault(tuple(sw[i : i + run]), i)
    flagged = 0
    for sent, part in clauses(summ, comments):
        w = words(part)
        reasons = []
        for i in range(len(w) - run + 1):
            g = tuple(w[i : i + run])
            if g in grams:
                reasons.append("RUN '" + " ".join(g) + "'")
                break
        cw = [stem(x) for x in w if x not in STOP]
        if len(cw) >= 4:
            need = set(cw)
            span = max(2 * len(w), 12)
            best = 0.0
            for toks in src_contents:
                j = 0
                for a in range(len(toks)):
                    while j < len(toks) and toks[j][0] - toks[a][0] < span:
                        j += 1
                    win = {s for _, s in toks[a:j]}
                    best = max(best, len(need & win) / len(need))
                    if best == 1.0:
                        break
            if best >= ratio:
                reasons.append(f"NEAR {best:.0%} of content words in one source window")
        if reasons:
            flagged += 1
            print(f"FLAG [{'; '.join(reasons)}]\n  clause: {part}\n  sentence: {sent}\n")
    print(f"{flagged} clause(s) flagged")
    return 1 if flagged else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
