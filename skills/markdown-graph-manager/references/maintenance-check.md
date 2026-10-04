# Maintenance freshness check (Step -1)

Usage-triggered, not scheduled: it runs inline at every skill invocation, throttled to once per 7 days. Rationale: the apps reading these graphs move fast — on a single observed day, one app shipped a save-path corruption fix plus a new release, and another shipped a whole major version adding markdown-folder support. One-time verified assumptions rot quickly; a weekly usage-triggered check keeps the caveats files honest without any background scheduler.

## State file

Portable form: runtime-provided per-skill storage (`runtime.storage("markdown-graph-manager").get/set("maintenance-state")` or the equivalent your runtime offers).

Claude-Code-tier fallback: `${XDG_DATA_HOME:-$HOME/.claude}/markdown-graph-manager/maintenance-state.json` — create the directory on first use.

Shape:
```json
{"last_check": "2026-08-11T13:44:00Z", "last_results": {"app-id": "current | gap | check-manually"}}
```

Rule: under 7 days since `last_check` → silent, proceed. Otherwise run both checks, print ONE compact notice (only apps with gaps or drift; silence per current item), update `last_check` regardless of outcome, continue. A failing check degrades to a "check manually" line — it must never block or error out of the requested subcommand.

## Check 1 — app updates (read-only + notify; NEVER auto-install)

Compare installed vs latest for every app in the registry's watchlist. Installed version for a macOS app: `defaults read "/Applications/<App>.app/Contents/Info.plist" CFBundleShortVersionString` (or read the plist directly). Per-app latest-version source, as verified per app:

| App | Latest-version source | Notes |
|---|---|---|
| Tine | GitHub releases API: `https://api.github.com/repos/martinkoutecky/tine/releases/latest` | No Homebrew cask, no auto-updater — the only install path is a manual download from the releases page. |
| Logseq | GitHub releases API — but NOT `/releases/latest`: list releases and take the newest tag matching the watchlist entry's `track` constraint | **Logseq split into two versions at 2.0: the 2.x line is the DB-graph version.** For a file-based graph, 2.x is a different product, not an update — compare only against the newest file-based (0.10.x-line) release, and never recommend a 2.x/DB release unless the user explicitly asks to migrate (verified 2026-08-11: 2.0.1 = "DB version" beta; newest file-based = 0.10.15). No cask found either. |
| Obsidian | No public version API (closed-source). Fetch `https://obsidian.md/changelog/` and parse the top entry — lower confidence. | Obsidian self-updates, so this is a courtesy cross-check; degrade to "check manually" freely. |
| Finalist | Mac App Store — no public API. Scriptable check needs the `mas` CLI (`brew install mas`, an explicit-permission install). | Without `mas`: fall back to "glance at App Store → Updates, or confirm automatic app updates are on." Never error. |

For each app with a gap, ask the user ("X vY available, you're on vZ — install?") via the runtime's question mechanism. **Answering yes means the USER installs (or explicitly confirms a download command); this skill never downloads or installs on its own initiative** — that includes `mas` and app updates. (Apple Notes needs no install of any kind — its markdown import is a native, built-in macOS feature; see `references/layers/apple-notes.md`.)

## Check 2 — documentation currency

Only the layers whose compatibility is real-but-unverified need tracking (the graph's native apps — Logseq/Obsidian — are the format's own definition, nothing to track):

- **Tine**: re-fetch `https://raw.githubusercontent.com/martinkoutecky/tine/main/CHANGELOG.md` and `.../docs/FEATURES.md`. Diff against `references/layer-tine-caveats.md`: new namespaced properties (→ the schema config's tolerance list may need entries), resolved caveats (e.g. `heading::` support documented), new format risks.
- **Finalist**: re-fetch its markdown docs page (`https://finalist.works/docs/markdown-files/`). Diff against `references/layer-finalist-caveats.md`: any mention of Logseq-style `property::` support or keyword tasks would change that layer's status.

**Flag drift for the user's review — never silently rewrite a caveats file.** The caveats files record verified observations; only a human-confirmed re-verification updates them.
