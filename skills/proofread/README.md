# proofread

## What this skill does

Proofreads a draft in strict British English: grammar, typos, spelling, consistency, and register quality, with an optional canonical-terms file for project vocabulary (transliterations, names).

- **Pre-submission proofread** — trigger: "proofread this" → steps: spelling and consistency prescans, six read-only proofreaders, challenger, report → result: findings by location and type with quick wins.
- **Vocabulary check** — trigger: proofread with a terms file → steps: unrecognised terms looked up in the file, near-misses reported, new terms added only after confirmation → result: consistent project spellings.

## Intent

Strict British `-ise` (decided 2026-10-04): every `-ize`/`-ization`/`-yze` form is an error except words spelt `-ize` in every system (size, prize, seize, capsize, maize). Prefer the other standard British spellings. Searching is deterministic (scripts with tests); judgement about intent (consistency, register) is left to agents and a challenger; nothing is silently corrected. Quoted source spelling is never touched.

## When to use / When NOT to use

**Use when:** a draft to check for errors before submission or during revision.

**Don't use when:** argument or structure feedback (use review-writing).

## How to install

Source: `skills/proofread` in https://github.com/Vaikri-costume/skills. Needs Python 3.

- **Claude Code**: copy the `proofread/` folder to `~/.claude/skills/proofread/` (all skills there), or to a project's `.claude/skills/proofread/` (that project only). Claude finds it automatically.
- **Cowork / claude.ai**: upload the folder as a skill. The review runs several parallel reviewer agents, so it works best where subagents are available.
- **Model notes**: smoke-tested on Haiku, Sonnet and Opus with an invented essay. Sonnet and Opus give the fullest reports; Haiku completes the run but writes a more condensed report and is less careful about stating what could not be checked, so prefer Sonnet or Opus for anything you will rely on.

## How to invoke

`/proofread [draft path]`; "proofread this", "check my British spelling", "check grammar".

Worked example: say "proofread essay.md, it's a research essay". The skill runs the prescans, six read-only reviewers and a challenger, then returns findings by location and type with quick wins. Nothing in your draft is changed.

Needs Python 3 for the scripts. Run the tests with `python3 -m unittest discover -s ${CLAUDE_SKILL_DIR}/scripts/tests` (and `${CLAUDE_SKILL_DIR}/scripts/shared/tests` for the shared scripts).

## Sibling skills

- `review-writing`: pairs after proofreading, for argument, evidence, clarity, voice.
- `plagiarism-check`: pairs as a separate pass for overlap with sources, patchwriting, citation integrity.
- `ai-detection-check`: pairs as a separate pass for authenticity review; not a detector.

## For developers

See `SKILL.md` for the run steps and `HISTORY.md` for changelog and lineage. Build, trace and ship with `skill-creator-ccvw`, `skill-tracer` and `skill-publisher` in https://github.com/Vaikri-costume/skills.
