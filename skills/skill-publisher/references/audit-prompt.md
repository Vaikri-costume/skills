# Audit Prompt (skill-publisher Step 3)

> **Adaptation note (moved from skill-tracer):** this file was skill-tracer's Step-9 audit, moved to skill-publisher as its Step-3 CCVW Word/Spirit audit. The ledger's GAP rows land in the publisher's AUDIT phase. The portability sub-audit described here is now skill-publisher's separate **Step 4** (tier-transition checks) — the publisher runs the portability lint there per `tier-transition-checks.md`, not inline with the audit. The CCVW Word/Spirit audit prompt body itself is unchanged (template only — "unchanged" means the raw template text has not been modified; the path-rewrite described in the Reference-skill resolution section below is still required before dispatch whenever the fallback resolver fires; the template is not ready to dispatch as-is).

The full skill-creator-ccvw compatibility audit prompt body. This reference owns the prompt text and the reference-skill resolution mechanics. (The portability-lint mechanics described below now live in `tier-transition-checks.md` as Step 4.)

---

## Reference-skill resolution (orchestrator-side, before dispatch)

Resolve which skill-creator variant to audit against. Try in order, use the first that exists:

1. `~/.claude/skills/skill-creator-ccvw/SKILL.md` — primary (the CCVW fork)
2. `~/.claude/skills/skill-creator/SKILL.md` — fallback (upstream skill-creator)
3. `~/.claude/plugins/marketplaces/claude-plugins-official/plugins/plugin-dev/skills/skill-development/SKILL.md` — fallback (plugin-dev's skill-development reference)

Store the resolved path in `<AUDIT_REFERENCE_PATH>`. The audit prompt body below references the PRIMARY path (`~/.claude/skills/skill-creator-ccvw/SKILL.md`) literally as a contract anchor (recovery rule 2 scans for the literal `skill-creator-ccvw audit of <skill>` description string regardless of which variant resolved). When `<AUDIT_REFERENCE_PATH>` ≠ the primary, the orchestrator MUST rewrite the prompt body's hardcoded paths to the resolved path before dispatch — string-replace every occurrence of `~/.claude/skills/skill-creator-ccvw/SKILL.md` in the prompt body with `<AUDIT_REFERENCE_PATH>`. This replacement covers the entire prompt body including the pre-flight gate block (the `PRE-FLIGHT` output line, the ABORTED message, and the Step 1 read instruction) — all hardcoded occurrences in the fenced block below are replaced in a single pass. The description string stays `skill-creator-ccvw audit of <skill>` for `recover_dispatch.py` scan compatibility (the regex `^skill-creator-ccvw\s+audit\s+of\s+(.+)$` in that script must match this description exactly to recover the audit Agent's result after compaction). The pre-flight gate inside the prompt body will then check the resolved path, not the hardcoded one. Surface to the user: `Note: audit reference resolved to <AUDIT_REFERENCE_PATH> (primary skill-creator-ccvw not installed; using fallback).`

If none of the three resolve (no skill-creator variant installed at all), do NOT dispatch the audit Agent — surface to the user: `Cannot audit: no skill-creator variant installed at any of: <list of 3 paths>. Install one of: \`claude plugins install skill-creator-ccvw\` (preferred), \`claude plugins install skill-creator\`, or \`claude plugins install plugin-dev\`.` Then pause the ship.

## Reference-skill mtime capture (orchestrator-side, before dispatch)

Capture the mtimes of all three reference SKILL.mds and echo the `audit-references::` ledger line — **in a single Bash call** (shell variables do not persist across tool calls). All three resolution paths are recorded (not just the one that resolved) so the ledger shows which references existed at audit time:

```bash
SCC=$(stat -f "%Sm" -t "%Y-%m-%d" ~/.claude/skills/skill-creator-ccvw/SKILL.md 2>/dev/null \
  || stat -c "%y" ~/.claude/skills/skill-creator-ccvw/SKILL.md 2>/dev/null | cut -d' ' -f1)
SC=$(stat -f "%Sm" -t "%Y-%m-%d" ~/.claude/skills/skill-creator/SKILL.md 2>/dev/null \
  || stat -c "%y" ~/.claude/skills/skill-creator/SKILL.md 2>/dev/null | cut -d' ' -f1)
PDS=$(stat -f "%Sm" -t "%Y-%m-%d" ~/.claude/plugins/marketplaces/claude-plugins-official/plugins/plugin-dev/skills/skill-development/SKILL.md 2>/dev/null \
  || stat -c "%y" ~/.claude/plugins/marketplaces/claude-plugins-official/plugins/plugin-dev/skills/skill-development/SKILL.md 2>/dev/null | cut -d' ' -f1)
SCC=${SCC:-<missing>}; SC=${SC:-<missing>}; PDS=${PDS:-<missing>}
echo "audit-references:: skill-creator-ccvw@${SCC}, skill-creator@${SC}, plugin-dev/skill-development@${PDS}"
```

(The `stat -f` form is BSD/macOS; `stat -c` is GNU/Linux. `${VAR:-<missing>}` substitutes the literal `<missing>` when stat fails — prevents a blank value in the ledger.) Write/overwrite the ledger's `audit-references::` line (per ledger-format.md header spec) with the echo'd output.

**Drift check.** Before overwriting, read the prior `audit-references::` line if it existed. For each entry compare prior vs current:
- If both prior and current are `<missing>`: no comparison; skip the entry.
- If prior is `<missing>` and current is a date: the reference was newly installed; surface `Note: <reference> newly installed (was <missing>, now <current-date>). First audit against this reference.` Informational.
- If prior is a date and current is `<missing>`: the reference was uninstalled; surface `Note: <reference> uninstalled (was <prior-date>, now missing). Audit will skip this reference.` Informational.
- If both are dates and current > prior (numeric date comparison): surface `Note: <reference> changed since last audit (<prior-date> → <current-date>). Re-audit will compare against the newer reference.` Informational.
- Otherwise (both dates, current ≤ prior): no note needed.

All notes are informational, not blocking — the audit proceeds either way.

---

## Audit Agent dispatch parameters

| Parameter | Value |
|---|---|
| `description` | exactly `skill-creator-ccvw audit of <skill>` (recovery-protocol.md rule 2 scans for this string) |
| `subagent_type` | `general-purpose` |
| `prompt` | the filled-in prompt below |

**SLOT table:**

| Slot | Value |
|---|---|
| `[TARGET_SKILL_PATH]` | absolute path to the target's `SKILL.md` (the target resolved in Step 1) |
| `[TARGET_FILE_LIST]` | absolute paths of every supporting file under the target skill directory — enumerate with `find <target-dir> -type f \( -name "*.md" -o -name "*.py" \) ! -name "README.md" ! -name "HISTORY.md"` (the target's runtime + reference files, one per line; README.md and HISTORY.md are excluded because they are user-facing and provenance docs, not the SKILL.md + references/*.md audit surface) |

**Stage with the shared `stage_cold_prompts.py`** rather than substituting the SLOTs by hand (it owns the RUN_TIMESTAMP colon→dash derivation + the no-unsubstituted-slot guard, so a leftover `[SLOT]` fails loudly instead of dispatching a half-filled audit prompt). Everything needed to invoke the stager — its `--template`/`--out-dir`/`--runtime`/`--spec` interface and the one-entry spec-JSON shape — is given inline in the fenced block below; you do **not** need skill-tracer's `dispatch-protocol.md` loaded. `stage_cold_prompts.py` is part of skill-tracer, not skill-publisher — before using it, confirm it is present: `ls ~/.claude/skills/skill-tracer/scripts/stage_cold_prompts.py`. If skill-tracer is not installed, the hand-substitution fallback below is fully self-contained — prefer it whenever the stager is absent; substitute by hand: replace `[TARGET_SKILL_PATH]` and `[TARGET_FILE_LIST]` directly in the prompt body text below, then verify no literal `[SLOT]` remains before dispatch. First write the `## The filled prompt` fenced body (below) to a template file, then pass that path to `--template`:

```bash
# write the audit prompt body to a temp template file first:
#   First ensure the parent directory exists: run `mkdir -p /tmp/skill-publisher-prompts/` in Bash.
#   Then use the Write tool to create /tmp/skill-publisher-prompts/audit-template.txt.
#   Write the contents of the fenced block under "## The filled prompt" BELOW,
#   EXCLUDING the opening ``` and closing ``` delimiter lines.
#   Keep the [TARGET_SKILL_PATH] and [TARGET_FILE_LIST] tokens as-is —
#   stage_cold_prompts.py substitutes them; do not substitute manually here.
python3 ~/.claude/skills/skill-tracer/scripts/stage_cold_prompts.py \
  --template /tmp/skill-publisher-prompts/audit-template.txt \
  --out-dir /tmp/skill-publisher-prompts \
  --runtime "<Runtime>" \   # <Runtime> = the invocation timestamp in YYYY-MM-DDTHH:MM[:SS] form; the stager derives RUN_TIMESTAMP by replacing every ":" with "-"
  --spec -   # `-` means read the spec JSON from stdin; pipe it directly. One entry: {"label":"audit","slots":{"[TARGET_SKILL_PATH]":"...","[TARGET_FILE_LIST]":"..."}}
             # Shell syntax: echo '{"label":"audit","slots":{"[TARGET_SKILL_PATH]":"<abs-path>","[TARGET_FILE_LIST]":"<paths-one-per-line>"}}' | python3 ... stage_cold_prompts.py ... --spec -
             # Or with a here-string: python3 ... stage_cold_prompts.py ... --spec - <<< '{"label":"audit","slots":{...}}'
```

(`stage_cold_prompts.py` is vendored with skill-tracer; if it is not installed, substitute the two SLOTs into the prompt body by hand and verify no literal `[SLOT]` remains before dispatch.)

(The publisher stages a single audit prompt, so this is one spec entry; the value is the no-half-filled-prompt guarantee + shared RUN_TIMESTAMP handling, not multi-prompt batching.)

---

## The filled prompt

```
You are a skill-creator-ccvw compatibility auditor.

This is a cold audit — do not request, reference, or remember any prior
audit or fix history of the target skill. Read the files as they currently
exist.

You are read-only. Do not edit any file. Do not run any script. Do not
dispatch any sub-agent. Reading and grepping are the only permitted
actions. (The portability lint is run by the orchestrator, not by you —
your scope is CCVW Word/Spirit audit only.)

### Pre-flight gate.
Before producing any audit output, verify the following files exist:
1. `~/.claude/skills/skill-creator-ccvw/SKILL.md` (the reference)
2. Every path in [TARGET_FILE_LIST] (the target)

For each, output one line: `PRE-FLIGHT <path>: <line_count> lines, last edited <yyyy-mm-dd>`.

If `~/.claude/skills/skill-creator-ccvw/SKILL.md` is missing, abort with
the single line `ABORTED — skill-creator-ccvw reference missing at
~/.claude/skills/skill-creator-ccvw/SKILL.md` and stop. If any target
file is missing, abort with `ABORTED — missing target files: <comma-
separated paths>` and stop.

### Step 1 — Read skill-creator-ccvw fresh.
Read ~/.claude/skills/skill-creator-ccvw/SKILL.md in full. Derive your
complete understanding of skill-creator-ccvw's Word requirements
(explicit rules the document states) and Spirit principles (how skills
should be written, structured, and explained) directly from that
document.

skill-creator-ccvw is the CCVW fork of upstream skill-creator. It
inherits every Word requirement and Spirit principle from upstream
skill-creator (including 500-line guidance, progressive disclosure,
explain-WHY) and adds one CCVW-specific requirement: eval outputs go
to ~/.claude/skill-creator-evals-ledger/<skill-name>/ instead of beside
the target skill. When auditing target skills, both inherited upstream
requirements AND the CCVW-specific requirement are in scope.

Audit against everything skill-creator-ccvw documents — inherited from
upstream skill-creator plus CCVW-specific eval-output centralization.
Read the reference SKILL.md and the linked specs (its sibling
references/portability-spec.md and references/attribution-spec.md, resolved
relative to the reference skill's own directory — so a fallback-resolved
reference finds them under that skill's references/) for the canonical requirements.

### Step 2 — Read the target skill fresh.
Target skill: [TARGET_SKILL_PATH]
Files in scope: [TARGET_FILE_LIST]

### Step 3 — Audit (CCVW Word/Spirit).
For each Word requirement, verify the target satisfies it. For each
Spirit principle, verify the target's text reflects it. Quote the target
text under `Target:` for every finding. These GAPs use plain `G<n>` IDs (e.g. `G1`, `G2`, … — a bare G code with no hyphen). WHY bare: the TIER sub-families used by the publisher's Step 4 always carry a hyphenated segment (`G-PORT*`, `G-ATTR*`, `G-COWORK*`); a bare `G<n>` is unambiguously an AUDIT Word/Spirit finding. A combined AUDIT+TIER finding gets a hyphenated TIER code — the AUDIT code is subsumed. (ledger-format.md has the full flag-family taxonomy, but that file is not in scope for this audit agent — the bare-G rule is self-contained above.)

Spirit principles to verify explicitly (in addition to everything the
reference SKILL.md documents):
- **Composability / non-exclusivity.** The target must work alongside other
  loaded skills — it must not assume it is the only capability available, must
  not instruct the executor to disable/override sibling skills, and must not
  claim exclusive ownership of a whole task class. A skill whose description
  grabs generic triggers that would crowd out siblings, or whose body says
  "ignore other skills / only use this," fails this principle. Flag it.

(Portability lint findings come from a separate orchestrator-side step,
NOT from this audit agent. Your scope is CCVW Word/Spirit only.)

### Output format
For each gap, output exactly:

GAP [tag]: [one sentence describing the gap]
File: [absolute path]
Skill-creator-ccvw says: [exact quote from skill-creator-ccvw's SKILL.md]
Target says: [exact quote from the target, or "absent"]

Tag with kebab-case Word/Spirit-failure name. Example: `GAP [missing-pushy-description]: ...`

After all gaps, conclude with exactly one of:
- `No gaps found`
- `No of gaps found:: N`
```

---

## Portability lint — runs separately at Step 4, not here

The portability-lint mechanics (invocation at each tier, the JSON schema, the exit-code handling, and the finding→cluster mapping) **moved to `references/tier-transition-checks.md`, which the publisher runs as its Step 4** — they are NOT run inline with this audit. This audit Agent produces only CCVW Word/Spirit GAPs (`G<n>`); the tier-transition portability findings are generated by Step 4 and tagged **Phase=TIER**. Do not run the lint from this audit. See `tier-transition-checks.md` for the lint's command form, output schema, and exit codes.

---

## Collecting the GAP set + how it relates to the tier checks

This audit (Step 3) produces only CCVW Word/Spirit GAPs (`G<n>` — e.g. `G1`, `G2`, …). The portability-lint findings are generated separately at **Step 4** (tier-transition checks) — they are NOT collected here. Both sets converge at **Step 5** (addressing), where each cluster gets FIX / STRENGTHEN / USER-PAUSE per `ship-checklist.md`. No GAP is dismissed externally — the reasoning must land in the skill so the next cold audit reads it.

**Ledger Phase column (publisher phases — POLISH / AUDIT / TIER / PACKAGE / PR):**
- A CCVW Word/Spirit GAP from this audit → **Phase=AUDIT**.
- A portability-lint or other tier-check finding from Step 4 → **Phase=TIER** (see `tier-transition-checks.md`).
- When an AUDIT GAP and a TIER finding share one root cause, cluster them and tag the row by the controlling defect: **Phase=TIER** if the portability/tier issue is the controlling fix, else **Phase=AUDIT**. If genuinely ambiguous, default to **Phase=TIER** (the more specific signal — a clustered row that contains a tier finding should surface as TIER so the Phase column keeps its visibility).

(Older ledger prose may show `TRACE` / `PORT-AUDIT` — those were skill-tracer's phase names before the audit + portability checks moved to the publisher; the publisher's phases are POLISH/AUDIT/TIER/PACKAGE/PR per `ledger-format.md`.)

---

## ABORTED handling

There are exactly two ABORTED output formats the audit Agent can emit (this list is closed):

**If the audit agent returns `ABORTED — skill-creator-ccvw reference missing ...`**: the CCVW reference skill (or the resolved fallback) is not installed on this machine. (The ABORTED label always reads `skill-creator-ccvw reference missing` as a fixed contract anchor even when a fallback was resolved; the PATH in the message is rewritten to the resolved reference per the line-17 rule, so read the path — not the label — to see which reference actually failed pre-flight.) The audit cannot proceed without it; tell the user and pause the ship. Leave the `audit run-N` in-flight marker in place — when the user installs the reference skill and re-invokes, recovery rule 2 (`audit run-N`) fires; `recover_dispatch.py` will return exit 1 (no prior result), directing a fresh cold re-dispatch of the audit. This is the one exception to the "no GAP dismissed externally" rule because the audit could not run at all — there are no GAPs to dismiss.

**If the audit returns `ABORTED — missing target files: ...`**: the `[TARGET_FILE_LIST]` was stale (a file moved/renamed between enumeration and dispatch). Re-resolve the target file list (re-run the `find` from the SLOT table), re-stage, and re-dispatch the Step 3 audit Agent only. When it returns, proceed to **Step 4** (tier-transition checks), then **Step 5** (address the AUDIT + TIER GAPs) — this is an in-place re-dispatch within the same ship run, not a new round; no handoff marker is involved. Do not skip Step 4 — the tier-transition checks have not yet run for this ship run.
