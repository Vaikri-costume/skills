#!/usr/bin/env python3
"""Mechanical isolation check for a baseline run's transcript.md.

Input: --transcript PATH --skill-name NAME [--allow SUBSTR ...] [--run-dir DIR].
A baseline is clean only if transcript.md has a `## Isolation Check` section and nothing in the
whole file contains a path-like token (one with a "/") holding the skill name or `/skills/<something>`,
or an absolute path ending in `SKILL.md` outside --run-dir (case-insensitive). Prose that merely names
the strings is not a hit. A bare mention of SKILL.md, or a relative path, is not a hit:
a baseline that builds a skill legitimately writes its own SKILL.md.  --allow lists substrings
that may appear (named sibling skills or a skill snapshot folder the task legitimately hands the
baseline); an allowed substring also covers the rest of the path-like token it starts.

Exit 0 clean; exit 1 contaminated or no Isolation Check section (discard and re-dispatch);
exit 2 transcript missing (also a failure: re-dispatch). With --run-dir each failure, exit 1 or 2, is counted in
DIR/isolation_attempts.json; at 3 failures the JSON says "cap_reached": true, and the caller
stops and asks the user instead of dispatching a fourth time.
"""
import argparse
import json
import re
import sys
from pathlib import Path

CAP = 3
ECHO = "otherwise access any file or directory whose path"
HEADING = re.compile(r"(?m)^##\s+Isolation Check\s*$")


def check(text, skill_name, allow=(), own_dir=None):
    hits = []
    # a baseline may quote the dispatch constraint itself; that line names the forbidden strings but touches nothing
    scrubbed = "\n".join(l for l in text.split("\n") if ECHO not in l)
    if own_dir:
        scrubbed = re.sub(re.escape(str(own_dir).rstrip("/")) + r"[^\s`'\"]*", "", scrubbed)
    # An allowed substring also covers the rest of the path-like token it starts, so allowing a snapshot
    # folder covers the SKILL.md inside it instead of leaving "/SKILL.md" behind.
    for a in allow:
        scrubbed = re.sub(re.escape(a) + r"[^\s`'\",()\[\]]*", "", scrubbed)
    # Only path-like tokens (containing "/") count: a baseline explaining its own constraints in prose
    # ("no skill-creator-ccvw path was accessed") names the strings without touching anything.
    for tok in re.findall(r"[^\s`'\",()\[\]]+", scrubbed):
        if "/" not in tok:
            continue
        kinds = []
        if skill_name.lower() in tok.lower():
            kinds.append("skill name")
        if re.search(r"/skills/[^/\s]", tok):
            kinds.append("/skills/ path")
        if re.search(r"^(?:/|~).*SKILL\.md$", tok, re.IGNORECASE):
            kinds.append("SKILL.md path")
        for kind in kinds:
            hits.append({"kind": kind, "line": tok[:200]})
    problems = []
    if not HEADING.search(text):
        problems.append("no '## Isolation Check' section")
    return hits, problems


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--transcript", required=True)
    ap.add_argument("--skill-name", required=True)
    ap.add_argument("--allow", action="append", default=[])
    ap.add_argument("--run-dir")
    a = ap.parse_args(argv)
    p = Path(a.transcript)
    missing = not p.is_file()
    if missing:
        clean = False
        out = {"clean": False, "error": f"transcript not found: {p}"}
    else:
        hits, problems = check(p.read_text(encoding="utf-8", errors="replace"), a.skill_name, a.allow, a.run_dir)
        clean = not hits and not problems
        out = {"clean": clean, "hits": hits, "problems": problems}
    # A missing transcript counts toward the same per-run cap, so a baseline that never writes one
    # cannot be re-dispatched without limit.
    if a.run_dir and not clean:
        f = Path(a.run_dir) / "isolation_attempts.json"
        try:
            n = json.loads(f.read_text()).get("failures", 0)
        except (OSError, ValueError):
            n = 0
        n += 1
        try:
            f.write_text(json.dumps({"failures": n}))
        except OSError:
            pass  # --run-dir missing or unwritable: report this check's result anyway, uncounted
        out["failures"] = n
        out["cap_reached"] = n >= CAP
    print(json.dumps(out, indent=2))
    if missing:
        return 2
    return 0 if clean else 1


if __name__ == "__main__":
    sys.exit(main())
