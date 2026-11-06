#!/usr/bin/env python3
"""report_lint.py - guard a finished report before it is relayed.

Usage: report_lint.py <report.md>

Reads the report, ignores quoted text (anything inside straight or curly
double quotes, and lines starting with `>`), and reports:
  tldr       a TLDR or "too long; didn't read" line
  offer      an offer of further help ("would you like", "I can also", ...)
  gendered   he/she/him/her/his/hers/himself/herself about the writer
  rewrite    supplied replacement wording ("rewrite:", "replace with", ...)
  grade      a numeric grade or score (8/10, score: 7, 72%)
  next-line  a line starting `Next:`
Output: {"problems": [{"rule", "line", "text"}]}; exit 1 if any, 2 on bad input.
"""
import json
import re
import sys

RULES = [
    ("tldr", re.compile(r"\btl;?\s?dr\b|too long;? ?didn'?t read", re.I)),
    ("offer", re.compile(r"\b(would you like|want me to|shall i|i can also|i could also|let me know if|happy to (?:help|also)|do you want me|if you(?:'d| would) like,? i)\b", re.I)),
    ("gendered", re.compile(r"\b(he|she|him|her|his|hers|himself|herself)\b", re.I)),
    ("rewrite", re.compile(r"^\s*(?:[-*]\s*)?(?:suggested (?:wording|rewrite|text|version)|rewrite[sd]?\b\s*:|revised (?:version|text|sentence)|replace (?:it )?with|try:)|\b(?:you could write|could be rewritten as|consider writing|a stronger version would read)\b", re.I)),
    ("grade", re.compile(r"\b\d+(?:\.\d+)?\s*/\s*(?:10|100|5)\b|\bscore\s*[:=]\s*\d|\b\d{2,3}\s?%\s*(?:mark|grade|score)", re.I)),
    ("next-line", re.compile(r"^\s*(?:\*\*)?next(?:\*\*)?\s*[:—-]", re.I)),
]
QUOTED = re.compile(r'"[^"\n]*"|“[^”\n]*”')


def lint(text):
    problems = []
    for i, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith(">"):
            continue
        stripped = QUOTED.sub(" ", line)
        for name, rx in RULES:
            if rx.search(stripped):
                problems.append({"rule": name, "line": i, "text": line.strip()[:120]})
    return problems


def main(argv):
    if len(argv) != 2:
        print(json.dumps({"error": "Usage: report_lint.py <report.md>"}))
        return 2
    try:
        text = open(argv[1], encoding="utf-8").read()
    except OSError as e:
        print(json.dumps({"error": str(e)}))
        return 2
    p = lint(text)
    print(json.dumps({"problems": p}, indent=2))
    return 1 if p else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
