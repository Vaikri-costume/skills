# review-writing

## What this skill does

Gives a substantive analytical review of a draft in four domains (argument structure, clarity, evidence, voice) as feed up, feed back and feed forward, adapted to research, personal and application essays.

- **Argument review** — trigger: "does my argument work" → steps: Toulmin reading of claims, grounds and warrants, pairs of agents, challengers, report → result: weakest warrants first, with next steps.
- **Evidence and quote integration** — trigger: "check my evidence" → steps: citation inventory by script, evidence agents → result: unsupported claims, floating quotes, argumentative substitution.

## Intent

Feedback that helps the writer revise: where the draft is going, what works, where it needs work, and up to three process-level next steps, always about the writing and never the writer. Argument review uses Toulmin's model because arguments usually fail at the warrant. Severity words are anchored, not graded. For the writer's own drafts only.

## When to use / When NOT to use

**Use when:** a draft where the question is whether the argument, evidence, clarity or voice work.

**Don't use when:** error-checking (use proofread) or overlap checking (use plagiarism-check).

## How to install

Source: `skills/review-writing` in https://github.com/Vaikri-costume/skills. Needs Python 3.

- **Claude Code**: copy the `review-writing/` folder to `~/.claude/skills/review-writing/` (all skills there), or to a project's `.claude/skills/review-writing/` (that project only). Claude finds it automatically.
- **Cowork / claude.ai**: upload the folder as a skill. The review runs several parallel reviewer agents, so it works best where subagents are available.
- **Model notes**: smoke-tested on Haiku, Sonnet and Opus with an invented essay. Sonnet and Opus give the fullest reports; Haiku completes the run but writes a more condensed report and is less careful about stating what could not be checked, so prefer Sonnet or Opus for anything you will rely on.

## How to invoke

`/review-writing [draft path]`; "review my draft", "is the structure working", "what's missing".

Worked example: input `/review-writing essay.md` (a 2,000-word research essay) produces a report with a reading of the draft, the strongest points, findings by domain (argument, evidence, clarity, voice) each marked upheld, disputed or needs-your-decision, and up to three next steps.

Needs Python 3 for the scripts. Run the tests with `python3 -m unittest discover -s ${CLAUDE_SKILL_DIR}/scripts/shared/tests`.

## Sibling skills

- `proofread`: run after revising, for the errors (grammar, spelling) this skill does not check.
- `plagiarism-check`: run before submitting a source-heavy essay, for overlap and citation integrity.
- `ai-detection-check`: run when originality of voice matters; this skill's voice review is about consistency, not authenticity.

## For developers

- `SKILL.md` is the run procedure; `references/dispatch-protocol.md` holds the shared mechanics.
- `HISTORY.md` records the changelog and provenance.
- To find bugs or polish and ship changes, use the `skill-tracer` and `skill-publisher` skills in https://github.com/Vaikri-costume/skills.
