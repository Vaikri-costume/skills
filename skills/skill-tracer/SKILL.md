---
name: skill-tracer
description: 'Use when the user wants to find bugs in, or verify the correctness of, an already-built Claude skill (a skill folder with SKILL.md, scripts and references). Canonical triggers: "trace skill X", "audit skill X for bugs", "check skill X for issues", "validate skill X scripts", "run the cascade on skill X". The decisive signal is the ACTION on a skill: auditing vs. building vs. shipping. Do NOT use it for general code review of other projects (use code-review), for proofreading prose (use proofread), when the action is ship / publish / release / package / PR (use skill-publisher) or create / build / scaffold (use skill-creator-ccvw). Here "trace" means bug-auditing a skill, not distributed tracing or stack traces.'
license: MIT
compatibility: Claude Code 2.0 or newer
metadata:
  tier: claude-users
  created: "2026-06-27"
  created-by: Vaikri-costume
  parent-version: "3.6.0"
  intended-audience: claude-users
allowed-tools:
  - Agent
  - Read
  - Edit
  - Write
  - Bash
  - SendMessage
---

<!-- Provenance, version, attribution and changelog: HISTORY.md. Intent: README.md.
     This file is the runnable contract for the normal path; the rest is in references/
     (see "Where the details live"). -->

# skill-tracer

## What this skill does

Finds bugs and verifies correctness in a target skill (or another directory of docs and scripts
named by path) by running a **2-tier cascade** each round:

- **Prepass**: deterministic checks for broken references (cited paths, `Step N` pointers, dead
  scripts, sub-step labels, CLI flags a doc cites for a script that does not register them,
  duplicated regexes). It clusters and fixes them in-round and re-enters until clean; each finding
  gets two fixer passes in total (the first fix and one re-fix) before its next return is auto-paused (Retry bound).
- **Code-review**: two cold READ-ONLY reviewer agents read the review scope on the all-lens prompt
  (from round 2, G2's copy adds a reading-order line). Their flags pass the `coverage gate` and the
  `no-drop gate`, then are clustered and fixed.

Read-only agents are dispatched with `subagent_type: Explore`, which has **no Edit/Write tools**.
The missing tools are the enforcement. The post-dispatch edit check in `references/dispatch.md` ("A
reviewer that edits a file") backstops the Bash tool they keep; a prompt's "do not edit" wording is
only secondary.

## When to invoke

- "trace <target>", "audit <target>", "run the cascade on <target>", "check <target> for bugs",
  "verify <target>".
- Proactively after the user creates or significantly edits a skill (an edit is when new defects enter,
  and the ship phase expects a traced skill). A proactive start counts as an invocation in that turn
  for the fresh-run test (Run options).

## Prerequisites

- `<target>`: absolute path to the directory to audit (a bare name resolves to
  `~/.claude/skills/<name>/`); must exist and be readable.
- `<ledger>`: `${XDG_DATA_HOME:-$HOME/.local/share}/skill-tracer-audit-ledger/<basename>.md`, where
  `<basename>` is the final component of `<target>`. Resolve it once to an absolute path and pass
  that literal path to every script (no script reads the variables). `begin-round` creates it and
  refuses (exit 2) a ledger that records a different target: then give this target its own path.
- Scripts live at `~/.claude/skills/skill-tracer/scripts/`. Run them as
  `python3 <absolute-script-path>`; `scripts/<name>.py …` below is shorthand. A relative path fails
  under zsh (exit 127).
- `Agent` must be available. It exists only in the **top-level** session: if the `Agent` tool is
  absent, stop and tell the user "skill-tracer must be invoked from the top-level Claude session;
  it needs the Agent tool to dispatch cold reviewers." Cold reviewers and fixers are separate agents
  by design, so no mode works without Agent.
- No network, no external services.

## The four invariants

1. **Cold-read.** Every code-review agent is dispatched independently: no sibling mentions, no
   fix-log carry-over, no "what changed" preamble.
2. **Considered-fix.** Before writing any fix guidance (a cluster `guidance` field, a
   considered-fix decision, an ORCHESTRATOR-PAUSE question) read the target's own SKILL.md and
   `references/`, not only its README `## Intent`. Weigh each finding against the documented
   intent. "Make the checker happy" fixes are forbidden; they destroy design.
3. **No-orphan-flag.** Every finding is addressed by FIX, STRENGTHEN, or ORCHESTRATOR-PAUSE, and
   the address must land inside the target. Doctrine: `references/how-to-fix.md`.
4. **WHY-strengthening.** When a finding flags a missing WHY for an intentional design decision,
   add the WHY; do not remove the rule.

## Run options

The default runs rounds until a stop rule fires. `--rounds N` runs at most N rounds (`--rounds 1`
is a single round). The options live on the ledger so they survive a compaction; a fresh run sets
them on its first `begin-round`:

```bash
python3 .../scripts/append_ledger.py begin-round <ledger> --round <N> --runtime <Runtime> --target <target> \
  --set run-start-round=<N> [--set rounds-budget=<budget>] [--set max-rounds=<cap>]
```

`<budget>` is the N the user gave `--rounds`. The `max-rounds` cap defaults to 8; with `--rounds N` above 8 also set `max-rounds=<N>`. On an
existing ledger, clear a previous run's `rounds-budget` / `max-rounds` with an empty value
(`--set rounds-budget=`). Only the first `begin-round` of a fresh run passes `--set`; a resume and
every later round of the same run pass none (`references/recovery.md` "Persisted run options").

**Fresh run or resume.** Decide from the ledger and this turn, never from memory. An *open-round
marker* is an `in-flight::` line (`grep '^in-flight::' <ledger>`) that is not `converged` and whose
round has no `<!-- Round <N> total` summary comment (`grep -c '^<!-- Round <N> total' <ledger>`
prints 0).
- **Resume**: an open-round marker exists. Finish that round (`references/recovery.md` "Resume"),
  passing no `--set`, even when the user invoked the skill this turn; the persisted run options
  apply, and options the user asked for this turn are merged with
  `scripts/append_ledger.py options <ledger> --set …` before resuming.
- **Fresh run**: no open-round marker for this target (no ledger, a `converged` marker, or a closed
  round whose gate stops: `append_ledger.py gate <ledger> --round <N>` exits 1), the skill was invoked
  this turn, by the user or proactively, and no `begin-round` has run since that invocation. Its first
  `begin-round` passes `--set`. A closed round whose gate continues (exit 0) is never a fresh run, even after a
  compaction between two `begin-round` calls: the ledger alone decides.
- Neither (no open-round marker, and either no invocation this turn, a `begin-round` already run
  since it, e.g. a compaction between two rounds of one run, or the next round that `close-round`'s
  gate starts in the same turn, or a closed round whose gate continues, e.g. a session that ended
  between `close-round` and the next `begin-round` and is invoked again this turn): when the marker
  is `converged`, or `append_ledger.py gate <ledger> --round <N>` (N the last closed round) exits 1,
  go to "Present result"; otherwise start the next round of the same run without `--set`, after
  merging any options the user asked for this turn with `scripts/append_ledger.py options <ledger>
  --set …`, as a resume does.

**Retry bound.** Each of these stops after 2 retries: the fixer re-emit after a failed decision
check, the fixer re-dispatch after an out-of-target edit, the reviewer re-dispatch after an edit,
and the post-fix gate's inner passes (the fixer re-emit after `post_fix_gate.py check` exits 1).
The third failure becomes an ORCHESTRATOR-PAUSE as each step states (for a reviewer slot, a hard
unrecoverable error), never a further retry. A prepass finding gets two fixer passes (the first fix and one re-fix); its next return is
auto-paused (`ledger_common.AUTO_PAUSE_REPEATS`). A resolved pause restarts the count, and an auto-pause after a
resolved pause is a USER-PAUSE (Prepass `auto_pause` bullet). Contract
recovery keeps its own stated limits (`references/dispatch.md` "Contract recovery").

## Stop rules

The cascade stops only for: **convergence** (a clean full-sweep code-review with all pauses
resolved); the **round gate** (`round-cap`, `budget-exhausted` or `stalled`, reported by every
`close-round`); a **USER-PAUSE** (a decision not derivable from the target's files); or a **hard
unrecoverable error** (the list is in `references/recovery.md` "Hard unrecoverable errors").

A gate stop is NOT convergence: report "stopped by <reason>, not verified clean", list what the
last round fixed and what was still flagged.

**FORBIDDEN-PAUSE.** While a run is in progress never offer to pause or stop early for tail
issues, diminishing returns, "minor" findings, session length, round size, cluster count or token
cost. The gate is the only cost control. Why: a stop for tail issues leaves the tree unverified, so the cascade ends only by a stop listed under "Stop rules".

**Fix depth.** Every round, considered-fix and the fixer apply the deepest root fix that does not
widen the interface, and fix every finding regardless of a "minor" label. The interface is frozen
from round 1 of a run: a fix that would add a CLI flag, mode, subcommand, file, ledger field, run-options key, row
kind, shared helper module, doc section, or any other new interface element (an output JSON field, status value or exit code) becomes an ORCHESTRATOR-PAUSE, unless it is the only way to fix a real
behaviour bug. When the behaviour is already correct and only a comment or doc is wrong, fix the
comment or doc, not the code (`references/how-to-fix.md` "Frozen interface"). A fixer adds no new
behaviour: a fix makes the doc match the code, or the code match its documented contract. Adding a
retry, cap, branch or exit path, or removing a fallback, that the documented contract does not
require is new behaviour: apply no edit for that cluster and emit ORCHESTRATOR-PAUSE naming it. A fix
that restores the documented contract is not new behaviour even when it adds a node (the post-fix
gate still flags it).

## Workflow

### 1. Resolve target and read state (every invocation, including after compaction)

Re-read state from disk; never reason from memory about what is in flight.

- `<Runtime>`: ISO-8601 UTC now to the second (`YYYY-MM-DDTHH:MM:SS`); `<RUN_TIMESTAMP>` is it
  with `:` replaced by `-` and is carried by every staged or tmp file name of this run. When the
  in-flight marker names a round that is still open, reuse the marker's `<Runtime>` instead.
- `<out-dir>`: `/tmp/skill-tracer-prompts/` (`mkdir -p`); shared by every invocation, so only ever
  delete files scoped to your own `<RUN_TIMESTAMP>`.
- If `<ledger>` does not exist (`test -f`), this is round 1 of a fresh run: skip the reads below,
  since `options` exits 2 on a missing ledger. Otherwise read `scripts/append_ledger.py options
  <ledger>` and `grep '^in-flight::' <ledger>` in one Bash call; then, when that marker is not `converged`, run the
  `Round <N> total` grep (Run options) with N taken from the marker's `round-<N>`, and apply the
  fresh-run-or-resume test (Run options): an open-round marker means resume it (`references/recovery.md` "Resume"); a `converged`
  marker, a closed round, or no marker means start round N+1, except where that test sends you to
  "Present result".

Expected output: the fresh-run-or-resume verdict, with `<Runtime>` and `<out-dir>` known.

### 2. Run round N

Run `scripts/append_ledger.py begin-round <ledger> --round <N> --runtime <Runtime> --target <target>`
(plus `--set` on a fresh run). It writes the round's first marker, `prepass running round-<N>`;
scripts own the marker, so never write it by hand. Append
`**[HH:MM:SS] SKILL:skill-tracer RUN:<basename> STEP:round-<N>-start**` to
`~/.claude/session-logs/session-log-$(date +%Y-%m-%d).md` (a failed echo never blocks).

**Fixer dispatch.** The fixer-staging script (`prepass_run.py` at Prepass, `cluster_enforce.py` at Code
review; `code_review_run.py` only stages the reviewers) prints `fixer`: the staged prompt, the cluster ids and
the `model`: `opus` when the tier pass (one `prepass_run.py` or `cluster_enforce.py` call) has more than 15
clusters, else `sonnet`. One fixer fixes the whole pass, whatever its cluster count. When a pass of 15
clusters or fewer needs more context than Sonnet holds (for example clusters sharing files), the
orchestrator may dispatch an `opus` fixer and records the reason as `"opus_reason"` in the fixer manifest. Dispatch it
(`subagent_type: general-purpose`) pointed at its prompt with the provenance wording in
`references/dispatch.md`; record its `agentId` in the fixer manifest at once (a re-dispatched fixer's id
replaces the discarded one).
A fixer edits only files under `<target>`; check its Edit/Write paths and `touched_files` (only those two sources are inspected: a Bash write outside `<target>` is not detected). On an
out-of-target edit, restore it, discard that fixer's decisions (record none of them) and re-dispatch
a fresh fixer with the same staged prompt plus an "edit only files under `<target>`" constraint
(`references/dispatch.md` "A fixer that edits outside `<target>`"). A re-dispatched fixer that stays
inside `<target>` is checked and recorded like any fixer. When the fixer from the 2nd re-dispatch
also edits outside `<target>` (the third failure, Retry bound), restore its out-of-target files as that section says, then leave that fixer's transcript out of the fix-recording step (when no transcript is left,
pipe `{"decisions": []}` on stdin as in the Decision check): its clusters get no decision
and fill-address records them as ORCHESTRATOR-PAUSE. Expected output: one `{"decisions": …}` JSON
object, with the fixer's `agentId` in the fixer manifest.

**Decision check.** After the fixer returns, run `scripts/check_decisions.py --fixer-transcript
<transcript> --expect <the fixer's cluster ids>`. On exit 1 (empty address, wrong kind prefix, banned
vocabulary, missing cluster, or a FIX without its **Closure block**: non-empty `Siblings:`, `Bound:`
`Claims:` and `Blocks:` lines, `references/how-to-fix.md` "Closure block") `SendMessage` the same fixer the
problems to re-emit; check again. After
2 re-emits that still fail, stop asking: leave the fixer's transcript out of the fix-recording step
(when no transcript is left for the fix-recording step, whatever the reason: re-emits that keep failing, out-of-target re-dispatches or a failed snapshot lint, pipe `{"decisions": []}` on stdin instead of `--fixer-transcript`), so
fill-address records its clusters as ORCHESTRATOR-PAUSE; resolve them at the check-pauses step,
checking the edits that fixer already made. Expected output: `check_decisions.py` exits 0.

**Post-fix gate.** Before dispatching the fixer run `scripts/post_fix_gate.py snapshot --target
<target> --out <out-dir>/gate-<N>-<RUN_TIMESTAMP>.json`; after the decision check
passes, run `post_fix_gate.py check --target <target>` with `--snapshot <out-dir>/gate-<N>-<RUN_TIMESTAMP>.json` and `--fixer-transcript <the fixer's
transcript>`. Exit 1 blocks closing this round (an orchestrator rule: `close-round` itself does not read
the gate): send the problems back to the same fixer, at most 2 inner passes (the retry bound); a problem
still listed after them, and any `new-behaviour` problem at once, becomes an ORCHESTRATOR-PAUSE. The full
procedure (send-back format, siblings list, the pause wording, the behaviour-preserving waiver) is
`references/dispatch.md` "Post-fix gate". The gate covers a fixer's edits only; the orchestrator's own edits (doc-lint fixes, check-pauses resolutions) are not gated, and each later round's prepass, review and doc lint re-read them. Expected output: `check` exits 0. Exit 2 is unreadable input. `post_fix_gate.py` prints `cause` and `remedy` in its stderr JSON; follow
that remedy. A missing or unknown option also exits 2, with usage text and no JSON: fix the command line. Every cause, with its remedy, is this table, generated from the script
(`post_fix_gate.py causes --write SKILL.md`; a test fails when it differs or when a raise names no cause), so
it is not edited by hand:

<!-- gate-exit2:begin -->
| Cause | Observable | Remedy |
|---|---|---|
| not-a-directory | `--target is not a directory: <path>` (`snapshot`, `check`) or `not a directory: <path>` (`merge-check`) | fix the path and re-run |
| unreadable-target-file | `cannot read <path>: ...` (an in-scope target file that is not UTF-8 text) | fix that file and re-run |
| snapshot-unusable | `unreadable snapshot <path>: ...` (the `--snapshot` path names no file, or the file is not a snapshot), or `lint data is not a JSON object` / `<source> lint data is not a JSON object` when the stderr JSON `cause` is this one (printed by `check`; the snapshot's stored `lint` field is malformed) | the fixer's baseline is lost: take no new snapshot after the fixer has edited the target, report the fixer's edits as unchecked and `SendMessage` the fixer to re-emit the decision of each of its clusters as `ORCHESTRATOR-PAUSE (post-fix gate: snapshot missing or unreadable)` |
| lint-run-failed | `<script> printed no JSON ...`, `<script> exited <N>: ...` (`doc_lint.py` or `cascade_sweep.py` failed) or `lint data is not a JSON object` / `<source> lint data is not a JSON object` when the stderr JSON `cause` is this one (printed by `check` on a lint it just ran) | report the fixer's edits as unchecked and `SendMessage` the fixer to re-emit the decision of each of its clusters as `ORCHESTRATOR-PAUSE (post-fix gate: lint run failed)` |
| snapshot-lint-failed | the same texts, with this stderr JSON `cause`, printed by `snapshot` (before the fixer is dispatched) | do not dispatch the fixer: leave its transcript out of the fix-recording step so fill-address records its clusters as ORCHESTRATOR-PAUSE |
| baseline-unusable | `unreadable --baseline-lint <path>: ...` or `<source> lint data is not a JSON object` when the stderr JSON `cause` is this one (including a dict holding only one of `doc_lint` / `cascade`) | fix that file and re-run (SKILL.md's commands never pass `--baseline-lint`) |
| ledger-unreadable | `unreadable ledger <path>: ...` (`survival`) | stop ("Broken ledger" in `references/script-contract.md`) |
| survival-row-ambiguous | `--row <id> matches <N> ledger rows (pass --round)`, N above 1 (`survival`) | re-run with the right `--round` |
| survival-row-missing | `--row <id> matches 0 ledger rows` (`survival`) | correct `--row` or `--round` and re-run |
<!-- gate-exit2:end -->

**Fix-recording step.** After the fixer's check passes, record its decisions:

```bash
python3 .../scripts/ledger_cascade.py <ledger> --mode fill-address --phase "<Phase>" --round <N> \
  --runtime <Runtime> --fixer-transcript <fixer-transcript> \
  --skill-root <target> --blast-json <out-dir>/blast-round-<N>-<RUN_TIMESTAMP>.json [--reenter] [--allow <files>]
```

`--phase` is `Prepass` (with `--reenter`) or `"Code Review"` (without). Write the `"blast"` array that
`prepass_run.py` or `cluster_enforce.py` printed to the blast file first as `{"blast_radius": <blast>}`; fill-address re-checks every FIX
decision on a TOKEN-BLAST cluster with `check_fix_radius.py` and refuses uncovered sites. `--allow` is only for a
site that legitimately keeps the token, with the reason in the FIX address. A cluster the fixer
skipped becomes an ORCHESTRATOR-PAUSE; when the printed marker's state (its third field,
`<Runtime> <phase> orch-fixes round-<N>`) is `orch-fixes`, resolve the pauses (check-pauses step
below) before re-running any tier script. Expected output: it exits 0 and the round's rows hold their addresses, none PENDING.

#### Prepass

```bash
python3 .../scripts/prepass_run.py --target <target> --ledger <ledger> --round <N> --runtime <Runtime> --out-dir <out-dir>
```

- `{"status":"converged","next":"code-review"}`: go to Code-review (the script advanced the marker).
- `{"status":"needs-fix","fixer":{…}}`: dispatch the fixer, run the decision check, the post-fix gate and the fix-recording step
  (`--phase Prepass --reenter`), then re-run `prepass_run.py` with the same round. The loop is
  bounded per finding: a signature already addressed twice this round since its last resolved pause (two fixer passes in total) is not
  sent to a fixer again but auto-paused (`auto_pause`, `ledger_common.AUTO_PAUSE_REPEATS`).
- `{"status":"needs-record"}`: Prepass PENDING rows remain although the sweep is clean; the script
  cannot tell a fixer that ran from a pass staged but never dispatched. Follow `references/recovery.md`
  "A fixer already ran" (the fixer manifest and transcript decide which case; it gives the way out for
  each), then re-run `prepass_run.py`.
- `auto_pause` (with or without `fixer`): a finding already addressed twice this round came
  back; it is an open ORCHESTRATOR-PAUSE row (a finding whose pause row an earlier run already opened
  is not listed again: `check-pauses` lists every open pause with its own flag ids). With `fixer`, first dispatch it and run the
  fix-recording step as for `needs-fix`; then resolve each pause with a different fix (check-pauses
  step), and only then re-run `prepass_run.py`. A resolving row restarts that finding's count, so
  the finding is fixed again (two more fixer passes in total) before it can be auto-paused again. An
  `auto_pause` entry with `resolutions` of 1 or more (the finding came back after a resolved pause)
  is a USER-PAUSE, not another resolve: promote it by the USER-PAUSE rule of the check-pauses step
  (append the USER-PAUSE row, then ask the user), which bounds the loop; for an entry with
  `resolutions` 0 promote only when the intent is not derivable (check-pauses step).
- Exit 1 with `detector_errors` on stderr: a detector crashed; hard error, never `converged`. Exit 1 with an
  `error` key and no `detector_errors`: a sub-script of the pipeline failed (the error text names it);
  also a hard error, never `converged` (`references/recovery.md` "Hard unrecoverable errors").

#### Code-review

```bash
python3 .../scripts/code_review_run.py --target <target> --ledger <ledger> --round <N> --runtime <Runtime> --out-dir <out-dir> [--scope full]
```

It decides the review scope (`auto`): every in-scope file (`scripts/inscope.py`) in rounds 1-2 of a run;
from round 3, only the files the previous round's and this round's ledger addresses name (a FIX address
names every file the fix edited, `references/how-to-fix.md` "Recording propagated sites"). If those addresses name none, it reviews every in-scope file: a full sweep, so a
clean result is `code-review-clean`. It stages the all-lens prompt, records the scope for the collector and prints a
`dispatch` array of two generalists (`G1`, `G2`; from round 2 G2's prompt asks for reverse file
order), each with its staged prompt. Take the edit-detection baseline
(`references/dispatch.md` "A reviewer that edits a file"), dispatch both in ONE same-turn message
(`model: sonnet`, `subagent_type: Explore`; why, and single-slot re-dispatch: `references/dispatch.md` "Dispatch prompts") with the code-reviewer provenance wording in
`references/dispatch.md`, record the review manifest, run the baseline's edit check, then collect:

```bash
python3 .../scripts/code_review_collect.py --agent-transcripts <G1,G2 paths> --agent-flags G1,G2 --target <target> --ledger <ledger> --round <N> --runtime <Runtime> --out-dir <out-dir> > <out-dir>/cr-verified-<N>-<RUN_TIMESTAMP>.json
```

On exit 1 read the stderr JSON: `aborted_agents` is a hard unrecoverable error; otherwise
`malformed_agents` (contract violations) and `incomplete_coverage` name the agents to `SendMessage`
(contract recovery, `references/dispatch.md`), then collect again. On exit 0 read the status from
that file:

- `{"status":"changed-scope-clean"}`: the changed-files review is clean. That is not convergence:
  re-run `code_review_run.py` with `--scope full` in the same round, dispatch and collect again.
- `{"status":"code-review-clean"}`: a full sweep is clean; go to "Convergence".
- `{"status":"verified-flags", …}`:
  1. Cluster by root cause. You may merge beyond `blast_advisory` groups but never split one.
     Read the target's SKILL.md and `references/` before writing any `guidance`. For a flag that
     repeats a finding an earlier round's row already addressed, write a survival record:
     `scripts/post_fix_gate.py survival --ledger <ledger> --row <that row's C-id> --round <its round>
     --cause <never-found|badly-fixed|cascade|not-merged>`. The cause: `cascade` when the flag sits on
     text a previous fix of this run wrote or changed; else `badly-fixed` when the earlier fix touched
     the flagged line but the flaw stayed; else `not-merged` when the earlier fix was made only in an
     audited copy; else `never-found` (the earlier round's reviewers did not surface this flaw). Exit 2
     with `matches N ledger rows (pass --round)`: add the right `--round`; with `matches 0`: correct
     `--row` / `--round`; with an unreadable ledger: stop ("Broken ledger", `references/script-contract.md`).
  2. Write `<out-dir>/cr-clusters-<N>-<RUN_TIMESTAMP>.json`:
     `{"clusters":[{"cluster":"C1","flags":["G11","G23"],"guidance":"<optional>"}]}` (ids are
     placeholders; `cluster_enforce.py` renumbers them and reports the mapping).
  3. Run `scripts/cluster_enforce.py <ledger> --round <N> --runtime <Runtime> --target <target> --out-dir <out-dir> --verified-flags <out-dir>/cr-verified-<N>-<RUN_TIMESTAMP>.json --clusters <out-dir>/cr-clusters-<N>-<RUN_TIMESTAMP>.json`.
     It is the only path to PENDING rows and fixer staging (it prints the `fixer`: its
     cluster ids, model and staged prompt) and exits 1 on a dropped, extra or duplicated flag or a split blast group.
     Never re-run the collector after it: a re-run renumbers the flags.
  4. Dispatch the fixer with its decision check and post-fix gate, then the fix-recording step
     (`--phase "Code Review"`, no `--reenter`).
  5. **Doc lint** (advisory; twelve fixed checks on docs and scripts): `scripts/doc_lint.py
     --target <target>`. For each finding that is real, fix it and record it with
     `append_ledger.py append <ledger> --runtime <Runtime> --round <N>
     --phase "Code Review" --cluster <next free C-id> --root-cause "doc-lint: <check> <file>:<line>"
     --flags "" --address "FIX (<file>: <edit>)" --blast-radius-status "<closure result>"`. The
     closure result is `clean: token <t>, <n> files, all touched` after `scripts/check_fix_radius.py`
     exits 0 for a changed shared token, else `n/a: single-site change, no shared token`. Expected output: `{"findings": [], "count": 0}`, or every real finding fixed and recorded. The
     next free C-id is `C<k+1>`, where `C<k>` is the highest cluster id any row of round N holds
     (`ledger_common.max_cluster_in_round`; a rejected `append` names it).
  6. **check-pauses**: `scripts/append_ledger.py check-pauses <ledger>` must exit 0. Resolve each
     open pause by deciding the intent-preserving fix, applying it and appending
     `append_ledger.py append <ledger> --runtime <Runtime> --round <N> --phase "<the pause row's
     Phase>" --cluster <next free C-id> --root-cause "<the pause row's root cause>" --flags ""
     --address "FIX (<file>: <edit>; resolves ORCHESTRATOR-PAUSE <flag-id>)"
     --blast-radius-status "<closure result>"`. Copy the pause row's root cause unchanged: the Prepass
     repeat-count guard restarts a finding's count only for a resolving row whose root cause parses to
     the same signature (`ledger_common.split_repeat_clusters`), so an edited one leaves the count at
     its limit and the next `prepass_run.py` auto-pauses the same finding again. Promote to USER-PAUSE only when the intent is
     genuinely not derivable: append a USER-PAUSE row with `append_ledger.py append <ledger> --runtime
     <Runtime> --round <N> --phase "<the pause row's Phase>" --cluster <next free C-id> --root-cause
     "<the pause row's root cause>" --flags <flag-id> --address "USER-PAUSE (<the question>)"
     --blast-radius-status "n/a: single-site change, no shared token"`, then stop and ask the user one
     question naming each candidate fix. The row repeats the pause's flag id on purpose: a pause
     resolves only through a row naming one of its flag ids, so the promoted flag is counted twice in
     the round's raw-flag total (a rare, small effect on the stall heuristic). The open row is what a
     resumed run reads: it asks the user again and never decides the pause without the answer. After the answer append the resolving row
     with `resolves USER-PAUSE <flag-id>`.
  7. **Close the round** (only once every fixer's post-fix gate `check` of this round exits 0 or its
     remaining problems are recorded as ORCHESTRATOR-PAUSE; the gate does not cover the orchestrator's own edits): `scripts/append_ledger.py close-round <ledger> --round <N>` (add `--strengthen-only
     "<reason>"` when every finding was a legitimate STRENGTHEN). When it exits 1 the round stays open and the
     fix-recording step may still need the round's blast file, so clean nothing yet. Once it exits 0, run `scripts/cleanup_tmp_prompts.py --run-timestamp "<Runtime>" --dir <out-dir>`.
     Expected output: close-round exits 0 and prints `gate.continue`. If its `gate.continue` is false,
     go to "Present result"; otherwise append the session-log line of the "Run round N" step with `STEP:round-<N>-closed` and run
     round N+1.

### 3. Convergence (reached only via a clean full-sweep code-review)

A clean full-sweep code-review means both tiers are clean this round: code-review is reachable only
after a clean prepass, and any prepass fix re-enters at prepass. A clean changed-files review never
converges; only the confirming full sweep does.

1. Run `append_ledger.py check-pauses <ledger>`. It should already exit 0, because every pause was
   resolved before this round's sweep re-ran. A pause still open here means the sweep did not cover
   its fix: do not converge. Resolve it as in the check-pauses step, close the round normally (no
   `--converged`) and let the next round's full sweep decide.
   Every row of round N must be resolved (no PENDING address, no open pause), the same
   precondition `close-round` enforces for any round, and every fixer's post-fix gate `check`
   of round N (the Prepass fixer included) must have exited 0 or had its remaining problems recorded
   as ORCHESTRATOR-PAUSE, the orchestrator's own condition from the close-the-round step, which
   `close-round` does not check.
2. Run `scripts/append_ledger.py close-round <ledger> --round <N> --converged`; it writes
   `in-flight:: <timestamp> converged round-<N>` (never hand-edit that marker) and exits 1, leaving the round
   open, on a PENDING row or open pause. Once it exits 0, remove this run's tmp files
   (`scripts/cleanup_tmp_prompts.py --run-timestamp "<Runtime>" --dir <out-dir>`).
3. Append the session-log line of the "Run round N" step with `STEP:round-<N>-converged` and go to "Present result".

### 4. Present result

- Clean up with `scripts/cleanup_tmp_prompts.py --run-timestamp "<Runtime>" --dir <out-dir>` (never
  `--all`) unless the close-the-round step or the Convergence step that removes this run's tmp files already ran it this round, and never
  after a stop that leaves an open round, a USER-PAUSE or hard-error stop (`references/recovery.md` "Stale-tmp cleanup").
- Find, without asking, any other copy of `<target>` that is its source: the installed
  `~/.claude/skills/<basename>/` and any directory named `<basename>` inside the git checkout holding
  `<target>` (take its root from `git -C <target> rev-parse --show-toplevel`, then
  `find <toplevel> -maxdepth 3 -type d -name <basename>`; when `rev-parse` fails, `<target>` is not in a
  checkout and this candidate is skipped), skipping a path that resolves to `<target>` itself. With
  one such copy, run `scripts/post_fix_gate.py merge-check --source <that copy> --audited <target>` and
  report each file it lists as differing (fixes not yet merged back). With none, skip this step. Ask the
  user (one question naming the paths) when there are several, since a wrong guess could
  compare the audit against the wrong copy.
- Point the user at the ledger and say which of these happened:
  - **Convergence**: "Converged after N round(s). Zero flags surfaced in the final full sweep."
  - **Stopped by the gate**: "Stopped after N rounds by <reason>; NOT verified clean." Give the
    per-round raw flag counts. In both, N is the number of rounds this run executed (the last round's
    number minus `run-start-round`, plus 1), not the last round number in a reused ledger.
  - **Stopped at a USER-PAUSE**: "Stopped in round N awaiting your decision: <question>; NOT
    verified clean." Give the pause's flag ids and the candidate fixes.
  - **Hard unrecoverable error**: "Stopped in round N on <error>; NOT verified clean." Name the
    failing script or agent and the path, and leave the ledger as it stands.
- Give a per-round summary (raw flags, rows, FIX / STRENGTHEN / ORCHESTRATOR-PAUSE); rows is the round's ledger-row count, which includes resolving, USER-PAUSE, doc-lint and waiver rows as well as cluster rows.
- If converged, suggest `/skill-publisher <target>` for the ship phase.

## Example

User: "trace skill drive-organizer".

1. Resolve `<target>` to `~/.claude/skills/drive-organizer/` and `<ledger>` to
   `${XDG_DATA_HOME:-$HOME/.local/share}/skill-tracer-audit-ledger/drive-organizer.md`. Expected
   output: no ledger yet, so round 1 of a fresh run; `begin-round` creates it.
2. Round 1: prepass until `{"status":"converged"}`, then `code_review_run.py` and two cold reviewers.
   Expected output: `{"status":"verified-flags", …}`; cluster, fix, record, close the round. Its
   `gate.continue` is true.
3. Round 3 or later, after a clean changed-files review: re-run with `--scope full`. Expected output:
   `{"status":"code-review-clean"}`.
4. Convergence step, then Present result. Expected output: "Converged after N round(s). Zero flags
   surfaced in the final full sweep." and a pointer to the ledger.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `skill-tracer must be invoked from the top-level Claude session` | `Agent` is absent: this is a nested or restricted session | Re-invoke from the top-level session |
| `scripts/<name>.py: No such file` or exit 127 | A relative script path under zsh | Run `python3 <absolute-script-path>` |
| `begin-round` exits 2 naming a different target | The ledger records another target | Give this target its own `<ledger>` path |
| `check-pauses` exits 1 | An ORCHESTRATOR-PAUSE or USER-PAUSE is open | Resolve each listed pause (check-pauses step), re-run |
| `close-round` exits 1 | A row is still PENDING, a pause is open, or no FIX row exists | Run the fix-recording step for PENDING rows; resolve open pauses (check-pauses step); for an all-STRENGTHEN round pass `--strengthen-only "<reason>"` (`references/script-contract.md`) |
| `post_fix_gate.py` exits 1 | A fix broke a path, flag, identifier or added behaviour | Post-fix gate procedure; after 2 inner passes it becomes an ORCHESTRATOR-PAUSE |
| `post_fix_gate.py` exits 2 | Unreadable input | The cause and remedy it prints; the exit-2 table in the Post-fix gate paragraph above |
| A run stopped with "NOT verified clean" | A gate stop, USER-PAUSE or hard error | `references/recovery.md` "Hard unrecoverable errors"; after a gate stop a new invocation starts a fresh run, after a USER-PAUSE or hard error it resumes the open round (fresh-run-or-resume test) |

## Where the details live

- `references/dispatch.md`: dispatch prompt text, manifests, reviewer edit detection, the
  out-of-target fixer restore, the post-fix gate procedure, contract recovery, the Explore trade-off, the provenance pointer.
- `references/recovery.md`: in-flight marker grammar, resume table, persisted run options,
  hard-error list, stale-tmp cleanup.
- `references/script-contract.md`: non-zero exit handling per script (including
  `post_fix_gate.py`) and the script index.
- `references/how-to-fix.md`: FIX / STRENGTHEN / ORCHESTRATOR-PAUSE doctrine, the frozen interface
  and fix-impact closure.
- `references/glossary.md`: defined terms.
