#!/usr/bin/env python3
"""tracer_changelog_rows.py — Phase 5b: the THIRD changelog signal for Step 7.

The structured diff (`diff_published.py`) and the publisher's own ship ledger
(POLISH/AUDIT/TIER rows) show that code *changed* but not *why* it changed or how
*severe* the fix was — that detail lives in the **skill-tracer audit ledger**
(`$XDG_DATA_HOME/skill-tracer-audit-ledger/<skill>.md` — defaults to
`~/.local/share/skill-tracer-audit-ledger/<skill>.md` — CODE-REVIEW / TRACE / REVIEW
rows). This selects the rows added **since the last ship** (Runtime newer than the
last ship's manifest timestamp) so the changelog's **Fixed** section can name the
real bugs and the bump can reflect their severity.

**READ-ONLY on the tracer ledger** — this reads skill-tracer's audit *output*, never
edits the skill (the "don't edit skill-tracer" boundary holds).

Only rows that record an applied change are emitted — Address beginning `FIX` or
`STRENGTHEN`. A `USER-PAUSE` (no change made) or a `would-*` verify-only row (nothing
applied) is not a changelog-worthy change and is dropped.

Usage:
    tracer_changelog_rows.py <skill> [--since <ISO-ts>] [--ledger <path>]
                                     [--manifest <path>] [--json]
      <skill>      skill name (keys both the tracer ledger and the ship manifest)
      --since      cutoff ISO timestamp (exclusive); rows with Runtime > cutoff are
                   kept. Default: the ship manifest's `timestamp` (the last ship).
                   No --since and no manifest → no cutoff (every applied row).
      --ledger     override the tracer-ledger path (default: the conventional path)
      --manifest   override the ship-manifest path (default: the conventional path)
      --json       emit structured JSON instead of the prompt-slot text block.

Exit: 0 ok (including zero rows / no cutoff); 1 no tracer ledger for the skill (the
caller degrades to the two-signal changelog — no regression); 2 usage / path error.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

TRACER_LEDGER_DIR = (
    Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share")))
    / "skill-tracer-audit-ledger"
)
SHIP_LEDGER_DIR = Path.home() / ".claude" / "skill-publisher-ledger"

# The tracer's correctness/fix phases. Any data row carries one of these.
CHANGELOG_PHASES = {"CODE-REVIEW", "TRACE", "REVIEW"}


def _manifest_timestamp(manifest_path: Path) -> str | None:
    """The last ship's timestamp from the ship manifest, or None if absent/unreadable."""
    if not manifest_path.is_file():
        return None
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8")).get("timestamp")
    except (OSError, json.JSONDecodeError):
        return None


def parse_rows(ledger_text: str) -> list[dict]:
    """Parse the pipe-delimited data rows of a tracer ledger into dicts. Tolerates the
    7-column `| Runtime | Round | Phase | Cluster | Root cause | Address | Flags |`
    form; skips the header, the `|---|` separator, comment lines, and short rows."""
    rows = []
    for line in ledger_text.split("\n"):
        s = line.strip()
        if not s.startswith("|") or s.startswith("|---") or "---" in s.split("|")[1:2]:
            continue
        # Split and drop the leading/trailing empty cells from the outer pipes.
        cells = [c.strip() for c in s.split("|")[1:-1]]
        if len(cells) < 7:
            continue
        runtime, rnd, phase, cluster, root, addr, flags = cells[:7]
        # Skip the header row.
        if runtime.lower() == "runtime" or phase.lower() == "phase":
            continue
        rows.append({"runtime": runtime, "round": rnd, "phase": phase,
                     "cluster": cluster, "root_cause": root, "address": addr, "flags": flags})
    return rows


def select(rows: list[dict], cutoff: str | None) -> list[dict]:
    """Keep rows that record an APPLIED change (FIX/STRENGTHEN) in a changelog phase,
    newer than the cutoff. ISO-8601 `YYYY-MM-DDTHH:MM` timestamps compare correctly as
    strings (fixed-width, lexicographically ordered), so no datetime parsing is needed."""
    out = []
    for r in rows:
        if r["phase"].upper() not in CHANGELOG_PHASES:
            continue
        addr = r["address"].lstrip()
        # Applied change only: FIX / STRENGTHEN. Not USER-PAUSE, not would-* (verify-only).
        if not (addr.startswith("FIX") or addr.startswith("STRENGTHEN")):
            continue
        if cutoff and not (r["runtime"] > cutoff):
            continue
        out.append(r)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="select skill-tracer audit rows since last ship (changelog signal 3)")
    ap.add_argument("skill", help="skill name (keys the tracer ledger + ship manifest)")
    ap.add_argument("--since", default=None, help="cutoff ISO timestamp (exclusive)")
    ap.add_argument("--ledger", default=None, help="override tracer-ledger path")
    ap.add_argument("--manifest", default=None, help="override ship-manifest path")
    ap.add_argument("--json", dest="json_out", action="store_true", help="emit JSON")
    args = ap.parse_args()

    # The skill may be given as an absolute ledger path (basename keys the manifest).
    if args.ledger:
        ledger = Path(args.ledger).expanduser()
        skill = ledger.stem
    elif "/" in args.skill:
        ledger = Path(args.skill).expanduser()
        skill = ledger.stem
    else:
        skill = args.skill
        ledger = TRACER_LEDGER_DIR / f"{skill}.md"

    if not ledger.is_file():
        print(json.dumps({"error": f"no skill-tracer audit ledger for {skill} at {ledger}",
                          "ledger_present": False}), file=sys.stderr)
        return 1

    manifest = Path(args.manifest).expanduser() if args.manifest else SHIP_LEDGER_DIR / f"{skill}.manifest.json"
    cutoff = args.since if args.since is not None else _manifest_timestamp(manifest)

    try:
        rows = select(parse_rows(ledger.read_text(encoding="utf-8")), cutoff)
    except OSError as e:
        print(json.dumps({"error": f"could not read tracer ledger: {e}"}), file=sys.stderr)
        return 2

    if args.json_out:
        print(json.dumps({"ledger_present": True, "skill": skill, "cutoff": cutoff,
                          "count": len(rows), "rows": rows}, indent=2))
    else:
        # Prompt-slot text block: one applied fix per line, with severity-bearing detail.
        if not rows:
            print(f"(no skill-tracer audit rows since the last ship"
                  + (f" at {cutoff}" if cutoff else "") + " — nothing to add from this signal)")
        else:
            print(f"# {len(rows)} skill-tracer audit fix(es) since the last ship"
                  + (f" ({cutoff})" if cutoff else " (all rows — no prior ship recorded)"))
            for r in rows:
                print(f"- [round-{r['round']} {r['phase']} {r['cluster']} {r['flags']}] "
                      f"{r['root_cause']} -> {r['address']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
