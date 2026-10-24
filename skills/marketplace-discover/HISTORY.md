---
version: "1.1.0"
category: D
parent-version: "1.0.0"
author:
  primary: "Vaikri-costume"
  history:
    - role: "original"
      name: "Vaikri-costume"
      skill: "marketplace-discover"
      license: "MIT"
      version: "1.0.0"
      date: "2026-05-29"
      source: "https://github.com/Vaikri-costume/skills"
---

# History — marketplace-discover

## Changelog

### 1.1.0 — 2026-10-24
#### Fixed
- Searched only one of the marketplaces on disk; it now reads every configured marketplace and checked-out folder.
- The install command used a `--source` option that does not exist; it is now `claude plugin install <name>@<marketplace>`.
- The stale-catalogue advice named the wrong command; it is now `claude plugin marketplace update`.
- The catalogue layout was assumed; the scan now handles catalogues with or without `external_plugins/`.
#### Added
- Tier B (Anthropic's built-in directory) and tier C (web and GitHub search on request).
- Vetting step: `scripts/vet_plugin.py` and `references/vetting-checks.md`; findings only, never "safe".
- "Adapt" as a third recommendation, with licence and attribution notes.
- `scripts/catalog_search.py` for the deterministic search, with tests.
- Settings read from the user profile section `## marketplace-discover`; no personal details in the skill.
- Standard README sections.
- "Learn from existing work" mode, an add-a-marketplace step with confirmation, and a check for an installed skill of the same name before any install.
- Unit tests in `scripts/tests/` and `evals/evals.json`; glossary terms for the script output and profile fields.
#### Changed
- Stale warnings are per marketplace with a configurable threshold instead of a fixed 24 hours.
- The output format adds Searched, Vetting, Licence and Last activity lines and a `Checked:` line for skill-creator-ccvw.
- Catalogue and plugin text is treated as data: instruction-like text is quoted as a red flag, not followed.
- `allowed-tools` adds WebSearch and WebFetch for tier C.
- Steps 3, 4 and 6 state their expected output; the vetting reference is read once and remote fetches are batched; Step 7 says why no checkpoint or log is kept.
- Glossary sorted by term; the catalogue-format reference and the README are rewritten.
- The fixed 24-hour freshness step, the Prerequisites section and the two-source scan are replaced by the per-marketplace search; no command or output users relied on is removed.

### 1.0.0 — 2026-10-04 (first public release)
#### Added
- First public release. Built with skill-creator-ccvw on 2026-05-29: searches the live Claude Code marketplace catalog and `external_plugins/`, ranks matches against a described need, and recommends build vs install. Release prep: CCVW audit fixes (frontmatter scope, negative trigger, examples, troubleshooting, glossary and install-command consistency), README with install and structure sections, MIT LICENSE.

## Lineage notes

checked-marketplace: 2026-05-29T20:00
