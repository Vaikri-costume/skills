# Layer: Finalist — markdown-folder integration, unverified for property-block graphs

Finalist 4.0 (shipped 2026-08-11) added markdown-folder-as-notebook support: per its own docs (`finalist.works/docs/markdown-files/`), "Obsidian vaults, iCloud Drive, any folder of .md files becomes a native notebook" — frontmatter round-trips, and tasks checked off in Finalist write back into the source file.

## Adapter mapping

| Method | How |
|---|---|
| `check_schema_support` | false — Finalist's documented metadata dialects are YAML frontmatter, Obsidian-Tasks checkboxes, and Dataview inline fields; no property-block schema |
| `list` / `read` / `search` | filesystem reads over whatever folder Finalist is pointed at |
| `create` / `edit` | **Unsupported as a scriptable call** — Finalist has no CLI or API; it is interactive-app-only. Automation from this skill is limited to (a) generating markdown/text for the user to review and paste or save, or (b) advising the user to point the Finalist app at a folder and letting the app do the rest |
| `validate` | not applicable |

**Before Finalist ever sees a live property-block graph, read `references/layer-finalist-caveats.md`** — its documented format support does not include this graph's conventions, and its behavior on an unrecognized format is undocumented.
