# Claude Skills by Vaikri-costume

My personal collection of Claude [Agent Skills](https://agentskills.io) — skills I build for my own workflows and share. All are `claude-users` tier (portable across Claude Code and Cowork; no hardcoded personal paths).

Some of these are domain/workflow skills; three of them are a **skill-building toolkit** — a *build → trace → ship* pipeline I use to create and ship the rest of my skills bug-free. The collection grows as I build more.

## Skill-building toolkit (build → trace → ship)

The meta-tooling that produces everything else here — chain them: **build** a skill, **trace** it clean, then **ship** it.

| Skill | Phase | What it does |
|---|---|---|
| [**skill-creator-ccvw**](skills/skill-creator-ccvw/) | 🔨 build | Create, edit, and eval skills against the CCVW conventions — scaffolds the `SKILL.md` + `README.md` + `HISTORY.md` structure, captures design intent + attribution, iterates via centralized evals. |
| [**skill-tracer**](skills/skill-tracer/) | 🔍 trace | Cold-parallel correctness trace — three independent agents (forward / backward / executor) read a skill from scratch and surface bugs; loops until all three return clean. Correctness only. |
| [**skill-publisher**](skills/skill-publisher/) | 🚀 ship | Make a finished skill release-ready — polish, CCVW Word/Spirit audit, per-tier portability + attribution + security checks, version bump, package, and PR. |

## Other skills

_More skills I build for my workflows will land here._ (Each gets its own row + folder under `skills/`, with its own README.)

## Requirements
- Claude Code 2.0+ (or Cowork). Skills here are `claude-users` tier unless a skill's own README says otherwise.

## Install a skill

**New to skills?** A skill is a folder Claude reads and follows when a task matches it. Skills live in `~/.claude/skills/` (available in all your projects) or a project's own `.claude/skills/` (that project only). Once a skill folder is in place, Claude finds it automatically — there's no build step.

**Which method?** Want the whole build → trace → ship toolkit? Use the **marketplace** (one command, auto-updates). Want just one skill, or you're on the web app? Use **clone & copy** or the **Cowork** steps below.

### Option A — Marketplace (gets all three toolkit skills)

Type these **in the Claude Code prompt** (not your terminal). You only `add` the marketplace once:
```
/plugin marketplace add Vaikri-costume/skills
/plugin install ccvw-toolkit@ccvw-skills
```

### Option B — Clone & copy (pick individual skills)

Run these **in your terminal**:
```bash
git clone --depth 1 https://github.com/Vaikri-costume/skills.git ccvw-skills
mkdir -p ~/.claude/skills
cp -R ccvw-skills/skills/skill-tracer ~/.claude/skills/   # repeat per skill you want
```
**No git?** On the repo page open `skills/<name>/`, download it (or grab the repo Zip), and move the `<name>/` folder into `~/.claude/skills/`.

**Project-scoped instead?** Put the `<name>/` folder under `.claude/skills/` in your project rather than `~/.claude/skills/` — then only that project sees it.

### Option C — Cowork / Claude.ai (web)

Zip the skill folder and upload it via **Settings → Capabilities → Skills**.

### Then: confirm it loaded

Skills added by copying are picked up when a new session starts — **restart Claude Code** if it was already running (the marketplace install reloads on its own). To check, type `/` and look for the skill in the list, or just run `/skill-tracer`. You can also describe the task and Claude triggers the right skill automatically.

Each skill's own `README.md` carries its full how-to and design intent.

## License & attribution
MIT — see [LICENSE](LICENSE). `skill-creator-ccvw` is a Category-A fork of Anthropic's [`skill-creator`](https://github.com/anthropics/skills) (MIT); that lineage and the original license are preserved in [`skills/skill-creator-ccvw/LICENSE.txt`](skills/skill-creator-ccvw/LICENSE.txt) and its `HISTORY.md`.
