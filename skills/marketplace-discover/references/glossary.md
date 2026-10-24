# Glossary — marketplace-discover

See also: `~/.claude/skills/skill-creator-ccvw/references/ccvw-glossary.md` for all CCVW shared terms (cluster, FIX, STRENGTHEN, in-flight marker, Round, Phase, ledger, cold-trace, tier, etc.). This file lists ONLY terms specific to marketplace-discover.

## Skill-specific terms

| Term | Definition |
|---|---|
| **adapt** | One of the three recommendations: study a candidate read-only and take its ideas into the user's own skill. The copying and the attribution happen in skill-creator-ccvw, never in this skill. |
| **built-in directory** | Anthropic's plugin directory cache, `plugin-directory-cache-v2.json`. Searched in tier B; its listings have no install command here. |
| **`candidates`** | Script output key: marketplace entries that match, ranked, each with its exact install command (Step 2). |
| **`description_flag`** | Candidate field set when its catalogue description has instruction-like text aimed at an AI (Step 2). |
| **`directory`** | Script output key: built-in directory listings that match, each with a repository URL and no install command; null when the directory was not searched (Step 2). |
| **external_plugins** | A folder some marketplaces have, one subfolder per third-party plugin, each with a `plugin.json`. |
| **`files_scanned`** | Scan field: how many files the pattern scan read (Step 4). |
| **`files_skipped`** | Scan field: how many files the pattern scan did not read (Step 4). |
| **finding** | One line from the vetting scan: a check, a file, a line. A prompt to read, not a verdict. |
| **install command** | `claude plugin install <name>@<marketplace>`, built only for marketplace entries and run only after the user confirms. |
| **`local_folder`** | Candidate field: the plugin's folder on disk, or null when only a remote repository exists (Step 4). |
| **`marketplaces`** | Script output key: one entry per marketplace searched, with its entry count, age and status (Step 2). |
| **match strength** | high, medium or low, with a reason, per candidate. |
| **`matches_not_shown`** | Field on a marketplace skipped by the profile or `--only`: how many of its entries match the keywords (Step 2). |
| **not vetted** | The vetting result when a candidate's files could not be read. |
| **`notes`** | Script output key: one line per thing the script could not read or search, such as a marketplace not checked out (Step 2). |
| **`prefer_marketplaces`** | Profile field: marketplace names whose candidate is listed first when matches are about equal (Step 0, Step 2). |
| **`prose_to_read`** | Scan field: the README, CLAUDE.md, command, agent and skill files the reader must open (Step 4). |
| **red flag** | A pattern in a plugin's files that deserves a human read: for example a hook on every tool call or a download piped into a shell. See `vetting-checks.md`. |
| **`skip_marketplaces`** | Profile field: marketplace names to leave out of the search; passed as `--skip` (Step 2). |
| **`stale`** | Field on a marketplace entry, true when its catalogue is older than the stale threshold (Step 2). |
| **`stale_hours`** | Profile field: age in hours after which a catalogue counts as stale; passed as `--stale-hours` (Step 2). |
| **tier A** | The local marketplaces on disk, searched by `scripts/catalog_search.py` (Step 2). A marketplace listed but not checked out is searched in no tier; the report says it was not searched. |
| **tier B** | The built-in directory cache, searched in the same script run (Step 2). |
| **tier C** | Web and GitHub search outside the marketplaces. When it runs is set in Step 3. |
| **`tools_installed_first`** | Profile field: tools to check for before proposing any install (Step 0, Step 5). |
| **vetting** | Reading a candidate's own files for red flags before recommending install. Findings only; never "safe". |
