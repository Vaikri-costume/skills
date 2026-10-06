#!/usr/bin/env python3
"""prepass_run.py — FRONT half of the Prepass loop: deterministic scripted steps.

Runs the full Prepass scripted pipeline for one round:
  0. If the ledger is absent (Prepass run without `append_ledger.py begin-round`), create it with
     the standard header (lc.ledger_header), recording --target on its `target::` line.
  1. cascade_sweep --level prepass --json  (find Prepass findings)
  2. If ZERO findings (and no detector errors, and no unfilled PENDING rows): advance marker to
     "code-review running round-N", print {"status":"converged","next":"code-review"}, exit 0.
     Unfilled PENDING rows -> {"status":"needs-record","pending_clusters":[...]}, exit 0.
     A detector that crashed or could not load -> stderr JSON error, exit 1 (never "converged").
  3. Else:
     a. cluster_prepass   (--target --ledger --round) — cluster the findings
     b. fix_blast (reads tokens from cluster JSON; auto-touches def files)
     c. ledger_cascade --mode cluster  (--phase Prepass; writes the PENDING rows, sets the
        "prepass addressing" marker)
     d. assemble_fix_prompt  (stage one considered-fix prompt per fixer batch, lc.stage_fixer_batches:
        one batch for 12 clusters or fewer, else batches of at most 12)
     Print {"status":"needs-fix","staged_prompt":"<batch 1 path>","batches":[{batch, model,
            clusters, staged_prompt}],"clusters":[...inline...],"blast":[...inline...]}, exit 0.
     A cluster whose signature (check, file, handler shape) was already addressed
     ledger_common.AUTO_PAUSE_REPEATS times (2) this round is written as an ORCHESTRATOR-PAUSE row (listed under "auto_pause") instead of being
     sent to the fixer again.

Exit: 0 = a status JSON was printed (converged / needs-record / needs-fix); 1 = pipeline error
(a sub-script failed or a detector crashed; detail JSON on stderr); 2 = --target is not a directory.

clusters and blast data are emitted INLINE in the stdout JSON — no result
files are written to --out-dir.  --out-dir is used only for the staged prompts
(the fixer agents' input files).

Usage:
    prepass_run.py --target <skill-dir> --ledger <path> --round <N>
                   --runtime <RT> --out-dir <scratch>

Pure stdlib. Python 3.9+. Haiku-runnable (no LLM calls).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Locate sibling scripts
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve().parent          # scripts/
_ROOT = _HERE.parent                             # skill-tracer/
for _p in (_HERE, _ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
import ledger_common as lc  # noqa: E402
import cluster_prepass as cp  # noqa: E402 — the one definition of a finding signature

_CASCADE_SWEEP   = _ROOT / "cascade_sweep.py"
_CLUSTER_PREPASS      = _ROOT / "cluster_prepass.py"
_FIX_BLAST       = _HERE / "fix_blast.py"
_LEDGER_CASCADE  = _HERE / "ledger_cascade.py"



def _run(cmd: list[str], *, stdin_text: str | None = None,
         label: str = "", ok_codes: tuple = (0,)) -> subprocess.CompletedProcess:
    """Run *cmd*, return CompletedProcess.  Raises RuntimeError unless the exit code is in *ok_codes*.

    Strict by default: only a script whose rc=1 is a documented gate signal (cascade_sweep: findings
    present; fix_blast: uncovered sites) is passed ok_codes=(0, 1). For every other sub-script rc=1
    is a failure (a rejected ledger row, a failed prompt assembly) and must not be reported as a
    staged fix."""
    proc = subprocess.run(
        cmd,
        input=stdin_text,
        capture_output=True,
        text=True,
    )
    if proc.returncode not in ok_codes:
        raise RuntimeError(
            f"{label or cmd[0]} exited {proc.returncode}\n"
            f"stderr: {proc.stderr.strip()}\nstdout: {proc.stdout.strip()}"
        )
    return proc


_PAUSE_THEN = lc.auto_pause_then("re-run prepass_run.py with the same round.")


def _write_pause_rows(ledger: Path, runtime: str, rnd: int, paused: list[dict]) -> None:
    """Write each auto-paused cluster as an open ORCHESTRATOR-PAUSE Prepass row (shared writer:
    ledger_common.write_pause_rows, idempotent on resume)."""
    lc.write_pause_rows(ledger, runtime, rnd, "Prepass", paused, cp.row_signature, cp.cluster_signature)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Prepass front-half: run sweep → cluster → blast → write PENDING rows → assemble."
    )
    ap.add_argument("--target",  required=True, help="Target skill directory.")
    ap.add_argument("--ledger",  required=True, help="Path to the audit ledger.")
    ap.add_argument("--round",   required=True, type=int, help="Audit round number.")
    ap.add_argument("--runtime", required=True, help="Runtime tag (YYYY-MM-DDTHH:MM:SS; the minute form is also accepted).")
    ap.add_argument("--out-dir", required=True, help="Scratch directory for intermediate files.")
    args = ap.parse_args()

    target   = Path(args.target).expanduser().resolve()
    ledger   = Path(args.ledger).expanduser()
    out_dir  = Path(args.out_dir).expanduser()
    rnd      = args.round
    runtime  = args.runtime

    if not target.is_dir():
        print(json.dumps({"error": f"--target is not a directory: {target}"}))
        return 2

    out_dir.mkdir(parents=True, exist_ok=True)

    # A Prepass run without `append_ledger.py begin-round` finds no ledger. It is created here, with
    # the target recorded, so ledger_cascade.py (which never creates a ledger) can write rows into it
    # and a later begin-round still refuses a different target.
    if not ledger.is_file():
        ledger.parent.mkdir(parents=True, exist_ok=True)
        ledger.write_text(lc.ledger_header(ledger.stem, f"{runtime} prepass running round-{rnd}", str(target)),
                          encoding="utf-8")

    # ------------------------------------------------------------------
    # cascade_sweep --level prepass --json
    # ------------------------------------------------------------------
    sweep_cmd = [
        sys.executable, str(_CASCADE_SWEEP),
        str(target),
        "--level", "prepass",
        "--json",
    ]
    try:
        sweep_proc = _run(sweep_cmd, label="cascade_sweep", ok_codes=(0, 1))
    except RuntimeError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1

    sweep_data = json.loads(sweep_proc.stdout)
    prepass_findings = sweep_data.get("prepass", [])

    # A detector that crashed or could not load never ran on (part of) the target, so "no findings"
    # proves nothing. Refuse to proceed; the detector must be fixed (or its failure understood) first.
    detector_errors = sweep_data.get("detector_errors", [])
    if detector_errors:
        print(json.dumps({
            "error": "detector-error: a prepass detector crashed or could not load; Prepass cannot be "
                     "declared converged. Fix the detector (or the file it chokes on) and re-run.",
            "detector_errors": detector_errors,
        }), file=sys.stderr)
        return 1

    # ------------------------------------------------------------------
    # ZERO findings → check for orphaned PENDING rows before advancing
    # ------------------------------------------------------------------
    if not prepass_findings:
        ledger_path = Path(ledger).expanduser()

        # Pending-rows guard: if ANY Prepass row for this round still has
        # Address == PENDING, the audit trail is desynced (fixes landed but rows
        # were never filled by ledger_cascade fill-address).  Do NOT advance; tell
        # the orchestrator to run ledger_cascade fill-address first.
        if ledger_path.is_file():
            ledger_text_chk = ledger_path.read_text(encoding="utf-8")
            pending_cluster_ids = [
                row.get("cluster", "?")
                for row in lc.round_rows(ledger_text_chk, rnd)
                if row.get("phase", "").upper() == "PREPASS" and lc.is_pending(row.get("address", ""))
            ]
            if pending_cluster_ids:
                print(json.dumps({
                    "status":           "needs-record",
                    "pending_clusters": pending_cluster_ids,
                }))
                return 0

        # No orphaned PENDING rows — safe to advance marker to code-review.
        new_marker = f"{runtime} code-review running round-{rnd}"
        lc.write_marker(ledger_path, new_marker)

        print(json.dumps({
            "status": "converged",
            "next":   "code-review",
            "then": [
                f"Prepass clean. The marker is already advanced to 'code-review running round-{rnd}' by this script — do NOT set it. Next: run scripts/code_review_run.py with the same --target --ledger --round --runtime --out-dir."
            ],
        }))
        return 0

    # ------------------------------------------------------------------
    # cluster_prepass  (reads sweep JSON from stdin)
    # ------------------------------------------------------------------
    cluster_cmd = [
        sys.executable, str(_CLUSTER_PREPASS),
        "--json",
        "--target", str(target),
        "--ledger", str(ledger),
        "--round",  str(rnd),
    ]
    try:
        cluster_proc = _run(cluster_cmd, stdin_text=sweep_proc.stdout, label="cluster_prepass")
    except RuntimeError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1

    # ------------------------------------------------------------------
    # Repeat-count annotation — No-orphan-flag invariant.
    # For each cluster, count how many PRIOR ADDRESSED Prepass rows this round carry the same
    # signature (check, file, handler shape — cluster_prepass.row_signature / cluster_signature).
    # Clusters with repeat_count >= lc.AUTO_PAUSE_REPEATS are auto-paused (written as
    # ORCHESTRATOR-PAUSE rows); clusters below it with repeat_count >= 1 are kept but annotated.
    # ------------------------------------------------------------------
    raw_clusters = json.loads(cluster_proc.stdout)
    cluster_list: list[dict] = (
        raw_clusters.get("clusters", [])
        if isinstance(raw_clusters, dict)
        else raw_clusters
    )

    fixer_clusters, auto_pause_clusters = lc.split_repeat_clusters(
        ledger, rnd, "Prepass", cluster_list, cp.row_signature, cp.cluster_signature)
    ledger_path_obj = Path(ledger).expanduser()

    # Build the fixer-bound cluster payload (with repeat_count); no file written.
    fixer_cluster_json: dict | list
    if isinstance(raw_clusters, dict):
        fixer_cluster_json = dict(raw_clusters)
        fixer_cluster_json["clusters"] = fixer_clusters
    else:
        fixer_cluster_json = fixer_clusters

    # If ALL clusters are auto-paused (none left for fixer), skip steps 3b–3d
    # and emit the result with only auto_pause populated.
    if not fixer_clusters:
        try:
            _write_pause_rows(ledger, runtime, rnd, auto_pause_clusters)
        except RuntimeError as exc:
            print(json.dumps({"error": str(exc)}), file=sys.stderr)
            return 1
        # Advance marker to "prepass orch-fixes round-N" (the pause rows are now open decisions).
        new_marker = f"{runtime} prepass orch-fixes round-{rnd}"
        lc.write_marker(ledger_path_obj, new_marker)

        result = {
            "status":     "needs-fix",
            "auto_pause": lc.auto_pause_report(auto_pause_clusters),
            "in_flight_marker": f"in-flight:: {new_marker}",
            "then": [_PAUSE_THEN],
        }
        print(json.dumps(result, indent=2))
        return 0

    # ------------------------------------------------------------------
    # fix_blast  (reads cluster JSON from stdin; --skill-root)
    # ------------------------------------------------------------------
    blast_cmd = [
        sys.executable, str(_FIX_BLAST),
        "--skill-root", str(target),
    ]
    try:
        blast_proc = _run(blast_cmd, stdin_text=json.dumps(fixer_cluster_json), label="fix_blast",
                          ok_codes=(0, 1))
    except RuntimeError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1

    # blast data is held in memory; no file written.

    # ------------------------------------------------------------------
    # ledger_cascade cluster --phase Prepass
    # Write PENDING rows (one per cluster, blast embedded in root_cause)
    # BEFORE dispatching the fixer.  Marker → "prepass addressing round-N".
    # Payload: {"clusters": [...], "blast": [...]}
    # ------------------------------------------------------------------
    blast_raw = json.loads(blast_proc.stdout)
    blast_list: list = (
        blast_raw.get("blast_radius", blast_raw)
        if isinstance(blast_raw, dict)
        else blast_raw
    )

    # Build combined cluster+blast payload for ledger_cascade cluster mode.
    pending_payload: dict
    if isinstance(fixer_cluster_json, dict):
        pending_payload = dict(fixer_cluster_json)
        pending_payload["blast"] = blast_list
    else:
        pending_payload = {"clusters": fixer_cluster_json, "blast": blast_list}

    pending_cmd = [
        sys.executable, str(_LEDGER_CASCADE),
        str(ledger),
        "--runtime", runtime,
        "--round",   str(rnd),
        "--mode",    "cluster",
        "--phase",   "Prepass",
    ]
    try:
        _run(
            pending_cmd,
            stdin_text=json.dumps(pending_payload),
            label="ledger_cascade cluster (PENDING rows)",
        )
        _write_pause_rows(ledger, runtime, rnd, auto_pause_clusters)
    except RuntimeError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1

    # ------------------------------------------------------------------
    # Stage the fixer prompts: one per batch of at most lc.FIXER_BATCH_MAX_CLUSTERS clusters
    # (lc.stage_fixer_batches runs assemble_fix_prompt.py per batch and deletes its temp inputs).
    # ------------------------------------------------------------------
    clusters_inline = (
        fixer_cluster_json.get("clusters", fixer_cluster_json)
        if isinstance(fixer_cluster_json, dict)
        else fixer_cluster_json
    )
    try:
        batches = lc.stage_fixer_batches(
            clusters=clusters_inline, blast=blast_list, skill_root=target, rnd=rnd, runtime=runtime,
            out_dir=out_dir, label="prepass", run_rnd=lc.run_round(ledger, rnd))
    except RuntimeError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1
    report = lc.batch_report(batches)
    staged_prompt = report[0]["staged_prompt"]

    # ------------------------------------------------------------------
    # Output: inline clusters + blast so the orchestrator can pipe them to
    # ledger_cascade fill-address without any intermediate files on disk.
    # The staged prompts (the fixer agents' inputs) are the only files in --out-dir.
    # ------------------------------------------------------------------
    # blast_raw / blast_list already parsed above (step 3b→3c)
    blast_inline = blast_list

    result: dict = {
        "status":        "needs-fix",
        "staged_prompt": staged_prompt,
        "batches":       report,
        "clusters":      clusters_inline,
        "blast":         blast_inline,
        "then": [
            f"Dispatch the {len(report)} fixer batch(es) in \"batches\" ONE AT A TIME, in order (never in parallel: they may edit the same files): "
            f"before each batch k, run python3 .../scripts/post_fix_gate.py snapshot --target {target} --out {out_dir}/gate-{rnd}-b<k>-<RUN_TIMESTAMP>.json; "
            f"then, for each, one fixer (the batch's \"model\", subagent_type general-purpose [edit-capable], edits ONLY files under <target>) pointed at the batch's staged_prompt with the "
            f"Fixer provenance wording in references/dispatch.md (not a bare 'read this file' pointer); it returns the JSON decisions object. "
            f"After each fixer returns, run scripts/check_decisions.py --fixer-transcript <its transcript> --expect <the batch's cluster ids>; on exit 1 SendMessage the same fixer to re-emit. "
            f"Once it exits 0, run python3 .../scripts/post_fix_gate.py check --target {target} --snapshot <that batch's gate snapshot>; on exit 1 follow SKILL.md \"Post-fix gate\" (inner passes, then ORCHESTRATOR-PAUSE). Dispatch the next batch only after both exit 0.",
            f"Write this response's \"blast\" array to a file (e.g. <out-dir>/blast-round-{rnd}-<RUN_TIMESTAMP>.json, as {{\"blast_radius\": <blast>}}) — fill-address needs it to re-verify fix-impact closure.",
            f"Run: python3 .../scripts/ledger_cascade.py <ledger> --mode fill-address --phase Prepass --round {rnd} --runtime <RT> --reenter --fixer-transcript <every batch's fixer transcript, comma-separated> --skill-root {target} --blast-json <path to the blast file just written>",
            f"Re-run scripts/prepass_run.py (same --round {rnd}). Do NOT set the marker manually.",
        ],
    }
    # Report any auto-paused clusters separately (orchestrator owns them). The pause step goes before
    # the final re-run step: the fixer batches are recorded first, the pauses resolved next, and only
    # then is prepass_run.py re-run (SKILL.md Prepass, `auto_pause`).
    if auto_pause_clusters:
        result["auto_pause"] = lc.auto_pause_report(auto_pause_clusters)
        result["then"].insert(len(result["then"]) - 1, _PAUSE_THEN)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
