# Layer: Tine — no adapter; filesystem-level only

[Tine](https://tine.page/) (`martinkoutecky/tine`, AGPL-3.0) is a local Logseq-format outliner that reads the same files the Logseq/Obsidian layer already manages. It is a third GUI over those files, **not** a `create()`/`edit()` target:

- **No CLI, no scripting API.** Its plugin system is capability-restricted WebAssembly with explicitly no filesystem or network access — there is nothing for this skill to call. Any "Tine support" is inherently filesystem-level, the same mechanism the primary layer already uses.
- **What this skill does for Tine instead:** (1) no script flags unknown property names, so Tine's own namespaced properties (`tine.view::`, `tine.header::`, `tine.fields::`, `tine.formula.*::`, `tine.filter::`, `tine.group-by::`, `collapsed::`, `icon::`) raise no finding; the schema config's `tolerated_properties` list and `tolerated_property_patterns` (where `tine.formula.*` sits) record them as expected content and exempt any of them that is also in `zotero_only_properties` from `schema-lint.py`'s Zotero-reserved-property finding; (2) the compatibility caveats in `references/layer-tine-caveats.md` gate any trust in Tine's handling of this graph's conventions.

Adapter contract answers: `check_schema_support` → not applicable (no adapter); `create`/`edit` → Unsupported ("edit the files via the primary layer; Tine picks them up itself"); `list`/`read`/`search` → the primary layer's filesystem reads serve identically.

**Before relying on Tine against a live graph, read `references/layer-tine-caveats.md`** — it lists what is still unverified and must be hand-tested on a scratch copy first.
