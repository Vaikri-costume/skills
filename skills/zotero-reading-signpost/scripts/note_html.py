#!/usr/bin/env python3
"""Lay out the Signpost Summary note as the simple HTML a Zotero note takes.

Usage: note_html.py SUMMARY_FILE [--related NAME] [--citekey KEY] [--author NAME] [--writer NAME]
SUMMARY_FILE: the approved summary as plain text, paragraphs separated by a blank line
([n] highlight markers, if present, are removed).
--related: the module the reading belongs to (written as [[NAME]], with the brackets as HTML
entities); omitted, the related:: line is written with no value.
--citekey: the item's citation key; omitted, the citekey:: line is left out.
--author: the item's author as on the item.
--writer: who wrote the note (default Claude).
Prints one line of HTML: the property lines in one <p> joined with <br>, a plain
"Notes / Summary" <p>, and each summary paragraph as its own <p>. Text is HTML-escaped.
Exit 0 on success, 2 on bad input.
"""
import html
import re
import sys
from pathlib import Path

MARK = re.compile(r"\s*\[\d+\]")


def option(args, name):
    if name not in args:
        return None
    i = args.index(name)
    if i + 1 >= len(args):
        raise ValueError(f"{name} needs a value")
    value = args[i + 1]
    del args[i:i + 2]
    return value


def main(argv):
    args = argv[1:]
    try:
        related = option(args, "--related")
        citekey = option(args, "--citekey")
        author = option(args, "--author")
        writer = option(args, "--writer") or "Claude"
    except ValueError as e:
        print(f"bad input: {e}")
        return 2
    if len(args) != 1:
        print(__doc__)
        return 2
    try:
        text = Path(args[0]).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        print(f"bad input: {e}")
        return 2
    paragraphs = [" ".join(p.split()) for p in re.split(r"\n\s*\n", MARK.sub("", text)) if p.strip()]
    if not paragraphs:
        print("bad input: the summary is empty")
        return 2
    # quote=False as for the paragraphs, so an apostrophe (O'Brien) reads back as Zotero stores it.
    rel = "" if related is None else "&#91;&#91;" + html.escape(related, quote=False) + "&#93;&#93;"
    props = [f"related:: {rel}".rstrip(), "type:: Signpost Summary", f"writer:: {html.escape(writer, quote=False)}"]
    if citekey:
        props.append(f"citekey:: {html.escape(citekey, quote=False)}")
    if author:
        props.append(f"author:: {html.escape(author, quote=False)}")
    out = "<p>" + "<br>".join(props) + "</p><p>Notes / Summary</p>"
    out += "".join(f"<p>{html.escape(p, quote=False)}</p>" for p in paragraphs)
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
