---
name: skill-creator-ccvw
description: "Create new skills, improve and evaluate existing skills, and measure skill performance: the CCVW fork of skill-creator and the BUILD phase of build, trace, ship. Scaffolds SKILL.md, README, HISTORY and glossary, runs a marketplace pre-check, compares Claude with and without the skill on test prompts, and iterates, optionally looping until a pass finds nothing new (max 3 rounds). Also adapts or forks another skill with licence and attribution, keeps personal data out of shared skills, and tunes a skill's trigger description. Use when the user wants to create a skill, turn a workflow into a reusable skill, improve or upgrade a skill, keep improving a skill until nothing new turns up, plan skill improvements, run evals or benchmarks on a skill, fork or adapt someone's skill, or fix a skill that triggers badly. Do NOT use to find bugs in a finished skill (skill-tracer), to polish, package or publish one (skill-publisher), or to search for existing plugins (marketplace-discover)."
license: Apache-2.0
compatibility: Claude Code 2.0 or newer
metadata:
  tier: claude-users
  created: 2026-05-27T12:30
  created-by: Vaikri-costume
  parent-version: 1.3.0
  intended-audience: claude-users
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
  - Glob
  - Grep
  - Agent
  - Skill
---

<!-- Provenance, version, attribution chain, and changelog live in HISTORY.md (not this frontmatter).
     Human-facing intent + how-to-install + sibling skills live in README.md.
     This frontmatter holds only the runtime contract the executor agent loads at startup. -->


# Skill Creator

For creating new skills and iteratively improving them. Core loop: decide what the skill should do → write a draft → run claude-with-and-without-skill on test prompts → help the user evaluate qualitatively (via `eval-viewer/generate_review.py`) and quantitatively (drafted while runs are in flight) → rewrite based on feedback → repeat until satisfied → expand the test set at scale.

Figure out where the user is and jump in. "I want a skill for X" → walk the whole loop. Has a draft → go straight to eval/iterate. Wants to skip evals and vibe → do that. After the skill is done, optionally run the description-improver script to tune triggering.

Jargon calibration: users range from non-coders to engineers. "Evaluation"/"benchmark" usually OK; "JSON"/"assertion" only after the user shows they know them. When in doubt, define inline in one short clause.

---

## Portable mode and tiers

Every CCVW skill declares `metadata.tier`. The tier governs frontmatter rules, body content, and where eval/audit outputs live.

| Tier | Use for | Allowed | Forbidden |
|---|---|---|---|
| `personal` | your own setup, when you ask for this tier | hardcoded user paths, local MCPs, your Claude Code config | — |
| `claude-users` | finished skills shared with Claude Code AND Cowork users | Claude-Code + Cowork extensions (Agent, dynamic injection, argument substitution; body-level uses get advisory `claude-users (warning)` findings that do not block this tier, per `references/lint-details.md`), marketplace access | user-specific paths, assumed-local config |
| `model-agnostic` | non-Claude runtimes (Gemini CLI, Cursor, OpenCode, agentskills.io agents) | agentskills.io base spec only | Claude-Code extensions; storage must use runtime APIs |

Full per-tier rules, Claude-extension blocklist, and path-mapping in `references/portability-spec.md`.

`scripts/portability_lint.py` runs at scaffold and every tier transition. Tier-conditional findings appear only at `claude-users`/`model-agnostic` (the lint emits none at `personal`; rule in `references/lint-details.md`), and there the orchestrator proposes fixes and confirms before applying. Findings that block every tier, `personal` included, are the `ccvw_mandatory_missing` entries and those `tier_violations` whose `blocks_tier` begins with `all` (examples in `references/lint-details.md`). The tier-change rule is the "Hard rules" rule that begins "Change a tier".

---

## Personal settings (read from the profile, never hard-coded)

Nothing personal is written into this skill. Settings resolve in this order: environment variable, then the user-profile file, then a safe default. `python3 scripts/skill_config.py get <key>` prints one value; `all` prints every key.

| Key | Environment variable | Default |
|---|---|---|
| `eval_workspace` | `CCVW_EVAL_WORKSPACE` | `${XDG_DATA_HOME:-~/.claude}/skill-creator-evals-ledger` |
| `session_log_dir` | `CCVW_SESSION_LOG_DIR` | empty = session logging off (`off` also means off) |
| `scratch_dir` | `CCVW_SCRATCH_DIR` | empty = you create a fresh temporary directory, pass it as `--var scratch_dir=<dir>` to `render_prompt.py`, and remove it when done |
| `author_identity` | `CCVW_AUTHOR` | empty = ask once |
| `helper_model` | `CCVW_HELPER_MODEL` | `sonnet` |

The profile is a markdown file with bullets like ``- `helper_model`: sonnet`` (`--profile PATH`, else `$CCVW_USER_PROFILE`, else the first `config/user-profile.md` found walking up from the current directory). A missing profile or key is not an error. When `session_log_dir` is set, append the iteration-start line that `references/eval-run-procedure.md` "Step 1: Spawn each test case's runs (with-skill AND baseline) in the same turn" defines; otherwise write nothing.
## Hard rules

1. **Write each rule once, in one file.** Every other file points to it. Before adding text, grep for the rule; if it exists, link to it.
2. Dispatch every eval helper that has a template (with_skill, baseline, grader, analyst) through `scripts/render_prompt.py`; the blind-comparison comparator and Mode A analyzer have none and follow this rule by hand (`references/blind-comparison.md`). Every prompt starts "You are the worker, no subagents, cannot redelegate.", runs on the configured helper model (Sonnet by default, never Opus; how the dispatch sets it: `references/eval-run-procedure.md` Step 1 (Spawn each test case's runs)), and contains no names or personal details ("the user"). A fictional persona that the eval task text names (name, folders, other details) is context for the task: the worker never writes it into any file of the built skill and calls that person "the user". The one exception is an author identity the task names: it goes into every field that holds the author's own name (`author.primary` and the `fork-adapter` entry `name` in HISTORY.md, `created-by` in frontmatter, the copyright line this author adds to a Category A `LICENSE`) and nowhere else; where the task names none, the worker writes `AUTHOR-NOT-SET` in each of those fields, and the orchestrator afterwards replaces only the fields still holding that marker, from the profile's `author_identity`, leaving a task-named identity as written (the HISTORY.md bullet of "Write the three root files"). The configured `author_identity` never goes into a worker prompt (`scripts/render_prompt.py` refuses any non-path value holding it). The model part covers dispatched helper agents only; the `claude -p` calls of description optimisation run on the session's model (`references/description-optimization.md` Step 3).
3. Eval and scratch files go only in `<workspace>` or the scratch directory, never in the skill's own tree; the one exception is `<skill-path>/evals/evals.json`, the skill's own eval definitions, and the fixtures it points to. Delete only by literal absolute path, never through a shell variable.
4. Deterministic steps are scripts, not prose. If you find yourself re-deriving the same step in three runs, add a helper with a stated input-to-output contract and a test. Why: a script gives the same result every run and prose does not.
5. Run one eval to completion (the pilot) before dispatching the rest of a batch; fix what it shows first. Which iterations repeat the pilot: "The iteration loop". Why: one broken setup repeated across a batch wastes every run.
6. Never copy text from another skill without its licence's attribution; never copy from a candidate `marketplace-discover` marked as a red flag. Why: the licence is the condition on which the text was shared, and a red flag means the candidate's own safety or licence is in doubt.
7. Change a tier, publish, or install over `~/.claude/skills/` only on the user's explicit request, never as an automatic bump. Building does not install. Why: each of these changes who can use the skill, or overwrites a working copy, and cannot be quietly undone.
8. Report every gap and every skipped check. A baseline that fails the isolation check is discarded, never counted. Why: a silent skip makes a pass look stronger than it is, and a baseline that saw the skill measures nothing.
9. Nothing personal in a skill that is not `personal` tier: no names, paths, or identities; they come from the profile. The author attribution fields (`created-by` in frontmatter and the HISTORY.md author fields) are exempt: they carry the profile's `author_identity` (Step 3 — Author identity below). Any file a built skill writes outside its own workspace (run logs, caches) gets a configurable path and an off switch, and a user's request to hard-code a personal path is declined in writing when the skill is not `personal` tier (at `personal` it is honoured, per the tier table), while a request for a banned helper model (Opus; the rule that begins "Dispatch every eval helper") is declined in writing at every tier (`<workspace>/deviations.md`, or inside an eval run that run's `outputs/deviations.md`, or the final reply), not silently.

## Creating a skill

### Capture Intent

Start from the conversation if it already holds a workflow ("turn this into a skill"): extract tools, steps, corrections and formats first, then fill gaps. Identify the use-case category (Document & Asset Creation, Workflow Automation, MCP Enhancement, or "other"; `references/build-planning.md`). Ask:

1. **2 to 3 concrete use cases** (one is enough when the user has only one: proceed with it and note the gap in the final reply), each a `{name, trigger, ordered steps, end result}` quadruple. Mark the deterministic steps for scripting now so they land in `scripts/` in the first draft (test: same inputs always give the same correct output).
2. **When should it trigger?** The phrases and contexts, drawn from the use cases.
3. **Expected output format.**
4. **Why this skill: what does it optimise for and trade off?** This becomes README `## Intent`, which skill-tracer reads. A vague answer weakens every later trace.
5. **Standing preferences and domain expertise** to embed (process, preferences, expertise are the three things a skill teaches). More than about 10 rules go to `references/<domain>.md`.
6. **Test cases?** Objective outputs benefit; subjective ones usually do not.
7. **Audience.** Default `claude-users`; `personal` or `model-agnostic` only on request. `intended-audience` and `tier` take the same value.

Capture the answers now and write them when the files are scaffolded (README gets Q1, Q2, Q4; frontmatter gets Q7; the body and `references/` get Q3 and Q5). Full text of Q1, Q5 and the answer-to-file mapping: `references/intent-and-decide-details.md`.

### Interview and Research

Proactively ask questions about edge cases, input/output formats, example files, success criteria, and dependencies. Wait to write test prompts until you've got this part ironed out.

Four scoping questions sharpen the build before drafting (they refine the Capture-Intent answers into buildable specifics):
1. **What does the user ultimately want to accomplish?** (the outcome behind the use cases)
2. **What multi-step workflows does that require?** (the ordered steps each use case decomposes into)
3. **Which tools are needed — built-in or MCP?** This directly drives the `allowed-tools` frontmatter: name the specific tools (`Bash`, `Write`, `Edit`, `Skill`, specific `mcp__*` servers) so the conservative default (`["Read"]`) is widened only as far as the skill actually needs.
4. **What domain knowledge or best practices should be embedded?** (the Q5 domain-expertise answer, made concrete — the rules, gotchas, and conventions to bake in).

Skim 1–2 existing skills as structural references before drafting — either similar skills surfaced by the marketplace check below, or the example skills installed by marketplace (at `~/.claude/plugins/marketplaces/claude-plugins-official/plugins/` if the marketplace plugin is installed). Seeing a real skill's shape (frontmatter, body sections, references layout) produces a better first draft than starting from a blank file.

Check available MCPs - if useful for research (searching docs, finding similar skills, looking up best practices), research in parallel via subagents if available, otherwise inline. Come prepared with context to reduce burden on the user.

If this is an MCP-enhancement skill (Category 3), read `references/mcp-enhancement-skills.md` — it covers what to elicit (happy-path call sequence, failure/empty-result handling, rate/ordering constraints, tool gotchas) and how to author the call-sequencing + error handling that make such a skill reliable.

### Decide: install, improve, adapt, or build

**Step 1: marketplace check** (mandatory before a new build). Invoke `marketplace-discover` with the captured intent as a prose argument (domain, key verbs, tool constraints, end result), unless the user says they already ran the check (then use their reported outcome). If it is not installed, errors, or finds nothing, go to Step 2 on Path 4. It ends with install, adapt or build. Detail and the timestamp capture rule: `references/intent-and-decide-details.md`.

- **Path 1, install.** A strong match the user chooses to install: run `marketplace-discover`'s install step and stop. If the user neither accepts nor declines, answer the question and re-present the choice.
- **Path 2, improve.** The user wants to evolve an installed skill: switch to `references/improve-existing-skill.md`, which runs to its own end (including its trace and ship handoff). The eval machinery below is shared infrastructure there.
- **Path 3, adapt.** The user wants to take part of someone else's skill or pattern (from `marketplace-discover`'s adapt answer, or named by the user). Inputs: the candidate, its licence, what is worth taking. Steps: (1) read the candidate's licence file; if it is unknown or restrictive (the "Licence classes" paragraph of `references/attribution-spec.md` "License preservation"), stop and ask the user; (2) if the candidate was marked a red flag, take nothing; (3) choose the attribution category: **B** when a pattern is reimplemented (record the source in `inspirations[]`), **C** when only the idea is borrowed (record it as a see-also), **A** when the result meets the Category A thresholds of `references/attribution-spec.md` (keep the original `LICENSE` and the `author.history[]` chain); when unsure choose the more-attributing one; (4) copy no text unless the licence allows it, and then keep the notice it requires; (5) record the source URL, licence and what changed in HISTORY.md (where, by category: `references/history-template.md` Lineage notes); (6) continue as a build (Path 4) with the category already decided, skipping Step 2 — Attribution category below.
- **Path 4, build.** Everything else. A weak match pauses for the user's go-ahead before building; a declined strong match, no results and an error need none (rule: the details file, Decide Step 1).

Capture the marketplace timestamp now (the user's stated one when they reported the check; none when no check ran) and write it to HISTORY.md at scaffold time (`checked-marketplace:` line; rule in the details file).

**Step 2 — Attribution category** (mandatory for Path 4; Path 3 chooses its category in its own step 3, and Path 2 asks it only in the case the next paragraph names). Ask the user which of four categories applies:

- **A. Direct fork** — structurally derived from an existing skill
- **B. Derivative work** — uses a named pattern (cold-parallel dispatch, ralph-loop, etc.) reimplemented
- **C. Idea inspiration** — influenced by another skill, no structural overlap
- **D. Independent design** — no recognizable lift

The category drives the `HISTORY.md` attribution fields (`category`, `author.history[]`, `inspirations[]`) per `references/attribution-spec.md` (full thresholds, schemas, license-preservation rules, worked examples) and `references/history-template.md` (the HISTORY.md format). When in doubt between adjacent categories (A↔B, B↔C, C↔D — see `references/attribution-spec.md` "How to decide between categories — the squishy lines"), choose the more-attributing one. (Path 2 takes the category from the installed skill's HISTORY.md and comes back to this question only when that file is missing; the rule is in `references/improve-existing-skill.md`.)

**Step 3 — Author identity** (mandatory). Determine the user's actual identity — GitHub username or preferred attribution name — to become `HISTORY.md`'s `author.primary`. Never the literal placeholder `user`. When `gh` is installed and authenticated, `attribution_lint.py` compares `author.primary` with `gh api user -q .login` and a mismatch is a blocking violation (`author-identity-mismatch`), so prefer the GitHub username (`references/attribution-spec.md` "Author identity values"). When the identity the user states differs from that login, tell the user the lint will flag it and let them choose; never replace their stated identity silently, and if they keep it, report the open violation in the final reply (the "Report every gap" hard rule); this is the one blocking violation that may remain at handoff. Read it from the profile (`author_identity`, see "Personal settings") when set; otherwise ask once and hold it as a visible line in your response. Steps 1–3 are a decision phase — capture this value now (same capture-now/write-later pattern); write it to HISTORY.md when that file is scaffolded below.

**Attribution answers feed HISTORY.md, not SKILL.md frontmatter.** The category + author + inspirations land in `HISTORY.md`'s YAML frontmatter (top-level fields). SKILL.md frontmatter stays lean (runtime contract only). See `references/history-template.md`.

Once Steps 1-3 settle, proceed to "### Write the three root files".

### Write the three root files

Every CCVW skill ships three root markdown files (SKILL.md + README.md + HISTORY.md), three directories (scripts/ + references/ + assets/), and a glossary. The scaffold creates them with sensible defaults the user reviews and edits. Full structure: `references/skill-structure-spec.md`.

**Where the folder goes.** Create the new skill's folder at the location the user names, else at `<working directory>/<skill-name>/` (tell the user they may name another location). That folder is `<skill-path>` in every lint, eval and package command below. Never create it under `~/.claude/skills/`: installing is the "Hard rules" rule that begins "Change a tier".

**SKILL.md** — the runtime workflow. Frontmatter is the lean runtime contract:
- **name** — skill identifier (1–64 lowercase alphanumeric + hyphens).
- **description** — when to trigger + what it does. Primary triggering mechanism; all "when to use" lives here. Lean pushy — Claude under-triggers.
- **license**, **compatibility**, **metadata** (required keys: `tier`, `created`, `created-by`, `parent-version`, `intended-audience` — runtime-relevant only), **allowed-tools**. See `references/skill-structure-spec.md`. Note: `version`, `author`, `inspirations`, `category`, `checked-marketplace` do NOT go here — they live in HISTORY.md.
- Body: the workflow instructions per `references/skill-writing-style.md` — pick the authoring pattern matching the skill's category, follow the body skeleton, and give the skill the reliability properties every skill should have (next-step guidance, embedded best-practices, a stated output contract). Keep it composable and single-scope (see the cross-cutting guidance there).

**README.md** — human intent (mandatory). Scaffold from `references/readme-template.md`. Populate `## What this skill does` (Capture-Intent Q1), `## Intent` (Q4 — the load-bearing design-intent section tracer reads), `## When to use / When NOT to use` (Q1 triggers and Q4 trade-offs, per the mapping above), `## How to invoke` (Q2 triggers). Leave `## How to install` and `## Sibling skills` as placeholders — skill-publisher fills them at ship time. The remaining template sections (`# <Skill Name>` title and `## For developers`) carry the template's fixed boilerplate — keep them from `references/readme-template.md` as-is; this populate/placeholder split covers only the interview-driven and publisher-filled sections, not those two.

**HISTORY.md** — provenance + changelog (mandatory). Scaffold from `references/history-template.md`. YAML frontmatter: `version: "1.0.0"`, `category` (from attribution Step 2), `parent-version` (null for fresh), `author` (primary + history chain for Category A), `inspirations` (for Category B). Markdown body: initial changelog entry (`### 1.0.0 — <date>` + "Initial scaffold") + lineage notes. When a dispatched eval worker scaffolds the skill, it fills the author fields as the "Hard rules" rule that begins "Dispatch every eval helper" says (a task-named author identity, else the marker `AUTHOR-NOT-SET`, never "the user", which `scripts/portability_lint.py` would match as the author name in ordinary prose); the orchestrator replaces the marker afterwards as that rule says.

**Required directories** (`.gitkeep` if empty): `scripts/`, `references/`, `assets/`. **Note: `evals/` is NOT scaffolded automatically** (it is created lazily when you first write evals.json, to avoid an empty directory in skills that do not reach the eval phase) — the "Test cases" step below creates it when it writes `evals.json`. Into `scripts/` go the deterministic steps marked back in Capture-Intent ("mark the DETERMINISTIC ones for scripting") — ship them as bundled helpers with a stated input→output contract in this first draft, rather than leaving them as prose each eval run re-improvises. If re-entering after compaction and the checklist is unavailable, check the task tree plan first; if absent there too, ask the user which steps they intended to script before proceeding.

**Required reference file**: `references/glossary.md` — scaffolded from `references/glossary-template.md` (when copying, perform the template's own substitutions: replace `<SKILL-NAME>` in the heading, delete the template's "How to use this template" and "When to update this glossary" sections and the `<example-term>` placeholder row, and add the skill's actual terms — do NOT ship the template's instructional scaffolding verbatim, because a shipped glossary still carrying the how-to text or the `<example-term>` row reads as unfinished and gets flagged by skill-tracer's cold read), inherits CCVW shared vocab from `references/ccvw-glossary.md`.

**LICENSE file at skill root**: required for Category A forks. See `references/attribution-spec.md`.

### Scaffold-time lint checks

Run these three lints the moment the scaffold exists, before the first eval, from this skill's root, in this order:

```bash
python3 scripts/quick_validate.py   <skill-path>   # frontmatter gate; plain-text output, branch on the exit code only
python3 scripts/portability_lint.py <skill-path>   # structure + tier + name checks; JSON; reads metadata.tier
python3 scripts/attribution_lint.py <skill-path>   # HISTORY.md attribution; JSON; exit 1 on a blocking violation or a missing HISTORY.md (lint-details.md)
```

Exit codes, JSON keys, what blocks which tier, the fix order and the fix-before-handoff rule (with its author-identity exception, named by Step 3 — Author identity): `references/lint-details.md`. These scripts are this skill's own copies; skill-publisher carries separate ones.

### Iterate-quality checks (opt-in)

During the iterate loop, run the checks in `references/iterate-quality-checks.md` (two lists: Efficiency 1-14 and Accessibility 1-14) against the current draft, but only when the user explicitly opts in (a `--with-iterate-quality` token in `$ARGUMENTS`, or a plain request for readability or efficiency feedback). Default off. The checks are advisories, not bugs; skill-publisher's final quality gate catches them at ship time otherwise, and the user decides which to act on.

### Test cases

Unless the user explicitly chooses to skip evals (Capture Intent Q6: record that choice in `<workspace>/deviations.md` or the final reply, report it as a skipped check, draft no prompts, create no `evals/`, and run none of the steps here or in "Running and evaluating test cases"), after drafting come up with 2–3 realistic test prompts. Share with the user: "Here are a few test cases I'd like to try. Do these look right, or do you want to add more?" Then run them.

Save to `<skill-path>/evals/evals.json` inside the skill's own directory (only run outputs go to `<workspace>`). It is the skill's eval definition file, versioned with the skill; `scripts/package_skill.py` leaves `evals/` out of the packaged archive. Run `mkdir -p <skill-path>/evals` first (`evals/` is created lazily; the command is idempotent, so it is safe even if the directory already exists from a prior recovered build). Do not write expectations yet; draft them while the runs are in flight, and if the build or session ends before any run is dispatched, write them into `evals.json` before handing off. Shapes: `references/schemas.md` (`{skill_name, evals: [{id, prompt, expectations, ...}]}`; the orchestrator selects an entry by `id` and passes its `expectations` to the grader). Structure and the lack-of-surprise rule: `references/skill-writing-style.md`.

## Running and evaluating test cases

Unless the user chose to skip evals (the guard at the start of "Test cases", which governs this section too), every build and every improve run compares Claude **with the skill** against Claude **without it** (create) or against the old version (improve). Both come from the helpers below, not from prose. Full gotchas: `references/eval-run-procedure.md`, which also holds the rough-benchmarks rule for pass rates and timings and the "Tool/MCP-dependent skills" test rule for a skill that makes MCP or tool calls.

`<workspace>` is `python3 scripts/skill_config.py get eval_workspace` plus `/<skill-name>`. Where eval artifacts may be written is set by the hard rule that begins "Eval and scratch files".

1. **Build and run the pilot, then the rest.** `scripts/eval_workspace.py` with `--only 0` creates the directories and `eval_metadata.json` for eval 0 only (it only makes folders). Dispatch eval 0's two runs, grade them, and check the result is sensible; then build the remaining ids and dispatch them (which iterations run a pilot: "The iteration loop"). The full command, the `--configs` value and the `--only` form for the rest: `references/eval-run-procedure.md` Step 1 (Spawn each test case's runs). Expected: eval 0 graded and judged sensible before the rest are dispatched. Record which eval ran first as an orchestrator note in the benchmark notes (how: `references/eval-run-procedure.md` Step 4 (Grade, aggregate, and launch the viewer), sub-step "Do an analyst pass").
2. **Render and dispatch both runs in the same turn** (same-turn dispatch keeps the runs independent): `python3 scripts/render_prompt.py --kind with_skill|baseline --var key=value ...` (the `--var` names each kind needs are listed in `references/eval-run-procedure.md` Step 1 (Spawn each test case's runs)). Expected: each run directory holds a `transcript.md`. The templates in `references/dispatch-prompts/` carry the framing line, helper model, no-names rule, the `## Eval Prompt` transcript heading and, for the baseline, the isolation constraints.
3. **Check every baseline:** `python3 scripts/check_isolation.py --transcript <baseline run>/transcript.md --skill-name <name> --run-dir <baseline run>`. Exit 1 or 2 means discard and re-dispatch (what each code means, and the `--allow` values an improve-mode baseline's snapshot and any input folder need: `references/eval-run-procedure.md` Step 1 (Spawn each test case's runs)); three failures on one run stop the loop and you ask the user. Isolation is by instruction, not sandbox; a clean check is harm reduction, not proof.
4. **Record timing** per finished run: `python3 scripts/write_timing.py --run-dir <run> --total-tokens T --duration-ms D`. Expected: a timing file in the run directory, read later by the aggregate.
5. **Draft assertions while runs are in flight**, objective and descriptively named, into `evals.json` `expectations`. Each iteration after the first adds at least one assertion the current version is likely to fail, so an iteration can fail honestly; in a loop-until-dry every round, round 1 included, adds one, and that assertion is reported but is not a finding (see "Loop-until-dry (opt-in)"). Expected: `evals.json` holds an `expectations` list for every eval before grading starts.
6. **Grade** one grader per run in the same turn (`--kind grader`), then `python -m scripts.aggregate_benchmark <workspace>/iteration-N --skill-name <name> --skill-path <path> --model <model-id>` and scan its output for `Warning:` lines. Analyst pass: `--kind analyst`, then `python3 scripts/merge_notes.py --iteration-dir <workspace>/iteration-N`. Write `recommendations.md` per `references/recommendations-template.md`.
7. **Launch the viewer** (`eval-viewer/generate_review.py`, `--static` when headless; never hand-write HTML) and tell the user what it shows (`references/viewer-ui.md`). Expected: the viewer opens (or a standalone file is written) with every run listed and the benchmark tab filled. When they say they are done, read `feedback.json` (server mode) or ask for the downloaded file (static mode), then stop the viewer by its recorded PID.

## Improving the skill

### How to think about improvements

1. **Generalize from the feedback.** Skills get used across many prompts, not just the test set. A skill that only handles the test examples is useless. If an issue is stubborn, try a different metaphor or working pattern instead of adding overfitty MUSTs.
2. **Keep the prompt lean.** Remove instructions that aren't pulling their weight. Read the transcripts (not just final outputs) — if the skill is making the model waste time, cut the parts causing that.
3. **Explain the why.** Direct imperatives + reasoning beat rote ALWAYS/NEVER. If you find yourself in all-caps or rigid structures, reframe and explain instead — the model has good theory of mind and uses it.
4. **Look for repeated work across test cases.** If multiple subagents independently wrote similar helper scripts, bundle the script in `scripts/` and tell the skill to use it. Saves every future invocation from reinventing the wheel.

Your thinking time isn't the blocker — draft a revision, re-read with fresh eyes, improve.

### The iteration loop

1. Apply the improvements. 2. Rerun all tests into `iteration-<N+1>/`, baseline included, dispatched in the same turn. The pilot (the "Hard rules" rule that begins "Run one eval") applies to the first iteration of a workspace or of an improve cycle and to any iteration that changes the eval set or the dispatch setup; a later iteration that reruns an unchanged eval set builds every id at once and dispatches all its runs in the same turn. In create mode the baseline is a fresh `without_skill` run each iteration, in improve mode `old_skill` against the cycle's snapshot (taken once, at `references/improve-existing-skill.md` Step 3 (Draft changes preserving intent); every iteration's baseline only reads it). 3. Run the full grade, aggregate, analyst and recommendations steps, then launch the viewer with `--previous-workspace <workspace>/iteration-<N>`. 4. Wait for the user, read feedback, repeat.

Stop when the user is happy, all feedback is empty, or you are not making meaningful progress.

### Loop-until-dry (opt-in)

When the user asks to "keep going until it finds nothing", evaluate and improve repeats until a whole pass finds nothing new, with a cap of **3 rounds** and an earlier stop on a clean pass.

Each round:
1. Run the evals, then grade, aggregate and write recommendations, launch the viewer and wait for the user, all as in "The iteration loop"; "that run" below means this round's runs. Every round adds its likely-to-fail assertion (draft assertions step of "Running and evaluating test cases"). That designated assertion's result is reported with the round but is not a finding and never blocks `clean_pass`.
2. List the findings as `{text, where}`: each failed assertion in the grading.json of a graded run of the version being improved (the `with_skill` or `new_skill` runs, leaving out the round's designated likely-to-fail assertion; the baseline runs `without_skill` and `old_skill` fail by design and never count), and each recommendation in recommendations.md that names a concrete defect or failure of the version under test (a "failed at" item, or a recommended change that fixes an observed failure) and that the user has not dismissed (the user's overall feedback for the iteration, in feedback.json or in chat, says so). Optional enhancements and analyst notes are context, not findings. A round with none of these is the round that reported nothing.
3. Record them: `python3 scripts/loop_ledger.py record --ledger <workspace>/ledger-<k>.json --round <n> --findings <file>`. For a round that reported nothing, write an empty JSON array (two brackets) to the findings file and record that file, since `record` requires `--findings`. A finding's id hashes its `where` and `text` wording, so a finding that persists keeps the same wording in every round (or carries an id field of your choosing); a re-worded one is a new finding.
4. Fix them, then `resolve` on the same ledger with `--round <n> --ids a,b`. After a `no_progress` stop, do not run `resolve` (it empties the open set, so `decide` could then no longer show the stop): stop the loop, report the still-open findings in the final report, and ask the user whether to fix them, since the same findings came back in two rounds.

Ledger files: each loop has its own ledger. Start a new one, whose `<k>` is one more than the highest `ledger-*.json` number in `<workspace>` (1 when there is none), when `<workspace>` holds no ledger, when the highest-numbered one is finished, or when the user asks for a fresh loop; otherwise keep recording into the highest-numbered one. So a loop resumed after compaction continues its own rounds and cap, and a second loop on the same skill starts again at round 1. Every `loop_ledger.py` command writes the ledger file, so run `decide` only on a ledger file that exists; on a missing path it would create an empty one.

Finished test, for a resumed executor: run `python3 scripts/loop_ledger.py decide --ledger <highest-numbered ledger file>`, which prints stop, reason and the open and resolved id lists. The ledger is finished when it prints stop true and the reason is `clean_pass` or `no_progress` (a `clean_pass` round reported nothing, so it has no fixes to do). For `cap`, it is finished only when the open list is empty (every recorded finding, the last round's included, is resolved); a `cap` printed by `record` still leaves that round's fixes to do. If that cannot be told, ask the user. Otherwise it is not finished, and you continue it.

Decisions: the one `record` prints for the round just recorded governs whether another round starts; the one `resolve` prints shows the state after your fixes and never overrides a stop, so a stop printed by `record` (such as `cap` once 3 rounds are recorded) still lets you fix and resolve that round's findings first (except after `no_progress`, which round step 4 handles). The ledger gives each finding a stable id, marks a resolved finding that comes back as **regressed**, and prints the decision after each command. Stop reasons are `clean_pass` (the round reported nothing; findings left open from earlier rounds do not block it), `cap` (the ledger holds 3 rounds, counted by rounds recorded, not by the `--round` value, so a ledger numbered from 1 stops after round 3) or `no_progress` (two rounds with the same non-empty open set, the later one reporting nothing new or regressed). Write the final report with the `reason` that `record` printed for the last round recorded, quoted verbatim (never re-labelled by judgement), and what is still open.

### Pre-handoff self-check

Run the three lints again in the order and under the fix rules of "Scaffold-time lint checks", then check: the description says what it does and when; the name is kebab-case and matches the folder; multi-stage workflows write a durable log point before advancing; examples are present; every cited `references/` file exists (`grep -Eo 'references/[a-z0-9._-]+\.md' <skill-path>/SKILL.md` against `ls`, ignoring files cited as another skill's); SKILL.md is 500 lines or fewer; `python3 -m unittest discover -s tests` passes for any skill that ships tests. **One-line self-check before you output:** "Does every rule I wrote here already live nowhere else, and does nothing personal remain?" If not, fix before handing off.

### Suggest the next phase: trace, then ship

When the loop exits, say: *"Converged. Next: `/skill-tracer <skill-name>`, a three-tier cascade (prepass, minor-bugs, code-review) run for up to 5 cycles until a cycle finds nothing new. Then `/skill-publisher <skill-name>`, which polishes it, runs the portability and tier checks, and can open a PR."* Skill-tracer is correctness-only; do not suggest `--portable`. Skip the trace offer when a trace has just run and come back clean (as at the end of Path 2): offer only the publish step.

## Build planning across iterations

For multi-iteration builds keep a task tree and a plan so a build can resume after compaction; the rules and the recovery steps are in `references/build-planning.md`. On re-entry read the plan and task tree first; the `in_progress` subtask is the resume point.

## Advanced: blind comparison

Optional and rarely needed: an independent comparator judges two outputs without knowing which is which. Procedure, tie handling and the analyzer's two modes: `references/blind-comparison.md`.

## Description optimisation

After creating or improving a skill, offer to tune its description with 16 to 20 trigger queries (8 to 10 should-trigger, 8 to 10 near-miss should-not), the review page, `scripts/validate_eval_set.py`, and `python -m scripts.run_loop`. Apply `best_description` only when `exit_reason` begins with `all_passed` or `max_iterations`. Full procedure, exit handling and triggering signals: `references/description-optimization.md`.

## Package and present

Only when a `present_files` tool exists: `python -m scripts.package_skill <path> <output-dir>` (the output directory keeps the `.skill` file out of any skill's tree). This is a local-delivery convenience; sharing or releasing is skill-publisher's job. Details: `references/package-and-present.md`.

## Runtime adaptations

Claude.ai (no subagents) and Cowork (no display) change test execution, viewer mode, feedback capture and packaging. Read `references/runtime-adaptations.md` at the start of any non-default-runtime session.

## Evidence for each technique

| Technique | Rating | Basis |
|---|---|---|
| With-skill versus without-skill comparison | measured | produced by the helpers; each build reports per-iteration pass counts |
| Baseline isolation by instruction plus transcript grep | convention | self-reported paths; the grep catches leaks it can see, not hidden ones |
| Deterministic steps as tested scripts | measured | unit tests in `tests/` |
| Loop-until-dry with cap 3 | convention | agreed rule; stop reasons are logged per run |
| Blind comparison | reported | upstream skill-creator technique; not re-measured here |
| Description optimisation with held-out split | measured | `run_loop` reports train and test scores |

## Worked example (synthetic)

User: "Make a skill that turns meeting notes into an action list." Capture: one use case (the user had only one; the gap is noted; trigger "action items from these notes", steps: extract, dedupe, assign, end: a checklist). Deterministic step: dedupe by normalised text, so it becomes a bundled dedupe script in the new skill's own scripts folder (not a file of this skill). Marketplace check finds a weak match, so the user is told and, once they agree, Path 4 begins; category D. Scaffold, run the three lints, write two evals, pilot eval 0 with the helpers, then run the rest. With-skill passes 4 of 5 assertions (it misses the owner field), without-skill 2 of 5 (it misses the duplicate item, the owner field and the checklist format). Fix the owner-field instruction and add one assertion the new version might fail, iteration 2 passes, hand off to the tracer.

## Known limitations

- Baseline isolation is instruction-based; a determined baseline can read the skill, and nothing records its tool calls except its own report.
- The helper scripts assume Python 3 and a shell; Claude.ai without code execution falls back to the inline recipes in `references/eval-run-procedure.md`.
- Grading is by a model on a model's output; rounds share a blind spot if the assertions are weak. The grader brief (`agents/grader.md`) asks the grader to critique the assertions for this reason, and the orchestrator carries each critique into recommendations.md (`references/eval-run-procedure.md` Step 4 (Grade, aggregate, and launch the viewer), sub-step "Author the recommendations payload").
- Loop-until-dry cannot detect a finding it never produces; a clean pass means nothing new was found, not that nothing is wrong.
- Upstream skill-creator is checked at the dates recorded in HISTORY.md, not live.
- A description-optimisation trigger score can count consults of an installed copy of the skill under the same name; when it is clean: `references/description-optimization.md` Step 3.

## Examples

**"I want a skill that summarises my meeting notes"** -> capture intent (tier defaults to `claude-users`) -> scaffold -> run the three lints -> pilot one eval. Output: a skill folder that passes all three lints (no blocking finding: `quick_validate` prints Skill is valid, `attribution_lint` exits 0, `portability_lint` has no `ccvw_mandatory_missing` entry and no blocking `tier_violations` finding for the chosen tier, where a `claude-users (warning)` finding and advisory-only results do not count and the array alone cannot show this; `references/lint-details.md`), with nothing written into it by eval runs.

**"Run the evals on my skill"** -> pilot, then dispatch with-skill and baseline runs in the same turn -> isolation check -> grade -> aggregate -> viewer. Output: an `iteration-<N>/` workspace with `benchmark.json`, per-run `grading.json` and a viewer URL (or static HTML path).

**"Adapt the useful part of that marketplace skill"** -> read its licence, choose category B or C, record the source, build. Output: a new skill whose HISTORY.md names the source and licence and contains none of its text unless the licence allowed it.

**"Make this skill trigger better"** -> generate trigger queries -> review -> `run_loop.py` -> apply `best_description`.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Description optimisation reports 0% recall on every query | The `claude` CLI or credentials were unusable from the subprocess | `run_eval.py` runs a pre-flight check and names the real error; fix it and re-run |
| Benchmark delta has the wrong sign | Config directories lacked the recognised names | Use `with_skill`/`new_skill` and `without_skill`/`old_skill` |
| `check_isolation.py` exits 1 or 2 | The baseline touched the skill or has no `## Isolation Check` section (1), or wrote no transcript (2) | Discard the run, re-dispatch, stop at the 3-failure cap |
| `render_prompt.py` refuses | A placeholder has no value, a non-path value (such as the task) holds a forbidden term (the configured author identity, plus any --forbid term; see `references/eval-run-procedure.md` Step 1 (Spawn each test case's runs)), or the model is Opus | Supply the value, neutralise the text ("the user"; the configured author identity never goes in, per the rule that begins "Dispatch every eval helper"), use Sonnet; path values are not checked for forbidden terms (`scripts/render_prompt.py` docstring) |
| Viewer URL never appears | The viewer process failed to start (for example a Python error); a taken port does not cause this, the viewer frees or replaces it (`references/eval-run-procedure.md`) | Read `viewer.log`; use `--static` when headless |
| A lint exits 1 and prints JSON | A structural, tier or attribution violation | Read `violations` / `tier_violations`, fix blocking items, re-run |

## References

| Path | Purpose | When to read |
|---|---|---|
| `agents/grader.md`, `agents/comparator.md`, `agents/analyzer.md` | Subagent briefs | grading; blind comparison; analyst pass |
| `references/eval-run-procedure.md` | Full eval Steps 1 to 5 and gotchas | running evals |
| `references/dispatch-prompts/*.txt` | Worker prompt templates (rendered by `scripts/render_prompt.py`) | never by hand |
| `references/description-optimization.md` | Trigger-query loop and triggering signals | tuning a description |
| `references/lint-details.md` | Lint exit codes and JSON keys | lint output is unclear |
| `references/intent-and-decide-details.md` | Long-form Capture Intent and marketplace rules | scaffolding; Decide |
| `references/blind-comparison.md`, `references/package-and-present.md` | Optional procedures | when needed |
| `references/schemas.md` | JSON shapes for evals, grading, benchmark | writing JSON by hand |
| `references/portability-spec.md`, `references/attribution-spec.md`, `references/skill-structure-spec.md` | Tier, attribution and structure rules | scaffold; tier changes; Paths 3 and 4 |
| `references/skill-writing-style.md`, `references/build-planning.md`, `references/mcp-enhancement-skills.md` | Authoring guidance | first draft |
| `references/improve-existing-skill.md`, `references/runtime-adaptations.md`, `references/iterate-quality-checks.md` | Path 2; non-default runtimes; opt-in checks | as named |
| `references/readme-template.md`, `references/history-template.md`, `references/recommendations-template.md`, `references/glossary*.md`, `references/ccvw-glossary.md`, `references/viewer-ui.md` | Templates and vocabulary | scaffold; per-iteration payload |
| `scripts/*.py`, `tests/` | Helpers and lints; their input-to-output contracts are in each file's docstring | run, do not re-read |

Standard section order for any skill this creates: README (template order), HISTORY, glossary, and in SKILL.md: Hard rules, workflow sections, Known limitations, Examples, Troubleshooting, References (the file table first, any see-also entries after it), so skill-tracer and skill-publisher can find each.

Peer skills: `marketplace-discover` (Decide Step 1), `skill-tracer` (bug-finding), `skill-publisher` (polish, tier checks, PR). skill-publisher's Word/Spirit audit reads this file (SKILL.md) as its reference standard, and falls back to upstream skill-creator, then to Anthropic's `skill-development` guidance, only when this skill is not installed.

If you have a task list, add the eval-and-iterate steps; in Cowork add "Create evals JSON and run `eval-viewer/generate_review.py` so the human can review test cases", since Cowork tends to skip it.
