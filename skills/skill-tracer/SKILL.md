---
name: skill-tracer
description: 'Use when the user''s core intent is defect discovery: finding bugs, auditing correctness, or verifying that code works as intended in an already-built skill, codebase, or directory. Canonical triggers: "trace X", "audit X for bugs", "check X for issues", "validate X scripts", "verify X", "is X clean?", "run the cascade on X". The decisive signal is the ACTION — auditing vs. building vs. shipping. Do NOT use it when the action is ship / publish / release / package / PR (use skill-publisher) or create / build / scaffold (use skill-creator-ccvw) — regardless of what the target is named. Here "trace" means bug-auditing a codebase — not distributed tracing or stack traces.'
license: MIT
compatibility: Claude Code 2.0 or newer
metadata:
  tier: claude-users
  created: "2026-06-27"
  created-by: Vaikri-costume
  version: "3.6.0"
  parent-version: "2.2.0"
  intended-audience: claude-users
allowed-tools:
  - Agent
  - Read
  - Edit
  - Write
  - Bash
  - SendMessage
---

<!-- Provenance, version, attribution, and changelog live in HISTORY.md.
     Human-facing intent lives in README.md.
     This file is the runnable orchestrator contract for the normal path; resume, stop and
     hard-error detail lives in references/recovery.md, and the other long procedures in
     references/ (dispatch.md, script-contract.md, how-to-fix.md, glossary.md). -->

# skill-tracer

## What this skill does

Finds bugs and verifies correctness in a target skill, codebase, or directory by running a
**2-tier cascade** each round:

- **Prepass**: deterministic checks for broken references (cited paths, `Step N` pointers, dead
  scripts, sub-step labels, CLI flags a doc cites for a script that does not register them,
  duplicated regexes); clusters and fixes them in-round; re-enters until clean, each finding
  getting at most 2 fixer passes per round before it is auto-paused (the retry bound below).
- **Code-review**: two cold reviewer agents (READ-ONLY) read the review scope on one all-lens
  prompt; their flags pass the `coverage gate` and the `no-drop gate`, are clustered and fixed.

Read-only agents are dispatched with `subagent_type: Explore`, which has **no Edit/Write tools**.
A prompt-only "do not edit" rule is insufficient as enforcement; the prompt's read-only wording
is a secondary statement, and the missing tools are the enforcement.

## When to invoke

- "trace <target>", "audit <target>", "run the cascade on <target>", "check <target> for bugs",
  "verify <target>".
- Proactively after the user creates or significantly edits a skill. A proactive start counts as
  an invocation in that turn for the fresh-run test (Run options).

## Prerequisites

- `<target>`: absolute path to the directory to audit (a bare name resolves to
  `~/.claude/skills/<name>/`); must exist and be readable.
- `<ledger>`: `${XDG_DATA_HOME:-$HOME/.local/share}/skill-tracer-audit-ledger/<basename>.md`, where
  `<basename>` is the final component of `<target>`. Resolve it once to an absolute path and pass
  that literal path to every script (no script reads the variables). `begin-round` creates it and
  refuses (exit 2) a ledger that records a different target: then give this target its own path.
- Scripts live at `~/.claude/skills/skill-tracer/scripts/`. Always run
  `python3 <absolute-script-path>`; `scripts/<name>.py …` below is shorthand for that. A bare
  relative path fails under zsh (exit 127).
- `Agent` must be available. It exists only in the **top-level** session: if the `Agent` tool is
  absent, stop and tell the user "skill-tracer must be invoked from the top-level Claude session;
  it needs the Agent tool to dispatch cold reviewers."
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
  --set run-start-round=<N> [--set rounds-budget=<N>] [--set max-rounds=<cap>]
```

The `max-rounds` cap defaults to 8; with `--rounds N` above 8 also set `max-rounds=<N>`. On an
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
  round's marker), the skill was invoked this turn, by the user or proactively, and no `begin-round`
  has run since that invocation. Its first `begin-round` passes `--set`.
- Neither (no open-round marker, and either no invocation this turn or a `begin-round` already run
  since it, e.g. a compaction between two rounds of one run, or the next round that `close-round`'s
  gate starts in the same turn): start the next round of the same run without `--set`.

**Retry bound.** The fixer re-emit after a failed decision check, the fixer re-dispatch after an
out-of-target edit and the reviewer re-dispatch after an edit each stop after 2 retries, as do the post-fix gate's inner passes (the fixer re-emit after `post_fix_gate.py check` exits 1); the third failure becomes an
ORCHESTRATOR-PAUSE as each step states (for a reviewer slot, a hard unrecoverable error), never a
further retry. The prepass re-fix of a returning finding gets 2 fixer passes per round; its next
return is auto-paused (`ledger_common.AUTO_PAUSE_REPEATS`). Contract recovery
keeps its own stated limits (`references/dispatch.md` "Contract recovery").

## Stop rules

The cascade stops only for: **convergence** (a clean full-sweep code-review with all pauses
resolved); the **round gate** (`round-cap`, `budget-exhausted` or `stalled`, reported by every
`close-round`); a **USER-PAUSE** (a decision not derivable from the target's files); or a **hard
unrecoverable error** (the list is in `references/recovery.md` "Hard unrecoverable errors").

A gate stop is NOT convergence: report "stopped by <reason>, not verified clean", list what the
last round fixed and what was still flagged, and say the run can be extended.

**FORBIDDEN-PAUSE.** While a run is in progress never offer to pause or stop early for tail
issues, diminishing returns, "minor" findings, session length, round size, cluster count or token
cost. The gate
is the only cost control.

**Fix depth.** Every round, considered-fix and the fixer apply the deepest root fix that does not
widen the interface, and fix every finding regardless of a "minor" label. The interface is frozen
from round 1 of a run: a fix that would add a CLI flag, mode, subcommand, file, ledger field, run-options key, row
kind, shared helper module or doc section becomes an ORCHESTRATOR-PAUSE, unless it is the only way to fix a real
behaviour bug. When the behaviour is already correct and only a comment or doc is wrong, fix the
comment or doc, not the code (`references/how-to-fix.md` "Frozen interface"). A fixer adds no new
behaviour: a fix makes the doc match the code, or the code match its documented contract. Adding a
retry, cap, branch or exit path, or removing a fallback, is new behaviour: apply no edit for that
cluster and emit ORCHESTRATOR-PAUSE naming it.

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
  <ledger>` and `grep '^in-flight::' <ledger>`, then apply the fresh-run-or-resume test (Run
  options): an open-round marker means resume it (`references/recovery.md` "Resume"); a `converged`
  marker, a closed round, or no marker means start round N+1.

### 2. Run round N

Run `scripts/append_ledger.py begin-round <ledger> --round <N> --runtime <Runtime> --target <target>`
(plus `--set` on a fresh run). It writes the round's first marker, `prepass running round-<N>`;
scripts own the marker, so never write it by hand. Append
`**[HH:MM:SS] skill-tracer — <basename> — round <N> START**` to
`~/.claude/session-logs/session-log-$(date +%Y-%m-%d).md` (a failed echo never blocks).

**Fixer dispatch.** The tier script prints `batches`, each with a staged prompt and a `model`:
`opus` when a cluster touches a `.py` file, `sonnet` when all are doc-only. A round of 12 clusters
or fewer is one batch (one fixer); only above 12 is it split into batches of at most 12, code
clusters first. Dispatch one fixer per batch (`subagent_type: general-purpose`) ONE AT A TIME,
in order, never in parallel (batches may edit the same files), pointed at its prompt with the
provenance wording in `references/dispatch.md`; record each `agentId` in the fixer manifest at once.
A fixer edits only files under `<target>`; check its Edit/Write paths and `touched_files`. On an
out-of-target edit, restore it, discard that fixer's decisions (record none of them) and re-dispatch
a fresh fixer with the same staged prompt plus an "edit only files under `<target>`" constraint
(`references/dispatch.md` "A fixer that edits outside `<target>`"). After 2 such re-dispatches for one
batch, leave that batch's transcript out of the fix-recording step: its clusters get no decision
and fill-address records them as ORCHESTRATOR-PAUSE.

**Decision check.** Before the next batch, run `scripts/check_decisions.py --fixer-transcript
<transcript> --expect <the batch's cluster ids>`. On exit 1 (empty address, wrong kind prefix, banned
vocabulary, missing cluster, or a FIX without its **Closure block**: non-empty `Siblings:`, `Bound:`
`Claims:` and `Blocks:` lines, `references/how-to-fix.md` "Closure block") `SendMessage` the same fixer the
problems to re-emit; check again. After
2 re-emits that still fail, stop asking: leave that batch's transcript out of the fix-recording step
(when no batch is left, pipe `{"decisions": []}` on stdin instead of `--fixer-transcript`), so
fill-address records its clusters as ORCHESTRATOR-PAUSE; resolve them at the check-pauses step,
checking the edits that fixer already made.

**Post-fix gate.** Before dispatching each fixer batch, run `scripts/post_fix_gate.py snapshot
--target <target> --out <out-dir>/gate-<N>-b<k>-<RUN_TIMESTAMP>.json` (batch `<k>`), once per batch: an
out-of-target re-dispatch keeps the batch's first snapshot, so `check` also sees the in-target edits
of the discarded fixer, which stay on disk. After the batch's
decision check passes, run `scripts/post_fix_gate.py check --target <target> --snapshot <that file>
--fixer-transcript <the batch's transcript>`.
Run `check` the same way for a batch left out of the fix-recording step (2 failed re-emits, or 2
out-of-target re-dispatches): its clusters are already ORCHESTRATOR-PAUSE, so send it nothing and
resolve its listed problems with those pauses at the check-pauses step.
Exit 1 blocks closing this round (an orchestrator rule: `close-round` itself does not read the
gate): send the listed problems to the same fixer as a
(line, claim, evidence) list (`<file>:<line>`, the problem's `kind`, the problem text; line 0 means
the whole file, as for a `syntax` problem, a touched .py file that no longer parses) to fix and
re-emit its decisions, then run the decision check and `check` again; at most 2 such inner passes
(the retry bound). A `block-reread` problem names a rewritten doc block: the fixer re-reads it whole
and lists it in its Closure `Blocks:` line (`references/how-to-fix.md` "Closure block"); the next
`check` reads that line from `--fixer-transcript`. Send with the problems the **siblings list**
(`check`'s non-blocking `siblings`: the few untouched lines naming a distinctive term of a touched doc
line; `siblings_omitted` counts the terms too common to list), asking the fixer to update or confirm
each in its Closure block. A problem still listed after the 2 inner passes, and any `new-behaviour` problem at once, becomes
an ORCHESTRATOR-PAUSE: `SendMessage` the fixer to re-emit the decision of each cluster that touched
that file as `ORCHESTRATOR-PAUSE (post-fix gate: <file>:<line> <problem>)`, so fill-address records an
open pause that the check-pauses step resolves. This gate outcome takes precedence over
`references/how-to-fix.md`'s "never a fix-failure fallback" rule, and it applies also to a
contract-required or real-bug fix that adds a raise, return or branch node: the check-pauses step
resolves that pause like any other. The one exception is a behaviour-preserving
refactor (the same inputs give the same outputs, exits and messages): re-run
`post_fix_gate.py check --accept-new-behaviour <file>:<kind>` (`<kind>` is the node kind the problem
text names, `<kind> count N -> M`: one of `raise`, `return`, `exit`, `if`, `for`, `while`, `try`,
`ifexp`, `boolop`; not `new-behaviour`), then record the waiver as a ledger row
appended as in the doc-lint step, with `--phase` the batch's phase (`Prepass` or `"Code Review"`),
root cause `post-fix gate waiver: <file>:<kind>` and `--address "FIX (<file>: <the refactor>)"`.
Exit 2 is unreadable input. `post_fix_gate.py` prints `cause` and `remedy` in its stderr JSON; follow
that remedy. Every cause, with its remedy, is this table, generated from the script
(`post_fix_gate.py causes --write SKILL.md`; a test fails when it differs or when a raise names no cause), so
it is not edited by hand:

<!-- gate-exit2:begin -->
| Cause | Observable | Remedy |
|---|---|---|
| not-a-directory | `--target is not a directory: <path>` (`snapshot`, `check`) or `not a directory: <path>` (`merge-check`) | fix the path and re-run |
| unreadable-target-file | `cannot read <path>: ...` (an in-scope target file that is not UTF-8 text) | fix that file and re-run |
| snapshot-unusable | `unreadable snapshot <path>: ...` (the `--snapshot` path names no file, or the file is not a snapshot), or `lint data is not a JSON object` / `<source> lint data is not a JSON object` with this `cause` (the snapshot's stored `lint` field is malformed) | the batch's baseline is lost: take no new snapshot after the batch has edited the target, report the batch as unchecked and `SendMessage` the fixer to re-emit the decision of each of its clusters as `ORCHESTRATOR-PAUSE (post-fix gate: snapshot missing or unreadable)` |
| lint-run-failed | `<script> printed no JSON ...`, `<script> exited <N>: ...` or `lint data is not a JSON object`, printed by `check` (`doc_lint.py` or `cascade_sweep.py` failed) | report the batch as unchecked and `SendMessage` the fixer to re-emit the decision of each of its clusters as `ORCHESTRATOR-PAUSE (post-fix gate: lint run failed)` |
| snapshot-lint-failed | the same texts, printed by `snapshot` (before the batch is dispatched) | do not dispatch the batch: leave its transcript out of the fix-recording step so fill-address records its clusters as ORCHESTRATOR-PAUSE |
| baseline-unusable | `unreadable --baseline-lint <path>: ...` or `<source> lint data is not a JSON object` (including a dict holding only one of `doc_lint` / `cascade`) | fix that file and re-run (SKILL.md's commands never pass `--baseline-lint`) |
| ledger-unreadable | `unreadable ledger <path>: ...` (`survival`) | stop ("Broken ledger" in `references/script-contract.md`) |
| survival-row-ambiguous | `--row <id> matches <N> ledger rows (pass --round)`, N above 1 (`survival`) | re-run with the right `--round` |
| survival-row-missing | `--row <id> matches 0 ledger rows` (`survival`) | correct `--row` or `--round` and re-run |
<!-- gate-exit2:end -->

**Fix-recording step.** After the last batch's check passes, record every batch's decisions at once:

```bash
python3 .../scripts/ledger_cascade.py <ledger> --mode fill-address --phase "<Phase>" --round <N> \
  --runtime <Runtime> --fixer-transcript <batch-1-transcript>,<batch-2-transcript>,… \
  --skill-root <target> --blast-json <out-dir>/blast-round-<N>-<RUN_TIMESTAMP>.json [--reenter] [--allow <files>]
```

`--phase` is `Prepass` (with `--reenter`) or `"Code Review"` (without). Write the tier script's
`"blast"` array to the blast file first as `{"blast_radius": <blast>}`; fill-address re-checks every
TOKEN-BLAST cluster with `check_fix_radius.py` and refuses uncovered sites. `--allow` is only for a
site that legitimately keeps the token, with the reason in the FIX address. A cluster the fixer
skipped becomes an ORCHESTRATOR-PAUSE; when the printed marker's state (its third field,
`<Runtime> <phase> orch-fixes round-<N>`) is `orch-fixes`, resolve the pauses (check-pauses step
below) before re-running any tier script.

#### Prepass

```bash
python3 .../scripts/prepass_run.py --target <target> --ledger <ledger> --round <N> --runtime <Runtime> --out-dir <out-dir>
```

- `{"status":"converged","next":"code-review"}`: go to Code-review (the script advanced the marker).
- `{"status":"needs-fix","batches":[…]}`: dispatch the fixer batches, run the fix-recording step
  (`--phase Prepass --reenter`), then re-run `prepass_run.py` with the same round. The loop is
  bounded per finding: a signature already addressed twice this round (two fixer passes) is not
  sent to a fixer again but auto-paused (`auto_pause`, `ledger_common.AUTO_PAUSE_REPEATS`).
- `{"status":"needs-record"}`: a fixer ran but its decisions were never recorded; run its decision
  check and post-fix gate `check` (`references/recovery.md` "A fixer already ran"), then the
  fix-recording step, then re-run `prepass_run.py`.
- `auto_pause` (with or without `batches`): a finding already addressed twice this round came
  back; it is an open ORCHESTRATOR-PAUSE row. With `batches`, first dispatch them and run the
  fix-recording step as for `needs-fix`; then resolve each pause with a different fix (check-pauses
  step), and only then re-run `prepass_run.py`. When the same signature is auto-paused again after
  the orchestrator has resolved it twice this round, promote it to USER-PAUSE (check-pauses step).
- Exit 1 with `detector_errors`: a detector crashed; hard error, never `converged`.

#### Code-review

```bash
python3 .../scripts/code_review_run.py --target <target> --ledger <ledger> --round <N> --runtime <Runtime> --out-dir <out-dir> [--scope full]
```

It decides the review scope (`auto`): every in-scope file (`scripts/inscope.py`) in rounds 1-2 of a run; from round 3,
only the files the previous round's and this round's ledger addresses name (the files the fixes
touched), or every in-scope file when those addresses name none (that review is a full sweep, so a
clean one is `code-review-clean`). It stages the all-lens prompt, records the scope for the collector and prints a
`dispatch` array of two generalists (`G1`, `G2`; from round 2 G2's prompt asks for reverse file
order), each with its staged prompt. Take the edit-detection baseline
(`references/dispatch.md` "A reviewer that edits a file"), dispatch both in ONE same-turn message
(`model: sonnet`, `subagent_type: Explore`) with the code-reviewer provenance wording in
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
     It is the only path to PENDING rows and fixer staging (it prints the `batches`, each with its
     cluster ids, model and staged prompt) and exits 1 on a dropped, extra or duplicated flag or a split blast group.
     Never re-run the collector after it: a re-run renumbers the flags.
  4. Dispatch the fixer batches with their decision checks, then the fix-recording step
     (`--phase "Code Review"`, no `--reenter`).
  5. **Doc lint** (advisory; twelve fixed checks on docs and scripts): `scripts/doc_lint.py
     --target <target>`. For each finding that is real, fix it and record it with
     `append_ledger.py append <ledger> --runtime <Runtime> --round <N>
     --phase "Code Review" --cluster <next free C-id> --root-cause "doc-lint: <check> <file>:<line>"
     --flags "" --address "FIX (<file>: <edit>)" --blast-radius-status "<closure result>"`. The
     closure result is `clean: token <t>, <n> files, all touched` after `scripts/check_fix_radius.py`
     exits 0 for a changed shared token, else `n/a: single-site change, no shared token`. The
     next free C-id is `C<k+1>`, where `C<k>` is the highest cluster id any row of round N holds
     (`ledger_common.max_cluster_in_round`; a rejected `append` names it).
  6. **check-pauses**: `scripts/append_ledger.py check-pauses <ledger>` must exit 0. Resolve each
     open pause by deciding the intent-preserving fix, applying it and appending
     `append_ledger.py append <ledger> --runtime <Runtime> --round <N> --phase "<the pause row's
     Phase>" --cluster <next free C-id> --root-cause "<the pause row's root cause>" --flags ""
     --address "FIX (<file>: <edit>; resolves ORCHESTRATOR-PAUSE <flag-id>)"
     --blast-radius-status "<closure result>"`. Promote to USER-PAUSE only when the intent is
     genuinely not derivable: stop, ask the user one question naming each candidate fix, and after
     the answer append the resolving row with `resolves USER-PAUSE <flag-id>`.
  7. **Close the round** (only once every batch's post-fix gate `check` of this round exits 0 or its
     remaining problems are recorded as ORCHESTRATOR-PAUSE): `scripts/cleanup_tmp_prompts.py --run-timestamp "<Runtime>" --dir <out-dir>`,
     then `scripts/append_ledger.py close-round <ledger> --round <N>` (add `--strengthen-only
     "<reason>"` when every finding was a legitimate STRENGTHEN). If its `gate.continue` is false,
     go to "Present result"; otherwise append `… round <N> CLOSED` to the session log and run
     round N+1.

### 3. Convergence (reached only via a clean full-sweep code-review)

A clean full-sweep code-review means both tiers are clean this round: code-review is reachable only
after a clean prepass, and any prepass fix re-enters at prepass. A clean changed-files review never
converges; only the confirming full sweep does.

1. Run `append_ledger.py check-pauses <ledger>`; resolve any open pause as in the check-pauses step.
   Every row of round N must be resolved (no PENDING address, no open pause), the same
   precondition `close-round` enforces for any round, and every fixer batch's post-fix gate `check`
   of round N (prepass batches included) must have exited 0 or had its remaining problems recorded
   as ORCHESTRATOR-PAUSE, the orchestrator's own condition from the close-the-round step, which
   `close-round` does not check.
2. Remove this run's tmp files (collection is complete, so the `dispatched` marker no longer needs
   them), then `scripts/append_ledger.py close-round <ledger> --round <N> --converged`.
   It writes `in-flight:: <timestamp> converged round-<N>`; never hand-edit that marker.
3. Append `… round <N> CONVERGED` to the session log and go to "Present result".

### 4. Present result

- Clean up with `scripts/cleanup_tmp_prompts.py --run-timestamp "<Runtime>" --dir <out-dir>` (never
  `--all`), except after a hard-error stop in a `dispatched` state (`references/recovery.md`
  "Stale-tmp cleanup").
- When the run audited a copy of a source tree, run `scripts/post_fix_gate.py merge-check --source
  <src> --audited <copy>` and report each file it lists as differing (fixes not yet merged back).
- Point the user at the ledger and say which of these happened:
  - **Convergence**: "Converged after N round(s). Zero flags surfaced in the final full sweep."
  - **Stopped by the gate**: "Stopped after N rounds by <reason>; NOT verified clean." Give the
    per-round raw flag counts and say the run can be extended.
  - **Stopped at a USER-PAUSE**: "Stopped in round N awaiting your decision: <question>; NOT
    verified clean." Give the pause's flag ids and the candidate fixes.
  - **Hard unrecoverable error**: "Stopped in round N on <error>; NOT verified clean." Name the
    failing script or agent and the path, and leave the ledger as it stands.
- Give a per-round summary (raw flags, clusters, FIX / STRENGTHEN / ORCHESTRATOR-PAUSE).
- If converged, suggest `/skill-publisher <target>` for the ship phase.

## Where the details live

- `references/dispatch.md`: dispatch prompt text, manifests, reviewer edit detection, the
  out-of-target fixer restore, contract recovery, the Explore trade-off, the provenance pointer.
- `references/recovery.md`: in-flight marker grammar, resume table, persisted run options,
  hard-error list, stale-tmp cleanup.
- `references/script-contract.md`: non-zero exit handling per script (including
  `post_fix_gate.py`) and the script index.
- `references/how-to-fix.md`: FIX / STRENGTHEN / ORCHESTRATOR-PAUSE doctrine, the frozen interface
  and fix-impact closure.
- `references/glossary.md`: defined terms.
