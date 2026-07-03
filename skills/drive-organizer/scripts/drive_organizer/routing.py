"""drive_organizer.routing — shared grouping/PARA-projection utilities used across the
organiser (classify_propose, execute, entities_rules, bootstrap, rules_viewer, reconcile).
Split out of cleanup_reconcile.py: these are general routing helpers, not reconcile-only
logic — reconcile.py is simply one of several callers."""
from __future__ import annotations

from drive_organizer.paths_config import _read_user_config, _load_templates


# The five groupings are the DEFAULT, not a hard limit. The active area set is
# data-driven (see _active_groupings): a user may have more, fewer, or differently
# named top-level groupings, declared via templates Q1_groupings or config "areas".
DEFAULT_GROUPINGS = {"ENTERTAINMENT", "PERSONAL", "WORK", "EDUCATION", "RESOURCES"}


def _active_groupings() -> set:
    """The active set of top-level grouping (area) names, ALL-CAPS, derived in order:
      1. config.json "areas": [...]  (per-drive override — authoritative if present)
      2. merged templates' "Q1_groupings" list (shipped skeleton ⊕ user override)
      3. DEFAULT_GROUPINGS (the shipped five) as a last-resort fallback
    Not independently cached — groupings are derived from _load_templates(), which
    carries its own mtime-keyed cache. Caching groupings separately would leave a
    stale window whenever paths_config._TEMPLATES_CACHE is repopulated (e.g. after a live save
    invalidates it), so groupings are derived on every call at negligible cost."""

    def _name(entry):
        # Q1_groupings entries (and config "areas") may be plain strings or dicts
        # carrying a "name" key (the templates skeleton uses the dict form).
        if isinstance(entry, dict):
            return entry.get("name")
        return entry

    areas = None
    cfg = _read_user_config()
    if isinstance(cfg.get("areas"), list) and cfg["areas"]:
        areas = cfg["areas"]
    if areas is None:
        q1 = _load_templates().get("Q1_groupings")
        if isinstance(q1, list) and q1:
            areas = q1
    if areas is None:
        areas = DEFAULT_GROUPINGS
    names = {str(_name(a)).upper() for a in areas if _name(a)}
    return names or {g.upper() for g in DEFAULT_GROUPINGS}


def _para_category(sub_rel: str, groupings=None) -> str:
    """The PARA category for a destination subfolder: its first path segment if that is
    an active grouping, else '_Inbox'. This is the SINGLE authoritative home for the
    projection — execute and crash-recovery both call it, and the verdict contract omits
    para_category entirely so the backend always derives it here. (The viewer's client-side
    `inferCategory` is NOT a mirror: it takes the raw first segment with no grouping check,
    and is display-only — its value is never sent back or persisted, so the two need not
    and do not match for legacy-flat paths.)
    `groupings` should be pre-loaded by the caller (e.g. cmd_execute calls _active_groupings()
    once at the top and passes it here) to avoid re-reading config.json on every file."""
    if groupings is None:
        groupings = _active_groupings()
    first_seg = sub_rel.split("/")[0] if sub_rel else ""
    # Normalise case before the membership check: groupings are stored canonical ALL-CAPS
    # (_active_groupings upper-cases them), but a destination derived from an on-disk path
    # (e.g. reconcile's Path.relative_to) can carry a miscased segment like 'Personal/'.
    # Compare upper-cased and return the canonical grouping so a miscased folder projects
    # to its real category instead of falling to '_Inbox' (which caused a reconcile re-flag loop).
    return first_seg.upper() if first_seg.upper() in groupings else "_Inbox"


def _ensure_in_suffix(desc: str, leaf: str) -> str:
    """Ensure a rule description carries the required ' in <leaf>' suffix (the
    self-describing-sentence convention; see SKILL.md "Description format"). The SINGLE
    home for the append — every site that writes a rule description calls this, so the
    suffix convention can never drift between writers."""
    if desc and not desc.endswith(f" in {leaf}"):
        return f"{desc} in {leaf}"
    return desc


def _normalize_grouping(para: str) -> str:
    """Force a destination's top-level grouping segment to its canonical ALL-CAPS
    form, so a viewer edit like 'Personal/PERSONAL Financial' lands in
    'PERSONAL/PERSONAL Financial'. Only the first path segment is touched; deeper
    names keep their case. (reconcile remains the safety net for legacy miscased
    folders already on disk.)"""
    if not para:
        return para
    parts = para.split("/")
    if parts[0].upper() in _active_groupings():
        parts[0] = parts[0].upper()
    return "/".join(parts)
