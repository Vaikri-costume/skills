"""drive_organizer.classify_propose — split from the original organizer.py (pure structural move, no behavior change)."""
from __future__ import annotations
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

from drive_organizer import paths_config
from drive_organizer.paths_config import (
    IMAGE_EXTS,
    PARA_ROOTS,
    RAW_EXTS,
    _atomic_write,
    _effective_batch_size,
    _effective_scan_file_limit,
    _load_templates,
    _read_user_config,
)
from drive_organizer.content_peek import (
    extract_photo_date,
    get_db,
)
from drive_organizer.date_range import (
    _enumerate_project_metadata,
)


def cmd_exif(args):
    """Extract routing-useful image metadata (Feature 2 — used when the running model has no
    vision: route an image by EXIF instead of pixels). ALWAYS prints a JSON object and never
    errors out: Pillow is an optional dep, and without it (or without embedded EXIF) it
    degrades to the filename-derived date. Routing-useful fields: `date` (match a project's
    date_range), `camera`, dimensions."""
    path = Path(args.path).expanduser()
    out = {"path": str(path), "date": None, "camera": None,
           "width": None, "height": None, "source": "none", "note": None}
    if not path.exists():
        out["note"] = "file not found"
        print(json.dumps(out, ensure_ascii=False)); return
    fdate = extract_photo_date(path.name)          # always-available, no-dep fallback
    if fdate:
        out["date"], out["source"] = fdate, "filename"
    try:
        from PIL import Image                       # optional dep — degrade gracefully if absent
        with Image.open(path) as im:
            out["width"], out["height"] = im.size
            raw = im.getexif()
            exif_ifd = {}
            try:
                exif_ifd = raw.get_ifd(0x8769)      # Exif sub-IFD: DateTimeOriginal lives here
            except Exception:
                pass
            dt = exif_ifd.get(36867) or exif_ifd.get(36868) or raw.get(306)  # Orig/Digitized/DateTime
            if dt:
                out["date"] = str(dt)[:10].replace(":", "-")   # "YYYY:MM:DD …" → "YYYY-MM-DD"
                out["source"] = "exif"
            cam = " ".join(str(x).strip() for x in (raw.get(271), raw.get(272)) if x)  # Make, Model
            if cam:
                out["camera"] = cam
    except ImportError:
        out["note"] = "Pillow not installed — EXIF unavailable; using filename date if any (pip install pillow for richer metadata)"
    except Exception as e:
        out["note"] = f"EXIF read failed ({e}); using filename date if any"
    print(json.dumps(out, ensure_ascii=False))


def cmd_merge_category(args):
    """Apply a diff-only taxonomy addition to the per-user templates override (Feature 2 —
    the model emits a small JSON DIFF and Python owns the merge, instead of the model
    rewriting the whole nested templates file, which is fragile under context accumulation).

    Diff (JSON): {"name": "<new subfolder>", "description": "<signal terms> in <name>",
                  "parent": "<optional compound-parent type, e.g. Financials>"}
    Writes name→description into the override's `subfolder_definitions`, and (if `parent` names
    a compound parent) appends `name` to that parent's `compound_children[parent].children`.
    `_load_templates` deep-merges the override over the shipped skeleton, so the addition takes
    effect on the next propose; the shipped skeleton is never touched."""
    root = Path(paths_config._EFFECTIVE_ROOT)
    try:
        diff = json.loads(args.diff)
    except Exception as e:
        sys.exit(f'Error: --diff is not valid JSON ({e}). Expected '
                 f'{{"name": "...", "description": "... in <name>", "parent": "<optional>"}}')
    if not isinstance(diff, dict):
        sys.exit("Error: --diff must be a JSON object.")
    name = str(diff.get("name", "")).strip()
    desc = str(diff.get("description", "")).strip()
    parent = str(diff.get("parent", "")).strip()
    if not name:
        sys.exit("Error: diff.name (the new subfolder name) is required.")
    override = root / ".organizer" / "templates.json"
    override.parent.mkdir(parents=True, exist_ok=True)
    try:
        data = json.loads(override.read_text(encoding="utf-8")) if override.exists() else {}
    except Exception as e:
        sys.exit(f"Error: could not parse {override} ({e}); fix or remove it before merging.")
    if not isinstance(data, dict):
        sys.exit(f"Error: {override} is not a JSON object.")
    defs = data.setdefault("subfolder_definitions", {})
    if not isinstance(defs, dict):
        sys.exit(f"Error: {override} 'subfolder_definitions' is not an object.")
    existed = name in defs
    defs[name] = desc or defs.get(name, "")
    linked = False
    if parent:
        cc = data.setdefault("compound_children", {})
        if not isinstance(cc, dict):
            sys.exit(f"Error: {override} 'compound_children' is not an object.")
        # Outer guard (isinstance cc dict) already exited above; remaining nesting:
        # pnode may be a non-dict if hand-edited → skip silently (don't corrupt).
        # kids may be a non-list for the same reason → skip silently.
        pnode = cc.setdefault(parent, {})
        if isinstance(pnode, dict):
            kids = pnode.setdefault("children", [])
            if isinstance(kids, list) and name not in kids:
                kids.append(name); linked = True
    _atomic_write(override, json.dumps(data, ensure_ascii=False, indent=2))
    print(json.dumps({"merged": name, "override": str(override),
                      "action": "updated" if existed else "added",
                      "linked_under": parent if linked else None}, ensure_ascii=False))


def _bubble_sort_proposals(proposals: list) -> list:
    """
    Sort proposals by destination so files going to the same leaf appear
    together in the viewer. (Name is historical — this uses Python's built-in
    sorted(), not a bubble sort.) Sort key: (para_subfolder, filename).
    Inbox / unrouted files sort to the end.
    """
    def sort_key(p):
        dest = p.get("para_subfolder", "") or ""
        # _Inbox / unrouted to end
        is_inbox = dest.startswith("_Inbox") or dest == ""
        return (1 if is_inbox else 0, dest.lower(), (p.get("filename") or "").lower())
    return sorted(proposals, key=sort_key)


# ---------------------------------------------------------------------------
# Project metadata (filename_tag + date_range) — read/write helpers
# ---------------------------------------------------------------------------

def _tokens_from(text: str, minlen: int = 4) -> set:
    return {t.lower() for t in re.split(r"[^A-Za-z0-9]+", text or "") if len(t) >= minlen}


def _build_rules_index(root: Path) -> tuple:
    """Build a lightweight index of every rule destination for the auto-classify
    fast-path: a list of {dest, tokens, neg} plus the set of all known destination
    paths. tokens are distinctive lowercased terms from the folderName + the rule's
    signal (len>=4 by default, per-entity overridable via entities.json
    `min_token_len` — e.g. short names like IBM/BBC/ADM that the global floor
    would otherwise exclude) PLUS the entity's aliases (len>=3, so short forms
    like 'ish' route — a separate, unrelated floor, not affected by
    `min_token_len`) from entities.json. neg = the entity's negative tokens
    (learned from rejections) that suppress a match (W5)."""
    from drive_organizer.cleanup_reconcile import _normalize_grouping
    from drive_organizer.entities_rules import _read_entities, _signal_from_description
    entities_meta = _read_entities(root)
    index, dest_set = [], set()
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
            dest = (f"{parent_disp}/{folder}" if parent_disp else folder).strip("/")
            # Normalise the grouping (first) segment to its canonical case so two
            # rules differing only in grouping case ('Personal/...' vs 'PERSONAL/...')
            # collapse to one destination — otherwise the auto-classify matcher reads
            # them as competing destinations and (wrongly) falls through as ambiguous.
            dest = _normalize_grouping(dest)
            dest_set.add(dest)
            leaf = folder.split("/")[-1]
            meta = entities_meta.get(leaf, {}) if isinstance(entities_meta, dict) else {}
            signal = _signal_from_description(r.get("description", ""), folder)
            # Per-entity override of the global 4-char token floor (hand-editable via
            # entities.json / the rules-viewer, so validate defensively — a malformed
            # value falls back to the safe default rather than corrupting matching).
            raw_min_len = meta.get("min_token_len")
            min_len = raw_min_len if isinstance(raw_min_len, int) and raw_min_len >= 1 else 4
            tokens = _tokens_from(folder + " " + signal, minlen=min_len)
            for a in meta.get("aliases", []) or []:           # aliases route too (len>=3)
                tokens |= _tokens_from(a, minlen=3)
            neg = set()
            for n in meta.get("negative", []) or []:          # learned-from-rejection (W5)
                neg |= _tokens_from(n, minlen=3)
            if tokens:
                index.append({"dest": dest, "tokens": tokens, "neg": neg})
    return index, dest_set


def _infer_signal_from_filenames(names: list, top: int = 6) -> list:
    """Auto-infer a rule's signal: the distinctive tokens common to >=2 of the
    approved files routed to a folder (W5 — so the learning loop writes a real
    signal, not just the folder name). Returns up to `top` tokens."""
    from collections import Counter
    c = Counter()
    for n in names:
        for t in _tokens_from(Path(n).stem):
            c[t] += 1
    return [t for t, k in c.most_common(top) if k >= 2]


def _auto_classify_entry(entry: dict, root: Path, index: list, dest_set: set) -> tuple:
    """Deterministically route an unambiguous pending file WITHOUT the classifier.
    Returns (dest_subfolder, reason) or (None, None) when the file is ambiguous and
    must fall through to classification. Conservative by design: only fires on a
    file already living in the organized tree, or a SINGLE unambiguous token match."""
    from drive_organizer.cleanup_reconcile import _active_groupings
    groupings = _active_groupings()
    cur = Path(entry["current_path"])
    try:
        rel_dir = cur.parent.relative_to(root)
    except Exception:
        rel_dir = None

    # 1. Already in the organized tree: a file under an active grouping AND under a
    #    rule-defined destination (dest_set) is already correctly placed — auto-route it
    #    to stay (just register it). Using dest_set (actual ruled destinations) in addition
    #    to grouping membership prevents a manually-moved file that happens to sit under a
    #    grouping folder from being falsely marked "already placed" when no rule routes to
    #    its parent. C3 fix: added dest_set membership check.
    if rel_dir is not None and rel_dir.parts:
        parts = rel_dir.parts
        rel_dir_str = str(rel_dir).replace(os.sep, "/").strip("/")
        in_grouping = parts[0] in groupings and not (set(parts) & PARA_ROOTS)
        # dest_set contains rule-resolved destinations; check any ancestor path segment.
        in_dest = any(
            rel_dir_str == d.replace(os.sep, "/").strip("/") or
            rel_dir_str.startswith(d.replace(os.sep, "/").strip("/") + "/")
            for d in dest_set
        ) if dest_set else False
        in_tree = in_grouping and in_dest
        if in_tree:
            return str(rel_dir), "already in ruled folder"

    # 2. Unambiguous filename token match: route only if every matching rule points
    #    to the SAME destination (competing destinations => ambiguous => classifier).
    fname = (entry.get("filename") or "").lower()
    if fname:
        # Only tokens of length>=3 (drop empty strings too) can drive an auto-route:
        # a single short/empty token must not trigger an over-confident match.
        ftok = {t for t in re.split(r"[^a-z0-9]+", fname) if len(t) >= 3}
        # match a dest when its tokens hit AND none of its negative tokens hit (W5)
        matched = {e["dest"] for e in index
                   if (e["tokens"] & ftok) and not (e.get("neg") and e["neg"] & ftok)}
        if len(matched) == 1:
            return next(iter(matched)), "unambiguous filename match"
    return None, None


def cmd_propose(args):
    from drive_organizer.cleanup_reconcile import _normalize_grouping
    from drive_organizer.entities_rules import _read_entities
    root = Path(paths_config._EFFECTIVE_ROOT)
    # Precedence: explicit --limit > config.json's scan_file_limit > hardcoded 250.
    limit = int(args.limit) if args.limit is not None else _effective_scan_file_limit(root)
    conn = get_db()
    rows = conn.execute(
        """SELECT id, current_path, filename, extension, file_size, file_date, content_peek
           FROM files WHERE status = 'pending' ORDER BY id LIMIT ?""",
        (limit,)
    ).fetchall()
    conn.close()

    if not rows:
        print("No pending files. Run 'scan' first or all files are already classified.")
        return

    cfg = _read_user_config(root)
    # W1 — auto-classify fast-path toggle: config.json auto_classify (default True),
    # overridable per-run with --no-auto-classify / --auto-classify.
    auto_on = cfg.get("auto_classify", True)
    if getattr(args, "no_auto_classify", False):
        auto_on = False
    if getattr(args, "auto_classify", False):
        auto_on = True
    # W5 — auto-approval: when opted in (config.json auto_approve, default OFF for
    # safety), ALL W1 auto-routed files are marked auto_approved so the orchestrator
    # may execute them without a viewer pass (still CSV-audited). This flag applies
    # only to the W1 deterministic fast-path — classifier confidence is never read.
    auto_approve = cfg.get("auto_approve", False)
    if getattr(args, "auto_approve", False):
        auto_approve = True
    # Per-entity auto_approve override (entities.json): tri-state — absent/null
    # inherits the global `auto_approve` above; true/false always/never auto-approves
    # this entity's W1 matches regardless of the global setting. Loaded once here and
    # applied at the W1 application site below via the entity's routed folder leaf.
    entities_meta = _read_entities(root)

    # W1b — cost toggles: skip the expensive content/vision read for some files.
    # vision (default on), skip_types (extensions), skip_over_mb (size cap). Config
    # values, each overridable per-run. A "blocked-open" file is never opened: it's
    # routed deterministically by the W1 matcher, or sent to the classifier with a
    # route_by_name_only flag (filename + path only), or falls to _Inbox.
    # Model capabilities (Feature 2 — model-agnostic): can the running model open file
    # CONTENTS (peek) and SEE images (vision)? Default both on; `config.json`
    # "model_capabilities": {"peek": bool, "vision": bool} overrides; per-run --no-peek /
    # --no-vision win (precedence: flag > config). `vision` also reads the legacy top-level
    # "vision" key for back-compat. When a capability is off the skill DEGRADES rather than
    # failing: peek off ⇒ agents classify from the pre-extracted content_peek, never opening
    # files; vision off ⇒ images route by name/path/EXIF (`organizer.py exif`). See SKILL.md.
    caps = cfg.get("model_capabilities")
    caps = caps if isinstance(caps, dict) else {}   # a malformed (non-dict) value degrades to defaults, never crashes
    vision_on = caps.get("vision", cfg.get("vision", True))
    if getattr(args, "no_vision", False):
        vision_on = False
    peek_on = caps.get("peek", True)
    if getattr(args, "no_peek", False):
        peek_on = False
    skip_types = set(str(t).lower() for t in cfg.get("skip_types", []))
    if getattr(args, "skip_types", None):
        skip_types |= {t.strip().lower() for t in args.skip_types.split(",") if t.strip()}
    skip_types = {(t if t.startswith(".") else "." + t) for t in skip_types}
    skip_over_mb = getattr(args, "skip_over_mb", None)
    if skip_over_mb is None:
        skip_over_mb = cfg.get("skip_over_mb")
    skip_over_bytes = float(skip_over_mb) * 1024 * 1024 if skip_over_mb else None

    need_index = auto_on or (not vision_on) or bool(skip_types) or bool(skip_over_bytes)
    index, dest_set = (_build_rules_index(root) if need_index else ([], set()))
    auto_log = []

    def _open_blocked(e: dict) -> list:
        # Returns ALL applicable block reasons (not just the first) — a file can be blocked by
        # several toggles at once, e.g. ["raw-not-decodable","skip-type"]. The closed reason set
        # is exactly: "raw-not-decodable" (RAW permanent block), "vision-off" (user toggle),
        # "skip-type", ">{N}MB".
        reasons = []
        if e["is_image"]:
            if e["is_raw"]:
                # RAW is PERMANENTLY undecodable (proprietary format — Claude cannot read it
                # even when vision is ON).  Use a distinct reason so consumers can tell this
                # apart from the user's vision-off toggle.
                reasons.append("raw-not-decodable")
            elif not vision_on:
                # Non-RAW image blocked only because the user turned vision off.
                reasons.append("vision-off")
        if e["extension"] in skip_types:
            reasons.append("skip-type")
        if skip_over_bytes and (e["file_size"] or 0) > skip_over_bytes:
            # Render a plain integer when whole (200), else the bare value — never :g, which
            # switches to scientific notation (1e+06) for large MB caps.
            mb = float(skip_over_mb)
            mb_str = str(int(mb)) if mb.is_integer() else repr(skip_over_mb)
            reasons.append(f">{mb_str}MB")
        return reasons

    result = []
    for row in rows:
        ext = (row["extension"] or "").lower()
        entry = {
            "id":           row["id"],
            "current_path": row["current_path"],
            "filename":     row["filename"],
            "extension":    ext,
            "file_size":    row["file_size"],
            "file_date":    row["file_date"],
            "is_raw":       ext in RAW_EXTS,            # camera RAW — never vision-readable
            "is_image":     ext in IMAGE_EXTS or ext in RAW_EXTS,
            "content_peek": row["content_peek"],  # None for images (incl RAW); text for everything else
            "auto_routed":  False,
        }
        blocked = _open_blocked(entry)
        dest = reason = None
        if auto_on:
            dest, reason = _auto_classify_entry(entry, root, index, dest_set)
        elif blocked and index:
            # Even with the fast-path off, a file we're not allowed to OPEN still
            # gets a deterministic destination from the matcher when one exists.
            # WHY this is NOT an auto_approve bypass: `auto_on` governs auto-APPROVAL,
            # not whether a destination is proposed. An unopenable file cannot be
            # LLM-classified, so the matcher is its only routing source — and the
            # result is still a PROPOSAL that passes the browser review like any
            # other, so the human-approval invariant is preserved. (Intentional
            # fallback, not a special-case to remove.)
            dest, reason = _auto_classify_entry(entry, root, index, dest_set)
            if reason:
                reason = "skipped-open; " + reason
        if dest:
            entry["auto_routed"] = True
            # Write the canonical routing field `para_subfolder` (the viewer, bubble-sort,
            # and execute all read THIS) so an auto-routed entry merged unchanged reaches
            # them with its destination intact. `proposed_subfolder` is kept as a readable
            # alias of the same value.
            routed = _normalize_grouping(dest)
            entry["para_subfolder"] = routed
            entry["proposed_subfolder"] = routed
            entry["auto_reason"] = reason
            # Per-entity auto_approve override wins over the global toggle when set
            # (true/false); otherwise inherit the global `auto_approve` unchanged.
            leaf = routed.split("/")[-1]
            entity_meta = entities_meta.get(leaf, {}) if isinstance(entities_meta, dict) else {}
            entity_override = entity_meta.get("auto_approve")
            effective_auto_approve = entity_override if isinstance(entity_override, bool) else auto_approve
            if effective_auto_approve:
                entry["auto_approved"] = True
            auto_log.append((row["id"], row["filename"], routed, reason))
        else:
            entry["needs_classification"] = True
            if blocked:
                # Respect the skip: do not hand the classifier the file content.
                entry["route_by_name_only"] = True
                entry["open_blocked_reason"] = blocked
                entry["content_peek"] = None
        result.append(entry)

    # W1b — partition the to-classify residual into batches of the effective batch size
    # for the fan-out: the skill dispatches one classification sub-agent per
    # classify_batch, briefed with file PATHS (not inlined content). auto_routed files
    # carry no batch. batch_size is config.json's `classify_batch_size` when valid, else
    # the BATCH=25 default (see paths_config._effective_batch_size).
    batch_size = _effective_batch_size(root)
    to_classify = [e for e in result if e.get("needs_classification")]
    for i, e in enumerate(to_classify):
        e["classify_batch"] = i // batch_size
    n_batches = (len(to_classify) + batch_size - 1) // batch_size

    # Audit trail: every auto-route is appended to <root>/.organizer/auto-routed.csv
    # so the user can see exactly what was decided deterministically (never opaque).
    # This is a best-effort APPEND-ONLY audit log, NOT authoritative state — the registry
    # (DB) is the source of truth — so it is written with a plain append (not _atomic_write):
    # a partial row from a crash mid-flush is cosmetic, never corrupts routing. Both kinds of
    # deterministic route land here and are distinguished by the `reason` column: a W1 fast-path
    # match has a bare reason; a file blocked-from-opening that the matcher still placed carries
    # the `skipped-open; ` prefix (set above) — same channel, self-labelling reasons.
    if auto_log:
        import csv as _csv
        audit = root / ".organizer" / "auto-routed.csv"
        audit.parent.mkdir(parents=True, exist_ok=True)
        new = not audit.exists()
        with open(audit, "a", newline="", encoding="utf-8") as f:
            w = _csv.writer(f)
            if new:
                w.writerow(["timestamp", "id", "filename", "destination", "reason"])
            ts = datetime.now().isoformat(timespec="seconds")
            for rid, fn, dest, reason in auto_log:
                w.writerow([ts, rid, fn, dest, reason])
        print(f"Auto-classified {len(auto_log)}/{len(rows)} files (fast-path) — "
              f"{len(rows) - len(auto_log)} need classification. Audit: {audit}", file=sys.stderr)

    name_only = sum(1 for e in to_classify if e.get("route_by_name_only"))
    print(f"To classify: {len(to_classify)} file(s) in {n_batches} batch(es) of {batch_size} "
          f"(fan-out one sub-agent per classify_batch){'; ' + str(name_only) + ' route-by-name-only (open blocked)' if name_only else ''}.",
          file=sys.stderr)
    print(f"Model capabilities: peek={'on' if peek_on else 'off'}, vision={'on' if vision_on else 'off'}. "
          f"Fill [CAPABILITIES] in references/classify-prompt.md from this: peek off ⇒ agents classify from the "
          f"pre-extracted content_peek and NEVER open files; vision off ⇒ route images by name/path + "
          f"`organizer.py exif <path>` metadata, never opening pixels.", file=sys.stderr)

    # Write project-metadata sidecar so Claude can look up filename_tag and
    # date_range for each known project when classifying.
    metadata = _enumerate_project_metadata(paths_config._EFFECTIVE_ROOT)
    sidecar = Path.home() / ".claude" / "drive-organizer" / "project_metadata.json"
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(sidecar, json.dumps(metadata, indent=2))
    print(f"Project metadata sidecar: {sidecar} ({len(metadata)} projects)", file=sys.stderr)

    # Surface active entity policies (Phase-3 Tier-1): a non-empty `policy` on an
    # entity now drives routing (see references/classify-prompt.md "Policy-driven
    # routing"); list them so the field is observable, not silently dormant.
    policies = {name: m["policy"] for name, m in _read_entities(paths_config._EFFECTIVE_ROOT).items()
                if isinstance(m, dict) and m.get("policy")}
    if policies:
        print(f"Active entity policies ({len(policies)}): "
              + ", ".join(f"{n}={p}" for n, p in sorted(policies.items())), file=sys.stderr)

    # Surface active entity filename_tags (Phase-3 Tier-1 item #3): a non-empty
    # `filename_tag` on an entity is the canonical tag for new_filename — same
    # purpose as a project's filename_tag, just entity-level (see
    # references/classify-prompt.md). List them so classify-time agents can use
    # a fixed tag instead of re-inferring the issuer/person name every round.
    entity_tags = {name: m["filename_tag"] for name, m in _read_entities(paths_config._EFFECTIVE_ROOT).items()
                   if isinstance(m, dict) and m.get("filename_tag")}
    if entity_tags:
        print(f"Active entity filename_tags ({len(entity_tags)}): "
              + ", ".join(f"{n}={t}" for n, t in sorted(entity_tags.items())), file=sys.stderr)

    print(json.dumps(result, indent=2))


# ---------------------------------------------------------------------------
# execute
# ---------------------------------------------------------------------------
