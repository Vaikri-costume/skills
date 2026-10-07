#!/usr/bin/env python3
"""assemble_fix_prompt.py — Build and stage the considered-fix prompt for every tier.

Callers: prepass_run.py (Prepass clusters from cluster_prepass.py) and cluster_enforce.py (Code
Review clusters, through ledger_common.stage_fixer_prompt).

Reads the cluster JSON + fix_blast.py JSON (each by path, or one of them from stdin), fills the
considered-fix.md template via stage_cold_prompts.py, and writes the staged
fixing prompt to --out-dir.

Slots filled:
  [ROUND]       — from --round
  [CLUSTERS]    — cluster JSON (pretty-printed)
  [BLAST]       — blast JSON (pretty-printed)
  [HOW_TO_FIX]  — absolute path to how-to-fix.md (a POINTER, never inlined)
  [README]      — the absolute path to the target's intent source (a POINTER, never
                  the file's contents): its README.md, or SKILL.md when there is no
                  README.md (ledger_common.intent_source; how-to-fix.md "considered-fix
                  constraint")
  [SKILL_FILES] — newline-separated absolute paths to the skill's in-scope files
                  (pointers, never inlined source)
  [INTERFACE_RULE] — the frozen-interface rule for this round of the run (ledger_common.interface_rule;
                  --run-round names the round)
  [OUTPUT_CHECK] — at the top of the prompt: the output contract (with a FIX's Closure block), the
                  cluster ids this fixer must decide, and the banned dismissal vocabulary (ledger_common.BANNED_PHRASES) that
                  check_decisions.py and fill-address reject

REUSES stage_cold_prompts.py for slot substitution — does not re-implement it.

Usage:
    assemble_fix_prompt.py \\
        --cluster-json  <path to the tier's cluster JSON>          \\
        --blast-json    <path to fix_blast.py output>       \\
        --readme-path   <absolute path to the target's intent source (README.md, else SKILL.md)> \\
        --skill-root    <root dir of target skill>             \\
        --round         <audit round number>                   \\
        --template      <path to considered-fix.md>     \\
        --howtofix-path <absolute path to how-to-fix.md>       \\
        --out-dir       <scratchpad dir for the staged prompt> \\
        --runtime       <YYYY-MM-DDTHH:MM:SS>                  \\
        [--run-round    <round number within this run, default --round>] \\
        [--label        <filename label, default "considered-fix">]

    # Either ONE of the two JSONs may be read from stdin by passing '-' (for a manual run; the
    # in-skill caller, lc.stage_fixer_batches, passes both as temp files); stdin is a single
    # stream, so passing '-' for both exits 2:
    assemble_fix_prompt.py --cluster-json /tmp/clusters.json --blast-json - ...

    # Or read each JSON from a file:
    assemble_fix_prompt.py --cluster-json /tmp/clusters.json --blast-json /tmp/blast.json ...

Output: prints the staged prompt path to stdout (one line).
Exit: 0 ok; 1 error; 2 usage.

Pure stdlib. Python 3.9+.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from inscope import inscope_files  # noqa: E402 — the one in-scope authority
import ledger_common as lc  # noqa: E402


def load_json_file(path_or_dash: str, label: str) -> dict | list:
    if path_or_dash == "-":
        try:
            return json.load(sys.stdin)
        except json.JSONDecodeError as e:
            print(f"ERROR: stdin is not valid JSON for {label}: {e}", file=sys.stderr)
            sys.exit(1)
    p = Path(path_or_dash).expanduser()
    if not p.is_file():
        print(f"ERROR: {label} file not found: {p}", file=sys.stderr)
        sys.exit(2)
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"ERROR: {label} is not valid JSON: {e}", file=sys.stderr)
        sys.exit(1)


def output_check(cluster_ids: list) -> str:
    """The [OUTPUT_CHECK] text: the decisions contract and the checks check_decisions.py applies
    before fill-address, with the banned phrases taken from ledger_common so the list never drifts."""
    banned = "; ".join(f'"{p}"' for p in lc.BANNED_PHRASES)
    return (
        "Your final message is ONE JSON object `{\"decisions\": [...]}` with one entry per cluster and no "
        "prose after it. Each entry has `cluster` (the id exactly as given), `decision` (exactly `FIX`, "
        "`STRENGTHEN` or `ORCHESTRATOR-PAUSE`), `address` and `touched_files`. The address is one "
        "non-empty line that starts with the decision word, a space and `(`: `FIX (<file>: <edit>)`, "
        "`STRENGTHEN (added at <file>:<lines>: \"...\")`, or for a pause the question, optionally as "
        "`ORCHESTRATOR-PAUSE (<question>)`. A FIX entry also has `closure`, a list of four one-line "
        "strings: `Siblings: <file:line updated|unchanged, ...>`, `Bound: <limit, edge case and existing "
        "remedy of each added loop, fallback, retry, error path or definition, or none added; when you rewrite an exit "
        "code's or error's remedy, every cause of it in the script, disjoint, each with one remedy>` and "
        "`Claims: <each factual sentence you wrote -> its proving file:line; for each artefact or step a new "
        "sentence tells the executor to use, the step that creates it on every path the sentence covers>` and "
        "`Blocks: <file:start-end of each paragraph, table or comment run you rewrote, re-read whole against the "
        "code and its sibling sites after your last edit, or none rewritten>` "
        "(how-to-fix.md \"Closure block\"). Add no recovery, restore, fallback or retake procedure the doc did "
        "not already define: remove or narrow the advice, or ORCHESTRATOR-PAUSE. No `|` and no newline in any value.\n\n"
        f"Clusters you must decide (every one, none other): {', '.join(cluster_ids) or '(none)'}.\n\n"
        "Before your decisions are recorded, `scripts/check_decisions.py` reads them and sends them "
        "back for you to re-emit if any address is empty, an address's kind prefix differs from its "
        "decision, a FIX lacks a non-empty `Siblings:`, `Bound:`, `Claims:` or `Blocks:` line, a cluster above is "
        "missing, or an address uses banned dismissal vocabulary. Banned "
        f"phrases (any case, anywhere in an address): {banned}. Describe the edit you made instead."
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Assemble and stage the considered-fix prompt (any tier).")
    ap.add_argument("--cluster-json", required=True,
                    help="Path to the tier's cluster JSON (or '-' for stdin; at most one of the two JSON args).")
    ap.add_argument("--blast-json", required=True,
                    help="Path to fix_blast.py output (or '-' for stdin; at most one of the two JSON args).")
    ap.add_argument("--readme-path", required=True,
                    help="Absolute path to the target's intent source: README.md, else SKILL.md (filled as a pointer).")
    ap.add_argument("--skill-root", required=True,
                    help="Root directory of the target skill (used to enumerate SKILL_FILES).")
    ap.add_argument("--round", required=True, type=int, help="Audit round number.")
    ap.add_argument("--template", required=True,
                    help="Path to the considered-fix.md template.")
    ap.add_argument("--howtofix-path", required=True,
                    help="Absolute path to how-to-fix.md (filled as a pointer into [HOW_TO_FIX]).")
    ap.add_argument("--out-dir", required=True,
                    help="Scratchpad directory for the staged prompt file.")
    ap.add_argument("--runtime", required=True,
                    help="Runtime tag (YYYY-MM-DDTHH:MM:SS; the minute form is also accepted; passed to stage_cold_prompts).")
    ap.add_argument("--run-round", type=int, default=None,
                    help="Round number within this run (round - run-start-round + 1); selects the "
                         "[INTERFACE_RULE] text. Default: --round.")
    ap.add_argument("--label", default="considered-fix",
                    help="Label for the staged filename (default: considered-fix).")
    args = ap.parse_args()

    # Validate paths
    howtofix = Path(args.howtofix_path).expanduser()
    if not howtofix.is_absolute():
        print(f"ERROR: --howtofix-path must be absolute: {howtofix}", file=sys.stderr)
        return 2
    if not howtofix.is_file():
        print(f"ERROR: --howtofix-path not found: {howtofix}", file=sys.stderr)
        return 2

    readme = Path(args.readme_path).expanduser()
    if not readme.is_absolute():
        print(f"ERROR: --readme-path must be absolute: {readme}", file=sys.stderr)
        return 2

    skill_root = Path(args.skill_root).expanduser()
    if not skill_root.is_dir():
        print(f"ERROR: --skill-root is not a directory: {skill_root}", file=sys.stderr)
        return 2

    template = Path(args.template).expanduser()
    if not template.is_file():
        print(f"ERROR: --template not found: {template}", file=sys.stderr)
        return 2

    if args.cluster_json == "-" and args.blast_json == "-":
        print("ERROR: --cluster-json and --blast-json cannot both read stdin ('-'); pass one as a file",
              file=sys.stderr)
        return 2

    # Load cluster and blast JSON
    cluster_data = load_json_file(args.cluster_json, "--cluster-json")
    blast_data = load_json_file(args.blast_json, "--blast-json")

    # Normalise: accept {"clusters": [...]} or bare list
    if isinstance(cluster_data, dict):
        clusters = cluster_data.get("clusters", cluster_data)
    else:
        clusters = cluster_data

    # blast_data is already {"blast_radius": [...]} as emitted by fix_blast.py
    # Pass it through as-is so the agent sees the same structure.

    # Surface repeat-count warnings for any cluster with repeat_count >= 1.
    # prepass_run annotates each cluster dict with "repeat_count"
    # (ledger_common.split_repeat_clusters) before writing the
    # clusters file; we surface a warning block prepended to [CLUSTERS] so the fixer
    # sees it without requiring a template slot change.
    repeat_warning_lines: list[str] = []
    if isinstance(clusters, list):
        for c in clusters:
            rc = c.get("repeat_count", 0)
            if rc >= 1:
                repeat_warning_lines.append(
                    f"⚠ Cluster {c.get('cluster', '?')} re-appeared from a prior pass "
                    f"(repeat_count={rc}) — your earlier fix was incomplete. Per "
                    f"{howtofix.resolve()} \"Escalation ladder for repeat-confirmed findings\": "
                    f"diagnose WHY the prior address was too weak, then move UP a "
                    f"rung (comment-only -> local patch -> structural extraction). Do NOT "
                    f"repeat the same rung or the same edit. ORCHESTRATOR-PAUSE stays "
                    f"decision-based (its three criteria in that file), never a fallback "
                    f"because a prior fix failed."
                )

    clusters_json_str = json.dumps(clusters, indent=2)

    # For Code Review clusters that carry a "members" list, render every
    # member's prose explicitly so the fixer agent sees ALL agent details —
    # not just the raw JSON blob.  A cluster with 3 members from 3 agents must
    # show all 3 quotes; relying on the agent to parse the JSON silently risks
    # one member's claim/target being overlooked.
    member_prose_lines: list[str] = []
    if isinstance(clusters, list):
        for c in clusters:
            members = c.get("members")
            if not members:
                continue
            cid = c.get("cluster", "?")
            member_prose_lines.append(f"\n### {cid} — per-agent details (all must be addressed)\n")
            for m in members:
                agent_flag = m.get("agent_flag", "?")
                loc        = m.get("loc", "?")
                issue_tag  = m.get("issue_tag", "")
                claim      = m.get("claim", "")
                target     = m.get("target", "")
                member_prose_lines.append(
                    f"- **{agent_flag}** @ `{loc}`"
                    + (f" [{issue_tag}]" if issue_tag else "")
                    + (f"\n  claim: {claim}" if claim else "")
                    + (f"\n  target: {target}" if target else "")
                )

    if member_prose_lines:
        member_prose_block = (
            "\n\n<!-- Code Review member detail — every agent quote rendered explicitly -->"
            + "\n".join(member_prose_lines)
        )
    else:
        member_prose_block = ""

    if repeat_warning_lines:
        clusters_slot = (
            "\n".join(repeat_warning_lines) + "\n\n" + clusters_json_str + member_prose_block
        )
    else:
        clusters_slot = clusters_json_str + member_prose_block

    # Build [SKILL_FILES]: newline-separated absolute paths
    skill_files_str = "\n".join(str(p) for p in inscope_files(skill_root))

    # Build the spec for stage_cold_prompts
    spec = [
        {
            "label": args.label,
            "slots": {
                "[ROUND]": str(args.round),
                "[CLUSTERS]": clusters_slot,
                "[BLAST]": json.dumps(blast_data, indent=2),
                "[HOW_TO_FIX]": str(howtofix.resolve()),
                "[README]": str(readme.resolve()),
                "[SKILL_FILES]": skill_files_str,
                "[INTERFACE_RULE]": lc.interface_rule(args.run_round or args.round),
                "[OUTPUT_CHECK]": output_check(
                    [str(c.get("cluster", "?")) for c in clusters] if isinstance(clusters, list) else []),
            },
        }
    ]

    # Locate stage_cold_prompts.py relative to this script
    scripts_dir = Path(__file__).resolve().parent
    stager = scripts_dir / "stage_cold_prompts.py"
    if not stager.is_file():
        print(f"ERROR: stage_cold_prompts.py not found at: {stager}", file=sys.stderr)
        return 1

    # Write spec to a temp file in out-dir (created by stager, but we need to write
    # spec before the stager runs — create out-dir first)
    out_dir = Path(args.out_dir).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)
    spec_path = lc.run_tmp_path(out_dir, f".assemble-fix-spec-r{args.round}", args.runtime)
    spec_path.write_text(json.dumps(spec, indent=2), encoding="utf-8")

    # Call stage_cold_prompts
    cmd = [
        sys.executable, str(stager),
        "--template", str(template),
        "--out-dir", str(out_dir),
        "--runtime", args.runtime,
        "--spec", str(spec_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)

    # Clean up temp spec
    try:
        spec_path.unlink()
    except OSError:
        pass

    if proc.returncode not in (0,):
        print(proc.stderr, file=sys.stderr)
        print(f"ERROR: stage_cold_prompts exited {proc.returncode}", file=sys.stderr)
        return 1

    # Parse staged output to extract the path
    try:
        result = json.loads(proc.stdout)
    except json.JSONDecodeError:
        print(f"ERROR: stage_cold_prompts output is not JSON: {proc.stdout[:200]}", file=sys.stderr)
        return 1

    staged = result.get("staged", [])
    if not staged:
        print("ERROR: stage_cold_prompts reported no staged files.", file=sys.stderr)
        print(proc.stderr, file=sys.stderr)
        return 1

    staged_path = staged[0]["path"]
    # Print the staged path to stdout (the caller's return value)
    print(staged_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
