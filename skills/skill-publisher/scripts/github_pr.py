#!/usr/bin/env python3
"""Open a GitHub PR for a shipped CCVW skill.

Pure-stdlib (subprocess + argparse + json). Wraps git + the `gh` CLI to:
  1. clone/worktree the upstream repo into a temp dir (never touch the live skill's git)
  2. branch ship/<name>-v<version>
  3. copy the polished skill into the repo at the right path
  4. commit + push
  5. gh pr create with a structured body
  6. tag the ship commit <name>-v<version> + push it (best-effort, idempotent)

Safety: never pushes to a default branch; always confirms before push (the
orchestrator passes --confirmed only after showing the user the diff). --dry-run
does everything except push + PR-create.

Usage:
    python3 github_pr.py <skill-path> --upstream <repo-url> --repo-path <path-in-repo> \
        --version <new-version> --body-file <pr-body.md> [--dry-run] [--confirmed]

This script intentionally does the mechanical git/gh steps; the orchestrator
(SKILL.md Step 9) owns the decision-making (which upstream, confirmation, etc.).
"""

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path


def run(cmd, cwd=None, check=True):
    """Run a command, return (returncode, stdout, stderr)."""
    try:
        result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    except FileNotFoundError:
        # git / gh not installed or not on PATH — surface a clean JSON error
        # rather than an uncaught traceback from the first run() call.
        print(json.dumps({"error": f"required tool not found on PATH: {cmd[0]}"}), file=sys.stderr)
        sys.exit(6)
    if check and result.returncode != 0:
        raise RuntimeError(f"command failed: {' '.join(cmd)}\nstderr: {result.stderr}")
    return result.returncode, result.stdout, result.stderr


def main():
    parser = argparse.ArgumentParser(description="Open a GitHub PR for a shipped skill")
    parser.add_argument("skill_path", help="Path to the polished skill directory")
    parser.add_argument("--upstream", required=True, help="Upstream repo URL (from HISTORY.md source)")
    parser.add_argument("--repo-path", required=True, help="Path within the repo where the skill lives (e.g. plugins/<name>)")
    parser.add_argument("--version", required=True, help="New version (for the branch name + PR title)")
    parser.add_argument("--body-file", required=True, help="Path to the PR body markdown (from assets/pr-template.md, filled)")
    parser.add_argument("--dry-run", action="store_true", help="Do everything except push + PR-create")
    parser.add_argument("--confirmed", action="store_true", help="User confirmed the push (orchestrator sets this after showing the diff)")
    args = parser.parse_args()

    skill_path = Path(args.skill_path).expanduser().resolve()
    name = skill_path.name
    branch = f"ship/{name}-v{args.version}"

    # gh auth check
    rc, _, err = run(["gh", "auth", "status"], check=False)
    if rc != 0:
        print(json.dumps({"error": "gh not authenticated. Run `gh auth login` first.", "stderr": err}), file=sys.stderr)
        sys.exit(1)

    with tempfile.TemporaryDirectory(prefix="skill-publisher-pr-") as tmp:
        tmp_path = Path(tmp)
        clone_dir = tmp_path / "repo"

        # Clone the upstream (shallow)
        try:
            run(["git", "clone", "--depth", "1", args.upstream, str(clone_dir)])
        except RuntimeError as e:
            print(json.dumps({"error": f"clone failed: {e}"}), file=sys.stderr)
            sys.exit(2)

        # Branch off default
        try:
            run(["git", "checkout", "-b", branch], cwd=clone_dir)
        except RuntimeError as e:
            print(json.dumps({"error": f"checkout failed: {e}"}), file=sys.stderr)
            sys.exit(2)

        # Copy the polished skill into the repo at repo-path
        dest = clone_dir / args.repo_path
        dest.mkdir(parents=True, exist_ok=True)
        # Copy the skill tree into the repo, excluding the same artifacts
        # package_skill.py strips (keep in sync with its EXCLUDE_* sets): *.bak*,
        # *.orig, hidden files, *-workspace/, evals/iteration-*/. (The ship ledger
        # lives outside the skill tree at ~/.claude/skill-publisher-ledger/, so it is
        # never under skill_path and needs no exclusion here.)
        # Replicates package_skill.py's should_exclude() inline to keep this script
        # standalone. If packaging rules change, update both. Prefer importing from
        # a shared module if one is ever extracted.
        import shutil
        exclude_name = (re.compile(r"\.bak"), re.compile(r"\.orig$"), re.compile(r"^\."))
        exclude_path = ("-workspace/", "/evals/iteration-")
        for f in sorted(skill_path.rglob("*")):
            if not f.is_file():
                continue
            rel = f.relative_to(skill_path)
            if any(p.search(rel.name) for p in exclude_name) or any(s in str(rel) for s in exclude_path):
                continue
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, target)

        try:
            run(["git", "add", "-A"], cwd=clone_dir)
            commit_msg = f"Ship {name} v{args.version}"
            run(["git", "commit", "-m", commit_msg], cwd=clone_dir)
        except RuntimeError as e:
            print(json.dumps({"error": f"commit failed: {e}"}), file=sys.stderr)
            sys.exit(2)

        if args.dry_run or not args.confirmed:
            rc, diff, _ = run(["git", "show", "--stat", "HEAD"], cwd=clone_dir, check=False)
            print(json.dumps({
                "dry_run": True,
                "branch": branch,
                "upstream": args.upstream,
                "repo_path": args.repo_path,
                "commit_message": commit_msg,
                "diff_stat": diff,
                "note": "Re-run with --confirmed to push + open the PR." if not args.dry_run else "Dry run complete. Re-run with --confirmed and WITHOUT --dry-run to push + open the PR.",
            }, indent=2))
            sys.exit(0)

        # Push + PR
        try:
            run(["git", "push", "-u", "origin", branch], cwd=clone_dir)
        except RuntimeError as e:
            print(json.dumps({"error": f"push failed: {e}"}), file=sys.stderr)
            sys.exit(3)

        try:
            body = Path(args.body_file).read_text()
        except OSError as e:
            print(json.dumps({"error": f"body-file unreadable: {args.body_file} ({e})"}), file=sys.stderr)
            sys.exit(5)
        rc, pr_out, pr_err = run(
            ["gh", "pr", "create", "--title", f"Ship {name} v{args.version}",
             "--body", body, "--head", branch],
            cwd=clone_dir, check=False,
        )
        if rc != 0:
            print(json.dumps({"error": f"gh pr create failed: {pr_err}"}), file=sys.stderr)
            sys.exit(4)

        # gh prints the PR URL; isolate the URL line (gh may also print advisory lines).
        url_lines = [ln.strip() for ln in pr_out.splitlines() if re.match(r"https?://", ln.strip())]
        pr_url = url_lines[-1] if url_lines else pr_out.strip()
        if not re.match(r"https?://", pr_url):
            print(json.dumps({"error": f"gh pr create returned no URL", "stdout": pr_out}), file=sys.stderr)
            sys.exit(4)

        # Tag the ship commit so the NEXT ship has a <last-ship-tag> to diff from
        # (changelog-format.md's `git log <last-ship-tag>..HEAD`). Best-effort: the PR
        # already succeeded, so a tag hiccup must not flip the overall result — it is
        # reported via `tag_warning`, never an exit code. Idempotent: skip if the tag
        # already exists (the exit-5 recovery re-run must not choke). The tag points at
        # the ship commit; valid for merge-commit upstreams (the commit is preserved on
        # the default branch) — see github-pr-workflow.md's squash/rebase caveat.
        tag = f"{name}-v{args.version}"
        result = {"pr_url": pr_url, "branch": branch, "version": args.version, "tag": tag}
        rc, _, _ = run(["git", "rev-parse", "-q", "--verify", f"refs/tags/{tag}"], cwd=clone_dir, check=False)
        if rc == 0:
            result["tag_warning"] = f"tag {tag} already exists; left as-is"
        else:
            rc, _, terr = run(["git", "tag", "-a", tag, "-m", commit_msg, "HEAD"], cwd=clone_dir, check=False)
            if rc != 0:
                result["tag_warning"] = f"tag create failed: {terr.strip()}"
            else:
                rc, _, perr = run(["git", "push", "origin", f"refs/tags/{tag}"], cwd=clone_dir, check=False)
                if rc != 0:
                    result["tag_warning"] = f"tag push failed: {perr.strip()}"
        # executor: carry pr_url into Step 10's verify_ship.py --pr-url; the artifact
        # path captured from package_skill.py in Step 8 is passed as --artifact (not via this script).
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
