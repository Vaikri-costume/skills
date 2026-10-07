---
version: "3.6.0"
category: B
parent-version: "2.2.0"
published-to:
  repo: "https://github.com/Vaikri-costume/skills"
  path: "skills/skill-tracer"
author:
  primary: "Vaikri-costume"
inspirations:
  - skill: "deep-research"
    by: "Anthropic"
    pattern: "adversarial-verify — cold-parallel independent agents commit to findings before reconciliation. skill-tracer's cold-parallel code-review dispatch (independent cold agents whose findings are unioned before clustering) is the same shape; named retrospectively."
  - skill: "pr-review-toolkit"
    by: "Anthropic"
    pattern: "adversarial-verify sibling — independent agents committing before reconciliation, applied to PR review. Cited in invariant 1's cold-read rationale for code-review agents."
  - skill: "ralph-loop"
    by: "community"
    pattern: "inline-with-cold-child-dispatch loop shape. The cascade round loop (prepass re-enters until clean, then code-review; any fix re-enters at prepass) is the convergence-bounded specialization of this shape."
  - skill: "code-review"
    by: "Anthropic (claude-plugins-official marketplace)"
    pattern: "derivative work — skill-tracer's code-review tier dispatches cold reviewers across five lenses (fidelity / executor / logic / integrity / design), adapting code-review's multi-angle methodology for the cascade's second tier. Earlier versions (2.3.0–2.4.2) baked code-review's angles as nine native lens files; 3.0.0 rebuilt them as five cascade lenses in a deterministic cold-dispatch tier. (3.0.0 to 3.0.x also borrowed code-review's confidence-scored adjudication step for a minor-bugs tier; 3.1.0-trim retired that tier.) This entry credits the continued structural correspondence. Homepage: https://github.com/anthropics/claude-plugins-public/tree/main/plugins/code-review"
---

# History — skill-tracer

## Changelog

### 3.6.0 — 2026-10-06
Major upgrade from the published 2.2.0: the 3.x line replaces the three-agent loop with a 2-tier cascade (prepass detectors, then two cold reviewers over five lenses), a post-fix gate and closure blocks. Intermediate 3.0 to 3.5 builds were never published; their entries below are kept for provenance.
Built from 3.5.0-trimplus-v3 against the v3 self-run (not converged: 30 flags, 3 cascades, all in the
SKILL.md post-fix-gate exit-2 remedy paragraph, rewritten in all 5 rounds; about 58k tokens per finding).
The author picked candidates 1 and 2 ("V3.6"); the exit-2 paragraph is made enforced rather than written.
**Known limits (stated plainly)**
- **Did not converge in its own self-run.** Run on itself, v3.6 stalled after round 4 (flags 2, 4, 4, 8) and an extra full sweep still found 2. Cascades fell from 3 (v3) to 0, so the fixer change worked, but about 74k tokens per finding.
- **The finder is inconsistent between runs.** 16 of 18 flags were not found by earlier rounds, and the two cold reviewers vary a lot from run to run. A clean round is weaker evidence than it looks.
- **The block-reread gate trusts the fixer's `Blocks:` line.** It checks that a decision names a rewritten block, not that the fixer actually re-read it, so one bad fix got through.
- **The skill-creator-ccvw re-trace never ran clean.** Eight rounds on the final tree reached the round cap (raw flags 17, 10, 13, 3, 2, 2, 5, 4); 4 flags were still arriving in round 8, so no clean full sweep exists for 3.6.0.
- **The 11 fixes from the final full review were not reviewed again.** That review (round 9, all 48 files) had a one-round budget, so its fixes rest on the post-fix gate, 89 tests and `doc_lint` alone.
- **One eval-2 check was never exercised.** No changed-files review came back clean, so the "changed-scope-clean, then re-run with `--scope full`" path is untested, and the fixer manifests and decision-check outputs for rounds 1 to 8 were not kept.
- **Eval 0 is incomplete.** A `--rounds 2` trace of an archived multi-skill skill stopped in round 2 with that round's 71 findings unfixed; 4 of them were follow-on problems caused by round 1's own fixes.
- **Eval 5 cannot tell the versions apart.** The nested-subagent stop check scores 4 of 4 on both the old and the new version.
- **Multi-skill folders are not handled.** On a target that holds two skills in one folder, the fixer reads its intent only from `<target>/README.md` or `<target>/SKILL.md`, cannot find each skill's own design docs and pauses clusters as "intent unreadable"; `doc_lint.py`'s `$VAR` check reads only the top-level `SKILL.md`, so variables an inner `SKILL.md` defines are reported as undefined. Trace each skill folder as its own target.
#### Added
- **Rewritten-block gate.** `post_fix_gate.py check` finds each rewritten doc block (3 or more lines,
  at least 2 and 30% changed), lints and name-checks its untouched lines too, and raises a
  `block-reread` problem until a `Blocks:` closure line of a decision in `--fixer-transcript` names it.
  The Closure block has a fourth label, `Blocks:`; `check_decisions.py` requires it.
- **Generated exit-2 table.** `EXIT2` in `post_fix_gate.py` is the one list of disjoint causes and
  remedies; every `GateInputError` names a cause; stderr JSON carries `cause` and `remedy`;
  `post_fix_gate.py causes --write|--check <file>` generates and verifies the table that SKILL.md and
  `references/script-contract.md` carry between `gate-exit2` markers, and a test fails on a raise with no
  cause, a cause never raised, or a doc copy that differs. The hand-written remedy paragraph is gone.
#### Changed
- **Siblings list is actionable.** Plain single words (`for`, `return`) are no longer terms; terms naming
  more than 12 untouched lines are counted in `siblings_omitted`, not listed; at most 15 terms, fewest
  lines first. On the v3 tree with a 40-line SKILL.md edit: 2565 hits across 35 terms before, 54 across 15 after.
- `snapshot` lint failure is its own cause (`snapshot-lint-failed`): the batch is not dispatched.
#### Changed
After the v3.6 build (2026-10-06, before shipping): edits made after the v3.6 build, from the publisher-run audit and from the skill-creator-ccvw re-trace.
- **Post-fix gate procedure moved** to `references/dispatch.md` "Post-fix gate"; SKILL.md keeps a
  summary and the exit-2 table. Step-1 reads are batched; cleanup is not repeated in Present result.
- **`metadata.version` removed** (nothing reads it; versions live in this file). Session-log markers are
  `SKILL:` / `RUN:` / `STEP:` (start, closed, converged). Added an Example section and a Troubleshooting table.
  The description is narrowed to skills.
- **Merge-check** finds the source copy itself (the installed `~/.claude/skills/<basename>/` or the folder
  of that name in the git checkout holding the target): one candidate runs, none skips, several ask one question.
- **Repeated auto-pause** is resolved as any pause and becomes a USER-PAUSE only when the intent is not
  derivable. Handler-shape is marked reserved (code kept); verify-auditability is an optional manual check;
  a fresh invocation starts a fresh run ("can be extended" dropped).
- **Fix-depth rule examples-only (re-trace C4).** The frozen-interface list (CLI flag, mode, subcommand,
  file, ledger field, run-options key, row kind, shared helper module, doc section) is examples: any
  other new interface element, such as an output JSON field, status value or exit code, also pauses.
- **Rename radius (C3).** A removed function or other defined name is a shared token for
  `check_fix_radius.py`; a `stale-sibling` gate problem is sent to the fixer with that command, and
  goes to the cluster that defined the name when no cluster touched the file.
- **Auto-pause loop bound (C6).** `split_repeat_clusters` restarts a finding's repeat count at a resolving
  row, and `auto_pause` carries `resolutions`; a finding that returns after a resolved pause is a
  USER-PAUSE, so the prepass loop is bounded.
- **Fixer model rule.** `fixer_model` takes the pass's cluster count: Opus only above 15 clusters, else
  Sonnet. The earlier "Opus when a `.py` file is touched" rule came from 3.2.0-trimplus, not from the owner,
  and conflicted with the agents-Sonnet-or-lesser rule; it is removed.
- **`cluster_enforce.py` guards (coordinator-approved).** Gate 1 rejects a clusters file with a missing or
  repeated cluster id or an empty flags list, and a `--verified-flags` status other than `verified-flags`;
  staging runs before rows and the marker are written, so a staging failure leaves no PENDING rows.
  These guards add exit-1 branches (the post-fix gate flagged them as new behaviour); they fix real
  failures, not features, and are documented in `references/script-contract.md`.
- **Doc fixes from the re-trace (rounds 1 to 8, 61 flags):** tier-script wording (`prepass_run.py` and
  `cluster_enforce.py` print `batches`), `substep_label_mismatch` roman-numeral labels, resume rules in
  `references/recovery.md`, the exit-2 cause table (observable named per cause), `code_review_run.py`
  single-pass slot substitution, null-intent and pause-address wording in the considered-fix template,
  `prepass_run.py` exit-1 causes, `check_fix_radius.py` output keys, directory-order note for `--agent-transcripts`.
#### Changed
At ship (2026-10-07):
- **Final full review and publisher pass.** 11 fixes from the round-9 full review, publisher polish and audit wording fixes (Expected output lines, one-clause WHY lines, a placeholder path in an example), and a note that cold reviewers and fixers are separate agents. README gains "Features & modes" and "Structure" sections and fuller "How to invoke" bullets. Not applied, deferred to a later "improve skill-tracer" task: the root-level layout (`cascade_sweep.py`, `cluster_prepass.py`, `prompts/`, `templates/`, `detectors/`, `tests/` outside `scripts/` and `assets/`) and the self-run history wording in references. The proactive start stays out of the description.
**Re-trace result (not clean)**
skill-creator-ccvw's re-trace ran 8 rounds (the round cap) on this tree: raw flags per round 17, 10, 13, 3, 2, 2, 5, 4, every flag fixed, no clean full sweep. Rounds 5 to 8 reviewed only the changed files.
A fresh full-skill review of all 48 files then found 11 more flags (cascade 3: how-to-fix versus the considered-fix template on null intent, a docstring quoting SKILL.md text rewritten earlier, the Troubleshooting row; finder miss 8, in code and docs no earlier round had flagged), fixed after the sweep and not re-reviewed. Those fixes have had no second review, so treat this tree as not verified clean.
Tests: 89 (12 new since the build). doc_lint 0, cascade_sweep clean.

### 3.5.0-trimplus-v3 — 2026-10-05 (never published — folded into 3.6.0)
Fixer changes against the 7 fixer cascades of the v3 analysis (`/home/claude/stwork/cascade-analysis.md`).
#### Added
- **Closure block.** Every FIX decision carries `closure` (`Siblings:`, `Bound:`, `Claims:` lines);
  `check_decisions.py` refuses a FIX without them; the fixer template, `assemble_fix_prompt.py` and
  how-to-fix.md "Closure block" state it.
- **Siblings list.** `post_fix_gate.py check` prints untouched lines naming each term of a touched doc
  line (non-blocking), sent to the fixer with the inner-pass problems.
#### Changed
- `post_fix_gate.py check` resolves a CLI flag on a touched line inside a script against that script's
  own argparse when the line names no other script. SKILL.md describes the new-behaviour waiver.

### 3.4.0-trimplus-v3 — 2026-10-05 (never published — folded into 3.6.0)
3.3.0-trimplus-v2 plus fixes for the 76 open flags of the v2 audit (grouped by root cause in
`/home/claude/stwork/v3-fixes.md`) and the post-fix gate.
#### Added
- **Post-fix gate.** `scripts/post_fix_gate.py` (`snapshot` / `check` around each fixer batch, blocking
  `close-round`; `merge-check`; `survival`) wired into SKILL.md, script-contract.md and the glossary.
- **Retry bound and fresh-run test.** Fixer re-emit, fixer and reviewer re-dispatch and the prepass
  re-fix loop stop after 2 retries, then ORCHESTRATOR-PAUSE (reviewer slot: hard error); SKILL.md
  states an executable fresh-run-or-resume test (open-round marker = resume).
#### Fixed
- Docs now match code: marker state is the third field; collect runs before contract recovery; the
  prepass flag detector's direction; recovery's supersede attribution; fill-address exit causes.
- Code now matches its contract: path-qualified `python3 <dir>/<x>.py` invocations are checked;
  dup-regex findings carry an explicit `token`; header regexes no longer swallow the next line;
  `fixer_model` counts TOKEN-BLAST `uncovered` files; lens bodies are substituted last; detectors
  share `_common.line_of`; `ledger_cascade.py` dispatches flat on `--mode`.

### 3.3.0-trimplus-v2 — 2026-10-05 (never published — folded into 3.6.0)
3.2.0-trimplus plus the five changes in the round-2 trim vs trim-plus comparison
(`hq/ccvw-skills/research/skill-tracer-selfrun-2026-10/COMPARISON.md`, "Trim-plus v2: what changes
and why"). Evidence: after round 2 trim had 6 issues and trim-plus 9, so neither has converged;
trim-plus cost about 350k tokens against 210k for trim, but its fixes came out clean where trim's own
fix tripped its linter.
#### Changed
- **One fixer for 12 clusters or fewer.** `ledger_common.fixer_batches` returns one batch (opus if
  any cluster touches a `.py` file, else sonnet) when a round has at most 12 clusters; only a larger
  round is split into batches of at most 12, code first. Why: splitting a small round into a code
  and a doc fixer about doubled fixer cost (about 220k vs 110k tokens; both re-read the whole skill)
  with no quality gain. `check_decisions.py` and the comma `--fixer-transcript` list stay (both
  sonnet runs slipped on decisions, both opus runs did not). SKILL.md, dispatch.md, glossary, README,
  evals and the tier-script docstrings follow.
- **No new behaviour from a fixer.** `ledger_common.interface_rule` (the fixer prompt's
  `[INTERFACE_RULE]`) adds: a fix makes the doc match the code, or the code match its documented
  contract; adding a retry, cap, branch or exit path, or removing a fallback, is an
  ORCHESTRATOR-PAUSE. The same sentence is in SKILL.md "Fix depth", how-to-fix.md "Frozen
  interface" and the glossary (a test keeps them identical). Why: both seeded round-2 findings were
  behaviour a fixer had added.
- **Three new `doc_lint.py` checks** (twelve in all; .py files outside tests/): `fix-narration` (a
  comment or docstring narrating a fix event), `raises-no-raise` (a docstring "Raises X" with no
  `raise` in the function body, AST) and `unused-param` (a parameter never read; self, cls,
  `_`-names and pass/raise-only bodies skipped, AST). Why: reviewers found these by hand in this run
  (dead_script, code_review_collect, substep_label_mismatch); code is deterministic, so a script
  should find them. On this skill they report six findings in files this version did not change
  (left as they are: advisory, out of scope).
- **fill-address refuses an all-empty fixer round.** When no `--fixer-transcript` yields any
  decision, `ledger_cascade.py` exits 2 with an ERROR and writes no rows, instead of marking every
  PENDING row ORCHESTRATOR-PAUSE; partial decisions still auto-pause the undecided clusters
  (script-contract.md). Why: in the comparison run it wrote 12 false pauses in one target's round 1,
  reverted by hand.
- **G2 reads in reverse order from round 2** (UNTESTED HYPOTHESIS). From round 2 of a run,
  `code_review_run.py` stages a G2-only prompt with one extra `## Scope` line asking it to read the
  listed files last to first; G1 is unchanged. Why: G2 added about one unique issue per round in
  round 2; reversing the order may decorrelate the two reviewers. Not yet measured; keep or drop
  after a run compares it.

### 3.2.0-trimplus — 2026-10-05 (never published — folded into 3.6.0)
3.1.0-trim plus five changes from the round-2 comparison of the full and trimmed tracers
(ROUND2-ANALYSIS.md).
#### Changed
- **Retired-term sweep.** Leftover mentions of removed features (the old exception-handler and
  column-header detectors, the removed third tier, the lens flag letters, the review and run modes,
  the old doc-sync check) are gone from the skill; the code that still reads 3.0 ledgers says it is
  legacy compatibility. `doc_lint.py` gains three advisory checks: `retired-term` (driven by the
  one `RETIRED_TERMS` constant), `doc-count` (a docstring that states a count must match its list)
  and `dollar-var` (a `$NAME` in prose must be defined in SKILL.md or an in-scope script).
- **Interface frozen from round 1** (was round 3): no new CLI flag, mode, file, ledger field, row
  kind, shared helper module or doc section unless it is the only way to fix a real behaviour bug
  (otherwise ORCHESTRATOR-PAUSE); when behaviour is correct and only a comment or doc is wrong, fix
  the comment or doc, not the code (`ledger_common.interface_rule`, considered-fix template,
  how-to-fix.md, SKILL.md, glossary).
- **Fixer batches.** `prepass_run.py` and `cluster_enforce.py` split a round's clusters into
  batches of at most 12 (code clusters first), stage one prompt per batch and print `batches` with
  each batch's model: opus when a cluster touches a `.py` file, sonnet when all are doc-only. The
  batches run one at a time. This replaces the 15-cluster sonnet/opus threshold. `fill-address`
  takes several `--fixer-transcript` values (repeated or comma list) so one call records the round.
- **Pre-record decision check.** New `scripts/check_decisions.py` reports an empty address, a
  wrong kind prefix, banned dismissal vocabulary or a missing cluster in a fixer's decisions (exit
  1); the orchestrator sends the problems to the same fixer to re-emit. The staged fixer prompt
  states the output contract, the batch's cluster ids and the banned phrases (from
  `ledger_common.BANNED_PHRASES`) at its top (`[OUTPUT_CHECK]`).
- **Reviewer prompt.** The review template says `N` counts surviving ISSUE blocks only (a withdrawn
  block is not counted), as `code_review_collect.py` does; the all-lens framing tells reviewers that
  SKILL.md and references/ prose has drawn about 3-4 times the defects per line of the code, so
  claim-versus-code agreement there is checked first.

### 3.1.0-trim — 2026-10-05 (never published — folded into 3.6.0)
Applies the trim plan from the October 2026 self-run analysis: fewer moving parts, a review that
scales with what changed, and a fixer that cannot seed its own findings.
#### Removed
- **Minor-bugs tier** (bug-hunters, `bughunter_run.py`, `bughunter_confirm.py`,
  `assemble_hunter_prompt.py`, `templates/bug-hunter.md`, the settled-reject memory) and every
  detector and adjudication rubric except the prepass set below and the advisory glossary lint. The
  cascade is now 2 tiers: prepass → code-review.
- **Run modes** `--verify-only` and `--one-round` (use `--rounds 1`), and the code-review modes
  `--mode specialist`, `specialist:+gen` and `generalist:opus`: code-review always runs two Sonnet
  generalists on the all-lens prompt.
- **`scripts/doc_sync_check.py`** and the `PATTERN-BLAST` fix class.
- `_archive/` (removed detectors); the 3.0.0 tree keeps them.
#### Changed
- **Prepass detectors** cut to six: `refs`, `steps-dangling-ref`, `dead-script`,
  `substep-label-mismatch`, `argparse-flag-undocumented` and `dup-regex`.
  `missing-glossary-entry` stays as an advisory lint (detector level `advisory`).
- **Incremental review.** `code_review_run.py --scope auto|full|changed`: full sweeps in rounds 1-2
  of a run; from round 3 only the files the ledger's addresses name since the previous round. A
  clean changed-scope review answers `changed-scope-clean` and is followed by a full sweep in the
  same round; only a clean full sweep converges. The scope record
  (`cr-scope-<N>-<RUN_TIMESTAMP>.json`) keeps the coverage gate on the reviewed files.
- **Frozen interface.** After round 2 of a run a fix may not add a CLI flag, mode, file, ledger
  field or doc section (ORCHESTRATOR-PAUSE instead); any persisted key or format change is versioned
  and migrated. "Smallest" vs "deepest" is resolved as "deepest root fix that does not widen the
  interface" (templates/considered-fix.md `[INTERFACE_RULE]`, references/how-to-fix.md).
- **Doc lint.** `scripts/doc_lint.py` replaces the doc-sync check: a fixed, quiet, advisory lint
  of section and ordinal references, list counts, script-contract exit rows vs return codes,
  docstring Usage flags vs argparse, and the glossary.
- **Collector contract.** More ISSUE blocks than the declared `No of issues found:: N` is now a
  contract violation to re-emit (previously the first blocks were dropped); so is an incomplete
  ISSUE block.
- **SKILL.md** cut from 458 to about 250 lines (linear path only); resume, stop and hard-error
  detail moved to references/recovery.md.
#### Migration
- Run options are format v2 (`rounds-budget`, `max-rounds`, `run-start-round`). A v1 `mode=one-round`
  is read as `rounds-budget=1`; other `mode` values and `cr-mode` are dropped on read.
- A legacy `minor-bugs` in-flight marker resumes as `code-review running`; legacy `Minor Bugs` and
  `would-` rows still parse and render.


### 3.0.0 — 2026-06-29 (unpublished — local only; published repo is 2.2.0)
#### Added
- **3-tier cascade architecture** (prepass → minor-bugs → code-review) replacing the prior three-direction + nine-lens design. Each round runs all three tiers in order; a full sweep in which cold agents surface zero flags at every tier is convergence.
- **Stage 1 — Prepass** (`scripts/prepass_run.py`): deterministic sweep for mechanical defects (broken refs, dead code, lint); clusters and blast-fixes in-round; re-enters until clean.
- **Stage 2 — Minor-bugs** (`scripts/bughunter_run.py` + `scripts/bughunter_confirm.py`): cold bug-hunter agents (READ-ONLY, `subagent_type: Explore`) hunt for logic/boundary/concurrency bugs; candidates confirmed before a fixer is dispatched.
- **Stage 3 — Code-review** (`scripts/code_review_run.py` + `scripts/code_review_collect.py`): five cold reviewer agents across five lenses (fidelity / executor / logic / integrity / design); findings collected, clustered, blast-fixed.
- **Code-review dispatch modes** via `--mode` flag to `code_review_run.py`: `generalist` (default — 2× Sonnet union), `generalist:opus` (1× Opus), `specialist` (5× Sonnet per-lens), `specialist:+gen` (5 specialists + 1 generalist union).
- **`--rounds N` run-control mode**: exactly N rounds, or until convergence — whichever comes first.
- **`--one-round` run-control mode**: one full prepass→minor-bugs→code-review sweep, then stop.
- **`--verify-only` run-control mode**: one sweep, no fixes applied; emits `would-FIX` / `would-STRENGTHEN` rows.
- **FORBIDDEN-PAUSE rule** (load-bearing): when `--rounds N` or run-to-convergence is in effect, the orchestrator must not offer to pause or stop early for tail issues, diminishing returns, grinding, round size, cluster count, or token cost. Only convergence, budget exhaustion, genuine USER-PAUSE, or a hard unrecoverable error are legitimate stops.
- **Last-round non-conservative rule** (load-bearing): on the final round of a requested set, both the orchestrator and fixer drop fix-conservatism — deepest correct fix, fix every finding regardless of label, no preference for a smaller patch. Intent-preservation (invariant 2) still holds.
- **WHY-escape** (bug-hunter universal REJECT): a bug-hunter may REJECT a candidate with a documented convincing rationale, without requiring positive suppressor evidence — the asymmetric-default (genuine uncertainty CONFIRMS) is universal, but a well-reasoned REJECT is permitted.
- **>15-clusters → Opus fixer rule** (load-bearing, all three stages): when the cluster count for a given fixer dispatch exceeds 15, the fixer is dispatched on `model: opus` instead of `model: sonnet`. Rationale + calibration data inlined at each dispatch site.
- **Orchestrator-side clustering + blast radius**: after `code_review_collect.py` emits verified flags, the orchestrator clusters by root cause, writes `cr-clusters-<N>.json`, and runs `cluster_enforce.py` (mandatory, cannot be bypassed) before staging the fixer.
- **Fixer reads transcript via `--fixer-transcript`** (`scripts/ledger_cascade.py --mode fill-address`): no on-disk decisions file needed; the fixer agent's JSONL transcript path is passed directly.
- **Per-round tmp cleanup**: each round removes its staged prompt and cluster files at close (`rm -f <out-dir>/*-<Runtime>.txt <out-dir>/cr-clusters-<N>.json …`); a long `--rounds N` run does not accumulate staged files.
- **READ-ONLY enforcement via `subagent_type: Explore`** for all bug-hunters and code-review agents (prompt-only "do not edit" is explicitly insufficient — structural enforcement is non-negotiable).
- **`scripts/doc_sync_check.py`** (advisory post-fix): verifies every doc blast site for a code-editing cluster was touched; warns on net-new fields; always exits 0 (warnings do not block round close).
- **Dispatch manifest written instantly at dispatch** for both bug-hunters (`dispatch-hunters-<RUN_TIMESTAMP>.json`) and code-review agents (`dispatch-review-<RUN_TIMESTAMP>.json`): chunk/flag → agentId binding recorded before any other work; survives compaction.
- **Bug-hunter chunking**: `bughunter_run.py` chunks candidates when count > 20 (N = ceil(total/15), balanced split); the orchestrator follows the chunk count the script reports.
- **Prepass repeat-count auto-pause**: if the same prepass finding signature re-appears for the 2nd time in one round, `prepass_run.py` auto-emits ORCHESTRATOR-PAUSE.
- **Coverage gate** in `code_review_collect.py`: agents that sample rather than full-read are caught and continued via SendMessage before findings are accepted.
- **Contract recovery via SendMessage** for non-resumable agents: a fresh cold re-dispatch stays cold (reuse the original staged prompt verbatim; never mention the prior attempt or its failure).
- **Session-log breadcrumbs** per round: round START and CLOSED/CONVERGED lines appended to `~/.claude/session-logs/session-log-YYYY-MM-DD.md` (non-blocking).
#### Changed
- **Convergence redefined**: previously Condition A (all three directions return clean in one round) + post-convergence review pass (Condition A′). Now: a full sweep (prepass → minor-bugs → code-review) in which cold agents surface zero flags at every tier. A clean code-review IS convergence — you cannot reach it without a clean prepass and clean minor-bugs in the same round. No separate post-convergence review pass.
- **`--verify-only`**: in 2.4.2 it was an existing mode; 3.0.0 gives it new semantics aligned to the cascade (one sweep, `would-FIX` / `would-STRENGTHEN` rows, no loop-back).
- **ORCHESTRATOR-PAUSE resolution**: orchestrator resolves from README Intent by default; promotes to USER-PAUSE only when the intent is genuinely not derivable. Promoting to avoid making a derivable call is the lazy-pause anti-pattern and is forbidden.
- **`ledger_cascade.py --mode fill-address`** replaces the prior `append_ledger.py`-only address recording; `--fixer-transcript` replaces the stdin pipe and the on-disk decisions file.
- **`allowed-tools`**: removed `Skill` (no longer invokes `/code-review` externally) and `mcp__scheduled-tasks__create_scheduled_task` (not used in the cascade).
- **Audit-ledger base path relocated to XDG data dir** for claude-users portability: `LEDGER_BASE="${XDG_DATA_HOME:-$HOME/.local/share}/skill-tracer-audit-ledger"`. Old path `~/.claude/skill-tracer-audit-ledger/` is no longer the live path; existing ledger files should be migrated to `$LEDGER_BASE/`.
- **Inspirations pattern notes updated** to reflect the cascade's use of each borrowed pattern (see frontmatter above).
#### Removed
- **Three trace directions** (forward / backward / executor) and all direction-specific machinery (`references/forward.md`, `references/backward.md`, `references/executor.md`, `F*/B*/E*` flag prefixes, `<dispatch-set>` constant, the direction prompt-build step).
- **Nine review lenses** (`references/lens-line-by-line.md` … `references/lens-altitude.md`) and the two review-pass dispatch points (Step 4 whole-skill + Step 11 diff-scoped). The five cascade code-review lenses (fidelity/executor/logic/integrity/design) are the cascade's Stage 3, not a pre/post overlay.
- **Condition A / Condition A′** convergence model.
- **`REVIEW` ledger phase** and `R*` flag prefix. Cascade uses prepass / minor-bugs / code-review phases.
- **`--audit-fixes` diagnostic mode** (dispatched one cold audit agent to check ledger-recorded fixes). Removed entirely — no replacement in 3.0.0.
- **`--code-review` mode** (single-pass nine-lens code-scoped audit with fixes, `CODE-REVIEW` ledger phase). Removed — the cascade's Stage 3 runs code-review every round as the third tier, not as a standalone diagnostic.
- **Git baseline snapshot mechanism** (Steps 3/4(d)/11 in 2.4.2): `snapshot-mechanism::` / `snapshot-pretrace::` / `snapshot-base::` header lines, isolated `.snap.git`, commit A/B, post-convergence diff-scoped review (Step 11). Cascade does not take a baseline snapshot.
- **Round-budget gate** (the cumulative-ledger-span gate that asked the user before proceeding past a threshold). Superseded by the FORBIDDEN-PAUSE rule.
- **`<gate-dismissed>` / `<rule5-fresh-accepted>` / `<snap-mechanism>` / `<snap-pretrace>` / `<snap-base>`** orchestrator state variables (all snapshot- and gate-related).
- **`references/audit-fixes.md`**, **`references/code-review-mode.md`**, **`references/prompt-template.md`** (direction/lens template), **`references/dispatch-protocol.md`** (RUN_TIMESTAMP + staging), **`references/prepass.md`** (the old prepass reference — replaced by `scripts/prepass_run.py`).
- **`Skill` tool** from `allowed-tools` (was added in 2.1.0 to invoke `/code-review`; no longer needed).

### 2.4.2 — 2026-06-22 (description re-optimized against a harder boundary eval set)
- **Description rewritten to a benefit-first framing** — from the mechanism-first "Cold-parallel trace of any skill via three direction agents (forward, backward, executor)…" to "Use this skill to find bugs and verify correctness in any existing skill — post-edit regression checks ("did my edit break anything?"), correctness audits before relying on a skill, offline code audits of bundled scripts for logic or concurrency bugs, and full workflow validation…". Surfaces two capabilities the prior description never advertised for triggering — the `--code-review` mode (offline code audit of bundled scripts; added in 2.4.0) and the post-edit regression check — adds an explicit "target must already exist in working form" boundary, and keeps the two-sibling routing exclusion (build/edit → skill-creator-ccvw; polish/package/publish → skill-publisher).
- **Measured cause.** The 2.3.1 description had already hit the optimizer ceiling on the original 20-query trigger set (100% recall, all_passed iteration 1 — no signal left to optimize). Re-ran skill-creator-ccvw's description-optimization loop (`run_loop.py`, Sonnet 4.6 improvement step) against a new **harder 32-query boundary set** (16 trigger / 16 no-trigger) built to probe the under-advertised modes and the near-neighbour negatives the easy set missed: CCVW-compliance → skill-publisher, attribution → attribution-lint, portability → portability-lint, mid-development → feature-dev, repo-wide cloud code-review → standalone /code-review. On that set the prior (2.3.1) description scored **held-out test recall 61%**; the optimizer selected this description at **test recall 67%, precision 100% (11/12 held-out)**. A continuation run — after a transient `claude -p` failure in the iteration-3 improvement step, re-run once rate limits reset — confirmed no candidate beat it (the model plateaued; a more-aggressive variant overfit train and collapsed on test).
- **Caveat / honesty.** The held-out gain is modest and partly within 3-runs-per-query trigger noise (P1 re-measured 10–11/12 across two runs); the durable win is recall (fewer missed hard trigger queries) at maintained test precision, plus the newly-surfaced code-review / regression phrasings. A house-voice-preserving hybrid was drafted and eval'd (full-set recall 69% / precision 82%, with a mid-development over-trigger) but **not** adopted — the applied description is the optimizer's verbatim winner. Eval set + run artifacts under `~/.claude/skill-creator-evals-ledger/skill-tracer/trigger-opt/` (`eval_set-harder.json`, timestamped result dirs). Description length 552 chars (≤1024 cap).

### 2.4.1 — 2026-06-20 (shared-script sync contract retired)
- `render_ledger.py` / `append_ledger.py` are no longer kept in sync with skill-publisher's copies. `render_ledger.py`'s internal "shared byte-for-byte across skill-tracer and skill-publisher" comment reframed to "each skill keeps its own independent copy, free to diverge — no sync." (Full record in skill-publisher 1.2.0.)

### 2.4.0 — 2026-06-20 (new `--code-review` mode: audit the bundled code as code)
- **Added the `--code-review` mode** (`references/code-review-mode.md`) — a single-pass sibling to `--audit-fixes` that runs the nine review lenses **once**, code-scoped, over the bundled executable code (`scripts/*.py`, `eval-viewer/*.py`) and **applies fixes**. WHY: the default trace + lenses read the bundled scripts as *workflow specification*, not as *code* — a logic bug, an unhandled edge case, or a silent-failure path (e.g. an early-`return` that swallows the real signal, the exact shape of the `run_eval` detector bug found this session) passes the workflow read and still breaks at runtime. `/code-review` catches this class but needs a git diff; this mode brings the same code-level scrutiny to the bundled code directly, no git required. The only change vs Step 4(a)'s nine-lens dispatch is the `[SCOPE]` slot, which re-points the lenses at the code (SKILL.md/references become context, not the review target).
- **New `CODE-REVIEW` ledger phase** — added to `ledger_common.KNOWN_PHASES` (write-allowed; `ROW_RE` already accepted hyphenated phases) and to `render_ledger.DEFAULT_PHASE_COLORS` (its own swimlane color; tracer-local default, publisher unaffected). Findings reuse the lenses' pooled `R*` flags — the phase column distinguishes code-review rows from workflow `REVIEW` rows; auditability derives `--expect` with `expected_flags.py --directions "" --lenses <nine>` (no trace directions ran).
- **Single-pass + fix, standalone** (does not run inside the default trace; design choice), and blocks on a pre-existing full-convergence in-flight marker exactly like the other diagnostic modes (it writes its own `reviewing`/`addressing` markers, so the same crash-window reasoning applies). Registered in the modes table, When-to-invoke, Step 1 mode-routing, and the references table.

### 2.3.1 — 2026-06-20 (description: length compliance + sibling-routing exclusion)
- **Description trimmed 1113→992 chars** to clear the 1024 cap (`quick_validate`/`portability_lint` `description-too-long`) — a pre-existing violation; compressed the internal methodology detail, which does not drive triggering.
- **Added an explicit two-sibling routing exclusion**: "Do NOT use to build, edit, or optimize a skill or its description (use skill-creator-ccvw) or to polish, package, or publish one (use skill-publisher)." Measured cause: the description-optimization loop (100% recall, all_passed iteration 1) surfaced one cross-boundary leak — "optimize the description on my skill" triggered skill-tracer 3/3 (that's skill-creator-ccvw's job); the exclusion routes it correctly. Non-skill near-misses (review a script, audit AWS, find a race condition) already scored 0/3 — never the problem.

### 2.3.0 — 2026-06-18 (native review lenses + whole-number steps + ownership-aligned terms)
- **Review baked in — no external `/code-review`.** The round-1 and post-convergence review passes no longer invoke the external `code-review` skill. Nine native **review lenses** (`references/lens-line-by-line.md` … `lens-altitude.md`, one prompt body each) are dispatched cold through the same `prompt-template.md` as the directions, via a new `[SCOPE]` slot — whole-skill on the first round (Step 4), diff-scoped after convergence (Step 11). The lens prompts carry no issue cap and no self-numbering (like the direction prompts). The lenses **adapt code-review's `max` 9-angle methodology** (credited in `inspirations` above). WHY: invoking the external tool forced fragile per-run adaptation (stripping its caps, forcing whole-file scope, dropping its diff-orientation and angle-numbering); baking the angles in removes the whole class.
- **Whole-number steps.** Eliminated `Step 2.5` / `Step 8.5`; the workflow is now Steps 1–12 (the baseline snapshot and the first-round review are their own steps). Every cross-reference updated.
- **Terminology aligned to concern-ownership.** Per the build→trace→ship division: **review / reuse / efficiency / the correctness half of altitude** belong to skill-tracer; the **size/polish simplify pass** and the polish half of altitude belong to skill-publisher; `altitude` is a shared-glossary term with one definition. Flag prefix `CR*` (external "code-review") → **`R*`** (skill-tracer's own review); the `REVIEW` phase stays (review belongs here).
- **State-machine + recovery fixes (self-trace audit, round 48).** New `reviewing` in-flight marker keyword for the review phase (recovery branches on it, not on reconstructed signals); the round-budget gate is derived from the ledger's cumulative round span (the old `<round-counter>` dual counter is gone — it desynced on resume); `close-round` is idempotent; the post-convergence baseline advances each round (each diff review covers only that round's delta); `snapshot-mechanism::` is always written (incl. `none`) so a resumed run is deterministic; the post-convergence clean pass leaves a durable ledger note; the snapshot `info/exclude` carries the full Step-2 skip set; zsh `nomatch` guarded on cleanup globs.
- **`append_ledger.py` now imports `ledger_common`** (the documented single source of truth) and enforces the full write contract it had only documented — address token-boundary, `--phase` ∈ KNOWN_PHASES, `--cluster` ~ `^C\d+$`, `--round` int, `utf-8` everywhere. `render_ledger.py` now renders 6-column back-compat rows (its own back-compat path was dead behind a length check); `ledger_common.ROW_RE` accepts a mixed-case phase; `recover_dispatch.py` docstring corrected.

### 2.2.0 — 2026-06-17 (exhaustive self-trace to convergence + `--audit-fixes` mode)
- **Added: `--audit-fixes` diagnostic mode.** Checks whether the fixes recorded in the ledger since the last convergence actually landed (vs light-touch / band-aid / regressed) by dispatching one cold audit agent over the rounds-since-convergence. Read-only — reports a per-finding classification, applies no fixes, writes no rows. Spec in `references/audit-fixes.md`; integrated into Step 1(a) recovery, Step 7 mode-routing, and the Step 9 exit set.
- **Exhaustive self-trace (rounds 31–47).** Forward + backward (the correctness directions) converged. Fixed script bugs across the ledger toolchain: `recover_dispatch` most-recent-wins on discard-retry + id-less-tuid skip + full-non-alphanumeric `encoded_cwd`; `_tally` token-boundary; `render_ledger` phantom-round-0 guard, `type(e).__name__` in the broad except, and 6-col back-compat row acceptance; `ledger_state` marker parse; `stage_cold_prompts` single-pass substitution; `append_ledger` `re.escape` in close-round + `utf-8` everywhere + `--cluster ^C\d+$` guard + close-round single-read. Introduced **`scripts/ledger_common.py`** as the single source of truth for the row / marker / PRE-FLIGHT / vocab parsers — `append_ledger`, `ledger_state`, `check_drift`, `check_results` import it; `render_ledger` stays standalone (config-driven, serves both this skill and skill-publisher).
- **Doc consolidations.** Resolved doc-vs-code contradictions and collapsed duplicated rules to single-home-plus-pointer — the malformed-marker tree, resume-wakeup, `verify-auditability --expect`, `check_drift` exit codes, the stop-after-round computation, the forward/backward/executor escape-hatch scaffold (→ `prompt-template.md`), and the TRACE-vs-all Condition-A invariant (→ Step 8 as the single authoritative home).
- **New mechanisms.** USER-PAUSE cross-round resolution + enumeration; Step-7 mode-routing completeness (`<stop-after-round>` `>` and `null` cases, the TRACE-clusters-plus-unresolved-USER-PAUSE precedence).
- **Final code-review fixes.** `check_results` ABORTED false-positive (a quoted `ABORTED` line in an ISSUE block no longer aborts the report — relevant when tracing skill-tracer on itself); the `--expect` comma-spacing doc claim corrected; the error-table `--cluster`-rejection row added.
- **Known / ratified.** SKILL.md grew to ~11k words; the cold-executor design keeps point-of-use detail inline (moving it to references re-triggers the executor cascade), so the length is ratified and flagged for a future deliberate structural pass.

### 2.1.0 — 2026-06-16 (round-1 code-review pass)
- **Added: round-1 code-review pass (SKILL.md Step 2.5).** On round 1 of a brand-new trace — and on the first round of a re-trace of a skill updated since it last converged — skill-tracer now runs one full-depth local pass of the sibling `code-review` skill (`/code-review max`, no `--fix`, no issue cap) as the **first phase of round 1**, before the cold agents dispatch. Runs in full-convergence mode only (diagnostic modes skip it). The post-update-convergence trigger gates on an mtime check (`find … -newermt "<prior convergence Runtime>"`) so an unchanged converged skill isn't re-reviewed for nothing.
- **Whole-skill scope, not a diff.** The pass reviews every in-scope file's full contents (`[SKILL_PATH]` + `[FILE_LIST]`), not a working-tree diff — skills aren't always under git (skill-tracer's own tree isn't) and a new skill has no diff. If `/code-review` can't be scoped to whole files, skill-tracer falls back to a single general-purpose Agent running code-review's `max` methodology over the file set.
- **Sub-phase of round 1, not a separate round.** The code-review phase and the cold trace share round 1: `REVIEW`-phase `CR*` rows and `TRACE`-phase `F/B/E` rows land under the same Round with one continuous cluster sequence; the round closes once (Step 7) and `verify-auditability --expect` is the union of both flag sets. **Condition A is tested over the `TRACE` clusters only** — the cold trace reads the post-code-review-fix files, so a clean cold trace in round 1 is a genuine clean cold round; `REVIEW` clusters never block convergence.
- **Findings go through the existing considered-fix gate**, not auto-applied: `--fix` is deliberately *not* passed, so each finding is clustered (Step 5) and addressed under Step 6's bias-toward-FIX + intent-preservation rules, preserving invariant 2. Recorded as **`REVIEW`-phase rows** with a new **`CR*`** flag prefix (distinct from the `C*` Cluster column).
- **Added: post-convergence suggestion** — Step 9 now suggests a final `/code-review max <skill>` pass over the converged artifact (the round-1 pass reviewed the pre-trace skill; convergence may have rewritten it across many rounds), then `/skill-publisher`.
- **`code-review` linked as a sibling** in SKILL.md "See also" + README, and `Skill` added to `allowed-tools` (skill-tracer invokes `/code-review` via the Skill tool).
- **Recovery: rule 2 handles the `REVIEW` phase** — an interrupted `addressing round-N` with no `Forward/Backward/Executor trace` dispatch in the JSONL is recovered by re-running the code-review phase then proceeding into the cold trace (same round); if a trace dispatch exists, the `REVIEW` rows are already done and only the trace addressing is recovered. Rules 4/5 note Step 2.5 is the first phase of round 1, not a separate round.

### 2.0.2 — 2026-06-07 (shipped — claude-users portability)
- **Now ships at `claude-users` tier** (was `personal`): guarded the glossary-precedence reads of the user's `CLAUDE.md`/`memory` to portable `${XDG_*:-$HOME/.claude}` form + explicitly optional, so the skill no longer hard-depends on personal config.
- **Fixed a portability-lint inconsistency** (canonical skill-creator-ccvw lint + vendored skill-publisher copy): a skill's own per-user ledger (e.g. `~/.claude/skill-tracer-audit-ledger/`) was flagged as a user-data-path while skill-publisher's own ledger was not — removed the skill-own-ledger entries from `USER_DATA_PATHS` so only genuine user-personal config is flagged.
- **Version field reconciled to 2.0.2** (it had lagged at 2.0.0 while the changelog already carried 2.0.1).
- Shipped via skill-publisher (full 10-step ship; CCVW audit + claude-users tier gate passed).

### 2.0.1 — 2026-05-30 (self-consistency + batch-edits fix-discipline)
- **Fix: description trimmed 1197 → 941 chars** so the skill passes the ≤1024 frontmatter-validity gate that skill-publisher now enforces at ship time (it previously would have been blocked by its own ecosystem's gate). Trimmed the glossary-precedence + README-Intent sentences — both fully documented in the body (Step 1c, Step 3), so no information lost.
- **Consistency: `compatibility` flattened to prose** `Claude Code 2.0 or newer`, matching skill-creator-ccvw + skill-publisher (was a nested `claude-code`/`agentskills-io` object). Cross-skill standardization; the tracer is personal-tier so the dropped structured agentskills.io declaration was aspirational.
- **Added: "Batch edits to the same document" fix-discipline** in `references/address-decision.md` — when several clusters in a round resolve in the same file, apply their fixes as one coordinated pass (not one-at-a-time), to remove the stale-read window that causes wrong-anchor / sibling-overwrite / double-touch errors. Composes with fix conservatism + Step-7 anchor verification.

### 2.0.0 — 2026-05-30 (three-skill ecosystem refactor — slimmed to correctness-only)
- **Major: slimmed to F/B/E correctness-only.** skill-tracer now finds bugs + inconsistencies via three cold-parallel direction agents (forward, backward, executor). That's its whole job.
- **Removed (moved to skill-publisher)**: the CCVW Word/Spirit audit (was Step 9), the mandatory simplify pass + verification re-trace (was Step 11), the portability sub-audit, the security cadenced direction, the `audit-references::` mtime tracking. These are ship-phase concerns — they live in skill-publisher now.
- **Removed (moved to skill-creator-ccvw)**: the efficiency + accessibility cadenced directions. Efficiency + accessibility (general readability) became iterate-quality checks in the builder; accessibility cats 15-16 (personalization + plan-code leakage) became portability-lint checks. These are quality/build concerns, not correctness bugs.
- **Convergence is now Condition A only** — F/B/E come back clean. No more Condition B (CCVW-compatibility); that gate moved to skill-publisher.
- **Removed flag prefixes**: EFF*, A11Y*, SEC*, G*, G-PORT*, SIM-*. Only F*/B*/E* remain.
- **Removed Phase column values**: PORT-AUDIT, SIMPLIFY. Only TRACE remains.
- **Added**: soft README.md `## Intent` read at Step 1 (orchestrator-side only — the cold agents never see it, preserving the cold-trace invariant). The orchestrator uses documented Intent to make considered-fix decisions: a fix that would violate stated Intent is a USER-PAUSE.
- **Structural**: frontmatter history moved to this HISTORY.md; README.md added.

### 1.x (pre-refactor) — 2026-05-27 → 2026-05-30
- Original cold-parallel three-agent trace. Grew Step 9 (CCVW audit + portability sub-audit), Step 11 (simplify), cadenced directions (efficiency/accessibility/security) — all of which the 2.0.0 refactor redistributed to creator + publisher.
- 11 rounds of self-trace hardened the recovery protocol, dispatch protocol, ledger format, and address-decision rules. Those are retained.

## Lineage notes

skill-tracer is Category B — original independent design whose cold-parallel dispatch is recognizable as deep-research's / pr-review-toolkit's adversarial-verify pattern, and whose inline loop is ralph-loop's shape. Named retrospectively; the patterns pre-existed as independent design and the inspirations credit the structural correspondence.

The 2.0.0 refactor was a deliberate narrowing: skill-tracer had accreted build + ship concerns that diluted its correctness-finding focus. The build → trace → ship split moved those out, leaving skill-tracer to do one thing well — find bugs and inconsistencies in any skill via cold-parallel reading.

The 3.0.0 rebuild is a second narrowing of a different kind: the 2.x architecture (three directions + nine lenses) grew a large orchestration surface across 12 steps, a git baseline snapshot mechanism, two diagnostic modes (--audit-fixes / --code-review), and a round-budget gate. The 3.0.0 3-tier cascade replaces all of that with a deterministic per-round sequence (prepass → minor-bugs → code-review) where convergence is simply a clean pass through all three tiers. The five code-review lenses (fidelity/executor/logic/integrity/design) are the direct descendent of code-review's multi-angle methodology, now embedded as the cascade's third tier rather than a pre/post overlay. The FORBIDDEN-PAUSE and last-round-non-conservative rules codify previously ad-hoc orchestrator judgment as load-bearing invariants.
