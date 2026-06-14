# GitHub PR Workflow

How skill-publisher opens a pull request (Step 9) when the target skill has an upstream origin. Uses `scripts/github_pr.py` + the `gh` CLI.

---

## When this runs

Only when the target's HISTORY.md records an upstream GitHub/marketplace origin:
- `author.history[].source` (a fork's original repo URL — Category A), OR
- `inspirations[].source` (a derivative's source repo, if recorded — Category B)

If no source URL is recorded, there's no upstream to PR *back* to — but the user may still want to publish the skill to a fresh public repo. Offer the **no-upstream hosting branch** (below) rather than silently skipping. Degraded-mode skills (no HISTORY.md) skip the PR-to-upstream flow; offer them the hosting branch too if they want to publish.

---

## No-upstream hosting branch (publish to a fresh repo)

When the skill has no recorded upstream but the user wants it public, offer to create a new repo instead of opening a PR:

1. Confirm intent + the license gate (below) — publishing makes the skill public under its declared license.
2. `gh repo create <name> --public --source <temp-clone> --push` (or `--private` if the user prefers), from a temp clone/worktree, never the live skill dir.
3. Generate a **repo-root human README** — distinct from the skill's in-folder `README.md`. The in-folder README is the skill's runtime-adjacent intent doc; the repo-root README is the GitHub landing page (what the skill is, install instructions, a usage example, a screenshot if available). Generating a repo-root README is **the user's responsibility to finalize** — the publisher drafts one and USER-PAUSEs for the user to review/replace before the repo goes public (a repo-level README is outward-facing marketing the publisher shouldn't auto-write-and-publish unreviewed).
4. The skill folder still must NOT contain a repo-style README (CCVW keeps `README.md` as the skill's intent doc) — the repo-root README lives one level up, at the repo root, beside the skill folder.

---

## The flow

`scripts/github_pr.py` does:

1. **Locate the upstream repo** from the HISTORY.md source URL. Verify `gh auth status` (the user is authenticated to GitHub).
2. **Determine where the skill lives in the repo** — for a fork, the skill is a directory in the upstream repo (e.g., `plugins/<name>/`). For a marketplace skill, it's the catalog entry's `source.url` path.
3. **Branch** — `git checkout -b ship/<name>-v<version>` off the upstream's default branch (in a clone/worktree the publisher creates under a temp dir; never the user's live skill dir). `<version>` is the HISTORY.md `version` value after Step 7's version bump (e.g., `ship/my-skill-v1.2.0`).
4. **Copy the polished + versioned skill** into the branch at the right path.
5. **Commit** — `github_pr.py` writes the message `Ship <name> v<version>` exactly (it does NOT append a changelog summary or a co-author trailer). A richer message or co-author trailer would be a manual step outside the script.
6. **Push** the branch to the user's fork (or the upstream if the user has write access).
7. **`gh pr create`** with the structured body the orchestrator passes via `--body-file` (which the orchestrator produces by filling `assets/pr-template.md` — see Invocation below): the changelog entry, the attribution chain, which tier-checks ran + passed, the version delta. (`github_pr.py` reads `--body-file` verbatim; it does NOT open or fill the template itself.)
8. **Return the PR URL** — on success `github_pr.py` prints a JSON object `{"pr_url": <url>, "branch": ..., "version": ...}` on stdout; the URL is its `pr_url` field. On the dry-run / unconfirmed path it instead prints `{"dry_run": true, ...}` with NO `pr_url` — do not present a URL in that case. On failure it prints `{"error": ...}` on stderr and exits non-zero. **Exit code reference:**
- **0** = success OR dry-run — distinguish by JSON shape (`pr_url` present = PR created; `dry_run: true` with no `pr_url` = confirmation-request path).
- **1** = auth failure — run `gh auth login` and retry (this remedy presumes `gh` is installed; a missing `gh` is exit 6, not exit 1 — branch on the exit code first).
- **2** = clone/checkout/commit failure OR argparse error when a required argument is missing/invalid (see Invocation above — if exit 2 occurs with no `error` JSON, i.e. before any git step, check the argument list first; otherwise read the `error` JSON for the git error, fix and retry).
- **3** = push failure — check branch conflicts or write-permission and retry.
- **4** = `gh pr create` did not yield a PR URL — two sub-paths: the `gh` command returned non-zero (read the `error` JSON on stderr; may be a duplicate PR) OR `gh` returned success but no parseable URL line (read the `stdout` field inside the JSON error object on stderr — that carries the gh output; raw stdout is empty — the URL parse failed). Handle per sub-path.
- **5** = body-file not found or unreadable (the script catches `OSError`, covering both missing and permission errors) — verify the `--body-file` temp file the orchestrator wrote (the canonical `/tmp/skill-publisher-pr-body.md`) is present and readable, NOT `assets/pr-template.md` (that is only the template source the orchestrator fills; the script reads the filled temp file). **Post-push caution:** the push (exit 3) happens BEFORE the body-file read, so on exit 5 the branch is already pushed with no PR — do NOT blindly re-run (that re-pushes; recovery rule 6 warns against double-push / duplicate PR). Fix the body file, then per recovery rule 6 check `gh pr list` / branch state and create the PR from the existing branch rather than re-pushing.
- **6** = required tool not found on PATH (git or gh not installed — the `error` JSON names the missing tool; tell the user to install it and retry).

Capture stdout, parse the JSON, and carry `pr_url` to Step 10's presentation. On a `pr_url`, sanity-check it looks like a PR URL (contains `/pull/` or the repo path) before carrying it forward — github_pr.py selects the last `https://` line gh emitted, which on rare occasions could be an advisory URL.

---

### Invoking `github_pr.py` (required arguments)

`github_pr.py` declares four required arguments plus the positional skill path — the **orchestrator supplies them; the script does not derive them**. The numbered flow above describes what the script does *with* these inputs, not values it computes:

- `<skill_path>` (positional) — the polished skill directory (`<target>`).
- `--upstream <url>` — the upstream repo URL, from HISTORY.md `author.history[].source` (Category A) or `inspirations[].source` (Category B).
- `--repo-path <path>` — the path within the upstream repo where the skill lives (e.g. `plugins/<name>` or `skills/<name>`). It is the in-repo location where the skill should live (e.g. `plugins/<name>` or `skills/<name>` by the upstream's layout convention), NOT a segment of the source URL (which is the repo root). The script's internal clone is created only after `--repo-path` is supplied, so it cannot be inspected beforehand — if the upstream's layout convention is unknown, ask the user.
- `--version <semver>` — the new HISTORY.md version (after Step 7's bump).
- `--body-file <path>` — a file the orchestrator writes by filling `assets/pr-template.md`'s `<...>` placeholders (changelog entry, attribution chain, tier-checks, version delta) with this run's values, then saving the result to the canonical temp file `/tmp/skill-publisher-pr-body.md` (use this exact path — Step 9's exit-5 recovery re-checks it). **The script reads this file verbatim — it does NOT open or fill the template.**
- `--confirmed` / `--dry-run` — confirmation flags (see Safety rails).

A missing or invalid required argument makes argparse exit **2** (the same code the flow uses for a clone/checkout/commit failure) — distinguish by output shape, which the executor can observe directly: argparse prints usage text with **no** JSON, while a git failure prints an `{"error": ...}` JSON object. On exit 2 with no `error` JSON, check the argument list first.

---

## Safety rails

- **Never push to a default branch directly.** Always a `ship/<name>-v<version>` branch + PR.
- **PR base + repo must be explicit.** The PR must target the **upstream** repo's default branch. `github_pr.py`'s `gh pr create` currently passes only `--title`/`--body`/`--head` — without `--base <upstream-default-branch>` and `--repo <upstream>`, `gh` infers base+repo from the clone's defaults, which can target the wrong branch/repo. **Known limitation:** until the script passes `--base`/`--repo`, verify the opened PR's base branch and target repo before treating Step 9 as done; this is flagged for a script code-fix. **If verification shows the wrong base or repo** (the PR is already open at this point — the script exited 0 with a `pr_url`): do not leave it; either `gh pr edit <url> --base <correct-branch>` if only the base is wrong, or close it (`gh pr close <url>`) and re-open against the correct repo/base, then carry the corrected URL forward. Surface the correction to the user.
- **Never operate on the user's live skill directory's git** — use a temp clone/worktree so a failed push doesn't corrupt the working skill.
- **Confirm before pushing.** The publisher shows the user the diff + target repo + branch name and asks for explicit confirmation before `git push` + `gh pr create`. Shipping to an external repo is outward-facing — confirm first.
- **Dry-run option.** `github_pr.py --dry-run` does everything except the push + PR-create, printing what it would do. The publisher offers this when the user is unsure. **`--dry-run` overrides `--confirmed`** — `github_pr.py` enters the dry-run path whenever `--dry-run` is present, regardless of `--confirmed`, so the confirmed re-run that actually opens the PR must OMIT `--dry-run`.
- **License gate before any public push.** Going public publishes the skill under whatever `license` its frontmatter declares — this gate applies to **both** publish paths: the PR-to-upstream flow (`git push` + `gh pr create`) AND the no-upstream hosting branch (`gh repo create --public … --push`). Before either, run `python3 ~/.claude/skills/skill-publisher/scripts/spdx_check.py <target> --require` to assert the frontmatter `license` is a recognized SPDX/OSI identifier (pass `--require` here — the PR license gate is a hard block; `--require` changes the verdict from `USER-PAUSE` to `FAIL` on exit 1 **only when the license is ABSENT** — a present-but-unrecognized license stays `USER-PAUSE` even under `--require`, so treat that case as a manual USER-PAUSE decision before pushing; the Step 4 attribution check intentionally omits `--require` because that is an advisory TIER cluster, not a hard gate). It prints a verdict JSON on stdout and exits: **0** = recognized (`verdict: OK`, ok to push); **1** = absent or unrecognized (`verdict: USER-PAUSE`; `--require` escalates to `FAIL` only for an ABSENT license — a present-but-unrecognized license stays `USER-PAUSE` even under `--require`) — it prints the corrected id for near-misses like "Apache 2.0" → "Apache-2.0"; **2** = usage error / SKILL.md not found (prints `ERROR:` to stderr, not the verdict JSON — fix the `<skill-path>` argument and re-run; this is not a license problem). If it's absent or unrecognized, **USER-PAUSE** — surface "no recognized license; a public PR would publish this under an unclear license. Set one (suggest MIT) or confirm intent before I push." Never silently default a license onto code headed to a public repo. (For Category A forks, the original's LICENSE preservation rules in skill-creator-ccvw's `attribution-spec.md` still govern.)

---

## PR body structure (from assets/pr-template.md)

```
## Ship: <name> v<version>

### What changed
<changelog entry for this version — the same text appended to HISTORY.md's changelog>

### Attribution
<category (A/B/C/D) + author chain or inspirations from HISTORY.md>

### Quality checks (tier: <tier>)
- Polish pass: <applied / N edits / no-op>
- CCVW Word/Spirit audit: <clean / N gaps addressed>
- Portability (<tier>): <pass>
- Cowork-compatibility: <pass / N/A — no user-facing output>
- Attribution lint: <pass>
- Security: <clean / N findings addressed>

### Version
<prior-version> → <new-version> (<patch|minor|major>)

---
🤖 Shipped via skill-publisher (the ship phase of build → trace → ship)
```
