# Glossary — drive-organizer

See also: [`~/.claude/skills/skill-creator-ccvw/references/ccvw-glossary.md`](../../skill-creator-ccvw/references/ccvw-glossary.md) for all CCVW shared terms (cluster, FIX, STRENGTHEN, in-flight marker, Round, Phase, ledger, cold-trace, tier, etc.). Do NOT redefine those terms here — they live in the shared glossary as the single source of truth. This file lists ONLY skill-specific terms.

## Skill-specific terms

| Term | Definition |
|---|---|
| atomic-unit folder | A directory treated as one indivisible entity (venv, Zotero store, Unity project, .app bundle) — proposed whole, never per-file |
| bubble-sort by destination | Grouping proposals by final destination path before display so same-leaf files appear together in the viewer |
| cascading-Q | The four-question routing model: Q1 grouping → Q2 thing → Q3 functional area → Q4 leaf type |
| content_peek | First ~300 chars of extracted text (or audio metadata) stored per file in the registry, used to classify ambiguous files |
| external folder | A folder marked `"external": true` in its `.tidy-rules.json` — never scanned, proposed into, or routed |
| active groupings (areas) | The top-level destination set, read via `_active_groupings()` from the merged templates' `Q1_groupings` or `config.json "areas"`. Default five (ENTERTAINMENT, PERSONAL, WORK, EDUCATION, RESOURCES) but NOT fixed — a user may have more, fewer, or differently-named areas |
| auto_routed / proposed_subfolder | A propose-output flag: the W1 fast-path deterministically routed this file; its destination is written to `para_subfolder` (with `proposed_subfolder` as an alias). `auto_approved` (opt-in) additionally lets it skip the viewer |
| bootstrap | The setup-walkthrough subcommand: detect+lock atomic units, then sample unruled folders and emit them for Claude to infer rules (cold-start / audit modes) |
| classify_batch | A propose-output index (groups of 25) on each `needs_classification` file — one classification sub-agent is dispatched per batch (the fan-out) |
| entities.json | Per-drive metadata at `[root]/.organizer/entities.json`: entity_type, locked, aliases, relation, policy/behaviour, notes, review, negative — merged into rule aggregation + read at propose time |
| route_by_name_only | A propose-output flag set when a cost toggle (vision/skip_types/skip_over_mb) blocked opening a file: classify it from filename + path + rules only, never open it; `content_peek` is null |
| skip-rehash | The scan optimisation that reuses a file's stored sha256 when its path + size + `mtime` are unchanged, avoiding a re-hash |
| flagged | A file marked `?` in the viewer (`status='flagged'`) — excluded from propose until peeked and reclassified |
| learning loop | The propose/process-return mechanism that turns an approved edited destination into a new `.tidy-rules.json` rule |
| `_Inbox/` | The staging leaf where files with no matching rule land, pending manual resolution |
| mark-unapproved | The one-time pre-scan step that `x`-prefixes every unknown root folder to quarantine legacy chaos |
| para_category / para_subfolder | Registry columns. `para_subfolder` = the full destination path relative to root (the only routing field). `para_category` = that path's top-level grouping segment (first segment, e.g. `WORK`), derived from the path — not a separate routing input |
| per-user override | Per-machine config + template extensions at `[root]/.organizer/` that deep-merge over the shipped skeleton |
| prefix propagation | The naming rule that carries a parent's name one level down (e.g. `PERSONAL/PERSONAL Financial/`) |
| process-return | The post-viewer pipeline: learn from approvals, reclassify rejects, execute, cleanup, refill the batch |
| reconcile | The drift-detection subcommand: reports misplaced files, stale registry rows, and a mangled folder tree; applies fixes only on confirmation |
| registry | The SQLite `registry.db` (authoritative) + auto-mirrored `registry.csv` at `[root]/.organizer/` tracking every file's state |
| `.tidy-rules.json` | The per-folder classification memory — a list of `{description, folderName}` rules that grows lazily via the learning loop |
| `subfolder-templates.json` | The shipped source-of-truth describing the *shape* of the tree (which children each parent type expects) |
| x-folder | A folder `x`-prefixed by mark-unapproved — deferred staging for unsorted/legacy files, scanned at lowest priority, never renamed again |

## When to update this glossary

- After every skill-tracer convergence, any new terms the trace agents had to derive cold get written back here. Review them after each trace.
- When you add new functionality that introduces new vocabulary, add the term here BEFORE the next trace runs.
- When you rename a term in SKILL.md, update the term here in the same edit pass.
