# Ship Ledger Format

How skill-publisher's ledger is structured. Adapted from skill-tracer's ledger-format — same row mechanics, different Phase values (POLISH / AUDIT / TIER / PACKAGE / PR instead of TRACE / SIMPLIFY / PORT-AUDIT).

---

## Location

```
~/.claude/skill-publisher-ledger/<skill>.md
```

One file per target skill, accumulating every ship run. Not written inside the target skill's tree (that would leave artifacts the next tracer/audit flags as dead text).

---

## Header template (new ledger)

```
# Ship ledger — <skill>

<!-- in-flight marker lives here when a ship run is mid-flight, in the form `in-flight:: YYYY-MM-DDTHH:MM <action> run-N`; absent means no ship in flight. The action-keyword enum and recovery rules are in recovery-protocol.md (authoritative) — the inline list here (polish/audit/tier/addressing/changelog/packaging/pr) is a convenience summary; if the two ever diverge, recovery-protocol.md wins. -->
audit-references:: skill-creator-ccvw@<date-or-missing>, skill-creator@<date-or-missing>, plugin-dev/skill-development@<date-or-missing>

| Runtime | Run | Phase | Cluster | Root cause | Address | Flags |
|---|---|---|---|---|---|---|
```

**`audit-references::` line (updated by Step 3):** records the mtime date of each reference skill the CCVW audit ran against — `skill-creator-ccvw@YYYY-MM-DD, skill-creator@YYYY-MM-DD, plugin-dev/skill-development@YYYY-MM-DD`. Set to `<missing>` if the reference skill was not installed. Absent if the audit has not yet run for this ledger. Written and kept current by the orchestrator per `references/audit-prompt.md`; the drift-check in audit-prompt.md compares prior vs current to surface reference-skill changes between runs.

(Publisher uses **Run** numbering — each ship invocation is a Run, cumulative per skill — analogous to skill-tracer's Round but at ship granularity.)

---

## Phase column values

- **POLISH** — Step 2 simplify-pass edits (flags: `SIM-R*`/`SIM-S*`/`SIM-E*`/`SIM-A*` from the 4-agent pass, same as the simplify pass uses).
- **AUDIT** — Step 3 CCVW Word/Spirit GAPs (flags: `G<n>` — bare G-codes, no hyphen).
- **TIER** — Step 4 tier-transition findings. Sub-typed by check: `G-PORT*` (portability lint), `G-ATTR*` (attribution lint), `SEC*` (security check), `G-COWORK*` (Cowork-compatibility).
- **PACKAGE** — Step 8 packaging issues (rare — usually a model-agnostic conformance failure that blocks packaging).
- **PR** — Step 9 PR-creation issues (rare — auth failure, no upstream, push conflict).

---

## Example rows

| Runtime | Run | Phase | Cluster | Root cause | Address | Flags |
|---|---|---|---|---|---|---|
| 2026-05-30T14:00 | 1 | POLISH | C1 | SKILL.md Step 4 verbose — 3 ways of saying same thing | FIX (SKILL.md Step 4: collapsed to one statement, -12 lines) | SIM-S1, SIM-R2 |
| 2026-05-30T14:00 | 1 | AUDIT | C2 | description not pushy enough per CCVW Spirit | FIX (frontmatter description: added trigger contexts) | G1 |
| 2026-05-30T14:00 | 1 | TIER | C3 | hardcoded ~/.claude/ path fails claude-users | FIX (SKILL.md: $XDG_DATA_HOME path with fallback) | G-PORT1 |
| 2026-05-30T14:00 | 1 | TIER | C4 | viewer is server-only, fails Cowork headless | USER-PAUSE (add --static mode OR document Claude-Code-only? — which matches intent?) | G-COWORK1 |

---

## Column meanings

- **Runtime** — ISO-8601 UTC when the ship run started, `YYYY-MM-DDTHH:MM`.
- **Run** — cumulative-per-skill ship-run number. First ship is Run 1; every subsequent ship increments.
- **Phase** — POLISH / AUDIT / TIER / PACKAGE / PR per above. (These five are the closed publisher-valid set. The vendored `append_ledger.py`'s `--phase` *also* accepts skill-tracer's current phases `TRACE`/`REVIEW` and the legacy historical phases `SIMPLIFY`/`PORT-AUDIT` (still read-tolerated) because the script is byte-vendored for sync parity — the publisher never writes those; only the five above are legal in a publisher ledger.)
- **Cluster** — `C<n>`, restarts at 1 within each Run.
- **Root cause** — one-line description of the finding.
- **Address** — FIX / STRENGTHEN / USER-PAUSE per `ship-checklist.md`.
- **Flags** — raw finding IDs. The families are: `SIM-*` (polish/simplify), `G<n>` (a bare AUDIT Word/Spirit GAP — `G1`, `G2`, … with no second hyphenated segment), and the TIER sub-families `G-PORT*` / `G-ATTR*` / `SEC*` / `G-COWORK*`. Plus the synthetic flag `audit-skipped` (the audit-declined USER-PAUSE row, Step 3). This family list is **illustrative, not closed** — synthetic workflow flags like `audit-skipped` are legal. The AUDIT family is written `G<n>` (not the glob `G*`, which would literally subsume the hyphenated `G-PORT*`/`G-ATTR*`/`G-COWORK*` families) — a bare `G` code has no hyphen; the `G-…` codes always do.

---

## Run + invocation summary comments

After each Run's rows, write the run-summary comment. Use `scripts/append_ledger.py close-round <ledger> --round N` to auto-compute it from the ledger rows — the script generates:
`<!-- Round N total: raw flags <flags> — clusters <M> — addresses: <F> FIX + <S> STRENGTHEN + <P> USER-PAUSE -->`
Note: `close-round` hardcodes `Round` in the label (skill-tracer's column name) and omits ship-context fields. The Edit-replace step's find target (`<!-- Round N total:`) is **tightly coupled to this hardcoded label** — the label is unconditionally hardcoded in the script body (`f"<!-- Round {args.round} total: …"`) and will not change without a deliberate code edit; if the script is ever updated and the label text changes, this find target must be updated in the same vendored-sync pass. Use `Edit` to find the generated `<!-- Round N total: raw flags … — clusters … — addresses: … -->` comment and replace it with the publisher's canonical form to add ship context:
`<!-- Run N total: <X> clusters — <F> FIX + <S> STRENGTHEN + <P> USER-PAUSE — shipped at tier <tier>, version <prior>→<new>, PR: <url-or-none> -->`
(The Replace operation is a single Edit — old_string = the generated `<!-- Round N total:` line, new_string = the canonical `<!-- Run N total:` line. Do not append a second comment; replace the existing one. WHY the generated comment is safe as `old_string`: `close-round` uses em-dash `—` as a separator, never literal `|` — the pipe constraint that applies to table rows does not apply to this HTML comment. Both the generated form and the canonical replacement form use only em-dashes and colons as separators.)

## Rendering

The ledger is rendered to HTML via `render_ledger.py` (SKILL.md Step 10), the shared renderer byte-vendored from skill-tracer.

Invocation:
```bash
python3 ~/.claude/skills/skill-publisher/scripts/render_ledger.py ~/.claude/skill-publisher-ledger/<skill>.md --config @~/.claude/skills/skill-publisher/scripts/ledger-render-config.json --open
```
`--config` is **required**: it supplies the publisher's Run column + POLISH/AUDIT/TIER/PACKAGE/PR phase colors. Omitting it makes the renderer fall back to skill-tracer defaults and flag valid publisher action keywords (`polish`/`audit`/…) as `INVALID ACTION` in the HTML. The `@` prefix signals a file path (a bare path is parsed as inline JSON and fails); `render_ledger.py` expands a leading `~` in `@`-prefixed config paths via `pathlib.Path.expanduser()`, so `@~/.claude/...` resolves correctly.

**Skip checks (run before rendering):** if the ledger is absent OR contains no data rows, skip the render.
- Absence: `[ -f ~/.claude/skill-publisher-ledger/<skill>.md ] || echo absent` — if absent, skip immediately.
- Data rows: `grep -c '^| 20' ~/.claude/skill-publisher-ledger/<skill>.md || true` — a header-only file returns `0`. `grep -c` exits 1 when no lines match, so `|| true` prevents a false non-zero exit from being misread as an error. (WHY `^| 20`: every data row's Runtime starts `20XX-…`; the header row and comment lines do not — so this counts exactly the data rows. This heuristic assumes machine-generated 21st-century Runtimes; a hand-edited Runtime not starting `20` would be undercounted — render manually if you suspect that.)

**Exit codes** (rendering is **non-blocking** — never block on a render failure; the ledger is still valid plain Markdown at its path):
- **0** = success → prints `Wrote HTML to <path>` to stdout; relay that HTML path to the user. If `--open` fails (headless / Cowork), it still prints the `Wrote HTML to <path>` line (then a benign could-not-open note) — include that HTML path + the ledger path in your response so the user can open them manually.
- **1** = ledger file not found — should not occur because the skip check above catches the absent-ledger case; note in your response: "render_ledger.py reports the ledger was not found at `<path>` despite the pre-render check passing — verify the file was not deleted after Step 1 created it," then proceed.
- **2** = config file not found, OR config JSON parse error, OR ledger read failure (OSError) — each sub-cause prints a different identifying stderr message, but the action is the same: include the stderr output in your response and proceed.
- **3** = parse/render exception — include stderr.
- **4** = HTML write failure — check disk/permissions.

The summary records the ship outcome (tier, version delta, PR) — making the ledger a complete ship history of the skill.

---

## Single-line + pipe-safe Address values

Same constraint as skill-tracer's ledger: Address values must be single-line (no embedded newlines) and must not contain a literal `|` (use "or" / "vs." / a dash) — the `render_ledger.py` table parser splits on `|` and exits table mode on blank lines.
