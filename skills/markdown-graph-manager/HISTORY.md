---
version: "1.3.0"
category: D
parent-version: "1.2.4"
author:
  primary: "Vaikri-costume"
  history:
    - role: "original"
      name: "Vaikri-costume"
      skill: "markdown-graph-manager"
      license: "MIT"
      version: "1.0.0"
      date: "2026-08-11"
      source: "https://github.com/Vaikri-costume/skills"
inspirations: []
---

# History — markdown-graph-manager

## Changelog

### 1.3.0 — 2026-10-04 (shipped)
#### Changed
- Polish pass over `SKILL.md` and `README.md`: condensed the bold-strip ordering-trap rule to one canonical statement, trimmed Step -1 and the write-rules checklist wording, removed Troubleshooting rows that duplicated body rules, and removed duplicate trigger/script lists from the README. README `## Features & modes` and `## Structure` regenerated from the final `SKILL.md`.
- `SKILL.md` now names the shipped sample configs (`assets/example-graphs.json`, `assets/example-schema.json`) and gives an Expected-output line for graph resolution and `audit`.
- `evals/evals.json`: the eval fixture path is now `/tmp/mgm-eval-fixture` instead of a machine-specific scratch path. `evals/trigger-eval-set.json` moved out of the skill tree to the CCVW evals ledger (`skill-creator-evals-ledger/markdown-graph-manager/trigger-opt/`).
- `references/layers/apple-notes.md`: removed dated build-history narrative (the Stash bridge-tool rationale is kept as the rule plus its WHY), and fixed a dangling "Finalist test below" pointer to `references/layer-finalist-caveats.md`.
#### Added
- `fix` now saves the pre-fix audit report to a scratch file before applying safe fixes, so the `inline-bold-heading` findings survive a lost context.
- Registered in the `ccvw-toolkit` plugin of the Vaikri-costume/skills marketplace (`.claude-plugin/marketplace.json`).
- `LICENSE` (MIT, matching the declared `license`) and an `author.history` entry recording the GitHub origin, as the attribution lint requires once a source is recorded.

### 1.2.4 — 2026-08-24
#### Fixed
- `~/.claude/hooks/md-format-reminder.py` (the global mirror of this skill's write-rules checklist, added in 1.2.0) was firing on any `.md` write anywhere, including scratch/test-fixture files under an OS temp directory — confirmed silently contaminating this skill's own eval harness in iteration 2: baseline (no-skill) subagents writing eval fixtures under a scratchpad tempdir got the skill's own formatting rules injected via the hook, inflating baseline scores against with-skill runs. The hook now excludes any path under `/tmp/`, `/private/tmp/`, or `$TMPDIR`.
#### Changed
- `evals/evals.json`: rewrote eval 0's "grouped by category not by script" assertion, which grading evidence across two iterations showed was non-discriminating (passed trivially in both with-skill and baseline configurations) — it now checks for the specific regression it should catch (a raw per-script heading leaking into the report). Marked evals 3 and 4 `baseline_required: false` — eval 3 (Step -1 read/skip-as-fresh path) was scoring a vacuous 4/4 baseline pass every run (no Step -1 mechanism exists for an unskilled agent to fail), diluting the iteration-2 benchmark average despite the skill itself improving; pairing it with a baseline measured nothing. Added eval 4, exercising Step -1's actual write path (forced via an artificially-aged state-file timestamp) — eval 3 only ever exercised the read/skip branch.

### 1.2.3 — 2026-08-21
#### Fixed
- `schema-pass.py` crashed with `KeyError: 'type'` (and, once that was patched, a follow-on `AttributeError` on `drop_type_when_specific_present`) whenever a schema config's `canonicalization` field was `{}` or `drop_type_when_specific_present` was absent — found during the first full task-completion eval run (a minimal fixture schema hit it). All four schema-derived lookups (`canonicalization.type`, `canonicalization.status`, `writer_vocab_plain`, `zotero_itemtypes`) now use `.get(..., default)` instead of direct indexing, matching the pattern already used for `drop_type_when_specific_present`/`global_replacements`.
#### Changed
- `evals/evals.json` (dev-only, not packaged): split the compound "grouped by category, not by script" assertion in the audit eval into two, added an assertion rewarding ordering-trap-aware reasoning, strengthened the write-new-page eval prompt so the "no colon-pseudo-labels" check is actually exercised, and added a fourth eval case regression-testing the Step -1 maintenance-freshness check's non-blocking/self-contained behavior. Findings from the first full with-skill/baseline task-completion eval run (iteration 1): 100% pass rate with-skill vs. 61.9% baseline, entirely explained by the skill's safe-fix/report-only categorization.

### 1.2.2 — 2026-08-17 (shipped)
#### Fixed
- Three maintenance scripts (`graph-heading-extract.py`, `graph-colon-label-fix.py`, `property-normalize.py`) implemented write mechanisms for report-only audit categories but were never cited anywhere in SKILL.md — unreachable from the documented workflow (confirmed dead by `link_check.py`). SKILL.md's `fix` subcommand now documents all three as "judgment-gated maintenance scripts," with their args and when to invoke each.
#### Added
- `## Examples` section in SKILL.md (three worked trigger → steps → result cases for audit/fix/write) and a `## Troubleshooting` table (five common failure symptoms with cause + fix) — both were absent from the runtime-loaded SKILL.md body (the audit noted only README carried a worked example).
- README `## Features & modes` and `## Structure` sections (ship-standard, publisher-authored) and a "Cross-runtime testing status" disclosure: live round-trip testing has only been done on Claude Code with MCP-connected Obsidian/Logseq; Gemini CLI, Cursor, and OpenCode are untested.
#### Changed
- README `## How to install` and `## Sibling skills` placeholders filled (manual-install instructions — no package registry entry exists yet; sibling skills: skill-tracer, skill-publisher).

### 1.2.1 — 2026-08-11
- **Verification 5 (write/create round-trip) closed for both apps.** Obsidian: live MCP write → exact-match read-back → confirmed real app process → opened in the actual window → user-confirmed correct rendering. Logseq: same arc once its HTTP API was enabled (user had to turn it on in Logseq's own Settings — not something this skill can do). Found and documented a real gotcha: the Logseq MCP server's create/update-page tool auto-converts YAML frontmatter and markdown `#` headings in its `content` parameter — exactly the format this graph forbids. Fix: always pass properties via the structured `properties` object, never as YAML-in-content; verified this produces correct native `property::` syntax, schema-lint clean, byte-identical round-trip.

### 1.2.0 — 2026-08-11
- **Writer-attribution rule added to the write-rules checklist.** New page (or whole-page write): PAGE property `writer:: Claude`. Adding/editing blocks in an existing page whose page-level `writer::` is someone else and isn't changing: leave the page property alone, add a BLOCK-level `writer:: Claude` on just the new blocks — matches the graph's existing type/writer promotion rule (block-level values only for exception blocks). Mirrored into the global filesystem-wide format-reminder hook (`~/.claude/hooks/md-format-reminder.py`) so it's enforced even outside the skill.

### 1.1.0 — 2026-08-11
- **Write/edit now enforces format rules during generation, not just after.** Found a real gap: `write`/`create`/`edit` (subcommands C/D) only ran the schema-validation pipeline (required properties, bracket rule, title uniqueness) — nothing told a writing agent to follow the format checklist (no bold, no single-colon pseudo-labels, real `heading:: true` structure) while generating content, so every write risked needing a follow-up `fix` pass. The layer's "Write rules that always apply" checklist is now an explicit, mandatory step in both C and D, and the checklist itself was brought up to date with this session's two new rules (unconditional no-bold; single-colon pseudo-labels use a hyphen, except inside a quoted external title). Minor version bump: this changes write-path behavior, not just wording.

### 1.0.1 — 2026-08-11
- Tuned frontmatter `description` via skill-creator-ccvw's real trigger-eval loop (`run_loop.py`, 16-query eval set, 3 runs/query, 2 iterations, model claude-sonnet-5): train pass rate 13/16 → 14/16. Fixed a real false negative ("add a new Entity or Person page to my graph" 0.33→1.0 trigger rate) by leading with concrete action verbs (add/create/edit) instead of a subcommand-name list, and by explicitly naming property:: block format up front.
- Two known remaining weaknesses, not yet fixed (candidates for a further tuning pass): (1) false negative on project-named phrasing that doesn't use generic "my graph" language (e.g. "does my dupatta research graph have any missing required properties" — 0.33 trigger rate); (2) false positive on the explicit "Do NOT use" exclusion case (a plain YAML-frontmatter Obsidian vault query still triggers ~0.67 of the time despite being explicitly excluded).

### 1.0.0 — 2026-08-11
- Initial scaffold: standalone skill for dual-format Logseq/Obsidian graph audit, safe fixes, and schema-validated write/edit, with a pluggable layer architecture (Logseq/Obsidian, Tine, Apple Notes native markdown import, Finalist).
- Applied to the author's live graph: 624 safe fixes across two rounds (property-value bracket rule, then a corrected location-independent pass covering body-prose dangling links too).
- Apple Notes layer corrected mid-build: the real requirement is read-import compatibility, not a bidirectional sync bridge. `shakedlokits/stash` was evaluated, found unreliable on this machine (duplicate-note bug), and removed — the layer has no automation hook at all (Notes' markdown import is GUI-only), so it stays a manual compatibility check, never a scriptable adapter.
- Absorbed and refactored four maintenance scripts previously living inside the graph itself (schema-lint, schema-pass, property-normalize, assets-audit) to take explicit graph-root and schema-config arguments.

## Lineage notes

checked-marketplace: 2026-08-11T13:44

Independent design (category D). Grew out of a plan to add graph auditing to a project-management skill; split into its own skill because graph-format internals are a separate concern from project/session management. The schema knowledge was externalized to `assets/` config at model-agnostic tier, so the shipped skill body carries no personal vocabulary or paths.
