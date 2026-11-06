#!/usr/bin/env python3
"""Open a GitHub PR for a shipped CCVW skill.

Pure-stdlib (subprocess + argparse + json). Wraps git + the `gh` CLI to:
  1. clone/worktree the upstream repo into a temp dir (never touch the live skill's git)
  2. branch ship/<name>-v<version>
  3. copy the polished skill into the repo at the right path
  3b. register it in the repo's .claude-plugin/marketplace.json (same commit; see
      marketplace_register.py) so `claude plugins install` can actually offer it
  3c. add a row for it to the repo-root README's skill listing (same commit; see
      readme_register.py) so the repo front page does not omit it
  4. commit + push
  5. gh pr create with a structured body
  6. tag the ship commit <name>-v<version> + push it (best-effort, idempotent)

Safety: never pushes to a default branch; always confirms before push (the
orchestrator passes --confirmed only after showing the user the diff). --dry-run
does everything except push + PR-create.

Usage:
    python3 github_pr.py <skill-path> --upstream <repo-url> --repo-path <path-in-repo> \
        --version <new-version> --body-file <pr-body.md> [--dry-run] [--confirmed] \
        [--marketplace-plugin NAME | --marketplace-new-plugin NAME --marketplace-description TEXT | --no-marketplace] \
        [--readme-section HEADING --readme-description TEXT [--readme-phase TEXT] | --no-readme-row] \
        [--work-dir DIR]
    python3 github_pr.py <skill-path> --upstream <repo-url> --repo-path <path> --cleanup [--work-dir DIR]

The published folder mirrors the skill: a file present in the upstream folder but not in
the skill (or excluded by package_skill.should_exclude) is deleted in the PR commit, and
listed under `removed_files` in the dry-run and in the final result so the user sees every
deletion before confirming.

Temp clones go under --work-dir (default: $SKILL_PUBLISHER_WORK_DIR, else the system temp
dir). --cleanup removes the Step-7a diff clone from inside Python so no shell `rm` is needed.

Exit 10: the mandatory full-history scan (history_scan.py) is missing, not clean, or for another repo
(--history-report); a confirmed push needs it.

Exit codes: 1 gh not authenticated; 2 clone/checkout/commit failure; 3 push failed;
4 gh pr create failed; 5 body-file unreadable; 6 git/gh not on PATH; 7 marketplace
choice missing or invalid (the catalog exists, the skill is not listed, and no
--marketplace-* flag resolved it; dry-run reports `needs_choice` instead of failing); 8 repo-README
row choice missing or invalid (same pattern: dry-run reports `needs_row`); 9 personal data
found in the staged skill folder or PR body (dry-run lists it under `personal_data`).

This script intentionally does the mechanical git/gh steps; the orchestrator
(SKILL.md Step 9) owns the decision-making (which upstream, confirmation, etc.).
"""

import argparse
import json
import os
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


def _same_repo(a, b):
    """Compare two repo references: local paths by resolved path, URLs by text without a trailing slash or .git."""
    def norm(x):
        if not x:
            return None
        x = str(x).strip()
        p = Path(x).expanduser()
        if p.exists():
            return str(p.resolve())
        return x.rstrip("/").removesuffix(".git")
    na, nb = norm(a), norm(b)
    return na is not None and na == nb


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
    mk = parser.add_mutually_exclusive_group()
    mk.add_argument("--marketplace-plugin", metavar="NAME",
                    help="Register the skill in this EXISTING plugin's skills[] in .claude-plugin/marketplace.json")
    mk.add_argument("--marketplace-new-plugin", metavar="NAME",
                    help="Register the skill as a NEW plugin entry (requires --marketplace-description)")
    mk.add_argument("--no-marketplace", action="store_true",
                    help="Do not touch marketplace.json (explicit opt-out)")
    parser.add_argument("--marketplace-description", help="Description for --marketplace-new-plugin")
    rd = parser.add_mutually_exclusive_group()
    rd.add_argument("--readme-section", metavar="HEADING",
                    help="Add a row for the skill under this existing heading of the repo-root README "
                         "(requires --readme-description)")
    rd.add_argument("--no-readme-row", action="store_true",
                    help="Do not touch the repo-root README (explicit opt-out)")
    parser.add_argument("--readme-description", help="One-line 'what it does' for the README row")
    parser.add_argument("--readme-phase", help="Value for a 3-column table's middle (phase/role) cell; default '—'")
    parser.add_argument("--work-dir", metavar="DIR",
                        help="Directory for temp clones (default: $SKILL_PUBLISHER_WORK_DIR, else the system temp dir)")
    parser.add_argument("--cleanup", action="store_true",
                        help="Remove the Step-7a diff clone under --work-dir and exit (no network, no gh)")
    parser.add_argument("--history-report", metavar="FILE",
                        help="JSON written by history_scan.py for this upstream; REQUIRED with --confirmed and must say clean=true "
                             "(the mandatory full-history personal-data scan, SKILL.md Step 9)")
    parser.add_argument("--dry-run", action="store_true", help="Do everything except push + PR-create")
    parser.add_argument("--confirmed", action="store_true", help="User confirmed the push (orchestrator sets this after showing the diff)")
    args = parser.parse_args()

    skill_path = Path(args.skill_path).expanduser().resolve()
    name = skill_path.name
    work_dir = Path(args.work_dir or os.environ.get("SKILL_PUBLISHER_WORK_DIR") or tempfile.gettempdir()).expanduser()
    work_dir.mkdir(parents=True, exist_ok=True)
    diffclone_root = work_dir / f"skill-publisher-diffclone-{name}"

    if args.cleanup:
        existed = diffclone_root.exists()
        shutil.rmtree(diffclone_root, ignore_errors=True)
        print(json.dumps({"cleanup": True, "removed": str(diffclone_root) if existed else None}))
        sys.exit(0)

    # --diff-only: read-only clone for the Step-7a changelog diff. No gh auth (a
    # public clone needs none), no branch, no push. Clones to a STABLE named dir so the
    # orchestrator can clean it up by a known path at Step 10 (the non-diff-only PR path
    # below makes its OWN TemporaryDirectory clone — it does not reuse this one — so this
    # dir's only reclaimers are Step 10's cleanup and the next --diff-only run's rmtree).
    if args.diff_only:
        clone_root = diffclone_root
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
                "work_dir": str(work_dir),
                "no_published_state": True,
                "clone_dir": str(clone_root),
                "published_path": str(published_path),
                "detail": f"repo-path {args.repo_path!r} not present in upstream — not yet published there",
            }, indent=2))
            sys.exit(0)
        print(json.dumps({
            "diff_only": True,
            "work_dir": str(work_dir),
            "clone_dir": str(clone_root),
            "published_path": str(published_path),
            "note": "clone left in place for diff_published.py to read; the orchestrator removes it at Step 10 by its known path. The Step-9 PR flow makes its OWN clone — it does not reuse this one.",
        }, indent=2))
        sys.exit(0)

    if not args.version or not args.body_file:
        parser.error("--version and --body-file are required unless --diff-only is given")
    if args.marketplace_new_plugin and not args.marketplace_description:
        parser.error("--marketplace-new-plugin requires --marketplace-description")
    if args.readme_section and not args.readme_description:
        parser.error("--readme-section requires --readme-description")
    branch = f"ship/{name}-v{args.version}"

    # gh auth check
    rc, _, err = run(["gh", "auth", "status"], check=False)
    if rc != 0:
        print(json.dumps({"error": "gh not authenticated. Run `gh auth login` first.", "stderr": err}), file=sys.stderr)
        sys.exit(1)

    with tempfile.TemporaryDirectory(prefix="skill-publisher-pr-", dir=str(work_dir)) as tmp:
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
        kept = set()
        for f in sorted(skill_path.rglob("*")):
            if not f.is_file():
                continue
            rel = f.relative_to(skill_path)
            if should_exclude(rel):
                continue
            kept.add(rel)
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, target)

        # Mirror deletions: anything in the published folder that the skill no longer has.
        # Hidden/excluded names (should_exclude) are never touched, so repo-level files
        # such as a folder's own .gitkeep are left alone.
        removed_files = []
        for f in sorted(dest.rglob("*")):
            if not f.is_file():
                continue
            rel = f.relative_to(dest)
            if should_exclude(rel) or rel in kept:
                continue
            f.unlink()
            removed_files.append(rel.as_posix())
        for d in sorted((p for p in dest.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
            if not any(d.iterdir()):
                d.rmdir()

        # Marketplace registration — same commit as the skill copy. Without it the skill
        # is in the repo but `claude plugins install` cannot offer it.
        import marketplace_register as mreg
        mk_plan = mreg.plan(clone_dir, args.repo_path)
        marketplace = dict(mk_plan)
        if mk_plan["state"] == "error":
            print(json.dumps({"error": f"marketplace: {mk_plan['detail']}"}), file=sys.stderr)
            sys.exit(7)
        if mk_plan["state"] == "needs_choice":
            if args.no_marketplace:
                marketplace["state"] = "skipped"
            elif args.marketplace_plugin or args.marketplace_new_plugin:
                try:
                    marketplace = mreg.apply(clone_dir, args.repo_path,
                                             plugin=args.marketplace_plugin,
                                             new_plugin=args.marketplace_new_plugin,
                                             description=args.marketplace_description)
                except ValueError as e:
                    print(json.dumps({"error": f"marketplace: {e}"}), file=sys.stderr)
                    sys.exit(7)
            elif not (args.dry_run or not args.confirmed):
                # A real push with the choice unresolved would publish an uninstallable skill.
                print(json.dumps({"error": "marketplace: skill is not listed in .claude-plugin/marketplace.json and no "
                                           "--marketplace-plugin / --marketplace-new-plugin / --no-marketplace was given",
                                  "existing_plugins": mk_plan["existing_plugins"]}), file=sys.stderr)
                sys.exit(7)

        # Repo-root README listing — same commit. A skill the front page never mentions
        # is invisible to anyone browsing the repo.
        import readme_register as rreg
        rd_plan = rreg.plan(clone_dir, args.repo_path)
        readme = dict(rd_plan)
        if rd_plan["state"] == "needs_row":
            if args.no_readme_row:
                readme["state"] = "skipped"
            elif args.readme_section:
                try:
                    readme = rreg.apply(clone_dir, args.repo_path, args.readme_section,
                                        args.readme_description, args.readme_phase)
                except ValueError as e:
                    print(json.dumps({"error": f"readme: {e}"}), file=sys.stderr)
                    sys.exit(8)
            elif not (args.dry_run or not args.confirmed):
                print(json.dumps({"error": "readme: skill is not linked in the repo-root README and no "
                                           "--readme-section / --no-readme-row was given",
                                  "sections": [x["heading"] for x in rd_plan["sections"]]}), file=sys.stderr)
                sys.exit(8)

        # Personal-data scan on what is about to be published: the staged skill folder and the PR
        # body (the changelog entry lives in HISTORY.md, inside the folder). A finding blocks a
        # confirmed push (exit 9) and is listed in the dry-run so the user sees it first.
        import personal_data_scan as pds
        pd_terms = pds.profile_terms(None)
        pd_patterns = pds.profile_patterns(None)
        pd_allow = pds.allowlist(None)
        personal_data = []
        for f, label in pds.iter_files(dest):
            try:
                personal_data += [x for x in pds.scan_text(f.read_text(encoding="utf-8"), label, pd_terms, None, pd_patterns) if not pds.allowed(x, pd_allow)]
            except (UnicodeDecodeError, OSError):
                continue
        try:
            personal_data += [x for x in pds.scan_text(Path(args.body_file).read_text(encoding="utf-8"), "<pr-body>", pd_terms, None, pd_patterns) if not pds.allowed(x, pd_allow)]
        except OSError:
            pass  # an unreadable body file is reported later (exit 5) on a real push
        history_status = {"state": "not provided"}
        if args.history_report:
            try:
                hr = json.loads(Path(args.history_report).read_text(encoding="utf-8"))
                history_status = {"state": "clean" if hr.get("clean") else "FINDINGS",
                                  "repo_matches": _same_repo(hr.get("repo"), args.upstream),
                                  "findings_total": hr.get("findings_total", 0) + len(hr.get("message_findings", [])),
                                  "refs_digest": hr.get("refs_digest")}
            except (OSError, ValueError) as e:
                history_status = {"state": f"unreadable: {e}"}
        if args.confirmed and not args.dry_run and not (history_status.get("state") == "clean" and history_status.get("repo_matches")):
            print(json.dumps({"error": "full-history scan must pass before a push: run history_scan.py on the upstream and pass its clean JSON with --history-report",
                              "history": history_status}), file=sys.stderr)
            sys.exit(10)
        if personal_data and not (args.dry_run or not args.confirmed):
            print(json.dumps({"error": "personal data found in the files to publish; replace each with 'the user' or a profile reference",
                              "personal_data": personal_data}), file=sys.stderr)
            sys.exit(9)

        try:
            run(["git", "add", "-A"], cwd=clone_dir)
            commit_msg = f"Ship {name} v{args.version}"
            run(["git", "commit", "-m", commit_msg], cwd=clone_dir)
        except RuntimeError as e:
            print(json.dumps({"error": f"commit failed: {e}"}), file=sys.stderr)
            sys.exit(2)

        if args.dry_run or not args.confirmed:
            rc, diff, _ = run(["git", "show", "--stat", "--format=%s", "HEAD"], cwd=clone_dir, check=False)
            _, c_name, _ = run(["git", "log", "-1", "--format=%an"], cwd=clone_dir, check=False)
            _, c_mail, _ = run(["git", "log", "-1", "--format=%ae"], cwd=clone_dir, check=False)
            print(json.dumps({
                "dry_run": True,
                "work_dir": str(work_dir),
                "branch": branch,
                "upstream": args.upstream,
                "repo_path": args.repo_path,
                "commit_message": commit_msg,
                "removed_files": removed_files,
                "personal_data": personal_data,
                "history": history_status,
                "commit_identity": {"name": c_name.strip(), "email": c_mail.strip(),
                                    "note": "The public commit and tag will carry this git identity (from git config). Past commits in the public repo are never scanned or rewritten by this script."},
                "marketplace": marketplace,
                "readme": readme,
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
        # If an open PR for this head branch already exists, reuse it instead of
        # calling `gh pr create` again — which would error on the duplicate. This
        # point is reached only after the push above succeeded; a fresh invocation
        # re-clones and commits anew, so re-running after an exit 5 normally fails
        # that push (exit 3) first and never gets here.
        rc_chk, existing, _ = run(
            ["gh", "pr", "list", "--head", branch, "--state", "open",
             "--json", "url", "--jq", ".[0].url // empty"],
            cwd=clone_dir, check=False,
        )
        existing = existing.strip() if rc_chk == 0 else ""
        if existing:
            pr_out, pr_err = existing, ""
        else:
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
        # reported via `tag_warning`, never an exit code. Skip if the tag
        # already exists, so a name collision is reported as a warning, not an error.
        # (Reached only after the push and PR-create succeed.) The tag points at
        # the ship commit; valid for merge-commit upstreams (the commit is preserved on
        # the default branch) — see github-pr-workflow.md's squash/rebase caveat.
        tag = f"{name}-v{args.version}"
        result = {"pr_url": pr_url, "work_dir": str(work_dir), "branch": branch, "version": args.version, "tag": tag,
                  "marketplace": marketplace, "readme": readme, "removed_files": removed_files}
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
