#!/usr/bin/env python3
"""READ-ONLY scan of a repository's FULL git history for personal data.

Checks, across every commit on every branch and tag (author and committer emails listed in the profile key
`private_emails` are reported as `author-identity` findings):
  - added file lines (home paths, emails, profile terms/patterns, gendered pronouns in .md files)
  - commit messages
  - author and committer identities (name + email), listed with commit counts
Nothing is modified: the repo is cloned as a bare mirror into --work-dir (default: system temp) and
the clone is removed at the end, or an existing local path is only read.

Usage: history_scan.py <repo-url-or-path> [--profile FILE] [--work-dir DIR] [--max-findings N]
Output JSON: {"commits": N, "authors": [...], "findings": [{kind, match, file, first_commit, count}],
              "message_findings": [...], "clean": bool}
Exit 0 clean, 1 findings, 2 usage/clone error.

Rewriting history is NOT done here: a rewrite plan (mirror backup, git filter-repo, force-push) is a
separate step that needs the user's typed yes for the exact findings list.
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from collections import OrderedDict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import personal_data_scan as pds  # noqa: E402


def git(args, cwd=None):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip()[:300])
    return r.stdout


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("repo")
    ap.add_argument("--profile")
    ap.add_argument("--work-dir")
    ap.add_argument("--max-findings", type=int, default=200)
    ap.add_argument("--exclude-pull-refs", action="store_true",
                    help="scan branches and tags only. GitHub keeps old commits reachable from refs/pull/* after a rewrite and a push cannot change them; the report then counts them under `pull_refs_commits` (fixing those needs GitHub support or a recreated repository)")
    a = ap.parse_args()
    terms = pds.profile_terms(a.profile)
    patterns = pds.profile_patterns(a.profile)
    work = Path(a.work_dir).expanduser() if a.work_dir else Path(tempfile.gettempdir())
    work.mkdir(parents=True, exist_ok=True)
    tmp = None
    try:
        if Path(a.repo).expanduser().is_dir():
            repo = Path(a.repo).expanduser()
        else:
            tmp = Path(tempfile.mkdtemp(prefix="skill-publisher-history-", dir=str(work)))
            git(["clone", "--mirror", a.repo, str(tmp / "mirror.git")])
            repo = tmp / "mirror.git"
        sep = "\x1e"
        revs = ["--branches", "--tags"] if a.exclude_pull_refs else ["--all"]
        meta = git(["log", *revs, f"--format=%H\x1f%an\x1f%ae\x1f%cn\x1f%ce\x1f%B{sep}"], cwd=repo)
        authors, msg_findings, commits = OrderedDict(), [], 0
        for rec in meta.split(sep):
            rec = rec.strip("\n")
            if not rec:
                continue
            parts = rec.split("\x1f", 5)
            if len(parts) < 6:
                continue
            h, an, ae, cn, ce, body = parts
            commits += 1
            for who in {(an, ae), (cn, ce)}:
                authors[who] = authors.get(who, 0) + 1
            for f in pds.scan_text(body, "<commit message>", terms, True, patterns):
                msg_findings.append({**f, "commit": h[:10]})
        patch = git(["log", *revs, "-p", "-U0", "--no-color", f"--format=\x1fCOMMIT %H"], cwd=repo)
        found = OrderedDict()
        cur, path = None, None
        for line in patch.split("\n"):
            if line.startswith("\x1fCOMMIT "):
                cur = line.split()[1][:10]
                continue
            if line.startswith("+++ "):
                path = line[6:] if line.startswith("+++ b/") else None
                continue
            if line.startswith("+") and not line.startswith("+++") and path:
                for f in pds.scan_text(line[1:], path, terms, None, patterns):
                    k = (f["kind"], f["match"], path)
                    if k in found:
                        found[k]["count"] += 1
                    else:
                        found[k] = {"kind": f["kind"], "match": f["match"], "file": path, "first_commit": cur, "count": 1}
        private = [e.lower() for e in pds.profile_values(a.profile, "private_emails")]
        id_findings = [{"kind": "author-identity", "match": f"{n} <{e}>", "file": "<commit author or committer>",
                        "first_commit": None, "count": c} for (n, e), c in authors.items() if e.lower() in private]
        allow = pds.allowlist(a.profile)
        findings = [f for f in found.values() if not pds.allowed(f, allow)]
        findings += id_findings
        msg_findings = [f for f in msg_findings if not pds.allowed(f, allow)]
        ident = [{"name": n, "email": e, "commits": c} for (n, e), c in authors.items()]
        refs = git(["for-each-ref", "--format=%(refname) %(objectname)"], cwd=repo)
        import hashlib
        out = {"repo": a.repo, "refs_digest": hashlib.sha256(refs.encode()).hexdigest()[:16], "commits": commits, "scope": "branches+tags" if a.exclude_pull_refs else "all refs", "pull_refs_commits": (len(git(["rev-list", "--all"], cwd=repo).split()) - len(git(["rev-list", "--branches", "--tags"], cwd=repo).split())) if a.exclude_pull_refs else 0, "authors": ident, "findings": findings[:a.max_findings],
               "findings_total": len(findings), "message_findings": msg_findings[:a.max_findings],
               "clean": not findings and not msg_findings}
        print(json.dumps(out, indent=2))
        sys.exit(0 if out["clean"] else 1)
    except RuntimeError as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(2)
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
