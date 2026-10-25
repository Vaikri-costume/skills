# JSON Schemas

This document defines the JSON schemas used by skill-creator.

## Table of contents

- [evals.json](#evalsjson)
- [history.json](#historyjson-legacy--not-produced-by-the-current-workflow) (legacy)
- [grading.json](#gradingjson)
- [metrics.json](#metricsjson)
- [timing.json](#timingjson)
- [benchmark.json](#benchmarkjson)
- [comparison.json](#comparisonjson)
- [analysis.json](#analysisjson)
- [eval_metadata.json](#eval_metadatajson)
- [results.json](#resultsjson)

---

## evals.json

Defines the evals for a skill. Located at `evals/evals.json` within the skill directory.

```json
{
  "skill_name": "example-skill",
  "evals": [
    {
      "id": 0,
      "prompt": "User's example prompt",
      "expected_output": "Description of expected result",
      "files": ["evals/files/sample1.pdf"],
      "expectations": [
        "The output includes X",
        "The skill used script Y"
      ]
    }
  ]
}
```

**Fields:**
- `skill_name`: Name matching the skill's frontmatter
- `evals[].id`: Unique integer identifier; the ids are consecutive integers starting at 0, because the pilot is eval 0 (`scripts/eval_workspace.py` with `--only 0`, `references/eval-run-procedure.md` Step 1 (Spawn each test case's runs))
- `evals[].name`: Optional descriptive name, used in the eval's `eval-<name>/` folder (`scripts/eval_workspace.py`). It must be a lowercase slug: letters, digits and hyphens, at most 61 characters, starting with a letter or digit, and unique within the file. When absent, the script uses a slug of the prompt (first 40 characters), so give a name whenever the prompt would not make a clear one.
- `evals[].prompt`: The task to execute
- `evals[].expected_output`: Human-readable description of success
- `evals[].files`: Optional list of input file paths (relative to skill root)
- `evals[].expectations`: List of verifiable statements
- `evals[].fixtures`, `evals[].copy_fixture`, `evals[].input_files` (this skill's own evals): fixture folders or files live under `evals/fixtures-workspace/` (a folder name ending in -workspace, so skill-tracer does not read the fixtures as this skill's own documentation) and are written relative to the skill root; a run resolves them against the skill root, and `evals/graders.py` takes the resolved folder through its `--fixtures` argument.
- `check_set`, `persona`, `intent_words`, and the `skill_out` and `run_dir` placeholders (this skill's own evals): this skill grades its own evals with `evals/graders.py`, a scripted grader used in place of the grader subagent. It is run as `python3 evals/graders.py --check-set <check_set> --skill-dir <built skill folder> --run-dir <run folder>`, adding `--persona` once per persona string, `--intent-word` once per intent word, and `--fixtures` with the resolved fixtures folder when the entry has one; it writes grading.json into the run folder. The name field follows the `evals[].name` rule above, and the round field is the eval round the entry was added in. Before rendering a prompt, the orchestrator replaces `{run_dir}` with the run's folder and `{skill_out}` with a folder inside it, such as its outputs folder (the dispatch templates keep the worker inside its run folder), in the prompt and input_files values: `scripts/render_prompt.py` fills only the template's own placeholders, not placeholders inside a value. For an entry with `copy_fixture`, the orchestrator copies that folder into the `skill_out` folder under the same folder name before dispatch, so the worker edits the copy and never the fixture.

---

## history.json (legacy — not produced by the current workflow)

**Note:** no current script writes or reads `history.json`. The improve workflow tracks version progression in HISTORY.md frontmatter + the `productivity:task-management` TASKS.md (see `improve-existing-skill.md`); this schema is retained for reference only. Originally: tracked version progression in Improve mode, located at workspace root.

```json
{
  "started_at": "2026-01-15T10:30:00Z",
  "skill_name": "pdf",
  "current_best": "v2",
  "iterations": [
    {
      "version": "v0",
      "parent": null,
      "expectation_pass_rate": 0.65,
      "grading_result": "baseline",
      "is_current_best": false
    },
    {
      "version": "v1",
      "parent": "v0",
      "expectation_pass_rate": 0.75,
      "grading_result": "won",
      "is_current_best": false
    },
    {
      "version": "v2",
      "parent": "v1",
      "expectation_pass_rate": 0.85,
      "grading_result": "won",
      "is_current_best": true
    }
  ]
}
```

**Fields:**
- `started_at`: ISO timestamp of when improvement started
- `skill_name`: Name of the skill being improved
- `current_best`: Version identifier of the best performer
- `iterations[].version`: Version identifier (v0, v1, ...)
- `iterations[].parent`: Parent version this was derived from
- `iterations[].expectation_pass_rate`: Pass rate from grading
- `iterations[].grading_result`: "baseline", "won", "lost", or "tie"
- `iterations[].is_current_best`: Whether this is the current best version

---

## grading.json

Output from the grader agent. Located at `<run-dir>/grading.json`.

```json
{
  "expectations": [
    {
      "text": "The output includes the name 'John Smith'",
      "passed": true,
      "evidence": "Found in transcript Step 3: 'Extracted names: John Smith, Sarah Johnson'"
    },
    {
      "text": "The spreadsheet has a SUM formula in cell B10",
      "passed": false,
      "evidence": "No spreadsheet was created. The output was a text file."
    },
    {
      "text": "The output file is saved as a CSV",
      "passed": true,
      "evidence": "outputs/results.csv exists and parses as comma-separated values"
    }
  ],
  "summary": {
    "passed": 2,
    "failed": 1,
    "total": 3,
    "pass_rate": 0.67
  },
  "execution_metrics": {
    "tool_calls": {
      "Read": 5,
      "Write": 2,
      "Bash": 8
    },
    "total_tool_calls": 15,
    "total_steps": 6,
    "errors_encountered": 0,
    "output_chars": 12450,
    "transcript_chars": 3200
  },
  "timing": {
    "executor_duration_seconds": 165.0,
    "grader_duration_seconds": 26.0,
    "total_duration_seconds": 191.0
  },
  "claims": [
    {
      "claim": "The form has 12 fillable fields",
      "type": "factual",
      "verified": true,
      "evidence": "Counted 12 fields in field_info.json"
    }
  ],
  "user_notes_summary": {
    "uncertainties": ["Used 2023 data, may be stale"],
    "needs_review": [],
    "workarounds": ["Fell back to text overlay for non-fillable fields"]
  },
  "eval_feedback": {
    "suggestions": [
      {
        "assertion": "The output includes the name 'John Smith'",
        "reason": "A hallucinated document that mentions the name would also pass"
      }
    ],
    "overall": "Assertions check presence but not correctness."
  }
}
```

**Fields:**
- `expectations[]`: Graded expectations with evidence
- `summary`: Aggregate pass/fail counts
- `execution_metrics`: Tool usage and output size (from executor's metrics.json)
- `timing`: Wall clock timing (from timing.json)
- `claims`: Extracted and verified claims from the output; each claim's `type` field is one of `"factual"`, `"process"`, or `"quality"` — these three are the only valid values
- `user_notes_summary`: Issues flagged by the executor
- `eval_feedback`: (optional) Improvement suggestions for the evals, only present when the grader identifies issues worth raising

---

## metrics.json

Output from the executor agent. Located at `<run-dir>/outputs/metrics.json`.

```json
{
  "tool_calls": {
    "Read": 5,
    "Write": 2,
    "Bash": 8,
    "Edit": 1,
    "Glob": 2,
    "Grep": 0
  },
  "total_tool_calls": 18,
  "total_steps": 6,
  "files_created": ["filled_form.pdf", "field_values.json"],
  "errors_encountered": 0,
  "output_chars": 12450,
  "transcript_chars": 3200
}
```

**Fields:**
- `tool_calls`: Count per tool type
- `total_tool_calls`: Sum of all tool calls
- `total_steps`: Number of major execution steps
- `files_created`: List of output files created
- `errors_encountered`: Number of errors during execution
- `output_chars`: Total character count of output files
- `transcript_chars`: Character count of transcript

---

## timing.json

Wall clock timing for a run. Located at `<run-dir>/timing.json`. The orchestrator writes only the first three fields (`total_tokens`, `duration_ms`, `total_duration_seconds`) from the task-completion notification (`references/eval-run-procedure.md` "Step 3: As runs complete, capture timing data"); the `executor_*`/`grader_*` start/end/duration fields below are OPTIONAL — the grader records those into `grading.json`'s `timing` block, not this raw file. `aggregate_benchmark` reads only `total_duration_seconds` + `total_tokens` from `timing.json`, so the minimal three-field form is sufficient.

**How to capture:** When a subagent task completes, the task notification includes `total_tokens` and `duration_ms`. Save these immediately — they are not persisted anywhere else and cannot be recovered after the fact.

```json
{
  "total_tokens": 84852,
  "duration_ms": 23332,
  "total_duration_seconds": 23.3,
  "executor_start": "2026-01-15T10:30:00Z",
  "executor_end": "2026-01-15T10:32:45Z",
  "executor_duration_seconds": 165.0,
  "grader_start": "2026-01-15T10:32:46Z",
  "grader_end": "2026-01-15T10:33:12Z",
  "grader_duration_seconds": 26.0
}
```

---

## benchmark.json

Output from Benchmark mode. Located at `<workspace>/iteration-N/benchmark.json` (the centralized eval ledger — `aggregate_benchmark` writes it into whatever `<benchmark_dir>` you pass, which the workflow sets to `<workspace>/iteration-N`).

```json
{
  "metadata": {
    "skill_name": "pdf",
    "skill_path": "/path/to/pdf",
    "executor_model": "claude-sonnet-4-20250514",
    "analyzer_model": "claude-sonnet-4-20250514",
    "timestamp": "2026-01-15T10:30:00Z",
    "evals_run": [0, 1, 2],
    "runs_per_configuration": 3
  },

  "runs": [
    {
      "eval_id": 1,
      "eval_name": "Ocean",
      "configuration": "with_skill",
      "run_number": 1,
      "result": {
        "pass_rate": 0.85,
        "passed": 6,
        "failed": 1,
        "total": 7,
        "time_seconds": 42.5,
        "tokens": 3800,
        "tool_calls": 18,
        "errors": 0
      },
      "expectations": [
        {"text": "...", "passed": true, "evidence": "..."}
      ],
      "notes": [
        "Used 2023 data, may be stale",
        "Fell back to text overlay for non-fillable fields"
      ]
    }
  ],

  "run_summary": {
    "with_skill": {
      "pass_rate": {"mean": 0.85, "stddev": 0.05, "min": 0.80, "max": 0.90},
      "time_seconds": {"mean": 45.0, "stddev": 12.0, "min": 32.0, "max": 58.0},
      "tokens": {"mean": 3800, "stddev": 400, "min": 3200, "max": 4100}
    },
    "without_skill": {
      "pass_rate": {"mean": 0.35, "stddev": 0.08, "min": 0.28, "max": 0.45},
      "time_seconds": {"mean": 32.0, "stddev": 8.0, "min": 24.0, "max": 42.0},
      "tokens": {"mean": 2100, "stddev": 300, "min": 1800, "max": 2500}
    },
    "delta": {
      "pass_rate": "+0.50",
      "time_seconds": "+13.0",
      "tokens": "+1700"
    }
  },

  "notes": [
    "Assertion 'Output is a PDF file' passes 100% in both configurations - may not differentiate skill value",
    "Eval 3 shows high variance (50% ± 40% pass rate across its with-skill runs; run 2 failed three assertions the other runs passed)",
    "Without-skill runs consistently fail on table extraction expectations",
    "Time cost concentrates in eval 2: its with-skill runs take about 3x as long as its baseline runs while the other evals stay within 10%"
  ]
}
```

**Fields:**
- `metadata`: Information about the benchmark run
  - `skill_name`: Name of the skill
  - `timestamp`: When the benchmark was run
  - `evals_run`: List of eval names or IDs
  - `runs_per_configuration`: Number of runs per config (e.g. 3)
- `runs[]`: Individual run results
  - `eval_id`: Numeric eval identifier
  - `eval_name`: Human-readable eval name (used as section header in the viewer); may be `null` when `eval_metadata.json` is absent — the viewer falls back to "Eval N"
  - `configuration`: the config dir name used by the run. Typically one of `"with_skill"` / `"without_skill"` (create-mode) or `"with_skill"` / `"old_skill"` (improve-mode; `"new_skill"` is an accepted alias of `"with_skill"`, per `references/eval-run-procedure.md` Step 1 (Spawn each test case's runs)) — the viewer color-codes only these four names; `aggregate_benchmark` accepts any config-dir name that has a `run-*` child, so the configuration field is **open** (any string is valid, not just these four)
  - `run_number`: Integer run number (1, 2, 3...)
  - `result`: Nested object with `pass_rate`, `passed`, `failed`, `total`, `time_seconds`, `tokens`, `tool_calls`, `errors` (all eight keys are always written by `aggregate_benchmark.py`; `failed` and `tool_calls` were previously omitted from this list but are emitted)
- `run_summary`: Statistical aggregates per configuration
  - one entry per config name (e.g. `with_skill` / `without_skill`, `with_skill` / `old_skill`): Each contains `pass_rate`, `time_seconds`, `tokens` objects with `mean`, `stddev`, `min`, and `max` fields (four fields each, not two)
  - `delta`: Difference strings like `"+0.50"`, `"+13.0"`, `"+1700"`, computed as primary − baseline, with the two roles matched by config-dir name (`with_skill`/`new_skill` = primary, `without_skill`/`old_skill` = baseline), so an improvement is positive for any combination of those four names. Only config names outside that vocabulary fall back to alphabetically-first − second (the script prints a `Warning:` to stderr); in that case read the per-config means, not the delta sign.
- `notes`: Freeform observations from the analyzer

`metadata.analyzer_model` always equals `executor_model`: both come from the single `--model` argument, and no separate analyzer-model selection exists.

**Important:** The viewer reads these field names exactly. Using `config` instead of `configuration`, or putting `pass_rate` at the top level of a run instead of nested under `result`, will cause the viewer to show empty/zero values. Always reference this schema when generating benchmark.json manually.

---

## comparison.json

Output from blind comparator. Located at the `output_path` the orchestrator passes in the comparator's dispatch prompt (the comparator defaults to `comparison.json` in its working directory when none is given).

```json
{
  "winner": "A",
  "reasoning": "Output A provides a complete solution with proper formatting and all required fields. Output B is missing the date field and has formatting inconsistencies.",
  "rubric": {
    "A": {
      "content": {
        "correctness": 5,
        "completeness": 5,
        "accuracy": 4
      },
      "structure": {
        "organization": 4,
        "formatting": 5,
        "usability": 4
      },
      "content_score": 4.7,
      "structure_score": 4.3,
      "overall_score": 9.0
    },
    "B": {
      "content": {
        "correctness": 3,
        "completeness": 2,
        "accuracy": 3
      },
      "structure": {
        "organization": 3,
        "formatting": 2,
        "usability": 3
      },
      "content_score": 2.7,
      "structure_score": 2.7,
      "overall_score": 5.4
    }
  },
  "output_quality": {
    "A": {
      "score": 9,
      "strengths": ["Complete solution", "Well-formatted", "All fields present"],
      "weaknesses": ["Minor style inconsistency in header"]
    },
    "B": {
      "score": 5,
      "strengths": ["Readable output", "Correct basic structure"],
      "weaknesses": ["Missing date field", "Formatting inconsistencies", "Partial data extraction"]
    }
  },
  "expectation_results": {
    "A": {
      "passed": 4,
      "total": 5,
      "pass_rate": 0.80,
      "details": [
        {"text": "Output includes name", "passed": true}
      ]
    },
    "B": {
      "passed": 3,
      "total": 5,
      "pass_rate": 0.60,
      "details": [
        {"text": "Output includes name", "passed": true}
      ]
    }
  }
}
```

---

## analysis.json

Output from post-hoc analyzer. Located at the `output_path` the orchestrator passes in the analyzer's dispatch prompt.

```json
{
  "comparison_summary": {
    "winner": "A",
    "winner_skill": "path/to/winner/skill",
    "loser_skill": "path/to/loser/skill",
    "comparator_reasoning": "Brief summary of why comparator chose winner"
  },
  "winner_strengths": [
    "Clear step-by-step instructions for handling multi-page documents",
    "Included validation script that caught formatting errors"
  ],
  "loser_weaknesses": [
    "Vague instruction 'process the document appropriately' led to inconsistent behavior",
    "No script for validation, agent had to improvise"
  ],
  "instruction_following": {
    "winner": {
      "score": 9,
      "issues": ["Minor: skipped optional logging step"]
    },
    "loser": {
      "score": 6,
      "issues": [
        "Did not use the skill's formatting template",
        "Invented own approach instead of following step 3"
      ]
    }
  },
  "improvement_suggestions": [
    {
      "priority": "high",
      "category": "instructions",
      "suggestion": "Replace 'process the document appropriately' with explicit steps",
      "expected_impact": "Would eliminate ambiguity that caused inconsistent behavior"
    }
  ],
  "transcript_insights": {
    "winner_execution_pattern": "Read skill -> Followed 5-step process -> Used validation script",
    "loser_execution_pattern": "Read skill -> Unclear on approach -> Tried 3 different methods"
  }
}
```

---

## eval_metadata.json

Per-eval metadata file. Located at `<workspace>/iteration-N/eval-<descriptive-name>/eval_metadata.json`.

```json
{
  "eval_id": 0,
  "eval_name": "descriptive-name-here",
  "prompt": "The user's task prompt"
}
```

**Fields:**
- `eval_id`: Integer identifier (0-based, unique within an iteration). Note: `evals.json` calls this `id`, while `eval_metadata.json` calls it `eval_id` — they are the same logical integer.
- `eval_name`: Human-readable name (used as section header in the viewer).
- `prompt`: The task prompt for this eval.

---

## results.json

Output from Description Optimization mode (`run_loop.py`). Located at `<workspace>/trigger-opt/<timestamped-subdir>/results.json`.

**Fields** (stable fields in run_loop.py's return value; this section is where they are documented):
- `exit_reason`: `"unknown"` / `"all_passed (iteration N)"` (all train queries passed; held-out test results are not consulted) / `"max_iterations (N)"` / `"improve_description crashed on iteration N: <error>"` (the improvement step failed; no traceback, partial results written)
- `best_description`: The optimized description (apply this to SKILL.md)
- `original_description`: The description at the start of the run
- `final_description`: The last description the loop tried (not necessarily best)
- `best_score`: The best iteration's score as `passed/total`, on the held-out test set when one exists and on the train set otherwise
- `best_train_score`: The train-set score of the best iteration, the one picked by held-out test score (definition: the glossary row in `references/glossary.md`)
- `best_test_score`: Best score on the held-out test set (may be `null` when holdout=0)
- `iterations_run`: Number of iterations completed
- `holdout` / `train_size` / `test_size`: Eval split parameters
- `history`: Per-iteration score history
