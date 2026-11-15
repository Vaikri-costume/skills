#!/usr/bin/env python3
"""report_lint.py - guard a finished ai-detection-check report before it is relayed.

Usage: report_lint.py <report.md>

Quoted text (inside double quotes, in `backticks` or on lines starting `>`) and table rows (lines
starting `|`, which hold the writer's own words) are ignored. Reports:
  tldr        a TLDR line
  offer       an offer of further help or another check ("would you like", "I can also", ...)
  next-line   a line starting `Next:`
  gendered    he/she/him/her/his/hers/himself/herself about the writer
  grade       a numeric grade or score
  ai-score    a percentage or likelihood that the text is machine-written
  verdict     a statement that the text is, or is not, machine-written
  evasion     advice on avoiding, lowering or beating a detector, or on humanising text
  american    an -ize/-ization form in the report's own prose (strict British -ise)
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
    ("ai-score", re.compile(r"\b\d{1,3}(?:\.\d+)?\s?%\s*(?:ai|machine|likely|chance)|\b(?:likelihood|probability|chance) (?:that|of) (?:it|this|the (?:text|draft|essay)|ai|machine)\b", re.I)),
    ("verdict", re.compile(r"\b(?:is|was|were|are) (?:probably |likely |definitely |clearly )?(?:written|generated|produced) by (?:an? )?(?:ai|chatgpt|llm|machine|model)\b|\b(?:is|was) (?:ai|machine)[- ](?:written|generated)\b|\b(?:is|was) human[- ]written\b", re.I)),
    ("evasion", re.compile(r"\b(?:how to|ways to|try to|you can|should) (?:avoid|evade|bypass|beat|lower|reduce|trick) (?:the |a |your )?(?:ai[- ])?(?:detection|detector|detectors|score|flag|checker)\b|\bhumani[sz]e (?:the|your) (?:text|draft)\b", re.I)),
    ("american", re.compile(r"\b\w+(?:iz(?:e|es|ed|ing|ation|ations)|yz(?:e|es|ed|ing))\b", re.I)),
]
ALLOW_IZE = re.compile(r"\b(size[sd]?|sizing|prize[sd]?|seize[sd]?|seizing|capsize[sd]?|maize|baptize|resize[sd]?|downsize[sd]?|oversize[sd]?|-ize|-ization|-yze)\b", re.I)
QUOTED = re.compile(r'"[^"\n]*"|“[^”\n]*”|`[^`\n]*`')


def lint(text):
    problems = []
    for i, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith((">", "|")):
            continue
        stripped = QUOTED.sub(" ", line)
        qs = [k for k, ch in enumerate(line) if ch in '"“”']
        if len(qs) >= 2:
            stripped = line[:qs[0]] + " " + line[qs[-1] + 1:]
        for name, rx in RULES:
            for m in rx.finditer(stripped):
                if name == "american" and ALLOW_IZE.fullmatch(m.group(0)):
                    continue
                problems.append({"rule": name, "line": i, "text": line.strip()[:120]})
                break
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
