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

## Install a skill

**Claude Code marketplace** (easiest — installs the toolkit as a plugin):
```bash
/plugin marketplace add Vaikri-costume/skills
/plugin install ccvw-toolkit@ccvw-skills
```

**Clone, then copy the one(s) you want** into your personal skills directory:
```bash
git clone --depth 1 https://github.com/Vaikri-costume/skills.git ccvw-skills
mkdir -p ~/.claude/skills
cp -R ccvw-skills/skills/skill-publisher ~/.claude/skills/   # repeat per skill
```

**No git?** On the repo page, open `skills/<name>/`, download it (or the whole repo as a Zip), and move the `<name>/` folder into `~/.claude/skills/`.

**Cowork / Claude.ai (web):** zip the skill folder and upload it via **Settings → Capabilities → Skills**.

**Project-scoped** (one project only): place the skill under `.claude/skills/<name>/` in your project instead of `~/.claude/skills/`.

Skills load automatically once they're in place. Run one with `/skill-name` or just describe the task — Claude triggers it when relevant. Each skill's own `README.md` carries its full how-to-install + intent.

## Requirements
- Claude Code 2.0+ (or Cowork). Skills here are `claude-users` tier unless a skill's own README says otherwise.

## License & attribution
MIT — see [LICENSE](LICENSE). `skill-creator-ccvw` is a Category-A fork of Anthropic's [`skill-creator`](https://github.com/anthropics/skills) (MIT); that lineage and the original license are preserved in [`skills/skill-creator-ccvw/LICENSE.txt`](skills/skill-creator-ccvw/LICENSE.txt) and its `HISTORY.md`.
