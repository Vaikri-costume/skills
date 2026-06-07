# Improving an Existing Skill

This reference covers the workflow for evolving a skill that already exists — distinct from building one from scratch. Read this before editing an established skill so you don't accidentally break invariants, lose intent across rounds, or ship an evolution that's actually a fork in disguise.

---

## When this workflow applies (the iterate-vs-build distinction)

skill-creator-ccvw branches at the top of "Creating a skill" — if a similar skill already exists (in `~/.claude/skills/` or in the marketplace per `marketplace-discover`'s catalog), this workflow takes over instead of the from-scratch path.

Concrete signals that this is an improve, not a build:
- A `SKILL.md` already exists at `~/.claude/skills/<name>/`
- The user's phrasing includes "improve", "extend", "fix", "evolve", "update", "polish", "tighten"
- The skill has a populated `version` in its HISTORY.md **or** at least one prior iteration in `~/.claude/skill-creator-evals-ledger/<name>/` (either signal alone is sufficient — a pre-versioned skill with no `version` yet but with a prior eval-ledger run still counts as improve-mode; see line 73, which starts such skills at `1.0.0`)
- The user references a known limitation, missing feature, or test failure of the current skill

If at least one of these holds, proceed with the steps below.

---

## Step 1. Pre-edit cold trace

Before touching the skill, baseline its current state and surface any latent issues by running:

```
/skill-tracer <skill-name>
```

This produces (or extends) the skill's ledger at `~/.claude/skill-tracer-audit-ledger/<skill-name>.md`. Two outcomes matter:

- **Trace converges clean** → the skill is in a healthy state to evolve from. Note the audit-references mtimes captured in the ledger header so you can detect if those references change mid-evolution.
- **Trace surfaces unaddressed clusters** → STOP. Address those clusters first (skill-tracer will iterate to convergence), then return to this workflow. Building on top of a dirty skill compounds problems — the new edits will mix with old issues and the next trace can't tell them apart.

---

## Step 2. Read the existing skill's load-bearing decisions

Before drafting changes, read the skill's existing SKILL.md and look for:

- **Invariants** — explicitly numbered or labeled rules the skill says it never violates. NEVER silently override an invariant; if the evolution requires it, flag for the user.
- **Design rationale paragraphs** — "Why X" / "We chose Y because Z" passages. These document non-obvious decisions; understand them before changing the related behavior.
- **Cross-reference targets** — sections other parts of the skill point to (e.g., "see the Recovery section for the resume procedure"). Renaming or restructuring these breaks the cross-references silently.
- **External consumers** — files, scripts, or other skills that import / read / dispatch this skill. Check `~/.claude/skills/` for any skill whose SKILL.md mentions this one — those are downstream consumers whose contracts you must preserve.

---

## Step 3. Draft changes preserving intent

The considered-fix principle: edits should preserve the skill's original intent. If a proposed change conflicts with an invariant or load-bearing decision from Step 2, EITHER:
- Rewrite the change to fit within the existing invariants, OR
- Surface the conflict to the user explicitly: "this change would require dropping invariant N — confirm intent before proceeding."

Apply the same fix-conservatism rule skill-tracer uses: change the minimum text needed for the evolution. Whole-section rewrites turn one focused change into a multi-cluster problem the next trace will spend rounds on.

---

## Step 4. Version bump rules

Record the evolution in **HISTORY.md** (per `history-template.md`) — version + lineage live there, not in SKILL.md `metadata`:

1. Bump the top-level `version` in HISTORY.md frontmatter (semver), and set its `parent-version` to the version this evolved from.
2. Append a changelog entry to the HISTORY.md body: `### <new-version> — <date>` followed by what changed (Added X / Fixed Y / Tightened Z wording).
3. Update SKILL.md's `metadata.parent-version` only — it carries the parent version at-a-glance for the runtime contract; the authoritative version + changelog stay in HISTORY.md.

```yaml
# HISTORY.md frontmatter — top-level keys (NOT nested under metadata:)
version: "2.3.0"          # increment per semver
parent-version: "2.2.4"   # the version this evolved from
```

Versioning convention: **major** for breaking changes (invariant changes, contract changes), **minor** for new functionality preserving old behavior, **patch** for bug fixes / wording fixes only.

If HISTORY.md has no `version` (pre-versioned skill), start at `1.0.0` and set `parent-version: "pre-versioned"`.

---

## Step 5. Re-run portability lint

If the skill's tier is `claude-users` or `model-agnostic`, run:

```bash
python3 ~/.claude/skills/skill-creator-ccvw/scripts/portability_lint.py ~/.claude/skills/<skill-name>
```

Address any new violations the evolution introduced. Personal-tier skills can skip this step (lint runs in advisory mode regardless).

---

## Step 6. Re-trace to verify the evolution

After the evolution edits, run skill-tracer again:

```
/skill-tracer <skill-name>
```

This cold round audits the EVOLVED skill, not the pre-edit one. Expected outcomes:

- **Clean trace** → evolution is sound; commit and ship.
- **New clusters surfaced** → expected if the evolution was substantive; address per normal trace flow. Pay attention to any REGRESSION clusters (a cluster whose Claim text matches one addressed in Step 1's pre-edit trace) — these signal the evolution broke a previously-fixed issue.
- **Portability concerns** → not produced by this trace (skill-tracer is correctness-only); portability is re-checked at ship time by skill-publisher per the tier rules.

---

## When to fork instead of evolve (the divergence test)

If the proposed change would substantially alter the skill's purpose, scope, or contract — to the point that downstream consumers of the original would be surprised by the new behavior — recommend forking to a new skill name rather than evolving in place.

Concrete divergence signals:
- The skill's `name` no longer accurately describes what it does
- The frontmatter `description` would need to be rewritten more than 50%
- The trigger conditions ("When to invoke") would change fundamentally
- More than one existing invariant must be dropped or contradicted

When these hold, propose: "This is a fork, not an evolution. Suggest creating a new skill `<new-name>` (per skill-creator-ccvw's from-scratch path) and leaving the original at its current version for users who rely on the original behavior."

---

## Records to update outside the skill itself

After a successful evolution:

- **Skill's ledger** — `~/.claude/skill-tracer-audit-ledger/<skill-name>.md` should show the evolution's trace rounds appended (skill-tracer handles this automatically).
- **TASKS.md** (if task-management integration is in use) — close the iteration task, update the parent task with the new version.
- **External consumers** — if any downstream skill mentions this one's version constraint, update those constraints. Check `~/.claude/skills/` for SKILL.md files mentioning this skill's name + version.
