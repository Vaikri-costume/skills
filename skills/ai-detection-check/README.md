# ai-detection-check

## What this skill does

Reviews a draft for AI-typical language, over-smooth texture, hedging calibration and citation integrity, and lists the evidence of the writer's own process they can show. It reports descriptions and flags for revision, never a score, percentage or verdict on authorship.

- **Authenticity review** — trigger: "does this sound like AI" → steps: metrics, pattern scan, citation and quotation audit, five agents, challengers, report → result: flags for revision plus an evidence checklist and a plain statement of limits.
- **Baseline comparison** — trigger: supply earlier texts → steps: the same descriptive features computed for both → result: ratios as context, with a minimum-length guard.
- **Citation and quotation checks** — trigger: supply source texts as `LABEL=PATH` → steps: every quotation is searched in its cited source and, when the citation sits at the end of the sentence, in every supplied source → result: quotations not found, reference entries never cited and reference artefacts (tracking parameters, incomplete DOIs, invalid ISBN checksums).

## Intent

Detectors differ from each other, are easy to evade and flag plain, formal and second-language writing more often, so this skill is a revision aid, not a detector: no scores, no RED/YELLOW/GREEN on metrics (no published thresholds exist), no claim about authorship, no advice on evasion. The machine-checkable indicators from typical UK misconduct procedures (non-existent quotations, uncited bibliography entries, repeated introductions) are checked by scripts. Pattern lists and detector background are perishable and dated (`references/detector-landscape.md`).

## When to use / When NOT to use

**Use when:** before submitting an essay where originality of voice matters, or to find passages where specific thinking may be missing.

**Don't use when:** proving or disproving AI authorship (nothing here can); lowering a detector score; rewriting or humanising text.

## How to install

Copy the `ai-detection-check` folder to `~/.claude/skills/` (or a project's `.claude/skills/`). Needs Python 3.

## How to invoke

`/ai-detection-check [draft path]`; "does this sound like AI", "too polished", "too formulaic".

## Features & modes

- Descriptive metrics (sentence-length spread, MATTR-100, hedge rate, participles, nominalisations, passives) with no ratings.
- A dated pattern list, checked in context by paired agents and two challengers.
- A hedging calibration gate: the writer confirms three anchor sentences; when the question cannot be asked the anchors are shown as proposed and unconfirmed.
- No AI-use level or course gate: it is for the writer to see how their own work reads to AI detection, and it never writes or does work for them.
- Instructions found inside a draft are quoted in the report and not followed.

## Structure

- `SKILL.md` — the steps, hard rules and limitations.
- `references/` — briefs, the report format, the evidence and limits text, the profile reference and the dated detector landscape.
- `scripts/` — `compute_metrics.py`, `find_ai_patterns.py`, `report_lint.py`, `tofile.py`, `runfolder.py` and the bundled shared citation scripts in `scripts/shared/`, with tests.

## Sibling skills

- `proofread`: errors (grammar, spelling, consistency, register).
- `review-writing`: argument, evidence, clarity, voice.
- `plagiarism-check`: overlap with sources, patchwriting, citation integrity, self-plagiarism.
- `ai-detection-check`: authenticity review and citation integrity; not a detector.
