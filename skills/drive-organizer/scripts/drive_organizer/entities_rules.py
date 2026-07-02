"""drive_organizer.entities_rules — split from the original organizer.py (pure structural move, no behavior change)."""
from __future__ import annotations
import json
import os
import re
import shutil
import sys
from pathlib import Path

from drive_organizer import paths_config
from drive_organizer.paths_config import (
    PARA_ROOTS,
    _CLUSTER_LABEL,
    _CLUSTER_ORDER,
    _COMMON_CATEGORY_WORDS,
    _atomic_write,
    _has_rules,
    _is_external,
    _load_templates,
    _reset_caches,
)
from drive_organizer.content_peek import (
    get_db,
    should_skip,
)
from drive_organizer.date_range import (
    _enumerate_project_metadata,
)


def _read_entities(root: "Path | None" = None) -> dict:
    """Per-drive entity metadata at <root>/.organizer/entities.json. Optional;
    absent => today's behaviour. Maps entity name -> {entity_type, locked,
    aliases, relation, policy, notes, date_range?}. `date_range` (a
    {"start","end"} ISO-date dict, Phase-3) lets ANY entity — not just project
    folders — route loose dated files (bills/statements/photos) to it by date.
    All keys pass through unfiltered. Never raises."""
    root = root or paths_config._EFFECTIVE_ROOT
    if not root:
        return {}
    p = Path(root) / ".organizer" / "entities.json"
    if not p.exists():
        return {}
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _locked_atomic_names(root: "Path | None" = None) -> set:
    """Names of entities that are locked atomic units (entity_type=atomic OR
    locked=true) per entities.json — folders scan/bootstrap/coverage treat as a
    single opaque leaf, never descending into them. Single source for the set."""
    return {name for name, m in _read_entities(root).items()
            if isinstance(m, dict) and (m.get("locked") is True or m.get("entity_type") == "atomic")}


def _write_entities(root: Path, data: dict) -> None:
    """Persist entity metadata. Used by the viewer/bootstrap write-back."""
    p = Path(root) / ".organizer" / "entities.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(p, json.dumps(data, ensure_ascii=False, indent=2))


def _signal_from_description(desc: str, folder: str) -> str:
    """Strip the required ' in <FolderName>' suffix to recover the rule's signal
    terms. Tolerates the (incorrect but seen) comma-before-in form."""
    if not desc:
        return ""
    leaf = folder.split("/")[-1]
    for suffix in (f" in {folder}", f" in {leaf}", f", in {folder}", f", in {leaf}"):
        if desc.endswith(suffix):
            return desc[:-len(suffix)].rstrip().rstrip(",").strip()
    return desc.strip()


def _category_names() -> set:
    """Functional-subfolder names known from the templates (Scripts, References,
    Bills, …) — used to infer entity_type=category. Data-driven, not hardcoded."""
    t = _load_templates()
    names = set()
    sd = t.get("subfolder_definitions", {})
    if isinstance(sd, dict):
        names |= set(sd.keys())
    cc = t.get("compound_children", {})
    # Each isinstance guard is a separate tolerance layer for a hand-editable JSON
    # file — cc may not be a dict, v may be a bare list, kids may be a non-list,
    # and each child may be a str or a {"name":...} dict. All six levels are required.
    if isinstance(cc, dict):
        names |= set(cc.keys())
        for v in cc.values():
            # Shipped/override shape is {"children": [...]}; tolerate a bare list too
            # (older or hand-edited overrides) so neither form is silently dropped.
            kids = v.get("children", []) if isinstance(v, dict) else v
            if isinstance(kids, list):
                for x in kids:
                    if isinstance(x, str):
                        names.add(x)
                    elif isinstance(x, dict) and "name" in x:
                        names.add(x["name"])
    return names


# Common functional-subfolder names (beyond whatever the templates define). Used to
# confidently infer entity_type=category so these never fall into triage. Lowercased.
def _infer_entity_type(name: str, has_filename_tag: bool, is_grouping: bool,
                       categories: set) -> str:
    """Best-effort entity_type from STRUCTURAL + cheap lexical signals, when
    entities.json doesn't set one explicitly. It makes a CONFIDENT guess wherever it
    reasonably can, and reserves 'unknown' (triage) for the genuinely ambiguous —
    chiefly Capitalized proper-noun names that could be a person OR a project, and
    junk names. It never guesses 'person' from name shape (that mislabelled 'Thesis'
    / 'Incoming4'); person vs project is resolved by Claude's inference or the user."""
    if is_grouping:
        return "area"
    if has_filename_tag:
        return "project"
    nl = name.lower()
    cats_lower = {c.lower() for c in categories} | _COMMON_CATEGORY_WORDS
    if nl in cats_lower:
        return "category"
    # A single all-lowercase alphabetic word is almost always a functional subfolder
    # (people / projects are Capitalized). Confident category, not triage.
    if " " not in name and name.isalpha() and name == nl:
        return "category"
    # Otherwise truly ambiguous (proper-noun container person-vs-project, or junk) -> triage.
    return "unknown"


def _aggregate_rules(root: "Path") -> list:
    """Group every .tidy-rules.json rule by entity (leaf folder name) across the
    whole tree. Each returned entity carries its cross-folder occurrences, inferred
    or explicit entity_type (the clustering key), project metadata, registry usage
    count, and a dead-rule flag. This is the single source the viewer/bootstrap read."""
    from drive_organizer.cleanup_reconcile import _active_groupings
    root = Path(root)
    entities_meta = _read_entities(root)
    groupings = _active_groupings()
    categories = _category_names()
    projects = {}
    for p in _enumerate_project_metadata(root):
        projects[p["path"].split("/")[-1]] = p

    agg: dict = {}
    for rules_file in sorted(root.rglob(".tidy-rules.json")):
        parent = rules_file.parent
        try:
            rel_parent = parent.relative_to(root)
        except Exception:
            continue
        parent_disp = "" if str(rel_parent) == "." else str(rel_parent)
        try:
            data = json.loads(rules_file.read_text(encoding="utf-8"))
        except Exception:
            continue
        rule_list = data.get("rules", []) if isinstance(data, dict) else data
        if not isinstance(rule_list, list):
            continue
        for r in rule_list:
            if not isinstance(r, dict):
                continue
            folder = r.get("folderName")
            if not folder:
                continue
            name = folder.split("/")[-1]
            dest_rel = (f"{parent_disp}/{folder}" if parent_disp else folder).strip("/")
            desc = r.get("description", "")
            ent = agg.setdefault(name, {"entity": name, "occurrences": []})
            ent["occurrences"].append({
                "parent": parent_disp,
                "folderName": folder,
                "dest": dest_rel,
                "description": desc,
                "signal": _signal_from_description(desc, folder),
                "rules_file": str(rules_file.relative_to(root)),
            })

    # Registry usage: files actually routed to each destination.
    usage: dict = {}
    try:
        conn = get_db()
        for row in conn.execute(
            "SELECT para_subfolder AS d, COUNT(*) AS c FROM files "
            "WHERE para_subfolder IS NOT NULL AND para_subfolder != '' GROUP BY para_subfolder"):
            usage[row["d"]] = row["c"]
        conn.close()
    except Exception:
        pass

    def _prefix_usage(area: str) -> int:
        # Files routed to the area itself OR anywhere beneath it.
        return sum(c for d, c in usage.items() if d == area or d.startswith(area + "/"))

    out = []
    for name, ent in agg.items():
        dests = {o["dest"] for o in ent["occurrences"]}
        meta = entities_meta.get(name, {})
        # Area entities count usage as a PREFIX-SUM (everything routed under the area),
        # consistent with the synthetic-area card below; non-area entities count the
        # files routed to their exact destination(s).
        if name.upper() in groupings:
            ucount = _prefix_usage(name)
        else:
            ucount = sum(usage.get(d, 0) for d in dests)
        proj = projects.get(name, {})
        has_tag = bool(proj.get("filename_tag"))
        explicit = meta.get("entity_type")
        if explicit:
            etype, inferred = explicit, False
        else:
            etype = _infer_entity_type(name, has_tag, name.upper() in groupings, categories)
            inferred = True
        ent.update({
            "entity_type": etype,
            "type_inferred": inferred,
            "locked": meta.get("locked") is True,
            "aliases": meta.get("aliases", []),
            "relation": meta.get("relation"),
            "policy": meta.get("policy"),
            "notes": meta.get("notes"),
            "review": meta.get("review"),   # persisted "rethink" flag — viewer reads e.review
            "filename_tag": proj.get("filename_tag"),
            "date_range": proj.get("date_range"),
            "occurrence_count": len(ent["occurrences"]),
            "usage_count": ucount,
            "dead": ucount == 0,
        })
        out.append(ent)

    # Locked/atomic entities declared in entities.json but carrying no rules.
    for name, meta in entities_meta.items():
        if name in agg:
            continue
        if meta.get("entity_type") == "atomic" or meta.get("locked") is True:
            out.append({
                "entity": name, "occurrences": [],
                "entity_type": meta.get("entity_type", "atomic"),
                "type_inferred": False, "locked": meta.get("locked", True) is True,
                "aliases": meta.get("aliases", []), "relation": meta.get("relation"),
                "policy": meta.get("policy"), "notes": meta.get("notes"),
                "review": meta.get("review"),
                "filename_tag": None, "date_range": None,
                "occurrence_count": 0, "usage_count": 0, "dead": True,
            })

    # Synthesize a card for every active grouping (area) so areas are editable as
    # full cards (signal/details/notes), not just top-of-page chips. Areas that
    # already have a root rule produced an entity above — just force their type.
    present = {e["entity"] for e in out}
    for area in sorted(groupings):
        if area in present:
            for e in out:
                if e["entity"] == area and not entities_meta.get(area, {}).get("entity_type"):
                    e["entity_type"] = "area"
                    e["type_inferred"] = False
            continue
        m = entities_meta.get(area, {})
        area_usage = _prefix_usage(area)
        out.append({
            "entity": area,
            "occurrences": [{"parent": "", "folderName": area, "dest": area,
                             "description": "", "signal": "", "rules_file": ".tidy-rules.json"}],
            "entity_type": "area", "type_inferred": False,
            "locked": m.get("locked") is True,
            "aliases": m.get("aliases", []), "relation": m.get("relation"),
            "policy": m.get("policy"), "notes": m.get("notes"),
            "review": m.get("review"),
            "filename_tag": None, "date_range": None,
            "occurrence_count": 1, "usage_count": area_usage, "dead": area_usage == 0,
            "synthetic_area": True,
        })

    out.sort(key=lambda e: (_CLUSTER_ORDER.index(e["entity_type"]) if e["entity_type"] in _CLUSTER_ORDER else 99,
                            e["entity"].lower()))
    return out


def cmd_rules(args):
    """Aggregate the .tidy-rules.json cascade by entity across the tree. Default
    output is a human one-line-per-entity summary, semantically clustered by
    entity_type. `--json` emits the full structure consumed by the rules viewer."""
    from drive_organizer.cleanup_reconcile import _active_groupings
    root = Path(paths_config._EFFECTIVE_ROOT)
    agg = _aggregate_rules(root)
    if getattr(args, "json", False):
        print(json.dumps(
            {"root": str(root), "areas": sorted(_active_groupings()), "entities": agg},
            ensure_ascii=False, indent=2))
        return
    by_type: dict = {}
    for e in agg:
        by_type.setdefault(e["entity_type"], []).append(e)
    areas = sorted(_active_groupings())
    print(f"Rules aggregated from {root}")
    print(f"Active areas ({len(areas)}): {', '.join(areas)}")
    print(f"{len(agg)} entities across {sum(len(e['occurrences']) for e in agg)} rule occurrences\n")
    for t in _CLUSTER_ORDER + [x for x in by_type if x not in _CLUSTER_ORDER]:
        ents = by_type.get(t)
        if not ents:
            continue
        print(f"== {_CLUSTER_LABEL.get(t, t.title())} ({len(ents)}) ==")
        for e in sorted(ents, key=lambda x: x["entity"].lower()):
            locs = len(e["occurrences"])
            flags = []
            if e["locked"]:
                flags.append("locked")
            if e["dead"] and e["occurrences"]:
                flags.append("DEAD 0-routed")
            if e["type_inferred"]:
                flags.append("type?")
            if e.get("aliases"):
                flags.append("aka " + "/".join(e["aliases"]))
            tag = f"  [{', '.join(flags)}]" if flags else ""
            where = ""
            if locs:
                ps = sorted({o["parent"] or "(root)" for o in e["occurrences"]})
                where = " @ " + ", ".join(ps[:4]) + (f" +{len(ps) - 4}" if len(ps) > 4 else "")
            print(f"  - {e['entity']} - {locs} folder(s), {e['usage_count']} files routed{where}{tag}")
        print()


# ---------------------------------------------------------------------------
# W2 — Rules viewer/editor: aggregated, clustered, editable rules in a browser.
# Mirrors cmd_generate_viewer (do_GET serves, do_POST writes back, then shuts
# down). Safe edits (metadata, signal text, delete-rule, area add/rename) apply
# directly; structural moves (folder rename, level promotion) return a dry-run
# plan the user confirms — never a silent move.
# ---------------------------------------------------------------------------

def _conflicts_for(index: list) -> dict:
    """Map entity-destination -> list of other destinations whose token set overlaps
    (a filename could match both). Surfaced as per-card conflict warnings."""
    out = {}
    for i, a in enumerate(index):
        clashes = []
        for j, b in enumerate(index):
            if i == j or a["dest"] == b["dest"]:
                continue
            if a["tokens"] & b["tokens"]:
                clashes.append({"with": b["dest"], "shared": sorted(a["tokens"] & b["tokens"])[:5]})
        if clashes:
            out[a["dest"]] = clashes
    return out


def _should_prune_subdir(d: str, cp: Path, locked_atomic: set) -> bool:
    """C4: shared pruning predicate for os.walk subdirs[:] filtering.
    Returns True when a subdirectory should be excluded from descent:
    - hidden or underscore-prefixed names (dot/underscore convention)
    - locked atomic-unit names (per entities.json)
    - atomic-unit markers (_atomic_marker test)
    - external/shared-library folders (_is_external test)
    Used by _coverage_gaps and _bootstrap_candidates to keep their pruning
    logic in sync; each caller still mutates subdirs[:] in its own loop."""
    from drive_organizer.bootstrap import _atomic_marker, _bootstrap_candidates
    return (
        d.startswith((".", "_"))
        or d in locked_atomic
        or _atomic_marker(cp / d)
        or _is_external(cp / d)
    )


def _coverage_gaps(root: Path, dest_set: set) -> list:
    """Folders that physically hold files but have no rule routing into them —
    candidates for 'create a rule' (feeds reconcile)."""
    from drive_organizer.bootstrap import _bootstrap_candidates
    from drive_organizer.cleanup_reconcile import _active_groupings
    gaps = []
    groupings = _active_groupings()
    locked_atomic = _locked_atomic_names(root)
    skip = {".organizer"} | PARA_ROOTS
    # Normalise destinations (forward-slash, case-folded) so a real folder isn't
    # reported as a gap merely because of separator/case differences vs the rule dest.
    norm_dest_set = {str(d).replace(os.sep, "/").strip("/").casefold() for d in dest_set}
    for top in sorted(p for p in root.iterdir() if p.is_dir()):
        if top.name in skip or top.name not in groupings:
            continue
        # os.walk (not rglob) so external/atomic subtrees can be pruned before descent —
        # rglob would walk into shared folders and node_modules/.git/venvs.
        # C4: pruning predicate extracted into _should_prune_subdir (shared with
        # _bootstrap_candidates). subdirs[:] mutation stays local; the predicate is called
        # per-entry so os.walk never descends into excluded subtrees.
        for cur, subdirs, files in os.walk(top):
            cp = Path(cur)
            subdirs[:] = [d for d in subdirs
                          if not _should_prune_subdir(d, cp, locked_atomic)]
            if cp == top:
                continue   # the grouping root itself isn't a "gap"
            try:
                rel = str(cp.relative_to(root))
            except Exception:
                continue
            if rel.replace(os.sep, "/").strip("/").casefold() in norm_dest_set:
                continue
            try:
                has_files = any(f.is_file() and not should_skip(f) for f in cp.iterdir())
            except OSError:
                continue   # unreadable (cloud/permission) folder — skip, don't crash
            if has_files and not (cp / ".tidy-rules.json").exists():
                gaps.append(rel)
                if len(gaps) >= 100:
                    # Hard cap at 100 to bound a huge drift. A returned length of exactly
                    # 100 signals "capped — there may be more"; the rules-viewer shows
                    # "showing N of <len>(+ capped)" so the operator can tell the list is
                    # truncated rather than complete.
                    return gaps
    return gaps[:100]


def _edit_rule_across_occurrences(root: Path, entity: str, occurrences: list,
                                  new_description: str = None, delete: bool = False,
                                  create_if_missing: bool = False) -> int:
    """Apply a signal/description edit (or delete the rule) to every occurrence of an
    entity across the tree. Returns the number of rule files changed. Folder names
    and files on disk are NOT touched — this edits routing rules only.
    create_if_missing: when a folderName isn't present in its rules file (e.g. a
    synthesized area card with no root rule yet), append a new rule for it."""
    from drive_organizer.cleanup_reconcile import _ensure_in_suffix
    changed = 0
    by_file = {}
    for occ in occurrences:
        by_file.setdefault(occ["rules_file"], []).append(occ["folderName"])
    for rel_file, folder_names in by_file.items():
        path = root / rel_file
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
        elif create_if_missing and new_description is not None:
            data = {"rules": []}
        else:
            continue
        rules = data.get("rules", []) if isinstance(data, dict) else data
        if not isinstance(rules, list):
            continue
        touched = False
        seen = set()
        new_rules = []
        for r in rules:
            if isinstance(r, dict) and r.get("folderName") in folder_names:
                seen.add(r["folderName"])
                if delete:
                    touched = True
                    continue  # drop the rule
                if new_description is not None:
                    leaf = r["folderName"].split("/")[-1]
                    r["description"] = _ensure_in_suffix(new_description.strip(), leaf)
                    touched = True
            new_rules.append(r)
        if create_if_missing and new_description is not None and not delete:
            for fn in folder_names:
                if fn not in seen:
                    leaf = fn.split("/")[-1]
                    new_rules.append({"folderName": fn, "description": _ensure_in_suffix(new_description.strip(), leaf)})
                    touched = True
        if touched:
            if isinstance(data, dict):
                data["rules"] = new_rules
            else:
                data = new_rules
            path.parent.mkdir(parents=True, exist_ok=True)
            _atomic_write(path, json.dumps(data, indent=2, ensure_ascii=False))
            changed += 1
    return changed


def _rewrite_rule_in_file(rf: Path, folder_name: str, new_name: str, did: dict):
    """Rewrite one rules file in-place: update the matching folderName (and its
    description suffix) to new_name. Updates did['rules'] and warns on failure."""
    if not rf.exists():
        return
    try:
        data = json.loads(rf.read_text(encoding="utf-8"))
        rules = data.get("rules", []) if isinstance(data, dict) else data
        for r in rules:
            if not (isinstance(r, dict) and r.get("folderName") == folder_name):
                continue
            r["folderName"] = new_name
            d = r.get("description", "")
            old_leaf = folder_name.split("/")[-1]
            if d.endswith(f" in {old_leaf}"):
                r["description"] = d[: -len(f" in {old_leaf}")] + f" in {new_name}"
            did["rules"] += 1
        if isinstance(data, dict):
            data["rules"] = rules
        _atomic_write(rf, json.dumps(data, indent=2, ensure_ascii=False))
    except Exception as e:
        # Surface failures — a rewrite failure (disk-full, bad JSON) leaves this rules file
        # un-updated while the rename proceeds; the caller's did["rules"] is understated.
        print(f"  WARNING: could not rewrite rules in {rf} for rename "
              f"'{folder_name}' -> '{new_name}' ({e}); that file may be out of "
              f"sync — re-run rename or fix it by hand.", file=sys.stderr)


def _rename_entity(root: Path, entity: str, occurrences: list, new_name: str,
                   apply: bool = False) -> dict:
    """Rename an entity (rule folderName leaf) across all its occurrences, and rename
    the on-disk folder + update the registry. dry-run unless apply=True."""
    from drive_organizer.cleanup_reconcile import _active_groupings, _para_category
    plan, did = [], {"rules": 0, "folders": 0, "rows": 0}
    # Build the per-occurrence plan first (dry-run is just this).
    for occ in occurrences:
        old_dest = occ["dest"]
        parent = occ["parent"]
        new_dest = (f"{parent}/{new_name}" if parent else new_name).strip("/")
        plan.append({"from": old_dest, "to": new_dest, "rules_file": occ["rules_file"],
                     "folderName": occ["folderName"]})
    if not apply:
        return {"entity": entity, "new_name": new_name, "apply": apply, "plan": plan,
                "applied": did}

    # PRE-SCAN: refuse the whole rename if ANY target already exists on disk or in the
    # registry, before mutating anything (no partial renames, no collisions).
    conn = get_db()
    try:
        for step in plan:
            new_dest = step["to"]
            dst = root / new_dest
            if dst.exists():
                return {"entity": entity, "new_name": new_name, "apply": apply,
                        "plan": plan, "applied": did,
                        "error": f"target already exists on disk: {dst} — aborted (no changes made)"}
            clash = conn.execute(
                "SELECT COUNT(*) FROM files WHERE para_subfolder = ? OR para_subfolder LIKE ?",
                (new_dest, new_dest + "/%")).fetchone()[0]
            if clash:
                return {"entity": entity, "new_name": new_name, "apply": apply,
                        "plan": plan, "applied": did,
                        "error": f"target destination already in registry: {new_dest} "
                                 f"({clash} row(s)) — aborted (no changes made)"}

        # Load active groupings once so the per-row para_category re-projection below does
        # not re-read config.json for every renamed row.
        groupings = _active_groupings()
        for step in plan:
            old_dest, new_dest = step["from"], step["to"]
            rules_file, folder_name = step["rules_file"], step["folderName"]
            # folder move on disk — if the destination already exists (a collision the
            # pre-scan can't catch if it appeared mid-run), ABORT this occurrence: do
            # NOT rewrite the registry to point at a folder files were never moved into.
            src, dst = root / old_dest, root / new_dest
            if src.exists():
                if dst.exists():
                    conn.rollback(); conn.close()
                    return {"entity": entity, "new_name": new_name, "apply": apply,
                            "plan": plan, "applied": did,
                            "error": f"collision: {dst} appeared before the move — "
                                     f"aborted and rolled back (no changes committed)"}
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dst))
                did["folders"] += 1
            elif not dst.exists():
                # Neither src nor dst exists. Either old_dest had no folder on disk (a
                # registry-only rename — proceed) OR a prior crashed run left the move
                # half-applied with the folder vanished. Distinguish via the registry: if
                # rows still route to old_dest the folder genuinely never existed on disk
                # (registry-only) and the rewrite below is safe; but if the folder is simply
                # absent we must NOT rewrite current_path to a dst that holds no files.
                # Guard: abort this occurrence unless old_dest was purely a registry path
                # (no on-disk component recorded in any routed row's current_path).
                disk_backed = conn.execute(
                    "SELECT COUNT(*) FROM files WHERE (para_subfolder = ? OR para_subfolder LIKE ?) "
                    "AND current_path LIKE ?",
                    (old_dest, old_dest + "/%", str(src) + os.sep + "%")).fetchone()[0]
                if disk_backed:
                    conn.rollback(); conn.close()
                    return {"entity": entity, "new_name": new_name, "apply": apply,
                            "plan": plan, "applied": did,
                            "error": f"neither source {src} nor destination {dst} exists on disk "
                                     f"but {disk_backed} routed row(s) reference the source folder "
                                     f"— a prior rename was left half-applied; aborted and rolled "
                                     f"back. Restore the folder or run reconcile, then retry."}
            # Rule rewrite happens ONLY AFTER the folder move (or the registry-only path)
            # has succeeded — a mid-move failure aborts and rolls back above before we ever
            # touch the rules JSON, so the rules file can never point at the new name while
            # the folder + registry still hold the old one. nesting levels are each
            # independently required — rf.exists() skips missing files; try/except guards
            # malformed JSON; for r in rules iterates all rules; isinstance+folderName ==
            # matches only the target rule (other rules in the same file are left untouched).
            _rewrite_rule_in_file(root / rules_file, folder_name, new_name, did)
            # If we reach here either the folder is now at dst (moved this run or by a prior
            # run whose registry update never committed) or old_dest was registry-only — both
            # safe to rewrite. registry update — rewrite the PREFIX exactly, in Python. SQL REPLACE
            # substitutes every substring occurrence, so a short/common old_dest
            # (e.g. "A") would corrupt unrelated path segments ("A/A Files" →
            # "B/B Files"). Match rows whose para_subfolder is exactly old_dest or a
            # child of it, and replace only the leading old_dest segment.
            src_str, dst_str = str(src), str(dst)
            rows = conn.execute(
                "SELECT id, para_subfolder, current_path FROM files "
                "WHERE para_subfolder = ? OR para_subfolder LIKE ?",
                (old_dest, old_dest + "/%")).fetchall()
            for row in rows:
                para = row["para_subfolder"] or ""
                if para == old_dest:
                    new_para = new_dest
                elif para.startswith(old_dest + "/"):
                    new_para = new_dest + para[len(old_dest):]
                else:
                    continue
                cp = row["current_path"] or ""
                # Only rewrite current_path when it is exactly src or a child of src
                # (boundary-anchored), so a sibling sharing the prefix — "WORK/Acme"
                # vs "WORK/Acme Corp" — is never corrupted.
                if cp == src_str or cp.startswith(src_str + os.sep):
                    new_cp = dst_str + cp[len(src_str):]
                else:
                    new_cp = cp
                # Re-project para_category from the new para_subfolder too — it is a pure
                # projection of para_subfolder (its first segment if an active grouping, else
                # _Inbox). Omitting it would break the para_category==projection(para_subfolder)
                # invariant after a rename until the next reconcile (mis-counts status,
                # can misroute).
                conn.execute(
                    "UPDATE files SET para_subfolder=?, current_path=?, para_category=? WHERE id=?",
                    (new_para, new_cp, _para_category(new_para, groupings), row["id"]))
                did["rows"] += 1
        # Commit once, atomically, after ALL occurrences succeed.
        conn.commit()
    except Exception as e:
        conn.rollback()
        conn.close()
        return {"entity": entity, "new_name": new_name, "apply": apply, "plan": plan,
                "applied": did, "error": f"rename failed, rolled back: {e}"}
    finally:
        try:
            conn.close()
        except Exception:
            pass
    return {"entity": entity, "new_name": new_name, "apply": apply, "plan": plan, "applied": did}


def _merge_entities(root: Path, src_entity: dict, dst_name: str) -> dict:
    """Fold a (misspelled/duplicate) entity into another: add the source name + its
    aliases as aliases of the destination, then delete the source's routing rules so
    future files route to the destination. REFUSED (no-op, returns an error) while the
    source still holds files on disk or registry rows route to it — deleting its rules
    then would orphan those files; the user must reconcile/promote them first."""
    # SAFETY: deleting the source's rules without moving its on-disk files would orphan
    # those files (no rule routes into the source folder any more, yet the files still
    # sit there). Refuse the merge while any source occurrence still holds files on disk
    # OR still has registry rows routed to it — the user must reconcile/promote first.
    occ_dests = [o["dest"] for o in src_entity["occurrences"]]
    holding = []
    for dest in occ_dests:
        folder = root / dest
        try:
            if folder.is_dir() and any(f.is_file() for f in folder.rglob("*")):
                holding.append(dest)
                continue
        except OSError:
            holding.append(dest)   # unreadable → treat as holding (refuse safely)
            continue
    routed = 0
    if occ_dests:
        try:
            conn = get_db()
            for dest in occ_dests:
                routed += conn.execute(
                    "SELECT COUNT(*) FROM files WHERE para_subfolder = ? OR para_subfolder LIKE ?",
                    (dest, dest + "/%")).fetchone()[0]
            conn.close()
        except Exception as _db_err:
            # DB failure must NOT silently leave routed=0 and allow the merge to
            # proceed — that would bypass the safety guard. Surface the error and
            # refuse the merge so the caller can retry once the registry is healthy.
            # Render the browser-submitted entity/destination names with !r (repr) so a name
            # containing quotes or brace characters can't produce a structurally ambiguous
            # error string — repr unambiguously delimits and escapes the embedded value.
            # Report BOTH signals: the DB failure AND any on-disk holding already found —
            # do not let a non-empty holding mask the DB error (the caller needs the DB
            # failure surfaced to know the registry must be repaired before retrying).
            return {"merged": None, "into": dst_name, "error": (
                f"REFUSED merge of {src_entity['entity']!r} into {dst_name!r}: "
                f"could not query registry to check for routed rows ({_db_err})"
                + (f"; source also still holds files on disk ({', '.join(holding)})" if holding else "")
                + ". Resolve the DB error"
                + (" and reconcile/promote the held files" if holding else "")
                + ", then retry.")}
    if holding or routed:
        return {"merged": None, "into": dst_name, "error": (
            f"REFUSED merge of {src_entity['entity']!r} into {dst_name!r}: source still "
            f"holds files"
            + (f" on disk ({', '.join(holding)})" if holding else "")
            + (f" and {routed} registry row(s) route to it" if routed else "")
            + ". Reconcile or promote those files first, then merge.")}

    ents = _read_entities(root)
    dst = ents.setdefault(dst_name, {})
    aliases = set(dst.get("aliases", []))
    aliases.add(src_entity["entity"])
    aliases |= set(src_entity.get("aliases", []))
    dst["aliases"] = sorted(aliases)
    if src_entity["entity"] in ents:
        del ents[src_entity["entity"]]
    _write_entities(root, ents)
    # _edit_rule_across_occurrences is called after _write_entities — so on partial failure
    # (entities.json updated but some rule files not yet rewritten), re-running _merge_entities
    # is SAFE: _write_entities is idempotent (aliases set-merge is additive), and
    # _edit_rule_across_occurrences(delete=True) skips rules already absent (touched stays False,
    # file not rewritten). No transaction/rollback needed — re-run recovers to the same final state.
    deleted = _edit_rule_across_occurrences(root, src_entity["entity"],
                                            src_entity["occurrences"], delete=True)
    return {"merged": src_entity["entity"], "into": dst_name, "rules_deleted": deleted,
            "alias_added": True,
            "note": "Future routing folds in (source held no files; safe to drop rules)."}


def _apply_area_changes(root: Path, add: list, rename: list, remove: list) -> dict:
    """Add / rename / remove top-level groupings in the per-drive config.json "areas"
    list (ALL-CAPS enforced). Removal is refused while files still live under the area
    (guard). On-disk folder renames for a renamed area are reported as a structural
    follow-up, not performed silently."""
    from drive_organizer.cleanup_reconcile import _active_groupings
    cfg_path = root / ".organizer" / "config.json"
    cfg = {}
    if cfg_path.exists():
        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        except Exception:
            cfg = {}

    def _area_has_files(au: str) -> bool:
        """True if the on-disk folder for area `au` has any contents. Unreadable
        (permission/cloud) folders are treated as HAS-contents so removal/rename is
        refused safely rather than proceeding on an unverifiable empty assumption."""
        folder = root / au
        if not folder.exists():
            return False
        try:
            return any(folder.iterdir())
        except OSError:
            return True

    def _registry_rows_under(au: str) -> int:
        try:
            conn = get_db()
            n = conn.execute(
                "SELECT COUNT(*) FROM files WHERE para_subfolder = ? OR para_subfolder LIKE ?",
                (au, au + "/%")).fetchone()[0]
            conn.close()
            return n
        except Exception:
            return 0

    # CONFIG-FREEZING CAVEAT: the very first area edit persists the *current* derived
    # _active_groupings() set into config.json "areas". Only the keys the user actually
    # changed are mutated below, but writing the "areas" list at all freezes the set
    # (subsequent template changes won't flow through). This is intentional: an explicit
    # area edit is the user taking ownership of the set.
    areas = [a.upper() for a in (cfg.get("areas") or sorted(_active_groupings()))]
    notes = []
    for a in add or []:
        au = str(a).upper()
        if au not in areas:
            areas.append(au)
            notes.append(f"added area {au}")
    for r in rename or []:
        old, new = str(r.get("old", "")).upper(), str(r.get("new", "")).upper()
        if old not in areas or not new:
            continue
        if new in areas:
            notes.append(f"REFUSED rename {old} -> {new}: target area name already exists")
            continue
        # Like remove, refuse the rename while files/rules/the OLD folder still exist
        # under the old name — the config would then point at a name with no folder
        # while real files remain under the old folder (orphaning them).
        if _area_has_files(old):
            notes.append(f"REFUSED rename {old} -> {new}: old folder still has contents "
                         f"(move/reconcile its files first)")
            continue
        rows = _registry_rows_under(old)
        if rows:
            notes.append(f"REFUSED rename {old} -> {new}: {rows} registry row(s) still route under {old}")
            continue
        if _has_rules(root / old, root):
            notes.append(f"REFUSED rename {old} -> {new}: old folder still has a .tidy-rules.json")
            continue
        areas[areas.index(old)] = new
        notes.append(f"renamed area {old} -> {new} (on-disk folder rename is a separate structural step)")
    for a in remove or []:
        au = str(a).upper()
        if _area_has_files(au):
            notes.append(f"REFUSED remove {au}: folder still has contents")
            continue
        # Also refuse while the registry still routes files under the area, even if
        # the on-disk folder is empty/absent (e.g. files classified but not yet
        # executed) — removing the area would strand those rows with a dead destination.
        n = _registry_rows_under(au)
        if n:
            notes.append(f"REFUSED remove {au}: {n} registry row(s) still route under it")
            continue
        if au in areas:
            areas.remove(au)
            notes.append(f"removed area {au}")
    cfg["areas"] = areas
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(cfg_path, json.dumps(cfg, indent=2, ensure_ascii=False))
    # The active-grouping set just changed on disk; drop the process cache so any later
    # _active_groupings() call in THIS process (reconcile, execute, a follow-up rules call)
    # re-reads config.json instead of returning the pre-change set. Not all callers go
    # through the rules-viewer /apply path that also resets — reset here at the source.
    _reset_caches()
    return {"areas": areas, "notes": notes}


def _promotion_plan(root: Path, entity: str, occurrences: list, target_parent: str) -> dict:
    """Dry-run plan for moving a folder up/down a level (e.g. a Q2 thing -> its own Q1
    area). Describes the folder move, the rule rewrites, and the registry path updates
    that --apply would perform. Never moves anything here (the user confirms)."""
    from drive_organizer.cleanup_reconcile import _normalize_grouping
    steps = []
    target_parent = _normalize_grouping(target_parent.strip("/")) if target_parent else ""
    for occ in occurrences:
        src_rel = occ["dest"]
        new_rel = (f"{target_parent}/{entity}" if target_parent else entity).strip("/")
        if src_rel == new_rel:
            continue
        n_files = 0
        try:
            conn = get_db()
            n_files = conn.execute(
                "SELECT COUNT(*) c FROM files WHERE para_subfolder = ? OR para_subfolder LIKE ?",
                (src_rel, src_rel + "/%")).fetchone()[0]
            conn.close()
        except Exception as _exc:
            import logging as _logging
            _logging.warning("merge-category dry-run: could not count registry rows for %r: %s", src_rel, _exc)
        steps.append({
            "move_folder": {"from": src_rel, "to": new_rel},
            "rewrite_rule_in": occ["rules_file"],
            "registry_rows_to_update": n_files,
        })
    return {"entity": entity, "target_parent": target_parent or "(root)",
            "steps": steps, "note": "DRY-RUN preview only — this plan is not wired to Apply/Save; "
            "perform the move manually (rewrite the named rules file(s), move the folder on disk, "
            "then run `reconcile` to update the affected registry rows), or use the reconcile "
            "move machinery directly."}

