#!/usr/bin/env python3
"""combine_findings.py - combine the four pair-synthesised finding lists into one numbered list.

Usage: combine_findings.py <run_dir> [--out <file>]

Input contract: <run_dir> holds Argument-merged.md, Evidence-merged.md,
Clarity-merged.md and Voice-merged.md (output of synthesise_pairs.py; a missing
file is skipped). Findings keep every field they carry (Layer, Would change if,
Analysis confidence, ...).
What it does:
  1. Cross-domain merge: a Clarity or Voice finding whose normalised
     `Current text` equals one in Argument or Evidence is folded into that
     finding, which is tagged `Domain: Cross-domain (merged)` and takes the
     higher Severity.
  2. Every finding gets a `Domain:` line (Argument structure, Evidence,
     Clarity, Voice or Cross-domain (merged)).
  3. Order by layer (foundation, structure, paragraph, sentence), then by
     severity (High, Medium, Low), then by domain order; renumber 1..n.
Output: the list (default <run_dir>/findings.md) and a one-line count on stdout.
Exit 2 and a JSON error on bad input.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "shared"))
import findings_lib as fl  # noqa: E402

DOMAINS = [("Argument", "Argument structure"), ("Evidence", "Evidence"), ("Clarity", "Clarity"), ("Voice", "Voice")]
LAYER = {"foundation": 0, "structure": 1, "paragraph": 2, "sentence": 3}
SEV = {"high": 0, "medium": 1, "low": 2}


def first_word(value, table, default):
    w = (value or "").split()
    return table.get(w[0].strip(" —-").lower(), default) if w else default


def combine(run_dir):
    items = []
    for rank, (stem, label) in enumerate(DOMAINS):
        path = os.path.join(run_dir, stem + "-merged.md")
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as fh:
            parsed = fl.parse_findings(fh.read())
        for f in parsed:
            f["domain"], f["rank"] = label, rank
            items.append(f)
    anchors, out = {}, []
    for f in items:
        q = fl.norm(fl.get(f, "Current text"))
        if f["rank"] < 2:
            anchors.setdefault(q, f)
            out.append(f)
        elif q in anchors:
            base = anchors[q]
            base["domain"] = "Cross-domain (merged)"
            if first_word(fl.get(f, "Severity"), SEV, 3) < first_word(fl.get(base, "Severity"), SEV, 3):
                base["fields"]["Severity"] = fl.get(f, "Severity")
        else:
            out.append(f)
    out.sort(key=lambda f: (first_word(fl.get(f, "Layer"), LAYER, 2),
                            first_word(fl.get(f, "Severity"), SEV, 3), f["rank"]))
    blocks = [fl.render(f, i).rstrip() + "\nDomain: " + f["domain"] for i, f in enumerate(out, 1)]
    return "\n\n".join(blocks) + ("\n" if blocks else ""), len(out)


def main(argv):
    args = argv[1:]
    out_path = None
    if "--out" in args:
        i = args.index("--out")
        out_path = args[i + 1]
        del args[i:i + 2]
    if len(args) != 1 or not os.path.isdir(args[0]):
        print(json.dumps({"error": "Usage: combine_findings.py <run_dir> [--out <file>]"}))
        return 2
    text, n = combine(args[0])
    with open(out_path or os.path.join(args[0], "findings.md"), "w", encoding="utf-8") as fh:
        fh.write(text)
    print(f"{n} findings")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
