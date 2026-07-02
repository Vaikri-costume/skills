"""drive_organizer.bootstrap — split from the original organizer.py (pure structural move, no behavior change)."""
from __future__ import annotations
import json
import os
import sys
from pathlib import Path

from drive_organizer import paths_config
from drive_organizer.paths_config import (
    _atomic_write,
    _effective_atomic_signatures,
    _effective_batch_size,
    _effective_scan_file_limit,
    _safe_dest,
)
from drive_organizer.content_peek import (
    peek_content,
    should_skip,
)


def _atomic_marker(p: Path, root: "Path | None" = None) -> "str | None":
    """Return a short marker string if folder p is an atomic unit, else None.

    Data-driven from the merged atomic-signature set (shipped
    references/atomic-signatures.json + any per-drive config.json
    `atomic_signatures_extra`) instead of hardcoded constants/if-statements — same
    external behavior/return values, same probe order (dir_names -> suffixes ->
    marker_files -> marker_pairs) as the original hardcoded version. `root` resolves
    which drive's config.json extension applies; callers with a root/drive variable
    already in scope MUST pass it explicitly (never rely on the implicit
    paths_config._EFFECTIVE_ROOT fallback inside _effective_atomic_signatures — that
    fragility was flagged and fixed in a prior review)."""
    sig = _effective_atomic_signatures(root)
    n = p.name
    if n in sig["dir_names"]:
        return n
    if n.endswith(tuple(sig["suffixes"])):
        return "bundle"
    try:
        for mf in sig["marker_files"]:
            probe, kind, marker = mf["probe"], mf["kind"], mf["marker"]
            target = p / probe
            if (kind == "file" and target.is_file()) or (kind == "dir" and target.is_dir()) \
               or (kind not in ("file", "dir") and target.exists()):
                return marker
        for mp in sig["marker_pairs"]:
            probes, kind, marker = mp["probes"], mp["kind"], mp["marker"]
            if kind == "file":
                ok = all((p / probe).is_file() for probe in probes)
            else:
                ok = all((p / probe).is_dir() for probe in probes)
            if ok:
                return marker
    except (PermissionError, OSError):
        pass
    return None


def _detect_atomic_units(root: Path) -> list:
    """Walk the tree and flag atomic-unit folders (without descending into them).
    Returns {folder, name, marker, file_count, locked}. The user approves these in
    the bootstrap walkthrough; on approval they're written locked to entities.json."""
    from drive_organizer.entities_rules import _locked_atomic_names, _should_prune_subdir
    root = Path(root)
    locked = _locked_atomic_names(root)
    out, skip = [], {".organizer"}
    for cur, dirs, files in os.walk(root):
        cp = Path(cur)
        keep = []
        for d in dirs:
            if d in skip:
                continue
            dp = cp / d
            marker = _atomic_marker(dp, root)
            if marker:
                try:
                    rel = str(dp.relative_to(root))
                    # Count direct children only — a full rglob would recurse huge
                    # node_modules/.git trees of a locked unit just to report a count.
                    fc = sum(1 for c in dp.iterdir() if c.is_file())
                except (PermissionError, OSError):
                    rel, fc = str(dp), 0
                out.append({"folder": rel, "name": d, "marker": marker,
                            "file_count": fc, "locked": d in locked})
                # do NOT descend into an atomic unit
            elif _should_prune_subdir(d, cp, locked, root):
                # Non-atomic-marker but otherwise prunable (dot/underscore, locked-atomic
                # name, external/shared-library): use the SAME shared predicate the other
                # walk sites use so pruning stays in sync — don't descend, don't emit.
                continue
            else:
                keep.append(d)
        dirs[:] = keep
    return out


def _bootstrap_candidates(root: Path, mode: str = "cold-start",
                          sample_k: int = 5, limit: int = 250) -> dict:
    """Enumerate folders to infer rules for. Candidates = folders that hold files
    but have no rule, excluding locked-atomic / external / staging. Each carries a
    sample of K files (name + content_peek + ext) for Claude to infer from. In audit
    mode, additionally flag ruled folders whose sampled file routes elsewhere (drift)."""
    from drive_organizer.classify_propose import _auto_classify_entry, _build_rules_index
    from drive_organizer.entities_rules import _coverage_gaps, _locked_atomic_names, _should_prune_subdir
    root = Path(root)
    index, dest_set = _build_rules_index(root)
    locked_atomic = _locked_atomic_names(root)
    skip = {".organizer", "Archive", "_Inbox"}
    candidates, drift = [], []
    # C4: pruning uses _should_prune_subdir (shared with _coverage_gaps). staging names
    # are checked separately (they live in the local `skip` set) so the predicate handles
    # dot/underscore + locked-atomic + atomic-marker + external only.
    for cur, dirs, files in os.walk(root):
        cp = Path(cur)
        # prune: staging names first, then shared structural predicate
        dirs[:] = [d for d in dirs
                   if d not in skip and not _should_prune_subdir(d, cp, locked_atomic, root)]
        try:
            rel = "" if cp == root else str(cp.relative_to(root))
        except Exception:
            continue
        if rel == "" or any(part in skip for part in Path(rel).parts):
            continue
        real_files = [f for f in files if not should_skip(cp / f)]
        if not real_files:
            continue
        has_rule = (cp / ".tidy-rules.json").exists() or rel in dest_set
        # sample
        sample = []
        for fn in real_files[:sample_k]:
            fp = cp / fn
            peek = None
            try:
                peek = peek_content(fp)
            except Exception:
                pass
            sample.append({"name": fn, "ext": fp.suffix.lower(), "peek": (peek or "")[:200]})
        if not has_rule:
            candidates.append({
                "folder": rel, "name": cp.name, "parent": str(Path(rel).parent) if Path(rel).parent != Path(".") else "",
                "file_count": len(real_files), "sample": sample,
            })
        elif mode == "audit" and sample:
            # quick drift flag: does a sampled file route somewhere other than here?
            e = {"filename": sample[0]["name"], "current_path": str(cp / sample[0]["name"]),
                 "is_image": False, "extension": sample[0]["ext"]}
            dest, _r = _auto_classify_entry(e, root, index, dest_set)
            # dest is a destination PATH; the "already-placed" case always returns
            # dest == rel (the file's own folder), so `dest != rel` alone excludes it —
            # no need to compare dest against the reason string (which it can never equal).
            if dest and dest != rel:
                drift.append({"folder": rel, "sampled": sample[0]["name"], "matches_instead": dest})
    batch_size = _effective_batch_size(root)
    capped = candidates[:limit]
    for i, c in enumerate(capped):
        c["batch"] = i // batch_size
    return {"mode": mode, "n_candidates": len(candidates), "emitted": len(capped),
            "n_batches": (len(capped) + batch_size - 1) // batch_size, "candidates": capped,
            "drift": drift, "dropped": max(0, len(candidates) - len(capped))}


def _bootstrap_apply(root: Path, proposed: dict) -> dict:
    """Write approved bootstrap proposals: rules into each folder's PARENT
    .tidy-rules.json (folderName=leaf), and entity metadata into entities.json."""
    from drive_organizer.classify_propose import _build_rules_index
    from drive_organizer.cleanup_reconcile import _ensure_in_suffix
    from drive_organizer.entities_rules import _aggregate_rules, _read_entities, _write_entities
    root = Path(root)
    res = {"rules_written": 0, "entities": 0}
    for rule in proposed.get("rules", []):
        if not isinstance(rule, dict):
            # A non-object rule entry (string/list) would crash the .get() calls below;
            # skip it like _aggregate_rules / _build_rules_index do, and count it as
            # rejected rather than aborting the whole apply.
            res.setdefault("rejected", []).append({"folderName": rule, "why": "not an object"})
            continue
        parent_rel = rule.get("parent", "") or ""
        folder = rule.get("folderName")
        desc = rule.get("description", "")
        if not folder:
            continue
        # Reject path-traversal / absolute parents — the proposals file is Claude-authored
        # and untrusted; a `../`, absolute, or symlink-escaping `parent` would write a rules
        # file outside the drive root. _safe_dest validates AND returns the resolved write
        # target, so the validation target is identical to the write target.
        if os.path.isabs(folder):
            res.setdefault("rejected", []).append({"parent": parent_rel, "folderName": folder, "why": "absolute path"})
            continue
        # C2 fix: also reject folderName containing path-traversal segments (`..`).
        # An absolute check alone misses `../../etc` — mirroring the parent_rel check.
        if ".." in Path(folder).parts:
            res.setdefault("rejected", []).append({"parent": parent_rel, "folderName": folder, "why": "path traversal"})
            continue
        if parent_rel and (".." in Path(parent_rel).parts or os.path.isabs(parent_rel)):
            res.setdefault("rejected", []).append({"parent": parent_rel, "folderName": folder, "why": "escapes root"})
            continue
        sub = os.path.join(parent_rel, ".tidy-rules.json") if parent_rel else ".tidy-rules.json"
        pf = _safe_dest(root, sub)
        if pf is None:
            res.setdefault("rejected", []).append({"parent": parent_rel, "folderName": folder, "why": "escapes root"})
            continue
        leaf = folder.split("/")[-1]
        # Canonical rule-description suffix is " in <leaf>" WITH the leading space; the
        # shared _ensure_in_suffix is the single home for that rule (the space matters:
        # endswith("in <leaf>") would also match a word ending in "in", e.g. "Bitcoin Bills"
        # ends with "in Bills", and wrongly skip the append).
        desc = _ensure_in_suffix(desc, leaf)
        data = {"rules": []}
        if pf.exists():
            try:
                data = json.loads(pf.read_text(encoding="utf-8"))
            except Exception:
                data = {"rules": []}
        rules = data.get("rules", []) if isinstance(data, dict) else data
        existing = next((r for r in rules if isinstance(r, dict) and r.get("folderName") == folder), None)
        if existing:
            existing["description"] = desc or existing.get("description", "")
        else:
            rules.append({"folderName": folder, "description": desc})
        # Always normalise to {"rules": [...]} on write — a previously bare-list file
        # would otherwise be rewritten as a bare list, dropping any sibling keys.
        if isinstance(data, dict):
            data["rules"] = rules
        else:
            data = {"rules": rules}
        pf.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(pf, json.dumps(data, indent=2, ensure_ascii=False))
        res["rules_written"] += 1
    ent = proposed.get("entities") or {}
    if ent:
        cur = _read_entities(root)
        for name, m in ent.items():
            base = dict(cur.get(name, {}))
            base.update({k: v for k, v in m.items() if v not in (None, "", [], {})})
            cur[name] = base
        _write_entities(root, cur)
        res["entities"] = len(ent)
    return res


def cmd_bootstrap(args):
    """Bootstrap rules from an existing tree. Steps:
      --detect-atomic         list atomic-unit folders (approve these first)
      --lock NAMES            write named atomic units locked to entities.json
      --emit [--mode M]       sample unruled folders -> <root>/.organizer/bootstrap-input.json
      --apply FILE            write approved proposals (rules + entities)
    The inference between --emit and --apply is Claude's (see SKILL.md); the result
    is reviewed in `rules-viewer` before/after apply.
    These flags are mutually exclusive (sequential pipeline phases): passing --emit
    alongside --detect-atomic, --lock, or --apply is an error (explicit check below)."""
    from drive_organizer.entities_rules import _read_entities, _write_entities
    root = Path(paths_config._EFFECTIVE_ROOT)
    # Mutual-exclusion guard: --emit is the default/sample action; --detect-atomic, --lock,
    # and --apply are distinct pipeline phases. Passing --emit alongside any other phase flag
    # would be ambiguous (and --emit would be silently ignored by the elif chain). Error loudly.
    emit_set = getattr(args, "emit", False)
    other_flags = [f for f, v in [("--detect-atomic", getattr(args, "detect_atomic", False)),
                                   ("--lock", bool(getattr(args, "lock", None))),
                                   ("--apply", bool(getattr(args, "apply", None)))] if v]
    if emit_set and other_flags:
        sys.exit(f"Error: --emit cannot be combined with {', '.join(other_flags)}. "
                 f"These are sequential pipeline phases: --detect-atomic → --lock → --emit → --apply. "
                 f"Run each phase separately.")
    if getattr(args, "detect_atomic", False):
        units = _detect_atomic_units(root)
        if getattr(args, "json", False):
            print(json.dumps(units, indent=2)); return
        print(f"Atomic-unit folders ({len(units)}) — approve to lock (never descended again):")
        for u in units:
            print(f"  [{'LOCKED' if u['locked'] else 'new'}] {u['folder']}  ({u['marker']}, {u['file_count']} files)")
        if units:
            print("\nLock all new ones:  bootstrap --lock " + ",".join(u["name"] for u in units if not u["locked"]))
        return
    if getattr(args, "lock", None):
        names = [n.strip() for n in args.lock.split(",") if n.strip()]
        cur = _read_entities(root)
        for n in names:
            base = dict(cur.get(n, {}))
            base["entity_type"] = "atomic"; base["locked"] = True
            cur[n] = base
        _write_entities(root, cur)
        print(f"Locked {len(names)} atomic unit(s): {', '.join(sorted(names))}")
        return
    if getattr(args, "apply", None):
        path = Path(args.apply)
        if not path.exists():
            sys.exit(f"Error: proposals file not found: {path}")
        try:
            proposed = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError) as e:
            sys.exit(f"Error: could not parse proposals file {path}: {e}. It must be a JSON "
                     f"object with 'rules'/'entities' keys. See SKILL.md bootstrap step 4 for the shape.")
        if not isinstance(proposed, dict):
            sys.exit(f"Error: proposals file must be a JSON object with 'rules'/'entities' keys, "
                     f"got a {type(proposed).__name__}. See SKILL.md bootstrap step 4 for the shape.")
        res = _bootstrap_apply(root, proposed)
        print(f"Bootstrap applied: {res['rules_written']} rules, {res['entities']} entity metadata entries.")
        print("Review/edit with:  rules-viewer")
        return
    # default / --emit
    mode = getattr(args, "mode", None) or "cold-start"
    sample_k = int(getattr(args, "sample", None) or 5)
    # Precedence: explicit --limit > config.json's scan_file_limit > hardcoded 250.
    _arg_limit = getattr(args, "limit", None)
    limit = int(_arg_limit) if _arg_limit is not None else _effective_scan_file_limit(root)
    atomic = _detect_atomic_units(root)
    cand = _bootstrap_candidates(root, mode=mode, sample_k=sample_k, limit=limit)
    out = {"root": str(root), "mode": mode, "atomic_units": atomic, **cand}
    dest = root / ".organizer" / "bootstrap-input.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding='utf-8')
    unlocked = [u for u in atomic if not u["locked"]]
    batch_size = _effective_batch_size(root)
    print(f"Bootstrap input written: {dest}")
    print(f"  mode: {mode}")
    print(f"  atomic units: {len(atomic)} ({len(unlocked)} not yet locked)")
    print(f"  inference candidates: {cand['emitted']} folder(s) in {cand['n_batches']} batch(es) of {batch_size}"
          + (f" ({cand['dropped']} over the {limit} cap, deferred)" if cand["dropped"] else ""))
    if mode == "audit" and cand["drift"]:
        print(f"  drift flagged: {len(cand['drift'])} ruled folder(s) whose sample routes elsewhere")
    if unlocked:
        print("\nNext: approve atomic units →  bootstrap --lock " + ",".join(u["name"] for u in unlocked))
    print(f"Then Claude infers each candidate's rule/type from its sample (fan-out, {batch_size}/batch),"
          " writes a proposals file, and you run:  bootstrap --apply <file>  →  rules-viewer")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
