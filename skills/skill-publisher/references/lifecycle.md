# Lifecycle (Phase 4) — ship status, docs-only ship, rollback

The post-PR lifecycle the publisher otherwise abandons at Step 9. Three on-demand modes, all reading the Step-10 **ship manifest** (`~/.claude/skill-publisher-ledger/<skill>.manifest.json`). SKILL.md Step 1's mode dispatch routes here; this file owns the mechanics.

---

## Pre-ship snapshot (every full / docs-only ship — Step 1)

So `--rollback` can restore a completed-but-wrong ship, **snapshot the target before Step 2 edits it**. After resolving `<target>` (and only for `full`/`docs-only` mode — not `readiness`/`rollback`/`status`), copy the skill's three mutable root files to a conventional snapshot dir:

```bash
SNAP="$HOME/.claude/skill-publisher-ledger/<skill>.pre-ship"
mkdir -p "$SNAP"
for f in SKILL.md README.md HISTORY.md; do [ -f "<target>/$f" ] && cp "<target>/$f" "$SNAP/$f"; done
echo "pre-ship snapshot:: $SNAP"   # record the path in your response text
```

The snapshot is the **latest ship only** (overwritten each ship) — the manifest is also overwritten each ship, so a single pre-ship state is sufficient (rollback undoes the most recent ship, not arbitrary history). A snapshot failure is a warning, not a ship-blocker (rollback simply won't be available for this ship); surface it and continue. The snapshot covers the three files the publisher mutates (polish + version-bump); a script fix from Step 5 is rare and recorded in the ledger + git, so rollback restores the three root files and notes any script change for the user to revert from git.

---

## `--status <skill>` (ship_status.py)

On-demand post-merge follow-up — **pull-based, never a background poller**.

```bash
python3 ~/.claude/skills/skill-publisher/scripts/ship_status.py --status <skill> [--repoint-tag]
```

Reads the manifest and reports, via `gh`:
- **PR merge state** (`gh pr view`): OPEN / MERGED (with date) / CLOSED, or `unverified` when gh/network is down (degrade, never a failure — mirrors `verify_ship`'s offline rule).
- **Dangling ship tag**: when the upstream **squash/rebase-merged**, the ship-branch commit the `<skill>-v<version>` tag points at is discarded, so the tag dangles on an orphan commit (a chore `github-pr-workflow.md` flags). `ship_status` detects this (the tag's commit is not reachable from the default branch) and, with `--repoint-tag`, force-updates the tag ref to the merge commit. **`--repoint-tag` is opt-in** because it rewrites a remote ref (outward-facing) — default is detect + report only.
- **Catalog staleness** (advisory): if the skill is a marketplace catalog entry, compares the catalog's recorded ref to the shipped version.

Exit: 0 reported (incl. unverified); 1 no manifest (skill never shipped); 2 usage/path error.

---

## `--docs-only` partial ship (opt-in, right-sized gate)

When the change since the last ship touches **only README.md / HISTORY.md prose** (no SKILL.md logic, no `scripts/*`), the full gate is overkill — the cold CCVW audit and the behavioral tier lints only re-validate unchanged SKILL.md logic. `--docs-only` runs **polish + a patch bump + repackage + PR**, skipping the cold audit (Step 3) and the behavioral tier lints (Step 4). Default stays the full gate; this is an **explicit opt-in override**, in slight tension with the "full gate every ship" intent — frame it as the user's choice, not a silent shortcut.

**Gate (this proves the override is safe):** resolve the upstream + diff against the published state exactly as Step 7a does (`github_pr.py --diff-only` + `diff_published.py`). Then inspect the diff's `modified`/`added`/`removed` paths:
- If **every** changed path is `README.md` or `HISTORY.md` → proceed on the docs-only path.
- If **any** changed path is `SKILL.md`, a `references/*.md`, a `scripts/*`, or an asset → **REFUSE**: tell the user "the change since last ship touches `<paths>`, not just README/HISTORY — `--docs-only` would skip the audit + tier checks that validate those. Re-run `/skill-publisher <skill>` for a full ship." Do not run the partial path.
- No published baseline (no upstream / first ship) → refuse too: there is nothing to prove the change is docs-only against; route to full.

**The docs-only path** (after the gate passes):
1. Step 2 polish (README + HISTORY prose only).
2. Skip Step 3 (cold audit) and Step 4's behavioral tier lints — but STILL run `quick_validate.py` + `spdx_check.py` (cheap frontmatter/license sanity; a docs edit can still break frontmatter). A failure there is a blocking TIER cluster as usual.
3. Step 5 addressing (only the polish + any quick_validate/spdx cluster).
4. Step 6 README, Step 7 **patch** bump + changelog (docs change = patch by definition).
5. Step 8 package, Step 9 PR, Step 10 verify + manifest — unchanged.

The ledger records the run with a note that the audit + behavioral tier lints were skipped under `--docs-only` (so the audit trail shows the reduced gate was a deliberate choice).

---

## `--rollback <skill>` (undo a completed-but-wrong ship)

Recovery handles *interrupted* ships; rollback handles a *completed-but-wrong* one (e.g. polish introduced a regression that shipped). Manifest-driven; outward-facing steps reuse the PR-confirmation rails.

```bash
python3 ~/.claude/skills/skill-publisher/scripts/ship_manifest.py read <skill>   # the ship to undo
```

Procedure:
1. **Read the manifest.** No manifest → nothing to roll back (tell the user, exit). It names the `version`, `artifact`, `pr_url`, `branch`, `tag`.
2. **Confirm with the user** (AskUserQuestion: "Roll back <skill> v<version>? This restores SKILL.md/README/HISTORY to the pre-ship snapshot, deletes the artifact, and closes PR <pr_url>." / Cancel). Rollback is outward-facing (it closes a PR) — never silent.
3. **Restore the three root files** from the pre-ship snapshot (`~/.claude/skill-publisher-ledger/<skill>.pre-ship/`): copy `SKILL.md`/`README.md`/`HISTORY.md` back over the live skill. If the snapshot dir is absent (an old ship from before snapshots, or it was cleaned), surface that — restore what you can and tell the user the rest must come from git.
4. **Delete the artifact** at `manifest.artifact` (the `.skill`), if present.
5. **Close the PR** (only after the confirm): `gh pr close <pr_url>` — and if the ship tag was pushed, optionally delete it (`git push origin :refs/tags/<tag>` via a temp clone, or `gh api -X DELETE repos/<owner>/<repo>/git/refs/tags/<tag>`). If the PR was already MERGED, do NOT close/delete — warn the user that the ship already merged and a rollback now needs a revert PR, not a close (offer to open one or stop).
6. **Record a ledger row** (`--phase PR`, root-cause "rollback of v<version>", address "FIX (rolled back: restored pre-ship snapshot, deleted artifact, closed PR <url>)") so the reversal is auditable, and a close-round/canonical comment noting the rollback.

Rollback is the one path that *deletes* a remote artifact (the PR/tag) — keep every such step behind the Step-2 confirm, and never act on a MERGED PR without re-confirming the revert-vs-close choice.
