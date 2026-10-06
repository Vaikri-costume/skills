#!/usr/bin/env python3
"""code_review_run.py — Code-review stage FRONT.

There is NO mechanical sweep at Code Review (irreducibly semantic); this script decides the review
scope, stages the one all-lens (ALLLENS) prompt for that scope, records the scope for the collector,
and flips the marker to dispatched. Dispatch is always two Sonnet generalists on the same prompt
(their findings are unioned): the October 2026 self-run measured little overlap between two
reviewers (8% of flags), so the second one roughly doubles the finds per round.

Review scope (--scope, default auto):
  full     every in-scope file of the target (scripts/inscope.py).
  changed  only the in-scope files the previous round's ledger rows and this round's addressed rows
           name in their Address cells (the files the fixes touched; how-to-fix.md requires a FIX
           address to name every file it edited).
  auto     full in rounds 1-2 of a run (round - run-start-round + 1 <= 2); from round 3, changed,
           unless that set is empty (then full). A clean `changed` review is NOT convergence:
           code_review_collect.py answers `changed-scope-clean` and the orchestrator re-runs this
           script with --scope full in the same round. Convergence is declared only by a clean
           full-sweep review.

From round 2 of a run, G2 gets its own staged prompt: the same prompt with one line in `## Scope` asking
it to read the listed files in reverse order (G2_REVERSE_ORDER_LINE); G1's prompt is unchanged.

The chosen scope and file list are written to <out-dir>/cr-scope-<N>-<RUN_TIMESTAMP>.json;
code_review_collect.py reads it so the coverage gate checks exactly the staged files.

Usage:
    code_review_run.py --target <skill-dir> --ledger <path> --round <N>
                       --runtime <RT> --out-dir <dir> [--scope auto|full|changed]

Prints JSON {"status":"needs-adjudication","scope":{...},"dispatch":[...],"staged_prompts":[...],"then":[...]}.
Exit: 0 staged; 2 invocation error (bad --target, missing template or lens body).

Pure stdlib. Python 3.9+. Haiku-runnable (no LLM calls).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent       # scripts/
_ROOT = _HERE.parent                          # skill-tracer/

if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from inscope import inscope_files as in_scope_files  # noqa: E402 — single source of truth
import ledger_common as lc  # noqa: E402

_CODE_REVIEW_TEMPLATE  = _ROOT / "templates" / "agent-cold-code-review.md"
_PROMPTS_DIR           = _ROOT / "prompts"

# The five code-review lenses whose bodies make up the ALLLENS prompt: (lens, body file).
_CODE_REVIEW_AGENTS = [
    ("fidelity",  "agent-fidelity.md"),
    ("executor",  "agent-executor.md"),
    ("logic",     "agent-logic.md"),
    ("integrity", "agent-integrity.md"),
    ("design",    "agent-design.md"),
]

GENERALIST_FLAGS = ("G1", "G2")
FULL_SCOPE_TEXT = "Whole-skill cold read — evaluate all files listed above as they currently exist on disk."
CHANGED_SCOPE_TEXT = (
    "Scoped review: the files listed above are your review scope; read each of "
    "them in full. You MAY open any other file of the target to verify a claim (for example the script "
    "a listed doc describes), and a contract broken between a listed file and an unlisted one is in "
    "scope. Findings must name a listed file in `File:`."
)
# From round 2 of a run G2's prompt gets this one extra line (G1's does not), staged as its own file.
# An untested hypothesis (HISTORY.md 3.3.0-trimplus-v2): reading in the opposite order may make the two
# reviewers' finds less correlated.
G2_REVERSE_ORDER_LINE = ("Read the files listed under `## Files` in reverse order: start with the last "
                         "file listed and end with the first.")


def scope_path(out_dir: Path, rnd: int, runtime: str) -> Path:
    """The scope record code_review_collect.py reads (one per round and run)."""
    return lc.run_tmp_path(out_dir, f"cr-scope-{rnd}", runtime)


def changed_files(ledger_text: str, target: Path, rnd: int, candidates: list) -> list:
    """The in-scope files named in the Address cells of round rnd-1's rows and round rnd's addressed
    rows: a file counts when its target-relative path, or its basename as a whole token, appears."""
    addresses = [r["address"] for r in lc.round_rows(ledger_text, rnd - 1)]
    addresses += [r["address"] for r in lc.round_rows(ledger_text, rnd) if not lc.is_pending(r["address"])]
    text = "\n".join(addresses)
    out = []
    for p in candidates:
        rel = p.relative_to(target).as_posix()
        if rel in text or re.search(r"(?<![\w./-])" + re.escape(p.name) + r"(?![\w-])", text):
            out.append(p)
    return out


def decide_scope(requested: str, ledger: Path, target: Path, rnd: int) -> dict:
    """{"scope": "full"|"changed", "reason": str, "files": [Path]} for this round's review."""
    all_files = in_scope_files(target)
    if requested == "full":
        return {"scope": "full", "reason": "--scope full", "files": all_files}
    text = ledger.read_text(encoding="utf-8") if ledger.is_file() else ""
    run_rnd = lc.run_round(ledger, rnd)
    if requested == "auto" and run_rnd <= 2:
        return {"scope": "full", "reason": f"round {run_rnd} of this run (rounds 1-2 are full sweeps)",
                "files": all_files}
    changed = changed_files(text, target, rnd, all_files)
    if not changed:
        return {"scope": "full", "reason": "no changed file is named in the ledger since the previous "
                                           "round", "files": all_files}
    return {"scope": "changed", "reason": f"{len(changed)} of {len(all_files)} files changed since the "
                                          f"previous round", "files": changed}


# ---------------------------------------------------------------------------
# Consolidated all-lens prompt assembler (in-memory; no per-lens files needed)
# ---------------------------------------------------------------------------

def _build_alllens_prompt(
    skill_files_block: str,
    scope_text: str,
    template_text: str,
) -> str:
    """Build the consolidated all-lens prompt from lens body files in-memory.

    Structure:
      - One-line role (single cold agent performing ALL FIVE lenses)
      - Shared framing ONCE (tool restriction, full-coverage requirement,
        pre-flight, files, scope) — taken from the shared template but
        with [AGENT_NAME] replaced and [AGENT_TASK_BODY] replaced by the
        assembled five-lens body.
      - Each lens's "## Task — <lens>" + "### Checks" once
      - The output contract once (PRE-FLIGHT + ISSUE [tag] four-line
        blocks + No of issues found:: N); the shared base template's existing
        "Anti-double-counting" rules ("If a single root cause produces
        multiple symptom claims... output one ISSUE block", "If a failure is
        flaggable under two categories, choose the one whose description
        most directly matches... Do not file twice.") already cover collapsing
        one root cause across lens boundaries with no lens-identifying tag
        needed — which lens flagged it is not information any downstream
        consumer (clustering, the fixer) reads or requires.
    """
    # Read all lens bodies
    lens_sections: list[str] = []
    for agent_name, body_filename in _CODE_REVIEW_AGENTS:
        body_path = _PROMPTS_DIR / body_filename
        body_text = body_path.read_text(encoding="utf-8")
        # Prefix each lens section with its lens header
        lens_sections.append(f"### Lens — {agent_name}\n\n{body_text}")

    assembled_task_body = (
        "You are a single cold agent performing ALL FIVE lenses (fidelity, executor, "
        "logic, integrity, design) in one pass. Complete your full reading of every "
        "file before writing any ISSUE blocks. Apply all five lenses below. The shared "
        "Anti-double-counting rules apply across all five lenses exactly as they apply "
        "within one: one root cause, one ISSUE block, tagged with whichever single check "
        "name most directly matches — never a lens-identifying prefix, and never split "
        "across lenses to inflate the count.\n\n"
        "Where to look first: in past audits of skills, the prose in SKILL.md and references/ drew "
        "about 3-4 times the defects per line that the code did. Check claim-versus-code agreement "
        "there first: every statement those files make about a script's flags, outputs, exit codes, "
        "file names or steps, against the script itself.\n\n"
        "---\n\n"
        + "\n\n---\n\n".join(lens_sections)
    )

    # Fill the shared template
    filled = template_text
    filled = filled.replace(
        "You are [AGENT_NAME], a cold-dispatch code-review trace agent.",
        "You are a single cold code-review agent performing ALL FIVE lenses "
        "(fidelity, executor, logic, integrity, design) in one pass.",
    )
    filled = filled.replace("[AGENT_NAME]", "all-lenses")
    # templates/agent-cold-code-review.md carries [SKILL_FILES] exactly once (under "## Files"); its
    # prose refers to that section by name, so a multi-line list never lands mid-sentence.
    filled = filled.replace("[SKILL_FILES]", skill_files_block)
    filled = filled.replace("[SCOPE]", scope_text)
    # The lens bodies go in last, so a slot name a lens body quotes ("[SKILL_FILES]") stays literal
    # instead of being substituted inside the body.
    filled = filled.replace("[AGENT_TASK_BODY]", assembled_task_body)

    # No lens-tag note added: which lens a finding came from is not read by any downstream
    # consumer, so tagging it would be noise on top of the base template's own dedup rules.

    return filled


def main() -> int:
    ap = argparse.ArgumentParser(description="Code-review front: decide the scope, stage the ALLLENS prompt, flip the marker.")
    ap.add_argument("--target",  required=True, help="Target skill directory.")
    ap.add_argument("--ledger",  required=True, help="Path to the audit ledger.")
    ap.add_argument("--round",   required=True, type=int, help="Audit round number.")
    ap.add_argument("--runtime", required=True, help="Runtime tag (YYYY-MM-DDTHH:MM:SS; the minute form is also accepted).")
    ap.add_argument("--out-dir", required=True, help="Scratch directory for staged prompts.")
    ap.add_argument("--scope", default="auto", choices=["auto", "full", "changed"],
                    help="Review scope (default auto: full in rounds 1-2 of a run, changed files from round 3).")
    args = ap.parse_args()

    target  = Path(args.target).expanduser().resolve()
    ledger  = Path(args.ledger).expanduser()
    out_dir = Path(args.out_dir).expanduser()
    rnd     = args.round
    runtime = args.runtime

    if not target.is_dir():
        print(json.dumps({"error": f"--target is not a directory: {target}"}), file=sys.stderr)
        return 2
    if not _CODE_REVIEW_TEMPLATE.is_file():
        print(json.dumps({"error": f"Code Review template not found: {_CODE_REVIEW_TEMPLATE}"}), file=sys.stderr)
        return 2
    missing = [str(_PROMPTS_DIR / b) for _, b in _CODE_REVIEW_AGENTS if not (_PROMPTS_DIR / b).is_file()]
    if missing:
        print(json.dumps({"error": "missing agent body files", "paths": missing}), file=sys.stderr)
        return 2
    out_dir.mkdir(parents=True, exist_ok=True)

    scope = decide_scope(args.scope, ledger, target, rnd)
    files = scope["files"]
    scope_text = FULL_SCOPE_TEXT if scope["scope"] == "full" else CHANGED_SCOPE_TEXT
    prompt = _build_alllens_prompt("\n".join(str(p) for p in files), scope_text,
                                   _CODE_REVIEW_TEMPLATE.read_text(encoding="utf-8"))
    alllens_path = out_dir / f"code-review-ALLLENS-{lc.runtime_slug(runtime)}.txt"
    alllens_path.write_text(prompt, encoding="utf-8")
    g2_path = alllens_path
    if lc.run_round(ledger, rnd) >= 2:
        g2_path = out_dir / f"code-review-ALLLENS-G2-{lc.runtime_slug(runtime)}.txt"
        g2_path.write_text(prompt.replace(scope_text, f"{scope_text}\n\n{G2_REVERSE_ORDER_LINE}", 1),
                           encoding="utf-8")
    scope_file = scope_path(out_dir, rnd, runtime)
    scope_file.write_text(json.dumps({"round": rnd, "scope": scope["scope"], "reason": scope["reason"],
                                      "files": [str(p) for p in files]}, indent=2), encoding="utf-8")

    lc.write_marker(ledger, f"{runtime} code-review dispatched round-{rnd}")

    flags = ",".join(GENERALIST_FLAGS)
    dispatch = [{"model": "sonnet", "role": "generalist", "flag": f,
                 "prompt": str(g2_path if f == "G2" else alllens_path)} for f in GENERALIST_FLAGS]
    then = [
        "BEFORE dispatching, take the edit-detection baseline: touch <out-dir>/dispatch-baseline-<RUN_TIMESTAMP>, "
        "and archive the target: tar -cf <out-dir>/target-before-<RUN_TIMESTAMP>.tar -C <target> . "
        "(references/dispatch.md \"A reviewer that edits a file\").",
        f"Dispatch {len(dispatch)} cold generalist agents (Sonnet, subagent_type Explore [READ-ONLY]) on the "
        "staged prompt each dispatch entry names, in ONE same-turn message, with the code-reviewer provenance wording in "
        "references/dispatch.md (not a bare 'read this file' pointer); instruct full sequential reads + exact ISSUE [tag] "
        "four-line block form. CAPTURE each agentId in the review manifest; transcript at "
        "<projects-dir>/subagents/agent-<agentId>.jsonl.",
        "After the agents return and BEFORE collecting: find <target> -type f -newer "
        "<out-dir>/dispatch-baseline-<RUN_TIMESTAMP>; any file listed means a reviewer edited it — revert it, "
        "discard that agent's result and re-dispatch it fresh (references/dispatch.md \"A reviewer that edits a file\").",
        f"Run: python3 .../scripts/code_review_collect.py --agent-transcripts <G1,G2 paths in manifest order> "
        f"--agent-flags {flags} --target <target> --ledger <ledger> --round {rnd} --runtime <RT> --out-dir <out-dir> "
        f"> <out-dir>/cr-verified-{rnd}-<RUN_TIMESTAMP>.json",
        "Contract or coverage violation → SendMessage that SAME agent (reformat / read-the-gap-and-re-emit); "
        "re-dispatch fresh ONLY if not addressable.",
    ]
    result = {
        "status":         "needs-adjudication",
        "scope":          {"scope": scope["scope"], "reason": scope["reason"], "files": len(files),
                           "scope_file": str(scope_file)},
        "dispatch":       dispatch,
        "staged_prompts": [{"agent": "all-lenses", "flag": "ALLLENS", "path": str(alllens_path)}]
                          + ([{"agent": "all-lenses", "flag": "G2", "path": str(g2_path)}]
                             if g2_path != alllens_path else []),
        "then":           then,
    }
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
