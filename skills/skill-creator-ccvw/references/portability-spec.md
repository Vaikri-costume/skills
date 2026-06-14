# CCVW Portability Specification

Defines the three portability tiers, the agentskills.io base spec CCVW skills inherit, the Claude-extension blocklist for model-agnostic portability, the CCVW-mandatory fields (lifted above agentskills.io's optional baseline), and the path-mapping rules per tier. This is the source of truth for `portability_lint.py` — run by skill-creator-ccvw at scaffold/tier-transition and by skill-publisher's Step 4 tier-transition checks at ship time. (Pre-refactor this was skill-tracer's Step 9 portability audit; it moved to the publisher when the tracer slimmed to correctness-only.)

---

## Portability tiers

CCVW skills declare their tier in `metadata.tier` in frontmatter. Three tiers in increasing portability:

| Tier | Use case | Allowed | Disallowed | Default for |
|---|---|---|---|---|
| **`personal`** | User-specific iteration; OK to bake in personal paths, MCP servers, hardcoded CCVW conventions | All Claude extensions; CCVW conventions; hardcoded `~/.claude/...` paths; productivity:* MCP integrations; assumed local environment | Nothing additional | Skills during iteration; default flag for new builds |
| **`claude-users`** | Skills shared with friends/family/coworkers on their own Claude Code installs | All Claude extensions; tier-portable paths (e.g. `$XDG_DATA_HOME/...`); CCVW conventions where they don't depend on personal MCP | Hardcoded `~/.claude/...` user-specific paths; productivity:* MCP without graceful-degradation fallback; assumed-installed personal skills | Skills marked ready-to-share |
| **`model-agnostic`** | Skills portable to Gemini CLI, Cursor, OpenCode, any agentskills.io-compatible runtime | Only agentskills.io base spec; pure-stdlib scripts; runtime-provided storage API | All Claude extensions (see blocklist below); claude-users-tier-allowed hardcoded paths; any Claude-Code-specific tool name | Skills explicitly tagged for model-agnostic publication |

---

## agentskills.io base spec (model-agnostic tier requirement, optional for claude-users/personal)

A skill conforming to agentskills.io is a directory containing at minimum a `SKILL.md` with YAML frontmatter:

| Field | Type | Required by agentskills.io | Required by CCVW (any tier) |
|---|---|---|---|
| `name` | string, 1-64 chars, lowercase alphanumeric + hyphens | ✓ | ✓ |
| `description` | string, ≤1024 chars | ✓ | ✓ |
| `license` | string (SPDX identifier or URL) | ✗ | **✓** |
| `compatibility` | string (`agentskills.io@<version>` for model-agnostic; runtime version range for claude-users) | ✗ | **✓** |
| `metadata` | object | ✗ | **✓** |
| `allowed-tools` | array of strings | ✗ (experimental in agentskills.io) | **✓** |

Optional directories at the skill root (CCVW requires all three exist, empty `.gitkeep` placeholders allowed):

| Directory | agentskills.io | CCVW (any tier) | Use |
|---|---|---|---|
| `scripts/` | optional | **required** | Executable code the skill invokes (Python, shell, etc.) |
| `references/` | optional | **required** | Supporting documentation; per-skill `glossary.md` lives here (CCVW requires every skill to ship a glossary) |
| `assets/` | optional | **required** | Templates, prompts, images, schema files |

Progressive disclosure budgets (advisory at all tiers, enforced at model-agnostic):
- Metadata budget: ~100 tokens (`name` + `description` + frontmatter, what the agent loads at startup)
- SKILL.md body: <5000 tokens recommended
- Referenced files: loaded on-demand

---

## CCVW-mandatory section (tier-independent)

CCVW elevates several agentskills.io-optional items to required for every CCVW skill regardless of tier. These apply at every tier including personal. `portability_lint.py` reports `ccvw_mandatory_missing` whenever any are absent.

**Frontmatter fields (required for all CCVW skills):**
- `license` — defaults to `MIT` when scaffolded; user can change.
- `compatibility` — defaults to current detected Claude Code version; for model-agnostic tier, must be `agentskills.io@1.0` or higher.
- `metadata` — required keys: `tier` (one of personal/claude-users/model-agnostic), `created` (Runtime when scaffolded), `created-by` (defaults `skill-creator-ccvw`), `parent-version` (null for fresh skills, prior version string for evolved skills), `intended-audience` (matches `tier` values: `personal` / `claude-users` / `model-agnostic`; default `claude-users` since the skill is intended to be shareable on Claude Code + Cowork by default; personal is the exception. `tier` and `intended-audience` are technically separate (tier is portability state; audience is intent) but the values map 1:1 and default the same).
- `allowed-tools` — required, even if conservative; CCVW default is `["Read"]` for read-only skills, broadened per skill needs.

**Directories (required to exist, empty allowed):**
- `scripts/` (with `.gitkeep` if no scripts yet)
- `references/` (always at least `glossary.md` — the per-skill glossary is itself CCVW-mandatory)
- `assets/` (with `.gitkeep` if no assets yet)

---

## Claude-extension blocklist (model-agnostic tier disallows; claude-users tier warns; personal tier allows)

The following Claude-specific features in SKILL.md will NOT work on non-Claude runtimes. `portability_lint.py --tier model-agnostic` flags every occurrence with a suggested-fix.

| Feature | What to do under model-agnostic tier |
|---|---|
| `disable-model-invocation` frontmatter field | Strip; restructure trigger description to convey intent in prose |
| `user-invocable: false` frontmatter field | Strip; restructure trigger description |
| `context: fork` frontmatter | Strip; design without isolated subagent execution |
| `agent:` frontmatter field | Strip; rewrite as direct-execution skill |
| `` !`command` `` dynamic shell injection in SKILL.md body | Strip; replace with instruction text directing the agent to run the command itself |
| `$ARGUMENTS[N]`, `$0`, named-argument substitution | Strip; use a single positional argument or natural-language arg parsing |
| `${CLAUDE_SESSION_ID}` substitution | Strip; use runtime-provided session ID or generate one if needed |
| `paths:` glob restriction in frontmatter | Strip; document path-applicability in description prose |
| `allowed-tools` with Claude-Code-specific tool names (e.g. `Agent`, `WebFetch`, `mcp__*__*`) | Strip Claude-only tools; keep standard ones (Read, Bash, Edit, Write); document missing-tool fallback |
| `Agent` tool dispatch in body | Major restructure required — agent dispatch is Claude-specific; design as single-actor skill or document the dispatch as "agent-internal" so it falls within the runtime's own subagent model |

---

## Path-mapping rules per tier

CCVW skills today hardcode `~/.claude/...` paths. These are not portable. The lint script flags each and proposes a tier-appropriate rewrite.

Two distinct path categories matter here:

**User-data paths** (block at claude-users+ — every Claude Code user has these locations, but with different content; your ledger isn't my ledger, your memory isn't my memory):

| User-data path | Shipped tier rewrite | Cross-runtime tier rewrite |
|---|---|---|
| `~/.claude/skill-tracer-audit-ledger/<skill>.md` | `$XDG_DATA_HOME/skill-tracer-audit-ledger/<skill>.md` (with fallback `~/.local/share/skill-tracer-audit-ledger/<skill>.md` on systems without XDG) | Runtime-provided per-skill storage API (e.g., `runtime.storage("audit-ledger").get(skill)`) |
| `~/.claude/skill-creator-evals-ledger/<skill>/` | `$XDG_DATA_HOME/skill-creator-evals-ledger/<skill>/` | Runtime-provided per-skill storage API |
| `~/.claude/CLAUDE.md` (user memory) | `$XDG_CONFIG_HOME/claude/CLAUDE.md` with fallback | Runtime-provided user-memory API |
| `~/.claude/memory/` | `$XDG_DATA_HOME/claude/memory/` | Runtime-provided memory API |
| `/tmp/skill-tracer-prompts/*` (scratchpad) | OK at claude-users tier (POSIX standard) | use runtime-provided tempdir API or `tempfile.mkdtemp()` |

**Claude-Code-system paths** (block at model-agnostic only — every Claude Code user has these paths AND the same content at them, so a skill referencing them works across Claude Code installs; non-Claude runtimes don't have these paths at all):

| Claude-Code-system path | Shipped tier handling | Cross-runtime tier rewrite |
|---|---|---|
| `~/.claude/plugins/marketplaces/...` | OK at claude-users — every Claude Code user has the same marketplace | Feature disabled with clear "this skill needs the Claude Code marketplace; not available on this runtime" message |
| `~/.claude/projects/<encoded-cwd>/*.jsonl` (session JSONLs) | OK at claude-users — every Claude Code user has session JSONLs at this path | Use runtime-provided session API; document as Claude-only on non-Claude runtimes |
| `~/.claude/skills/<dep-skill>/SKILL.md` (cross-skill dependency) | OK at claude-users if the dep is also a claude-users skill the user has installed | Use skill-discovery API (`runtime.skills.find("<dep-skill>")`) |

---

## Personalization rules (cats 15-16 — absorbed from skill-tracer accessibility direction)

A skill that leaks the author's identity or references internal planning artifacts isn't cleanly shareable. These two checks (originally skill-tracer accessibility categories 15 and 16) are enforced by `portability_lint.py`.

### Cat 15 — author-identity / personalization leakage (blocks at claude-users+)

The skill body mentions a specific person's name, hardcodes a username, or uses first-person personal framing ("I built this for", "my personal", "for my own use") in content that ships with the skill. A new installer who isn't that person is confused by it.

- **At `personal` tier**: allowed (it's your own skill; reference yourself freely).
- **At `claude-users` and `model-agnostic` tiers**: flagged. The orchestrator prompts to anonymize — replace the author's name with "the user" / "you", or drop the personal reference. Replacement is user-confirmed, never silent.

The lint flags two things: (a) generic personalization phrasings (the patterns above), and (b) the author's exact name/username if passed via `--author` or read from HISTORY.md `author.primary`.

### Cat 16 — plan-document / decision-code references (flagged at ALL tiers)

The skill body references internal planning notation that doesn't ship with the skill: `(per D5)`, `per the plan`, `per the original feedback`, `per the decision in section X`, `see the plan-doc`. A reader with only the installed skill (no plan file, no decision log) sees these as unresolvable referents.

Flagged at **every tier including personal** — even the author's future self loses the plan-doc context once the build session ends. The fix is to rewrite the reference as standalone prose conveying the actual meaning without the internal pointer.

These checks run at scaffold time and at every tier transition. skill-creator-ccvw surfaces them during the build; skill-publisher re-checks at ship time.

---

## agentskills.io version attribution (model-agnostic requirement)

Cross-runtime tier MUST include in frontmatter:

```yaml
compatibility: agentskills.io@1.0
```

This is the explicit signal for non-Claude runtimes consuming the agentskills.io compatibility field — it tells the receiving runtime which version of the base spec the skill was authored against, enabling runtime-side compat handling.

Personal and claude-users tiers MAY include this; if absent, the runtime defaults to "Claude Code extensions assumed."

---

## Lint output schema

`portability_lint.py` emits:

```json
{
  "skill_path": "/absolute/path/to/skill",
  "declared_tier": "personal | claude-users | model-agnostic",
  "ccvw_mandatory_missing": ["license", "scripts/", ...],
  "tier_violations": [
    {"line": 14, "type": "claude-extension", "message": "$ARGUMENTS[0] used", "suggested_fix": "Use single-arg positional", "blocks_tier": "model-agnostic"}
  ],
  "would_fail_at_tiers": ["claude-users", "model-agnostic"]
}
```

The orchestrator (skill-creator-ccvw during authoring, skill-publisher during Step 4 tier-transition checks) consumes this JSON to render user-facing warnings, propose fixes, or flag GAP entries.
