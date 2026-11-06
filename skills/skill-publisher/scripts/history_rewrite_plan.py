#!/usr/bin/env python3
"""PRINT (never run) a plan to remove findings from a repo's public git history.

Input: the JSON written by history_scan.py. Output: the exact findings list and the commands, in order:
  1. mirror backup:   git clone --mirror <repo> <backup>.git   (and a copy of any unpushed local commits)
  2. rewrite:         git filter-repo --replace-text <rules> --mailmap <map> --replace-message <rules>  (on a fresh mirror)
  3. verify:          history_scan.py on the rewritten mirror must exit 0
  4. force-push:      git push --force-with-lease --mirror <repo>   (only after the user's typed yes for THIS list)
This script writes the rule files next to the plan (to --out-dir) but runs no git command. Rewriting public
history changes every later commit id; it conflicts with a merge-never-rebase rule, so state that when asking.

Usage: history_rewrite_plan.py <report.json> --out-dir DIR [--repo-url URL] [--replacement "the user"]
"""
import argparse
import json
import re
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("report")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--repo-url")
    ap.add_argument("--replacement", default="the user")
    a = ap.parse_args()
    rep = json.loads(Path(a.report).read_text(encoding="utf-8"))
    repo = a.repo_url or rep.get("repo", "<repo-url>")
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rules, mailmap, kinds = [], [], {}
    for f in rep.get("findings", []):
        kinds.setdefault(f["kind"], []).append(f)
        if f["kind"] == "author-identity":
            continue  # handled by the mailmap below
        if f["kind"] in ("profile-term", "home-path", "email", "module-code", "module-assessment", "profile-pattern"):
            rules.append(f"literal:{f['match']}==>{a.replacement}")
        elif f["kind"] == "gendered-pronoun":
            rules.append(f"regex:(?i)\\b{re.escape(f['match'])}\\b==>they")
    for m in rep.get("message_findings", []):
        rules.append(f"literal:{m['match']}==>{a.replacement}")
    for au in rep.get("authors", []):
        if au["email"] and "noreply" not in au["email"] and any((f["kind"] == "email" and f["match"] == au["email"]) or (f["kind"] == "author-identity" and f["match"].endswith("<" + au["email"] + ">")) for f in rep.get("findings", [])):
            mailmap.append(f"{au['name']} <noreply@users.noreply.github.com> <{au['email']}>")
    rules = list(dict.fromkeys(rules))
    (out / "replace-text.txt").write_text("\n".join(rules) + "\n", encoding="utf-8")
    (out / "mailmap.txt").write_text("\n".join(mailmap) + "\n", encoding="utf-8")
    plan = {
        "findings_by_kind": {k: len(v) for k, v in kinds.items()},
        "message_findings": len(rep.get("message_findings", [])),
        "needs_the_users_typed_yes_for_this_exact_list": True,
        "steps": [
            f"git clone --mirror {repo} backup-before-rewrite.git   # keep this; it is the way back",
            "# keep any UNPUSHED local commits safe first: git -C <local checkout> bundle create ../unpushed.bundle --all",
            f"git clone --mirror {repo} rewrite.git && cd rewrite.git",
            f"git filter-repo --replace-text {out/'replace-text.txt'} --replace-message {out/'replace-text.txt'}" + (f" --mailmap {out/'mailmap.txt'}" if mailmap else ""),
            f"python3 history_scan.py <path to rewrite.git> --profile <profile>   # must exit 0",
            f"git push --force-with-lease --mirror {repo}   # ONLY after the typed yes for this list",
        ],
        "warnings": ["Rewrites every commit id after the first changed commit; clones elsewhere must be re-cloned.",
                     "Conflicts with a merge-never-rebase/reset rule: say so when asking.",
                     "Nothing was run. Files written: replace-text.txt, mailmap.txt."],
    }
    print(json.dumps(plan, indent=2))


if __name__ == "__main__":
    main()
