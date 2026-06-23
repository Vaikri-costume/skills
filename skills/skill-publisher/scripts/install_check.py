#!/usr/bin/env python3
"""Install-doc executability check for skill-publisher Step 6.

Step 6 derives a `claude plugins install <org>/<repo>` command by string-parsing
the upstream source URL — with no check that the repo actually exists or that a
marketplace catalog entry is present. A baked-in install command pointing at a
nonexistent/private repo, or naming a plugin not in the catalog, is an outward-
facing error: users run a command that fails.

This probes the derived command's target:
  1. **repo reachability** — `gh repo view <org>/<repo>` (real + accessible?).
     gh absent → a weak HTTP HEAD fallback (reachability hint only). Neither
     available / network down → DEGRADE to "unverified" (NOT a failure), exactly
     like verify_ship.py's PR check.
  2. **marketplace catalog** (optional) — scan the live catalog JSON for an entry
     matching the repo URL or `--marketplace-name`. Reuses marketplace-discover's
     catalog path (`~/.claude/plugins/marketplaces/claude-plugins-official/
     .claude-plugin/marketplace.json`); `--catalog` overrides.

WARNING, not a hard block: a confirmed-bad result (exit 1) is surfaced by Step 6
as a warning; the ship still completes. Only the orchestrator decides whether to
pause — this script reports.

Usage:
    install_check.py (--repo <org/repo> | --source-url <github-url>)
        [--marketplace-name <plugin-name>] [--catalog <path>] [--json]

Exit:
    0  reachable, or unverified (could not check → degrade; never fails the ship)
    1  confirmed problem — repo not found/inaccessible, OR (marketplace) catalog
       entry absent. Surfaced as a warning, not a ship-blocker.
    2  usage error (neither --repo nor --source-url, or an unparseable URL)
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_CATALOG = (Path.home() / ".claude" / "plugins" / "marketplaces"
                   / "claude-plugins-official" / ".claude-plugin" / "marketplace.json")

# github.com/<org>/<repo> — tolerate a trailing .git, a trailing path, and an
# optional scheme. org/repo are the two path segments after the host.
_URL_RE = re.compile(r"github\.com[/:]+([^/]+)/([^/#?]+?)(?:\.git)?(?:[/#?].*)?$", re.I)
_REPO_RE = re.compile(r"^([^/\s]+)/([^/\s]+?)(?:\.git)?$")


def parse_repo(repo: str | None, url: str | None) -> tuple[str, str] | None:
    """Return (org, repo) from --repo or --source-url, or None if unparseable."""
    if repo:
        m = _REPO_RE.match(repo.strip())
        if m:
            return m.group(1), m.group(2)
        return None
    if url:
        m = _URL_RE.search(url.strip())
        if m:
            return m.group(1), m.group(2)
    return None


def check_repo(org: str, name: str) -> dict:
    """gh first, then HTTP HEAD; degrade to 'unverified' if neither works."""
    slug = f"{org}/{name}"
    if shutil.which("gh"):
        try:
            r = subprocess.run(
                ["gh", "repo", "view", slug, "--json", "visibility,isPrivate,nameWithOwner"],
                capture_output=True, text=True, timeout=20,
            )
            if r.returncode == 0:
                try:
                    data = json.loads(r.stdout)
                except json.JSONDecodeError:
                    data = {}
                if data.get("isPrivate") or (data.get("visibility") or "").upper() == "PRIVATE":
                    return {"status": "private", "via": "gh", "slug": slug,
                            "detail": "repo exists but is PRIVATE — public users cannot install from it"}
                return {"status": "reachable", "via": "gh", "slug": slug,
                        "visibility": data.get("visibility", "PUBLIC")}
            err = (r.stderr or "").strip()
            # A resolve failure = nonexistent OR private-without-access. From an
            # installer's view both are broken-on-arrival, so classify as not_found
            # with a note; an auth/rate-limit/transient error is unverified instead.
            # WHY substring-matching gh's stderr is acceptable here (not a fragile
            # verdict): this only refines the MESSAGE/label — BOTH arms produce a
            # non-blocking outcome (not_found → exit 1, a dismissable warning the
            # ship survives; unverified → exit 0 degrade). So if gh rewords its
            # error or runs under a non-English locale, the worst case is a
            # mislabelled *warning*, never a wrong ship decision. The whole check is
            # advisory (install_check is "warning, not a hard block"), so a robust-
            # but-heavier gh-api/HTTP-status classifier would buy no ship-safety.
            low = err.lower()
            if "could not resolve" in low or "not found" in low or "404" in low:
                return {"status": "not_found", "via": "gh", "slug": slug,
                        "detail": f"gh could not resolve {slug} (nonexistent or private-no-access): {err[:120]}"}
            return {"status": "unverified", "via": "gh", "slug": slug,
                    "detail": f"gh exit {r.returncode}: {err[:120]}"}
        except (subprocess.TimeoutExpired, OSError) as e:
            return {"status": "unverified", "via": "gh", "slug": slug, "detail": f"gh error: {e}"}
    # Fallback: HTTP HEAD. 200 = reachable (public); 404 = not found. Weaker than
    # gh — a private repo also 404s, and some proxies rewrite status — so treat a
    # non-404 as a reachability HINT, not a confirmation.
    repo_url = f"https://github.com/{org}/{name}"
    try:
        req = urllib.request.Request(repo_url, method="HEAD", headers={"User-Agent": "install_check"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            code = resp.status
        if code == 404:
            return {"status": "not_found", "via": "http", "slug": slug, "code": code,
                    "detail": f"HTTP 404 for {repo_url}"}
        return {"status": "unverified", "via": "http", "slug": slug, "code": code,
                "detail": "HTTP reachability only — a 200/3xx does not confirm the repo is public/installable"}
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {"status": "not_found", "via": "http", "slug": slug, "code": 404,
                    "detail": f"HTTP 404 for {repo_url}"}
        return {"status": "unverified", "via": "http", "slug": slug, "code": e.code,
                "detail": f"HTTP {e.code} (not a definitive verdict)"}
    except Exception as e:
        return {"status": "unverified", "via": "http", "slug": slug,
                "detail": f"network unavailable: {str(e)[:100]}"}


def check_catalog(catalog: Path, org: str, name: str, marketplace_name: str | None) -> dict:
    """Look for a catalog entry matching the repo URL (or --marketplace-name).
    Returns status present | absent | unchecked (catalog missing/unreadable)."""
    try:
        data = json.loads(catalog.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"status": "unchecked", "detail": f"catalog not found at {catalog}"}
    except OSError as e:
        return {"status": "unchecked", "detail": f"catalog unreadable: {e}"}
    except json.JSONDecodeError as e:
        return {"status": "unchecked", "detail": f"catalog is not valid JSON: {e}"}

    plugins = data.get("plugins", [])
    if not isinstance(plugins, list):
        return {"status": "unchecked", "detail": "catalog has no plugins[] array"}

    slug_l = f"{org}/{name}".lower()
    for e in plugins:
        if not isinstance(e, dict):
            continue
        # `e.get("name") or ""` (not `e.get("name", "")`) so a catalog entry with an
        # explicit "name": null does not crash `.lower()` with AttributeError.
        if marketplace_name and ((e.get("name") or "").lower() == marketplace_name.lower()):
            return {"status": "present", "matched_on": "name", "entry": e.get("name")}
        src = e.get("source", {})
        url = (src.get("url", "") if isinstance(src, dict) else "") or ""
        m = _URL_RE.search(url)
        if m and f"{m.group(1)}/{m.group(2)}".lower() == slug_l:
            return {"status": "present", "matched_on": "source.url", "entry": e.get("name")}
    target = marketplace_name or slug_l
    return {"status": "absent", "detail": f"no catalog entry matching {target}"}


def main() -> int:
    ap = argparse.ArgumentParser(description="skill-publisher install-doc executability check (Step 6)")
    ap.add_argument("--repo", default=None, help="org/repo (e.g. anthropics/skill-foo)")
    ap.add_argument("--source-url", default=None, help="GitHub URL to parse org/repo from")
    ap.add_argument("--marketplace-name", default=None,
                    help="plugin name to match in the catalog (marketplace installs)")
    ap.add_argument("--catalog", default=None,
                    help=f"marketplace catalog JSON (default: {DEFAULT_CATALOG}); "
                         "passing this (even the default path) forces the catalog check")
    ap.add_argument("--json", dest="json_out", action="store_true", help="emit JSON")
    args = ap.parse_args()

    if not args.repo and not args.source_url:
        print("ERROR: pass --repo <org/repo> or --source-url <github-url>", file=sys.stderr)
        return 2
    parsed = parse_repo(args.repo, args.source_url)
    if not parsed:
        print(f"ERROR: could not parse org/repo from {args.repo or args.source_url!r}", file=sys.stderr)
        return 2
    org, name = parsed

    repo = check_repo(org, name)
    result = {"repo": repo}
    # Run the catalog check when this is a marketplace install (a name was given) or
    # `--catalog` was explicitly passed. Gate on whether the FLAG was set (default
    # None), NOT on a string-compare against the default path — passing the default
    # path explicitly is a legitimate request and must not silently skip the check.
    run_catalog = bool(args.marketplace_name) or args.catalog is not None
    catalog = None
    if run_catalog:
        catalog_path = Path(args.catalog).expanduser() if args.catalog else DEFAULT_CATALOG
        catalog = check_catalog(catalog_path, org, name, args.marketplace_name)
        result["catalog"] = catalog

    # Exit: 1 only on a CONFIRMED problem; unverified/unchecked degrade to 0.
    problem = repo["status"] in ("not_found", "private") or (
        catalog is not None and catalog["status"] == "absent")
    rc = 1 if problem else 0

    if args.json_out:
        print(json.dumps(result, indent=2))
    else:
        print(f"Install check: {org}/{name}")
        print(f"  repo     : {repo['status']}" + (f" — {repo['detail']}" if repo.get("detail") else ""))
        if catalog is not None:
            print(f"  catalog  : {catalog['status']}" + (f" — {catalog['detail']}" if catalog.get("detail") else ""))
        if rc == 0 and repo["status"] == "unverified":
            print("  (unverified — could not confirm; not a ship-blocker, verify the install command manually)")
    return rc


if __name__ == "__main__":
    sys.exit(main())
