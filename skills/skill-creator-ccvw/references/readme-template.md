# README.md Template

Every CCVW skill ships a `README.md` at its root. It's the human-facing document — what the skill is for, why it exists, how to install and invoke it. It's distinct from SKILL.md (the executor's runtime workflow) and HISTORY.md (provenance/changelog).

**Two important consumers beyond humans:**
1. **skill-tracer's orchestrator** reads the `## Intent` section (soft — warns if absent) to inform its considered-fix decisions: when tracer addresses a flagged issue, it checks "would this fix preserve the documented Intent?" The cold trace agents do NOT read the README (that would break the cold-trace invariant) — only the orchestrator does.
2. **skill-publisher** fills in `## How to install` and `## Sibling skills` at ship time, and polishes the whole README for end-user clarity.

---

## Template

```markdown
# <Skill Name>

## What this skill does

<One paragraph, end-user-facing. What the skill accomplishes, in plain language.
No internal jargon. Someone deciding whether to install reads this first.>

<Then the 2-3 concrete use cases from Capture-Intent Q1, each as a four-field
quadruple — name, trigger, ordered steps, end result. Example:
- **Sprint planning** — trigger: "plan this sprint" → steps: fetch status,
  analyze velocity, propose priorities, create tickets → result: a planned sprint.
These make "what it does" concrete and seed the triggers in How to invoke.>

## Intent

<WHY this skill exists. What problem it solves, what it's optimized for, the
design trade-offs made and why. This is the section skill-tracer's orchestrator
reads for considered-fix decisions — so state the load-bearing intent clearly:
"this skill prioritizes X over Y because Z". If a future fix would trade away X,
that's a signal the fix needs human judgment.>

## When to use / When NOT to use

**Use when:** <situations where this skill is the right tool>

**Don't use when:** <situations where another skill or no skill is better>

## How to install

<Filled by skill-publisher at ship time. For personal-tier skills: "Already
installed locally at ~/.claude/skills/<name>/". For claude-users tier:
marketplace install command + manual install steps. For model-agnostic tier:
per-runtime install commands.>

## How to invoke

<Slash command + natural-language triggers + 1-2 concrete examples.>

- Slash command: `/<skill-name> <args>`
- Natural language: "<example trigger phrase>", "<another>"

Example:
```
<a worked example invocation + what it produces>
```

## Sibling skills

<Filled by skill-publisher from HISTORY.md inspirations[] if present; interview
the user otherwise. Related skills, see-also patterns, what pairs well with this.>

- `<sibling-skill>` — <one-line relationship>

## For developers

The runtime workflow lives in [`SKILL.md`](SKILL.md). Provenance and changelog
live in [`HISTORY.md`](HISTORY.md). To trace this skill for bugs:
`/skill-tracer <skill-name>`. To ship a new version: `/skill-publisher <skill-name>`.
```

---

## Required sections

These eight sections are mandatory for every CCVW skill's README:

1. **`# <Skill Name>`** — title
2. **`## What this skill does`** — one-paragraph end-user summary
3. **`## Intent`** — WHY + design trade-offs (skill-tracer's considered-fix input)
4. **`## When to use / When NOT to use`** — applicability boundaries
5. **`## How to install`** — placeholder at scaffold, filled by publisher
6. **`## How to invoke`** — commands + triggers + examples
7. **`## Sibling skills`** — placeholder at scaffold, filled by publisher
8. **`## For developers`** — pointers to SKILL.md, HISTORY.md, tracer, publisher

(Scaffold-time: sections 5 and 7 are placeholders the publisher fills. Sections 2, 3, 4 are populated from the intent-capture interview. Section 6 from the trigger interview.)

---

## Intent section — the load-bearing part

The `## Intent` section is the one skill-tracer's orchestrator reads. Write it so a reader (human OR the tracer orchestrator) can answer: "if I change X about this skill, am I violating its intent?"

Good Intent prose names what the skill optimizes for and what it deliberately sacrifices:

> This skill prioritizes **exhaustive coverage over speed** — it re-scans the full file tree every round rather than tracking deltas, because a missed file is a worse failure than a slow run. Fixes that trade coverage for speed should be surfaced for human judgment, not applied automatically.

That tells the tracer: a FIX that adds delta-tracking to "speed things up" would violate intent → USER-PAUSE, not auto-FIX.

Vague Intent prose ("this skill helps with file organization") gives the tracer nothing to preserve. Be specific about the trade-offs.

---

## Authoring the other sections (good vs weak)

The Intent section gets the most attention because the tracer reads it, but the human-facing sections decide whether anyone installs and uses the skill. Quick good-vs-weak contrasts:

**`## What this skill does`** — lead with the *outcome*, in the installer's language, then back it with the concrete use cases.
- ✅ *"Turns a folder of meeting recordings into a searchable, tagged archive — transcribes each file, extracts action items, and files them by project."*
- ❌ *"A skill for processing audio files."* (no outcome, no scope, no reason to install)

**`## When to use / When NOT to use`** — the NOT half is what prevents over-triggering and wrong installs; make it specific, and point at the better tool.
- ✅ Use when: *"you have raw `.m4a`/`.wav` recordings and want structured notes."* Don't use when: *"you already have transcripts — use `note-summarizer` instead"* / *"for live transcription (this is batch-only)."*
- ❌ Don't use when: *"it's not appropriate."* (says nothing — the reader can't self-select)

**`## How to invoke`** — show a real worked example, not a schema. The natural-language triggers should be phrases a real user would actually type (mirror the use-case triggers from What-this-skill-does).
- ✅ *Natural language: "summarize the standups in my recordings folder", "pull action items from yesterday's call"* + a worked example showing input → output.
- ❌ *Natural language: "[trigger phrase]"* left as an unfilled placeholder, or a bare command with no example of what it produces.

Across all of them: end-user language, no internal jargon (the reader hasn't seen the SKILL.md), and concrete over abstract.
