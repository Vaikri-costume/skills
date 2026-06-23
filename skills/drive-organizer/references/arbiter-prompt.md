# Inbox Arbiter Prompt — drive-organizer
<!-- The orchestrator fills every [SLOT] and dispatches ONE arbiter per ≤25-file batch.
     PATHS ONLY. This is a periodic _Inbox-reclamation sweep, NOT a per-round step — see
     the "Inbox arbiter sweep" note in SKILL.md's propose section (triggered when the registry's _Inbox population reaches
     ~100 files; the sweep covers ALL _Inbox files, including ones inboxed in earlier rounds,
     because rules learned since then may now place them). Keep light: pointers, not inlines. -->

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
  stderr line — the same slot the classify fan-out uses):
  - **peek ON** — you may open document/text contents (Read) to re-judge.
  - **peek OFF** — classify each document from filename + path + rules only; never open file contents.
  - **vision ON** — you may open images (Read) and describe them.
  - **vision OFF** — route images by filename + path + rules + `organizer.py exif <path>` metadata
    (date/camera/dimensions); never open pixels.
- Read yourself: active groupings `[GROUPINGS]`; merged taxonomy `[TEMPLATES_CMD]`; the
  touched `.tidy-rules.json` under `[ROOT]`; entity aliases/negatives `[ENTITIES_PATH]`;
  cascading-Q + file-type handling `[FILE_TYPE_ROUTING_PATH]`; conventions
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
<!-- list of {id, filename, current_path} — exactly the fields `organizer.py inbox-list`
     emits. Determine image-vs-document yourself from the extension. -->

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
```
Every input `id` appears exactly once. `verdict` is **exactly one of** `confirm_inbox` / `reroute_high` / `reroute_low` — a closed set; emit no other value. Do not emit `para_category`. Verdicts only.

---

## When + how the orchestrator runs the sweep (SKILL.md's `propose` points here)

`_Inbox/` is where files with no fit land. Because the rule set grows as you organise, files
inboxed earlier often become placeable later. **When the registry's `_Inbox/` population reaches
~100 files** (check `organizer.py inbox-list` → `count`), run a reclamation sweep over **all** of
them (not just this round's). The `~100` is a soft batching guideline, not a hard gate: the sweep is
correct at any count — `~100` simply amortizes dispatch into ~4 parallel arbiters of 25. Re-judging
files a prior sweep returned `confirm_inbox` is **intentional**: `confirm_inbox` means "unplaceable
under the rules that existed *then*", and the rule set has grown since — re-judging is how such a
file gets placed once a fitting rule exists, so the sweep carries no "already-arbitrated" marker that
would freeze a file in `_Inbox/` forever.

- Get the list: `organizer.py inbox-list` → `{count, files:[{id, filename, current_path}]}`. (`count`
  is the number of files already **executed** into `_Inbox/` — rows with `status='organized'` and a
  `_Inbox` path; files merely classified-to-`_Inbox` this round but not yet executed don't count.)
  Fill the arbiter batch directly from those records into `[INBOX_BATCH_JSON]` — `inbox-list` emits
  exactly the fields this template expects. Split `files` into batches of ≤25 (so ~4 arbiters at 100)
  and dispatch one arbiter per batch **in parallel**, each filled from this template — including its
  `[CAPABILITIES]` slot, filled from propose's `Model capabilities: peek=… vision=…` stderr line
  exactly as the classify fan-out does, so arbiters under a no-vision / no-peek model degrade the same
  way (route by name/path + EXIF, never open files they can't).
- Each arbiter re-judges its files against the *current* taxonomy and returns the verdict object above.
- Apply: `confirm_inbox` → leave in `_Inbox/`; `reroute_high` → build an approved entry
  (`para_subfolder` = the new destination; `new_filename` = the arbiter's clean name when it returned
  one, else omit so execute keeps the current filename) and `execute` it directly; `reroute_low` →
  add it to the next `proposals_classified.json` so it surfaces in the **viewer** for the user to
  confirm — never moved silently. Re-run `inbox-list` after to confirm the count dropped.
