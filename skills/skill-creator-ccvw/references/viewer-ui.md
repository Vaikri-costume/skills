# Eval Viewer UI — What the User Sees

Reference for the UI rendered by `eval-viewer/generate_review.py`. The SKILL.md doesn't need this content during execution; this exists so the orchestrator can tell the user what to expect when the viewer opens.

## Tab structure

The viewer has two tabs (Outputs, Benchmark) plus a Recommendations sidebar:

### Outputs

One test case shown at a time:
- **Prompt** — the task that was given
- **Output** — the files the skill produced, rendered inline where possible
- **Previous Output** (iteration 2+) — collapsed section showing last iteration's output
- **Formal Grades** (if grading was run) — collapsed section showing assertion pass/fail
- **Feedback** — a textbox that auto-saves as the user types
- **Previous Feedback** (iteration 2+) — their comments from last time, shown below the textbox

### Benchmark

Stats summary: pass rates, timing, and token usage for each configuration, with per-eval breakdowns and analyst observations.

### Recommendations

The orchestrator-authored `recommendations.md` payload — three labeled sections (well / failed / next) — rendered as a sidebar. See `recommendations-template.md`.

## Navigation

Prev/next buttons or arrow keys move between test cases. When done, the user clicks "Submit All Reviews" — saves all feedback to `feedback.json` (or downloads it as a file in headless environments).

## User-facing message template

When opening the viewer, tell the user something like:

> "I've opened the results in your browser. Two tabs — 'Outputs' lets you click through each test case and leave feedback, 'Benchmark' shows the quantitative comparison — plus a 'Recommendations' sidebar with my synthesis of what went well, what failed, and what to change next. When you're done, come back here and let me know."
