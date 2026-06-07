#!/usr/bin/env python3
"""Post-ship verification for skill-publisher Step 10.

Before reporting a ship as done, confirm it actually landed — that a prior step
didn't silently half-complete. Four deterministic checks:
  1. version_present   — the new <version> appears in HISTORY.md frontmatter
  2. changelog_present — a changelog heading for <version> exists in HISTORY.md body
  3. artifact_present  — the package artifact exists at its path (claude-users/model-agnostic)
  4. pr_resolves       — the PR URL resolves (gh pr view / HTTP 200)

Checks 1–3 are local/deterministic. Check 4 is network-dependent: if `gh` is
absent or the network is unavailable, it DEGRADES to "unverified" (not a failure)
— a missing tool must not fail a ship that otherwise landed.

Pure-stdlib (uses `gh` if present for the PR check, else urllib HEAD, else degrade).

Usage:
    verify_ship.py <skill-path> --version X.Y.Z [--artifact <path>] [--pr-url <url>]
        --artifact / --pr-url omitted = that check is "n/a" (skipped, not failed)
        (personal-tier ships have no artifact and no PR — pass neither.)

Output JSON: {version_present, changelog_present, artifact: {...}, pr: {...}, all_required_ok}
Exit: 0 all required checks passed (n/a + unverified don't fail); 1 a required check FAILED; 2 usage.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path


def check_history(history: Path, version: str) -> tuple[bool, bool]:
    """(version_present_in_frontmatter, changelog_heading_present_in_body)."""
    if not history.is_file():
        return False, False
    text = history.read_text()
    fm = None
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end >= 0:
            fm = text[4:end]
    body = text[len(fm) + 9:] if fm is not None else text  # 4 ("---\n") + len(fm) + 5 ("\n---\n")
    vesc = re.escape(version)
    version_present = bool(re.search(rf"^version\s*:\s*['\"]?{vesc}['\"]?\s*$", fm, re.MULTILINE))
    # changelog heading like '### 1.2.0', '## 1.2.0 — date', '### v1.2.0',
    # '### [1.2.0]' (keepachangelog format), or '### 1.2.0 — date (shipped)'.
    # \[? allows an optional leading '[' (keepachangelog style).
    # \b after a digit is a valid word boundary (next char must be non-alphanumeric);
    # works correctly for all-numeric-ending versions and pre-release tags like
    # 1.0.0-alpha (\b after 'a'). Would also match '1.2.0' inside '1.2.0-shipped'
    # at the boundary before '-' — intended, since '-' is non-word.
    changelog_present = bool(re.search(rf"^#{{1,4}}\s*\[?v?{vesc}\b", body, re.MULTILINE))
    return version_present, changelog_present


def check_pr(pr_url: str) -> dict:
    """Try gh first, then a plain HTTP HEAD; degrade to 'unverified' if neither works."""
    if shutil.which("gh"):
        try:
            r = subprocess.run(["gh", "pr", "view", pr_url], capture_output=True, text=True, timeout=20)
            if r.returncode == 0:
                return {"status": "resolves", "via": "gh"}
            return {"status": "unverified", "via": "gh", "detail": f"gh exit {r.returncode}: {r.stderr.strip()[:120]}"}
        except (subprocess.TimeoutExpired, OSError) as e:
            return {"status": "unverified", "via": "gh", "detail": f"gh error: {e}"}
    # Fallback: HTTP reachability check (weak — only confirms URL is reachable,
    # NOT that the PR exists). A private/nonexistent GitHub PR commonly returns 200
    # (SPA shell) or a 3xx redirect to a login page, both < 400. Use this path only
    # when `gh` is absent; treat the result as a connectivity hint, not a PR-exists
    # confirmation. `gh pr view` is the reliable check when available.
    try:
        req = urllib.request.Request(pr_url, method="HEAD", headers={"User-Agent": "verify_ship"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            code = resp.status
        return {"status": "unverified", "via": "http", "code": code,
                "detail": "HTTP reachability only — a 200 or 3xx does not confirm the PR exists"}
    except Exception as e:
        return {"status": "unverified", "via": "http", "detail": f"network unavailable: {str(e)[:100]}"}


def main() -> int:
    ap = argparse.ArgumentParser(description="Post-ship verification (publisher Step 10)")
    ap.add_argument("skill_path")
    ap.add_argument("--version", required=True)
    ap.add_argument("--artifact", default=None, help="package artifact path (omit for personal tier)")
    ap.add_argument("--pr-url", default=None, help="PR URL (omit if no PR opened)")
    args = ap.parse_args()

    root = Path(args.skill_path).expanduser()
    skill_root = root if root.is_dir() else root.parent
    history = skill_root / "HISTORY.md"

    version_present, changelog_present = check_history(history, args.version)

    if args.artifact:
        ap_path = Path(args.artifact).expanduser()
        artifact = {"status": "present" if ap_path.is_file() else "MISSING", "path": str(ap_path)}
    else:
        artifact = {"status": "n/a", "detail": "no artifact (personal tier or not packaged)"}

    pr = check_pr(args.pr_url) if args.pr_url else {"status": "n/a", "detail": "no PR opened"}

    # Required = the local deterministic checks + any artifact that was claimed.
    # 'unverified' (PR network) and 'n/a' never fail the ship.
    required_failures = []
    if not version_present:
        required_failures.append(f"version {args.version} not in HISTORY.md frontmatter")
    if not changelog_present:
        required_failures.append(f"no changelog heading for {args.version} in HISTORY.md")
    if artifact["status"] == "MISSING":
        required_failures.append(f"package artifact missing at {artifact['path']}")

    result = {
        "skill": str(skill_root),
        "version": args.version,
        "version_present": version_present,
        "changelog_present": changelog_present,
        "artifact": artifact,
        "pr": pr,
        "required_failures": required_failures,
        "all_required_ok": not required_failures,
    }
    print(json.dumps(result, indent=2))
    if pr.get("status") == "unverified":
        print(f"NOTE: PR check unverified ({pr.get('detail','')}) — not a failure; verify the URL manually.", file=sys.stderr)
    return 1 if required_failures else 0


if __name__ == "__main__":
    sys.exit(main())
