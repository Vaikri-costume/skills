#!/usr/bin/env python3
"""verdict_table.py - check a rubric verdict table against the rubric.

Usage: verdict_table.py <rubric.md> <report.md> [--draft <draft>]

Rubric contract: each criterion is a list item (`- `, `* `, `1.`, `1)`) or, if
the file has no list items, a non-empty line. Report contract: a markdown
table whose columns are Criterion | Verdict | Quoted line (header row names
the columns; the first two are positional, the third is the quote cell).
Allowed verdict words (case-insensitive): met, partly, not met,
not found in the draft.
Checks (each failure is one entry in "problems"):
  missing-criterion  a rubric criterion has no row
  order              rows are not in the rubric's order
  verdict-word       a verdict outside the allowed list
  quote-missing      met/partly with an empty quote cell
  quote-not-in-draft (with --draft) a quote that is not in the draft
  not-found-quote    'not found in the draft' row that still carries a quote
Output: {"problems": [...], "rows": n, "criteria": n}; exit 1 on problems,
2 on bad input.
"""
import json
import re
import sys

ALLOWED = {"met", "partly", "not met", "not found in the draft"}
ITEM = re.compile(r"^\s*(?:[-*]|\d+[.)])\s+(.*\S)\s*$")


def fold(s):
    s = s.replace("‘", "'").replace("’", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"[\s*_`]+", " ", s).strip().casefold()


def criteria(text):
    items = [m.group(1) for m in map(ITEM.match, text.splitlines()) if m]
    if not items:
        items = [l.strip() for l in text.splitlines() if l.strip() and not l.lstrip().startswith("#")]
    return items


def rows(text):
    out = []
    for line in text.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 2 or set("".join(cells)) <= set("-: "):
            continue
        out.append(cells)
    if out and out[0][1].casefold().strip("* ") in ("verdict", "status", "result"):
        out = out[1:]
    return out


def check(rubric_text, report_text, draft_text=None):
    crit = criteria(rubric_text)
    rws = rows(report_text)
    problems = []
    positions = []
    for c in crit:
        key = fold(c)[:40]
        idx = next((i for i, r in enumerate(rws) if key and (key in fold(r[0]) or fold(r[0])[:40] in fold(c))), None)
        if idx is None:
            problems.append({"rule": "missing-criterion", "detail": c})
        else:
            positions.append(idx)
    if positions != sorted(positions):
        problems.append({"rule": "order", "detail": "rows are not in the rubric's order"})
    dfold = fold(draft_text) if draft_text is not None else None
    # Only rows that match a rubric criterion are judged; other tables in the report are ignored.
    for r in [rws[i] for i in sorted(set(positions))]:
        verdict = fold(r[1]).strip("*. ")
        quote = r[2].strip() if len(r) > 2 else ""
        empty = quote in ("", "-", "—", "–", "n/a")
        if verdict not in ALLOWED:
            problems.append({"rule": "verdict-word", "detail": f"{r[0][:40]}: {r[1]}"})
            continue
        if verdict in ("met", "partly") and empty:
            problems.append({"rule": "quote-missing", "detail": r[0][:40]})
        if verdict == "not found in the draft" and not empty:
            problems.append({"rule": "not-found-quote", "detail": r[0][:40]})
        if dfold is not None and not empty and verdict in ("met", "partly"):
            for q in re.findall(r'["“]([^"”]{6,})["”]', quote) or [quote]:
                if fold(q).strip(".… ") not in dfold:
                    problems.append({"rule": "quote-not-in-draft", "detail": q[:60]})
    return {"problems": problems, "rows": len(rws), "criteria": len(crit)}


def main(argv):
    args = argv[1:]
    draft = None
    if "--draft" in args:
        i = args.index("--draft")
        try:
            draft = open(args[i + 1], encoding="utf-8").read()
        except (IndexError, OSError) as e:
            print(json.dumps({"error": str(e)})); return 2
        del args[i:i + 2]
    if len(args) != 2:
        print(json.dumps({"error": "Usage: verdict_table.py <rubric.md> <report.md> [--draft <draft>]"}))
        return 2
    try:
        rub = open(args[0], encoding="utf-8").read()
        rep = open(args[1], encoding="utf-8").read()
    except OSError as e:
        print(json.dumps({"error": str(e)})); return 2
    res = check(rub, rep, draft)
    print(json.dumps(res, indent=2))
    return 1 if res["problems"] else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
