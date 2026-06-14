# CCVW Shared Glossary

The canonical definitions for vocabulary shared across all CCVW skills (skill-creator-ccvw, skill-tracer, marketplace-discover, and the user's own CCVW-built skills). Per-skill `references/glossary.md` files inherit from this — never redefine shared terms; only extend with skill-specific ones.

Alphabetized.

## Terms

| Term | Definition |
|---|---|
| **Anti-double-counting** | Orchestrator-side rule: when two trace agents flag the same exact text under the same root cause, log both flag IDs but apply one fix. Different root causes on the same text → both fixes apply. |
| **cluster** | A group of raw flag IDs (F*/B*/E*/G*) from one or multiple trace directions all pointing at the same underlying problem. Addressed once per cluster. |
| **cold-trace / cold-parallel / cold dispatch** | An Agent dispatch that has no awareness of sibling agents, no prior fix history, no convergence-round mentions. Each dispatch reads files as they currently exist and forms its view from scratch. Load-bearing invariant of skill-tracer. |
| **convergence** | (skill-tracer) The state where all three trace agents (forward/backward/executor) return clean in one cold round — **Condition A only**. There is no Condition B: the CCVW Word/Spirit audit and the simplify pass moved to skill-publisher's ship phase, so the tracer converges on correctness alone. |
| **FIX** | An address type — apply a surgical change to the underlying artifact (script, doc, code) so the next cold trace will not re-raise the flag. The DEFAULT address per the bias-toward-FIX rule. |
| **GAP** | Skill-creator-ccvw compatibility audit's output block (analog of trace agents' ISSUE block). Prefixed `G*` in the ledger. |
| **handoff marker** | `in-flight:: <Runtime> handoff round-N+1` — written at end of a round when the orchestrator yields (opt-in handoff, asymptotic stop, or budget-pressure yield). Cleared by the next invocation's Step 1(a) recovery rule 4. |
| **inline continuation** | Step 7 default: orchestrator loops in the same session through all rounds until convergence. Cold-trace invariant is preserved (each round's agents read current file state cold), only the orchestrator's session boundary differs from the opt-in handoff path. |
| **in-flight marker** | `in-flight:: <Runtime> <action> round-N` header in the ledger. Atomic-write protocol's mutable state for compaction recovery. **skill-tracer** action keywords: `dispatch` / `addressing` / `handoff` (the `audit` keyword was removed with tracer's Step 9). **skill-publisher** uses its own set (`polish` / `audit` / `tier` / `addressing` / `packaging` / `pr`). Distinct, never overloaded. |
| **ISSUE** | A trace agent's structured output block: tag, file path, `Claim:` (exact quote from skill), `Target:` (what file/script/brief actually says). |
| **ledger** | `~/.claude/skill-tracer-audit-ledger/<skill-name>.md` — one file per target skill accumulating every cluster from every round across every invocation. Cumulative round numbering. |
| **marketplace-discover** | Sibling skill at `~/.claude/skills/marketplace-discover/`. Scans the live marketplace catalog (`~/.claude/plugins/marketplaces/claude-plugins-official/.claude-plugin/marketplace.json` + `external_plugins/`) to recommend existing community plugins before building new. Invoked pre-eval by skill-creator-ccvw. |
| **Phase** | Ledger column distinguishing the kind of work a row records. In **skill-tracer** the only value is `TRACE` (correctness-only). In **skill-publisher** the values are `POLISH` / `AUDIT` / `TIER` / `PACKAGE` / `PR`. (Pre-refactor tracer ledgers may carry historical `SIMPLIFY` / `PORT-AUDIT` rows — back-compat only; not produced by the current tracer.) |
| **portability-spec** | `~/.claude/skills/skill-creator-ccvw/references/portability-spec.md` — defines the three portability tiers, agentskills.io base spec, Claude-extension blocklist, path-mapping rules. Source of truth for `portability_lint.py`. |
| **regression vs cascade** | Convergence-check distinction. **Regression** = round N+1 flag has a `Claim:` quote matching one already addressed in round N (the address was incomplete). **Cascade** = round N+1 has all-new `Claim:` quotes (healthy — round-N fixes opened previously-invisible gaps). The load-bearing convergence metric is regression count → 0, NOT raw flag count → 0. |
| **Round** | (skill-tracer) Cumulative-per-skill round number (always integer). Increments across invocations of skill-tracer on the same skill. The Round column in the ledger is the authoritative round counter. (skill-publisher's ledger uses a **Run** column with the same cumulative semantics.) |
| **Runtime** | ISO-8601 UTC time when an invocation started, formatted `YYYY-MM-DDTHH:MM`. Used in the ledger Runtime column and in every in-flight marker the orchestrator writes during that session. |
| **RUN_TIMESTAMP** | The current invocation's Runtime with every `:` replaced by `-` (filename-safe). Example: Runtime `2026-05-27T09:12` → RUN_TIMESTAMP `2026-05-27T09-12`. Used only for scratchpad filenames; ledger uses Runtime unchanged. |
| **self-invoking handoff** | Opt-in alternative to inline continuation: orchestrator writes the handoff marker at end of round and exits, waiting for user re-invocation. The default behavior of skill-tracer (full-convergence mode) before the inline-default was made standard. |
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
