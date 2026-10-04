# Tine compatibility caveats

Verified against Tine v0.6.92 (2026-08-11) via its own repo (`martinkoutecky/tine`): README, `docs/FEATURES.md`, `CHANGELOG.md`, and issue tracker — each claim below was checked against those sources directly, not assumed from "it's Logseq-compatible."

**Standing rule: Tine is alpha software (pre-1.0, multiple releases per week; a save-path markdown-corruption bug was patched the same day this file was researched). Nothing here is a permanent guarantee — re-check these caveats against the actually-installed Tine version before trusting them, and let the Step -1 documentation-currency check flag drift.**

## Verified safe

- **Page-properties-as-first-block (no YAML)**: fully supported — it's Tine's own native format.
- **Existing `CANCELLED` task markers**: safe. Tine's default cancel keyword is `CANCELED` (one L), but `docs/FEATURES.md` is explicit that the checkbox logic treats `CANCELED`/`CANCELLED` as equivalent for display and preserves whichever spelling is already on disk — round-tripping existing content does not rewrite the marker.

## Verified risk zones

- **Property-block edits**: historically the risky zone — closed issue #163 had page-property edits corrupting the header by merging blocks. Fixed, but treat property-block edits made *inside Tine* with extra attention after upgrades.
- **Tine writes its own properties** when its features are used: `tine.view::`, `tine.header::`, `tine.fields::`, `tine.formula.*::`, `tine.filter::`, `tine.group-by::`, `collapsed::`, `icon::`. These are expected file content, exempted via the schema config's tolerance list — do not "clean them up."

## Unverified — hand-test on a scratch copy before trusting

1. **`heading:: true` round-trip**: zero documentation either way in Tine's docs or issues. Test: open a scratch copy of a page using `heading:: true`, edit nearby content in Tine, save, and diff the file.
2. **New cancelled tasks**: does a task cancelled *through Tine's UI* write `CANCELED` (its default) or match the graph's `CANCELLED` vocabulary? Existing content is safe (above); this narrower question only affects tasks created/cancelled inside Tine. Test: create and cancel a task in Tine on a scratch copy, inspect the file.
