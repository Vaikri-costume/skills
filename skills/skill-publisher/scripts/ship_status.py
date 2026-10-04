#!/usr/bin/env python3
"""ship_status.py — Phase 4 on-demand post-merge follow-up for skill-publisher.

Reads the ship manifest (`~/.claude/skill-publisher-ledger/<skill>.manifest.json`,
written by ship_manifest.py at Step 10), reports the PR's merge state via `gh pr
view`, and — when the upstream **squash/rebase-merged** so the ship-branch commit
the tag points at was discarded — detects (and optionally re-points) the **dangling
ship tag** to the merge commit. Also flags marketplace-catalog staleness (the
catalog's recorded ref vs what shipped).

**Pull-based, on demand — NOT a background poller** (a PR-watcher is out of scope;
the skill is terminal). When `gh`/network is unavailable every remote check
**degrades to "unverified"** (mirrors `verify_ship.py`'s offline discipline) — never
a hard failure.

Usage:
    ship_status.py --status <skill> [--repoint-tag] [--catalog <path>] [--json]
        --repoint-tag : actually move a dangling ship tag to the merge commit
                        (default: detect + REPORT only — re-pointing force-updates a
                        remote ref, so it is opt-in / outward-facing).
        --catalog     : marketplace catalog JSON (default: the claude-plugins-official
                        catalog); checked for staleness vs the shipped version.

Exit: 0 status reported (including `unverified`); 1 no manifest for the skill;
      2 usage / path error.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

LEDGER_DIR = Path.home() / ".claude" / "skill-publisher-ledger"
DEFAULT_CATALOG = (Path.home() / ".claude" / "plugins" / "marketplaces"
                   / "claude-plugins-official" / ".claude-plugin" / "marketplace.json")

# github.com/<owner>/<repo>(/pull/<n>) — owner/repo are the two path segments.
_PR_RE = re.compile(r"github\.com[/:]+([^/]+)/([^/#?]+?)(?:\.git)?/pull/(\d+)", re.I)
_REPO_RE = re.compile(r"github\.com[/:]+([^/]+)/([^/#?]+?)(?:\.git)?(?:[/#?]|$)", re.I)


def _gh(args: list[str], timeout: int = 20) -> tuple[int, str, str]:
    """Run a gh command; (rc, stdout, stderr). rc 127 if gh is absent."""
    if not shutil.which("gh"):
        return 127, "", "gh not on PATH"
    try:
        r = subprocess.run(["gh", *args], capture_output=True, text=True,
                           encoding="utf-8", timeout=timeout)
        return r.returncode, r.stdout, r.stderr
    except (subprocess.TimeoutExpired, OSError) as e:
        return 1, "", f"gh error: {e}"


def read_manifest(skill: str) -> dict | None:
    path = LEDGER_DIR / f"{skill}.manifest.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


# ── PR merge state ──────────────────────────────────────────────────────────────

def check_pr(pr_url: str) -> dict:
    """gh pr view → {state, merged_at, merge_commit} or an `unverified` degrade."""
    rc, out, err = _gh(["pr", "view", pr_url, "--json", "state,mergedAt,mergeCommit"])
    if rc == 127:
        return {"state": "unverified", "detail": "gh not installed — cannot check merge state"}
    if rc != 0:
        return {"state": "unverified", "detail": f"gh pr view failed: {(err or out).strip()[:120]}"}
    try:
        d = json.loads(out)
    except json.JSONDecodeError:
        return {"state": "unverified", "detail": "gh pr view returned no parseable JSON"}
    mc = d.get("mergeCommit") or {}
    return {"state": (d.get("state") or "UNKNOWN"),
            "merged_at": d.get("mergedAt"),
            "merge_commit": mc.get("oid")}


# ── dangling-tag detection + re-point ─────────────────────────────────────────────

def _tag_commit(owner: str, repo: str, tag: str) -> str | None:
    """The commit the tag ultimately points at (deref an annotated tag), or None."""
    rc, out, _ = _gh(["api", f"repos/{owner}/{repo}/git/ref/tags/{tag}"])
    if rc != 0:
        return None
    try:
        obj = json.loads(out).get("object", {})
    except json.JSONDecodeError:
        return None
    sha, typ = obj.get("sha"), obj.get("type")
    if typ == "commit":
        return sha
    if typ == "tag" and sha:  # annotated tag → deref to the commit
        rc2, out2, _ = _gh(["api", f"repos/{owner}/{repo}/git/tags/{sha}"])
        if rc2 == 0:
            try:
                return json.loads(out2).get("object", {}).get("sha")
            except json.JSONDecodeError:
                return None
    return sha


def check_tag(owner: str, repo: str, tag: str, merge_commit: str | None,
              merge_strategy_unknown: bool, repoint: bool) -> dict:
    """Detect a dangling ship tag (its commit not reachable from the default branch,
    as happens on squash/rebase merge) and optionally re-point it to merge_commit."""
    tcommit = _tag_commit(owner, repo, tag)
    if tcommit is None:
        return {"status": "unverified", "detail": f"could not resolve tag {tag} (gh/network or tag absent)"}
    if merge_commit and tcommit == merge_commit:
        return {"status": "ok", "detail": "tag already points at the merge commit"}
    # Reachability: is the tag's commit an ancestor of the default branch? compare
    # <default>...<tcommit>: status "behind"/"identical" = reachable (merge-commit
    # merge preserved it); "diverged"/"ahead" = orphaned (squash/rebase discarded it).
    rc, out, _ = _gh(["api", f"repos/{owner}/{repo}/compare/HEAD...{tcommit}"])
    if rc != 0:
        # Can't compare — fall back to the manifest's intent flag.
        if merge_strategy_unknown and merge_commit:
            dangling = True
            detail = "compare unavailable; merge_strategy_unknown set → treating tag as dangling"
        else:
            return {"status": "unverified", "detail": "could not compare tag to default branch"}
    else:
        try:
            status = json.loads(out).get("status", "")
        except json.JSONDecodeError:
            status = ""
        dangling = status in ("diverged", "ahead")
        detail = f"tag commit is {status or 'unknown'} vs default branch"
    if not dangling:
        return {"status": "ok", "detail": detail}
    # Dangling.
    res = {"status": "dangling", "tag_commit": tcommit, "merge_commit": merge_commit, "detail": detail}
    if not merge_commit:
        res["detail"] += "; no merge commit known — cannot re-point"
        return res
    if not repoint:
        res["detail"] += f"; re-run with --repoint-tag to move {tag} → {merge_commit[:12]}"
        return res
    rc, _, err = _gh(["api", "-X", "PATCH", f"repos/{owner}/{repo}/git/refs/tags/{tag}",
                      "-f", f"sha={merge_commit}", "-F", "force=true"])
    if rc == 0:
        res["status"] = "repointed"
        res["detail"] = f"re-pointed {tag} → {merge_commit[:12]} (the merge commit)"
    else:
        res["detail"] += f"; re-point FAILED: {(err or '').strip()[:120]}"
    return res


# ── marketplace catalog staleness ─────────────────────────────────────────────────

def check_catalog(catalog: Path, owner: str, repo: str, version: str) -> dict:
    """Best-effort: find the catalog entry for this repo and compare its recorded
    source ref to the shipped version. Advisory only."""
    try:
        data = json.loads(catalog.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"status": "unchecked", "detail": f"catalog not readable at {catalog}"}
    slug = f"{owner}/{repo}".lower()
    for e in data.get("plugins", []):
        if not isinstance(e, dict):
            continue
        src = e.get("source", {})
        url = (src.get("url", "") if isinstance(src, dict) else "") or ""
        m = _REPO_RE.search(url)
        if m and f"{m.group(1)}/{m.group(2)}".lower() == slug:
            ref = (src.get("ref") if isinstance(src, dict) else "") or ""
            # Compare the catalog ref's embedded version to the shipped one. Split on
            # "-" FIRST, then strip the leading "v" from the version segment — the ship
            # tag is `<name>-v<version>` (github_pr.py), so stripping "v" off the whole
            # ref leaves it untouched (it doesn't start with "v") and the version keeps
            # its "v", spuriously failing the equality below.
            cat_ver = ref.split("-")[-1].lstrip("v") if ref else ""
            if version and cat_ver and cat_ver != version:
                return {"status": "stale", "catalog_ref": ref, "shipped": version,
                        "detail": f"catalog ref {ref!r} != shipped {version} — catalog may need a refresh"}
            return {"status": "current", "catalog_ref": ref, "entry": e.get("name")}
    return {"status": "absent", "detail": f"no catalog entry for {slug} (not a marketplace skill, or not listed)"}


# ── main ──────────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="skill-publisher post-ship status (Phase 4)")
    ap.add_argument("--status", metavar="SKILL", required=True, help="skill name (manifest key)")
    ap.add_argument("--repoint-tag", action="store_true",
                    help="move a dangling ship tag to the merge commit (force-updates the remote ref)")
    ap.add_argument("--catalog", default=str(DEFAULT_CATALOG), help="marketplace catalog JSON")
    ap.add_argument("--json", dest="json_out", action="store_true", help="emit JSON")
    args = ap.parse_args()

    m = read_manifest(args.status)
    if m is None:
        print(f"ERROR: no ship manifest for {args.status!r} "
              f"(expected {LEDGER_DIR / (args.status + '.manifest.json')}) — has it shipped?",
              file=sys.stderr)
        return 1

    result: dict = {"skill": args.status, "version": m.get("version"), "tier": m.get("tier"),
                    "shipped_at": m.get("timestamp")}
    pr_url = m.get("pr_url")
    if not pr_url:
        result["pr"] = {"state": "n/a", "detail": "no PR opened (local-only / no-upstream / degraded ship)"}
    else:
        pr = check_pr(pr_url)
        pr["url"] = pr_url
        result["pr"] = pr
        prm = _PR_RE.search(pr_url)
        owner, repo = (prm.group(1), prm.group(2)) if prm else (None, None)
        # Tag re-point only matters once merged.
        if m.get("tag") and owner and pr.get("state") == "MERGED":
            result["tag"] = check_tag(owner, repo, m["tag"], pr.get("merge_commit"),
                                      bool(m.get("merge_strategy_unknown")), args.repoint_tag)
        elif m.get("tag"):
            result["tag"] = {"status": "n/a", "detail": f"tag {m['tag']} — re-point check applies only after merge"}
        # Catalog staleness (advisory).
        if owner:
            result["catalog"] = check_catalog(Path(args.catalog).expanduser(), owner, repo, m.get("version", ""))

    if args.json_out:
        print(json.dumps(result, indent=2))
    else:
        print(f"Ship status: {args.status} v{result['version']} (tier {result['tier']}, shipped {result['shipped_at']})")
        pr = result["pr"]
        print(f"  PR     : {pr['state']}" + (f" — {pr.get('detail','')}" if pr.get("detail") else "")
              + (f"  (merged {pr['merged_at']})" if pr.get("merged_at") else ""))
        if "tag" in result:
            t = result["tag"]
            print(f"  tag    : {t['status']}" + (f" — {t['detail']}" if t.get("detail") else ""))
        if "catalog" in result:
            c = result["catalog"]
            print(f"  catalog: {c['status']}" + (f" — {c['detail']}" if c.get("detail") else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
