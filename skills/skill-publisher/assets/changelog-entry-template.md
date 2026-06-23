### <version> — <ISO-date> (<status>)
#### Added
- <new backward-compatible capability>
#### Changed
- <change to existing behavior, prose, or internals — no contract break>
#### Fixed
- <bug fix>
#### Removed
- <removed/renamed command or feature — a breaking change (major bump)>

<!--
Keep-a-Changelog format. Insert this block at the TOP of HISTORY.md's "## Changelog"
section (newest first). The category headings are `#### Added / Changed / Deprecated /
Removed / Fixed / Security` (Keep-a-Changelog's six) — OMIT any category with no entries
(do not leave an empty heading). One line per meaningful change; summarize prose tweaks
as a single "polish pass" under Changed.

Sourcing per references/changelog-format.md — diff-driven when a published baseline
exists (the Step-7 changelog agent reconciles diff_published.py + the ledger rows), else
ledger-only:
  1. the structured diff vs the published state (changelog-agent-prompt.md), AND
  2. this ship run's ledger rows (POLISH/AUDIT/TIER clusters), AND
  3. user-described changes.

Bump (SemVer), highest level any change warrants:
  patch (1.0.0->1.0.1) = Fixed / Changed-no-contract / docs;
  minor (1.0.0->1.1.0) = Added (new backward-compatible capability);
  major (1.0.0->2.0.0) = Removed / a breaking Changed (renamed command, changed output contract).

Status suffix <status>: "shipped" for a normal ship; "initial publish" for a
degraded-mode first publish (per changelog-format.md).
-->
