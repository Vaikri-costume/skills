# Tier-Transition Checks

The per-audience-tier validation gate (Step 4). Which check-SET runs is chosen from the target's `metadata.intended-audience` (one of `personal` / `claude-users` / `model-agnostic`) — that drives the Cowork / MCP / cross-runtime checks below. When invoking `portability_lint.py`, pass the matching tier as `--tier <tier>`: the lint itself reads `metadata.tier` when `--tier` is omitted, and skill-creator-ccvw keeps `tier` and `intended-audience` 1:1 (same value triplet) — so they normally agree, but `metadata.tier` is the field the lint actually keys on. If the two ever diverge on a target, the orchestrator resolves it at Step 1 by asking the user which field is authoritative for this run (not a fix-before-ship block). The tiers are defined in skill-creator-ccvw's `references/portability-spec.md`; this file specifies which checks the publisher runs at each.

## Vendored-sync checks

The lint scripts are vendored into the publisher (behavioral copies of their canonical sources with exactly one intentional difference — the vendor-header docstring; the three lint scripts source from skill-creator-ccvw, the two ledger scripts from skill-tracer), so the publisher runs standalone without the builder installed. They carry a sync-contract header and MUST stay in sync with canonical — re-copy when the builder's or tracer's versions change:
- `~/.claude/skills/skill-publisher/scripts/portability_lint.py`
- `~/.claude/skills/skill-publisher/scripts/attribution_lint.py`
- `~/.claude/skills/skill-publisher/scripts/quick_validate.py`
- `~/.claude/skills/skill-publisher/scripts/render_ledger.py` (canonical: skill-tracer)
- `~/.claude/skills/skill-publisher/scripts/append_ledger.py` (canonical: skill-tracer)

**Confirm the vendored copies are in sync before running them** — `scripts/check_vendored_sync.py` (exit 0 = in sync; exit 2 = usage error — check the `--pairs` argument if you override the default) compares the behavioral code of all five vendored copies (the three lints + `render_ledger.py` + `append_ledger.py`) against their canonical sources, ignoring only the intentional vendor-header docstring. A drift means the builder/tracer evolved its version and the publisher would otherwise enforce a stale standard:

```bash
python3 ~/.claude/skills/skill-publisher/scripts/check_vendored_sync.py
```

On exit 1, the report identifies the case per vendored file — act per case:
- **DRIFT** (file present, content differs) → re-copy from canonical source (the `diff` command and canonical path are in each file's sync-contract header); each DRIFT finding is a TIER cluster addressed in Step 5.
- **CANONICAL_MISSING** (canonical source not found — can't verify or re-copy) → USER-PAUSE; record the canonical path from the error so the user can locate the source manually.
- **VENDORED_MISSING** (vendored copy absent from this skill tree) → copy from canonical source directly.

**When multiple vendored files report different cases in one run, sequence the addressing:** resolve every `CANONICAL_MISSING` first (each is a USER-PAUSE — the user must locate the canonical before anything can be verified or copied), then re-copy the `DRIFT` and `VENDORED_MISSING` files from their canonical sources, then re-run `check_vendored_sync.py` once to confirm all five copies are in sync before proceeding.

On exit 2, fix the invocation and re-run. (If a vendored or canonical file is present but unreadable — a permission error — `check_vendored_sync.py` raises rather than returning a clean 0/1/2; treat such a crash as a USER-PAUSE, reporting the unreadable path.) Run this once at the top of Step 4.

---

## `personal` tier — skip Step 4

Personal skills aren't shared. No portability, Cowork, attribution-completeness, or cross-runtime checks apply. Step 4 is a no-op. (Polish + CCVW audit at Steps 2-3 still run — those are about quality, not shareability.)

---

## Frontmatter-validity gate (claude-users+ — runs first, blocking)

Before the tier-specific checks below, the frontmatter must be valid and structurally correct. Two vendored scripts (behavioral copies of their canonical sources — see the sync note above). `<target>` in all script commands below is the **absolute path to the skill root** being shipped (e.g. `~/.claude/skills/my-skill/`); use it consistently across calls since Bash cwd does not persist between tool calls:

```bash
python3 ~/.claude/skills/skill-publisher/scripts/quick_validate.py   <target>
python3 ~/.claude/skills/skill-publisher/scripts/portability_lint.py <target> --tier <tier>
```

These are two invocations of separate scripts with distinct purposes — not redundant. `quick_validate.py` runs first (blocking YAML/field check). `portability_lint.py` then adds structural checks (`name` == folder basename, reserved-prefix, SKILL.md spelling, frontmatter XML-tag content, plan-code leakage) that hold at every shared tier. The tier-specific portability violations (user-path/personalization/plan-code categories — see portability-spec.md for the full category list) are in the next step's invocation below. `quick_validate.py` (non-zero exit = blocking): YAML parses; `name` + `description` present; `name` kebab-case ≤64 chars; `description` ≤1024 chars with no angle brackets; `compatibility` ≤500 chars; only allowed top-level keys. Each failure is a blocking TIER cluster — a malformed name or misnamed file breaks discovery on every runtime, so resolve regardless of tier. (If `portability_lint.py` exits 1 with an `error` key instead of the normal `tier_violations`/`would_fail_at_tiers` shape, that means SKILL.md was not found at `<target>` — fix the path and re-run; it is a path error, not a findings result.)

---

## Interpreting `portability_lint.py` output

Capture the JSON to the canonical temp file `/tmp/skill-publisher-lint-out.json` (shell variables don't persist across Bash calls). The fixed path assumes one active ship run at a time; for concurrent ships of *different* skills, suffix it with the skill name — but the Step-8 package-out and Step-9 pr-body temp paths are fixed by design (Step 9's exit-5 recovery re-reads the fixed body path), so concurrent ships of the *same* skill are not supported — run those serially.

**Reuse:** when the frontmatter gate's `--tier` matches the tier the per-tier checks need (the same tier string), re-read the captured file (`cat /tmp/skill-publisher-lint-out.json`) rather than re-running — the output is identical. Run a fresh invocation only when the gate ran with a different `--tier`, which happens only when a Step-1 metadata divergence was resolved to the non-`intended-audience` field.

**Output keys:** `skill_path`, `declared_tier`, `ccvw_mandatory_missing`, `tier_violations`, `would_fail_at_tiers`. The script exits 1 when `ccvw_mandatory_missing` OR `tier_violations` is non-empty. (Exit 1 also covers the SKILL.md-not-found case — an `{"error": ...}` shape instead of the normal keys; check for an `error` key to distinguish a path error from a findings result.) If `would_fail_at_tiers` is absent or an empty array, there are no tier-escalation blockers — proceed.

**Blocking rule:** a finding **blocks the target's own tier if and only if the authoritative tier** (resolved in Step 1 — normally `metadata.intended-audience`, or `metadata.tier` if the user chose it on a divergence) **appears in `would_fail_at_tiers`.** "Blocks" means blocks *ship* (the finding must be addressed in Step 5); it does NOT halt Step 4 — keep collecting all tier findings first. If the target's tier is absent from the list, the finding is informational.
- `would_fail_at_tiers` holds plain tier-name strings, not objects. A body-level Claude pattern at claude-users is recorded in `tier_violations[]` with `blocks_tier: "claude-users (warning)"` but still collapses to a bare `claude-users` in `would_fail_at_tiers`, so it reads as blocking here. To treat it as a soft warning instead, inspect that originating `tier_violations[]` entry's `blocks_tier` for the `(warning)` suffix — `claude-users (warning)` is the only `(warning)`-suffixed `blocks_tier` value the lint produces.
- Structural / name / folder / SKILL.md-spelling and plan-code-leakage findings always block: they appear in `would_fail_at_tiers` for every tier. Only the **tier-conditional** violations (user-path / Claude-extension categories) are absent for `personal`; structural / CCVW-mandatory findings DO place `personal` in `would_fail_at_tiers` (they block every tier). In practice `personal` skips Step 4 entirely, so this matters only if the lint is consulted for a personal target against the skip rule.

Each finding that blocks the target's own tier is a TIER cluster. Maintain an in-memory `<tier-clusters>` list as you collect them across all the per-tier checks below; Step 5 addresses them together with `<audit-gaps>`.

---

## `claude-users` tier — Claude Code + Cowork

The skill is shared with other Claude users, on Claude Code AND Cowork. The frontmatter gate above plus all four checks must pass:

1. **Portability — Claude Code**
   ```bash
   python3 ~/.claude/skills/skill-publisher/scripts/portability_lint.py <target> --tier claude-users
   ```
   The frontmatter-validity gate above already ran `portability_lint.py --tier <tier>` and its JSON output includes both `ccvw_mandatory_missing` (gate check) and `tier_violations` (this check) — reuse that output rather than running a second invocation when the tier matches. Run a fresh invocation only if the gate ran with a different `--tier` value. (WHY reuse: shell variables do not persist across Bash tool calls in Claude Code; the temp file at `/tmp/skill-publisher-lint-out.json` bridges the gap; when the tier arguments are identical, the script output would be identical, so re-running is pure waste — re-read the file instead.)
   Pass: no `tier_violations`, no `ccvw_mandatory_missing`. Failures: hardcoded user-specific paths (your ledger isn't their ledger), missing CCVW-mandatory structure (README/HISTORY/glossary/dirs), personalization leakage (cat 15 — your name in shippable content), plan-code leakage (cat 16). Each becomes a TIER cluster addressed per `ship-checklist.md`.

2. **Cowork-compatibility** — per `cowork-compatibility.md`. The skill must work in Cowork's runtime, not just Claude Code. Both this AND the Claude Code portability lint must pass.

3. **Attribution completeness + license validity**
   ```bash
   python3 ~/.claude/skills/skill-publisher/scripts/attribution_lint.py <target>
   ```
   Pass: `would_fail_attribution_check: false`. Verifies HISTORY.md attribution is well-formed for the declared category, and LICENSE present whenever `author.history[]` is non-empty (any history chain, not only Category A forks — note attribution_lint.py's own missing-LICENSE message text says "Category A", which is imprecise; the check fires for any non-empty history, so trust the any-history rule, not the message wording). Valid `role` values in `author.history[]` entries are exactly: `original`, `fork-adapter`, `heavy-revision` (this set is closed — `attribution_lint.py` rejects any other value with a `history-entry-invalid-role` finding). **Branch on the output shape first:** when HISTORY.md is absent, `attribution_lint.py` does NOT emit `would_fail_attribution_check` — it prints `{"error": ..., "note": ...}` and exits 1. Treat that shape (an `error` key, no `would_fail_attribution_check`) as the **degraded/backfill** path: offer to scaffold a minimal HISTORY.md (Step 1's degraded-mode flow), not as a normal attribution failure. Only when the output carries `would_fail_attribution_check` do you read it as the pass/fail signal. (`attribution_lint.py` also emits advisory-severity entries in its `violations[]` array — e.g. `see-also-without-reference` — that do NOT set `would_fail_attribution_check` and do NOT change the exit code. Read `violations[]` for advisory-severity entries and surface them to the user as informational notes; `would_fail_attribution_check` remains the blocking pass/fail gate. Each violation's `severity` is exactly one of `blocking` or `advisory` — that set is closed. The `violations[].type` strings are the lint's own internal set — branch on `severity` + the human `message`, not on an exhaustive `type` enumeration. Blocking violations include not only missing fields but **structural-parse failures** — `author`/`history`/`inspirations` of the wrong YAML shape (not a dict / not a list); address those by fixing the malformed shape, not by adding a field.) If HISTORY.md was generated by Step 1's degraded-mode flow (a minimal scaffold) and `would_fail_attribution_check: true` is returned: create a TIER cluster for each missing field and address it — whenever `author.history[]` is non-empty (any history chain, not only Category A), attribution_lint flags a missing `LICENSE` file (plus any missing `role`/`name` on any entry, and `skill`/`license` on the FIRST entry); for missing inspiration fields, `skill`/`by`/`pattern` in `inspirations[]`. Note `attribution_lint.py` does NOT check any `source` field — the upstream `source` URL a PR needs is not an attribution_lint finding; it is resolved at Step 9 (`github-pr-workflow.md`). `attribution_lint.py`'s output names the specific gaps among the fields it does check. Additionally, confirm the frontmatter `license` is a recognized SPDX/OSI identifier with `scripts/spdx_check.py <target>` (deterministic membership test — no more re-improvising the recognized set):

   ```bash
   python3 ~/.claude/skills/skill-publisher/scripts/spdx_check.py <target>
   # exit 0 = recognized (verdict: OK); exit 1 = absent/unrecognized; exit 2 = usage error (SKILL.md not found — fix the path)
   # NOTE: do NOT pass --require here (Step 4 is advisory — a license issue becomes a TIER cluster in Step 5, not a hard gate;
   #       the hard --require gate runs at PR time in github-pr-workflow.md's license gate)
   ```

   On exit 1, read the `verdict` field in the JSON output: `"USER-PAUSE"` (default — license missing/unrecognized, manual decision needed) or `"FAIL"` (only when `--require` is passed AND the license is ABSENT — a present-but-unrecognized license stays `"USER-PAUSE"` even under `--require`; FAIL is the hard failure that blocks the public push gate). Both paths are USER-PAUSE for the ship operator: the script never auto-sets a license and the corrected-id hint in the output guides the fix.

   A missing or unrecognized license when the skill is heading to a public upstream is a USER-PAUSE, not an auto-FIX — the script never sets a license (you can't guess the author's licensing intent). The PR step enforces this as a hard gate before pushing to a public repo (`github-pr-workflow.md`). (If the license is an uncommon-but-valid SPDX identifier the default recognized set omits, pass `--extra "ID1,ID2"` to extend the set before treating it as a USER-PAUSE — the script's "re-run with --extra" hint in the output names the exact id.)

4. **Security** — per `security-checks.md`. Runs once here at ship time (it's the heaviest check; running it at the final shippable state catches the released artifact, not transient drafts). **Start with the deterministic pre-pass** `scripts/security_scan.py <target>` — it regex-scans the grep-able categories (1 hardcoded creds, 3 unsafe deser, 7 insecure crypto, 8 path traversal, 13 telemetry, 14 deprecated APIs) and emits `SEC-*` candidate findings in code files (`.md` hits go to a separate review-only `prose_matches` bucket; the scanner's own pattern lines carry a `security-scan: ignore-line` opt-out):

   ```bash
   python3 ~/.claude/skills/skill-publisher/scripts/security_scan.py <target>
   # exit 0 = no code findings; exit 1 = candidate SEC-* finding(s) → confirm each + address per ship-checklist
   # exit 2 = argument is not a directory OR directory walk raised OSError — check the <target> path and permissions, then re-run
   ```

   After the scan, check the `unreadable_files` array in the JSON output — files that were counted in the scan total but could not be read. If `unreadable_files` is non-empty, the scan is incomplete: review those files manually for the grep-able categories before treating the scan as done. (security_scan.py also emits a `prose_matches` array — regex hits in `.md` docs; these are review-only/advisory: skim for a real secret pasted into docs but do NOT fail on them.) This is **advisory, not blocking** — continue the remaining tier checks, but record a TIER cluster noting that manual security review of the unreadable file(s) is still pending, so the gap isn't silently skipped.

   Then walk the **judgment categories the script does NOT cover** (2 injection, 4 weak authn/authz, 5 sensitive-data-in-logs, 6 broken access control, 9 SSRF, 10 TOCTOU, 11 timing/error-leak, 12 cross-agent trust) by adversarial reading per `security-checks.md` — these need to know what's user-supplied / sensitive / privileged and can't be regex'd. Each confirmed finding (scripted or judgment) becomes a TIER cluster. (Category 15 — frontmatter prompt-injection — appears in neither list above: it is already enforced by the frontmatter-validity gate's `portability_lint.py` XML-tag-content check, so skip it in this judgment pass.)

5. **MCP-dependency declaration** (only when the skill uses MCP tools). If SKILL.md references `mcp__<server>__*` tool names anywhere (frontmatter included — `mcp_deps.py` scans the whole file, both frontmatter and body, as the calling contract) — i.e. it's an MCP-enhancement or multi-MCP skill (skill-creator-ccvw Category 2/3) — the skill depends on an MCP server the new installer must connect *before* it works. Verify that dependency is declared where the installer will see it. `mcp_deps.py` considers a server declared if **either** condition holds:
   - the README names the required server(s) anywhere in its text (word-boundary match on the server slug — not restricted to a specific section heading), **or**
   - `metadata.mcp-server` is set in frontmatter (the conventional machine-readable signal).

   At least one of the two must be present per undeclared server.

   ```bash
   python3 ~/.claude/skills/skill-publisher/scripts/mcp_deps.py <target>
   # exit 0 = no MCP calls (N/A) or every called server declared; exit 1 = undeclared server(s)
   # exit 2 = SKILL.md not found at the given path (check the argument) or argparse usage error — fix and re-run
   ```
   (Note: `mcp_deps.py` counts every `mcp__<server>__*` occurrence anywhere in SKILL.md, including frontmatter `allowed-tools` entries, as a called server requiring declaration in `metadata.mcp-server` or the README — listing a server in `allowed-tools` does not by itself declare it.) `mcp_deps.py` extracts the distinct `mcp__<server>__*` servers the SKILL.md calls (handling underscores in server names, which the old grep/sed one-liner mangled) and confirms each is declared in EITHER `metadata.mcp-server` OR the README. A skill that calls `mcp__notion__*` but never tells the installer "connect the Notion MCP" ships broken-on-arrival for everyone but the author — exactly the "users connect your MCP but don't know what to do / blame your connector" failure. Each entry in the script's `undeclared` list is a TIER cluster (FIX: add the dependency note to the README install section + set `metadata.mcp-server`). Skills that call no `mcp__*` tools skip this check entirely (the script reports N/A, exit 0). (Branch on the exit code and the `undeclared` array — the script's human-readable `note` field is advisory output, not a parsed signal; do not branch on its wording.)

---

## `model-agnostic` tier — beyond Claude

The skill is portable to Gemini CLI / Cursor / OpenCode / any agentskills.io-compatible runtime. All `claude-users` checks PLUS:

6. **Portability — model-agnostic**
   ```bash
   python3 ~/.claude/skills/skill-publisher/scripts/portability_lint.py <target> --tier model-agnostic
   ```
   (Reuse, don't re-run: for a `model-agnostic` target the Step-4 frontmatter gate already ran `portability_lint.py --tier model-agnostic`, so re-read the captured `/tmp/skill-publisher-lint-out.json` per "Interpreting portability_lint.py output" above rather than re-invoking. A fresh run is needed only if the gate ran a different `--tier` — a Step-1 metadata divergence resolved to the non-`intended-audience` field.)
   Stricter: also flags Claude-specific extensions (Agent tool, dynamic injection, `$ARGUMENTS`, `mcp__*` tool names, Claude-Code-system paths). Each non-portable construct must be stripped or rewritten per the blocklist in skill-creator-ccvw's `portability-spec.md`. (Note: a Category-3 MCP-enhancement skill that depends on `mcp__*` tools generally cannot reach `model-agnostic` at all — `mcp__*` names are Claude-specific. Such a skill's natural ceiling is `claude-users`; shipping it model-agnostic means abstracting the MCP calls behind a runtime-neutral tool interface, which is usually a redesign, not a ship-time fix. Surface this to the user rather than mechanically stripping the calls.)

7. **agentskills.io compatibility verification** — confirm frontmatter has `compatibility: agentskills.io@1.0` (or higher). This is the explicit signal to non-Claude runtimes.

8. **Cross-runtime install surface** — a user-confirmed note listing which runtimes the skill was tested on (`tested install on: Gemini CLI, Cursor`). Not automated — the publisher asks the user which runtimes they verified, records the answer in the README install section + changelog. Honest about what was actually tested vs claimed.

---

## What "pass" means before ship proceeds

Step 4 doesn't block ship outright on failure — it generates TIER clusters that Step 5 addresses. The skill ships once every TIER cluster has a FIX or STRENGTHEN (or a USER-PAUSE the user has resolved). A USER-PAUSE left unresolved blocks ship at that tier — the publisher tells the user "N tier-checks need your decision before shipping at `<tier>`; resolve them or ship at a lower tier."
