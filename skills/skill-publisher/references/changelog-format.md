# Changelog Format

How skill-publisher writes the version bump + changelog entry (Step 7) into the target's HISTORY.md.

---

## Version bump (semver)

Increment the target's HISTORY.md `version` field:
- **Patch** (`1.0.0` → `1.0.1`) — bug fixes, prose polish, no behavior change.
- **Minor** (`1.0.0` → `1.1.0`) — new capability, backward-compatible.
- **Major** (`1.0.0` → `2.0.0`) — breaking change (renamed commands, changed output format, removed feature).

If the change scope is ambiguous, ask the user which bump applies. Set `parent-version` to the version being superseded — and also update SKILL.md's `metadata.parent-version` to the same value. **Pre-versioned target:** if the prior HISTORY.md exists but carries no `version` (a pre-versioned skill), there is nothing to bump *from* — set `parent-version: pre-versioned` (unquoted, per SKILL.md's unquoted-YAML rule — one form only; this is the token skill-creator-ccvw's `improve-existing-skill.md` uses) and start `version` at `1.0.0`, then write the entry as a first-version entry (see Degraded mode below for the heading form). **At Step-10 verification:** a `pre-versioned` parent makes `verify_ship --strict-changelog`'s **bump check n/a by design** — there is no prior version to bump *from*. `_parse_semver` returns None, so `verify_ship` records "bump check skipped (pre-versioned / unparseable version)" and still enforces the Keep-a-Changelog **category** checks, just not the bump-level step. Either omit `--parent-version` or pass the literal `pre-versioned` — both are treated identically. So a present-HISTORY pre-versioned skill shipping its `1.0.0` initial entry on the normal path is **not** an enforcement gap; the skipped bump is the correct verdict for a first version.

---

## Changelog entry (Keep-a-Changelog format)

Append a new entry at the TOP of the changelog body (newest first) by filling `assets/changelog-entry-template.md` (the canonical template the executor fills — the block below mirrors it). Group changes under **Keep-a-Changelog category headings** (`#### Added / Changed / Deprecated / Removed / Fixed / Security`) — omit any category with no entries:

```markdown
### <new-version> — <ISO-date> (shipped)
#### Added
- <new backward-compatible capability>
#### Fixed
- <bug fix>
```

**On the `(shipped)` suffix:** skill-creator-ccvw's `history-template.md` writes a bare heading `### <version> — <ISO-date>` with no status word. The publisher deliberately appends a status suffix — `(shipped)` for a normal ship, `(initial publish)` for degraded-mode first publish — to mark which entries the publisher produced. This is an intentional extension of the template, not a conflict: `verify_ship.py`'s changelog-presence check matches on the version prefix (`^#{2,3}\s*\[?v?<version>\b` — version headings are `##` (keepachangelog `[1.2.0]`) or `###`; the `\[?` allows the keepachangelog bracket), so the trailing suffix does not affect detection.

**Sourcing the change summary — diff-driven when a published baseline exists.** Step 7a diffs the local skill against its published state (`diff_published.py` over the `github_pr.py --diff-only` checkout); when that diff exists, the **Step-7 cold changelog agent** (`references/changelog-agent-prompt.md`) reconciles **two signals at equal weight** and tags each change `from: both|diff-only|ledger-only`:
1. The **structured diff** vs the published state — catches out-of-ledger manual edits the ledger never recorded.
2. This ship run's **ledger rows** (the POLISH + AUDIT + TIER clusters addressed — the publisher's cluster-bearing phases; PACKAGE/PR rows are packaging/PR bookkeeping, not change clusters).
3. Any **user-described** change ("I added a new export format").

**No-published-state fallback** (no upstream, or the skill isn't published there yet, or git unavailable): skip the agent and source from the ledger rows alone (+ the user description + an optional `<last-ship-tag>` git log: `git log <last-ship-tag>..HEAD --oneline`, where `<last-ship-tag>` is `<skill>-v<prior-version>` — the per-skill tag the PR flow pushes at each ship, `github-pr-workflow.md` step 8; if absent, `git log --since=<prior-ship-date>` or ledger-only).

**Bump (SemVer)** — the highest level any single change warrants: **patch** = Fixed / Changed-with-no-contract-break / docs; **minor** = Added (new backward-compatible capability); **major** = Removed / a breaking Changed (renamed command, changed output contract). When the agent ran, `final_bump = max(agent_bump, ledger_bump)`. Keep entries factual + concise — one line per meaningful change; summarize prose tweaks as a single "polish pass" under Changed.

---

## Degraded mode (no prior HISTORY.md)

If the target had no HISTORY.md (Step 1 degraded mode generated a minimal one), there's no prior version to bump from. Default to `1.0.0`; use `0.1.0` only if the user explicitly states the skill is pre-release or experimental — do not ask unless there is a signal that the user intends pre-release (e.g. they said "it's a draft"). Write the first changelog entry as `### <version> — <date> (initial publish)`. No version increment — this IS the first version.

**Step-7 degraded-mode handling (the two Step-1 sub-paths):**
- **(a) Attribution declared** (a minimal HISTORY.md with `version: 1.0.0` was generated): skip only the version *increment* — the scaffold's first version (1.0.0, or 0.1.0 on a pre-release signal) IS the version; use it. Still write the first changelog entry `### <new-version> — <date> (initial publish)`, **creating the `## Changelog` section first** (the minimal scaffold omits it, so this entry establishes it). Add `parent-version: pre-versioned` (the scaffold has no parent-version line, so this adds it; on a non-degraded HISTORY.md it updates the existing line). `verify_ship` does NOT read `parent-version`; the Step-10 changelog-presence check is satisfied by the first changelog entry, not by `parent-version`.
- **(b) User skipped entirely** (no HISTORY.md): skip Step 7's version-bump + changelog actions wholly (the Step-7 session-log echo is harmless; an already-written `STEP:version` marker needs no cleanup). Step 10 then omits the verify_ship version/changelog assertions — there is no version to check.

---

## Degraded-mode HISTORY.md scaffold (Step 1 procedure)

When HISTORY.md is absent, Step 1 prompts once and either scaffolds a minimal HISTORY.md or ships locally. Full procedure (SKILL.md keeps only the trigger + skip-branch consequences inline):

**Prompt (verbatim):** `No HISTORY.md found at <target>. Declare attribution category now? (A/B/C/D — A=fork of existing work, B=derivative/remix, C=idea-inspiration, D=independent/original; see skill-creator-ccvw's attribution-spec.md for the authoritative definitions — these one-liners mirror attribution_lint.py's A=fork / B=derivative / C=inspiration / D=independent and suffice for the choice; load attribution-spec.md only if the user asks for elaboration. Or 'skip' to ship locally without provenance)`. Retain the answer as `<attribution-answer>`.

**Comparison is case-insensitive** (A/a … D/d, SKIP/skip). If the answer is not A/B/C/D or "skip", re-ask once with the full prompt verbatim. If the second answer is also invalid, set `<attribution-answer> = "skip"` (degraded-mode) and note it to the user.

**Minimal scaffold field set (closed for the *initial* scaffold — fixes the field SET written now, not the `1.0.0` value):** `name`, `description`, `version` (`1.0.0`, or `0.1.0` on an explicit pre-release signal), `category`, and `author.primary`. (Closure governs only what the scaffold writes at Step 1 — Steps 7 and 9 legitimately ADD `parent-version`, a `## Changelog` section, and `author.history[]`/`inspirations[]` later; those are not scaffold fields and do not violate this closure.)
- `name` / `description`: source from the target SKILL.md frontmatter.
- `category`: the bare uppercase letter A/B/C/D. `attribution_lint.py`'s `infer_category` RETURNS this explicit letter when it is a valid A/B/C/D, so the scaffold reports the declared category; it shape-infers from `author.history[]`/`inspirations[]` presence (history→A, inspirations→B, none→D) only when the letter is absent or invalid. The letter records declared intent and drives which fields to add next — a real Category A/B still needs `author.history[]` (plus a LICENSE), whose absence `attribution_lint` flags at Step 4, so the declared letter alone is not an attribution-complete artifact.
- `author.primary`: ask via AskUserQuestion "Author name for attribution?" (offer 'unknown'; a typed name comes through the free-text 'Other' choice); block until answered.
- YAML shape: `name`/`description`/`version`/`category` as top-level keys, `author` as a mapping holding `primary` (i.e. `author:` on its own line, then an indented `  primary: <name>`) — the nested shape `attribution_lint.py` parses. `inspirations` and `author.history[]` may be added later.
- `license` is a **SKILL.md** frontmatter field, NOT a HISTORY.md field — Step 9's public-push gate runs `spdx_check` on the SKILL.md license, so a degraded skill heading to a public PR must have its SKILL.md license set (that gate's USER-PAUSE enforces it).

**The minimal scaffold is a starting point, NOT an attribution-complete artifact.** It carries no `author.history[]`, so `attribution_lint.py` flags no history/LICENSE gaps from the scaffold alone. To declare a real Category A/B fork the user must add `author.history[]` entries; `attribution_lint.py` then requires `role`/`name` on every entry (plus `skill`/`license` on the FIRST entry) and `skill`/`by`/`pattern` in `inspirations[]`, and a LICENSE file whenever `author.history[]` is non-empty — those gaps surface at Step 4 once history is filled in and are addressed in Step 5. `attribution_lint.py` does NOT check any `source` field; the upstream `source` URL a PR needs is resolved at Step 9. The first changelog entry follows the **Degraded mode** path above.

**On 'skip' (or default-to-skip):** the skill ships **as-is, without provenance** — **Steps 2–5 (polish, audit, tier checks, addressing) are bypassed entirely** (a quick local ship skips the expensive cold audit + tier gates, so **no Step-5 close-round comment is written** — this is the "no close-round comment" path Step 5 and Step 10's append-fresh check reference). No version bump (no prior version known); Step 9 still runs but opens **no upstream PR** (no upstream repo known) — it offers the no-upstream hosting-branch option and clears the packaging marker on its no-PR path; run Step 8 packaging as normal (`.skill` for shared tiers; personal-tier remains unpackaged per Step 8's personal branch). (Steps 6–7 and Step 10 carry their own degraded-mode handling.)

---

## Relationship to the ship ledger

The ship ledger (`~/.claude/skill-publisher-ledger/<skill>.md`) is the publisher's internal record of every cluster across every ship run. The changelog in the target's HISTORY.md is the user-facing summary. The changelog entry is distilled FROM the ledger rows — the ledger has per-cluster detail (which file, which fix); the changelog has the human summary ("polished + portability-fixed for claude-users").
