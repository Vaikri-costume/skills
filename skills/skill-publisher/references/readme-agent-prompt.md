# README user-facing sections agent (skill-publisher Step 6)

The cold agent that drafts the user-facing README sections the **publisher owns** —
`## Features & modes` and `## Structure`, plus a mode-completeness check on
`## How to invoke` — by reading the **final, shipped SKILL.md + the reference/script
inventory** as the source of truth. It **augments**, never overrides: it does not touch
the creator-authored `## What this skill does` / `## Intent` / `## When to use` sections.

**Runs every full ship (verify + fill).** These two sections are *mechanically derived*
from the SKILL.md — the modes come from the mode dispatch, the features from the
workflow steps, the structure from the file layout — so the agent re-drafts them each
ship and the orchestrator **replaces** them, keeping them in sync as the skill evolves.
(Contrast the hand-authored `## Intent` / `## What this skill does`, which are preserved
across ships — regenerating *those* would clobber human-tuned prose.)

## Why a cold agent

Same rationale as `audit-prompt.md` / `changelog-agent-prompt.md`: a cold read of the
shipped artifact, with the orchestrator reviewing and applying. The agent describes the
skill the way a new user/contributor discovers it — in **end-user language**, from the
SKILL.md alone, with no prior-version or internal-design baggage. It is a single Agent,
a constant description, a completion sentinel. **No recovery marker** — Step 6 is already
marker-cleared (steps 6–7 are re-runnable local edits), and the draft is idempotent
(re-reading the current SKILL.md), so an interrupted run simply re-dispatches.

## Building the slots (orchestrator-side, before dispatch)

- `[SKILL_NAME]` — the target skill name.
- `[SKILL_MD]` — the **full final SKILL.md** (post-polish, post-tier-fix — the workflow
  as it will ship). The agent reads modes + features + structure from this.
- `[FILE_LIST]` — the **bare absolute paths** of every `references/*.md` and `scripts/*`
  file, one per line, **no descriptions**. The orchestrator supplies only the paths; the
  agent reads whichever files it needs and derives each one's role itself (the same
  cold-read discipline the trace agents use). Do NOT pre-extract the roles into the slot —
  that pre-digests a conclusion the cold agent should reach from the files, and it merely
  duplicates the one-liners already visible in `[SKILL_MD]`'s References section.
- `[CURRENT_README]` — the existing README.md (so the agent enriches `## How to invoke`
  rather than duplicating it, and never re-authors What-it-does / Intent / When-to-use).

Dispatch with `description` = **`readme sections for <skill>`** (the bare skill name;
constant for consistency). `subagent_type` `general-purpose`.

## The filled prompt

```
You are drafting the user-facing README sections for the <skill> skill. Read the SKILL.md
below, and **read whichever of the listed reference/script files you need** (Read the paths
directly) to understand and describe the skill's structure — derive each file's role
yourself; do not expect it pre-summarized. Write for an END USER deciding whether to use the
skill and a CONTRIBUTOR orienting themselves — plain language, no executor/runtime jargon
(the reader has not seen SKILL.md). Read only the files listed below; do not request other
files or prior context.

## The skill's runtime workflow (source of truth)
[SKILL_MD]

## The skill's reference + script files — Read any you need to derive the structure (paths only; their roles are yours to determine)
[FILE_LIST]

## The current README (for context — do NOT re-author its What-this-skill-does / Intent /
## When-to-use sections; only enrich How-to-invoke)
[CURRENT_README]

## Your task — draft exactly these, from the SKILL.md:
1. `## Features & modes` — the skill's capabilities and every INVOCATION MODE. Read the
   mode dispatch (e.g. a default/full mode plus any flagged modes) and the workflow's
   distinct features. One bullet per mode/feature: **what it does** + **how to trigger it**
   (the flag or natural-language phrase). A user should be able to pick the right mode from
   this list alone.
2. `## Structure` — a short orientation map of the skill's layout: `SKILL.md` (the workflow
   spine the executor follows), `references/` (the mechanics loaded on demand — group by
   theme, don't list all), `scripts/` (the deterministic helpers — what kinds), `assets/`
   (templates) if present, and where the skill writes its outputs (ledger / artifact /
   manifest locations). **Read the listed files to derive what each does** — don't lean on
   SKILL.md's one-line References summaries alone; open the ones you're unsure of. For
   someone deciding to read or contribute, not a file-by-file dump.
3. `## How to invoke` gaps — compare the modes you found in the SKILL.md against the current
   README's `## How to invoke`. List any mode/trigger present in the SKILL.md but MISSING
   from How-to-invoke (so the orchestrator can add it). Do not rewrite How-to-invoke.

Keep every section end-user-facing and concrete. Omit a section only if the skill genuinely
has no modes (then `## Features & modes` becomes a plain feature list) or no scripts/refs.

## Output format (exactly these blocks, in order)
FEATURES_AND_MODES:
## Features & modes
<the section body>

STRUCTURE:
## Structure
<the section body>

INVOKE_GAPS:
- <one line per mode missing from How-to-invoke, or the single line `none`>

Then a final line, exactly:
README SECTIONS COMPLETE
```

## Reconciliation (orchestrator-side, after the agent returns)

- **Completion check** — the result must end with `README SECTIONS COMPLETE`. If absent
  (truncated/aborted), re-dispatch the cold agent (cheap — same inputs).
- **Apply the two derived sections** — insert `## Features & modes` then `## Structure` in
  the canonical README order (**after `## How to invoke`, before `## How to install`**). If
  either section already exists from a prior ship, **replace it wholesale** (it is derived,
  not hand-tuned). Use Edit on README.md.
- **Apply the invoke gaps** — for each `INVOKE_GAPS` line, add that mode/trigger to the
  existing `## How to invoke` (append a bullet; do **not** rewrite the section — it may hold
  a hand-tuned worked example). `none` → no change.
- **Never touch** `## What this skill does` / `## Intent` / `## When to use / When NOT to
  use` — those are the author's; the publisher only polishes their wording at Step 6's
  outcomes-first pass, never re-authors them here.
- The result feeds Step 6's existing install/sibling fill + the outcomes-first polish, which
  run after this (so the polish pass also smooths the newly-drafted sections).

## Canonical README section order (the augmented set)

1. `# <Skill Name>` · 2. `## What this skill does` (creator) · 3. `## Intent` (creator) ·
4. `## When to use / When NOT to use` (creator) · 5. `## How to invoke` (creator scaffold;
publisher keeps mode-complete) · **6. `## Features & modes` (publisher — this agent)** ·
**7. `## Structure` (publisher — this agent)** · 8. `## How to install` (publisher) ·
9. `## Sibling skills` (publisher) · 10. `## For developers` (creator).
