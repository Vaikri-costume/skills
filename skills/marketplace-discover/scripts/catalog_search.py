#!/usr/bin/env python3
"""Search every Claude Code marketplace catalogue on disk for a described need.

Usage:
    catalog_search.py [--plugins-dir DIR] [--skip NAME,NAME] [--only NAME,NAME]
                      [--stale-hours N] [--limit N] KEYWORD [KEYWORD ...]

Reads (read-only, no network):
  <plugins-dir>/known_marketplaces.json   which marketplaces are configured
  <plugins-dir>/marketplaces/*/            every checked-out marketplace
  <plugins-dir>/plugin-directory-cache-v2.json   Anthropic's built-in directory (if present)

Prints one JSON object on stdout:
  marketplaces: name, path, entries, age_hours, stale, status per marketplace
  directory:    the built-in directory (listings count, fetched_at timestamp, matches) or null
  candidates:   ranked entries (name, marketplace, description, category, source,
                homepage, score, matched, install, local_folder, description_flag)
  notes:        anything the reader must be told (missing files, skipped entries)

Exit codes: 0 ran; 2 usage error or no keywords; 3 no marketplace was searched (none readable,
or every one skipped by --skip or --only; the built-in directory is not read either).
local_folder is the plugin's folder on disk: a path-style source, or the external_plugins/<sub>
folder of an external plugin; null otherwise (remote source, a string source not starting with
"." or "/", or a folder that is missing or outside the marketplace).
Pure standard library. The install command is built only for marketplace entries
(`claude plugin install <name>@<marketplace>`); directory-only listings get no
install command because their id is not the display name.
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # -I does not add the script folder
sys.dont_write_bytecode = True  # importing vet_plugin must not write a __pycache__ file: the skill writes no files
from vet_plugin import AI_TEXT  # noqa: E402

DEFAULT_STALE_HOURS = 24


def _load_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def find_marketplaces(plugins_dir, notes):
    """Return {name: root_path} from known_marketplaces.json plus marketplaces/*."""
    found = {}
    updated = {}
    unlocated = []
    known = os.path.join(plugins_dir, "known_marketplaces.json")
    if os.path.isfile(known):
        try:
            for name, meta in _load_json(known).items():
                loc = (meta or {}).get("installLocation")
                if loc and os.path.isdir(loc):
                    found[name] = loc
                    updated[name] = (meta or {}).get("lastUpdated")
                else:
                    unlocated.append(name)
        except (OSError, ValueError, AttributeError) as exc:
            notes.append(f"known_marketplaces.json unreadable: {exc}")
    base = os.path.join(plugins_dir, "marketplaces")
    if os.path.isdir(base):
        for name in sorted(os.listdir(base)):
            root = os.path.join(base, name)
            if os.path.isdir(root) and name not in found:
                found[name] = root
    # A listed marketplace whose installLocation is stale may still sit under marketplaces/; it is
    # reported as not checked out only when neither source located it.
    for name in unlocated:
        if name not in found:
            notes.append(f"{name}: listed in known_marketplaces.json but not checked out on disk")
    return found, updated


def parse_iso(text):
    """Seconds since epoch from an ISO-8601 string such as 2026-10-05T16:35:42.165Z, else None."""
    import datetime
    try:
        return datetime.datetime.fromisoformat(str(text).replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError):
        return None


def catalogue_file(root):
    for rel in (os.path.join(".claude-plugin", "marketplace.json"), "marketplace.json"):
        path = os.path.join(root, rel)
        if os.path.isfile(path):
            return path
    return None


def load_entries(root, notes, name):
    """Entries from the catalogue file plus any external_plugins/*/plugin.json.

    Returns (entries, catalogue_path, folders); folders maps an external plugin's name to its
    external_plugins/<sub> folder, which is its local_folder in the search output.
    """
    entries, folders = [], {}
    path = catalogue_file(root)
    if path:
        try:
            plugins = _load_json(path).get("plugins")
            if plugins is None:
                plugins = []
            if not isinstance(plugins, list):
                raise ValueError("plugins is not a list")
            entries.extend(p for p in plugins if isinstance(p, dict) and p.get("name"))
        except (OSError, ValueError, AttributeError) as exc:
            # An unparsable catalogue counts as no catalogue file, so the caller does not report it as searched.
            path = None
            notes.append(f"{name}: catalogue unreadable ({exc})")
    else:
        notes.append(f"{name}: no marketplace.json found")
    ext = os.path.join(root, "external_plugins")
    if os.path.isdir(ext):
        seen = {e["name"] for e in entries}
        for sub in sorted(os.listdir(ext)):
            pj = os.path.join(ext, sub, ".claude-plugin", "plugin.json")
            if not os.path.isfile(pj):
                continue
            try:
                entry = _load_json(pj)
            except (OSError, ValueError):
                notes.append(f"{name}: skipped external plugin {sub} (plugin.json unreadable)")
                continue
            if isinstance(entry, dict) and entry.get("name") and entry["name"] not in seen:
                entries.append(entry)
                folders[entry["name"]] = os.path.join(ext, sub)
                seen.add(entry["name"])
    return entries, path, folders


def source_text(src):
    if isinstance(src, str):
        return src
    if isinstance(src, dict):
        return src.get("url") or src.get("repo") or src.get("path") or json.dumps(src, sort_keys=True)
    return ""


def local_folder(root, src):
    """Folder on disk for a path-style source such as ./plugins/x, else None."""
    if not isinstance(src, str) or not src.startswith((".", "/")) or "://" in src:
        return None
    full = os.path.normpath(os.path.join(root, src))
    inside = os.path.commonpath([os.path.realpath(root), os.path.realpath(full)]) == os.path.realpath(root)
    return full if inside and os.path.isdir(full) else None


def score_entry(entry, keywords):
    """Keyword score: name hit 3, category/keywords hit 2, description hit 1 (per keyword)."""
    name = str(entry.get("name", "")).lower()
    cat = str(entry.get("category", "")).lower()
    kws = " ".join(str(k) for k in entry.get("keywords", []) or []).lower()
    desc = str(entry.get("description", "")).lower()
    score, matched = 0, []
    for kw in keywords:
        k = kw.lower()
        hit = 0
        if k in name:
            hit = max(hit, 3)
        if k in cat or k in kws:
            hit = max(hit, 2)
        if k in desc:
            hit = max(hit, 1)
        if hit:
            score += hit
            matched.append(kw)
    return score, matched


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("keywords", nargs="*")
    ap.add_argument("--plugins-dir", default=os.path.expanduser("~/.claude/plugins"))
    ap.add_argument("--skip", default="", help="comma-separated marketplace names to leave out")
    ap.add_argument("--only", default="", help="comma-separated marketplace names to search (default all)")
    ap.add_argument("--stale-hours", type=float, default=DEFAULT_STALE_HOURS)
    ap.add_argument("--limit", type=int, default=30)
    args = ap.parse_args(argv)
    keywords = [k for k in args.keywords if k.strip()]
    if not keywords:
        print("error: give at least one keyword", file=sys.stderr)
        return 2

    args.plugins_dir = os.path.abspath(os.path.expanduser(args.plugins_dir))  # local_folder is documented as absolute
    skip = {s for s in args.skip.split(",") if s}
    only = {s for s in args.only.split(",") if s}
    notes = []
    now = time.time()
    roots, updated = find_marketplaces(args.plugins_dir, notes)
    mp_report, candidates = [], []

    for name, root in sorted(roots.items()):
        if name in skip or (only and name not in only):
            skipped_entries, _, _ = load_entries(root, [], name)
            hidden = sum(1 for e in skipped_entries if score_entry(e, keywords)[0])
            mp_report.append({"name": name, "path": root, "status": "skipped by profile or request",
                              "matches_not_shown": hidden})
            continue
        entries, path, folders = load_entries(root, notes, name)
        if path is None and not entries:
            mp_report.append({"name": name, "path": root, "status": "no catalogue file"})
            continue
        stamp = parse_iso(updated.get(name)) if updated.get(name) else None
        if stamp is None and path:
            stamp = os.path.getmtime(path)
        age = (now - stamp) / 3600 if stamp is not None else None
        mp_report.append({
            "name": name, "path": root, "status": "searched", "entries": len(entries),
            "age_hours": round(age, 1) if age is not None else None,
            "stale": bool(age is not None and age > args.stale_hours),
        })
        for e in entries:
            score, matched = score_entry(e, keywords)
            if not score:
                continue
            candidates.append({
                "name": e["name"], "marketplace": name,
                "description": e.get("description", ""), "category": e.get("category", ""),
                "source": source_text(e.get("source")), "homepage": e.get("homepage", ""),
                "score": score, "matched": matched,
                "install": f"claude plugin install {e['name']}@{name}",
                "local_folder": local_folder(root, e.get("source")) or folders.get(e["name"]),
                "description_flag": ("instruction-like text aimed at an AI in the catalogue description"
                                     if AI_TEXT.search(str(e.get("description", ""))) else None),
            })

    if not any(m.get("status") == "searched" for m in mp_report):
        print(json.dumps({"marketplaces": mp_report, "directory": None, "candidates": [], "notes": notes}, indent=2))
        return 3

    directory = None
    dpath = os.path.join(args.plugins_dir, "plugin-directory-cache-v2.json")
    if os.path.isfile(dpath):
        try:
            d = _load_json(dpath)
            listings = d.get("listings")
            if listings is None:
                listings = []
            if not isinstance(listings, list):
                raise ValueError("listings is not a list")
            directory = {"listings": len(listings), "fetched_at": d.get("fetchedAt"), "matches": []}
            for item in listings:
                entry = {"name": item.get("name", ""), "description": item.get("summary", "")}
                score, matched = score_entry(entry, keywords)
                if score:
                    repo = ((item.get("source") or {}).get("repository") or {}).get("url", "")
                    directory["matches"].append({
                        "name": entry["name"], "description": entry["description"],
                        "repository": repo, "score": score, "matched": matched,
                    })
            directory["matches"].sort(key=lambda m: (-m["score"], m["name"].lower()))
            directory["matches"] = directory["matches"][: args.limit]
        except (OSError, ValueError, AttributeError) as exc:
            notes.append(f"built-in directory cache unreadable: {exc}")

    candidates.sort(key=lambda c: (-c["score"], c["name"].lower(), c["marketplace"]))
    out = {"marketplaces": mp_report, "directory": directory, "candidates": candidates[: args.limit], "notes": notes}
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
