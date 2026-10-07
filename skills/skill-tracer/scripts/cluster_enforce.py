#!/usr/bin/env python3
"""cluster_enforce.py — Mandatory gate between orchestrator clustering and fixer dispatch.

Takes the verified flags (the JSON code_review_collect.py prints, whose "status" is
"verified-flags", passed as --verified-flags) and the
orchestrator's cluster assignment (cr-clusters-<N>.json), enforces two gates, then on
pass writes PENDING ledger rows, advances the marker, and stages the fixer prompt.

Gates:
  Gate 1 — no-drop:        every verified flag appears in exactly one orchestrator
                            cluster, and no cluster names a flag id the collector did not verify.
                            Each cluster also needs a distinct non-empty "cluster" id and a
                            non-empty "flags" list.
  Gate 2 — no-split-blast: no advisory blast group (computed from verified flags) is split
                            across multiple orchestrator clusters.

Exit codes:
  1  A gate failed, --verified-flags is not a "verified-flags" status JSON, or staging / the
     ledger_cascade cluster call failed: JSON to stderr, a gate object ({"gate", "message", ...})
     or {"error": ...} (the ledger_cascade failure adds "stderr").
  2  Invocation error: --target is not a directory, or --verified-flags / --clusters is missing,
     not valid JSON, or not a JSON object or array: {"error": ...} to stderr.
On gate failure: print JSON to stderr naming the violation, exit 1.
On gate pass:
  - Renumber the orchestrator's clusters to CONTINUE the round's C-sequence (ids are placeholders in
    cr-clusters-<N>.json; earlier phases of the round already hold C1..Ck) and report the mapping.
  - Build clusters+blast payload (radius = member locs ∪ advisory group sites; preserve
    any `guidance` key from the orchestrator cluster).
  - Stage the fixer batches (lc.stage_fixer_batches, label "code-review-b<k>"): 12 clusters or
    fewer are one batch; only above 12 are the code clusters and the doc-only clusters each
    chunked separately into batches of at most 12, code batches first. Model opus when the pass has more than 15 clusters,
    sonnet otherwise; one staged prompt per batch. Staging runs before any ledger write.
  - Call `ledger_cascade --mode cluster --phase "Code Review"` to write PENDING rows.
  - Call lc.write_marker(ledger, "<runtime> code-review addressing round-<N>").
  - Print result JSON to stdout with status "needs-fix", batches ([{batch, model, clusters,
    staged_prompt}], dispatched in sequence), staged_fixer_prompt (batch 1's prompt), blast (the
    array fill-address needs written to a file), cluster_id_map and then[].
  - Exit 0.

Args:
    ledger           Path to the audit ledger.
    --round          Audit round number (int).
    --runtime        Runtime tag (YYYY-MM-DDTHH:MM:SS; the minute form is also accepted).
    --target         Target skill directory.
    --out-dir        Scratch directory for staged prompt + temp files.
    --verified-flags Path to verified-flags JSON (or - to read from stdin).
    --clusters       Path to orchestrator clusters JSON file.

Pure stdlib. Python 3.9+.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

# ---------------------------------------------------------------------------
# Bootstrap: ensure scripts/ dir is on sys.path
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent

if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import ledger_common as lc

_LEDGER_CASCADE = _HERE / "ledger_cascade.py"


# Advisory blast groups come from ledger_common (shared with code_review_collect.py, which
# reports them): the "no-split-blast" gate must judge the very groups the collector showed.
import re as _re

_compute_advisory_groups = lc.compute_advisory_groups


# ---------------------------------------------------------------------------
# Gate 1 — no-drop
# ---------------------------------------------------------------------------

def check_no_drop(
    verified_flag_ids: Set[str],
    clusters: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Gate 1: every verified flag is in exactly one cluster, and every cluster has a distinct
    non-empty id and a non-empty flags list.

    WHY the structure check lives here: a cluster with no flags adds nothing to the coverage sets
    below, and two clusters sharing an id collapse into one entry of the renumbering map and of
    Gate 2's flag-to-cluster map, so neither would otherwise be caught before staging.

    Returns None on pass, or an error dict on fail.
    """
    malformed: List[str] = []
    seen_ids: Set[str] = set()
    for i, c in enumerate(clusters, 1):
        if not isinstance(c, dict):
            malformed.append(f"entry {i} is not an object")
            continue
        cid = c.get("cluster")
        flags = c.get("flags")
        if not isinstance(cid, str) or not cid.strip():
            malformed.append(f"entry {i} has no cluster id")
        elif cid in seen_ids:
            malformed.append(f"cluster id {cid} is used more than once")
        else:
            seen_ids.add(cid)
        if not isinstance(flags, list) or not flags:
            malformed.append(f"cluster {cid if isinstance(cid, str) and cid.strip() else i} has an empty or missing flags list")
    if malformed:
        return {
            "gate":       "no-drop",
            "dropped":    [],
            "extra":      [],
            "duplicated": [],
            "message": (
                "Gate 1 FAILED: the clusters file is malformed: " + "; ".join(malformed) + ". "
                "Each cluster needs a distinct non-empty \"cluster\" id and a non-empty \"flags\" list."
            ),
        }

    assigned: List[str] = []
    for c in clusters:
        assigned.extend(c["flags"])

    assigned_set = set(assigned)

    # Detect each type of violation
    dropped     = sorted(verified_flag_ids - assigned_set)
    extra       = sorted(assigned_set - verified_flag_ids)
    seen: Dict[str, int] = {}
    for f in assigned:
        seen[f] = seen.get(f, 0) + 1
    duplicated  = sorted(k for k, v in seen.items() if v > 1)

    if dropped or extra or duplicated:
        return {
            "gate":        "no-drop",
            "dropped":     dropped,
            "extra":       extra,
            "duplicated":  duplicated,
            "message": (
                "Gate 1 FAILED: orchestrator clusters do not exactly cover the verified flags. "
                f"dropped={dropped}, extra={extra}, duplicated={duplicated}"
            ),
        }
    return None


# ---------------------------------------------------------------------------
# Gate 2 — no-split-blast
# ---------------------------------------------------------------------------

def check_no_split_blast(
    advisory_groups: List[Dict[str, Any]],
    clusters: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Gate 2: no advisory blast group is split across multiple orchestrator clusters.

    Returns None on pass, or an error dict on fail.
    """
    # Build map: flag_id → cluster_id
    flag_to_cluster: Dict[str, str] = {}
    for c in clusters:
        cid = c.get("cluster", "?")
        for f in c.get("flags", []):
            flag_to_cluster[f] = cid

    split_violations: List[Dict[str, Any]] = []
    for group_info in advisory_groups:
        group_flags = group_info["group"]
        shared      = group_info["shared"]
        clusters_hit = {flag_to_cluster.get(f) for f in group_flags if f in flag_to_cluster}
        clusters_hit.discard(None)
        if len(clusters_hit) > 1:
            split_violations.append({
                "advisory_group": group_flags,
                "shared":         shared,
                "split_into":     sorted(clusters_hit),
            })

    if split_violations:
        return {
            "gate":             "no-split-blast",
            "split_violations": split_violations,
            "message": (
                "Gate 2 FAILED: one or more advisory blast groups are split across "
                "multiple orchestrator clusters. Each advisory group must be wholly "
                "within ONE cluster. Merge the listed clusters."
            ),
        }
    return None


# ---------------------------------------------------------------------------
# Build blast payload for cluster_enforce pass
#
# blast radius per cluster = union of member locs + advisory group sites
# (i.e. all locs in the cluster, plus any locs of advisory-group siblings)
# ---------------------------------------------------------------------------

def _build_blast(
    clusters: List[Dict[str, Any]],
    advisory_groups: List[Dict[str, Any]],
    all_flags_by_id: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Compute blast radius per orchestrator cluster.

    Radius = member locs (from the verified flags) ∪ advisory group sites
    (locs of all flags that share an advisory group with any cluster member).

    The advisory_groups list links flags sharing a file:line locus (reviewer flags carry no token); the
    blast for a cluster that contains ANY member of an advisory group must
    also include the locs of ALL flags in that group (which per Gate 2 are
    in the same cluster anyway, but we enumerate for completeness).
    """
    # flag_id → set of advisory-group indices that include it
    flag_to_groups: Dict[str, List[int]] = defaultdict(list)
    for gi, ag in enumerate(advisory_groups):
        for f in ag["group"]:
            flag_to_groups[f].append(gi)

    blast: List[Dict[str, Any]] = []
    for c in clusters:
        cid    = c.get("cluster", "?")
        c_flags = c.get("flags", [])

        # Collect member locs
        member_locs: List[str] = []
        seen_locs: Set[str] = set()
        for fid in c_flags:
            fdata = all_flags_by_id.get(fid, {})
            loc = lc.flag_locus(fdata.get("file", ""), fdata.get("claim", ""), fdata.get("target", ""))
            if loc and loc not in seen_locs:
                seen_locs.add(loc)
                member_locs.append(loc)

        # Add locs of advisory-group siblings (all in same cluster per Gate 2,
        # but included for explicitness in the blast record)
        advisory_extra: List[str] = []
        seen_advisory_groups: Set[int] = set()
        for fid in c_flags:
            for gi in flag_to_groups.get(fid, []):
                if gi in seen_advisory_groups:
                    continue
                seen_advisory_groups.add(gi)
                ag = advisory_groups[gi]
                for afid in ag["group"]:
                    if afid not in c_flags:
                        fdata = all_flags_by_id.get(afid, {})
                        loc = lc.flag_locus(fdata.get("file", ""), fdata.get("claim", ""), fdata.get("target", ""))
                        if loc and loc not in seen_locs:
                            seen_locs.add(loc)
                            advisory_extra.append(loc)

        radius = member_locs + advisory_extra

        blast.append({
            "cluster":   cid,
            "fix_class": "LOCAL",
            "reason": (
                "Code Review finding: fix is scoped to the flagged location(s). "
                "Radius includes all member locs plus any advisory blast sites."
            ),
            "radius": radius,
        })

    return blast


# ---------------------------------------------------------------------------
# Enrich orchestrator clusters with member data from verified flags
# ---------------------------------------------------------------------------

def _enrich_clusters(
    clusters: List[Dict[str, Any]],
    all_flags_by_id: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Add root_cause, members, check, token fields from verified-flag data.

    The orchestrator's cr-clusters JSON may only carry cluster + flags (+ optional guidance).
    We enrich each cluster with the detail needed by ledger_cascade and assemble_fix_prompt.
    """
    enriched: List[Dict[str, Any]] = []
    for c in clusters:
        cid     = c.get("cluster", "?")
        c_flags = c.get("flags", [])
        guidance = c.get("guidance", "")

        # Build members
        members: List[Dict[str, str]] = []
        seen_tags: Dict[str, None] = {}
        seen_agents: Set[str] = set()
        for fid in c_flags:
            fdata = all_flags_by_id.get(fid, {})
            file_   = fdata.get("file", "")
            target_ = fdata.get("target", "")
            claim_  = fdata.get("claim", "")
            tag_    = fdata.get("tag", "")
            loc = lc.flag_locus(file_, claim_, target_)
            if tag_:
                seen_tags.setdefault(tag_, None)
            # A flag id is the agent's flag prefix (letter + agent digit: G1, G2) followed by its
            # number (code_review_collect.py), so G212 is agent G2's flag 12.
            agent_m = _re.match(r"[A-Za-z]+\d?", fid or "")
            seen_agents.add(agent_m.group(0) if agent_m else "?")
            members.append({
                "agent_flag": fid,
                "loc":        loc,
                "issue_tag":  tag_,
                "claim":      claim_,
                "target":     target_,
            })

        checks_label  = ", ".join(seen_tags)
        agents_label  = ", ".join(sorted(seen_agents))
        rep = members[0] if members else {}
        # Root cause = the representative's file:line locus, then its Target text as the
        # description (kept apart from the locus), then the tags.
        rep_desc = rep.get("target", "")
        root_cause = (
            f"{rep.get('loc', '?')}"
            + (f" — {rep_desc}" if rep_desc else "")
            + f" [tags: {checks_label}; agents: {agents_label}]"
        )

        ec: Dict[str, Any] = {
            "cluster":    cid,
            "check":      checks_label,
            "token":      "",
            "fix_class":  "LOCAL",
            "root_cause": root_cause,
            "flags":      c_flags,
            "members":    members,
        }
        if guidance:
            ec["guidance"] = guidance

        enriched.append(ec)
    return enriched


# ---------------------------------------------------------------------------
# Blast expansion: code→prose doc sites
# ---------------------------------------------------------------------------

# Matches filenames ending in .md / .json / .txt, optionally prefixed with
# "references/" — e.g. "filename-conventions.md", "references/arbiter-prompt.md"
_DOC_REF_RE = _re.compile(
    r'(?:references/)?([A-Za-z0-9_.\-]+\.(?:md|json|txt))'
)


def _extract_doc_refs(findings: List[Dict[str, Any]]) -> Set[str]:
    """Extract doc-file basenames explicitly named in findings' claim + target strings."""
    basenames: Set[str] = set()
    for f in findings:
        for field in ("claim", "target"):
            text = f.get(field) or ""
            for m in _DOC_REF_RE.finditer(text):
                basenames.add(m.group(1))
    return basenames


def _expand_blast_with_doc_sites(
    blast: List[Dict[str, Any]],
    enriched_clusters: List[Dict[str, Any]],
    all_flags_by_id: Dict[str, Dict[str, Any]],
    skill_root: Path,
) -> None:
    """Mutate blast entries to add doc blast sites (enriched_clusters is only read, for each cluster's flag ids).

    For each cluster whose member locs include a code file (scripts/ or .py),
    extract doc-file basenames explicitly named in findings' claim/target strings,
    resolve each to an existing file under <skill_root> (checking references/ first,
    then skill_root directly), and record those resolved paths as doc_sites.
    """
    # Build map cluster_id → enriched_cluster for mutation
    ec_by_id: Dict[str, Dict[str, Any]] = {ec["cluster"]: ec for ec in enriched_clusters}

    for blast_entry in blast:
        cid = blast_entry["cluster"]
        radius = blast_entry.get("radius", [])

        # Does this cluster touch any code file?
        # A member radius entry is a "<relfile>:<line>" locus (lc.flag_locus) or a bare file, so
        # the code-file test reads the file part before the first ":".
        has_code = any(
            ("scripts/" in loc.split(":", 1)[0] or loc.split(":", 1)[0].endswith(".py"))
            for loc in radius
        )
        if not has_code:
            continue

        # Gather all flag data for this cluster
        ec = ec_by_id.get(cid, {})
        flag_ids: List[str] = ec.get("flags", [])
        findings = [all_flags_by_id[fid] for fid in flag_ids if fid in all_flags_by_id]

        # Extract doc basenames named in findings
        basenames = _extract_doc_refs(findings)
        if not basenames:
            continue

        # Resolve each basename to an existing file under skill_root.
        # Check references/<basename> first, then <skill_root>/<basename>.
        # Exclude code files and the cluster's own member files. A radius entry is a
        # "<relfile>:<line>" locus or a path, so it is reduced to its resolved file before the
        # comparison with each resolved doc path.
        member_files: Set[str] = set()
        for loc in radius:
            fpart = Path(loc.split(":", 1)[0])
            member_files.add(str((fpart if fpart.is_absolute() else skill_root / fpart).resolve()))
        doc_sites: List[str] = []
        seen_doc_paths: Set[str] = set()
        for bn in sorted(basenames):
            resolved: Optional[Path] = None
            candidate_refs = skill_root / "references" / bn
            candidate_root = skill_root / bn
            if candidate_refs.is_file():
                resolved = candidate_refs
            elif candidate_root.is_file():
                resolved = candidate_root
            if resolved is None:
                continue
            rstr = str(resolved)
            # Exclude code files
            if rstr.endswith(".py") or "/scripts/" in rstr:
                continue
            # Exclude a doc that is already one of the cluster's member files
            if str(resolved.resolve()) in member_files:
                continue
            if rstr not in seen_doc_paths:
                seen_doc_paths.add(rstr)
                doc_sites.append(rstr)

        if not doc_sites:
            continue

        # Update blast entry
        blast_entry["doc_sites"] = doc_sites
        # Extend radius with new doc sites (deduplicated)
        existing_radius = set(radius)
        for ds in doc_sites:
            if ds not in existing_radius:
                radius.append(ds)
                existing_radius.add(ds)
        blast_entry["radius"] = radius



# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Mandatory gate: verify orchestrator clusters cover all verified flags "
            "without splitting advisory blast groups, then write PENDING rows and "
            "stage the fixer prompt."
        )
    )
    ap.add_argument("ledger", help="Path to the audit ledger.")
    ap.add_argument("--round",          required=True, type=int, help="Audit round number.")
    ap.add_argument("--runtime",        required=True, help="Runtime tag (YYYY-MM-DDTHH:MM:SS; the minute form is also accepted).")
    ap.add_argument("--target",         required=True, help="Target skill directory.")
    ap.add_argument("--out-dir",        required=True, help="Scratch directory.")
    ap.add_argument(
        "--verified-flags",
        required=True,
        metavar="PATH|-",
        help="Path to verified-flags JSON (code_review_collect.py output), or - for stdin.",
    )
    ap.add_argument(
        "--clusters",
        required=True,
        metavar="PATH",
        help='Path to orchestrator clusters JSON: {"clusters":[{"cluster":"C#","flags":[...],"guidance":"<opt>"}]}.',
    )
    args = ap.parse_args()

    ledger     = Path(args.ledger).expanduser()
    skill_root = Path(args.target).expanduser().resolve()
    out_dir    = Path(args.out_dir).expanduser()
    rnd        = args.round
    runtime    = args.runtime

    if not skill_root.is_dir():
        print(
            json.dumps({"error": f"--target is not a directory: {skill_root}"}),
            file=sys.stderr,
        )
        return 2

    out_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Load verified-flags
    # ------------------------------------------------------------------
    if args.verified_flags == "-":
        try:
            vf_data = json.load(sys.stdin)
        except json.JSONDecodeError as exc:
            print(json.dumps({"error": f"stdin is not valid JSON: {exc}"}), file=sys.stderr)
            return 2
    else:
        vf_path = Path(args.verified_flags).expanduser()
        if not vf_path.is_file():
            print(json.dumps({"error": f"--verified-flags not found: {vf_path}"}), file=sys.stderr)
            return 2
        try:
            vf_data = json.loads(vf_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(json.dumps({"error": f"--verified-flags is not valid JSON: {exc}"}), file=sys.stderr)
            return 2

    # Accept either the full verified-flags JSON (with "flags" key) or a bare list
    if isinstance(vf_data, list):
        all_flags: List[Dict[str, Any]] = vf_data
    elif isinstance(vf_data, dict):
        # code_review_collect.py also prints "code-review-clean" and "changed-scope-clean" (no
        # flags): clustering them would advance the marker to "addressing" with nothing to fix.
        if vf_data.get("status") != "verified-flags":
            print(
                json.dumps({
                    "gate": "verified-flags",
                    "message": (
                        f"--verified-flags status is {vf_data.get('status')!r}, not 'verified-flags': "
                        "there are no flags to cluster; follow that status's own next step."
                    ),
                }),
                file=sys.stderr,
            )
            return 1
        all_flags = vf_data.get("flags", [])
    else:
        print(json.dumps({"error": "verified-flags must be a JSON object or array"}), file=sys.stderr)
        return 2

    verified_flag_ids: Set[str] = {f.get("agent_flag", "") for f in all_flags if f.get("agent_flag")}
    all_flags_by_id: Dict[str, Dict[str, Any]] = {
        f.get("agent_flag", ""): f for f in all_flags if f.get("agent_flag")
    }

    # ------------------------------------------------------------------
    # Load orchestrator clusters
    # ------------------------------------------------------------------
    clusters_path = Path(args.clusters).expanduser()
    if not clusters_path.is_file():
        print(json.dumps({"error": f"--clusters not found: {clusters_path}"}), file=sys.stderr)
        return 2
    try:
        cl_data = json.loads(clusters_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(json.dumps({"error": f"--clusters is not valid JSON: {exc}"}), file=sys.stderr)
        return 2

    if isinstance(cl_data, list):
        orch_clusters: List[Dict[str, Any]] = cl_data
    elif isinstance(cl_data, dict):
        orch_clusters = cl_data.get("clusters", [])
    else:
        print(json.dumps({"error": "--clusters must be a JSON object or array"}), file=sys.stderr)
        return 2

    # ------------------------------------------------------------------
    # Gate 1 — no-drop
    # ------------------------------------------------------------------
    err1 = check_no_drop(verified_flag_ids, orch_clusters)
    if err1:
        print(json.dumps(err1, indent=2), file=sys.stderr)
        return 1

    # ------------------------------------------------------------------
    # Gate 2 — no-split-blast
    # ------------------------------------------------------------------
    advisory_groups = _compute_advisory_groups(all_flags)
    err2 = check_no_split_blast(advisory_groups, orch_clusters)
    if err2:
        print(json.dumps(err2, indent=2), file=sys.stderr)
        return 1

    # ------------------------------------------------------------------
    # Gates passed — enrich clusters and build blast
    # ------------------------------------------------------------------
    # Cluster ids CONTINUE the round's sequence across phases (ledger_common.max_cluster_in_round):
    # earlier Prepass clusters of this round already hold C1..Ck, so the ids in
    # cr-clusters-<N>.json are placeholders and are renumbered here.
    first_id = lc.max_cluster_in_round(ledger, rnd) + 1
    cluster_id_map: Dict[str, str] = {}
    for i, c in enumerate(orch_clusters):
        new_id = f"C{first_id + i}"
        cluster_id_map[str(c.get("cluster", "?"))] = new_id
        c["cluster"] = new_id

    enriched_clusters = _enrich_clusters(orch_clusters, all_flags_by_id)
    blast = _build_blast(enriched_clusters, advisory_groups, all_flags_by_id)

    # ------------------------------------------------------------------
    # Blast expansion: code→prose doc sites
    # ------------------------------------------------------------------
    _expand_blast_with_doc_sites(blast, enriched_clusters, all_flags_by_id, skill_root)

    # ------------------------------------------------------------------
    # Stage the fixer prompts, one per batch
    # WHY: staging runs before any ledger write, so a staging failure (exit 1) leaves the ledger
    # and marker untouched and the re-run renumbers from the same first id instead of adding a
    # second set of PENDING rows.
    # ------------------------------------------------------------------
    try:
        batches = lc.stage_fixer_batches(
            clusters=enriched_clusters,
            blast=blast,
            skill_root=skill_root,
            rnd=rnd,
            runtime=runtime,
            out_dir=out_dir,
            label="code-review",
            run_rnd=lc.run_round(ledger, rnd),
        )
    except RuntimeError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1

    # ------------------------------------------------------------------
    # Write PENDING rows via ledger_cascade --mode cluster --phase "Code Review"
    # ------------------------------------------------------------------
    pending_payload = {
        "clusters": enriched_clusters,
        "blast":    blast,
    }
    pending_cmd = [
        sys.executable, str(_LEDGER_CASCADE),
        str(ledger),
        "--runtime", runtime,
        "--round",   str(rnd),
        "--mode",    "cluster",
        "--phase",   "Code Review",
    ]
    pending_proc = subprocess.run(
        pending_cmd,
        input=json.dumps(pending_payload),
        capture_output=True,
        text=True,
    )
    if pending_proc.returncode != 0:
        print(
            json.dumps({
                "error": (
                    f"ledger_cascade cluster (Code Review) exited "
                    f"{pending_proc.returncode}"
                ),
                "stderr": pending_proc.stderr.strip(),
            }),
            file=sys.stderr,
        )
        return 1

    # ------------------------------------------------------------------
    # Advance marker: "<runtime> code-review addressing round-<N>"
    # ------------------------------------------------------------------
    lc.write_marker(ledger, f"{runtime} code-review addressing round-{rnd}")

    # ------------------------------------------------------------------
    # Emit result JSON
    # ------------------------------------------------------------------
    blast_file = f"{out_dir}/blast-round-{rnd}-{lc.runtime_slug(runtime)}.json"
    close_then = (
        "Read its `gate` object — if gate.continue is false go to SKILL.md \"Present result\" (tmp cleanup, merge-check, per-round summary) with the stop reason, "
        f"otherwise run: python3 .../scripts/append_ledger.py begin-round <ledger> --round {rnd + 1} "
        f"--runtime <RT> --target {skill_root} and start round {rnd + 1} at Prepass, since this sweep's findings were addressed and "
        "the next round is the confirming one."
    )
    report = lc.batch_report(batches)
    transcripts = ",".join(f"<batch-{b['batch']}-fixer-transcript>" for b in report)
    result = {
        "status":              "needs-fix",
        "staged_fixer_prompt": report[0]["staged_prompt"] if report else None,
        "batches":             report,
        "cluster_id_map":      cluster_id_map,
        "blast":               blast,
        "then": [
            f"Dispatch the {len(report)} fixer batch(es) in \"batches\" ONE AT A TIME, in order (never in parallel: they may edit the same files): before each batch k, run: python3 .../scripts/post_fix_gate.py snapshot --target {skill_root} --out {out_dir}/gate-{rnd}-b<k>-<RUN_TIMESTAMP>.json; then, for each, one fixer (general-purpose, the batch's \"model\", edits ONLY <target>) pointed at the batch's staged_prompt with the Fixer provenance wording in references/dispatch.md (not a bare 'read this file' pointer). The fixer's decisions use the renumbered cluster ids in cluster_id_map.",
            f"After each fixer returns, run: python3 .../scripts/check_decisions.py --fixer-transcript <its transcript> --expect <the batch's cluster ids, comma-separated>. On exit 1, SendMessage the same fixer with the reported problems and ask it to re-emit its decisions, then check again. Once it exits 0, run: python3 .../scripts/post_fix_gate.py check --target {skill_root} --snapshot <that batch's gate snapshot> --fixer-transcript <that batch's transcript>; on exit 1 follow references/dispatch.md \"Post-fix gate\" (inner passes, then ORCHESTRATOR-PAUSE). Dispatch the next batch once the decision check exits 0 and `check` has exited 0 or its problems are recorded as ORCHESTRATOR-PAUSE.",
            f"Write this result's \"blast\" array to {blast_file}, as {{\"blast_radius\": <the blast array>}} — fill-address requires --skill-root/--blast-json whenever any decision is FIX, but Code Review clusters are LOCAL with no token, so it re-checks nothing for them: closure for a Code Review FIX rests on the fixer's own check_fix_radius.py run (references/how-to-fix.md \"Fix-impact closure\").",
            f"Run: python3 .../scripts/ledger_cascade.py <ledger> --mode fill-address --phase \"Code Review\" --round {rnd} --runtime <RT> --fixer-transcript {transcripts} --skill-root {skill_root} --blast-json {blast_file}   (every batch's transcript in one call; NO --reenter for code-review fixes; no on-disk decisions file needed)",
            f"Run: python3 .../scripts/doc_lint.py --target {skill_root}   (advisory doc lint: for each finding that is real, fix it and record a 'doc-lint' FIX row with append_ledger.py append; exits 0 whatever it finds — does NOT block close).",
            f"Run: python3 .../scripts/append_ledger.py check-pauses <ledger>. If any ORCHESTRATOR-PAUSE/USER-PAUSE is open, you CANNOT close — resolve each (orchestrator decides the fix from the README intent; promote to USER-PAUSE only if genuine user attention is truly needed), apply it, and append a row whose Address says 'resolves ORCHESTRATOR-PAUSE <flag>'.",
            f"Run: python3 .../scripts/cleanup_tmp_prompts.py --run-timestamp \"<RT>\" --dir {out_dir}  (scoped to this run's <RUN_TIMESTAMP>; never --all — the out-dir is shared).",
            f"Run: python3 .../scripts/append_ledger.py close-round <ledger> --round {rnd}  (it REFUSES if a pause is open, or if the round has no FIX row: when every finding was a legitimate STRENGTHEN, add --strengthen-only \"<reason naming the how-to-fix.md case>\"). " + close_then,
        ],
    }
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
