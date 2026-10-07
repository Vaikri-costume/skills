# ai-detection-check

## What this skill does

Reviews a draft for AI-typical language, over-smooth texture, hedging calibration and citation integrity, and lists the evidence of their own process the writer can show. It reports descriptions and flags for revision, never a verdict on authorship.

- **Authenticity review** — trigger: "does this sound like AI" → steps: metrics, pattern scan, citation and quotation audit, five agents, challengers, report → result: flags for revision plus an evidence checklist.
- **Baseline comparison** — trigger: supply earlier texts → steps: the same descriptive features computed for both → result: ratios as context, with a minimum-length guard.

## Intent

Detectors are unreliable, easy to evade and biased against formal and second-language writing, so this skill is a revision aid, not a detector: no scores, no RED/YELLOW/GREEN on metrics (no published thresholds exist), no claim about authorship, no advice on evasion. The machine-checkable indicators from typical UK misconduct procedures (non-existent quotations, uncited bibliography entries, repeated introductions) are checked by scripts. Pattern lists are perishable and dated.

## When to use / When NOT to use

**Use when:** before submitting an essay where originality of voice matters, or to find passages where specific thinking may be missing.

**Don't use when:** proving or disproving AI authorship (nothing here can); lowering a detector score.

## How to install

Source: `skills/ai-detection-check` in https://github.com/Vaikri-costume/skills. Needs Python 3.

- **Claude Code**: copy the `ai-detection-check/` folder to `~/.claude/skills/ai-detection-check/` (all skills there), or to a project's `.claude/skills/ai-detection-check/` (that project only). Claude finds it automatically.
- **Cowork / claude.ai**: upload the folder as a skill. The review runs several parallel reviewer agents, so it works best where subagents are available.
- **Model notes**: smoke-tested on Haiku, Sonnet and Opus with an invented essay. Sonnet and Opus give the fullest reports; Haiku completes the run but writes a more condensed report and is less careful about stating what could not be checked, so prefer Sonnet or Opus for anything you will rely on.

## How to invoke

`/ai-detection-check [draft path]`; "does this sound like AI", "too polished", "too formulaic".

Example: `/ai-detection-check essay.md` -> optionally supply earlier texts for a baseline and `LABEL=PATH` sources -> the report lists descriptive metrics, flags for revision and an evidence checklist.

Needs Python 3 for the scripts. Run the tests with `python3 -m unittest discover -s ${CLAUDE_SKILL_DIR}/scripts/tests` (and `${CLAUDE_SKILL_DIR}/scripts/shared/tests` for the shared scripts).

## Sibling skills

- `proofread`: errors (grammar, spelling, consistency, register); run it after revising for flags raised here.
- `review-writing`: argument, evidence, clarity, voice; pairs with the voice flags here.
- `plagiarism-check`: overlap with sources, patchwriting, full citation integrity; this skill's citation checks are only a light signal.

## For developers

- `SKILL.md`: runtime instructions; `references/` holds the detail.
- `HISTORY.md`: changelog and lineage.
- Build, trace and ship tooling: `skill-creator-ccvw`, `skill-tracer` and `skill-publisher` in https://github.com/Vaikri-costume/skills.
