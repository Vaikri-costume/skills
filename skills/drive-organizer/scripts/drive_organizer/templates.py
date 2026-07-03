"""drive_organizer.templates — split from paths_config.py (pure structural move, no behavior change).

Subfolder-template loading/merging: the shipped generic skeleton
(references/subfolder-templates.json) deep-merged with a per-drive user override
(<root>/.organizer/templates.json)."""
from __future__ import annotations
import copy
import json
import os
import sys
from pathlib import Path

from drive_organizer import paths_config
from drive_organizer.paths_config import _skill_references_dir


def _merge_lists(base_list: list, override_list: list) -> list:
    """
    Merge two lists for the template override. If every element is a dict with a
    "name" key, merge by name (override replaces the same-named base entry, new
    names append) — so a user override of `ENTERTAINMENT` cleanly replaces the
    skeleton's `ENTERTAINMENT` rather than duplicating it. Otherwise concatenate
    with simple dedup.

    Dedup semantics (by-name branch): keys are the `name` values; within base or
    override, an earlier same-named entry is dropped in favour of the override's
    (or, absent an override, the base's first occurrence). If any `name` is
    unhashable (e.g. a list/dict value), we cannot build the name index, so we
    fall back to the concat+value-dedup branch rather than crash.
    """
    items = base_list + override_list
    if items and all(isinstance(x, dict) and "name" in x for x in items):
        try:
            by_name = {x["name"]: x for x in base_list}
            for x in override_list:
                by_name[x["name"]] = x  # override wins
            result, seen = [], set()
            for x in base_list + override_list:
                if x["name"] not in seen:
                    result.append(by_name[x["name"]])
                    seen.add(x["name"])
            return result
        except TypeError:
            # An unhashable "name" — can't dedup by name; fall through to concat.
            pass
    return base_list + [x for x in override_list if x not in base_list]


def _deep_merge(base: dict, override: dict) -> dict:
    """
    Recursively merge `override` into a copy of `base`. Dicts merge key-by-key;
    lists merge via _merge_lists (by "name" when present, else concat+dedup);
    scalars from the override win. Used to layer a per-user template override
    over the shipped skeleton.

    The result must NOT alias the cached base or the override: nested dict/list
    values that are NOT recursively merged are deep-copied so a caller mutating
    the returned tree can never corrupt the process-wide _TEMPLATES_CACHE base.
    """
    out = {k: copy.deepcopy(v) for k, v in base.items()}
    for k, v in override.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        elif k in out and isinstance(out[k], list) and isinstance(v, list):
            # _merge_lists returns elements aliased from base/override; deep-copy
            # so the merged list can't reach back into the cached base or override.
            out[k] = copy.deepcopy(_merge_lists(out[k], v))
        else:
            out[k] = copy.deepcopy(v)
    return out


_TEMPLATES_CACHE = None


def _reset_cache():
    """Clear this module's process-level cache. Called by paths_config._reset_caches()."""
    global _TEMPLATES_CACHE
    _TEMPLATES_CACHE = None


def _load_templates() -> dict:
    """
    Load the subfolder templates source-of-truth from the skill's references folder,
    then deep-merge any per-user override at <root>/.organizer/templates.json on top.
    Returns {} if the shipped file is missing.

    Caching: a long-running viewer server can hold this process while the user
    edits their override file, so the cache is keyed on the override file's mtime
    (and existence) — if that changes, we re-read instead of serving stale data.

    The shipped file is a generic skeleton (the five Q1 groupings + universal compound
    children). Each user grows their own taxonomy lazily via .tidy-rules.json, and may
    also drop a templates.json beside their registry to extend the skeleton with their
    own projects/structure — that override is merged here so the shipped skill stays
    generic while the user's drive carries their specifics.
    """
    global _TEMPLATES_CACHE
    override_path = None
    if paths_config._EFFECTIVE_ROOT:
        override_path = Path(paths_config._EFFECTIVE_ROOT) / ".organizer" / "templates.json"
    try:
        override_mtime = override_path.stat().st_mtime if override_path and override_path.exists() else None
    except OSError:
        override_mtime = None
    # Templates live in the skill's references/ at the canonical Claude Code skills
    # path. First-time-setup copies the drive_organizer/ package plus the thin
    # organizer.py entrypoint to ~/.claude/drive-organizer/; references/ are NOT
    # copied, so they are read from the install dir here. If the
    # skill is installed somewhere non-standard this file won't be found and `base`
    # stays {} (then _active_groupings falls back to DEFAULT_GROUPINGS and the taxonomy
    # is the bare skeleton) — a documented degradation, not a crash. Override with the
    # DRIVE_ORG_SKILL_DIR env var when installed elsewhere.
    skill_dir = os.environ.get("DRIVE_ORG_SKILL_DIR")
    base_dir = Path(skill_dir) if skill_dir else (Path.home() / ".claude" / "skills" / "drive-organizer")
    templates_path = base_dir / "references" / "subfolder-templates.json"
    try:
        skeleton_mtime = os.path.getmtime(templates_path) if templates_path.exists() else 0
    except OSError:
        skeleton_mtime = 0
    cache_key = (override_mtime, skeleton_mtime)
    if _TEMPLATES_CACHE is not None and _TEMPLATES_CACHE[0] == cache_key:
        return _TEMPLATES_CACHE[1]
    base = {}
    if templates_path.exists():
        try:
            base = json.loads(templates_path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"WARNING: could not parse shipped templates {templates_path} "
                  f"({e}); using empty skeleton.", file=sys.stderr)
            base = {}
    # Per-user override on the active drive (never shipped with the skill).
    if override_path and override_path.exists():
        try:
            override = json.loads(override_path.read_text(encoding="utf-8"))
            if isinstance(override, dict):
                base = _deep_merge(base, override)
        except Exception as e:
            print(f"WARNING: could not parse template override {override_path} "
                  f"({e}); ignoring it.", file=sys.stderr)
    _TEMPLATES_CACHE = (cache_key, base)
    return base


def cmd_templates(args):
    """Print the effective templates as JSON — the shipped generic skeleton
    deep-merged with the per-user <root>/.organizer/templates.json override.
    The propose flow loads THIS (not the raw shipped file) so the executor sees
    the user's full taxonomy, not just the generic skeleton."""
    print(json.dumps(_load_templates(), ensure_ascii=False, indent=2))
