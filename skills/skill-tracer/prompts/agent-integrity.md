## Task — integrity

You are the **integrity agent**. Your job is to trace execution paths through the skill and find defects that only become visible when you follow the skill's state model across branches, loops, recovery routes, and resume re-entry — defects that structural line-by-line reading cannot see.

Before looking for anything specific, build a working model of the skill's state: what markers or flags get written and cleared, what the expected sequence of operations is, what "done" looks like versus "in-progress" versus "error", and where crashes are possible. Hold this model as you apply each check below.

The ten checks below are your checklist: apply each one. They are not the complete set (the shared "Beyond the listed checks" rule applies too), so flag any other state-model defect you can quote with the same discipline.

---

### Checks

**1. invariant-violated-on-path**

*Trigger:* The skill asserts or implies a condition that should hold at a particular program point — explicitly ("exactly one in-flight marker line ever", "the ledger is guaranteed to exist by now", "at this point X is always true") or implicitly (a flag read without re-checking, a module-level variable assumed initialized). You find a *reachable* path — a recovery resume, an early exit, an error handler, a loop-back, a mode-switch — where that condition is false when the skill relies on it.

*Scope:* Requires tracing across at least two state transitions or branches. Multi-step path required — a condition falsified in a single branch without path reasoning is out of scope.

*CONFIRM-IF:* You can name the invariant, name the falsifying path (branch sequence, recovery condition, mode), and quote the point where the skill relies on the now-false condition.

*REJECT-IF:* The path requires multiple simultaneous unlikely triggers with no plausible mechanism; a guard that fires before the relied-upon point correctly enforces the invariant (the guard is the fix, not the problem); a theoretical invariant with no documented reliance point.

*Worked example:*
```
ISSUE [invariant-violated-on-path]: The skill asserts "the session ledger is guaranteed to exist by the time any round opens", but on a diagnostic-mode entry (--diagnose flag) the pre-flight ledger-creation step is skipped, so a round dispatched in diagnostic mode reads a ledger that was never written.
File: my-skill/references/lens-invariants.md
Claim: my-skill/references/lens-invariants.md:17 "the ledger is guaranteed to exist by now"
Target: The diagnostic-mode entry path (--diagnose flag branches at pre-flight, skipping ledger initialization) reaches the round-open step with no ledger on disk. The round-open step reads the ledger unconditionally, so the relied-upon guarantee is false on this path.
```

---

**2. consumer-not-updated-for-producer-change**

*Trigger:* A producer (a step, script, or document section) changed what it *means* — not just what key it emits. The consumer references the correct new field name or data shape, so structural checks pass, but the consumer's logic misreads the *semantic meaning* of the producer's new behavior. Example: a producer now returns a list sorted descending where it previously returned ascending; the consumer reads `result[0]` still assuming it is the minimum. The consumer runs; the values it produces are wrong.

*Scope:* Semantic meaning change — the field name or data shape the consumer references is correct, but the consumer's logic misreads what the producer's output now means. A consumer that simply ignores a new field without misreading it is not in scope. A consumer that is aware of the change and handles it correctly is not in scope.

*CONFIRM-IF:* You can describe what the producer's behavior *meant* before and after the change, and show that the consumer's logic is only correct under the old meaning.

*REJECT-IF:* The consumer was structurally updated and the logic is correct under the new semantics; the consumer ignores the new output without producing wrong results.

*Worked example:*
```
ISSUE [consumer-not-updated-for-producer-change]: Step 4 was changed to emit flag-IDs sorted by most-recent-first, but Step 6's summary consumer reads flags[0] expecting the oldest unresolved flag (as Step 4 previously returned). Step 6 was not updated for the sort-order reversal.
File: my-skill/references/lens-cross-file.md
Claim: my-skill/references/lens-cross-file.md:24 Step 6: "take the first unresolved flag from Step 4's result as the priority flag"
Target: Step 4 now emits "sorted descending by timestamp". flags[0] is the newest flag, not the oldest. Step 6's logic is correct only under the previous ascending sort.
```

---

**3. counter-mis-step**

*Trigger:* A counter — round number, retry count, iteration index, attempt number, progress marker — is incremented, decremented, or reset at a state point that makes the count wrong relative to the logic that relies on it. Classic forms: incrementing *before* the attempt so the first attempt is already counted as attempt 1 when the limit check fires; resetting inside a nested loop when the reset should be per-outer-iteration; decrementing on success instead of failure; a counter whose reset is in a branch the loop does not take on the path that hits the limit check.

*Scope:* Requires reasoning about the state machine — which transition fires when, what value the counter holds at which state point. An off-by-one that is obviously intentional (e.g., `range(n)` with clear 0-based semantics) is not in scope.

*CONFIRM-IF:* You can walk the counter through a full state cycle and name the specific transition at which the count is wrong relative to the step that relies on it.

*REJECT-IF:* The index is 0-based where 1-based might be expected, but the downstream logic is written for 0-based and the behavior is correct.

*Worked example:*
```
ISSUE [counter-mis-step]: The round counter is incremented at the start of dispatch (before the agent call completes), so after a crash-and-resume the counter reads N+1 when only N rounds have closed, and the convergence-check compares against a count that is one ahead of the actual closed-round total.
File: my-skill/references/lens-state-machine.md
Claim: my-skill/references/lens-state-machine.md:31 "the convergence check fires when round_count equals target_rounds"
Target: round_count is incremented at dispatch-start, not at round-close. After one crash, a resume sees round_count=2 with only one closed round. The convergence check fires one round early.
```

---

**4. marker-lifecycle**

*Trigger:* A state marker — a file, a flag variable, a status field, an in-flight line, a semaphore — is written, cleared, or checked at a point in the lifecycle that breaks the state machine's guarantees. The skill asserts "exactly one in-flight marker line at every point" or similar. Find any path that orphans a marker (a crash before clear), strands a marker (transition to a new state without clearing the old), promotes or demotes a marker at the wrong step, or checks a marker before it has ever been written on first run.

*Scope:* Creation, promotion, deletion, and stranding defects. A marker that is simply never cleared (resource leak without incorrect behavior) is not in scope. A marker whose presence vs. absence is handled in all branches — even if complicated — is not in scope.

*CONFIRM-IF:* You can name the marker, name the path (crash point, error handler, early exit), and show that no recovery rule covers the resulting orphaned or stranded state, OR that the lifecycle check fires at a step where the marker is not yet written.

*REJECT-IF:* The recovery rules explicitly enumerate and handle the resulting state; the marker's absence on first run is guarded.

*Worked example:*
```
ISSUE [marker-lifecycle]: The in-flight marker is written to the ledger after the agent dispatch returns, but the skill also writes a "started" marker at dispatch-time. A crash between "started" write and "in-flight" write leaves the ledger with "started" but no in-flight marker; the recovery rules enumerate only "in-flight present" and "no marker" — the "started-only" state is unhandled.
File: my-skill/references/lens-state-machine.md
Claim: my-skill/references/lens-state-machine.md:38 "if a running marker is present, re-dispatch the job" / "if no marker is present, dispatch fresh"
Target: The "started" marker is a third state the recovery rules do not enumerate. The executor reaching this state has no rule to follow.
```

---

**5. non-terminating-loop**

*Trigger:* A loop whose exit condition some reachable path never satisfies — or a prose `.md` loop-back whose re-entry condition is never falsified, leaving the skill cycling indefinitely. Two forms:

**(a) State-machine cycle:** A state machine has no terminal state reachable from some starting configuration. The skill claims convergence ("loop until convergence", "repeat until all flags addressed") but a path exists where the convergence condition is never established: a flag that is never cleared, a condition that each pass re-sets, a branch the loop takes that bypasses the exit check.

**(b) Prose `.md` loop-back:** A written workflow step says "return to Step N" or "repeat from the top" under a condition that is never falsified once true — making the prose workflow non-terminating.

*Scope:* Both forms (a) and (b). The target is a loop — state-machine or prose — that path reasoning shows has an unreachable exit: a convergence condition never established, a re-entry condition never falsified, a branch that bypasses the exit check. Bounded loops with a documented maximum iteration count enforced on all branches are not in scope.

*CONFIRM-IF:* You can name the exit condition, name the path that never satisfies it, and show no safety bound (gate, stop, limit check) applies on that path.

*REJECT-IF:* The loop has a documented maximum iteration count enforced on all branches; non-termination requires a sequence of events with no plausible trigger in normal skill use.

*Worked example (state-machine cycle):*
```
ISSUE [non-terminating-loop]: The convergence loop exits when "all flag-IDs are in state resolved", but the re-dispatch branch on a partial result re-opens flags that were already resolved in the same pass, so the set of resolved flags can never reach "all" on a skill with interdependent flags.
File: my-skill/references/lens-state-machine.md
Claim: my-skill/references/lens-state-machine.md:45 "loop until all flags addressed"
Target: The re-dispatch branch (fired when any flag score < threshold) resets previously-resolved flags to "open". On a skill where flag scores are interdependent, re-dispatch always fires and always resets, so "all resolved" is unreachable.
```

*Worked example (prose loop-back):*
```
ISSUE [non-terminating-loop]: Step 8 says "if any issue remains unresolved, return to Step 3". Step 3 dispatches agents whose output feeds into the same resolution check. No maximum iteration count or stop condition is stated for this loop-back. A persistent unresolvable condition cycles the workflow indefinitely.
File: SKILL.md
Claim: SKILL.md:52 "Step 8: if any issue remains unresolved, return to Step 3"
Target: No bound on the number of return-to-Step-3 cycles exists. The resolution check re-runs agents whose output is determined by the same data condition — a persistent data condition that agents cannot change produces an infinite loop-back.
```

---

**6. idempotency-on-resume**

*Trigger:* The skill is designed to be resumable after interruption — a crash boundary exists (a marker, a checkpoint, a recovery rule). But a step that is correct on first execution produces a wrong or duplicate result when executed a second time on a partially-completed state, and the skill has no guard distinguishing "already done" from "not yet done" at that step. Requires tracing the resume path and comparing it to the fresh path.

*Scope:* Only applies where the skill has explicit resume / recovery semantics. A skill explicitly documented as non-resumable is out of scope. A skill where re-running from scratch (not resuming) is the intended recovery strategy and no resume logic exists is out of scope. Idempotency of individual side effects where the skill's overall outcome is still correct is not in scope.

*CONFIRM-IF:* You can name the crash boundary, name the step that re-runs on resume, and show what double-write, double-count, or re-applied effect the step produces when the prior partial run's output already exists.

*REJECT-IF:* The step checks for prior output before acting and correctly skips if already done; the skill documents that re-running the step from scratch is safe and describes the mechanism.

*Worked example:*
```
ISSUE [idempotency-on-resume]: A crash between writing the compiled output and recording the "done" marker leaves the skill with output on disk and a "running" marker. On resume, the recovery rule re-dispatches the compile step, which overwrites the already-correct output and increments the compile counter again — no guard checks for the prior output's existence before re-running.
File: my-skill/references/lens-state-machine.md
Claim: my-skill/references/lens-state-machine.md:59 "if a running marker is present, re-dispatch the job"
Target: The re-dispatch path does not check for existing output. The compile step writes its output unconditionally. A resume after the described crash double-compiles and double-counts.
```

---

**7. header-ledger-contract-drift**

*Scope:* A field's *meaning* or *accounting rule* diverges between where it is written and where it is read, without a corresponding update to the consumer's interpretation logic. The field name may be identical across both sites; the interpretations are incompatible.

*Trigger:* A ledger header field or row field is written by one step with one semantic meaning (e.g., "count of issues found in this round") and read by another step as if it means something different (e.g., "cumulative count of all issues across all rounds"). The field name may be identical; the interpretation diverges.

*CONFIRM-IF:* You can quote the writing step's description of the field's meaning and the reading step's description of how it uses the field, and show the two interpretations are incompatible.

*REJECT-IF:* The reading step's logic produces the correct result under either interpretation; the accounting-rule divergence is documented as intentional.

*Worked example:*
```
ISSUE [header-ledger-contract-drift]: The ledger's "issues_found" field is written by the dispatch step as "count of issues in this round only", but the compile step reads it as "total issues across all rounds" and sums it into the session total — producing a double-count on any multi-round run.
File: my-skill/references/lens-cross-file.md
Claim: my-skill/references/lens-cross-file.md:66 "issues_found: count of issues surfaced in this dispatch round"
Target: compile step: "session_total = sum(row['issues_found'] for row in ledger)" — treating each row's value as an independent addend when the value already reflects the round subtotal.
```

---

**8. positional-ref-not-stable-name**

*Trigger:* A cross-reference — to a step, section, phase, tier, round, check, or any other concept — identifies its target using a positional pointer (a line number, a bare `Step N`/`Section N`/`Tier N` with no descriptive name attached at the point of use) or a bare alphanumeric code (a cluster ID, flag code, or type-N label used as the persistent identifier) instead of a stable, descriptive name. The pointer resolves correctly today, but nothing re-derives or re-checks it when the target moves, gets renumbered, or is split/merged — the reference can silently drift to the wrong target, or to nothing, with no error.

*Scope:* Applies to any reference used to *identify* a concept for a reader or a consumer at another point in the skill — prose cross-references (e.g. a hypothetical `"see line 776"`, `"per Section 9"`, `"Tier 3b"`), enum/outcome/status values that are bare number-suffixed labels (e.g. hypothetical `type1`/`type2`/`type3`) reaching a consumer or a log/JSON field, and bare codes (e.g. hypothetical `C1`, `P26`, `G11`-style) used as the sole identifier where no descriptive alternative exists. These backtick-wrapped tokens in this Scope paragraph illustrate the pattern and do not point at any particular target (ids of the same form may still be real identifiers in the skill under review); do not flag this paragraph itself as an instance of the defect it defines. Does NOT apply to: ordinary numbered lists nothing else points back to by number; version numbers, byte counts, or other genuine quantities; a numbered heading that is *always* immediately paired with a descriptive title at every point of use, including at the cross-reference site itself (not just at the target).

*CONFIRM-IF:* You can quote the bare positional/coded reference, show it identifies a specific target elsewhere in the skill (a step, section, enum member, etc.), and show that reference is not paired with a descriptive name at the point of use — so a renumbering, reordering, or split of the target silently breaks or misdirects the reference with no check catching it.

*REJECT-IF:* The reference is paired with a descriptive name at the point of use (e.g. "Tier 3b (batch-reconciliation)"), even if a bare number also appears elsewhere; the number is a genuine quantity, not an identifier; the same numbered heading is used consistently as a stable anchor that nothing else can silently desynchronize from (e.g. a markdown heading found by exact-text search, not position).

*Worked example:*
```
ISSUE [positional-ref-not-stable-name]: The scoring module's docstring identifies the confidence-normalization rule only as "(Section 9)" at six separate call sites, with no descriptive name given at any of those sites — only the file's own top-of-module docstring glosses what Section 9 is. If the build brief this cross-references is ever renumbered, split, or the module docstring is trimmed, every one of these six bare "(Section 9)" references silently points to the wrong rule (or nothing) with no check catching the drift.
File: my-skill/scripts/classify_propose.py
Claim: my-skill/scripts/classify_propose.py:73 "(Section 9)" used bare at six call sites (score_slot, score_traversal, _effective_score_thresholds x3, the stage-set comment)
Target: No descriptive name is restated at any of the six use sites; only the module docstring (which could itself be edited or trimmed independently) supplies the meaning. A renumbering of the external build brief desynchronizes all six references silently.
```

---

**9. hardcoded-value-should-be-config**

*Trigger:* A literal value (a number, path, or string) is hardcoded directly into logic where the skill's own design already exposes — or clearly should expose — that same value as a user-configurable setting. The hardcoded copy and the config mechanism diverge silently: a user who changes the config value never actually changes the behavior, because the code path in question never reads it.

*Scope:* Applies when the skill has an established config-reading pattern (a dial, a settings file, an env var, a `config.json` key) for values of that same kind, and a specific instance bypasses it with a literal instead. Also applies when the skill's own documentation claims a value is configurable but a call site hardcodes it anyway — a doc↔code contract gap on the configurability claim itself. Does NOT apply to: genuine constants with no user-facing configurability claim anywhere (a fixed retry-count of 1 for a truly one-shot operation, a protocol-mandated magic number); a hardcoded value that is itself the documented default AND is read through the config mechanism when the user overrides it (defaults are not violations — silently bypassing the override path is).

*CONFIRM-IF:* You can name the config mechanism the skill already uses for values of this kind (or the documentation's explicit configurability claim), quote the hardcoded literal at its call site, and show that changing the config value would have no effect on that call site's behavior.

*REJECT-IF:* The literal is read from config at that call site (correctly implemented, not a violation); the value has no documented or implied configurability claim anywhere in the skill; the hardcoded value is the fallback used only when config is absent, and the config-present path correctly overrides it.

*Worked example:*
```
ISSUE [hardcoded-value-should-be-config]: The dispatch-prompt template hardcodes a literal batch size of 25 files ("dispatch up to 25 files per batch"), but the skill's config.json already exposes a `classify_batch_size` dial that every OTHER batch-size read in the codebase uses. A user who sets `classify_batch_size: 100` in config.json sees no change in the dispatched batch size at this call site — the config write is silently inert here.
File: my-skill/references/classify-prompt.md
Claim: my-skill/references/classify-prompt.md:10 config.json's `classify_batch_size` dial (documented elsewhere as the authoritative batch-size setting)
Target: The dispatch template's own comment hardcodes "25" instead of interpolating the `classify_batch_size` value read at dispatch time — the config mechanism exists and is used everywhere else, just not here.
```

---

**10. module-boundary-violated**

*Trigger:* The skill's own design assigns a module, script, or step a specific architectural role that excludes a category of operation — stated in a docstring, header comment, README, or architecture doc (e.g. "this module is a pure Python classifier — it must never call an LLM directly", "the ledger writer must never itself dispatch agents") — but the code inside that same module performs the excluded operation directly instead of delegating it to the module/step whose role is to do so.

*Scope:* Applies when the skill documents a role boundary for a specific module/script/step, and that module's own code crosses the boundary. Does NOT apply to: a module with no stated role boundary anywhere (nothing to violate); a module that correctly delegates the excluded operation to its designated collaborator (it invokes a sibling module/script that performs the operation, rather than performing it inline); a boundary crossing that is itself documented as an explicit, scoped exception in the same doc.

*CONFIRM-IF:* You can quote the stated role boundary (the docstring, header, or architecture text naming what this module must/must not do) and quote the call site inside that same module performing the excluded operation directly rather than delegating it to another module/step.

*REJECT-IF:* No role boundary is stated anywhere for this module; the excluded operation is delegated to a separate module/script whose role is to perform it (the boundary-holder only invokes the collaborator, it doesn't perform the operation itself); the boundary crossing is documented as an explicit, scoped exception.

*Worked example:*
```
ISSUE [module-boundary-violated]: classify_propose.py's own module docstring states "pure Python classifier — never calls an LLM directly", but the `propose_fix` function in the same file calls the LLM API directly to draft a fix suggestion, crossing the boundary the module's own docstring establishes.
File: my-skill/scripts/classify_propose.py
Claim: my-skill/scripts/classify_propose.py:17 Module docstring: "classify_propose.py: pure Python classifier — never calls an LLM directly"
Target: `propose_fix()` (same file) calls `anthropic.Client().messages.create(...)` directly instead of delegating fix-drafting to a separate LLM-calling step; the classifier module performs the excluded operation itself.
```
