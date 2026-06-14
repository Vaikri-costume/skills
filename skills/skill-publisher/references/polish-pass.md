# Polish Pass (skill-publisher Step 2)

The mandatory polish pass: invoke the `simplify` skill on the target's SKILL.md + README.md, apply its findings with consolidation + intent awareness, and handle any regressions a polish edit introduces. This reference owns the mechanics. (Lineage: this is the simplify pass that used to be skill-tracer's Step 11 — it moved here when the tracer slimmed to correctness-only. Ledger rows land in the publisher's **POLISH** phase.)

---

## Why the polish pass exists

A skill arrives at ship having accumulated phrasing entropy across its build + trace history: every iteration's edit adds prose, and neither the eval loop nor the cold trace agents detect when the accumulated prose has become redundant, baroque, or no-longer-load-bearing. Without a deliberate polish pass, a skill ships 20–30% larger than its content actually requires — taxing every session it loads in. Polish is mandatory at ship; it's the one pass whose whole job is removing entropy rather than adding capability.

---

## Step 2.1 — Invoke the simplify skill

Invoke the `simplify` skill (the global, shared simplify pattern — typically at `~/.claude/skills/simplify/`; check the installed-skill list and use whichever simplify skill is installed and most current) via the Skill tool — e.g. `Skill(skill: "simplify", args: "<absolute path to target SKILL.md> <absolute path to target README.md>")`. If the installed simplify skill documents a different argument form, follow its own SKILL.md (it is authoritative for its exact arguments). Target the SKILL.md + README.md (and any reference file that grew significantly).

The 4-agent simplify pass runs in parallel (Reuse / Simplification / Efficiency / Altitude). Apply every finding **with consolidation and intent awareness, not blind execution**: overlapping findings collapse to one action, and intent-bearing WHY content stays (check each proposed cut against the target's README `## Intent` — a cut that removes load-bearing rationale is a USER-PAUSE, not a FIX). Two findings overlap when they target the same section of the same file AND would produce conflicting edits (e.g. one shortens a paragraph while another proposes moving it entirely) — collapse to the action that achieves both intents, or accept the more conservative one and note the collapse in the ledger row.

**Flag-ID prefixes for the four lenses** (recorded in the ledger Flags column):
- `SIM-R*` — Reuse (duplicate content, references-needed cases)
- `SIM-S*` — Simplification (verbose phrasing, redundant qualifiers)
- `SIM-E*` — Efficiency (executor-side workflow inefficiency)
- `SIM-A*` — Altitude (wrong abstraction level — move to references)

Each finding is clustered and addressed with the same FIX / STRENGTHEN / USER-PAUSE discipline as the audit/tier findings (see `ship-checklist.md`). Each addressed cluster is one **POLISH**-phase ledger row written with `scripts/append_ledger.py` (Root cause = the underlying defect, defect-focused; the lens lives in the Flags prefix).

**If the simplify skill is not installed**: `ls ~/.claude/skills/` to confirm; if absent, tell the user "simplify skill not installed; install via `claude plugins install simplify` (or the current install command)" and skip the polish pass (record no POLISH rows). Don't hand-simulate the 4-agent pass — the authoritative invocation lives in the simplify skill's own SKILL.md. (Skipping polish skips only the simplify invocation and its POLISH rows — the `polish run-N` marker written at Step 2's start still advances to `audit run-N` at Step 3 normally; do not clear it on skip.)

---

## Step 2.2 — Regression check on the polished text

Polish edits can introduce regressions like any edit: a collapsed definition that loses precision, a removed cross-reference that leaves something unanchored, a worked example whose context got cut. After applying the simplify findings, **re-read the polished SKILL.md + README.md** for these. (The publisher does NOT run its own cold-trace loop — that's the tracer's job. If the polish made substantial structural edits, suggest the user re-run `/skill-tracer <skill>` to verify; don't block ship on it.)

For any regression found, tag the addressing ledger row's Root cause with `ship-regression:` (e.g. `ship-regression: collapsed Step 4 description lost the Agent-call parameter table`) — this is the marker `render_ledger.py` highlights in red (see its `--config` regression_patterns). Address it: **FIX** (revert or partially restore the polish edit), **STRENGTHEN** (the polished text is correct but needs a closure marker), or **USER-PAUSE** (the polish made a judgment call the user must reconcile).

**Targeted reversal when a regression persists.** If the same `ship-regression` cluster survives a fix attempt, stop re-fixing — the polish edit itself is the problem. Identify the POLISH ledger row that introduced the regression-causing edit and apply a FIX that reverts *that specific edit* (`FIX (SKILL.md: revert polish edit at lines X-Y, restore pre-polish text)`), keeping the other polish gains. Re-read once more to confirm the reversal cleared it.

The regression *count* is not a gate — address each `ship-regression` cluster on its substance (persistence is detected by re-reading, not by tallying). The rendered ledger already surfaces these rows (red, via `render_ledger.py`'s `regression_patterns`), so there is deliberately no separate per-cluster counter script; a bare count would drive no decision the per-cluster pass doesn't already make.

---

## SKILL.md size ceiling (the 5,000-word target)

The polish pass is the moment to enforce the size ceiling, because polishing is when prose gets cut. After simplify, check the SKILL.md body: the target is **≤ ~5,000 words / ~500 lines**. Past that, comprehension and trigger latency suffer, and — because a triggered skill's body loads into context — an over-long SKILL.md taxes every session it fires in, not just this one.

If the body exceeds the ceiling after polishing, that's a POLISH cluster:
- **FIX** (default) — move a self-contained section into a `references/<topic>.md` and leave a one-line pointer ("Full X spec: `references/<topic>.md`"). Progressive disclosure: the detail loads only when needed.
- **STRENGTHEN / USER-PAUSE** — only if the length is genuinely load-bearing (rare) and can't be pushed to a reference without breaking the runtime path. Surface to the user rather than forcing a cut that loses something.

This mirrors skill-creator-ccvw's authoring-time 500-line guideline (`skill-writing-style.md`) — build aims for it; ship enforces it on the final artifact.

---

## Outcomes-first positioning (README + description polish)

A skill's value copy should lead with **the outcome the user gets**, not the skill's internal mechanism. This is a polish *heuristic* the publisher applies while polishing the README and description (Step 6) — not a hard gate. Flag and rewrite copy that describes structure instead of result:

- ✅ **Outcome-first:** "Turns a folder of meeting recordings into a searchable, tagged archive — transcribes each file, extracts action items, files them by project."
- ❌ **Mechanism-first:** "A skill containing YAML frontmatter and Markdown instructions that call the transcription MCP and write output files."

The mechanism version tells a prospective user nothing about whether to install it. Rewrite toward what they get.

**Ownership boundary:** BUILD (skill-creator-ccvw) authored `## What this skill does` and `## Intent` at scaffold time from the intent interview — the publisher does **not** re-author intent. The publisher fills the install/sibling placeholders and *polishes* the existing copy for end-user clarity (outcome-first phrasing, no internal jargon). If polishing would change the *meaning* of the stated intent (not just its phrasing), that's a USER-PAUSE, not a polish edit.

**MCP-pairing note (conditional):** when the target declares an MCP dependency/pairing (in frontmatter `metadata.mcp-server` or HISTORY), check the README carries a one-line combined-value statement — "the MCP connects Claude to `<service>`; this skill teaches the workflow on top of it." Add it if missing. Skip entirely for skills with no MCP dependency — don't manufacture an MCP story for a standalone skill.
