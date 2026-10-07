# How to Fix — Fix-Executor Doctrine

Contents: context · FIX vs STRENGTHEN · considered-fix and pauses · no-orphan-flag · fix depth · frozen interface · batch edits · fix-impact closure · closure block · naming · fix comments · root not symptom · fix everything · address formats · regression vs cascade · escalation ladder · verifying STRENGTHEN · decision tree.

This guide tells a fix-executor agent exactly how to decide and apply every fix or strengthen for a confirmed defect. Read it before touching any file.

---

## Context: findings here are already confirmed

In the cascade workflow the findings you receive are **confirmed defects** (Prepass detector findings or adjudicated Code Review findings). That means:

- You may **never reject or withdraw** a finding.
- You may **never emit USER-PAUSE** — that is the orchestrator's last-resort tool only (used when even the orchestrator cannot resolve intent from the skill files + README Intent + work items). You are not the orchestrator.
- If you cannot determine the correct intent-preserving fix from the work items, the blast set, the README `## Intent`, and the skill files, **emit `ORCHESTRATOR-PAUSE` with a precise question** and escalate up to the orchestrator. Do not guess. Do not proceed with an ambiguous fix.

---

## Decide: FIX vs STRENGTHEN

**FIX is the default.** STRENGTHEN is the narrow exception.

### Choose FIX when:

The artifact has a defect — wrong value, broken cross-reference, two artifacts disagreeing on a shared convention, missing case in a script that the documented contract already requires, undocumented behaviour that does not match documented intent. (A missing case that would add a retry, cap, branch or exit path the contract does not document is new behaviour: ORCHESTRATOR-PAUSE, see "Frozen interface" below. A FIX that adds a raise, return or branch node, even one the contract requires or one that fixes a real behaviour bug, is also reported by the post-fix gate as `new-behaviour` and becomes an ORCHESTRATOR-PAUSE that the orchestrator resolves at the check-pauses step, SKILL.md "Post-fix gate".) The correct address is to change the underlying artifact so the issue no longer exists. Adding language that says "this defect is intentional" is not a fix; aligning the artifact is.

### Choose STRENGTHEN when (four exhaustive cases):

1. **Missing WHY for a deliberate design choice.** The artifact is correct; what is missing is the reasoning text. Add the WHY at the point of use. Never delete the rule to silence the flag.
2. **A list with no closure marker.** The list omits whether it is exhaustive. Add an explicit closure marker ("these four are exhaustive" / "examples only — others valid").
3. **Cross-reference variable used at a distance** from its introduction where renaming would be disruptive. Add the "see preceding line" pointer.
4. **Unreachable-looking branch that is a real edge case** (verified, not assumed). Add the note naming the specific condition that triggers it.

**Special case: clusters that leak hidden information.** When the cluster's `check` names `hidden-info-leak-in-dispatch` or `hidden-leak-at-use` (information that should remain internal is present in the assembled prompt or a sub-agent brief), the default address is **FIX-by-removal** — remove the leaked information from the relevant document. STRENGTHEN applies only when the underlying design has shifted and the WHY of that shift is absent; it does not apply merely because the leaked information happens to be present.

Before choosing STRENGTHEN, apply this two-step test:

1. Can the underlying artifact be changed so the issue disappears? If yes → FIX.
2. If the artifact is genuinely correct, is the root cause "trace agent did not see the intent"? AND would the added text actually prevent a future cold agent from re-flagging? Only if both are yes → STRENGTHEN.

**Anti-patterns — these are forbidden:**

- STRENGTHEN to document drift between two artifacts. Align them (FIX-by-alignment), do not annotate the disagreement.
- STRENGTHEN to paper over a script bug. Fix the script (or the doc, whichever is wrong).

Any address that claims "this defect is intentional" without one of the four legitimate cases holding is the wrong behavior this section warns against — it is not a named anti-pattern in its own right.

---

## The considered-fix constraint and ORCHESTRATOR-PAUSE criteria

Before applying any FIX, check it against the target skill's documented intent (the README `## Intent` section; the SKILL.md frontmatter `description:` only when the target has no README.md).

**Would this fix trade away something the skill explicitly optimises for?** If yes → `ORCHESTRATOR-PAUSE` with the conflict stated precisely. Do not apply a "make the tracer happy" edit that degrades the skill's design.

If intent is null (a README.md with no `## Intent` section, or no README.md and no `description:`), say so in your ORCHESTRATOR-PAUSE and escalate — do not guess at intent.

**Three independent ORCHESTRATOR-PAUSE criteria** — any one of these alone is sufficient to escalate:

1. **Two plausible FIX paths exist and documented intent does not select between them.** State both candidates in the pause question.
2. **Cluster tagged `internal-contradiction` AND both sides carry load-bearing roles** (each is referenced elsewhere in the skill, or has documented consumers). Choosing which side to align without human judgement risks removing a load-bearing contract.
3. **A FIX would require modifying a script whose downstream consumers the orchestrator cannot enumerate from the materials.** When the blast radius is unknowable, escalate rather than guess.

**ORCHESTRATOR-PAUSE is decision-based only — never a fix-failure fallback.** If a FIX attempt did not stick (regression), the fix-executor owns the re-fix — that is an execution problem, not a reason to escalate. Do not auto-escalate to ORCHESTRATOR-PAUSE because fixes are failing. The one precedence exception is the post-fix gate (SKILL.md "Post-fix gate"): when the orchestrator, after its 2 inner passes or at once for a `new-behaviour` problem, asks you to re-emit a decision as `ORCHESTRATOR-PAUSE (post-fix gate: ...)`, that gate outcome overrides this rule; re-emit it as asked.

**Promotion rule (orchestrator layer).** The orchestrator RESOLVES an ORCHESTRATOR-PAUSE by default — deciding the intent-preserving fix from the target's README `## Intent` / the skill's own rationale. It PROMOTES the pause to USER-PAUSE ONLY when genuine user attention is truly needed (the intent is not derivable from the README or skill). Promoting to avoid making a derivable call is the lazy-pause anti-pattern and is forbidden. The one standing exception is a prepass `auto_pause` entry with `resolutions` of 1 or more (the finding came back after a resolved pause): that is a USER-PAUSE whether or not the intent is derivable, which bounds the prepass loop (SKILL.md prepass result handling).

---

## No-orphan-flag

Every finding must be addressed by FIX, STRENGTHEN, or (when you must escalate) ORCHESTRATOR-PAUSE. The address must land **inside the skill**, not in an external log.

If a finding reappears in a later cold round, the prior address was incomplete. The correct response is to investigate and strengthen further — never re-log, never escalate to dodge the work.

There is no DISMISS branch.

---

## Fix depth — deepest root fix that does not widen the interface

This is the single rule for how big a fix is (skill-tracer's SKILL.md restates it for the orchestrator as "Fix depth"). It resolves the old tension between "smallest change" and "deepest fix" in favour of depth, bounded by the interface:

- *Deepest:* fix the mechanism, not the symptom ("Fix at the root — not the symptom" below): refactor over band-aid, generalise over special-case, and fix every finding regardless of "minor". Do not prefer a smaller patch that leaves the root unfixed. This holds on every round, including the last budgeted one.
- *Does not widen the interface:* the fix adds no CLI flag, mode, subcommand, file, ledger field, run-options key, row kind, shared helper module, doc section, or any other new interface element such as an output JSON field, status value or exit code (moving duplicated logic into an existing shared module is fine; it adds no interface). The interface is frozen from round 1 of a run (see "Frozen interface" below).
- *Smaller when the behaviour is right:* when the behaviour is already correct and only a comment or doc is wrong, fix the comment or doc, not the code.
- *No new behaviour:* a fix makes the doc match the code, or the code match its documented contract; adding a retry, cap, branch or exit path, or removing a fallback, is an ORCHESTRATOR-PAUSE (see "Frozen interface" below).
- *Minimum sprawl:* do not rewrite text the fix does not need. A whole-section rewrite turns a one-cluster round into a multi-cluster round. Re-read the surrounding paragraph after the edit.

Intent-preservation (the considered-fix constraint above) still governs.

---

## Frozen interface

From round 1 of a run, a fixer may **not** add a CLI flag, mode, subcommand, file, ledger field, run-options key, row kind, shared helper module, doc section, or any other new interface element such as an output JSON field, status value or exit code. When the deepest root fix would need one, apply no edit for that cluster and emit `ORCHESTRATOR-PAUSE` naming the addition and the best non-widening alternative; the orchestrator decides (and promotes to USER-PAUSE only if intent cannot be derived). The one exception is a real behaviour bug (wrong output, wrong exit code, a crash) that cannot be fixed any other way: then make the smallest such addition and say in the FIX address why no non-widening fix exists. When the behaviour is already correct and only a comment or doc is wrong, fix the comment or doc, not the code. A fixer adds no new behaviour: a fix makes the doc match the code, or the code match its documented contract. Adding a retry, cap, branch or exit path, or removing a fallback, is new behaviour: apply no edit for that cluster and emit ORCHESTRATOR-PAUSE naming it. `assemble_fix_prompt.py` fills the fixer prompt's `[INTERFACE_RULE]` slot with this rule for the round.

*Versioned keys and formats.* In any round, a change to a persisted key or format (a ledger column, a run-options key, the in-flight marker, a JSON field another script reads) must be versioned and migrated: the reader keeps accepting the old form and converts it, and the doc that describes the format names both forms. A rename without a migration breaks every ledger written before it.

*Why:* in the October 2026 self-run, round 1 added a subcommand and sidecar files, and 31% of rounds 4-8's flags were about machinery that earlier rounds' fixes had added. In the later trim comparison the freeze started at round 3, and round 1's fixer, with the interface still open, added a shared helper, a token field and a row kind; about three of round 2's flags were about them. Freezing the interface from round 1 stops a run from seeding its own findings. In the trim-plus comparison both seeded round-2 findings were behaviour a fixer had added, not interface; hence the no-new-behaviour rule.

---

## Batch edits to the same document

When several clusters resolve in the same file, apply their fixes as one coordinated edit pass — not one cluster at a time with a re-read between each. Group clusters by target file; for each file, plan all edits together, then apply them in one pass. This prevents stale-anchor errors where a second edit works from a line-count invalidated by the first.

**Mandatory ordering with fix-impact closure (see "Fix-impact closure — cover the full blast radius" below):** Run fix-impact closure enumeration for **all** the round's FIXes **first** — it may add files to the edit set. Only after the full edit set is known should you apply batch edits to each file in one coordinated pass per file. Do not apply file edits before closure enumeration is complete.

---

## Fix-impact closure — cover the full blast radius

After deciding FIX, and **before** emitting the decision, enumerate the blast radius and apply the fix to every site the same change requires, in the same round.

**The four blast categories** (defined together as "blast category" in `references/glossary.md`):

1. *Shared convention / value / format.* If the fix changed a status string, format string, value, schema, exit-code meaning, or filename convention, grep the whole skill for every other site that produces or reads it and align all of them.
2. *Producer ↔ consumer.* If the fix changed what a step/script produces, fix every documented consumer. If it changed a consumer's expectation, confirm the producer still satisfies it.
3. *Parallel call sites.* If the fix corrected one instance of a repeated instruction or pattern, fix all sibling instances carrying the same defect.
4. *Cross-reference pointers.* If the fix moved, renamed, or deleted a step, section, file, or variable, update every `see Step N` / `references/<name>.md` / variable pointer to it.

**Mechanical enforcement — required:**

For every FIX that changed a shared token (renamed step number, flag prefix, status string, value, format, filename, variable, function or other defined name, cross-reference), run:

```bash
python3 ~/.claude/skills/skill-tracer/scripts/check_fix_radius.py \
  --skill-root <skill-root> --token "<the shared token>" \
  --touched "<comma-separated files this FIX edited>"
```

- For a **rename old→new**, pass the **old** token — surviving occurrences in un-touched files are stragglers.
- For a **value/format/contract change**, pass the shared string and confirm every site is in the edit set.

Do **not** emit the cluster's FIX decision until the check exits 0 (the ledger row itself is written later by `ledger_cascade.py --mode fill-address` from that decision; a fixer never edits the ledger). On exit 1: fix the named uncovered sites and re-run. If an in-scope site legitimately keeps the token (e.g. a deliberate quotation of the old value in a WHY comment), add it to `--allow` and state the reason in the FIX address (`README.md`, `HISTORY.md` and `LICENSE` are outside the check's scope and never need `--allow`): pass `--allow <files>` to `check_fix_radius.py` yourself, and name those files and the reason in your decision's address; the orchestrator then passes the same `--allow <files>` to `ledger_cascade.py --mode fill-address`, whose mechanical re-check uses exactly the files it is given.

**Where this is enforced, and where it is not.** For a TOKEN-BLAST cluster (Prepass clusters whose detector names a shared token), `ledger_cascade.py --mode fill-address` re-runs this exact check itself (via `fix_blast.run_check_fix_radius_all`, once per token of the cluster) against your decision's `touched_files` plus the cluster's own definition file, which the blast computation already counted as touched (`auto_touched` in the blast entry) — it does not trust that you ran it. It refuses to write any row (every decision of the call rejected) if `--skill-root`/`--blast-json` are missing or if any TOKEN-BLAST FIX still has uncovered sites. Code Review clusters are always LOCAL with no token (a reviewer's finding is prose, so no token is known before the fix), so for a Code Review FIX that changes a shared token the closure check rests on your own `check_fix_radius.py` run; the post-fix gate adds a `stale-sibling` check for a removed file, flag or defined name (`post_fix_gate.py` `stale_siblings`), but not for a changed value or format, whose only later backstop is the next round's cold sweep. Running the check yourself is therefore required on every tier — on TOKEN-BLAST clusters the mechanical re-check is a backstop, not a substitute.

---

## Closure block

Every FIX decision carries a `closure` field: a list of four one-line strings with these labels, each with a non-empty value. `scripts/check_decisions.py` exits 1 naming the cluster when a label is absent or empty, and the orchestrator sends the decision back for re-emit.

- `Siblings:` every other site that names the same claim, term, flag or step, found by grepping it, as `file:line updated` or `file:line unchanged`. A new or changed rule must agree with each sibling rule on the same subject (a fresh-run test with the resume rule; a test with every trigger that must meet it); a script and the doc that describes it are siblings. When the grep finds none, write `none found (grep <term>)`.
- `Bound:` for each loop, fallback, retry, error path or definition the fix adds or changes: its limit or exit, its edge case, and the existing command or option a reader uses to act on it. An error text that says "supply --x" names a flag that the script printing it registers. When the fix writes or rewrites the remedy for an exit code or error, grep the script for every cause that produces it, list each cause, and give each a remedy (one shared remedy is fine if it truly applies to all); a remedy written for one cause must not stand as the remedy for the whole code. The causes must be disjoint: name the observable that tells two causes apart, or merge them under one remedy, so no two sentences give different remedies for the same event. Write `none added` when the fix adds none. A generated table (the gate's exit-2 table between `<!-- gate-exit2:begin -->` and `<!-- gate-exit2:end -->`) is never edited by hand: change the source table (`EXIT2` in `scripts/post_fix_gate.py`) and run `post_fix_gate.py causes --write <file>` on each doc that carries it; a test fails when a copy differs.
- `Claims:` each factual sentence the fix wrote (an exit code, a printed line, a field, a count), each followed by the `file:line` that proves it. Delete a sentence you cannot point at. When a new sentence tells the executor to use an artefact, file, snapshot, archive or step, also name, in the same `Claims:` line, the step that creates it on every path the sentence covers (prepass and code-review; first and later fixer batches); where a path lacks it, narrow the sentence to the paths that have it.
- `Blocks:` each paragraph, table or comment run the fix rewrote, as `file:start-end` on the file as it stands after your last edit, after re-reading the whole block (not only the lines you changed) against the code and its sibling sites: every claim in it still holds, and each cause or case it lists has one remedy. `post_fix_gate.py check` names each such block (a doc block of 3 or more lines in which at least 2 lines and 30% changed) as a `block-reread` problem until a `Blocks:` line of a decision in `--fixer-transcript` overlaps it, and also lints and name-checks the block's untouched lines. Write `none rewritten` when the fix rewrote no block.
- A fix never adds a recovery, restore, fallback or retake procedure the doc did not already define for that path: that is new behaviour (SKILL.md "Fix depth"). Remove or narrow the unsafe advice instead, or emit ORCHESTRATOR-PAUSE naming the procedure.

When `post_fix_gate.py check` lists sibling lines (its `siblings` list) for lines you touched, the orchestrator may send them back; confirm or update each and re-emit the Closure block.

Why: in the v3 cascade analysis, 7 of 52 round-2 flags came from round-1 fixes: an added fallback, error path or retry with no bound or usable remedy (3), a new rule not reconciled with its sibling (2), an inaccurate added claim (1), and one site fixed with its sibling left stale (1). In the v3 self-run, a round-2 fix added a restore step that cited an archive existing on only one path (cascade, caught in round 3), which is why `Claims:` now names the creating step per path and a fix adds no new recovery procedure. A round-3 rewrite of an exit-2 remedy covered only the missing-snapshot cause and left the lint-failure cause with none (cascade, caught in round 4), which is why `Bound:` now lists every cause of the code. The round-4 rewrite listed overlapping causes (a wrong `--snapshot` path and a missing snapshot file are the same event) with two different remedies (cascade, caught in round 5), which is why the causes must be disjoint. Rounds 1 to 5 of the v3 self-run rewrote that one paragraph five times and it cascaded three times; v3.6 therefore moves the causes and remedies into the generated table and gates a rewritten block as a whole (`Blocks:`).

---

## Naming discipline when a fix introduces a new stable name

Some fixes — most commonly the integrity lens's `positional-ref-not-stable-name` finding —
require replacing a bare positional pointer (a line number, `Step N`, `(Section 9)`, a
hypothetical bare code like `C1`/`P26`) with a stable, descriptive name restated at every
use site. (These backtick-wrapped tokens illustrate the pattern; in this sentence they do not
point at any particular step, section, cluster or flag, even though ids of the same form, such as
cluster ids `C<n>` and flag ids, are real identifiers in a ledger.) Choosing and documenting that name
is part of the fix, not a stylistic afterthought — a fix that skips any of the four rules
below is incomplete (the four rules are defined together as "Naming discipline" in
`references/glossary.md`):

1. *No collision with ordinary prose.* The chosen name must not double as a common word
   or phrase that will keep occurring elsewhere in the skill with its ordinary meaning — in
   prose, in code, in a WHY comment, anywhere. If it does, every later occurrence of that
   ordinary phrase becomes ambiguous with the newly-named concept: a reader (or another cold
   agent) cannot tell whether a given occurrence means the concept or is just ordinary
   language. For example, naming a concept `for_example` would collide with the literal
   phrase "for example" wherever it appears afterward, including in unrelated sentences —
   that collision makes the name unusable however fitting it seemed in isolation. If the
   first name considered isn't distinctive enough to avoid this, assign a different one.

2. *Compositional honesty.* If the new name is built by extending or combining an EXISTING
   name already used in the skill (for example, prefixing an existing name with "use"), the
   new name's actual referent must genuinely be about that composition — the composed name
   must actually mean "using" the existing concept, not something unrelated that merely
   borrows its words. Do not construct a composed name whose real meaning drifts from what its
   components imply.

3. *Mandatory, standalone glossary entry.* Every newly introduced stable name must be
   added to `references/glossary.md` (matching its existing `| **Term** | Definition |`
   table format) with a definition that stands entirely on its own. A reader must be able to
   understand the concept from the glossary entry alone, without already knowing some other
   process it's embedded in. A definition of the form "step 6 of classifying prompt, which
   does X" is NOT acceptable — it is not self-contained; the reader still has to go find and
   understand "classifying prompt" and its step 6 to make sense of the entry. Write the
   definition as if the glossary is the only place the reader will ever see it.

4. **Check for an existing near-synonym before adding a new entry.** Before writing a new
   glossary row, scan `references/glossary.md` for an entry that already covers the same
   concept under a different exact spelling (e.g. a hypothetical case where the skill's own
   prose bolds a bullet as "**Cold-read.**" while the glossary defines "cold-read invariant" —
   same concept, two spellings, not two concepts — this exact drift was found and fixed in this
   skill's own glossary earlier, by aligning the entry to the bare form actually used live).
   This differs from rule 2's compositional case: rule 2 is
   about a name that genuinely means something DIFFERENT from the name it extends (e.g.
   `use_classify_prompt` is a distinct concept from `classify_prompt`); this rule is about the
   SAME concept accidentally referred to two ways. If you find a near-synonym covering the
   same concept, do not add a redundant second entry — fix the naming inconsistency at the
   root (align the skill's own bolded label or in-text usage to the glossary's existing term,
   or vice versa if the skill's spelling is the more established one), per "Fix at the
   root — not the symptom." A redundant entry papers over the drift instead of fixing it.

---

## Fix comments document behavior, not the fix event

A FIX's job is to make the artifact correct. Any comment a FIX adds or edits must describe what the code does or why — durably, for whoever reads it next — never that a fixer touched this line.

**Forbidden pattern:** `# C3 fix: added dest_set membership check.` — this states an action the fixer took, not a fact about the code. It gives a future reader zero information: it doesn't say what the check prevents, why it's needed, or what breaks without it.

**Required pattern:** if the surrounding comment doesn't already carry the WHY, add the WHY in present tense, describing the code's behavior/invariant — not the edit event. (Often the WHY is already stated in the lines just above; in that case the fix comment is pure noise and should be deleted outright, not merely reworded.)

**Test before writing any fix comment:** would this sentence make sense to someone who has never seen the ledger, doesn't know a fix ID like "C3" exists, and is reading this code cold long after the fix? If its only content is "a fix was applied here," delete it.

**Where the provenance belongs:** the ledger row this FIX already writes (see "Recording propagated sites" below, in this section) is the durable record that a fix happened, by what cluster, when, and why. An inline comment announcing the same thing is a duplicate changelog living in the wrong place — it clutters the code and helps no one reading it.

**Recording propagated sites.** Propagated sites are part of the same FIX — never separately flagged. Name every file touched in the FIX address, e.g.: `FIX (foo.py + SKILL.md's relevant section + references/<ref>.md: rename status 'compiled'→'built' at producer + all 3 readers)`.

Exception: if a closure-reached site needs a genuinely different fix (not the same change), treat it as its own cluster in the current round — fix it now, do not defer.

---

## Fix at the root — not the symptom

Fix the underlying mechanism so a future executor or maintainer cannot repeat the same mistake.

- Two artifacts drifted because one re-implements logic the other owns → make it **import/reference the single source of truth** (removes the whole drift class), not just re-sync the copies.
- A contract is documented but unenforced → add **enforcement at the mechanism** (the validator, the parser), not just correct the one bad value.
- A cross-reference broke because a step/section/file moved → fix it so the pointer **resolves structurally**, and update every other pointer to it (compose with fix-impact closure).
- A wrong-altitude special case was bolted onto shared machinery → **generalise the underlying mechanism** so the special case is subsumed.

Root-cause depth is chosen over symptom-shallowness. The minimum-sprawl and frozen-interface limits ("Fix depth" above) still govern how the chosen root fix is applied; neither is an excuse to prefer a shallower patch.

---

## Fix everything — no volume cap, no "just cleanup" skip

Every finding from every source (Prepass detectors and Code Review reviewers) must be addressed. There is no volume limit.

At the skill altitude, a review-lens finding labelled "reuse", "efficiency", or "simplification" **is** correctness: dead code misleads a reader, duplication drifts between producer and consumer, wrong-altitude detail creates executor ambiguity. Fix all of them.

The only legitimate "out of scope" call is a **pure size/polish reduction** — shorter prose, fewer words, with no change to what the workflow does or how unambiguously it reads. That belongs to skill-publisher's `/simplify`, not here. "Too many" and "too minor" are never valid reasons to skip.

---

## Address column formats (required for the ledger row)

**FIX:**
```
FIX (<file>: <one-line summary of change>)
```
Name the file changed and summarise the edit in one line. If the fix spans multiple files, name all of them: `FIX (foo.py + SKILL.md's relevant section + references/<ref>.md: …)`.

**STRENGTHEN:**
```
STRENGTHEN (added at <file>:<line-range>: "<quoted first 80 chars>")
```
Name the file, exact line range where the new text landed, and the first 80 characters of the added text. Approximate anchors (`~line N`) are not acceptable — re-read the file after the edit to capture the exact range.

**ORCHESTRATOR-PAUSE (cascade adaptation — replaces USER-PAUSE in the fix executor's hands):**
```
ORCHESTRATOR-PAUSE (<one-line question with both candidate fixes named>)
```
The bare question is also accepted: `ledger_cascade.py` wraps it as `ORCHESTRATOR-PAUSE (<question>)`, and `templates/considered-fix.md` and `assemble_fix_prompt.py` allow either form. State the question and the two or three plausible fix paths so the orchestrator can answer without requesting further context.

---

## Regression vs cascade — how to read a reappearing root cause

- **Regression** — a later round's cluster has the same root cause as one already addressed. The prior address was incomplete. Investigate and strengthen further, and name the regression and the failure mode of the prior address in the new FIX address, using the exact phrase `regression of round <N> <C-id>` for the prior cluster (e.g. `FIX (<file>: regression of round 2 C4 — the prior fix patched one call site; ...)`): `scripts/render_ledger.py` highlights a regression row by that phrase in the Address column. The Root cause cell is script-generated, and the ledger repeat-count guard parses it, so a fixer never edits or prefixes it.
- **Discovery cascade (expected)** — later clusters are genuinely independent latent defects a prior fix exposed. Raw flag count may stay flat or tick up. This is healthy.
- **Propagation cascade (avoidable)** — a later cluster is the same change as a prior FIX left unpropagated. Fix-impact closure ("Fix-impact closure — cover the full blast radius" above) should have caught it in the earlier round. When you spot one, note it and tighten the closure pass.

The convergence metric is: *no prior-round root cause reappears in a later round*. Raw count is secondary.

---

## Escalation ladder for repeat-confirmed findings

A finding confirmed again after a fix was already applied to it (`repeat_count >= 1`, per the
repeat-count annotation `prepass_run.py` puts on each Prepass cluster) is a signal that the **prior address was too weak for this
defect** — not a cue to reapply the same kind of address again. Re-emitting the same guidance
verbatim is how a round spins without converging. Before choosing the next address:

1. **Diagnose WHY the prior address was too weak — first, explicitly.** Read the prior ledger
   row's Address for this signature and identify the specific failure mode:
   - It patched the symptom at one site while the mechanism that produces the defect stayed
     unchanged (the defect class survives).
   - It added a WHY-comment (STRENGTHEN) at a spot a cold reader still will not see or connect to
     the flagged behaviour.
   - It patched only one of several call sites carrying the same pattern (incomplete fix-impact
     closure).
   Name the specific failure mode in the new decision's address (see
   "Regression vs cascade" above) — "strengthen more" or "try again" is not a diagnosis and is not
   acceptable as the stated reason.

2. **Move up the ladder — never re-apply the rung that already failed.** Three rungs, weakest
   to strongest (named "rungs", not "tiers", because "tier" already means a cascade stage):

   - *Rung 1 — comment-only / STRENGTHEN.* Adds a WHY note or closure marker at the existing
     site; changes no behaviour. Weakest rung: it relies on a future reader actually finding and
     reading the added text. Legitimate only the first time a genuine STRENGTHEN case (the four
     cases above) is confirmed correct but under-explained.
   - *Rung 2 — local patch.* Fixes the specific site the finding names — the one bad value, the
     one missing check, the one out-of-sync line — without touching the surrounding mechanism.
     Appropriate when the defect really is local and rung 1 was either skipped or already tried
     and insufficient.
   - *Rung 3 — structural extraction.* Removes the whole defect class by changing the mechanism
     itself: extract duplicated logic into a single source of truth, add enforcement at the
     validator/parser instead of the one call site, generalise a bolted-on special case into the
     shared machinery (see "Fix at the root — not the symptom" above). Strongest rung: a future
     variant of the same mistake becomes structurally impossible, not merely individually caught.

   If a signature reappears after a rung 1 address, escalate to rung 2. If it reappears after
   rung 2, escalate to rung 3. Do not retry a rung that has already failed on this signature —
   the repeat-count auto-pause of `prepass_run.py` (triggered on the 2nd reappearance) exists precisely
   to stop that spin; by the time you are addressing a `repeat_count >= 1` cluster, you are already
   committed to moving up a rung, not sideways to a same-rung variant.

   A repeat-confirmed finding never makes ORCHESTRATOR-PAUSE a fallback: the pause stays
   decision-based ("The considered-fix constraint and ORCHESTRATOR-PAUSE criteria" above), so when
   the next rung is correct you apply it; you pause only when a pause condition holds: the considered-fix conflict, one of the three criteria, a frozen-interface addition or new behaviour ("Frozen interface" above), or the post-fix gate's re-emit request ("The considered-fix constraint and ORCHESTRATOR-PAUSE criteria" above).

   Rung selection composes with, and does not replace, the FIX-vs-STRENGTHEN decision and the
   ORCHESTRATOR-PAUSE criteria above — a rung 3 structural extraction is still a FIX, addressed and
   ledgered exactly as any other FIX (including fix-impact closure).

---

## Verifying STRENGTHEN landed

After applying a STRENGTHEN, re-read the named file at the named line range and confirm the quoted first-80-chars text is present. If a subsequent FIX in the same round overwrote it, re-apply the STRENGTHEN to a stable location (one not touched by remaining clusters), then put the corrected anchor in the Address of your decision JSON. The ledger lives outside the target and is written only by `ledger_cascade.py --mode fill-address` from that decision, so a fixer never edits it; if a row was already filled with a stale anchor, the orchestrator replaces only that substring of the Address cell in the ledger, leaving the rest of the pipe-delimited line byte-for-byte intact.

---

## Quick-reference decision tree

```
Confirmed finding received
        │
        ▼
Can the underlying artifact be changed to remove the issue?
  YES → FIX
        │
        ├─ Check considered-fix: does this trade away documented intent?
        │     YES → ORCHESTRATOR-PAUSE (escalate with precise question)
        │     NO  → apply FIX
        │             │
        │             ├─ Run fix-impact closure ("Fix-impact closure — cover the full blast radius"); run check_fix_radius.py if shared token changed
        │             ├─ Fix at the root ("Fix at the root — not the symptom"), not the symptom
        │             └─ Emit the decision only after radius check exits 0
        │
  NO → Does this fit one of the four legitimate STRENGTHEN cases?
        YES → STRENGTHEN (add WHY / closure / pointer / edge-case note inside the skill)
              │
              └─ Never delete the rule to silence the flag
        NO  → FIX (default — there is no DISMISS branch)
```

---

*Provenance: every rule in this guide is drawn from skill-tracer's own SKILL.md (the four invariants — specifically "No-orphan-flag" — and the "Convergence" step) and consolidates the fix-decision doctrine formerly carried in a separate address-decision reference — bias-toward-FIX, fix everything, anti-patterns, the four legitimate STRENGTHEN cases, the three address formats, PAUSE criteria, fix depth, the frozen interface, batch edits, fix-impact closure, fix at the root, and verifying STRENGTHEN landed are now all sections of this document. The cascade-escalation adaptation (ORCHESTRATOR-PAUSE replacing USER-PAUSE in the fix executor's hands; prohibition on fix-executor USER-PAUSE emission) is a workflow-layer rule layered on top of those sources.*
