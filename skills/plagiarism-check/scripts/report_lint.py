#!/usr/bin/env python3
"""report_lint.py - guard a finished report before it is relayed.

Usage: report_lint.py <report.md> [--refs reference-check.json]

Quoted text (inside straight or curly double quotes, and lines starting `>`) is ignored. Reports:
  tldr        a TLDR line
  offer       an offer of further help or another check ("would you like", "I can also", ...)
  next-line   a line starting `Next:`
  gendered    he/she/him/her/his/hers/himself/herself about the writer
  grade       a numeric grade or score
  accuse      a finding of misconduct or of intent ("you plagiarised", "cheated", "guilty", ...)
  evade       advice on avoiding detection ("avoid detection", "undetectable", "so it passes", ...)
  rewrite     supplied replacement wording for the draft ("rewrite:", "replace with", ...)
  limits      the honest-limits sentence "nothing found through the search used" is missing
  invented-id with --refs: a DOI or ISBN in the report that is in no entry or index record
Output: {"problems": [{"rule", "line", "text"}]}; exit 1 if any, 2 on bad input.
"""
import json
import re
import sys

RULES = [
    ("tldr", re.compile(r"\btl;?\s?dr\b|too long;? ?didn'?t read", re.I)),
    ("offer", re.compile(r"\b(would you like|want me to|shall i|i can also|i could also|let me know if|happy to (?:help|also)|do you want me|if you(?:'d| would) like,? i|i can (?:run|check|rewrite|fix))\b", re.I)),
    ("next-line", re.compile(r"^\s*(?:\*\*)?next(?:\*\*)?\s*[:—-]", re.I)),
    ("gendered", re.compile(r"\b(he|she|him|her|his|hers|himself|herself)\b", re.I)),
    ("grade", re.compile(r"\b\d+(?:\.\d+)?\s*/\s*(?:10|100|5)\b|\bscore\s*[:=]\s*\d|\b\d{2,3}\s?%\s*(?:mark|grade|score)", re.I)),
    ("accuse", re.compile(r"\b(you (?:have )?(?:plagiari[sz]ed|cheated|copied deliberately)|(?:is|are|was|were) plagiari[sz]ed|committed (?:plagiarism|misconduct)|guilty|deliberate(?:ly)? (?:copied|plagiari)|intended to (?:deceive|cheat)|dishonest)", re.I)),
    ("evade", re.compile(r"\b(avoid(?:ing)? detection|undetectable|escape detection|evade|so (?:that )?it (?:passes|slips)|get past (?:turnitin|the (?:checker|detector)))\b", re.I)),
    ("rewrite", re.compile(r"^\s*(?:[-*]\s*)?(?:suggested (?:wording|rewrite|text|version)|rewrite[sd]?\b\s*:|revised (?:version|text|sentence)|replace (?:it )?with|try:)|\b(?:you could write|could be rewritten as|consider writing|a stronger version would read)\b", re.I)),
]
QUOTED = re.compile(r'"[^"\n]*"|“[^”\n]*”|\'[^\'\n]{12,}\'')
DOI = re.compile(r"\b10\.\d{4,9}/[^\s\"<>|)]+", re.I)
ISBN = re.compile(r"\b(?:97[89][\d-]{10,14}|\d{9}[\dXx])\b")


def lint(text, refs=None):
    problems = []
    for i, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith(">"):
            continue
        stripped = QUOTED.sub(" ", line)
        qs = [i for i, ch in enumerate(line) if ch in '"“”']
        if len(qs) >= 2:  # a report quoting the draft may nest quotation marks: ignore everything between the first and last
            stripped = line[:qs[0]] + " " + line[qs[-1] + 1:]
        for name, rx in RULES:
            if name == "evade" and re.search(r"\b(not|never|cannot|won't|can't|no advice|declin\w+|refus\w+)\b|n't\b", stripped, re.I):
                continue  # a refusal to give evasion advice is allowed
            if rx.search(stripped):
                problems.append({"rule": name, "line": i, "text": line.strip()[:120]})
    if not re.search(r"nothing found through the search used", text, re.I):
        problems.append({"rule": "limits", "line": 0, "text": "the sentence 'nothing found through the search used' is missing"})
    if refs is not None:
        blob = json.dumps(refs).lower().replace("\\/", "/")
        digits = re.sub(r"[^0-9x]", "", blob)
        for i, line in enumerate(text.splitlines(), 1):
            for m in DOI.finditer(line):
                if m.group(0).rstrip(".,;").lower() not in blob:
                    problems.append({"rule": "invented-id", "line": i, "text": m.group(0)[:80]})
            for m in ISBN.finditer(line):
                if re.sub(r"[^0-9Xx]", "", m.group(0)).lower() not in digits:
                    problems.append({"rule": "invented-id", "line": i, "text": m.group(0)[:80]})
    return problems


def main(argv):
    args = argv[1:]
    refs = None
    if "--refs" in args:
        k = args.index("--refs")
        try:
            refs = json.load(open(args[k + 1], encoding="utf-8"))
        except (OSError, IndexError, ValueError) as e:
            print(json.dumps({"error": str(e)}))
            return 2
        del args[k:k + 2]
    if len(args) != 1:
        print(json.dumps({"error": "Usage: report_lint.py <report.md> [--refs reference-check.json]"}))
        return 2
    try:
        text = open(args[0], encoding="utf-8").read()
    except OSError as e:
        print(json.dumps({"error": str(e)}))
        return 2
    p = lint(text, refs)
    print(json.dumps({"problems": p}, indent=2))
    return 1 if p else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
