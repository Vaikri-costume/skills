#!/usr/bin/env python3
"""Check that every highlight comment appears word for word in the summary.

Usage: tandem_check.py SUMMARY_FILE COMMENTS_FILE
SUMMARY_FILE: the summary text (plain text).
COMMENTS_FILE: one planned comment per line (blank lines ignored).
Matching requires whole words (no match inside a longer word) and ignores capitals, repeated spaces, line breaks and curly versus straight quotes.
Prints each comment that is missing. Exit 0 when every comment appears in the summary,
1 when any is missing, 2 on bad input.
"""
import re
import sys
from pathlib import Path


def norm(text):
    text = text.replace("‘", "'").replace("’", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", text).strip().lower()


def main(argv):
    if len(argv) != 3:
        print(__doc__)
        return 2
    s_path, c_path = Path(argv[1]), Path(argv[2])
    if not s_path.is_file() or not c_path.is_file():
        print("missing input file")
        return 2
    try:
        summary = norm(s_path.read_text(encoding="utf-8"))
        comment_lines = c_path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as e:
        print(f"bad input: {e}")
        return 2
    comments = [c.strip() for c in comment_lines if c.strip()]
    if not comments:
        print("no comments")
        return 2
    missing = [c for c in comments if not re.search(r"(?<!\w)" + re.escape(norm(c)) + r"(?!\w)", summary)]
    for c in missing:
        print(f"NOT IN SUMMARY: {c}")
    print(f"{len(comments) - len(missing)} of {len(comments)} comments appear in the summary")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
