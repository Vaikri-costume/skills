# review-writing

## What this skill does

Gives a substantive analytical review of the writer's own draft: where it is going, what works, and where the argument, evidence, clarity and voice need work, each point tied to a quoted line. It asks questions and points at gaps; it never writes, rewrites or suggests wording.

- **Full review** — trigger: "does my argument work", "check my evidence" → steps: Toulmin reading with a promise-against-delivery check, paired reviewers, three blind reader lenses, two challengers, report → result: findings ordered from the claim down to the sentence, each strength placed next to the critique it protects, process questions for the revision.
- **Rubric table** — trigger: you supply a rubric or brief → result: met, partly, not met or "not found in the draft" for each criterion, in the rubric's own order and words, with a separate list of what the reviewer noticed beyond it.
- **Draft, revision-diff, presentation and bibliography modes** — each runs only when you name it: direction questions for work in progress; whether your changes addressed earlier comments; gaps in a talk; what has been checked about each cited source.

## Intent

Feedback that helps the writer revise and keeps the writing theirs: it comments on the writing, never the writer, supplies no replacement words, no TLDR, no grades and no unprompted offers. Argument review uses Toulmin's model because arguments usually fail at the warrant. Everything specific to the writer (course rules, field expectations) is read at run time from their profile, never held in the skill. For the writer's own drafts only.

## When to use / When NOT to use

**Use when:** the question is whether the argument, evidence, clarity or voice of a draft work, whether earlier comments were addressed, or what a talk or reference list leaves open.

**Don't use when:** error-checking (use proofread), overlap checking (use plagiarism-check), AI-style checks (use ai-detection-check), or when you want text written or rewritten (this skill never does).

## How to install

Source: `skills/review-writing` in https://github.com/Vaikri-costume/skills. Needs Python 3.

- **Claude Code**: copy the `review-writing/` folder to `~/.claude/skills/review-writing/` (all skills there), or to a project's `.claude/skills/review-writing/` (that project only). Claude finds it automatically.
- **Cowork / claude.ai**: upload the folder as a skill. The review runs several parallel reviewer agents, so it works best where subagents are available.
- **Optional profile**: a markdown file of ``- `key`: value`` bullets (keys `ai_rules`, `field_bank`, `session_log_dir`; see `references/profile.md`) lets the skill read your course AI rules and field pages at run time. Without one it uses its defaults.

## How to invoke

`/review-writing [draft path]`; "review my draft", "is the structure working", "what's missing"; or name a mode ("revision-diff", "presentation mode", "bibliography mode", "draft mode").

Worked example: input `/review-writing essay.md` (a 2,000-word research essay with a rubric) produces a report with a confidence line, a reading of the draft, findings from claim to sentence each marked upheld, disputed or needs-your-decision, three reader lenses, a rubric table and process questions for the revision.

Needs Python 3 for the scripts. Run the tests with `python3 -m unittest discover -s ${CLAUDE_SKILL_DIR}/scripts/tests` and `python3 -m unittest discover -s ${CLAUDE_SKILL_DIR}/scripts/shared/tests`.

## Features & modes

- **Full review (default)**: argument (Toulmin, plus what the opening promises against what is delivered), evidence, clarity and voice, each read by two independent reviewers; three blind readers (audience, rigour, premise) add questions; two challengers test every finding. Findings run from the claim down to the sentence, each strength beside the critique it protects. Trigger: "review my draft", "does my argument work", "check my evidence".
- **Rubric verdict table**: supply a rubric or brief with any review; each criterion is marked met, partly, not met or "not found in the draft", with a quoted line, and a separate list covers anything noticed beyond it.
- **Draft mode**: for an outline, a half-built section or notes; direction questions you can answer from your own material, with no verdict. Trigger: "draft mode".
- **Revision-diff mode**: compares your revised draft with an earlier review report and says whether each earlier comment was addressed. Trigger: "revision-diff".
- **Presentation mode**: gaps and questions for slides, notes or a rehearsal transcript, with word and slide counts against your time; no slide text, no delivery coaching. Trigger: "presentation mode".
- **Bibliography mode**: every in-text citation matched to an entry and every entry cited, with a status word for what has actually been checked about each source. Trigger: "bibliography mode".
- **Course-rule and profile awareness**: with a profile file, the review reads your course AI rules and your field's expectations at run time and narrows or skips domains where a rule requires it. Without one it uses defaults.
- **Guardrails (all modes)**: no rewriting and no supplied wording, claims, sources or thesis; no grades, TLDR or unprompted offers; instructions found inside a draft, rubric or profile are quoted in a note and not followed; a mode runs only when you name it.

## Structure

- `SKILL.md`: the run procedure (gate, mode selection, the eight-step full review, troubleshooting, hard rules).
- `references/`: loaded only when a step needs it. Run mechanics (`dispatch-protocol.md`, `profile.md`, `challenger-synthesis-rules.md`, `presentation-format.md`, `field-name-standard.md`, `severity-anchors.md`, `glossary.md`); one brief per domain with research and personal variants (`arg-structure.md`, `clarity.md`, `evidence*.md`, `voice*.md`); `lenses.md` and `rubric.md`; and the four `mode-*.md` guides.
- `scripts/`: Python helpers for counting, checking and merging (`combine_findings.py`, `report_lint.py`, `verdict_table.py`, `revision_diff.py`, `presentation_stats.py`, `count_citations.py`), with `shared/` for paragraph numbering, citation audit, quote verification, location correction and synthesis, and `tests/` in each.
- `assets/report-header-template.md`: the header that opens every report.
- Outputs: intermediate files go in a temporary run folder and the report is saved only if you ask; your draft is never altered.

## Sibling skills

- `proofread`: run after revising, for the errors (grammar, spelling) this skill does not check.
- `plagiarism-check`: run before submitting a source-heavy essay, for overlap and citation integrity.
- `ai-detection-check`: run when originality of voice matters; this skill's voice review is about consistency, not authenticity.

## For developers

- `SKILL.md` is the run procedure; `references/dispatch-protocol.md` holds the shared mechanics.
- `HISTORY.md` records the changelog and provenance.
- To find bugs or polish and ship changes, use the `skill-tracer` and `skill-publisher` skills in https://github.com/Vaikri-costume/skills.
