# CCVW Shared Glossary

The canonical definitions for vocabulary shared across all CCVW skills (skill-creator-ccvw, skill-tracer, skill-publisher, marketplace-discover, and the user's own CCVW-built skills). Per-skill `references/glossary.md` files inherit from this — never redefine shared terms; only extend with skill-specific ones. (Terms used by only *one* skill — e.g. skill-tracer's convergence / Condition A′ / the trace directions and lenses, or skill-publisher's ship stages — live in that skill's own glossary, not here.)

Alphabetized.

## Terms

| Term | Definition |
|---|---|
| **Anti-double-counting** | Orchestrator-side rule: when two trace agents flag the same exact text under the same root cause, log both flag IDs but apply one fix. Different root causes on the same text → both fixes apply. |
| **altitude** | Whether a change/mechanism is implemented at the right *depth* rather than as a fragile bandaid or a special case bolted on shared machinery. **Dual ownership, one definition:** **skill-tracer** owns the *correctness* half (wrong-depth that causes executor ambiguity or breaks on edge inputs — one of its nine review lenses); **skill-publisher** owns the *polish/size* half (wrong-depth that bloats or obscures, in the simplify pass). Same concept, two phases. |
| **cluster** | A group of raw flag IDs (skill-tracer: F*/B*/E* trace + R* review; skill-creator-ccvw: G*) from one or multiple agents all pointing at the same underlying problem. Addressed once per cluster. |
| **cold-trace / cold-parallel / cold dispatch** | An Agent dispatch that has no awareness of sibling agents, no prior fix history, no convergence-round mentions. Each dispatch reads files as they currently exist and forms its view from scratch. Load-bearing invariant of skill-tracer. |
| **FIX** | An address type — apply a surgical change to the underlying artifact (script, doc, code) so the next cold trace will not re-raise the flag. The DEFAULT address per the bias-toward-FIX rule. |
| **GAP** | Skill-creator-ccvw compatibility audit's output block (analog of trace agents' ISSUE block). Prefixed `G*` in the ledger. |
| **handoff marker** | `in-flight:: <Runtime> handoff round-N+1` — written at end of a round when the orchestrator yields (opt-in handoff, asymptotic stop, or budget-pressure yield). Overwritten/cleared by the next invocation's Step 1(a) recovery (skill-tracer: rule 3, resume-on-handoff). |
| **in-flight marker** | `in-flight:: <Runtime> <action> round-N` header in the ledger. Atomic-write protocol's mutable state for compaction recovery. **skill-tracer** action keywords: `dispatch` / `reviewing` / `addressing` / `handoff` (the old `audit` keyword was removed in the refactor). **skill-publisher** uses its own set (`polish` / `audit` / `tier` / `addressing` / `packaging` / `pr`). Distinct, never overloaded. |
| **ISSUE** | A trace agent's structured output block: tag, file path, `Claim:` (exact quote from skill), `Target:` (what file/script/brief actually says). |
| **ledger** | `~/.claude/skill-tracer-audit-ledger/<skill-name>.md` — one file per target skill accumulating every cluster from every round across every invocation. Cumulative round numbering. |
| **marketplace-discover** | Sibling skill at `~/.claude/skills/marketplace-discover/`. Scans the live marketplace catalog (`~/.claude/plugins/marketplaces/claude-plugins-official/.claude-plugin/marketplace.json` + `external_plugins/`) to recommend existing community plugins before building new. Invoked pre-eval by skill-creator-ccvw. |
| **Phase** | Ledger column distinguishing the kind of work a row records. In **skill-tracer** the values are `TRACE` (cold-trace directions) and `REVIEW` (the native nine-lens review). In **skill-publisher** the values are `POLISH` / `AUDIT` / `TIER` / `PACKAGE` / `PR`. (Pre-refactor tracer ledgers may carry historical `SIMPLIFY` / `PORT-AUDIT` rows — read-tolerated back-compat only; the current tracer writes only `TRACE`/`REVIEW`.) |
| **portability-spec** | `~/.claude/skills/skill-creator-ccvw/references/portability-spec.md` — defines the three portability tiers, agentskills.io base spec, Claude-extension blocklist, path-mapping rules. Source of truth for `portability_lint.py`. |
| **Round** | (skill-tracer) Cumulative-per-skill round number (always integer). Increments across invocations of skill-tracer on the same skill. The Round column in the ledger is the authoritative round counter. (skill-publisher's ledger uses a **Run** column with the same cumulative semantics.) |
| **Runtime** | ISO-8601 UTC time when an invocation started, formatted `YYYY-MM-DDTHH:MM`. Used in the ledger Runtime column and in every in-flight marker the orchestrator writes during that session. |
| **RUN_TIMESTAMP** | The current invocation's Runtime with every `:` replaced by `-` (filename-safe). Example: Runtime `2026-05-27T09:12` → RUN_TIMESTAMP `2026-05-27T09-12`. Used only for scratchpad filenames; ledger uses Runtime unchanged. |
| **ship-regression** | (skill-publisher) Root-cause tag applied when the Step-2 polish pass's regression check finds a polish edit introduced a defect (lost precision, unanchored reference, cut context). Surfaces polish edits that weren't clean wins; `render_ledger.py` highlights it red. (Was `simplify-regression` when this pass lived in skill-tracer's Step 11.) |
| **STRENGTHEN** | An address type — when the underlying artifact is correct and the cluster reflects intent trace agents couldn't see, add a WHY paragraph / closure marker / disambiguation note inside the skill at the point of use. The EXCEPTION address (only when FIX is ruled out per the two-step test). Four legitimate STRENGTHEN cases. |
| **tier** | Portability tier of a CCVW skill, declared in frontmatter `metadata.tier`. Three values: `personal` (user-specific behaviour with hardcoded local paths, default during iteration) / `claude-users` (portable within Claude Code AND Cowork — no user-specific paths or configs, default for finished skills shared with friends/family/coworkers running Claude) / `model-agnostic` (portable to Gemini CLI / Cursor / OpenCode / other agentskills.io-compatible runtimes). See `portability-spec.md` in this directory for the full per-tier rules. |
| **USER-PAUSE** | An address type — only valid when the orchestrator cannot decide between FIX and STRENGTHEN (or between two FIX paths) without user judgment per the PAUSE criteria. Other clusters in the round proceed normally; USER-PAUSE does not block. |
| **Word / Spirit** | Skill-creator-ccvw's two audit categories: **Word** = explicit rules the document states. **Spirit** = how skills are written, structured, explained. skill-publisher's Word/Spirit audit (ship phase) checks both. |

## Inheritance pointer for per-skill glossaries

Per-skill `references/glossary.md` files should begin with:

```
# Glossary — <skill-name>

See also: [`~/.claude/skills/skill-creator-ccvw/references/ccvw-glossary.md`](../../skill-creator-ccvw/references/ccvw-glossary.md) for all CCVW shared terms (cluster, FIX, STRENGTHEN, in-flight marker, Round, Phase, ledger, cold-trace, etc.). This file lists ONLY skill-specific terms not in the shared glossary.

## Skill-specific terms

| Term | Definition |
|---|---|
| ... | ... |
```
