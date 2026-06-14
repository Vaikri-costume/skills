# Dispatch Protocol

How Step 4 stages prompts, issues the three Agent calls in a single message, and preserves cold-parallel independence. SKILL.md Step 4 owns the dispatch (the three directions — forward, backward, executor — and the per-call parameter table); this reference covers the mechanics that don't change between rounds.

---

## RUN_TIMESTAMP format

The current invocation's `<Runtime>` (per recovery-protocol.md) with **every** `:` character replaced by `-` for filesystem-safe filenames.

Use a global replace, not single — the canonical Runtime format `YYYY-MM-DDTHH:MM` contains one `:`, but a Runtime sourced from a non-conforming clock that includes seconds (`YYYY-MM-DDTHH:MM:SS`) needs all colons replaced.

Examples:
- Runtime `2026-05-27T09:12` → RUN_TIMESTAMP `2026-05-27T09-12`
- Runtime `2026-05-27T09:12:45` → RUN_TIMESTAMP `2026-05-27T09-12-45`

The Runtime value goes into the ledger Runtime column unchanged; the RUN_TIMESTAMP variant is only for filenames where `:` is reserved.

---

## Prompt staging procedure

Before issuing any Agent call, compose all filled prompts (one per direction in this round's `<dispatch-set>`) and write them to scratchpad files. This separates prompt composition (many tokens, prone to serializing) from dispatch (cheap, must be same-turn).

### Canonical: `scripts/stage_cold_prompts.py` (shared stager)

Use the shared stager rather than hand-rolling the substitution — it owns the RUN_TIMESTAMP colon→dash derivation, the all-files-present check, and the no-unsubstituted-slot guard (a leftover `[SLOT]` fails loudly instead of dispatching a half-filled prompt). It is shared with skill-publisher's Step-3 audit staging. Build a spec — one `{label, slots}` entry per direction; **each entry's `label` MUST be exactly the bare direction name (`forward` / `backward` / `executor`)**, because the stager names the output file `<label>-<RUN_TIMESTAMP>.txt` and Step 4's dispatch reads `<direction>-<RUN_TIMESTAMP>.txt` — a `label` that differs (e.g. `Forward`) stages a file the dispatch Read never finds. (Slots map each `[SLOT]` to its value; `[INLINED_TRACE_DEFINITION]` is the verbatim body of `references/<direction>.md`.) Pass it:

```bash
python3 ~/.claude/skills/skill-tracer/scripts/stage_cold_prompts.py \
  --template ~/.claude/skills/skill-tracer/references/prompt-template.md \
  --out-dir /tmp/skill-tracer-prompts \
  --runtime "<Runtime>" \
  --spec /tmp/skill-tracer-prompts/spec.json     # [{label:forward, slots:{...}}, backward, executor]
# writes <direction>-<RUN_TIMESTAMP>.txt; exits non-zero on any unfilled slot or missing file
```

The `--spec` JSON is the only per-round composition work; the stager handles the rest. Exit 0 = all three staged + verified.

### Fallback: inline Bash+Python loop (equivalent, if you prefer not to write a spec file)

Compose all three prompts in one loop and write them in one go:

```bash
mkdir -p /tmp/skill-tracer-prompts && python3 << 'PYEOF'
from pathlib import Path

TEMPLATE = (Path.home() / ".claude/skills/skill-tracer/references/prompt-template.md").read_text()
SKILL_PATH = "<absolute-path-to-target-SKILL.md>"
SKILL_NAME = "<target-skill-name>"
RUN_TIMESTAMP = "<RUN_TIMESTAMP>"  # YYYY-MM-DDTHH-MM derived from current invocation's Runtime per "RUN_TIMESTAMP format" above

FILE_LIST = "<one-absolute-path-per-line-from-Step-2-enumeration>"
GLOSSARY = "<5-15 one-line definitions per Step 3 Glossary precedence procedure, or the literal word 'none'>"
DISPATCH_SET = ["forward", "backward", "executor"]  # constant — skill-tracer's three cold directions

for direction in DISPATCH_SET:
    inlined = (Path.home() / f".claude/skills/skill-tracer/references/{direction}.md").read_text()
    prompt = (TEMPLATE
        .replace("[DIRECTION]", direction)
        .replace("[SKILL_NAME]", SKILL_NAME)
        .replace("[SKILL_PATH]", SKILL_PATH)
        .replace("[FILE_LIST]", FILE_LIST)
        .replace("[GLOSSARY]", GLOSSARY)
        .replace("[INLINED_TRACE_DEFINITION]", inlined))
    out = Path(f"/tmp/skill-tracer-prompts/{direction}-{RUN_TIMESTAMP}.txt")
    out.write_text(prompt)
    print(f"Staged {out.name} ({len(prompt)} chars)")
PYEOF
```

Built-in verification: the loop's `print` lines report each file's character count, providing the `ls` cross-check inline (one tool call output covers what would otherwise be: three Write calls + 1 ls call).

`<dispatch-set>` is the constant `[forward, backward, executor]` every round, so exactly three files are staged each time (see `references/glossary.md` "`<dispatch-set>`" entry).

### Failure handling

If one or more prompt files is missing after staging: re-run the Python loop until all are present. Write errors deterministically; a silent miss indicates a path-permission or disk issue and warrants a one-line note to the user before retrying.

If `stage_cold_prompts.py` exits 1 with an `unfilled` slot list (every file present, but a `[SLOT]` token remained after substitution): a slot value was missing from the spec — do NOT dispatch, since a half-filled prompt would mislead the cold agent. Fill the missing slot and re-run the stager (the `[INLINED_TRACE_DEFINITION]` slot — an unreadable `references/<direction>.md` — is the usual culprit). The `--allow-unfilled` flag exists only for deliberate partial staging and must not be used for a real dispatch.

If `stage_cold_prompts.py` exits **2** (usage error — `--template` or `--spec` not found, or the spec is not valid JSON / not a non-empty list of `{label, slots}`): the *invocation* is malformed, not the content. Check that the `--template` and `--spec` paths exist and the spec is a valid JSON array, fix the invocation, and re-run. Do NOT dispatch.

Do not abort the round and do not advance to dispatch with a partial set — partial dispatch would issue Agent calls referencing scratchpad files that the agent's `Read` would fail on, producing an `ABORTED — missing files` return from a file that exists on disk but not at the named scratchpad path.

---

## Agent dispatch (single-message, N calls)

Once every staged prompt file exists, issue one `Agent` tool call per direction in `<dispatch-set>`, all in a **single assistant message** — one `function_calls` block containing N `tool_use` entries.

All N use `subagent_type: general-purpose`. Each prompt body is short and structurally identical:

```
Read /tmp/skill-tracer-prompts/<direction>-<RUN_TIMESTAMP>.txt and follow the instructions in that file verbatim. Do not improvise. Do not request the orchestrator's context. Your output is the report the file's instructions ask for.
```

(SKILL.md Step 4 contains the description-string table for the three directions.)

---

## Same-turn requirement (load-bearing)

All N Agent calls MUST be in the same assistant message. Do NOT:
- Dispatch one Agent call and wait for its tool_result before issuing the next.
- Split the N dispatches across two or more assistant turns.
- Read any tool_result from the N dispatches before all N have been issued.

**Why.** If you dispatch serially — Agent 1, read its result, then Agent 2 — the orchestrator has knowledge of Agent 1's findings when composing Agent 2's prompt. Even if you don't *intend* to bias Agent 2, your selection of which file to mention first, which glossary terms to include, or how you phrase ambiguities will reflect what Agent 1 found. The cold-parallel property requires the orchestrator to commit to all three prompts simultaneously, without any feedback loop between dispatch and prompt composition: the bias risk grows with each serialized dispatch.

**Why staging makes same-turn easy.** With prompts pre-written to files, each Agent call body is ~150 chars (just the "read this file" instruction). Three short Agent calls fit trivially in one message — the temptation to serialize disappears because there is no per-call composition work left to do at dispatch time.

---

## Self-check + discard-and-retry

If you find yourself reading a tool_result before all N Agent calls have been issued in the same message, you have violated the same-turn rule. The Agent tool offers no cancellation primitive for already-issued calls, so "discard" here means **ignore the partial results** — do not feed them into Step 5, do not record them anywhere.

Recovery procedure:
1. Re-derive `[FILE_LIST]` (re-run Step 2's `find` if it's been lost from context).
2. Re-determine `<dispatch-set>` — it is the constant `[forward, backward, executor]` every round (no per-round variation; see "Why exactly three directions" below and glossary.md's `<dispatch-set>` entry).
3. Re-build all N prompts from scratch (overwrite the scratchpad files).
4. Issue all N Agent calls in one fresh assistant message.

The in-flight marker (already `dispatch round-N` from atomic-write) remains correct — only the prompts are rewritten, not the marker. If the session crashes between the retry's dispatch and recording its results, the next invocation's recovery rule 1 will correctly scan the JSONL for the retry's dispatch (not the discarded one — the discarded dispatch's tool_uses are still in the JSONL but recovery rule 1 finds the most-recent matching descriptions, which will be the retry's).

After all N dispatches are issued in the same message, wait for all N tool_results to come back (they run in parallel).

---

## Why exactly three directions (forward, backward, executor)

skill-tracer dispatches the same three cold directions every round — they're the correctness core: forward catches claim/reality drift, backward catches producer/consumer gaps, executor catches line-by-line ambiguity. Together they cover the ways a skill's runtime workflow can be wrong.

Earlier versions also ran cadenced directions (efficiency, accessibility) and a simplify-only direction (security). Those moved out in the three-skill refactor: efficiency + accessibility are quality concerns the builder (skill-creator-ccvw) handles during iteration; security is a ship-time concern the publisher (skill-publisher) runs once before release. skill-tracer is correctness-only — three directions, every round, no cadence, no override flags.
