# Inbox Arbiter Prompt — drive-organizer
<!-- The orchestrator fills every [SLOT] and dispatches ONE arbiter per ≤25-file batch.
     PATHS ONLY. This is a periodic _Inbox-reclamation sweep, NOT a per-round step. The
     batching formula (~100 soft guideline → ceil(count/25) parallel arbiters of 25) and
     the full when/how are stated authoritatively ONCE in the "When + how the orchestrator
     runs the sweep" section below (and SKILL.md's propose "Inbox arbiter sweep" note) —
     not repeated here. Keep light: pointers, not inlines. -->

A first-pass classifier (or an earlier round) sent these files to `_Inbox/` — its bucket for
"couldn't place." Your job: decide, per file, whether it is TRULY unclassifiable, or whether
the placement was lazy / stale and a real destination now exists. Be skeptical — after a
learning loop has run, most `_Inbox/` files should find a home. You are read-only.

## Rules
- Re-examine each file against the CURRENT taxonomy and rules — which may have grown since the
  file was inboxed. These files are already on local disk (no cost-toggle / online-only download
  skip applies here), but **inspect each only by the means your model capabilities permit** (next
  rule) — "already downloaded" is not the same as "this model can open it".
- **Model capabilities** `[CAPABILITIES]` (fill from propose's `Model capabilities: peek=… vision=…`
  stderr line — the same slot the classify fan-out uses. **Fallback:** if that line is absent or
  suppressed and cannot be re-derived, default to the conservative `peek=off vision=off` — never
  dispatch with an unfilled `[CAPABILITIES]` slot; degrading to name/path/EXIF routing is always
  safe, whereas assuming a capability the model lacks is not):
  - **peek ON** — you may open document/text contents (Read) to re-judge.
  - **peek OFF** — classify each document from filename + path + rules only; never open file contents.
  - **vision ON** — you may open images (Read) and describe them.
  - **vision OFF** — route images by filename + path + rules + `organizer.py exif <path>` metadata
    (date/camera/dimensions); never open pixels.
- Read yourself: active groupings `[GROUPINGS]`; merged taxonomy `[TEMPLATES_CMD]`; the
  touched `.tidy-rules.json` under `[ROOT]`; entity aliases/negatives `[ENTITIES_PATH]`;
  file-type-specific decisions (vision-vs-name, sidecars, atomics, RAW, lock files, legacy formats, and the fall-through bucket) `[FILE_TYPE_ROUTING_PATH]` + the fall-through category signals `[TIDY_BUILTIN_PATH]` (the documented builtin-category bucket — without it an inboxed doc whose only signal is a builtin-category keyword can't reach the fall-through and you could only `confirm_inbox`, defeating reclamation; matches the classify fan-out's reading list); conventions
  `[FILENAME_CONVENTIONS_PATH]`.
- **`confirm_inbox` ONLY when there is genuinely no fit** — no rule, no entity/alias match,
  no parent-folder signal, content too generic to place. Otherwise reroute.
- Distinguish confident reroutes from unsure ones (the unsure go to the human viewer, not
  silent execution):
  - `reroute_high` — you are confident of the destination; it can be applied directly.
  - `reroute_low` — a destination is plausible but not certain; surface it in the viewer for
    the user to confirm rather than moving it silently.

## Your batch (the _Inbox-routed files to re-judge)
[INBOX_BATCH_JSON]
<!-- list of {id, filename, current_path, file_date, is_image, is_raw} — exactly the fields
     `organizer.py inbox-list` emits. `is_image` uses IMAGE_EXTS only (NOT IMAGE_EXTS ∪ RAW_EXTS)
     — RAW files are presented with is_image: false. `is_raw` is the separate RAW flag. Use
     `is_image` and `is_raw` to apply the vision/peek capability gates instead of re-deriving
     from the extension. For reroute_high/reroute_low verdicts, carry `file_date` through from
     the input record into the approved entry so cmd_execute can update the destination
     project's date_range.
     NOTE: `is_image` semantics here differ intentionally from the propose fan-out — see
     `references/file-type-routing.md` "Images and Camera RAW" for the full explanation. In the
     arbiter feed (this template), `is_image=False` for RAW files so the single flag encodes
     vision-readability; in propose, `is_image=True` for RAW (paired with `is_raw`) because the
     RAW-never-vision block is applied as a separate gate. -->

## Output — return EXACTLY this JSON array, one object per input id, nothing else
```json
[
  {
    "id": 0,
    "verdict": "confirm_inbox|reroute_high|reroute_low",
    "para_subfolder": "<destination if reroute_*, else _Inbox>",
    "new_filename": "<clean name per conventions if rerouting, else omit>",
    "reason": "<one line: why it is truly ambiguous, or what the first pass / earlier round missed>"
  }
]
<!-- NOTE: `current_path` is NOT emitted by the arbiter in its verdict — it is carried
     through from the input batch record (the `current_path` field in [INBOX_BATCH_JSON]).
     The orchestrator must propagate `current_path` from input to approved entry so
     `cmd_execute` can locate the file. -->
```
Every input `id` appears exactly once. `verdict` is **exactly one of** `confirm_inbox` / `reroute_high` / `reroute_low` — a closed set; emit no other value. Do not emit `para_category`. Verdicts only.

---

## When + how the orchestrator runs the sweep (SKILL.md's `propose` points here)

`_Inbox/` is where files with no fit land. Because the rule set grows as you organise, files
inboxed earlier often become placeable later. **When the registry's `_Inbox/` population reaches
~100 files** (check `organizer.py inbox-list` → `count`), run a reclamation sweep over **all** of
them (not just this round's). The `~100` is a soft batching guideline, not a hard gate: the sweep is
correct at any count — `~100` simply amortizes dispatch into ceil(count/25) parallel arbiters of 25 (≈4 at ~100 — illustrative; 5 at 101–125, etc.). Re-judging
files a prior sweep returned `confirm_inbox` is **intentional**: `confirm_inbox` means "unplaceable
under the rules that existed *then*", and the rule set has grown since — re-judging is how such a
file gets placed once a fitting rule exists, so the sweep carries no "already-arbitrated" marker that
would freeze a file in `_Inbox/` forever.

- Get the list: `organizer.py inbox-list` → `{count, files:[{id, filename, current_path, file_date, is_image, is_raw}]}`. (`count`
  is the number of files already **executed** into `_Inbox/` — rows with `status='organized'` and a
  `_Inbox` path; files merely classified-to-`_Inbox` this round but not yet executed don't count.)
  Fill the arbiter batch directly from those records into `[INBOX_BATCH_JSON]` — `inbox-list` emits
  exactly the fields this template expects. Split `files` into batches of ≤25 (so ~4 arbiters at 100)
  and dispatch one arbiter per batch **in parallel**, each filled from this template — including its
  `[CAPABILITIES]` slot, filled from propose's `Model capabilities: peek=… vision=…` stderr line
  exactly as the classify fan-out does, so arbiters under a no-vision / no-peek model degrade the same
  way (route by name/path + EXIF, never open files they can't); its `[GROUPINGS]` slot, filled
  from `organizer.py rules --json` → the top-level `areas` array (the resolved active groupings,
  same source as the classify fan-out — do NOT read `templates` `Q1_groupings` here, since it does
  not apply the separate `config.json "areas"` freeze-override); and its
  `[TEMPLATES_CMD]` slot, filled with `python3 ~/.claude/drive-organizer/organizer.py templates`
  (the merged-taxonomy command — same as the classify fan-out; the arbiter reads the taxonomy to
  re-judge files against the current category structure). Note: the
  classify fan-out's reading list (`references/classify-prompt.md`, the "Read these yourself for the
  taxonomy + logic" section) is broader than the arbiter's — it also covers on-disk rules,
  dated-destination metadata, entity policy-driven routing, the cascading-Q model detail, and the
  glossary; the arbiter's reading list above covers what re-judging inboxed files requires (taxonomy,
  rules, entities, file-type routing + the tidy-builtin fall-through bucket, filename conventions).
- Each arbiter re-judges its files against the *current* taxonomy and returns the verdict object above.
- Apply: `confirm_inbox` → leave in `_Inbox/` (no entry written; no `action` field needed);
  `reroute_high` → build an approved entry
  (`para_subfolder` = the new destination; `new_filename` = the arbiter's clean name when it returned
  one, else omit so execute keeps the current filename; `current_path` = the file's `current_path`
  from the `inbox-list` batch record — this field is required by `execute` to locate the file on
  disk and must be carried through from the input, since the arbiter verdict does not return it;
  `file_date` = carry through from the input batch record's `file_date` field (source: `inbox-list` → `files[*].file_date`) — this is required so `cmd_execute` can call `_expand_date_range` on the destination project; omitting it silently skips date_range widening for arbiter reroutes;
  `action` = `"approved"` (set this field explicitly on every reroute_high entry — it is a required field of the entry, not optional). WHY required: arbiter entries bypass the viewer entirely, so `action: "approved"` is the only audit signal distinguishing them from viewer-approved entries, and every arbiter run must emit the same shape. Never carry `verdict` as-is — execute reads `action`, never `verdict`)
  and `execute` it directly; `reroute_low` →
  build a proposals entry (`para_subfolder` = the arbiter's destination; `new_filename` = the
  arbiter's clean name when it returned one, else omit; `current_path` = the file's `current_path`
  from the `inbox-list` batch record — this field is required by `execute` to locate the file on
  disk and must be carried through from the input, since the arbiter verdict does not return it;
  `file_date` = carry through from the input batch record's `file_date` field (source: `inbox-list` → `files[*].file_date`) — same as reroute_high: a reroute_low that clears the viewer reaches execute, and without `file_date` `cmd_execute` silently skips `_expand_date_range` on the destination project;
  no `action` field because this entry goes to the viewer (proposals_classified.json) for user confirmation, not to execute directly; the viewer assigns `action` on submit)
  and add it to the next `proposals_classified.json` so it surfaces in the **viewer** for the user
  to confirm — never moved silently. Re-run `inbox-list` after to confirm the count dropped.
