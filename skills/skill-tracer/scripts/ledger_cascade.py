#!/usr/bin/env python3
"""ledger_cascade.py — ledger entry-point for the skill-tracer CASCADE (PENDING rows and fixer decisions).

Modes, selected by --mode (cluster, fill-address):

  cluster  (default)
    Consumes cluster_prepass.py JSON on stdin.  Each cluster MUST already carry a
    "flags" list (P<n> for Prepass, reviewer flags such as G1<n> for Code Review) assigned by the
    upstream stage (cluster_prepass or cluster_enforce).  Appends one ledger row
    per cluster with PENDING (considered-fix) as the address placeholder (blast
    recorded in root_cause cell), then advances the in-flight marker to
    "<phase> addressing round-<N>".  The ledger never assigns or renumbers flags.

    Accepts clusters WITH blast data embedded:
      {"clusters": [...], "blast": [...]}
    or plain cluster-only JSON (no blast):
      {"clusters": [...]}

    Required: --phase (Prepass or "Code Review"). Idempotent on resume: PENDING rows
    of the same round+phase left by an interrupted earlier pass are superseded (dropped) before the
    new rows are written, since the deterministic sweep re-derives them; a (round, cluster) id that
    collides with a row that is NOT such a stale PENDING row is refused (exit 1).

  fill-address
    Fills the real FIX/STRENGTHEN address into EXISTING PENDING rows (matched
    by round + cluster).  Does NOT create new rows.  After filling all rows,
    advances the in-flight marker:
      - The marker's phase is "prepass" when --reenter is passed (a Prepass fixer's edits are
        re-swept from prepass), else <phase>.
      - If any decision is ORCHESTRATOR-PAUSE → "<marker phase> orch-fixes round-<N>"
      - Else                                  → "<marker phase> running round-<N>"
    A PENDING row of the round+phase with no decision becomes an ORCHESTRATOR-PAUSE, so --phase must
    name the phase the rows were written under (Prepass / Code Review). When the --fixer-transcript
    values together yield no decision at all, nothing is written and the script exits 2.

    Reads decisions JSON from stdin, or from the final message of each --fixer-transcript (one per
    fixer batch of the round; repeat the option or give a comma list; a cluster decided twice is
    refused, exit 1):
      {"decisions": [{"cluster": "C1", "address": "FIX ..."}, ...]}
    Required: --round, --phase. Optional: --allow (files that legitimately keep a TOKEN-BLAST token).
    Tolerates a cluster with no matching PENDING row (reports it).

    BLOCKING PRECONDITION — fix-impact closure (how-to-fix.md "Mechanical
    enforcement — required"): whenever any decision is FIX, --skill-root and
    --blast-json are REQUIRED. For every FIX decision whose cluster's blast
    entry has fix_class TOKEN-BLAST, this script itself (not the fixer agent's
    say-so) re-runs check_fix_radius.py against the decision's touched_files.
    If --skill-root/--blast-json are absent, or any TOKEN-BLAST FIX comes back
    with uncovered sites, fill-address REJECTS EVERY DECISION (no rows
    written) instead of trusting that the fixer ran the check. This closes the
    gap where the check was documented as mandatory but nothing forced it to
    actually run.

Pure stdlib. Mechanical — no judgment at runtime (haiku-agent safe).

Usage:
    # cluster mode — write PENDING rows + blast before dispatching fixer:
    echo '<clusters+blast JSON>' \\
        | python ledger_cascade.py <ledger> --runtime <RT> --round <N> \\
            --mode cluster --phase Prepass

    # fill-address (fixer has returned; fill real addresses into PENDING rows):
    echo '<decisions JSON>' \\
        | python ledger_cascade.py <ledger> --runtime <RT> --round <N> \\
            --mode fill-address --phase Prepass [--reenter] [--allow FILES]

    # or from the fixer transcripts (one per batch):
    python ledger_cascade.py <ledger> --runtime <RT> --round <N> --mode fill-address \\
        --phase "Code Review" --fixer-transcript <t1> --fixer-transcript <t2> \\
        --skill-root <target> --blast-json <blast file>

Exit: 0 ok; 1 validation failure; 2 usage / ledger not found.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Bootstrap: ensure scripts/ dir is importable regardless of cwd
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import ledger_common as lc

# ---------------------------------------------------------------------------
# Row writer (validation and row format come from ledger_common, shared with append_ledger)
# ---------------------------------------------------------------------------

def _append_row(ledger: Path, runtime: str, rnd: int, phase: str,
                cluster: str, root_cause: str, address: str, flags: str) -> tuple[int, str]:
    """Validate and append one row. Returns (rc, message)."""
    errs = []
    for fname, val in (("root-cause", root_cause), ("address", address), ("flags", flags)):
        errs.extend(lc.reject_unsafe(fname, val))
    # Banned dismissal vocabulary applies to the address only here: a root-cause cell is quoted from
    # the target's own text (which may legitimately contain a banned phrase), while the address is
    # the fixer's own statement of what it did.
    errs.extend(lc.reject_banned_vocabulary("address", address))
    # Allow PENDING placeholder or valid ADDRESS_KINDS
    _placeholder = lc.is_pending(address)
    if not _placeholder and not lc.address_kind_ok(address):
        errs.append(
            f"address must start with one of {lc.ADDRESS_KINDS} at a token boundary: {address!r}"
        )
    if phase not in lc.KNOWN_PHASES:
        errs.append(f"phase {phase!r} not in KNOWN_PHASES {lc.KNOWN_PHASES}")
    if not lc.CLUSTER_RE.match(cluster):
        errs.append(f"cluster must match ^C\\d+$: {cluster!r}")
    if errs:
        return 1, "\n".join(f"REJECTED: {e}" for e in errs)

    row = lc.format_row(runtime, rnd, phase, cluster, root_cause, address, flags)
    text = ledger.read_text(encoding="utf-8")
    if not text.endswith("\n"):
        text += "\n"
    ledger.write_text(text + row + "\n", encoding="utf-8")
    return 0, row


# ---------------------------------------------------------------------------
# Row updater: fill the Address cell of an existing PENDING row
# ---------------------------------------------------------------------------

def _fill_pending_row(ledger: Path, rnd: int, cluster: str, new_address: str) -> tuple[bool, str]:
    """Find the PENDING row matching (rnd, cluster) and replace its Address cell.

    Returns (found, message).
    Only replaces the FIRST matching row whose Address starts with 'PENDING '.
    """
    text = ledger.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)

    # We look for a markdown table row that contains the round, the cluster id,
    # and has PENDING in the Address position.
    # Row format: | runtime | rnd | phase | cluster | root_cause | address | flags |
    # We match by scanning parsed rows; but for replacement we need the raw line.
    # Strategy: parse each line as a table row, find the match, then rewrite.

    found = False
    new_lines: list[str] = []
    for line in lines:
        stripped = line.rstrip("\n\r")
        if not stripped.startswith("|"):
            new_lines.append(line)
            continue

        cols = [c.strip() for c in stripped.split("|")]
        # cols[0] is empty (before first |), cols[1..7] are the 7 cells, cols[8] is empty
        if len(cols) < 8:
            new_lines.append(line)
            continue

        row_rnd_str   = cols[2]   # Round
        row_cluster   = cols[4]   # Cluster
        row_address   = cols[6]   # Address

        # Match: round == rnd, cluster == cluster, address starts with PENDING
        try:
            row_rnd = int(row_rnd_str)
        except ValueError:
            new_lines.append(line)
            continue

        if (not found
                and row_rnd == rnd
                and row_cluster == cluster
                and lc.is_pending(row_address)):
            # Replace address column
            cols[6] = new_address
            # Reconstruct the row in the canonical padded form `| a | b | ... |`
            new_row = "| " + " | ".join(cols[1:8]) + " |"
            # Preserve original line ending
            ending = line[len(stripped):]
            new_lines.append(new_row + ending)
            found = True
        else:
            new_lines.append(line)

    if found:
        ledger.write_text("".join(new_lines), encoding="utf-8")
        return True, f"Filled {cluster} round={rnd}: {new_address!r}"
    else:
        return False, f"No PENDING row found for cluster={cluster} round={rnd}"


# ---------------------------------------------------------------------------
# Stale-PENDING supersession (resume idempotency)
# ---------------------------------------------------------------------------

def _drop_stale_pending(ledger: Path, rnd: int, phase: str) -> list[str]:
    """Remove PENDING rows of *rnd*+*phase* (staged by an interrupted earlier pass, never filled).

    WHY: the sweeps are deterministic, so a re-run re-derives the same clusters; leaving the old
    PENDING rows would make fill-address auto-pause every stale cluster that has no decision.
    Returns the dropped cluster ids."""
    text = ledger.read_text(encoding="utf-8")
    kept: list[str] = []
    dropped: list[str] = []
    for line in text.splitlines(keepends=True):
        row = lc.parse_row(line)
        if (row and row["round"] == rnd and row["phase"] == phase.strip().upper()
                and lc.is_pending(row["address"])):
            dropped.append(row["cluster"])
            continue
        kept.append(line)
    if dropped:
        ledger.write_text("".join(kept), encoding="utf-8")
    return dropped


# ---------------------------------------------------------------------------
# Blast summary for embedding in root_cause cell
# ---------------------------------------------------------------------------

def _blast_note_for_cluster(blast_data: list[dict], cluster_id: str) -> str:
    """Return a compact blast note string for the given cluster, or '' if none."""
    for entry in blast_data:
        if entry.get("cluster") != cluster_id:
            continue
        fix_class = entry.get("fix_class", "")
        if fix_class == "LOCAL":
            return ""
        if fix_class == "TOKEN-BLAST":
            rr = entry.get("radius_result", {})
            # check_fix_radius.py reports every file holding the token (files_with_token) and the
            # subset not yet touched (uncovered); the note lists the full scope, sorted for a stable cell.
            with_token = rr.get("files_with_token", [])
            uncovered = entry.get("uncovered", rr.get("uncovered", []))
            all_files = sorted({f for f in (with_token + uncovered) if f})
            if all_files:
                joined = ", ".join(all_files)
                return f" [blast: {joined}]"
        # Generic: if radius list present
        radius = entry.get("radius", [])
        if radius:
            return f" [blast: {', '.join(radius)}]"
    return ""


# ---------------------------------------------------------------------------
# Modes
# ---------------------------------------------------------------------------

def _closure_failure(args, fix_decisions: list) -> int:
    """Fix-impact closure for fill-address (how-to-fix.md "Mechanical enforcement — required"): for
    every FIX decision whose cluster is TOKEN-BLAST, re-run check_fix_radius.py against the decision's
    touched_files instead of trusting the fixer's say-so; without --skill-root/--blast-json no row is
    filled. Prints the error JSON and returns the exit code (2 for unusable inputs; 1 for a missing
    blast entry, a token-less TOKEN-BLAST entry, empty touched_files or uncovered sites), else 0."""
    if not args.skill_root or not args.blast_json:
        print(json.dumps({
            "error": (
                "fill-address received FIX decision(s) but --skill-root/"
                "--blast-json is missing — cannot verify fix-impact "
                "closure (how-to-fix.md 'Fix-impact closure — cover the "
                "full blast radius'). No rows written."
            ),
            "fix_clusters": [d.get("cluster", "") for d in fix_decisions],
            "recovery": (
                "Re-run fill-address with --skill-root <target> "
                "--blast-json <path to this round's blast JSON "
                "(the 'blast' array this round's cluster-stage script "
                "printed — write it to a file first)>."
            ),
        }), file=sys.stderr)
        return 2

    if args.blast_json == "-":
        print(json.dumps({
            "error": "--blast-json must be a real file path, not '-'.",
        }), file=sys.stderr)
        return 2

    blast_path = Path(args.blast_json).expanduser()
    if not blast_path.is_file():
        print(json.dumps({
            "error": f"--blast-json not found: {blast_path}",
        }), file=sys.stderr)
        return 2
    try:
        blast_raw = json.loads(blast_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(json.dumps({
            "error": f"--blast-json is not valid JSON: {exc}",
        }), file=sys.stderr)
        return 2
    blast_list = (
        blast_raw.get("blast_radius", blast_raw)
        if isinstance(blast_raw, dict) else blast_raw
    )
    blast_by_cluster = {
        b.get("cluster", ""): b for b in blast_list if isinstance(b, dict)
    }

    import fix_blast as fbl  # noqa: E402 (scripts/ already on path)

    radius_failures: list[dict] = []
    for dec in fix_decisions:
        c_id = dec.get("cluster", "")
        entry = blast_by_cluster.get(c_id)
        if entry is None:
            radius_failures.append({
                "cluster": c_id,
                "error": (
                    "no blast entry for this cluster in --blast-json — "
                    "cannot verify fix-impact closure."
                ),
            })
            continue
        if entry.get("fix_class") != "TOKEN-BLAST":
            continue  # LOCAL: no mechanical grep to run

        # Every token of the cluster is re-checked, not only the first (fbl.blast_tokens).
        tokens = fbl.blast_tokens(entry)
        token = ", ".join(tokens)
        touched_files = dec.get("touched_files") or []
        if not tokens:
            radius_failures.append({
                "cluster": c_id,
                "error": "TOKEN-BLAST cluster has no token in --blast-json.",
            })
            continue
        if not touched_files:
            radius_failures.append({
                "cluster": c_id,
                "token": token,
                "error": (
                    "FIX decision for a TOKEN-BLAST cluster must include "
                    "a non-empty touched_files list."
                ),
            })
            continue

        # The cluster's own definition file, which fix_blast.py already counted as
        # touched when it computed the radius shown to the fixer ("auto_touched"),
        # stays touched here too, so both checks judge the same edit set.
        recheck_touched = list(dict.fromkeys(list(entry.get("auto_touched") or []) + list(touched_files)))
        exit_code, radius_result = fbl.run_check_fix_radius_all(
            skill_root=str(Path(args.skill_root).expanduser()),
            tokens=tokens,
            touched=",".join(recheck_touched),
            allow=args.allow,
            ignore_case=False,
            dry_run=False,
        )
        if exit_code != 0:
            radius_failures.append({
                "cluster": c_id,
                "token": token,
                "touched_files": touched_files,
                "uncovered": (radius_result or {}).get("uncovered", []),
                "error": (
                    "check_fix_radius.py found uncovered sites for this "
                    "token — the FIX did not cover the full blast radius."
                ),
            })

    if radius_failures:
        print(json.dumps({
            "error": (
                "fix-impact closure check FAILED for one or more FIX "
                "decisions — no rows written."
            ),
            "radius_failures": radius_failures,
            "recovery": (
                "Cover the listed uncovered sites (or, where a site legitimately "
                "keeps the token, re-run with --allow <files> and state the reason in "
                "the FIX address, per how-to-fix.md), update the decision's "
                "touched_files, and re-run fill-address."
            ),
        }), file=sys.stderr)
        return 1
    return 0


def _fill_address(args, ledger: Path) -> int:
    """--mode fill-address: fill the fixers' decisions into the round's PENDING rows of --phase and
    advance the marker (module docstring "fill-address")."""
    if not ledger.is_file():
        print(f"ERROR: ledger not found for fill-address: {ledger}", file=sys.stderr)
        return 2

    if args.fixer_transcript:
        # Read decisions from the fixer agents' transcripts (preferred path — no on-disk decisions
        # file needed). A round split into fixer batches has one transcript per batch; their
        # decisions are recorded together, so one call (and one marker write) covers the round.
        paths = [x.strip() for v in args.fixer_transcript for x in v.split(",") if x.strip()]
        decisions = []
        for tp in paths:
            try:
                decisions.extend(lc.fixer_decisions(tp))
            except (ValueError, OSError) as exc:
                print(f"ERROR: cannot read decisions from fixer transcript {tp!r}: {exc}",
                      file=sys.stderr)
                return 2
        if not decisions:
            # No transcript yielded a decision: the fixers' replies were lost or empty, not a
            # fixer skipping some clusters, so auto-pausing every PENDING row would record the
            # whole round as pauses. Refuse instead; partial decisions still auto-pause below.
            print(f"ERROR: no fixer transcript yielded any decision ({', '.join(paths)}); no rows "
                  "written. SendMessage each fixer to re-emit its {\"decisions\": [...]} object, "
                  "then re-run.", file=sys.stderr)
            return 2
        seen_ids: dict = {}
        for d in decisions:
            seen_ids[d.get("cluster", "")] = seen_ids.get(d.get("cluster", ""), 0) + 1
        dup_ids = sorted(c for c, n in seen_ids.items() if n > 1)
        if dup_ids:
            print(json.dumps({
                "error": "a cluster has decisions in more than one place; no rows written.",
                "duplicated": dup_ids,
                "recovery": "Each batch's fixer decides only its own clusters: SendMessage the "
                            "fixer that decided a cluster outside its batch to re-emit, then re-run.",
            }), file=sys.stderr)
            return 1
    else:
        try:
            data = json.load(sys.stdin)
        except json.JSONDecodeError as exc:
            print(f"ERROR: stdin is not valid JSON: {exc}", file=sys.stderr)
            return 2
        decisions = data.get("decisions", [])

    # Auto-pause: any PENDING row for this round+phase with NO matching
    # decision in the input is treated as ORCHESTRATOR-PAUSE — the fixer
    # skipped a cluster, so the orchestrator must resolve it (no silent drop).
    phase_lc_match = args.phase.strip().lower()
    ledger_text_fa = ledger.read_text(encoding="utf-8")
    pending_clusters_in_ledger = {
        row["cluster"]
        for row in lc.round_rows(ledger_text_fa, args.round)
        if row.get("phase", "").strip().lower() == phase_lc_match
        and lc.is_pending(row.get("address", ""))
    }
    decision_cluster_ids = {d.get("cluster", "") for d in decisions}
    for skipped_cid in sorted(
        pending_clusters_in_ledger - decision_cluster_ids,
        key=lambda c: int(c[1:]) if c[1:].isdigit() else 0,
    ):
        print(
            f"WARN: no fixer decision for cluster {skipped_cid}; "
            "auto-filling as ORCHESTRATOR-PAUSE",
            file=sys.stderr,
        )
        decisions.append({
            "cluster":  skipped_cid,
            "decision": "ORCHESTRATOR-PAUSE",
            "address":  (
                f"ORCHESTRATOR-PAUSE (no fixer decision returned for cluster "
                f"{skipped_cid} — orchestrator must resolve)"
            ),
        })

    # An empty decisions list with no PENDING rows has nothing to record. With PENDING rows it
    # still reaches this point holding one auto-filled ORCHESTRATOR-PAUSE per skipped cluster,
    # so an empty fixer reply can never silently drop a cluster.
    if not decisions:
        print(json.dumps({"warning": "no decisions in input", "rows_filled": 0}))
        return 0

    # Banned dismissal vocabulary: the same lint append_ledger.py applies (shared in
    # ledger_common), so a fixer's "already correct, no change" cannot reach the ledger via
    # fill-address either. Reject before writing ANY row.
    banned_errs = [
        e for d in decisions
        for e in lc.reject_banned_vocabulary(f"address for {d.get('cluster', '')}", d.get("address", ""))
    ]
    if banned_errs:
        print(json.dumps({
            "error": "banned dismissal vocabulary in fixer address(es); no rows written.",
            "details": banned_errs,
        }), file=sys.stderr)
        return 1

    # Pre-validate: FIX/STRENGTHEN addresses MUST be canonical (kind at a token
    # boundary — kind followed by " " or "("). fill-address is as strict as append:
    # a non-canonical address (e.g. "FIX: added X" with a colon) would be stored
    # verbatim and then tally as 0 FIX at close. Reject up front so the emitter (the
    # fixer) is forced to re-emit canonical "KIND (<file>: ...)" form — do NOT loosen
    # the tally to accept the variant. ORCHESTRATOR-PAUSE is normalized below, so skip
    # it here. Reject before writing ANY row (no partial fill).
    malformed_addr = [
        {"cluster": d.get("cluster", ""), "address": d.get("address", "")}
        for d in decisions
        if d.get("decision", "FIX").upper() != "ORCHESTRATOR-PAUSE"
        and not lc.address_kind_ok(d.get("address", ""))
    ]
    if malformed_addr:
        print(json.dumps({
            "error": "non-canonical fixer address(es) — fill-address rejects them (as append does); no rows written.",
            "malformed": malformed_addr,
            "required_format": (
                "each address must begin with a kind at a token boundary: "
                "'FIX (<file>: <summary>)' or 'STRENGTHEN (added at <file>:<lines>: \"...\")'. "
                "A colon after the kind (e.g. 'FIX:') is NOT accepted."
            ),
            "recovery": (
                "Ask the fixer (SendMessage the same agent) to re-emit these decisions with "
                "canonical addresses, or reformat them, then re-run fill-address."
            ),
        }), file=sys.stderr)
        return 1
    # ------------------------------------------------------------------
    fix_decisions = [
        d for d in decisions
        if d.get("decision", "FIX").upper() == "FIX"
    ]
    if fix_decisions:
        rc = _closure_failure(args, fix_decisions)
        if rc:
            return rc

    rows_filled: list[dict] = []
    rows_missing: list[str] = []
    has_orch_pause = False

    for dec in decisions:
        c_id    = dec.get("cluster", "")
        address = dec.get("address", "")
        decision_kind = dec.get("decision", "FIX").upper()

        if decision_kind == "ORCHESTRATOR-PAUSE":
            has_orch_pause = True

        # Validate address (ORCHESTRATOR-PAUSE gets ORCHESTRATOR-PAUSE form)
        if decision_kind == "ORCHESTRATOR-PAUSE":
            if not lc.address_kind_ok(address):
                address = f"ORCHESTRATOR-PAUSE ({address or c_id})"
        else:
            if not lc.address_kind_ok(address):
                print(
                    f"WARN: address for {c_id} is not a valid ADDRESS_KIND: {address!r}",
                    file=sys.stderr,
                )

        # Safety: strip forbidden chars
        address = address.replace("|", "/").replace("\n", " ").replace("\r", " ")

        found, msg = _fill_pending_row(ledger, args.round, c_id, address)
        if found:
            rows_filled.append({"cluster": c_id, "address": address, "detail": msg})
        else:
            rows_missing.append(c_id)
            print(f"WARN: {msg}", file=sys.stderr)

    # Determine marker
    # --reenter always routes the marker through prepass, including when a decision is an
    # ORCHESTRATOR-PAUSE: a pause leaves the fixer's other edits applied, and those still need
    # the prepass re-sweep before this tier resumes.
    phase_lc = "prepass" if args.reenter else args.phase.lower().replace(" ", "-")
    state = "orch-fixes" if has_orch_pause else "running"
    marker = f"{args.runtime} {phase_lc} {state} round-{args.round}"

    lc.write_marker(ledger, marker)

    result = {
        "mode":              "fill-address",
        "ledger":            str(ledger),
        "round":             args.round,
        "phase":             args.phase,
        "rows_filled":       len(rows_filled),
        "rows_missing":      rows_missing,
        "in_flight_marker":  f"in-flight:: {marker}",
        "rows":              rows_filled,
    }
    print(json.dumps(result, indent=2))
    return 0


def _cluster(args, ledger: Path) -> int:
    """--mode cluster: write one PENDING row per cluster read from stdin and advance the marker to
    "<phase> addressing round-<N>" (module docstring "cluster")."""
    default_address = "PENDING (considered-fix)"
    address = args.address if args.address else default_address

    # Validate address early (same token-boundary rule as append_ledger).
    _placeholder = lc.is_pending(address)
    if not _placeholder and not lc.address_kind_ok(address):
        print(
            f"ERROR: --address must start with one of {lc.ADDRESS_KINDS} at a token boundary "
            f"(or be the default placeholder 'PENDING (considered-fix)'): {address!r}",
            file=sys.stderr,
        )
        return 1

    # The ledger does not derive a flag prefix — flags arrive pre-assigned from upstream.
    phase = args.phase

    # Read cluster (+blast) JSON from stdin.
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(f"ERROR: stdin is not valid JSON: {exc}", file=sys.stderr)
        return 2

    clusters = data.get("clusters", [])
    blast_data: list[dict] = data.get("blast", [])

    if not clusters:
        print(json.dumps({"warning": "no clusters in input", "rows_written": 0}))
        return 0

    # The ledger is created only with its target recorded (append_ledger.py begin-round, or
    # prepass_run.py before its first sweep), so this writer refuses an absent ledger instead of
    # creating one with no `target::` line.
    if not ledger.is_file():
        print(f"ERROR: ledger not found for cluster: {ledger} (append_ledger.py begin-round creates it)",
              file=sys.stderr)
        return 2

    # Resume idempotency + id uniqueness. Only a call that writes PENDING placeholders supersedes
    # stale PENDING rows (a call writing ORCHESTRATOR-PAUSE rows must not delete the PENDING rows
    # the same pass just wrote). Then refuse any (round, cluster) id that already exists: ids
    # continue across the round, so a collision means the caller renumbered wrongly.
    superseded: list[str] = []
    if lc.is_pending(address):
        superseded = _drop_stale_pending(ledger, args.round, phase)
        if superseded:
            print(f"WARN: superseded stale PENDING row(s) {superseded} of round {args.round} "
                  f"({phase}) left by an interrupted earlier pass", file=sys.stderr)
    existing_ids = {r["cluster"] for r in lc.round_rows(ledger.read_text(encoding="utf-8"), args.round)}
    clashes = sorted(c.get("cluster", "") for c in clusters if c.get("cluster", "") in existing_ids)
    if clashes:
        print(f"ERROR: cluster id(s) {clashes} already exist in round {args.round}; cluster ids must "
              f"CONTINUE across every phase of the round (ledger_common.max_cluster_in_round).",
              file=sys.stderr)
        return 1

    # Read flags verbatim from each cluster — the ledger is a pure writer and never
    # assigns or renumbers flags.  Upstream stages are responsible:
    #   cluster_prepass.py  → assigns P-flags on each Prepass cluster's "flags" list
    #   cluster_enforce.py  → carries the reviewer flags code_review_collect.py assigned
    # A cluster arriving without a "flags" key is a pipeline bug — raise immediately
    # so the error surfaces at the culprit stage rather than silently writing wrong rows.
    flag_sets: list[list[str]] = []
    for c in clusters:
        c_id = c.get("cluster", "<unknown>")
        raw_flags = c.get("flags")
        if not raw_flags:
            print(
                f"ERROR: uncoded cluster reached the ledger: {c_id} — "
                f"flags must be assigned upstream (cluster_prepass for P-flags, "
                f"code_review_collect for reviewer flags).",
                file=sys.stderr,
            )
            return 1
        flag_sets.append(list(raw_flags))
    all_flags = [f for fs in flag_sets for f in fs]

    rows_written = []
    for cluster, flags in zip(clusters, flag_sets):
        c_id = cluster["cluster"]
        root_cause = cluster.get("root_cause", "")

        # Embed blast radius into the root_cause cell so the pre-fixer row
        # shows the full scope (the blast is determined before the row is
        # written and appended with it).
        blast_note = _blast_note_for_cluster(blast_data, c_id)
        if blast_note:
            root_cause_cell = (root_cause + blast_note).replace("|", "/")
        else:
            root_cause_cell = root_cause.replace("|", "/")

        # Safety: strip newlines from root_cause_cell
        root_cause_cell = root_cause_cell.replace("\n", " ").replace("\r", " ")

        flags_str = ",".join(flags)

        rc, msg = _append_row(
            ledger=ledger,
            runtime=args.runtime,
            rnd=args.round,
            phase=phase,
            cluster=c_id,
            root_cause=root_cause_cell,
            address=address,
            flags=flags_str,
        )
        if rc != 0:
            print(msg, file=sys.stderr)
            return rc
        rows_written.append({"cluster": c_id, "flags": flags, "row": msg})

    # Advance in-flight marker: clustering+append done → now <phase> addressing.
    phase_lc = phase.lower().replace(" ", "-")
    marker = f"{args.runtime} {phase_lc} addressing round-{args.round}"
    lc.write_marker(ledger, marker)

    result = {
        "ledger":           str(ledger),
        "round":            args.round,
        "phase":            phase,
        "clusters_written": len(rows_written),
        "superseded_pending": superseded,
        "flags_written":    all_flags,
        "in_flight_marker": f"in-flight:: {marker}",
        "rows":             rows_written,
    }
    print(json.dumps(result, indent=2))
    return 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(
        description="Ledger entry-point — consume cluster JSON, write PENDING rows or fill addresses."
    )
    ap.add_argument("ledger", help="Path to the audit ledger (must exist; append_ledger.py begin-round creates it).")
    ap.add_argument("--runtime", required=True, help="Runtime tag, e.g. 2025-01-15T09:00:00.")
    ap.add_argument("--round", type=int, required=True, help="Audit round number.")
    ap.add_argument(
        "--mode",
        default="cluster",
        choices=["cluster", "fill-address"],
        help=(
            "cluster (default): consume cluster JSON (+blast) from stdin, append PENDING rows "
            "with blast recorded, advance marker to '<phase> addressing round-<N>'. "
            "fill-address: fill real addresses into EXISTING PENDING rows matched by "
            "round+cluster; advance marker after filling."
        ),
    )
    ap.add_argument(
        "--phase",
        default=None,
        help=(
            "Phase name the rows belong to: Prepass or Code Review. REQUIRED for "
            "both modes. It selects "
            "which PENDING rows fill-address matches/auto-pauses and names the marker written."
        ),
    )
    ap.add_argument(
        "--reenter",
        action="store_true",
        default=False,
        help=(
            "fill-address only: the marker written after filling names the prepass phase "
            "('prepass running round-<N>', or 'prepass orch-fixes round-<N>' when a decision is "
            "ORCHESTRATOR-PAUSE) instead of <phase>, so the fixer's edits are re-swept from prepass."
        ),
    )
    ap.add_argument(
        "--fixer-transcript",
        action="append",
        default=None,
        metavar="PATH[,PATH...]",
        help=(
            "fill-address only: path to a fixer agent's JSONL transcript. "
            "When given, extract the final assistant message and parse the "
            "{\"decisions\":[...]} JSON from it — no stdin required. "
            "Repeat the option or give a comma list for a round split into several fixer batches; "
            "the decisions are recorded together. Falls back to stdin when absent."
        ),
    )
    ap.add_argument(
        "--allow",
        default="",
        metavar="FILES",
        help=(
            "fill-address only: comma-separated files where a TOKEN-BLAST token legitimately stays "
            "(passed to check_fix_radius.py --allow). Use only with a stated reason in the FIX address "
            "(references/how-to-fix.md 'Mechanical enforcement')."
        ),
    )
    ap.add_argument(
        "--address",
        default=None,
        help=(
            "Address value for every cluster row (cluster mode only). "
            "If omitted, defaults to: PENDING (considered-fix)"
        ),
    )
    ap.add_argument(
        "--skill-root",
        default=None,
        metavar="DIR",
        help=(
            "fill-address only: root directory of the target skill. Required "
            "whenever any decision is FIX — used to re-run check_fix_radius.py "
            "for TOKEN-BLAST clusters (see 'BLOCKING PRECONDITION' above)."
        ),
    )
    ap.add_argument(
        "--blast-json",
        default=None,
        metavar="PATH",
        help=(
            "fill-address only: path to the SAME blast JSON this round's "
            "'ledger_cascade cluster' call received (either {\"blast_radius\": "
            "[...]} as emitted by fix_blast.py, or a bare list). Supplies each "
            "cluster's fix_class/token so fill-address can mechanically "
            "re-verify TOKEN-BLAST fix-impact closure. Required whenever any "
            "decision is FIX. Must be a real file path — '-' is not accepted "
            "(stdin/--fixer-transcript already carry the decisions)."
        ),
    )
    args = ap.parse_args()

    ledger = Path(args.ledger).expanduser()

    if not args.phase:
        print(f"ERROR: --phase is required for --mode {args.mode} (Prepass or Code Review): "
              f"it selects which rows are matched and which marker is written.", file=sys.stderr)
        return 2

    if args.mode == "fill-address":
        return _fill_address(args, ledger)
    return _cluster(args, ledger)


if __name__ == "__main__":
    sys.exit(main())
