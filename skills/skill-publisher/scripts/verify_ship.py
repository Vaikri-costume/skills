#!/usr/bin/env python3
"""Post-ship verification for skill-publisher Step 10.

Before reporting a ship as done, confirm it actually landed — that a prior step
didn't silently half-complete. Deterministic checks:
  1. version_present   — the new <version> appears in HISTORY.md frontmatter
  2. changelog_present — a changelog heading for <version> exists in HISTORY.md body
  3. artifact_present  — the package artifact exists at its path (claude-users/model-agnostic)
  3b. artifact_digest  — with --expected-digest, re-hash the artifact and confirm it
                         is byte-for-byte the one packaged at Step 8 (n/a if omitted)
  4. pr_resolves       — the PR URL resolves (gh pr view / HTTP 200)
  5. changelog quality — the new version's entry uses valid Keep-a-Changelog categories
                         (Added/Changed/Deprecated/Removed/Fixed/Security) and the SemVer
                         bump is a clean single-level step consistent with the changes
                         (Removed→major, Added→≥minor). Advisory by default; REQUIRED
                         under --strict-changelog. Bump check needs the parent version
                         (--parent-version, else SKILL.md metadata.parent-version).

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

# Streaming SHA-256 lives in one place (hashutil), shared with package_skill.py.
# Frontmatter parsing lives in frontmatter_util (BOM/CRLF/trailing-newline tolerant),
# shared with readiness_report.py + package_skill.py so the scan can't drift.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from hashutil import sha256_file as _sha256_file
from frontmatter_util import block as _fm_block, field as _fm_field

# Version headings are written at `##` (keepachangelog `## [1.2.0]`) or `###`
# (`### 1.2.0 — date`); category headings are `####`. So a VERSION heading is 2–3
# hashes — used consistently by the presence check, the entry-start match, and the
# entry-end terminator below, so none can drift out of step (a `#{1,4}`/`#{2,4}`
# mismatch previously let an entry's presence pass while its extraction returned
# None, or a `####`-level heading's block run past its own version).
_VER_HEADING = r"#{2,3}"


def check_history(history_text: str | None, version: str) -> tuple[bool, bool]:
    """(version_present_in_frontmatter, changelog_heading_present). `history_text`
    is the HISTORY.md contents, or None when the file is absent (read once by the
    caller — Step 10 reads HISTORY.md a single time and threads the text through
    every check, rather than each re-reading from disk)."""
    if history_text is None:
        return False, False
    # block() tolerates a leading BOM + CRLF/CR; a hand-rolled `startswith("---\n")`
    # scan (the prior form) read version_present as False on a BOM/CRLF HISTORY.md
    # and falsely failed the ship — the exact drift frontmatter_util exists to end.
    fm = _fm_block(history_text)
    vesc = re.escape(version)
    version_present = bool(fm and re.search(rf"^version\s*:\s*['\"]?{vesc}['\"]?\s*$", fm, re.MULTILINE))
    # changelog heading like '### 1.2.0', '## 1.2.0 — date', '### v1.2.0',
    # '### [1.2.0]' (keepachangelog), or '### 1.2.0 — date (shipped)'. \[? allows a
    # leading '['. \b after the version is a valid boundary (next char non-word);
    # works for numeric-ending versions and '1.0.0-alpha'. Searching the whole text
    # is safe — a version heading never appears inside the frontmatter block.
    changelog_present = bool(re.search(rf"^{_VER_HEADING}\s*\[?v?{vesc}\b", history_text, re.MULTILINE))
    return version_present, changelog_present


_KAC_CATEGORIES = {"Added", "Changed", "Deprecated", "Removed", "Fixed", "Security"}


def _changelog_entry(history_text: str | None, version: str) -> str | None:
    """Return the changelog entry block for `version` (its heading line through just
    before the next `##`/`###` version heading), or None if not found. `history_text`
    is the HISTORY.md contents (read once by the caller), or None when absent."""
    if history_text is None:
        return None
    text = history_text.replace("\r\n", "\n").replace("\r", "\n")
    vesc = re.escape(version)
    # Start and end both keyed on the same 2–3-hash version-heading level, so the
    # entry always closes at the next version heading (never swallows a following
    # version, and a `####` category heading inside the entry is never a boundary).
    m = re.search(rf"^{_VER_HEADING}\s*\[?v?{vesc}\b.*$", text, re.MULTILINE)
    if not m:
        return None
    start = m.start()
    nxt = re.search(rf"^{_VER_HEADING}\s+\S", text[m.end():], re.MULTILINE)
    end = m.end() + nxt.start() if nxt else len(text)
    return text[start:end]


def check_changelog_quality(history_text: str | None, version: str, parent: str | None) -> dict:
    """Keep-a-Changelog category validity + SemVer bump consistency for the entry.
    Returns {entry_found, categories_ok, bump_consistent, bump, detail[]}.
    `history_text` is the HISTORY.md contents (read once by the caller), or None."""
    out = {"entry_found": False, "categories_ok": True, "bump_consistent": True,
           "bump": None, "detail": []}
    entry = _changelog_entry(history_text, version)
    if entry is None:
        out["detail"].append(f"no changelog entry found for {version}")
        return out
    out["entry_found"] = True

    # Category headings must all be Keep-a-Changelog categories; the entry must
    # carry at least one change bullet.
    headings = re.findall(r"^#{4}\s*(.+?)\s*$", entry, re.MULTILINE)
    bad = [h for h in headings if h not in _KAC_CATEGORIES]
    if bad:
        out["categories_ok"] = False
        out["detail"].append(f"unknown changelog categories: {', '.join(bad)} "
                             f"(allowed: {', '.join(sorted(_KAC_CATEGORIES))})")
    if not re.search(r"^\s*[-*]\s+\S", entry, re.MULTILINE):
        out["categories_ok"] = False
        out["detail"].append("changelog entry has no change bullets")

    # Bump consistency: a clean single-level SemVer step from parent, and at least as
    # high as the entry's categories imply (Removed → major; Added → ≥ minor).
    pv = _parse_semver(parent) if parent else None
    nv = _parse_semver(version)
    if pv is None or nv is None:
        out["detail"].append("bump check skipped (pre-versioned / unparseable version)")
        return out
    level = _bump_level(pv, nv)
    out["bump"] = level
    if level is None:
        out["bump_consistent"] = False
        out["detail"].append(f"version {version} is not a clean single-level bump from {parent}")
    else:
        seen = set(headings)
        needs = "major" if "Removed" in seen else ("minor" if "Added" in seen else "patch")
        rank = {"patch": 0, "minor": 1, "major": 2}
        if rank[level] < rank[needs]:
            out["bump_consistent"] = False
            out["detail"].append(
                f"bump {level} too low for the changes: a '{needs}' bump is implied "
                f"(entry has {'Removed' if needs=='major' else 'Added'})")
    return out


def _parse_semver(s: str | None):
    if not s:
        return None
    m = re.match(r"^v?(\d+)\.(\d+)\.(\d+)", s.strip())
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def _bump_level(pv: tuple, nv: tuple) -> str | None:
    """'major'/'minor'/'patch' if nv is a clean single-level increment of pv, else None."""
    if nv == (pv[0] + 1, 0, 0):
        return "major"
    if nv == (pv[0], pv[1] + 1, 0):
        return "minor"
    if nv == (pv[0], pv[1], pv[2] + 1):
        return "patch"
    return None


def check_pr(pr_url: str) -> dict:
    """Try gh first, then a plain HTTP HEAD; degrade to 'unverified' if neither works.

    WHY this only ever returns 'resolves' or 'unverified', and 'unverified' never
    fails the ship: this is POST-ship verification — by the time it runs the PR was
    already created (Step 9 returned its URL). A network/tooling gap here must not
    false-fail a ship that actually landed, so any non-confirmation degrades to
    'unverified' (a stderr NOTE, not a required failure). The one genuinely broken
    state — a branch pushed but the PR never opened (recovery-protocol.md Rule D) —
    is detected and resolved at RECOVERY time from the in-flight marker, not here:
    post-ship verify has no marker to read and must not re-litigate sequencing it
    cannot see. So 'unverified' is deliberate, not a missing check."""
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
    ap.add_argument("--expected-digest", default=None,
                    help="expected archive SHA-256 (from package_skill.py's archive_sha256) — "
                         "re-hashes the artifact and fails the ship on a mismatch")
    ap.add_argument("--pr-url", default=None, help="PR URL (omit if no PR opened)")
    ap.add_argument("--parent-version", default=None,
                    help="the version being superseded (for the bump-consistency check); "
                         "falls back to SKILL.md metadata.parent-version if omitted")
    ap.add_argument("--strict-changelog", action="store_true",
                    help="make the Keep-a-Changelog category + SemVer bump-consistency checks "
                         "REQUIRED (fail the ship on a violation); advisory otherwise")
    args = ap.parse_args()

    # Enforce the integrity check at the layer that holds both inputs, not in
    # orchestrator prose: a packaged artifact must always be digest-checked. The
    # only path with --artifact but no digest would be a bug (the sole digest-free
    # ship is personal tier, which passes no --artifact at all).
    if args.artifact and not args.expected_digest:
        ap.error("--expected-digest is required whenever --artifact is given "
                 "(re-run Step 8 to capture archive_sha256)")

    root = Path(args.skill_path).expanduser()
    # Treat the arg as the skill root unless it points AT a SKILL.md file (then use
    # its parent). A non-existent/odd path stays as-is — the HISTORY checks below
    # then fail loudly rather than silently reading a sibling directory's HISTORY.
    skill_root = root.parent if root.name == "SKILL.md" else root
    history = skill_root / "HISTORY.md"

    # Read HISTORY.md ONCE and thread the text through every check below, rather than
    # each of check_history / _changelog_entry / check_changelog_quality re-reading
    # it from disk (three reads of one file per run).
    try:
        history_text = history.read_text(encoding="utf-8") if history.is_file() else None
    except OSError:
        history_text = None

    version_present, changelog_present = check_history(history_text, args.version)

    if args.artifact:
        ap_path = Path(args.artifact).expanduser()
        if ap_path.is_file():
            artifact = {"status": "present", "path": str(ap_path)}
            # Re-hash the artifact and confirm it is byte-for-byte the one packaged
            # at Step 8 — catches corruption, truncation, or a swapped artifact
            # between packaging and verification.
            if args.expected_digest:
                actual = _sha256_file(ap_path)
                # Normalize the expected value: command substitution / copy-paste can
                # introduce trailing whitespace or uppercase hex; _sha256_file returns
                # lowercase, no whitespace. Compare on the normalized form so an intact
                # artifact is not flagged MISMATCH over formatting.
                expected = args.expected_digest.strip().lower()
                if actual == expected:
                    artifact["digest"] = "verified"
                    artifact["sha256"] = actual
                else:
                    artifact["digest"] = "MISMATCH"
                    artifact["expected"] = expected
                    artifact["actual"] = actual
            else:
                artifact["digest"] = "n/a"
        else:
            artifact = {"status": "MISSING", "path": str(ap_path)}
    else:
        artifact = {"status": "n/a", "detail": "no artifact (personal tier or not packaged)"}

    pr = check_pr(args.pr_url) if args.pr_url else {"status": "n/a", "detail": "no PR opened"}

    # Changelog quality (Keep-a-Changelog categories + SemVer bump consistency).
    parent = args.parent_version
    if parent is None:
        # Fall back to SKILL.md metadata.parent-version (field() is indentation-
        # tolerant, so the flat scalar match reaches the nested `metadata:` field).
        try:
            sm = skill_root / "SKILL.md"
            parent = _fm_field(_fm_block(sm.read_text(encoding="utf-8")), "parent-version") if sm.is_file() else None
        except OSError:
            parent = None
    changelog = check_changelog_quality(history_text, args.version, parent)

    # Required = the local deterministic checks + any artifact that was claimed.
    # 'unverified' (PR network) and 'n/a' never fail the ship.
    required_failures = []
    if not version_present:
        required_failures.append(f"version {args.version} not in HISTORY.md frontmatter")
    if not changelog_present:
        required_failures.append(f"no changelog heading for {args.version} in HISTORY.md")
    if artifact["status"] == "MISSING":
        required_failures.append(f"package artifact missing at {artifact['path']}")
    if artifact.get("digest") == "MISMATCH":
        required_failures.append(
            f"artifact digest mismatch (expected {artifact['expected'][:12]}…, "
            f"got {artifact['actual'][:12]}…) — the artifact is not the one packaged")
    # Changelog quality failures are REQUIRED only under --strict-changelog; advisory
    # otherwise (surfaced in the JSON + a stderr NOTE, but don't fail the ship).
    if args.strict_changelog and changelog["entry_found"]:
        if not changelog["categories_ok"]:
            required_failures.append("changelog categories invalid: " + "; ".join(changelog["detail"]))
        if not changelog["bump_consistent"]:
            required_failures.append("version bump inconsistent: " + "; ".join(changelog["detail"]))

    result = {
        "skill": str(skill_root),
        "version": args.version,
        "version_present": version_present,
        "changelog_present": changelog_present,
        "changelog": changelog,
        "artifact": artifact,
        "pr": pr,
        "required_failures": required_failures,
        "all_required_ok": not required_failures,
    }
    print(json.dumps(result, indent=2))
    if pr.get("status") == "unverified":
        print(f"NOTE: PR check unverified ({pr.get('detail','')}) — not a failure; verify the URL manually.", file=sys.stderr)
    if (not args.strict_changelog and changelog["entry_found"]
            and (not changelog["categories_ok"] or not changelog["bump_consistent"])):
        print(f"NOTE: changelog advisory ({'; '.join(changelog['detail'])}) — not a failure; "
              "re-run with --strict-changelog to enforce.", file=sys.stderr)
    return 1 if required_failures else 0


if __name__ == "__main__":
    sys.exit(main())
