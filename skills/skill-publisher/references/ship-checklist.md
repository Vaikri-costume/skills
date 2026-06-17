# Ship Checklist

What skill-publisher checks before a skill is release-ready, and how it addresses what it finds. This is the publisher's analog of skill-tracer's address-decision rules — same FIX/STRENGTHEN/USER-PAUSE discipline, applied to ship-phase findings.

---

## The checklist (by workflow step)

| Step | Check | Pass condition |
|---|---|---|
| 2 Polish | SKILL.md + README.md simplified | simplify pass applied; no regressions in the verification (per `polish-pass.md`) |
| 2 Polish | SKILL.md body ≤ ~5,000 words / ~500 lines | over-length flagged; detail moved to `references/` (or length ratified as load-bearing) |
| 3 Audit | CCVW Word/Spirit compliance | audit Agent returns `No gaps found` (after addressing any GAPs) |
| 3 Audit | Description quality — WHAT + WHEN + triggers | description states both what the skill does AND when to use it, carries realistic trigger phrases, and names relevant file types when format-specific; judged by the cold CCVW audit (not a script) |
| 4 Tier | Frontmatter validity (claude-users+) | `quick_validate.py` exit 0 + `portability_lint.py` structural checks clean (name/folder/reserved/SKILL.md-spelling/no-frontmatter-tags/plan-code-leakage) |
| 4 Tier | Portability at declared tier | `portability_lint.py --tier <tier>` → no `tier_violations` (tier-specific portability violations), no `ccvw_mandatory_missing` (structural/name/folder/SKILL.md-spelling checks that apply at every shared tier) |
| 4 Tier | Attribution complete | `attribution_lint.py` → `would_fail_attribution_check: false` (an `{error}`-shaped exit 1 with no such key = HISTORY.md absent → degraded/backfill path, not a fail) |
| 4 Tier | Security | `security-checks.md` categories → no findings (or all addressed) |
| 4 Tier | Cowork-compat (claude-users+) | `cowork-compatibility.md` checks pass |
| 4 Tier | MCP-dependency declared (MCP skills only) | skill calling `mcp__<server>__*` declares the required server in README install + `metadata.mcp-server`; non-MCP skills skip |
| 6 README | Install + sibling sections filled | no remaining placeholder text in README |
| 7 Version | Version bumped + changelog appended | HISTORY.md has a new entry (unless degraded mode) |
| 9 PR | Ship tag `<skill>-v<version>` created + pushed | `github_pr.py` returns a `tag` field with no `tag_warning` (best-effort — a `tag_warning` is surfaced, not a ship-blocker) |

A skill is ship-ready when every applicable row passes. Personal-tier skills skip **all** Step-4 rows — including the frontmatter-validity gate — because a personal skill isn't distributed, so the publisher does no ship-time portability/structural/attribution/security/Cowork checking for it (the builder, skill-creator-ccvw, already validated structure at scaffold time). (Note: `portability_lint.py` itself *would* report the registration-correctness checks — name kebab-case + folder-match, reserved-prefix, `SKILL.md` spelling, XML-tag-shaped frontmatter, plan-code-leakage — as failing at every tier including `personal` if run; the publisher simply chooses not to run it for personal. At every **shared** tier those checks block and must pass.)

**On the description-quality row:** it is judged by the cold CCVW audit (Step 3), *not* wired as a deterministic script. `skill-creator-ccvw`'s `improve_description.py` is eval-output-driven (it runs trigger queries and rewrites against scores) — useful at build time, but the publisher doesn't run an eval loop at ship, so it can't be a pass/fail gate here. A weak description (missing WHEN, no trigger phrases, too vague/too technical, no file-type mention when format-specific) becomes an AUDIT cluster addressed FIX/STRENGTHEN/USER-PAUSE like any other. If the description is sound, there is no cluster and therefore no ledger row — `append_ledger.py` rows require a real finding's flag ID, which a no-finding re-validation does not have. Note "description re-validated for triggering" in your response text instead, and move on.

---

## Addressing findings (FIX / STRENGTHEN / USER-PAUSE)

Every AUDIT + TIER cluster gets exactly one address. The publisher and skill-tracer share the *same* FIX/STRENGTHEN/USER-PAUSE discipline — this is the publisher's authoritative local statement of it (no foreign step-number pin; the rule stands on its own here so a tracer renumber can't stale it):

**Bias toward FIX.** The default is to change the artifact so the finding disappears. A portability violation (hardcoded path) → rewrite the path. An audit GAP (missing pushy description) → rewrite the description. A security finding (hardcoded credential) → remove it.

**STRENGTHEN** (the exception) — when the artifact is correct and the finding reflects intent the checker couldn't see. Add a WHY at the point of use. Example: a portability lint flags a `~/.claude/` path, but the skill is explicitly `personal` tier and the path is intentional → STRENGTHEN by noting the tier-intentionality (though usually personal-tier skips Step 4 entirely, so this is rare).

**USER-PAUSE** — only when:
- A FIX would violate the README's stated `## Intent` (use `<target-intent>` to detect this). Example: the skill's intent says "prioritizes exhaustive re-scan over speed"; an efficiency-flavored audit finding suggests delta-tracking. That trades away stated intent → ask the user.
- Two plausible FIX paths exist and intent doesn't select between them.
- A security finding requires a design change whose blast radius the orchestrator can't scope.

**No orphan findings.** Every finding gets FIX/STRENGTHEN/USER-PAUSE — none deferred to an external log. The address lands in the skill (or the ledger row for USER-PAUSE).

**Exact address formats (required — the ledger renderer + next round parse these).** Write each cluster's Address column in the same format skill-tracer uses, so `render_ledger.py` and any re-read parse it:
- `FIX (<file>: <one-line summary of change>)`
- `STRENGTHEN (added at <file>:<line-range>: "<quoted first 80 chars>")`
- `USER-PAUSE (<one-line question naming the candidate paths>)`

Write rows with `scripts/append_ledger.py` (it rejects a literal `|` / embedded newline that would silently corrupt the row). When scripting several appends, invoke `python3` as the literal command word and put only the *paths* in quoted variables — never store the whole command in a shell variable, because zsh (a common default shell) does not word-split it, so the string becomes one bogus command name and fails with exit 127. These three formats are the shared contract with skill-tracer's `address-decision.md` — keep them identical so a skill traced then shipped has one consistent ledger format across both phases. (The vendored `append_ledger.py` *additionally accepts* the `would-FIX`/`would-STRENGTHEN`/`would-USER-PAUSE` family and counts them into the same tallies — those are skill-tracer's verify-only-mode addresses, retained because the script is byte-vendored for sync parity. The publisher never runs a verify-only pass and never writes a `would-*` address; its address contract is intentionally these three only.)

---

## Intent preservation

The publisher reads the target's README `## Intent` into `<target-intent>` at Step 1. Every FIX is checked against it: would this change trade away what the skill explicitly optimizes for? If yes → USER-PAUSE, not auto-FIX. This is why README's Intent section is load-bearing — it's the publisher's (and the tracer's) guard against "improvements" that violate the skill's design.

A skill with no README (or no Intent section) ships with a warning: "No documented Intent; ship-phase fixes will use the SKILL.md description as fallback intent — fixes may not preserve undocumented design trade-offs."
