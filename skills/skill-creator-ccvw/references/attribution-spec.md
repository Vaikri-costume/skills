# CCVW Attribution Specification

Defines the four attribution categories, the structural thresholds that decide which category a skill falls into, the schema for recording attribution, and the courtesy bar for pattern citation. This is the source of truth for `attribution_lint.py`.

**Where attribution lives:** as of the three-skill ecosystem refactor, machine-readable attribution lives in **`HISTORY.md`'s YAML frontmatter** (top-level `category`, `author`, `inspirations` fields) — NOT in SKILL.md's `metadata`. **The YAML examples below are HISTORY.md frontmatter** — `author:`, `inspirations:`, and `category:` are top-level keys with **no `metadata:` wrapper**; copy them into HISTORY.md as-is. See `history-template.md` for the full HISTORY.md format. Category C "see also" references still live in SKILL.md's References section (prose, human-facing). `attribution_lint.py` reads HISTORY.md for the machine-readable fields and SKILL.md's body for the see-also advisory check.

The default bias: **over-attribute when in doubt**. The cost of one extra "see also" is small; missing attribution when you should have credited someone else's work is a larger failure.

---

## The four attribution categories

Every CCVW skill falls into exactly one category. The category drives what attribution is required.

| Category | Definition (threshold) | Attribution required | Where it lives |
|---|---|---|---|
| **A. Direct fork** | The new skill's SKILL.md retains ≥50% of the original's structure (sections, headings, step numbers, flow), OR ≥25% of script lines are unchanged from the original, OR the original's references/templates are kept largely intact. | **Original author + original license preserved + change-log of YOUR contributions.** | `author.history[]` chain in HISTORY.md frontmatter + preserved `LICENSE` file at skill root |
| **B. Derivative work** | You took a recognizable, named design pattern from another skill and rewrote the implementation substantially. SKILL.md prose and code are yours; the pattern (e.g., cold-parallel three-agent dispatch, ralph-loop while-true convergence) is borrowed. | **Inspirations cited with pattern name + source skill + author.** You are the primary author. | `inspirations[]` array in HISTORY.md frontmatter |
| **C. Idea inspiration** | You read someone's skill and a general idea stuck (e.g., "scan → quality-report → targeted-update pattern"). No structural overlap; no named-pattern adoption. | **"See also" reference in the References section at the end of SKILL.md.** No frontmatter metadata addition required. | Prose-level pointer in the References section |
| **D. Independent design** | Built from scratch; no recognizable lift. | No external attribution needed. | HISTORY.md `author.primary = "<your-author-identity>"` |

---

## How to decide between categories — the squishy lines

### Fork (A) vs. derivative (B)

The line between A and B is structural similarity. If you can `diff` your SKILL.md against the original and:

- **≥50% of lines unchanged** → A (direct fork). Even if you've added significant new content, the original is structurally present.
- **<50% unchanged but SECTION STRUCTURE recognizably matches** (same step numbers, same role names, same workflow shape) → A. The structural fingerprint is the original's; you've evolved the prose.
- **Structure differs but the underlying design PATTERN is recognizably the original's distinctive contribution** (e.g., cold-parallel three-agent dispatch is recognizable as skill-tracer's pattern even when implemented differently) → B (derivative).

When in doubt between A and B, choose A — preserving the LICENSE and history is the conservative call.

### Derivative (B) vs. inspiration (C)

The line between B and C is named-pattern adoption.

- **Pattern has a named originator** (deep-research's adversarial-verify, ralph-loop's while-true loop, pr-review-toolkit's decomposed-reviewer model, skill-tracer's cold-parallel dispatch) → B. Attribute in HISTORY.md `inspirations[]`.
- **Pattern is a general approach you arrived at after reading someone's skill** but you can't point at a single source skill that "owns" the pattern → C. "See also" reference in the References section.

When in doubt between B and C, choose B — explicit `inspirations[]` entry costs nothing and makes the lineage clear.

### Inspiration (C) vs. independent (D)

The line between C and D is whether anyone could plausibly recognize your design as derivative of someone else's.

- **You can name a source skill** whose existence influenced yours — even loosely → C. "See also" reference.
- **You arrived at the same approach independently, and the approach is generic enough that you couldn't credibly claim it traces to one source** (e.g., a workflow with a "review" step — most skills have review steps) → D. No attribution.

When in doubt between C and D, choose C — one extra reference is cheap; the cost of failing to acknowledge an influence you actually had is larger.

### What does NOT need attribution (the "generic CS patterns" exception)

The following are considered common knowledge in skill design and don't require attribution to anyone:

- **Generic programming patterns**: caching, retry-with-backoff, queue, batch processing, parallelism (in general), idempotency, retry-on-failure
- **Generic workflow steps**: read → process → write, validate → execute → report, iterate-with-feedback
- **Generic file structure**: SKILL.md + references/ + scripts/ — this IS the agentskills.io standard; everyone uses it
- **Generic conventions**: YAML frontmatter, markdown bodies, kebab-case naming

The threshold for "needs attribution": is this someone's DISTINCTIVE contribution or common knowledge? If you'd find the pattern in a CS textbook or in the agentskills.io baseline spec, it's common knowledge and no attribution needed. If you can point at the specific skill/person who originated it as a recognizable named pattern, attribute.

---

## Frontmatter schema

### Author and history (used for Category A skills)

```yaml
author:
    primary: "<your-author-identity>"          # who's responsible for the current version — see "Author identity values" below
    history:                                   # chain of derivation; ordered oldest → newest
      - role: "original"                       # roles: original / fork-adapter / heavy-revision
        name: "Anthropic"                      # author name of the original
        skill: "skill-creator"                 # source skill name
        version: "1.0.0"                       # source version at fork time
        license: "MIT"                         # source license (SPDX identifier)
        source: "https://github.com/anthropics/skills"  # source URL if available
      - role: "fork-adapter"
        name: "<your-author-identity>"
        date: "2026-05-27"                     # ISO date of the adaptation
        changes-summary: "Centralized eval output location to ~/.claude/skill-creator-evals-ledger/<skill>/ instead of beside the target skill."
```

Multiple `fork-adapter` or `heavy-revision` entries can chain if the skill has been evolved multiple times. The newest entry is the current adapter's edit; the oldest is always `role: original`.

### Author identity values

HISTORY.md `author.primary` and the `name` field in any `history` or `inspirations` entry must be the **actual identity** of the author — typically a GitHub username (preferred for OSS-style attribution), or another stable identifier the author uses for credit. Do **not** write the literal word `"user"` — that's a placeholder used in spec documentation only, never a real value.

- For skills the current author is building or evolving: their actual GitHub username (e.g., `"Vaikri-costume"`).
- For the `original` entry in a fork's history chain: the original author's published identity (e.g., `"Anthropic"`, or a GitHub handle if the original was a community skill).
- If someone else later uses skill-creator-ccvw to build their own skills, they set HISTORY.md `author.primary` to THEIR identity (not the identity of whoever built skill-creator-ccvw). Skill-creator-ccvw itself can be cited as a tool dependency in `inspirations[]` if the user wants to credit the builder, but that's optional — a tool you used isn't required attribution the way a forked or pattern-borrowed skill is.

skill-creator-ccvw's "Step 3 — Author identity" in the SKILL.md asks the user once for their identity and persists it via `productivity:memory-management` so subsequent scaffolds don't re-ask.

### Inspirations (used for Category B skills)

```yaml
author:
    primary: "<your-author-identity>"
inspirations:
    - skill: "deep-research"
      by: "Anthropic"
      pattern: "Adversarial-verify cold-parallel dispatch — independent agents commit to claims before seeing peers' findings"
    - skill: "ralph-loop"
      by: "Anthropic"
      pattern: "While-true inline convergence loop — orchestrator-internal iteration with cold child dispatches"
```

Each entry: source skill name, source author, one-line description of the pattern borrowed.

### Combined (Category A AND B — a fork that also borrows additional patterns)

A fork can also use patterns from other skills outside the fork chain. Both fields populate independently:

```yaml
author:
    primary: "<your-author-identity>"
    history: [...]      # the fork chain
inspirations: [...]   # additional patterns borrowed from non-ancestor skills
```

### Category C (see-also references)

No frontmatter addition required. The reference lives at the END of SKILL.md in a `## References` (or `## See also`) section:

```markdown
## References

- `references/glossary.md` — skill-specific terms
- See also: `claude-md-improver` (in claude-md-management plugin) — same scan → quality-report → targeted-update pattern applied to CLAUDE.md files
```

### Category D (independent)

Only the primary author is required:

```yaml
author:
    primary: "<your-author-identity>"
```

No `history` field, no `inspirations` field, no extra prose pointers.

---

## License preservation (required for Category A)

When the original was licensed (MIT, Apache, BSD, GPL, etc.), the original LICENSE file must be preserved verbatim at the new skill's root. Add your own copyright notice to the LICENSE file if you've made substantial contributions; don't replace the original.

- **MIT**: preserve the original copyright line; add yours: `Copyright (c) <year> <your-author-identity>` (your actual GitHub username / attribution name — never the literal word `user`, per the author-identity rule above).
- **Apache 2.0**: preserve LICENSE; if the original had a NOTICE file, preserve and extend it.
- **BSD**: preserve the original copyright; add yours.
- **GPL / AGPL**: your derivative inherits the same license; preserve LICENSE; you cannot relicense.
- **Public domain / CC0**: no preservation required but courtesy attribution in HISTORY.md `author.history` is still expected.

When unsure of the original's license, check the source repo's LICENSE file or fall back to the original author's stated terms in the SKILL.md frontmatter.

---

## Auto-population from marketplace-discover

When the user installs a skill via marketplace-discover and later evolves it (per `improve-existing-skill.md`), skill-creator-ccvw pre-populates HISTORY.md `author.history` with the original entry derived from the marketplace catalog data:

- `name` = original's `author.name` field from the catalog entry
- `skill` = original's `name`
- `version` = current installed version (from the catalog `source.ref` field)
- `license` = the LICENSE file at the original's skill root, parsed
- `source` = `source.url[#source.ref]` from the catalog

The user reviews the auto-populated chain and confirms before scaffolding proceeds. If the catalog data is incomplete, the user fills the gaps manually.

---

## Worked examples per category

### Category A example — skill-creator-ccvw (fork of skill-creator)

```yaml
author:
    primary: "Vaikri-costume"
    history:
      - role: "original"
        name: "Anthropic"
        skill: "skill-creator"
        version: "1.0.0"
        license: "MIT"
        source: "https://github.com/anthropics/skills/tree/main/plugins/skill-creator"
      - role: "fork-adapter"
        name: "Vaikri-costume"
        date: "2026-05-27"
        changes-summary: "Centralized eval output location to ~/.claude/skill-creator-evals-ledger/<skill>/; added portable-mode tier system; added attribution framework; added marketplace-discover pre-check."
```

LICENSE file preserved verbatim from skill-creator with the adapter's copyright line appended.

### Category B example — a new skill that uses cold-parallel three-agent dispatch

```yaml
author:
    primary: "<your-author-identity>"
inspirations:
    - skill: "skill-tracer"
      by: "Vaikri-costume"
      pattern: "Cold-parallel three-agent dispatch — three independent agents reading the same target from different directions, prompts staged before dispatch, all dispatches issued same-turn to preserve independence."
```

### Category C example — a skill that uses scan→quality-report→targeted-update workflow

```markdown
## References

- `references/glossary.md` — skill-specific terms
- See also: `claude-md-improver` (in claude-md-management plugin) — same scan → quality-report → targeted-update workflow, applied to CLAUDE.md files instead.
```

No metadata addition. The reference at the end of SKILL.md is sufficient.

### Category D example — a skill built from scratch

```yaml
author:
    primary: "<your-author-identity>"
```

No `history`, no `inspirations`, no pattern attribution. The skill is independent design.

---

## Lint output schema

`attribution_lint.py` emits:

```json
{
  "skill_path": "/absolute/path/to/skill",
  "declared_category": "A | B | C | D | unknown",
  "primary_author": "user | <name> | missing",
  "history_chain_length": 2,
  "inspirations_count": 0,
  "license_file_present": true,
  "violations": [
    {"type": "missing-license-file", "message": "history[] declares original but LICENSE file is absent at skill root", "severity": "blocking"},
    {"type": "inspiration-incomplete", "message": "inspirations[2] is missing the `pattern` field", "severity": "blocking"},
    {"type": "see-also-without-reference", "message": "skill body mentions a CCVW pattern with no see-also reference in References section", "severity": "advisory"}
  ],
  "would_fail_attribution_check": true
}
```

The orchestrator (skill-creator-ccvw during scaffolding, skill-publisher during Step 4 tier-transition checks) consumes this JSON to render user-facing warnings, propose fixes, or flag GAP entries. A `declared_category` of `unknown` means HISTORY.md's `author` field exists but is **not a mapping** (e.g. a bare string), so no category could be inferred — the consumer treats it as a blocking attribution error (populate a well-formed `author` block plus an explicit A/B/C/D category), not a fifth valid category to accept. (A wholly *missing* `author` key instead infers category **D** and emits a `missing-primary-author` blocking violation — also fix-before-handoff. `infer_category` does `author = fm.get("author", {})`, so a missing key becomes `{}`, a dict, and falls through to shape inference → `D`; only a present-but-non-dict `author` yields `unknown`.)
