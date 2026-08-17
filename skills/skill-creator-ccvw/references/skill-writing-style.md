# Skill Writing Style Guide

How to structure, write, and disclose content within a CCVW skill. Read at first-draft time and again when a skill grows past the 500-line guideline.

---

## Progressive disclosure

Skills use a three-level loading system:

1. **Metadata** (name + description) — always in context (~100 words).
2. **SKILL.md body** — in context whenever skill triggers (<5000 tokens / ~500 lines ideal).
3. **Bundled resources** (`references/`, `scripts/`, `assets/`) — loaded as needed; scripts can execute without loading.

Word counts are approximate but the 500-line target is load-bearing — past that, comprehension and trigger latency suffer.

**Key patterns:**
- Keep SKILL.md under 500 lines. Approaching the limit → add a hierarchy layer with clear pointers about where the model goes next.
- Reference files cited clearly from SKILL.md with guidance on when to read them.
- Large reference files (>300 lines) include a table of contents.
- A skill shares the **system-wide context budget** with every other loaded skill — its frontmatter is always in context, and its body loads whenever it triggers. Lean SKILL.md isn't just about this skill's latency; a bloated skill taxes every session it's enabled in. Keep the always-loaded description tight and push detail into `references/`.

---

## Domain organization

When a skill supports multiple domains/frameworks, organize by variant:

```
cloud-deploy/
├── SKILL.md (workflow + selection)
└── references/
    ├── aws.md
    ├── gcp.md
    └── azure.md
```

Claude reads only the relevant reference file at runtime.

---

## Writing patterns

Prefer **imperative form** in instructions.

**Defining output formats**:

```markdown
## Report structure
ALWAYS use this exact template:
# [Title]
## Executive summary
## Key findings
## Recommendations
```

**Examples pattern** — useful to include examples:

```markdown
## Commit message format
**Example 1:**
Input: Added user authentication with JWT tokens
Output: feat(auth): implement JWT-based authentication
```

---

## Recommended SKILL.md body skeleton

A reliable starting shape for the body (adapt — not every skill needs every section). The scaffold step seeds this; replace bracketed placeholders with real content.

```markdown
## Instructions

### Step 1: [first major step]
[What to do.] Run `[exact command]` — Expected output: [what success looks like].

### Step 2: [next step]
...

## Examples

**Example — [common scenario]**
User says: "[realistic trigger]"
→ [the actions taken] → [the result]

## Troubleshooting

**[Symptom / error message]**
Cause: [why it happens] → Fix: [concrete recovery steps]
```

Pair every procedural step with an **"Expected output:"** (or "what success looks like") line. It turns a bare command into a checkpoint the executor can verify against — and it's exactly the kind of claim a later trace checks against reality, so making it explicit pays off twice.

---

## Choosing the framing: problem-first vs tool-first

Two ways a skill can be framed, and most lean one way:

- **Problem-first** — the user describes an outcome ("set up a project workspace") and the skill orchestrates the right calls in the right order. The user names the *what*; the skill owns the *how*.
- **Tool-first** — the user has a capability ("I have the Notion MCP connected") and the skill teaches the optimal workflow and best practices on top of it. The user has *access*; the skill supplies the *expertise*.

Knowing which framing fits sharpens both the description (problem-first skills trigger on outcome phrases; tool-first on capability/tool mentions) and which authoring pattern below you reach for.

---

## Authoring patterns

Reusable shapes for the SKILL.md body, drawn from patterns seen working across many skills. Pick the one matching the skill's category (`references/build-planning.md`) and adapt the skeleton.

### Pattern 1 — Sequential workflow orchestration
**Use when:** users need a multi-step process in a specific order.
**Skeleton:** numbered steps, each naming the action/tool call and its inputs; mark dependencies between steps (e.g. "uses the `id` from Step 1"); validate at each stage before advancing; **write or log that stage's output to durable storage (a file, a log, a tracked record — not just conversation state) before advancing to the next stage** — never a design where nothing is written until a single final report step; give rollback instructions for failures.
**Key techniques:** explicit step ordering · declared inter-step dependencies · per-stage validation · **incremental checkpointing (durable write/log after each stage, or after each unit within a stage for long stages)** · rollback on failure.

### Pattern 2 — Multi-MCP coordination
**Use when:** a workflow spans multiple services/servers.
**Skeleton:** group the work into clearly separated phases (one per service); pass data explicitly between phases (name which output feeds which input); validate before moving to the next phase; **persist each phase's output durably as it completes**, so a phase's work survives even if a later phase never runs; handle errors centrally rather than per-call.
**Key techniques:** clear phase separation · explicit data-passing between services · validate-before-advance · **incremental checkpointing per phase (durable write/log, not deferred to a final step)** · centralized error handling.

### Pattern 3 — Iterative refinement
**Use when:** output quality improves with iteration (drafts, reports, designs).
**Skeleton:** produce an initial draft → run an explicit quality check (ideally a `scripts/` validation script) → refine the flagged parts → re-check → **stop when a stated quality threshold is met.**
**Key techniques:** explicit quality criteria · iterative improvement · validation scripts · a clear stop condition (a loop with no termination is a defect — say when to stop).

### Pattern 4 — Context-aware tool selection
**Use when:** the same outcome needs different tools depending on context.
**Skeleton:** a decision step with explicit, checkable criteria (file size, type, destination) → the selected action → transparency to the user about *why* that choice was made; provide fallbacks when no criterion matches.
**Key techniques:** unambiguous decision criteria · fallback options · transparency about the choice.

### Pattern 5 — Domain-specific intelligence
**Use when:** the skill adds specialized knowledge beyond tool access (compliance, financial rules, medical conventions).
**Skeleton:** embed the expertise in the logic (not just "be careful"); enforce gating rules *before* the action they guard ("check compliance → then process"); document the embedded rules so a reader sees what knowledge is baked in; keep governance/ownership clear.
**Key techniques:** expertise embedded in logic · gating-before-action ordering · the embedded domain rules written down · clear governance. (Distinct from "Domain organization" below, which is about file *layout* for multi-domain skills; this pattern is about embedding *expertise*.)

### Pattern — Error handling / troubleshooting
**Use when:** always — every skill that calls tools or transforms data needs it.
**Skeleton:** a `## Troubleshooting` section pairing each likely failure with `Cause → Fix`; in the workflow itself, author recovery/fallback steps and validation gates at the points where things break. Worked shape for an MCP call:

```markdown
**"Connection refused" when calling the server**
Cause: MCP server not running or auth expired.
Fix: 1) verify the server is connected; 2) check API key / OAuth scopes;
     3) retry; if it still fails, tell the user it's an MCP-setup issue, not the skill.
```

**Key techniques:** name the recoverable cases (retry / fall back / ask) vs. abort cases · place validation gates before the steps that depend on them · prefer a bundled `scripts/` check over prose when the validation is deterministic (code is reliable; language interpretation isn't).

---

## Cross-cutting authoring guidance

Short rules that apply across all patterns:

- **Composability.** A skill runs alongside other loaded skills — never assume it's the only capability available. Scope the description to the skill's real domain so it doesn't grab generic triggers that collide with siblings, and prefer dispatching to a peer skill over duplicating its function.
- **Scope discipline.** One skill = one coherent capability. If the captured intent spans several unrelated jobs, split it into separate skills (or a related "pack") rather than one sprawling skill. The 500-line limit caps *length*, not *scope* — a skill can be short and still over-broad.
- **Document-layering (where a fact belongs + how to reference it).** Three homes, by what the reader needs: the **runtime contract + workflow** lives in SKILL.md/references (what the executor must DO); **intent** lives in README `## Intent` (WHY); **provenance / lineage** ("adapted from X", "this is the same as Y", "moved from Z") lives in HISTORY.md. The executing skill almost never needs to know it's "the same as" something else — it needs the *rule*, stated locally. So: (a) state a rule where it's used, don't make the executor chase a pointer to learn it; (b) when you must reference another artifact the executor actually reads at runtime, anchor to a **stable address** (file + named section, or a resolve-at-runtime path) — **never a foreign step number** ("see X's Step 6"), which silently rots the moment X renumbers; (c) keep "same as / moved from" notes in HISTORY, not in the runtime docs. (The tracer's executor direction flags a foreign step-number pin as a stale/unresolvable cross-reference.)
- **Prominence.** Put critical and order-dependent instructions near the top of the body; flag non-skippable constraints clearly (a brief "do this before that" beats burying it mid-list); repeat a load-bearing constraint at its point of use rather than relying on the reader to remember it from earlier. (Intentional repetition of a load-bearing instruction is *not* redundancy to trim.)
- **Reliability properties every skill should have.** Author the skill so it (a) gives the user next-step guidance at decision points rather than stalling, (b) embeds the best-practices/gotchas that prevent the common failure, and (c) states its output contract (what it produces, in what shape). These are what make a skill deliver consistent results instead of varying by how the request was phrased.
- **Anti-"laziness."** If you observe the model skipping steps or stopping short, add explicit encouragement to be thorough ("work through every item; quality over speed; don't skip the validation"). Note: such encouragement tends to land better in the *user prompt* than baked into SKILL.md — try it there first before hardcoding it.
- **Compaction recovery.** Claude Code compacts context automatically in long sessions — a skill with no recovery infrastructure silently loses its in-progress state and cannot resume. Two mechanisms, by skill complexity:
  - **Session-log marker (every multi-step skill):** At the start of each major round, phase, or iteration, append a step marker to the shared session log in the format `**[HH:MM:SS] SKILL:[name] RUN:[id] STEP:[name]**` (append to `~/.claude/session-logs/session-log-$(date +%Y-%m-%d).md`). This tells compact hooks which skill and step were active so they can build a targeted resume prompt. Non-blocking — if the write fails, continue.
  - **In-flight marker (complex multi-round workflows with a ledger):** For skills that run multi-round loops or multi-phase sequential workflows, pair every major-phase write with an atomic `in-flight:: <Runtime> <action>` marker in the ledger header. Step 1 of every invocation reads this marker and runs the matching recovery rule so a post-compaction resume picks up where it left off without user intervention. See `~/.claude/skills/skill-tracer/references/recovery-protocol.md` for the full pattern; for build-phase recovery (no ledger needed), see `references/build-planning.md` "Recovery across sessions."
- **Incremental checkpointing — never defer all output to a final report step (required for any multi-stage workflow/skill).** A design where "you see nothing until the final report is complete" loses ALL work the moment context runs out mid-process — and context exhaustion in a long-running workflow is a routine, near-guaranteed event, not an edge case. Every multi-stage workflow spec must name a durable write/log point after each stage (or after each unit within a stage, for stages that process many items) — a file write, an append to a ledger/log, a tracked record — so partial progress survives a restart even if the final stage never runs. This is distinct from the compaction-recovery markers above: those let the *skill* resume its own execution; this ensures the *user* has real, inspectable output accumulating as the workflow runs, not just at the end. When designing or reviewing a multi-stage workflow, treat "all output deferred to the last stage" as a structural defect to fix before the design ships, not a style preference to note and move past.

---

## Writing style

- Explain the *why* instead of stacking MUSTs.
- Use theory of mind; keep instructions general, not narrowly bound to specific examples.
- Draft, then re-read with fresh eyes and tighten.

---

## Principle of lack of surprise

Skills must not contain malware, exploit code, or anything that compromises security. The skill's behavior should match its stated intent — no covert side effects. Decline requests to build misleading skills or tools for unauthorized access / data exfiltration. Roleplay skills are fine.

---

## Test cases

After writing the skill draft, come up with 2–3 realistic test prompts — the kind of thing a real user would actually say. Share them with the user: "Here are a few test cases I'd like to try. Do these look right, or do you want to add more?" Then run them.

Save test cases to `evals/evals.json` (or to the centralized location per `<workspace>` resolution). Don't write expectations yet — draft them in the next step while runs are in progress.

```json
{
  "skill_name": "example-skill",
  "evals": [
    {
      "id": 0,
      "prompt": "the user's task prompt",
      "expected_output": "what success looks like",
      "expectations": []
    }
  ]
}
```
