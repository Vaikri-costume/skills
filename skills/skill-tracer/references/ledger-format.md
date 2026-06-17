# Ledger Format

How the audit ledger is structured: location, header, columns, flag-ID prefixes, cluster grouping, and the drift test that protects against stale cold-trace results. SKILL.md Step 5 owns the workflow ("collect ISSUE blocks, group into clusters, write rows as Step 6 addresses them"); this reference owns the data spec.

---

## Location

```
~/.claude/skill-tracer-audit-ledger/<target-skill-name>.md
```

One file per target skill, accumulating every trace across every invocation and every round. (WHY: the cumulative ledger is load-bearing — regression detection across all prior rounds requires the complete Root-cause history, the per-cluster defect identity the regression check compares against [see address-decision.md "Convergence check between rounds"]; rotating or archiving entries would cause regressions against older defects to go undetected.) The orchestrator MUST NOT write the ledger inside the target skill's tree — that would leave artifacts the next cold trace flags as dead text. One-file-per-skill avoids directory bloat: ten invocations of the same skill produce N rows across one continuous round sequence in one file, not ten directories or ten separate restart-at-Round-1 sections.

---

## Header template (new ledger)

```
# Audit ledger — <target-skill-name>

<!-- in-flight marker lives here when a trace is mid-run, in the form `in-flight:: YYYY-MM-DDTHH:MM <action> round-N` (one of dispatch/addressing/handoff per recovery-protocol.md); absent means no trace in flight. This format must stay in lockstep with recovery-protocol.md "In-flight marker format" section. -->


| Runtime | Round | Phase | Cluster | Root cause | Address | Flags |
|---|---|---|---|---|---|---|
```

---

## Round numbering — cumulative per skill, not per invocation

Round numbers never restart on a new invocation. Before assigning any Round number, scan existing ledger rows for the highest Round value. Current invocation's first round = highest existing Round + 1. If ledger empty, start at Round 1.

The Runtime column disambiguates which invocation a row came from; the Round column accumulates. Reading the ledger top-to-bottom gives the skill's complete trace history in chronological round order.

---

## Row-writing timing

Step 5 produces the `<flag-to-cluster-map>` (its flag→cluster map) in memory; Step 6 addresses each cluster and writes the row at that moment (one row per cluster as it's addressed, not a batch at end of Step 6). The row's Address column is the Step-6 decision; the Cluster/Flags/Root-cause columns are Step-5 outputs the orchestrator carries forward.

**Pipe characters in Address values:** the render script splits rows on `|` to parse table cells; an Address value containing a literal `|` (e.g., `FIX (SKILL.md: replace "A | B" with "A or B")`) will cause that row to be silently skipped. Avoid literal `|` in Address column text. Use "or", "vs.", or a dash as separator instead.

**Blank lines in Address values:** the render script also exits table-parsing mode on any blank line inside the table. An Address value that spans multiple lines (blank line embedded) will silently truncate the table at that row, dropping all subsequent rows. Address values must be single-line (no embedded newlines). SKILL.md Step 6 delegates row format to this reference — this single-line constraint applies at every Step 6 write.

**Write rows with `scripts/append_ledger.py` instead of hand-typing** — it rejects (non-zero exit) any of three malformations, so a bad row fails loudly at write time rather than being silently dropped/truncated by the renderer later: (1) a literal `|` in a cell, (2) an embedded newline, and (3) an Address that doesn't start with one of `FIX` / `STRENGTHEN` / `USER-PAUSE` (or their `would-` variants) **at a token boundary** — `ledger_common.address_kind_ok` requires the kind be followed by a space *or* `(` (so `would-STRENGTHEN (…)` and `would-STRENGTHEN(…)` both pass; a *bare* kind with nothing after it, or `FIXED…`/`STRENGTHENING`, is rejected):

```bash
python3 ~/.claude/skills/skill-tracer/scripts/append_ledger.py append <ledger> \
  --runtime <Runtime> --round <N> --phase TRACE --cluster C<n> \
  --root-cause "<one-line>" --address "<FIX/STRENGTHEN/USER-PAUSE ...>" --flags "F1,B3,E5"
```

**Shell-invocation guard (write for zsh).** Invoke `python3` as the literal command word; do NOT store the whole `append` invocation in a shell variable. Under zsh — a common default shell — an unquoted variable holding `python3 .../append_ledger.py append ...` is **not** word-split: the entire string is treated as one command name and fails with `command not found` (exit 127). When writing several rows in a round, repeat the literal `python3 "$SCRIPT" append "$LEDGER" ...` per row, putting only the *paths* in quoted variables (never the command). Bash word-splits and would mask this; zsh does not.

At end of round, `append_ledger.py close-round <ledger> --round <N>` recomputes the round-summary comment (raw-flag count, cluster count, FIX/STRENGTHEN/USER-PAUSE tally) **from the round's actual rows** rather than hand-counting — so the summary can't drift from the rows. `append_ledger.py verify-auditability <ledger> --round <N> --expect "<all flag-IDs this round, comma-separated — e.g. F1,B2,E3>"` asserts the no-orphan-flag invariant (every flag-ID appears in exactly one row). `--expect` is split on **commas**; pass space-separated values and the whole string is read as one flag-ID, so the check spuriously fails. `append` is the Step 6 per-cluster row write; `close-round` and `verify-auditability` are the Step 7 round-close actions (the summary tally + the no-orphan-flag assertion) — see SKILL.md Step 7.

---

## Example rows

| Runtime | Round | Phase | Cluster | Root cause | Address | Flags |
|---|---|---|---|---|---|---|
| 2026-05-27T03:50 | 1 | TRACE | C1 | <one-line description> | FIX (<file>: <one-line summary of change>) | F1, B3, E5 |
| 2026-05-27T03:50 | 1 | TRACE | C2 | <one-line description> | STRENGTHEN (added at <file>:<exact-line-or-range>: "<quoted text first 80 chars>") | F2 |
| 2026-05-27T03:50 | 1 | TRACE | C3 | <one-line description> | USER-PAUSE (<one-line question with both candidate fixes named>) | B7 |
| 2026-05-27T03:50 | 2 | TRACE | C1 | <one-line description> | FIX (...) | F1, B2 |
| 2026-06-15T10:30 | 3 | TRACE | C1 | <description, second invocation continues at Round 3> | FIX (...) | F1, E2 |

---

## Column meanings

- **Runtime**: ISO-8601 UTC time when the round started, formatted `YYYY-MM-DDTHH:MM`. Fresh rounds (recovery rules 4/5) use current invocation's Runtime; resumed rounds (rules 1/2/3) preserve the prior session's Runtime from the in-flight marker. All rows in the same round share the same Runtime regardless of how many invocations addressed that round's clusters.
- **Round**: cumulative-per-skill round number.
- **Phase**: `TRACE` for cold-trace-agent clusters (the overwhelming majority — skill-tracer is correctness-only). `REVIEW` for clusters sourced from the round-1 code-review pass (SKILL.md Step 2.5). The code-review pass is the *first phase of round 1* (not a separate round), so a round-1 ledger can hold **both** `REVIEW` rows and `TRACE` rows under the same Round number — the Phase column is what tells them apart; only round 1 (or a re-trace's fresh first round) ever carries `REVIEW` rows. `SIMPLIFY` for clusters from a `/simplify` cleanup pass (prose/structure cleanups, not correctness). The writable phases are therefore `TRACE`/`REVIEW`/`SIMPLIFY` (`append_ledger.py`'s `KNOWN_PHASES`); `PORT-AUDIT` is **read-tolerated** in old ledgers (`ledger_state.py`/`render_ledger.py` accept any `[A-Z\-]+` phase) but **write-forbidden** here — it belongs to skill-publisher.
- **Cluster**: simple `C<n>` — `C1` is the first cluster in this round, `C2` the second. Cluster numbers restart at 1 **at the start of each round** (the Round column disambiguates) — **with one exception: round 1's two phases share a single continuous sequence**. The code-review (`REVIEW`) clusters take the first `C` numbers, then the cold-trace (`TRACE`) clusters *continue* from there — the TRACE phase does NOT restart at `C1` within round 1 (it is the same round, so restart-at-1 applies once, at the REVIEW phase's start, not again at the TRACE phase). (WHY this is a hand-maintained convention, not machine-enforced — review-finding 9: no script verifies cluster-number continuity; `verify-auditability` and the summary tally key only on Round number and **flag-IDs**, never cluster-IDs. Cluster IDs are organizational display labels, so a slip like two `C1` rows in one round is cosmetic, not an auditability breach — the no-orphan-flag invariant is defined over flags, which remain unique. Keep the continuity for readability; nothing breaks if it drifts.)
- **Root cause**: one-line description of what the cluster is (the underlying problem all its flags point at). Defect-focused.
- **Address**: FIX / STRENGTHEN / USER-PAUSE in the per-type formats spec'd in address-decision.md.
- **Flags**: every raw flag-ID belonging to this cluster (comma-separated, ordered by prefix — see Flag-ID scheme below).

---

## Flag-ID scheme

Four flag prefixes — three for the cold directions, one for the code-review pass. Per-source counters are independent — a round with forward + backward findings has `F1, F2, B1`, not `F1, F2, F3`.

| Prefix | Source | Phase |
|---|---|---|
| `F*` | forward trace | TRACE |
| `B*` | backward trace | TRACE |
| `E*` | executor trace | TRACE |
| `CR*` | code-review pass (SKILL.md Step 2.5) | REVIEW |

`CR*` is distinct from `C*` on purpose — `C*` is the Cluster column (`C1`, `C2`, …), never a flag. `CR*` flags appear only in the round-1 code-review *phase* (the `REVIEW`-phase rows); a single cluster is always one phase, so a cluster never mixes `CR*` with `F*/B*/E*` even though both can appear under round 1.

**Flags-column ordering** (when a cluster has multiple prefixes): `F*` → `B*` → `E*` (`TRACE`-phase clusters). A `REVIEW`-phase cluster carries only `CR*` flags.

(Pre-refactor ledgers may carry historical `EFF*`/`A11Y*`/`SEC*`/`G*`/`G-PORT*`/`SIM-*` flags from when skill-tracer ran cadenced directions + the CCVW audit + simplify pass. Those moved to skill-creator-ccvw (efficiency/accessibility iterate-quality) and skill-publisher (security, CCVW audit, simplify). New trace rows use only `F*`/`B*`/`E*`.)

---

## Cluster grouping procedure

Group flags by root cause. Two flags belong to the same cluster when at least one of these tests passes:

1. **Same Claim text anchor**: their `Claim:` quotes reference the same `<file>:<exact line or block>` (whitespace-tolerant match on the quoted text).
2. **Same fix would close both**: applying one surgical edit (or one strengthen) would address what both flags describe. The orchestrator mentally drafts the FIX or STRENGTHEN address (per address-decision.md's address formats) and checks whether the same edit closes both flags; the draft does not get written anywhere — it's a clustering check the orchestrator performs in head before deciding.
3. **Same root cause across symptoms**: both flags describe symptoms whose Target sections trace back to the same upstream defect (e.g., one wrong filename in a script causes both a forward-claim mismatch and a backward-consumer absence — different symptoms, same root cause). Quote-overlap in the Target sections is the test.

**When in doubt, keep flags in separate clusters and address them separately.** Over-clustering risks one fix addressing only part of the underlying defect, and obscures the consolidation signal the Flags column displays (a one-cluster row with `F1, B2, E4` is informative; merging unrelated flags into the same cluster destroys that signal).

---

## Anti-double-counting (orchestrator-side)

If two of the three trace agents flag the same exact text under the same root cause, treat them as one ISSUE for fix purposes. Log both flags (preserves the trace history) but apply one fix.

If they flag the same text under **different** root causes (e.g. forward says "claim contradicts reality" while executor says "line is ambiguous in isolation"), apply both fixes — they address different aspects.

---

## PRE-FLIGHT drift test

Each trace agent returns a `PRE-FLIGHT` line per file in the format `PRE-FLIGHT <path>: <line_count> lines, last edited <yyyy-mm-dd>`.

**Concrete drift test:** for each PRE-FLIGHT line, compare the reported line count against the file's current line count (`wc -l <path>`) and the reported last-edited date against the file's current mtime date. **Line count is the strict signal** — any non-zero line-count delta is drift. **The date dimension tolerates a ±1-calendar-day skew** (review-finding 6): the agent's PRE-FLIGHT date and the file's local mtime date can straddle a midnight / timezone boundary and differ by one day with no real edit, so only a date delta of **more than one day** counts as drift. This does not weaken detection — a genuine mid-round edit changes the line count (caught strictly), and the date check still catches a multi-day-stale dispatch. `check_drift.py` implements exactly this.

**Run it deterministically with `scripts/check_drift.py`** rather than hand-comparing (hand-counting `wc -l` across N files + matching dates is exactly the silent-error-prone work a script should own). Pipe the agents' PRE-FLIGHT lines (or a whole agent report — non-PRE-FLIGHT lines are ignored) to it:

```bash
python3 ~/.claude/skills/skill-tracer/scripts/check_drift.py --file <preflight-lines-or-report>
# or:  printf '%s\n' "$PREFLIGHT_LINES" | python3 .../check_drift.py
```

Exit 0 = no drift (proceed); exit 1 = drift or a now-missing file (re-dispatch cold — see below); exit 2 = no PRE-FLIGHT lines parsed **when JSON is printed** (`checked: 0` — the report carries no PRE-FLIGHT block, a malformed/aborted report; treat that direction as unusable and re-dispatch it, the same response as `check_results.py` returning `usable:false`). (A usage-error exit 2 — **no JSON printed at all**, e.g. `--file` not found — is an invocation error, not this content case: fix the invocation and re-run, do not re-dispatch.) The JSON output lists each drifted file with its `reported→current` line-count/date delta. A non-empty `unparseable` list (PRE-FLIGHT-looking lines the script couldn't parse) signals a garbled report even when the exit is 0 (the parsed lines showed no drift) — treat that direction as unusable and re-dispatch it. **Precedence:** exit 1 (drift/missing) takes priority — when a report both drifts and carries `unparseable` lines, run the all-three re-run (the round is stale wholesale); the single-direction `unparseable` response applies only when there is no drift (exit 0, or exit 2 where no PRE-FLIGHT parsed at all). Both call sites use it: SKILL.md Step 5 (result-collection) and recovery-protocol.md rule 1 (before consuming recovered results).

If drift is detected: tell the user, then re-run Steps 2–4 against the current files (Step 2 re-enumerates, Step 3 rebuilds the prompts, Step 4 re-stages + re-dispatches — all three directions). The re-run replaces the in-flight `dispatch round-N` marker via the atomic-write protocol's overwrite path (round number stays at N; same Runtime stays on the marker because this is still the same invocation; prior partial agent outputs are discarded and not recorded on the ledger).

---

## Exact line numbers in STRENGTHEN

After applying a STRENGTHEN edit, re-read the file to capture the exact line numbers where the new text landed. The anchor format is `<file>:<line>` for a single-line addition or `<file>:<start>-<end>` for a multi-line block.

Approximate anchors (`~line N`, "around line 176") are NOT acceptable — the next cold trace's ability to verify the STRENGTHEN landed depends on being able to find the exact text at the named location. Address format is spec'd in address-decision.md.

---

## Round and invocation summary comments

After each round's rows, append: `<!-- Round N total: raw flags A — clusters M — addresses: F FIX + S STRENGTHEN + P USER-PAUSE -->`.

After the invocation completes (or pauses), append: `<!-- Invocation <Runtime> total: rounds N..M — raw flags A — clusters X — addresses: F FIX + S STRENGTHEN + P USER-PAUSE -->`. Derive it from the ledger (no script emits it): **N..M** = the lowest..highest Round whose rows carry **the Runtime value this session actually wrote onto its rows** — which for a resumed invocation (recovery rules 1/2/3) is the *prior* session's Runtime preserved from the in-flight marker, NOT the current wall-clock (all of one invocation's rounds share that one Runtime; scan the ledger for rows bearing it, and do not scan for a fresh clock value — a resumed run's rows do not carry one); **A / X / F / S / P** = the sums, across rounds N..M, of the per-round `close-round` summaries (raw flags / clusters / FIX / STRENGTHEN / USER-PAUSE).

These comments don't appear in the rendered table but make per-invocation totals greppable. The Round summary is also the authoritative signal for "round was clean" — see recovery-protocol.md definition.


---

## Auditability invariant

Every raw flag from every round must appear in the Flags column of exactly one row tagged with that round's Runtime. No flag-ID may be left out. If you tell the user "round 1 raised 78 flags and we applied 24 fixes," the ledger must show all 78 flag-IDs distributed across 24 rows with that round's Runtime.

This is the no-orphan-flag invariant (Invariant 3 in SKILL.md) operationalized at the ledger row level.

`verify-auditability` enforces it, but its missing-flag detection is **only as complete as `--expect`**: a flag omitted from *both* a ledger row *and* the `--expect` set is invisible to the check (nothing flags its absence). So `--expect` must be the round's *complete* raised flag set (the full key-set of `<flag-to-cluster-map>`) — that completeness is the orchestrator's responsibility, not something the script can verify on its own. (The check independently catches double-counting and stale/unexpected flags regardless of `--expect` completeness; only the missing-flag arm depends on it.)
