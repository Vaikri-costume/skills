#!/usr/bin/env python3
"""Validate a skill's frontmatter `license` against recognized SPDX/OSI identifiers.

A ship-time gate (skill-publisher Step 4 attribution + the github-pr public-PR
gate): pushing to a public upstream publishes the skill under whatever its
frontmatter `license` declares. The prose check ("is it a recognized SPDX
identifier?") was specified with a literal "…" — so the executor re-improvised
the recognized-set each run, accepting `Apache 2.0` (wrong format) on one run and
rejecting it on another. This script makes the membership test deterministic.

Distinct from attribution_lint.py, which only checks that a LICENSE *file* exists;
this checks the frontmatter `license` *value* is a real SPDX identifier. A
publisher-owned script (NOT a vendored copy) — license-VALUE validation is a
ship concern, not part of the builder's scaffold lints.

Policy (matches the publisher's ship-checklist):
  - recognized SPDX id  -> OK (exit 0)
  - absent / unrecognized -> USER-PAUSE (exit 1); the script NEVER auto-sets a
    license — picking one is the user's call.

Pure-stdlib. The recognized set is the common open-source identifiers a skill
would plausibly use; extend via --extra "ID1,ID2" for an uncommon-but-valid one.

Usage:  spdx_check.py <skill-path-or-SKILL.md> [--extra "ID,ID"] [--require]
        --require: treat a MISSING license as a hard failure too (default: missing
                   is still exit 1 / USER-PAUSE, same as unrecognized).

Output JSON: {"license": "<value|null>", "recognized": <bool>, "verdict": "OK|USER-PAUSE|FAIL", "reason": "..."}
           verdict is "FAIL" (not "USER-PAUSE") only when --require is passed AND the license is absent (a present-but-unrecognized license stays USER-PAUSE even under --require).
Exit: 0 recognized; 1 absent/unrecognized (USER-PAUSE); 2 usage / SKILL.md not found.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Common SPDX/OSI identifiers a skill would plausibly declare. Not the full SPDX
# list (hundreds) — the recognized set for "is this a real, usable license id?".
RECOGNIZED = {
    "MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC",
    "MPL-2.0", "LGPL-2.1-only", "LGPL-2.1-or-later", "LGPL-3.0-only", "LGPL-3.0-or-later",
    "GPL-2.0-only", "GPL-2.0-or-later", "GPL-3.0-only", "GPL-3.0-or-later",
    "AGPL-3.0-only", "AGPL-3.0-or-later",
    "CC0-1.0", "CC-BY-4.0", "CC-BY-SA-4.0", "Unlicense", "0BSD", "Zlib",
}
# Common WRONG forms → the correct SPDX id, for a precise nudge.
COMMON_MISTAKES = {
    "APACHE 2.0": "Apache-2.0", "APACHE-2.0": "Apache-2.0", "APACHE2": "Apache-2.0",
    "BSD": "BSD-3-Clause (or BSD-2-Clause)", "GPL": "GPL-3.0-only (pick a version+variant)",
    "GPLV3": "GPL-3.0-only", "GPL-3.0": "GPL-3.0-only (or GPL-3.0-or-later)",
    "LGPL": "LGPL-3.0-only (pick a version+variant)", "CC0": "CC0-1.0",
    "MIT LICENSE": "MIT", "THE UNLICENSE": "Unlicense",
}


def read_license(skill_md: Path) -> str | None:
    text = skill_md.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 4)
    if end < 0:
        return None
    for line in text[4:end].split("\n"):
        m = re.match(r"^license\s*:\s*(.*)$", line)
        if m:
            return m.group(1).strip().strip('"').strip("'") or None
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="SPDX/OSI license-identifier check (ship gate)")
    ap.add_argument("path", help="skill directory or path to its SKILL.md")
    ap.add_argument("--extra", default=None, help="comma-separated extra recognized SPDX ids")
    ap.add_argument("--require", action="store_true",
                    help="treat a MISSING license as a hard FAIL (verdict FAIL) rather than USER-PAUSE; "
                         "use at the public-PR gate where an unlicensed skill must block, not just pause")
    args = ap.parse_args()

    p = Path(args.path).expanduser()
    skill_md = p if p.name == "SKILL.md" else p / "SKILL.md"
    if not skill_md.is_file():
        print(f"ERROR: SKILL.md not found at {skill_md}", file=sys.stderr)
        return 2

    recognized_set = set(RECOGNIZED)
    if args.extra:
        recognized_set |= {x.strip() for x in args.extra.split(",") if x.strip()}

    lic = read_license(skill_md)
    if lic is None:
        verdict = "FAIL" if args.require else "USER-PAUSE"
        reason = ("no `license` in frontmatter — a public PR would publish under an unclear license. "
                  "Set a recognized SPDX id (e.g. MIT) or confirm intent. (Never auto-set — user's call.)")
        if args.require:
            reason += " (--require: a missing license is a hard FAIL at this gate.)"
        result = {"license": None, "recognized": False, "verdict": verdict, "reason": reason}
        print(json.dumps(result, indent=2)); return 1

    if lic in recognized_set:
        result = {"license": lic, "recognized": True, "verdict": "OK", "reason": "recognized SPDX identifier"}
        print(json.dumps(result, indent=2)); return 0

    hint = COMMON_MISTAKES.get(lic.upper())
    reason = f"`{lic}` is not in the common SPDX set"
    if hint:
        reason += f" — did you mean `{hint}`?"
    reason += (
        " USER-PAUSE: fix to a recognized id or confirm intent before a public PR (never auto-set)."
        " If this IS a valid SPDX identifier not in the common set (e.g. EPL-2.0, BSL-1.0),"
        f" re-run with --extra \"{lic}\" to accept it."
    )
    result = {"license": lic, "recognized": False, "verdict": "USER-PAUSE", "reason": reason}
    print(json.dumps(result, indent=2)); return 1


if __name__ == "__main__":
    sys.exit(main())
