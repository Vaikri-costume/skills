# Packaging

How skill-publisher packages a skill for distribution (Step 8), per audience tier. Uses `scripts/package_skill.py`.

---

## Per-tier packaging

| Tier | Packaging | Output |
|---|---|---|
| `personal` | None — files stay in place at `~/.claude/skills/<name>/` | (no artifact) |
| `claude-users` | `.skill` archive — a tarball of the skill tree installable on Claude Code AND Cowork. **Plus** a `.zip` for the Claude.ai web upload route when the user ships there. | `<name>.skill` (+ optional `<name>.zip`) |
| `model-agnostic` | agentskills.io-standard package — same tarball but verified against the agentskills.io@1.0 layout (SKILL.md + frontmatter conformant, no Claude-only extensions) | `<name>.skill` (agentskills.io-conformant) |

**Install surfaces and the format each needs:**
- **Claude Code** — `.skill` archive (`claude skills install <name>.skill`) or manual copy into `~/.claude/skills/`.
- **Cowork** — same `.skill` archive.
- **Claude.ai (web)** — a **zip** of the skill folder, uploaded via **Settings > Capabilities > Skills**. This is the route a non-CLI user takes; produce it with `--format zip`.

---

## What goes in the package

The full skill tree EXCEPT the following. **The authoritative exclusion set is `package_skill.py`'s `EXCLUDE_NAME_PATTERNS` + `EXCLUDE_PATH_SUBSTRINGS` + the `evals/iteration-*` component check in `should_exclude()` — that code is the single home; the list below is an illustrative summary for the reader, not a second source of truth.** If the two ever disagree, the script governs (it is what actually runs); when adding or removing an exclusion, edit the script and treat this list as documentation that may lag:
- `*.bak*` files (pre-edit snapshots)
- `*.orig` files (patch/merge backups)
- Hidden files and directories (`.DS_Store`, `.gitignore`, `.git/` tree, etc.)
- `__pycache__/` directories and `*.pyc`/`*.pyo` compiled bytecode
- Any `*-workspace/` or `evals/iteration-*/` artifacts (eval outputs — per CCVW convention, eval outputs go to `~/.claude/skill-creator-evals-ledger/`, not the skill tree; the `evals/iteration-*/` exclusion is defensive in case stray outputs landed in the tree)
(The ship ledger lives at `~/.claude/skill-publisher-ledger/<skill>.md` — outside the skill tree — and is never under `<skill-path>`, so it is never picked up by the packaging rglob; no explicit exclusion needed.)

Include: SKILL.md, README.md, HISTORY.md, LICENSE (if present), references/, scripts/, assets/. Note: `evals/evals.json` and `evals/eval_set.json` (eval definition files, if present in the skill tree) ARE included — they define the skill's test suite, not runtime outputs. Only `evals/iteration-*/` directories (run outputs) are excluded.

---

## package_skill.py

```bash
python3 ~/.claude/skills/skill-publisher/scripts/package_skill.py <skill-path> --tier <tier> [--format skill|zip] [--output <path>]
```

- Reads the skill tree, applies the exclude rules, writes a `.skill` tarball (default) or a `.zip` (`--format zip`).
- `--format skill` (default): gzipped tarball for Claude Code + Cowork install. `--format zip`: a plain zip with the skill folder as the top-level entry, for the Claude.ai web upload route.
- At `model-agnostic` tier, also runs a final conformance check (frontmatter has `agentskills.io@` compatibility; no Claude-extension patterns) and refuses to package if the skill would not load on a non-Claude runtime — directs the user back to Step 4's model-agnostic portability fixes. (The conformance gate applies regardless of `--format`.)
- Default output: `<skill-path>/../<name>.skill` (or `<name>.zip` for `--format zip`). Override with `--output`.

---

## Content hashing

Every package carries integrity hashes so a consumer (and Step 10) can confirm the bytes are the bytes that were packaged:

- **`SHA256SUMS` inside the package** — a `sha256sum`-format manifest (`<hex>  <path>`, one line per shipped file) at `<name>/SHA256SUMS`, keyed by the path relative to the package root. After unpacking, `cd <name> && sha256sum -c SHA256SUMS` validates every file. It lists the content files, not itself.
- **`archive_sha256` in the JSON output** — the SHA-256 of the final archive bytes. It cannot live inside the archive (it would hash itself), so it is emitted in `package_skill.py`'s stdout JSON and recorded in the ship manifest. Step 8 captures it and Step 10 passes it to `verify_ship.py --expected-digest`, which re-hashes the artifact on disk and fails the ship on a mismatch (corruption / truncation / a swapped artifact between packaging and verification).

The per-file `SHA256SUMS` is reproducible (content hashes); the whole-archive digest is NOT reproducible across packagings (gzip embeds an mtime) — it identifies *this* artifact, which is exactly what the Step-8→Step-10 integrity check needs.

---

## package_skill.py exit codes

On success the script prints a multi-field JSON object on stdout (`packaged`, `tier`, `format`, `files_included`, `archive_sha256`, `sha256sums_included`, `manifest`); error paths print a JSON error object on **stderr** (stdout empty), except argparse usage errors which print usage text. **Branch on the exit code first** — exits 1, 2, and 4 all print a JSON error object, so stderr-shape alone never separates them:

- **0** = success → parse stdout JSON, extract `packaged` (the artifact path for Step 10's `--artifact`) **and `archive_sha256`** (Step 10's `--expected-digest`).
- **1** = SKILL.md absent from target. It existed at Step 1, so this means it was deleted/moved mid-run. USER-PAUSE: report the missing path, ask the user to restore it, then retry (not an inline target-fix).
- **2** = personal-tier packaging attempted, OR a missing/invalid `--tier`, OR an out-of-choices `--format` value. (The personal-tier refusal is a **defensive guard for a manual/standalone invocation** — it is NOT reachable from the publisher's own Step-8 flow, which routes `personal` to "no packaging, files stay in place" and only ever calls this script with `--tier claude-users`/`model-agnostic`. So from a normal ship this exit-2 sub-cause means an argument-assembly bug, not an expected path.) Distinguish by output shape: a **JSON error object** = the personal-tier refusal (a manual run hit it, or Step 8's tier branch mis-fired — check the branch and re-route); **argparse usage text with no JSON** = a missing required `--tier` or an out-of-choices `--tier`/`--format` value (correct it — `--tier` to `claude-users`/`model-agnostic`, `--format` to `skill`/`zip` — and re-run; an omitted `--format` does NOT exit 2, it defaults to `skill`). An invalid-`--tier` *value* is structurally precluded because the tier is validated upstream, so argparse-2 here signals an argument-assembly bug, not an expected path.
- **3** = model-agnostic conformance failure (model-agnostic tier only — does not occur for a claude-users invocation) → PACKAGE cluster, address, retry.
- **4** = archive write failure → investigate disk/permission and retry.

Do not capture stdout as a plain path; it is multi-field JSON. **Prefer** capturing the full JSON to a temp file (`python3 … package_skill.py <target> --tier <tier> > /tmp/skill-publisher-package-out.json; echo "exit:$?"`) then reading `packaged` from it in a subsequent Bash call — this keeps the exit code visible. The inline `| python3 -c "import sys,json; print(json.load(sys.stdin)['packaged'])"` form is a fallback that is only safe **after** confirming exit 0, because a pipe masks the script's own exit code. State the artifact path in your response text (shell variables are lost between Bash tool calls) so Step 10 can use it for `--artifact`.

---

## Install instructions the package implies

The publisher writes these into the target README's `## How to install` (Step 6):
- `claude-users`: "Download `<name>.skill`, then `claude skills install <name>.skill`" (or the manual `~/.claude/skills/` copy + the Cowork equivalent).
- `model-agnostic`: per-runtime install commands for the runtimes the user confirmed testing at Step 4's cross-runtime install-surface step. Common patterns: Gemini CLI → `gemini skills install <name>.skill`; Cursor → drag-and-drop or `cursor://skill/install/<name>`; OpenCode → `opencode skill add <name>.skill`. Exact commands evolve with the runtimes — confirm against current docs for each. List only runtimes the user actually verified, not a speculative all-runtime list.

---

## Install-command form derivation (Step 6 `## How to install`)

The install-command FORM is chosen by whether a resolvable upstream source URL exists — `author.history[].source`, or `inspirations[].source` as the same fallback Step 9 uses (so a Category-B skill recording only `inspirations[].source` still gets a registry install command, matching the upstream Step 9 PRs to) — independent of previously-published status:

- **`personal`** → "installed locally".
- **`claude-users`** → marketplace command + manual path:
  - If `author.history[].source` is a GitHub-based registry URL (host contains `github.com`; otherwise treat the registry as unknown), the form is `claude plugins install <org>/<repo>` (parse `<org>/<repo>` from the URL path after the host; a `github.com` URL with no parseable `<org>/<repo>` — bare host or org-only — falls to USER-PAUSE like an unknown registry).
  - If the URL is from a different registry whose install syntax is unknown → **USER-PAUSE**: halt and ask the user for the correct command form; do not proceed to Step 7 until they answer. WHY: a wrong install command baked into the published README sends users a command that fails or installs the wrong thing — an outward-facing error — so when the registry's syntax is not certain, ask rather than guess.
  - If there is no resolvable source URL — a first ship, a no-URL record, a `source` value that does not parse as a URL, or previously-published-by-tag-only — include only the manual `~/.claude/skills/` install path.
- **`model-agnostic`** → per-runtime install commands (same first-ship vs previously-published split: if no agentskills.io/registry URL is recorded, manual per-runtime paths only; once published, add the registry install command).

**Previously-published** = the skill's HISTORY.md records a prior release (an `author.history[]` entry carrying a `source` URL) OR a `v<semver>` git tag exists in the target. To check tags: first confirm a git repo with `git -C <target> rev-parse HEAD` (if it fails, the target is not a git repo — treat the tag signal as absent, not an error), then `git -C <target> tag --list 'v*'`; a non-empty list of `v<semver>` tags = previously-published-by-tag. This tag signal feeds Step 7's changelog "changes since last ship" git-log sourcing, NOT the install-command form (which keys on the source URL) — so the tag check is not redundant with the URL check.

**Executability probe (after the GitHub-registry form is generated).** The `<org>/<repo>` parsed above is derived by string-parsing the URL alone — nothing yet confirms the repo exists or that a marketplace catalog entry is present. After generating a `claude plugins install <org>/<repo>` command (only this form — the manual-path and "installed locally" forms have nothing reachable to probe), run `scripts/install_check.py --repo <org>/<repo> [--marketplace-name <plugin-name>] --json` (`--json` makes the result the machine-readable object the orchestrator reads `repo`/`catalog` fields from — the bare command prints only human-readable lines):
- `gh repo view <org>/<repo>` checks the repo is real + accessible; gh-absent falls back to a weak HTTP HEAD; neither/offline → `unverified` (degrade, like `verify_ship.py`'s PR check — never a failure).
- `--marketplace-name <plugin-name>` additionally scans the live catalog (`~/.claude/plugins/marketplaces/claude-plugins-official/.claude-plugin/marketplace.json`, matched by entry `name` or `source.url`) for the documented marketplace install — reusing marketplace-discover's catalog path.
- **Exit 0** = reachable or unverified (no action). **Exit 1** = a confirmed problem (`repo: not_found`/`private`, or `catalog: absent`) — surface as a **warning, not a hard block**: on a first ship that creates the repo in Step 9 a `not_found` is expected, so let the user decide (fix the URL vs ship anyway). **Exit 2** = usage/unparseable URL. Write no ledger row for an `unverified` result — an unconfirmable probe is not a finding.
