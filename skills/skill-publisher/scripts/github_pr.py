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
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def run(cmd, cwd=None, check=True, timeout=300):
    """Run a command, return (returncode, stdout, stderr).

    `encoding="utf-8"` pins decoding — `text=True` alone uses the locale default,
    which raises UnicodeDecodeError on a non-UTF-8 locale when git/gh emit UTF-8
    (em-dashes appear in this repo's own commit text). `timeout` bounds every call
    so a network stall or an interactive credential prompt cannot hang the ship: a
    timeout on a check=True call raises (caught at the call site → clean JSON exit);
    on a best-effort check=False call it returns a non-zero rc so the caller's
    existing warning path handles it instead of aborting."""
    try:
        result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                                encoding="utf-8", timeout=timeout)
    except FileNotFoundError:
        # git / gh not installed or not on PATH — surface a clean JSON error
        # rather than an uncaught traceback from the first run() call.
        print(json.dumps({"error": f"required tool not found on PATH: {cmd[0]}"}), file=sys.stderr)
        sys.exit(6)
    except subprocess.TimeoutExpired:
        if check:
            raise RuntimeError(f"command timed out after {timeout}s: {' '.join(cmd)}")
        return 124, "", f"timed out after {timeout}s"
    if check and result.returncode != 0:
        raise RuntimeError(f"command failed: {' '.join(cmd)}\nstderr: {result.stderr}")
    return result.returncode, result.stdout, result.stderr


def main():
    parser = argparse.ArgumentParser(description="Open a GitHub PR for a shipped skill")
    parser.add_argument("skill_path", help="Path to the polished skill directory")
    parser.add_argument("--upstream", required=True, help="Upstream repo URL (from HISTORY.md source)")
    parser.add_argument("--repo-path", required=True, help="Path within the repo where the skill lives (e.g. plugins/<name>)")
    # Required for a full PR; NOT for --diff-only (a read-only clone for the
    # Step-7a changelog diff). Validated manually below so --diff-only can omit them.
    parser.add_argument("--version", help="New version (for the branch name + PR title); required unless --diff-only")
    parser.add_argument("--body-file", help="Path to the filled PR body markdown; required unless --diff-only")
    parser.add_argument("--diff-only", action="store_true",
                        help="Clone the upstream into a stable temp dir and emit the published skill path "
                             "for Step 7a's changelog diff — no branch, no push, no PR")
    parser.add_argument("--dry-run", action="store_true", help="Do everything except push + PR-create")
    parser.add_argument("--confirmed", action="store_true", help="User confirmed the push (orchestrator sets this after showing the diff)")
    args = parser.parse_args()

    skill_path = Path(args.skill_path).expanduser().resolve()
    name = skill_path.name

    # --diff-only: read-only clone for the Step-7a changelog diff. No gh auth (a
    # public clone needs none), no branch, no push. Clones to a STABLE named dir so
    # Step 9 can reuse it and the orchestrator can clean it up by a known path.
    if args.diff_only:
        clone_root = Path(tempfile.gettempdir()) / f"skill-publisher-diffclone-{name}"
        if clone_root.exists():
            shutil.rmtree(clone_root, ignore_errors=True)
        clone_dir = clone_root / "repo"
        try:
            run(["git", "clone", "--depth", "1", args.upstream, str(clone_dir)])
        except RuntimeError as e:
            # A failed clone can leave a partial tree under the stable named dir.
            # Remove it here rather than orphaning it until the next --diff-only run
            # (which is the only other reclaimer of this path) — the caller gets a
            # clean error and nothing is left on disk.
            shutil.rmtree(clone_root, ignore_errors=True)
            print(json.dumps({"error": f"diff-only clone failed: {e}"}), file=sys.stderr)
            sys.exit(2)
        published_path = clone_dir / args.repo_path
        if not published_path.is_dir():
            # Cloned fine, but the skill isn't published at that path yet — the
            # caller falls back to ledger-only changelog sourcing.
            print(json.dumps({
                "diff_only": True,
                "no_published_state": True,
                "clone_dir": str(clone_root),
                "published_path": str(published_path),
                "detail": f"repo-path {args.repo_path!r} not present in upstream — not yet published there",
            }, indent=2))
            sys.exit(0)
        print(json.dumps({
            "diff_only": True,
            "clone_dir": str(clone_root),
            "published_path": str(published_path),
            "note": "clone left in place for diff_published.py + Step 9 reuse; remove clone_dir when done",
        }, indent=2))
        sys.exit(0)

    if not args.version or not args.body_file:
        parser.error("--version and --body-file are required unless --diff-only is given")
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
        # Use package_skill.py's should_exclude() as the single authoritative exclusion
        # source so packaging rules and PR-copy rules stay in sync automatically.
        sys.path.insert(0, str(Path(__file__).parent))
        from package_skill import should_exclude
        for f in sorted(skill_path.rglob("*")):
            if not f.is_file():
                continue
            rel = f.relative_to(skill_path)
            if should_exclude(rel):
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
            body = Path(args.body_file).read_text(encoding="utf-8")
        except OSError as e:
            print(json.dumps({"error": f"body-file unreadable: {args.body_file} ({e})"}), file=sys.stderr)
            sys.exit(5)
        # --base is intentionally omitted: gh targets the base repo's DEFAULT branch,
        # which is the correct base for a ship PR. Passing an explicitly-detected base
        # would risk mis-targeting — the shallow clone's checked-out HEAD can differ
        # from the repo's current default if the default was changed upstream — so we
        # defer to gh's own default-branch resolution rather than re-deriving it.
        rc, pr_out, pr_err = run(
            ["gh", "pr", "create", "--title", f"Ship {name} v{args.version}",
             "--body", body, "--head", branch],
            cwd=clone_dir, check=False,
        )
        if rc != 0:
            print(json.dumps({"error": f"gh pr create failed: {pr_err}"}), file=sys.stderr)
            sys.exit(4)

        # gh prints the PR URL, but it may ALSO print advisory lines that are URLs
        # (e.g. "A new release of gh is available: https://github.com/cli/cli/...").
        # Match only a GitHub PR-shaped URL (".../pull/<n>") so an advisory line is
        # never mistaken for the PR URL and carried into verify_ship's --pr-url.
        pr_matches = re.findall(r"https?://\S+/pull/\d+", pr_out)
        pr_url = pr_matches[-1] if pr_matches else ""
        if not pr_url:
            print(json.dumps({"error": "gh pr create returned no PR URL", "stdout": pr_out}), file=sys.stderr)
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
