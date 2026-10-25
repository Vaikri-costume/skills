# HISTORY.md Template

Every CCVW skill ships a `HISTORY.md` at its root. It holds provenance, lineage, and changelog — everything about WHERE the skill came from and HOW it evolved. This data used to live in SKILL.md frontmatter (`metadata.author`, `metadata.inspirations`, `metadata.version`); it moved out so SKILL.md frontmatter stays a lean runtime contract (only an at-a-glance copy of `parent-version` stays in SKILL.md `metadata`; the HISTORY.md value is authoritative), and so the skill-publisher has one authoritative place to read lineage from when shipping or generating a PR.

**Format: hybrid.** A YAML frontmatter block (machine-readable — `attribution_lint.py` and skill-publisher parse it) followed by a markdown changelog body (human-readable — the changelog and lineage notes).

---

## Template

```markdown
---
version: "1.0.0"                          # semver — the skill's current version
category: D                              # A (fork) / B (derivative) / C (inspiration) / D (independent)
parent-version: null                     # null for fresh skills; prior version string for evolved skills
author:
  primary: "<author-identity>"           # GitHub username preferred; never literal "user"
  history:                               # ONLY for Category A (forks); ordered oldest → newest
    - role: "original"
      name: "<original-author>"
      skill: "<source-skill-name>"
      version: "<source-version-at-fork>"
      license: "<SPDX-id>"
      source: "<source-url>"
    - role: "fork-adapter"
      name: "<author-identity>"
      date: "<ISO-date>"
      changes-summary: "<one-line summary of what the fork changed>"
inspirations:                            # Category B (derivatives), or a Category A fork that also borrows named patterns (combined shape in attribution-spec.md); empty list otherwise
  - skill: "<source-skill>"
    by: "<source-author>"
    pattern: "<one-line description of the borrowed pattern>"
---

# History — <skill-name>

## Changelog

### <version> — <ISO-date>
- <change>
- <change>

### <prior-version> — <ISO-date>
- <change>

## Lineage notes

<Free-form prose: where the skill came from, why it was forked/derived, design-trade-off
notes that don't belong in the changelog. For Category C (inspiration) skills, note the
"see also" source here even though it's also referenced in SKILL.md's References section.>
```

---

## Field rules

**`version`** (required) — semver. Fresh skills start at `1.0.0`. Bumped by skill-publisher at each ship (patch for fixes, minor for features, major for breaking changes).

**`category`** (required) — one of A/B/C/D per `attribution-spec.md`. Drives what attribution fields are required:
- A (fork) → `author.history[]` chain required + `LICENSE` file at skill root
- B (derivative) → `inspirations[]` required
- C (inspiration) → no YAML attribution; a "see also" reference in SKILL.md's References section (note it in Lineage notes here too)
- D (independent) → only `author.primary`

**`parent-version`** (required, may be `null`) — for evolved skills, the version this one descended from. `null` for fresh builds.

**`author.primary`** (required) — the current author's identity. GitHub username preferred. Never the literal word `"user"`, the phrase "the user" or the marker `AUTHOR-NOT-SET` in a shipped HISTORY.md: these are doc placeholders (the marker is what an eval worker writes, and the orchestrator replaces it in eval runs) (SKILL.md "Write the three root files").

**`author.history[]`** (Category A only) — the fork chain, oldest → newest. Each entry: `role` (exactly one of original / fork-adapter / heavy-revision; the set is closed, per `references/attribution-spec.md` "Author and history (used for Category A skills)"), `name`, and for `original`: `skill` + `version` + `license` + `source`; for adapters: `date` + `changes-summary`.

**`inspirations[]`** (Category B, or a Category A fork that also borrows named patterns, as in the combined shape in `attribution-spec.md`) — borrowed named patterns. Each: `skill` + `by` + `pattern`.

**Changelog body** — newest entry first. Each entry: version + date + bulleted changes. skill-publisher appends a new entry at each ship.

**Lineage notes** — free-form provenance prose. Optional but recommended for forks/derivatives. Required for a skill built on the adapt path (SKILL.md "Path 3, adapt") in Category B or C, which have no YAML field for the source URL and licence: write one line per source, after the `checked-marketplace:` line and a blank line, in the shape `Adapted from: <source-skill>, <licence>, <source-url>; took: <idea or pattern>; changed: <what differs>`. A Category A fork carries the source and licence in `author.history[]` and the changes in `changes-summary`, so it needs no such line.

---

## Why this lives outside SKILL.md frontmatter

1. **SKILL.md frontmatter stays a runtime contract.** The executor agent loads frontmatter at startup; it only needs `name`, `description`, `license`, `compatibility`, `allowed-tools`, `metadata.tier`, `metadata.intended-audience`, `metadata.created`, `metadata.created-by`, and the at-a-glance copy `metadata.parent-version` (HISTORY.md holds the authoritative one). Lineage/version/attribution aren't runtime concerns.
2. **skill-publisher has one authoritative source.** When generating a GitHub PR or version-bumping, the publisher reads HISTORY.md — not scattered frontmatter fields.
3. **Changelog has room to grow.** A markdown changelog body can hold many entries without bloating the frontmatter the executor parses every invocation.
