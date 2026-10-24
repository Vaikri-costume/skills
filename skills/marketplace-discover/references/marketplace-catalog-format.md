# Marketplace Catalog Format Reference

Where Claude Code keeps marketplace catalogues on disk and the fields `scripts/catalog_search.py` reads. A reading reference so the format is not re-derived on each run.

## Where catalogues live

| File | What it is |
|---|---|
| `~/.claude/plugins/known_marketplaces.json` | The marketplaces that are configured: name, source repository, `installLocation`, `lastUpdated` |
| `~/.claude/plugins/marketplaces/<name>/.claude-plugin/marketplace.json` | One marketplace's catalogue (some use `<name>/marketplace.json` at the root) |
| `~/.claude/plugins/marketplaces/<name>/external_plugins/<sub>/.claude-plugin/plugin.json` | Extra third-party entries; `<sub>` is the subfolder's name, which need not equal the plugin's `name`; only some marketplaces have this folder |
| `~/.claude/plugins/plugin-directory-cache-v2.json` | Anthropic's built-in directory: `fetchedAt` and a `listings` array (`name`, `summary`, and the repository URL at `source.repository.url`), usually larger than any one marketplace |

The number of marketplaces and their sizes change, so the script lists them each run and the report states the counts. Do not quote counts from this file.

## Catalogue shape

```json
{ "name": "...", "owner": {...}, "plugins": [ { ...entry... } ] }
```

## Entry fields

| Field | Notes |
|---|---|
| `name` | Plugin id; used in the install command |
| `description` | What the script keyword-matches, with `name`, `category` and `keywords` |
| `category`, `keywords` | Optional |
| `author` | Optional object |
| `source` | Either a string (a path inside the marketplace) or an object (keys seen: `source`, `url`, `repo`, `path`, `ref`, `sha`); the script reads `url`, then `repo`, then `path`, and ignores `ref` and `sha`; a `url` or `repo` value may be `owner/name` rather than a full URL |
| `homepage` | Optional |

## Local folder

The script's `local_folder` is the plugin's folder on disk as an absolute path: the marketplace's folder joined with a path-style `source` (an entry whose `source` is `./plugins/x` gets `<marketplace folder>/plugins/x`), or the `external_plugins/<sub>` folder for an external entry. Only a string `source` that starts with `.` or `/` counts as path-style. It is null for a remote-only source (a URL or repository object), for a string `source` that does not start with `.` or `/` (such as `plugins/x`), and for a path-style `source` whose folder does not exist or lies outside the marketplace. A null `local_folder` therefore does not prove the plugin is remote: SKILL.md Step 4 gives the on-disk check to run before treating it as remote-only.

## Install command

`claude plugin install <name>@<marketplace>` (add `-s user|project|local` for a scope). Check `claude plugin install --help` if in doubt; an older form with `--source` does not exist. Built-in directory listings are not marketplace entries, so no install command is built for them: show the repository URL and let the user decide.

## Refreshing

`claude plugin marketplace update` refreshes all marketplaces (add a name for one). `claude plugin update <plugin>` updates one installed plugin and is not the catalogue refresh.
