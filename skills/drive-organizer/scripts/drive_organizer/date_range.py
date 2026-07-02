"""drive_organizer.date_range — split from the original organizer.py (pure structural move, no behavior change)."""
from __future__ import annotations
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

from drive_organizer import paths_config
from drive_organizer.paths_config import (
    PARA_ROOTS,
    _atomic_write,
    _effective_date_ceiling_days,
    _effective_date_floor,
    _is_external,
    _safe_dest,
)


def _project_metadata(project_path: Path) -> dict:
    """
    Read filename_tag and date_range from a project's .tidy-rules.json.
    Returns {} if the file is missing, unparseable, or has no metadata fields.
    """
    rules_file = project_path / ".tidy-rules.json"
    if not rules_file.exists():
        return {}
    try:
        data = json.loads(rules_file.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"WARNING: could not parse {rules_file} ({e}); "
              f"treating '{project_path.name}' as having no project metadata.", file=sys.stderr)
        return {}
    if not isinstance(data, dict):
        return {}
    out = {}
    if data.get("filename_tag"):
        out["filename_tag"] = data["filename_tag"]
    dr = data.get("date_range") or data.get("production_period")  # legacy key back-compat
    if dr:
        out["date_range"] = dr
    return out


def _enumerate_project_metadata(root: Path) -> list:
    """
    Walk top-level project folders under root and collect their metadata.
    Returns list of {path (relative), filename_tag?, date_range?} entries for every folder
    whose .tidy-rules.json carries a filename_tag **OR a date_range** (Phase-3 generalisation:
    date-first routing is no longer projects-only — an area, an event folder, a course-term or
    tax-year folder can carry a date_range and route dated files by date even with no
    filename_tag). Used by propose to surface candidate matches by date for loose bills/photos.
    """
    out = []
    # The walk is unrolled to EXACTLY three levels on purpose — it mirrors the
    # Cascading-Q structure, not an arbitrary depth: level 1 = top-level grouping (or a
    # legacy flat project), level 2 = the "thing inside" (entity / company), level 3 =
    # the project folder (e.g. WORK/ACME/ACME Project Alpha/). A project's
    # filename_tag can live at any of those three depths, but never deeper — depth-4+
    # folders are leaf TYPE subfolders (Scripts, Docs, …), never project roots, so a
    # generic recursive walk would have to re-impose this same cap and would additionally
    # blur the depth-specific skip rules below (level 1 excludes SKIP; levels 2–3 exclude
    # PARA_ROOTS). Keeping the three levels explicit makes that domain contract legible.
    SKIP = {".organizer", "Archive"}
    try:
        tops = sorted(root.iterdir())
    except (PermissionError, OSError) as e:
        print(f"WARNING: could not list {root} ({e}); no project metadata enumerated.",
              file=sys.stderr)
        return out
    for top in tops:
        if not top.is_dir() or top.name.startswith(('.', '_')):
            continue
        if top.name in SKIP:
            continue
        if _is_external(top):
            continue
        # Direct-level project (legacy flat)
        meta = _project_metadata(top)
        if meta.get("filename_tag") or meta.get("date_range"):
            out.append({"path": top.name, **meta})
        # Two-level (new nested: WORK/COMPANY/PROJECT, PERSONAL/PERSONAL X)
        try:
            for mid in sorted(top.iterdir()):
                if not mid.is_dir() or mid.name.startswith(('.', '_')) or mid.name in PARA_ROOTS:
                    continue
                if _is_external(mid):
                    continue
                meta_mid = _project_metadata(mid)
                if meta_mid.get("filename_tag") or meta_mid.get("date_range"):
                    out.append({"path": f"{top.name}/{mid.name}", **meta_mid})
                # Three-level (e.g. WORK/ACME/ACME Project Alpha/)
                try:
                    for deep in sorted(mid.iterdir()):
                        if not deep.is_dir() or deep.name.startswith(('.', '_')) or deep.name in PARA_ROOTS:
                            continue
                        if _is_external(deep):
                            continue
                        meta_deep = _project_metadata(deep)
                        if meta_deep.get("filename_tag") or meta_deep.get("date_range"):
                            out.append({"path": f"{top.name}/{mid.name}/{deep.name}", **meta_deep})
                except (PermissionError, OSError):
                    pass
        except (PermissionError, OSError):
            pass
    return out


def _find_project_for_destination(dest_subfolder: str, root: Path) -> "Path | None":
    """
    Given a destination subfolder path like 'WORK/ACME/ACME Project Alpha/Scripts',
    walk up from the deepest folder until we find an ancestor whose .tidy-rules.json
    carries a filename_tag OR a date_range. Returns the absolute path to that folder,
    or None. A date_range-only ancestor (an area/event/tax-year folder with no
    filename_tag) is a valid dated destination — it must match _enumerate_project_metadata
    (which accepts filename_tag OR date_range), so execute can widen its date_range too.
    """
    if not dest_subfolder:
        return None
    # Contain the candidate inside root: reject absolute / '..' / symlink escapes
    # so we never walk arbitrary ancestors outside the configured drive.
    cur = _safe_dest(root, dest_subfolder)
    if cur is None:
        return None
    root_r = Path(root).resolve()
    # Walk up until cur is root
    while True:
        if cur == root_r or cur.parent == cur:
            return None
        meta = _project_metadata(cur)
        # Accept filename_tag OR date_range — mirrors _enumerate_project_metadata so a
        # date_range-only folder (area/event/tax-year, no filename_tag) is still a valid
        # dated destination and execute can widen its date_range.
        if meta.get("filename_tag") or meta.get("date_range"):
            return cur
        cur = cur.parent


def _expand_date_range(project_path: Path, file_date_iso: str, buffer_days: int = 30,
                        root: "Path | None" = None) -> None:
    """
    Expand the project's date_range to include file_date_iso, with a
    buffer_days padding at each end. If the project has no date_range
    yet, initialise one centred on this file's date. Writes back to .tidy-rules.json.

    `buffer_days` is a plain function default (30) — callers should pass the effective
    per-drive value explicitly via `buffer_days=paths_config._effective_period_buffer_days(root)`
    (config.json's `period_buffer_days`, else 30) rather than relying on this default;
    it stays at 30 here only as a safety net for a caller that omits it.

    `root` resolves the config-aware clamp bounds (config.json's `date_floor` /
    `date_ceiling_days`, else datetime(1990,1,1) / now+365d) via
    _effective_date_floor()/_effective_date_ceiling_days(). Callers should pass the
    active drive root explicitly; omitting it falls back to paths_config._EFFECTIVE_ROOT
    (via the helpers' own `root or _EFFECTIVE_ROOT` default), same safety-net posture as
    `buffer_days`.
    """
    rules_file = project_path / ".tidy-rules.json"
    if not rules_file.exists():
        return
    try:
        data = json.loads(rules_file.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"WARNING: could not parse {rules_file} ({e}); "
              f"not expanding date_range.", file=sys.stderr)
        return
    if not isinstance(data, dict):
        return  # legacy list-format files don't carry project metadata

    try:
        file_dt = datetime.fromisoformat(file_date_iso[:10])
    except (ValueError, TypeError):
        return

    # Clamp the file date to a sane range so one mis-dated file (e.g. epoch 1970,
    # or a future timestamp from a bad clock) can't blow the period out forever.
    # Bounds are config-aware: config.json's `date_floor` / `date_ceiling_days`, else
    # the same datetime(1990,1,1) / now+365d this always used (unset config reproduces
    # today's exact behavior).
    floor_dt = _effective_date_floor(root)
    ceil_dt = datetime.now() + timedelta(days=_effective_date_ceiling_days(root))
    if file_dt < floor_dt or file_dt > ceil_dt:
        return  # out-of-range date: ignore rather than widen the period

    buf = timedelta(days=buffer_days)
    period = data.get("date_range") or data.get("production_period")  # legacy key back-compat
    if not period or not isinstance(period, dict):
        new_start = (file_dt - buf).date().isoformat()
        new_end = (file_dt + buf).date().isoformat()
    else:
        # Parse the existing bounds independently. A half-open period (only start
        # OR only end set) is widened only on the side that exists — the missing
        # bound is filled from THIS file's date, never coerced to overwrite a
        # real existing bound. Non-ISO bound strings are treated as absent.
        def _parse(v):
            if not v:
                return None
            try:
                return datetime.fromisoformat(str(v)[:10])
            except (ValueError, TypeError):
                return None
        cur_start = _parse(period.get("start"))
        cur_end = _parse(period.get("end"))
        new_start_dt = min(cur_start, file_dt - buf) if cur_start is not None else (file_dt - buf)
        new_end_dt = max(cur_end, file_dt + buf) if cur_end is not None else (file_dt + buf)
        new_start = new_start_dt.date().isoformat()
        new_end = new_end_dt.date().isoformat()

    # Use the already-resolved `period` (which covers both "date_range" and the
    # legacy "production_period" key) so the guard fires for files that have not
    # yet been migrated to "date_range".  Comparing data.get("date_range") alone
    # would always return None for legacy files, making the guard a no-op for them.
    # C6: this is a whole-period short-circuit — it fires only when BOTH bounds already
    # equal the computed targets (i.e. the period is already exactly right). It does NOT
    # mean "each bound is already up to date independently"; widening is per-bound
    # idempotent but this guard requires both to match simultaneously before skipping the write.
    if period == {"start": new_start, "end": new_end}:
        return  # nothing changed
    data["date_range"] = {"start": new_start, "end": new_end}
    data.pop("production_period", None)  # migrate legacy key on write
    _atomic_write(rules_file, json.dumps(data, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
