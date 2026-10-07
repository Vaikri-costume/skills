# Recovery reference

Contents: in-flight marker · resume table · persisted run options · hard unrecoverable errors ·
stale-tmp cleanup.

## In-flight marker

The ledger header holds at most one line:

```
in-flight:: <Runtime> <phase> <state> round-<N>
```

`<phase>` is `prepass` or `code-review`. `<state>` is `running`, `addressing`, `dispatched`
(optionally `dispatched-<n>`, the fan-out count) or `orch-fixes`. A Prepass fix is recorded with
`--reenter`, so its marker stays `prepass` (`prepass running`, or `prepass orch-fixes` when a
decision is ORCHESTRATOR-PAUSE). This is the `VALID_STATES` / `VALID_PHASES` set
`scripts/ledger_common.py` defines; the code is the source of truth if this list and the code
disagree. `ledger_common.parse_in_flight` reports `phase_valid` / `state_valid` for a marker, but no
script refuses an invalid one, so check them when reading a marker: a phase or state outside these
sets is a broken ledger (Hard unrecoverable errors, "A broken ledger").

*Legacy phase.* Ledgers written before 3.1.0 may carry a `minor-bugs` phase; for legacy
compatibility the parser migrates it to `code-review running` (code-review followed that removed
tier in the cascade), so such a ledger resumes at the code-review row of the table below.

The terminal convergence record has no phase:

```
in-flight:: <timestamp> converged round-<N>
```

It is written only by `close-round --converged`; never hand-edit or clear it. Every marker has a
script that owns it: `append_ledger.py begin-round` writes a round's first marker (`prepass running
round-<N>`, creating the ledger on round 1), `prepass_run.py`, `code_review_run.py` and
`ledger_cascade.py` advance it, and `close-round --converged` writes the terminal record.

## Resume

At every invocation, including after a compaction: `grep '^in-flight::' <ledger>`, then read the
persisted run options (`scripts/append_ledger.py options <ledger>`) and apply SKILL.md's
fresh-run-or-resume test (Run options): an open-round marker is a resume whether or not the user
invoked the skill this turn, and a resume passes no `--set`. When the marker names a round
that is still open, take the marker's `<Runtime>` as this resume's `<Runtime>`: every staged and tmp
file of the interrupted pass, and the scoped cleanup, carry its `<RUN_TIMESTAMP>`. Then re-run the
in-flight phase's front-half script, except for a `dispatched` state, where the agents already ran
and their output is re-collected from their transcripts instead of being re-dispatched.

A re-run is idempotent: `ledger_cascade.py --mode cluster` supersedes (drops) PENDING rows of the
same round and phase left by an interrupted pass and continues cluster ids and flag numbers past
them; ORCHESTRATOR-PAUSE rows are never superseded, and `prepass_run.py` does not write a second
auto-pause row for a signature that already has an open one.

**A fixer already ran** for a batch of a tier's PENDING rows when the fixer manifest
(`<out-dir>/dispatch-fixer-<RUN_TIMESTAMP>.json`; `references/dispatch.md` "Dispatch manifests")
names that tier's phase and that batch's agent transcript ends with a `{"decisions": …}` object
whose cluster ids are the batch's PENDING rows' ids. When every batch's fixer ran, run the decision
check on each, then the post-fix gate `check` for each batch whose `check` you have not seen pass,
with that batch's snapshot `<out-dir>/gate-<N>-b<k>-<RUN_TIMESTAMP>.json` (`references/dispatch.md` "Post-fix gate";
a missing snapshot is its `snapshot-unusable` cause), and record all their transcripts in one
`--fixer-transcript` list only once each `check` exits 0 or its problems are ORCHESTRATOR-PAUSE. When only the first
batches ran, or at Code Review while the round has `Code Review` PENDING rows and no batch ran, dispatch the remaining
batches from their staged prompts (`prepass-b<k>-<RUN_TIMESTAMP>.txt` or `code-review-b<k>-<RUN_TIMESTAMP>.txt` in
`<out-dir>`), then record: re-running `code_review_run.py` there would re-review (the review is not deterministic) and
`cluster_enforce.py` would then supersede those rows. When no fixer ran and no such Code Review PENDING rows exist,
re-run that tier's front-half script, same round.

| Marker | Resume action |
|---|---|
| `prepass *` | If this round has `Prepass` PENDING rows and a fixer already ran, run its checks and record its decisions first ("A fixer already ran" above; fix-recording step, `--phase Prepass --reenter`). Otherwise re-run `prepass_run.py`, same round; for `prepass orch-fixes`, first resolve each open pause (`append_ledger.py check-pauses`) so the re-run does not send the paused defect to a fixer again |
| `code-review running` / `addressing` / `orch-fixes` | If this round has `Code Review` PENDING rows and no fixer ran, dispatch their batches from the staged prompts and record ("A fixer already ran" above). If it has them and a fixer already ran, run its checks and record its decisions first ("A fixer already ran" above; fix-recording step, `--phase "Code Review"`, no `--reenter`): re-running the tier would supersede them (`cluster_enforce.py` writes rows through `ledger_cascade.py --mode cluster`, which drops this round's stale Code Review PENDING rows; `code_review_run.py` itself writes no rows). If this round has `Code Review` rows and none is PENDING, the fixes are recorded: continue at doc lint / check-pauses / close-round. If this round has no `Code Review` row, re-run `code_review_run.py`, same round (it derives the scope from the ledger again, so it picks the same scope) |
| `code-review dispatched` | Re-collect if the transcripts named in the review manifest exist in `<projects-dir>`, else re-dispatch; then `code_review_collect.py` with the marker's `<Runtime>`. The collector needs the scope record (see the review-scope note below) |
| `converged round-N` | Terminal. When SKILL.md's fresh-run-or-resume test finds a fresh run (invoked this turn, no `begin-round` since), start round N+1; otherwise go to "Present result" |
| Any marker naming a round that already has a `Round N total` summary comment | That round was closed without converging (`close-round` leaves the last marker in place). Apply SKILL.md's fresh-run-or-resume test: a fresh run starts round N+1; otherwise start round N+1 only when `append_ledger.py gate <ledger> --round <N>` exits 0, else go to "Present result". `begin-round` refuses to restart a closed round |
| No marker, prior rounds exist | Round N+1, subject to the same gate test as the closed-round row above, which a fresh run skips (`begin-round` takes `--set` options only on a fresh run, which SKILL.md's fresh-run-or-resume test decides; "Persisted run options" below) |
| No marker, no ledger | Round 1 |

*Review scope on resume.* `code_review_run.py` writes the scope record
`<out-dir>/cr-scope-<N>-<RUN_TIMESTAMP>.json` and the collector reads it, so the coverage gate checks
exactly the files the reviewers were given. If the record is gone (`/tmp` cleared), the collector
assumes a full sweep and a changed-files review fails its coverage gate: re-run
`code_review_run.py` and re-dispatch instead. If the record is newer than the review manifest (an
interrupted `--scope full` re-run after `changed-scope-clean`), the manifest's agents reviewed only
the changed files: dispatch the full sweep rather than re-collecting.

Manifests and cluster JSON live under `<out-dir>` in `/tmp`; if `/tmp` was cleared and no fixer ran
for the round's PENDING rows, re-run the front-half script (it re-stages) instead of looking for them; for a
round whose PENDING rows await a fixer or its recording, follow "A fixer already ran" above (and "Lost blast file" below).

*Lost blast file.* When a fixer already ran (`needs-record`, or a recorded-fixer resume) and the
blast file `<out-dir>/blast-round-<N>-<RUN_TIMESTAMP>.json` is gone, re-running the front-half script
does not print the blast again. Rebuild it from the fixers' transcripts: each staged fixer prompt
embeds its batch's blast JSON (the `[BLAST]` slot `assemble_fix_prompt.py` fills), and the fixer's
Read of that prompt in its transcript holds the text. Concatenate every batch's `blast_radius`
entries (Read line-number prefixes removed) into `{"blast_radius": [...]}`, write that file, then run
the fix-recording step.

## Persisted run options

`run-options:: rounds-budget=… max-rounds=… run-start-round=…` on the ledger header (format v2).
`scripts/append_ledger.py options <ledger> [--set k=v …]` reads or merges it; any other key is
refused. The round gate (`append_ledger.py gate`, also reported by `close-round`) reads `max-rounds`
(default 8), `rounds-budget` and `run-start-round` from it, so a compaction cannot turn `--rounds N`
into an unbounded run. `run-start-round` also counts the run's rounds for the auto review scope and
for the round number the frozen-interface rule names (`references/how-to-fix.md` "Frozen interface").

A fresh run on an existing ledger sets `run-start-round` to its first round so the cap counts only
this run's rounds, and clears a previous run's `rounds-budget` / `max-rounds` with an empty value
(`--set rounds-budget=` removes the key) unless this run sets its own, because a merge alone never
removes a key.

*Legacy keys (v1).* Ledgers written before 3.1.0 may carry `mode=` and cr-mode keys. The parser
migrates them for legacy compatibility: `mode=one-round` becomes `rounds-budget=1` (unless a budget
is already set); every other `mode` value and every cr-mode value is dropped, because those modes no
longer exist. The next write stores the v2 form.

## Hard unrecoverable errors

The run stops, NOT verified clean, on any of these:

1. A broken ledger: a row or header line the scripts reject, or a marker no script can advance.
2. A missing prerequisite (SKILL.md "Prerequisites").
3. A prepass detector that crashes or cannot load (`prepass_run.py` exit 1 with `detector_errors`),
   or a sub-script of `prepass_run.py` that fails (exit 1 with an `error` key on stderr and no
   `detector_errors`); neither is ever read as a clean tier.
4. A cold code-review agent that aborts because files in its staged list do not exist
   (`aborted_agents` from `code_review_collect.py`).
5. A cold-agent slot that stays invalid after the retries in `references/dispatch.md` "Contract
   recovery".
6. A fixer's out-of-target Write over an existing file that cannot be restored because the fixer's
   earlier Read of it did not return the whole file (`references/dispatch.md` "A fixer that edits
   outside `<target>`").
7. A code-review slot whose reviewer edits a file a third time, after the 2 re-dispatches
   `references/dispatch.md` "A reviewer that edits a file" allows.

The retry bound's fixer loops are not on this list: a fixer that still fails its decision check after
2 re-emits, or edits outside `<target>` after 2 re-dispatches, leaves its batch's clusters as
ORCHESTRATOR-PAUSE (SKILL.md "Decision check" and "Fixer dispatch"), and the run continues.

Report it as "Stopped in round N on <the error>; NOT verified clean", naming the failing script or
agent and the path, and leave the ledger as it stands for the user to inspect.

## Stale-tmp cleanup

`<out-dir>` is shared across every invocation and target; a blanket wipe can delete another
still-active run's files. Clean only with a timestamp to scope to, never `--all`:

- `converged round-N`: do not clean. The convergence step removes the run's tmp files before
  `close-round --converged` writes this marker, and the marker's timestamp is the time of that
  close, not the run's `<Runtime>`, so it selects none of the run's files.
- No marker (prior rounds or none): do not clean; there is no timestamp to scope to.
- Never after a stop that leaves an open round (a USER-PAUSE or hard-error stop), whatever its marker: "A fixer already ran"
  and the marker table above read the fixer manifest, the staged prompts and the gate snapshots in `<out-dir>`, and a
  `dispatched` state also reads the review manifest and scope record (the agents' transcripts in `<projects-dir>` are
  checked before deciding to re-collect or re-dispatch). The Convergence step is not such a stop: its collection is complete.

There is deliberately no self-perpetuating resume wakeup: recovery is always to read the marker on
disk and re-run the front-half script.
