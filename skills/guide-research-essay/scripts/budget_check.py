#!/usr/bin/env python3
"""Add the word budgets in an outline, or count the words in a file.

Contract
  budget_check.py FILE [--limit N]   ->  JSON on stdout
      {"sections": [{"line": int, "words": int, "text": str}],
       "sum": int, "stated_total": int or null, "limit": int or null,
       "sum_matches_limit": bool or null, "sum_matches_stated_total": bool or null}
    A budget is a number followed by "word" or "words" on a line. A line
    that starts with "Total" (any case) is the stated total, not a section.
  budget_check.py --count FILE        ->  {"words": int}
Exit code 0 on success, 2 on a usage or read error.
"""
import argparse
import json
import re
import sys

BUDGET = re.compile(r"(\d[\d,]*)\s*words?\b", re.IGNORECASE)


def parse_budgets(text):
    sections, stated_total = [], None
    for number, line in enumerate(text.splitlines(), 1):
        match = BUDGET.search(line)
        if not match:
            continue
        words = int(match.group(1).replace(",", ""))
        if line.strip().lstrip("-*# ").lower().startswith("total"):
            stated_total = words
        else:
            sections.append({"line": number, "words": words, "text": line.strip()})
    return sections, stated_total


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("file")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--count", action="store_true")
    args = parser.parse_args(argv)
    try:
        with open(args.file, encoding="utf-8") as handle:
            text = handle.read()
    except OSError as error:
        print(f"cannot read {args.file}: {error}", file=sys.stderr)
        return 2
    if args.count:
        print(json.dumps({"words": len(text.split())}))
        return 0
    sections, stated_total = parse_budgets(text)
    total = sum(item["words"] for item in sections)
    print(json.dumps({
        "sections": sections,
        "sum": total,
        "stated_total": stated_total,
        "limit": args.limit,
        "sum_matches_limit": None if args.limit is None else total == args.limit,
        "sum_matches_stated_total": None if stated_total is None else total == stated_total,
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
