# CCVW Skill Structure Specification

The complete required structure for every CCVW skill — frontmatter fields, required directories, required reference files, and license-file rules. The orchestrator scaffolds new skills against this spec; `portability_lint.py` enforces it; skill-tracer audits against it.

Companion specs:
- `portability-spec.md` — per-tier portability rules, Claude-extension blocklist, path-mapping
- `attribution-spec.md` — four-category attribution framework, license preservation rules
- `readme-template.md` — required README.md sections
- `history-template.md` — HISTORY.md hybrid format (provenance + changelog)

---

## Three mandatory root files (SKILL.md / README.md / HISTORY.md)

As of the three-skill ecosystem refactor (build → trace → ship), every CCVW skill ships **three** root markdown files, each with a distinct audience:

| File | Audience | Holds |
|---|---|---|
| **`SKILL.md`** | the executor agent (runtime) | the workflow + a lean frontmatter runtime contract |
| **`README.md`** | humans + skill-tracer's orchestrator | intent, what-it-does, how-to-install, sibling skills (`## Intent` is what tracer reads for considered-fix) |
| **`HISTORY.md`** | skill-publisher + humans | provenance, attribution chain, version, changelog (hybrid YAML frontmatter + markdown body) |

The split keeps SKILL.md frontmatter minimal (only what the executor loads at startup), gives humans a real README, and gives the publisher one authoritative place to read lineage from. README.md required sections: see `readme-template.md`. HISTORY.md format: see `history-template.md`.

---

## Required SKILL.md frontmatter fields (runtime contract only)

SKILL.md frontmatter holds ONLY what the executor agent loads at startup. Lineage/version/attribution moved to HISTORY.md.

> **Parser-convergence note.** Several scripts parse this frontmatter independently — `scripts/utils.py` (`parse_skill_md`), `scripts/quick_validate.py` (PyYAML, strict-validation), and `scripts/portability_lint.py` (bespoke nested parser for tier checks) — each for a different need, so they are deliberately NOT a single shared parser. They MUST agree on `name` + `description` extraction (verified: they currently produce identical results for single-line values). One known exception to verify: **YAML block-scalar descriptions** (`description: |` or `description: >`). `utils.py` handles them explicitly (joins continuation lines); `portability_lint.py`'s bespoke parser currently stores the bare `|` / `>` literal. Avoid block-scalar descriptions in SKILL.md frontmatter — use a single quoted line instead, or verify portability_lint sees the full text. If you change any one parser's frontmatter handling, re-check the others against the same SKILL.md — a divergence here is silent (one gate would accept what another rejects). Quick divergence check: parse the same SKILL.md through all three and assert equal `name`/`description`.

- **`name`** — skill identifier. 1–64 chars, lowercase alphanumeric + hyphens. Used in install commands and slash-command paths.
- **`description`** — when to trigger + what it does. The primary triggering mechanism. Include both, including specific trigger contexts; all "when to use" lives here, not in the body. Lean pushy — Claude under-triggers. Mention the relevant **file types/extensions** when the skill operates on specific formats (`.pdf`, `.xlsx`, `.fig`) — they are strong trigger signals. Add a **negative/exclusion clause** when the skill is prone to over-triggering against a near-neighbor (*"Do NOT use for [X] — use [other-skill] instead"*) so Claude knows the boundary, not just the target. Example: *"How to build a fast dashboard. Use whenever the user mentions dashboards, data visualization, internal metrics, or wants to display any kind of data, even if they don't explicitly ask for a 'dashboard.'"* (Tuning levers — under/over-trigger remedies, the manual probe, post-deploy re-tuning — are in the build SKILL.md "Triggering signals from real use".)
- **`license`** — SPDX identifier (`MIT`, `Apache-2.0`, `BSD-3-Clause`, `CC0-1.0`, etc.). Default: `MIT`. For Category A (direct fork) skills, see `attribution-spec.md` for per-category preservation rules.
- **`compatibility`** — runtime requirement, as readable prose. Personal/claude-users: typically `Claude Code 2.0 or newer` (avoid bare `<`/`>` version operators — they're a tag-shaped prompt-injection surface in frontmatter; write the constraint in words. Note: this is advisory — neither `quick_validate.py` nor `portability_lint.py` enforces the absence of bare operators in the compatibility field, so violating this advisory would not be caught by the lints). Model-agnostic: MUST include `agentskills.io@<version>` (e.g., `agentskills.io@1.0`) — see `portability-spec.md`.
- **`metadata`** — required object. Required keys (runtime-relevant only):
  - `tier`: `personal` / `claude-users` / `model-agnostic`
  - `created`: ISO-8601 timestamp when scaffolded
  - `created-by`: typically `skill-creator-ccvw`; can be `user` for hand-authored
  - `parent-version`: `null` for fresh skills; `<prior version>` for evolved (this duplicates HISTORY.md's `parent-version` for at-a-glance runtime visibility; HISTORY.md is the authoritative source)
  - `intended-audience`: matches `tier` triplet (`personal` / `claude-users` / `model-agnostic`); default `claude-users`. Personal is the exception, not the default.
- **`allowed-tools`** — array of tool names the skill is permitted to invoke. Default conservative set: `["Read"]` for read-only skills; broaden per skill needs (`Bash`, `Edit`, `Write`, `Skill`, etc.). Model-agnostic restrictions: see `portability-spec.md`.

**Moved to HISTORY.md** (no longer in SKILL.md frontmatter): `version`, `author` (primary + history chain), `inspirations`, `category`, `checked-marketplace`. See `history-template.md`.

---

## Required directories

Every CCVW skill ships with all three directories. `.gitkeep` placeholders are OK when a directory has no files yet — the structure must be uniform so downstream tooling can predict layout.

- `scripts/` — executable code the skill invokes
- `references/` — supporting documentation; the per-skill `glossary.md` lives here
- `assets/` — templates, schemas, images, prompts

---

## Required reference files

- **`references/glossary.md`** — every CCVW skill ships a glossary. Scaffolded from `~/.claude/skills/skill-creator-ccvw/references/glossary-template.md`. Inherits the CCVW shared vocabulary from `~/.claude/skills/skill-creator-ccvw/references/ccvw-glossary.md` (cluster, FIX, STRENGTHEN, in-flight marker, Round, Phase, ledger, cold-trace, tier, etc.) and adds skill-specific terms. When skill-tracer later audits this skill, its Step 3 reads this glossary first instead of deriving terms cold — keeps definitions stable across rounds.

---

## Scaffold-time structural rules (enforced by portability_lint.py at every tier)

These hold at **every** tier — they are registration-correctness, not tier-portability. A malformed name or a misnamed main file breaks skill discovery on any runtime (Claude Code, Claude.ai, agentskills.io), so `portability_lint.py` blocks them even at `personal`:

| Rule | Violation type | Why |
|---|---|---|
| `name` is kebab-case (lowercase alphanumeric + single hyphens; no leading/trailing/double hyphen) | `name-format` | The loader and slash-command path require it; `My_Skill` is rejected on upload |
| `name` equals the skill folder basename | `name-folder-mismatch` | Install commands and discovery key off the folder; a mismatch silently loads the wrong identity |
| `name` does not start with `claude`/`anthropic` (e.g. `claude-x`, `anthropic_y`) | `reserved-name` | Those prefixes are reserved; upload rejects them |
| Main file is named exactly `SKILL.md` (case-sensitive) | `skill-md-misnamed` | The loader matches the exact byte-name. The diagnostic compares real directory entries, so it catches `Skill.md`/`skill.md` **even on macOS's case-insensitive filesystem** (where a naive path check would falsely pass). Rename via a two-step `mv` on macOS |
| No XML-tag-shaped `<...>` content anywhere in frontmatter | `frontmatter-angle-bracket` | Frontmatter is injected into the system prompt, so a literal `<tag>` is a prompt-injection surface. Tag-SHAPED only — version operators (`>=2.0`, `<3.0`) are legitimate and never flagged. Use `[placeholder]` brackets for placeholders |
| `description` ≤ 1024 chars | `description-too-long` | Hard limit; the description is the always-loaded triggering signal |
| `compatibility` is 1–500 chars | `compatibility-length` | Documented bound |

`quick_validate.py` is the companion fast gate (frontmatter parse + the `name`/`description`/`compatibility` content rules + allowed-key check); run it first at scaffold so a malformed-YAML frontmatter surfaces before the richer lints run. See the build SKILL.md "Scaffold-time lint checks" step for the invocation order.

---

## License file at skill root

Required when the skill is Category A (direct fork — HISTORY.md `author.history[]` has an `original` entry). The original's LICENSE file is preserved verbatim; the user's copyright line is appended for substantial contributions. Full per-license preservation rules in `attribution-spec.md`.

For Category B/C/D skills, a LICENSE file is recommended but not required — defaults to the SPDX identifier in the **top-level `license` frontmatter field** (a sibling of `name`/`description`/`metadata`, NOT a key inside `metadata`).

---

## Anatomy of a CCVW skill (visual)

```
skill-name/
├── SKILL.md (required)   — runtime workflow
│   ├── YAML frontmatter (name, description, license, compatibility, metadata, allowed-tools — runtime contract only)
│   └── Markdown instructions
├── README.md (required)  — human intent + how-to-install + sibling skills (## Intent = tracer's considered-fix input)
├── HISTORY.md (required) — provenance + attribution chain + version + changelog (hybrid YAML+md)
├── scripts/    — executable code for deterministic/repetitive tasks
├── references/ — docs loaded into context as needed (glossary.md is mandatory)
├── assets/     — files used in output (templates, icons, prompts, schemas)
└── LICENSE     — required for Category A forks; recommended otherwise
```
