#!/usr/bin/env python3
"""fix_blast.py — thin blast-radius driver for Prepass fix classes.

Reads a JSON array of cluster dicts from stdin (as produced by cluster_prepass.py
--json, which wraps them as {"clusters": [...]}). For each cluster, classifies
the fix as TOKEN-BLAST or LOCAL, and for TOKEN-BLAST clusters calls
check_fix_radius to compute the actual blast radius.

Fix-class taxonomy. Keys are the CHECK_IDs of the prepass detectors (detectors/*.py); a check with
no entry is LOCAL, the safe default (a check is TOKEN-BLAST only if its fix changes a shared token
across sites, and its cluster carries that token as the first backtick-quoted name in the
detector's detail):
    refs / steps / dead-script /   → TOKEN-BLAST (the cited path, `Step N` pointer, script name or
      dup-regex                        duplicated regex literal is the shared token; every other
                                       site naming it must be fixed in the same pass)
    substep-label-mismatch /       → LOCAL  (the edit is one reference or one label in one file)
      argparse-flag-undocumented
  Code Review clusters are not classified here: cluster_enforce.py builds their blast (member locs
  plus advisory groups) and the fixer applies fix-impact closure per references/how-to-fix.md.

Usage:
    cluster_prepass.py --json | fix_blast.py --skill-root <dir> \\
        [--touched file1,file2,...] [--allow file1,...] [--ignore-case]

    The --touched list is the set of files the proposed fix will edit.
    For TOKEN-BLAST clusters, check_fix_radius is invoked (via subprocess) to
    find any files that contain the token but are NOT in --touched.

    The output is {"blast_radius": [<one entry per cluster>]}. For LOCAL clusters the entry is:
        {"cluster": "C1", "check": "<check>", "fix_class": "LOCAL", "reason": "...",
         "radius": ["<member loc>", ...]}
    "radius" holds the cluster's distinct member "loc" values in member order ([] when the
    cluster has no members).

    For TOKEN-BLAST clusters the entry includes the full check_fix_radius
    result plus a "blast_exit" key, the check_fix_radius exit code (0 = no uncovered sites,
    1 = uncovered, null on --dry-run; any other code is passed through as-is):
        {"cluster": "C4", "check": "<check>", "fix_class": "TOKEN-BLAST", "token": "<first>",
         "tokens": [...], "blast_exit": 0|1|<other>|null, "auto_touched": [...], "radius_result": {...}}
    "auto_touched" is present when the cluster names a "file", and an "uncovered" list is added
    only when blast_exit is 1.
    "tokens" holds one token per distinct cluster member (each member's first backtick-quoted name,
    as cluster_prepass.py collects them); check_fix_radius runs once per token in "tokens";
    blast_exit is the last code other than 0 or 1 that any token's run gave, else 1 when any token
    has an uncovered site, else 0; radius_result merges files_with_token / uncovered across the
    tokens. A code other than 0 or 1 comes only from an abnormal check_fix_radius run (its exit 2
    usage errors cannot arise here: main() rejects a --skill-root that is not a directory and
    passes no empty token); a run that prints no JSON keeps {"raw_stdout", "raw_stderr"} as its
    per-token result. ledger_cascade.py fill-address, which re-runs this check through
    run_check_fix_radius_all, rejects a FIX whose re-check returns anything but 0.

    Exit status: 0 = no TOKEN-BLAST entry has blast_exit 1 (also when an entry has another
    blast_exit, or carries "error" because no token was found); 1 = at least one entry has
    blast_exit 1; 2 = --skill-root is not a directory.

Options:
    --skill-root DIR   Root of the skill/project tree to scan (passed to
                       check_fix_radius).
    --touched FILES    Comma-separated files the fix will touch.
    --allow FILES      Comma-separated files where the token legitimately
                       stays (passed through to check_fix_radius).
    --ignore-case      Case-insensitive token search.
    --dry-run          Print the check_fix_radius command but do not execute
                       it; TOKEN-BLAST clusters get blast_exit=null.
    --token TOKEN      The token for a TOKEN-BLAST cluster that carries no "tokens"
                       (cluster_prepass.py sets "tokens" whenever a member names one,
                       and those clusters keep their own tokens).

Pure stdlib. Python 3.9+.

KNOWN GAP (TOKEN-BLAST checks, e.g. dead-script / refs):
    check_fix_radius greps the *static* file tree. It cannot see dynamic imports
    (importlib + getattr), reflection or runtime plugin registries, so the caller
    must treat exit 0 as "no static refs found", not as "safe to delete".
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

# Maps check name to fix class (keys = CHECK_IDs of prepass detectors; see the module docstring).
# TOKEN-BLAST: the fix changes a shared token that appears across multiple sites; all sites must be
#              covered in one fix. LOCAL: the fix is self-contained at one site (the default).
_FIX_CLASS: dict[str, str] = {
    "refs":                       "TOKEN-BLAST",
    "steps":                      "TOKEN-BLAST",
    "dead-script":                "TOKEN-BLAST",
    "dup-regex":                  "TOKEN-BLAST",
    "substep-label-mismatch":     "LOCAL",
    "argparse-flag-undocumented": "LOCAL",
}


def classify(check: str) -> str:
    """'TOKEN-BLAST' or 'LOCAL' for a prepass check name; LOCAL for any unrecognised check."""
    return _FIX_CLASS.get(check, "LOCAL")


# ---------------------------------------------------------------------------
# Token extraction for TOKEN-BLAST clusters
# ---------------------------------------------------------------------------

def extract_token(cluster: dict) -> str | None:
    """Extract the shared token from a cluster dict.

    cluster_prepass.py forwards the backtick-quoted names of each finding's detail as
    cluster["tokens"] (fix_blast.main checks every one of them); this fallback covers clusters
    from other producers.

    Fallback strategy (in order):
      1. cluster["token"]             — caller-supplied explicit override
      2. cluster["detail"]            — the first backtick-quoted name in the finding's detail
                                        (None when it quotes none; never the whole sentence)
      3. members' name / detail / token
      4. None                         — caller must supply --token manually
    """
    if "token" in cluster:
        return str(cluster["token"])
    if "detail" in cluster:
        # The detail names the token in backticks, e.g. "`_date_matches_period` ..."
        quoted = re.search(r"`([^`]+)`", str(cluster["detail"]))
        return quoted.group(1) if quoted else None
    members = cluster.get("members", [])
    for m in members:
        name = m.get("name") or m.get("detail") or m.get("token")
        if name:
            return str(name)
    return None


def _cluster_tokens(cluster: dict, cli_token: str | None) -> list[str]:
    """Every token of a cluster, in order: cluster["tokens"] (a list, or one string) when present,
    else the --token CLI value, else extract_token()'s fallback; [] when none is found."""
    raw = cluster.get("tokens")
    if isinstance(raw, list) and raw:
        out: list[str] = []
        for t in raw:
            t = str(t)
            if t and t not in out:
                out.append(t)
        return out
    if isinstance(raw, str) and raw:
        return [raw]
    tok = cli_token or extract_token(cluster) or ""
    return [tok] if tok else []


def blast_tokens(entry: dict) -> list[str]:
    """The tokens a blast entry's closure check covers: its "tokens" list, else its single "token";
    [] when it has neither."""
    toks = entry.get("tokens")
    if isinstance(toks, list) and toks:
        return [str(t) for t in toks if t]
    tok = entry.get("token", "")
    return [str(tok)] if tok else []


# ---------------------------------------------------------------------------
# check_fix_radius runner
# ---------------------------------------------------------------------------

_SCRIPT_DIR = Path(__file__).parent


def run_check_fix_radius(
    *,
    skill_root: str,
    token: str,
    touched: str,
    allow: str,
    ignore_case: bool,
    dry_run: bool,
) -> tuple[int | None, dict | None]:
    """Invoke check_fix_radius.py as a subprocess.

    Returns (exit_code, result_dict).  On dry_run returns (None, None).
    """
    script = _SCRIPT_DIR / "check_fix_radius.py"
    cmd = [sys.executable, str(script), "--skill-root", skill_root, "--token", token]
    if touched:
        cmd += ["--touched", touched]
    if allow:
        cmd += ["--allow", allow]
    if ignore_case:
        cmd.append("--ignore-case")

    if dry_run:
        print(f"[dry-run] would run: {' '.join(cmd)}", file=sys.stderr)
        return None, None

    proc = subprocess.run(cmd, capture_output=True, text=True)
    try:
        result = json.loads(proc.stdout)
    except json.JSONDecodeError:
        result = {"raw_stdout": proc.stdout, "raw_stderr": proc.stderr}
    return proc.returncode, result


def run_check_fix_radius_all(
    *,
    skill_root: str,
    tokens: list[str],
    touched: str,
    allow: str,
    ignore_case: bool,
    dry_run: bool,
) -> tuple[int | None, dict | None]:
    """run_check_fix_radius for every token; exit 1 when any token has an uncovered site (the
    last non-0/1 exit from any token is returned as-is instead). The merged result lists the union of
    files_with_token and uncovered, plus the per-token results under "per_token"."""
    if dry_run:
        for tok in tokens:
            run_check_fix_radius(skill_root=skill_root, token=tok, touched=touched, allow=allow,
                                 ignore_case=ignore_case, dry_run=True)
        return None, None
    worst = 0
    per_token: dict = {}
    with_token: list[str] = []
    uncovered: list[str] = []
    for tok in tokens:
        code, res = run_check_fix_radius(skill_root=skill_root, token=tok, touched=touched,
                                         allow=allow, ignore_case=ignore_case, dry_run=False)
        per_token[tok] = res
        if code not in (0, 1):
            worst = code
        elif code == 1 and worst in (0, 1):
            worst = 1
        for f in (res or {}).get("files_with_token", []):
            if f not in with_token:
                with_token.append(f)
        for f in (res or {}).get("uncovered", []):
            if f not in uncovered:
                uncovered.append(f)
    return worst, {"files_with_token": with_token, "uncovered": uncovered, "per_token": per_token}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(
        description="Compute Prepass fix blast radius per cluster."
    )
    ap.add_argument(
        "--skill-root",
        required=True,
        metavar="DIR",
        help="Root of the skill/project tree to scan.",
    )
    ap.add_argument(
        "--touched",
        default="",
        metavar="FILES",
        help="Comma-separated files the fix will touch.",
    )
    ap.add_argument(
        "--allow",
        default="",
        metavar="FILES",
        help="Comma-separated files where the token legitimately stays.",
    )
    ap.add_argument(
        "--ignore-case",
        action="store_true",
        help="Case-insensitive token search.",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Print check_fix_radius commands but do not execute them.",
    )
    ap.add_argument(
        "--token",
        default="",
        metavar="TOKEN",
        help=(
            "Token for a TOKEN-BLAST cluster whose JSON carries no \"tokens\" "
            "(a cluster with \"tokens\" keeps its own)."
        ),
    )
    args = ap.parse_args()

    root = Path(args.skill_root).expanduser()
    if not root.is_dir():
        print(f"ERROR: --skill-root is not a directory: {root}", file=sys.stderr)
        return 2

    raw = json.load(sys.stdin)
    # Accept either {"clusters": [...]} (cluster_prepass.py --json output)
    # or a bare list.
    clusters: list[dict] = raw.get("clusters", raw) if isinstance(raw, dict) else raw

    results = []
    for c in clusters:
        check = c.get("check", "")
        cid = c.get("cluster", "?")
        fix_class = classify(check)

        if fix_class == "LOCAL":
            # When a cluster carries a "members" list, each member's "loc" is a fix site;
            # radius lists every distinct one in member order so the fixer prompt's blast
            # section shows each site. cluster_prepass.py clusters carry no "members", so
            # their radius is [] (the module docstring's LOCAL entry).
            members = c.get("members", [])
            if members:
                seen_locs: dict[str, None] = {}  # ordered-set via insertion-order dict
                for m in members:
                    loc = m.get("loc", "")
                    if loc and loc not in seen_locs:
                        seen_locs[loc] = None
                member_locs = list(seen_locs)
            else:
                member_locs = []
            results.append({
                "cluster": cid,
                "check": check,
                "fix_class": "LOCAL",
                "reason": "Fix is self-contained at one site; no shared token propagates.",
                "radius": member_locs,
            })
            continue

        # TOKEN-BLAST — every token of the cluster is checked: one cluster can merge several
        # findings (cluster_prepass.py collects each member's backtick tokens), and a site of any
        # of them that the fix leaves untouched is an uncovered site.
        tokens = _cluster_tokens(c, args.token)

        if not tokens:
            results.append({
                "cluster": cid,
                "check": check,
                "fix_class": "TOKEN-BLAST",
                "error": (
                    "Could not extract token from cluster JSON. "
                    "Re-run with --token <def_name>."
                ),
            })
            continue

        # Auto-mark the file where the def lives as touched, so it does not
        # appear in "uncovered" (it IS the edit site, not an external reference).
        # The entry records it as "auto_touched" so ledger_cascade.py fill-address
        # re-runs the closure check with the same touched set the fixer prompt saw.
        cluster_file = c.get("file", "")
        auto_touched_parts: list[str] = []
        if cluster_file:
            abs_cluster_file = (
                Path(cluster_file)
                if Path(cluster_file).is_absolute()
                else root / cluster_file
            )
            auto_touched_parts.append(str(abs_cluster_file))

        # Merge with any caller-supplied --touched list (deduplicated, order preserved).
        caller_touched = [f for f in args.touched.split(",") if f] if args.touched else []
        seen: set[str] = set()
        merged_touched_parts: list[str] = []
        for f in auto_touched_parts + caller_touched:
            if f not in seen:
                seen.add(f)
                merged_touched_parts.append(f)
        merged_touched = ",".join(merged_touched_parts)

        exit_code, radius_result = run_check_fix_radius_all(
            skill_root=str(root),
            tokens=tokens,
            touched=merged_touched,
            allow=args.allow,
            ignore_case=args.ignore_case,
            dry_run=args.dry_run,
        )

        entry: dict = {
            "cluster": cid,
            "check": check,
            "fix_class": "TOKEN-BLAST",
            "token": tokens[0],
            "tokens": tokens,
            "blast_exit": exit_code,  # None on dry-run
        }
        if auto_touched_parts:
            entry["auto_touched"] = auto_touched_parts
        if radius_result is not None:
            entry["radius_result"] = radius_result
            if exit_code == 1:
                entry["uncovered"] = radius_result.get("uncovered", [])
        results.append(entry)

    print(json.dumps({"blast_radius": results}, indent=2))
    # Exit 1 if any TOKEN-BLAST cluster has uncovered sites (blast_exit 1); a blast_exit other than
    # 0 or 1 does not change the exit status, and stays in the entry for the consumer to read.
    any_uncovered = any(
        r.get("blast_exit") == 1 for r in results if r["fix_class"] == "TOKEN-BLAST"
    )
    return 1 if any_uncovered else 0


if __name__ == "__main__":
    sys.exit(main())
