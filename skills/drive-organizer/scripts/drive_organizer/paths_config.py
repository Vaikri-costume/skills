"""drive_organizer.paths_config — split from the original organizer.py (pure structural move, no behavior change)."""
from __future__ import annotations
import functools
import json
import os
import sys
import threading
from datetime import datetime
from pathlib import Path


REGISTRY_DB = Path.home() / ".claude" / "drive-organizer" / "registry.db"  # overridden at startup


def _default_root() -> Path:
    """Best-effort default drive root per OS (override with --root; saved to config).
    macOS and Windows have a standard OneDrive sync location; Linux has no convention, so
    we guess ~/OneDrive and rely on the 'root not found' guard + --root to correct it. The
    name DEFAULT_ONEDRIVE is historical — any cloud or local drive works via --root."""
    home = Path.home()
    if sys.platform == "darwin":
        return home / "Library" / "CloudStorage" / "OneDrive-Personal"
    if sys.platform == "win32":
        # The OneDrive client exports %OneDrive%; fall back to %USERPROFILE%\OneDrive.
        env = os.environ.get("OneDrive") or os.environ.get("OneDriveConsumer")
        return Path(env) if env else home / "OneDrive"
    # Linux / other: no standard cloud-sync path. Guess ~/OneDrive (e.g. abraunegg/onedrive,
    # onedriver); the user overrides with --root when the drive lives elsewhere.
    return home / "OneDrive"


DEFAULT_ONEDRIVE = _default_root()
CONFIG_PATH = Path.home() / ".claude" / "drive-organizer" / "config.json"
_EFFECTIVE_ROOT = DEFAULT_ONEDRIVE  # set in main() from --root / config / DEFAULT
_PATHS_FINALIZED = False  # flipped by _finalize_runtime_paths(); see get_db()

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".heic", ".heif", ".webp", ".tiff", ".tif", ".bmp", ".jfif"}
# Camera RAW formats (file-type-routing.md "Images and Camera RAW"). RAW is an image for
# routing purposes (no text peek, route by parent folder + filename) BUT can NEVER be
# vision-read regardless of the vision toggle — Claude can't decode proprietary RAW. So
# is_image is TRUE for RAW (the no-peek / image-routing gate) and RAW is permanently
# vision-blocked (see _open_blocked), making the arbiter route it by name like a JPEG.
RAW_EXTS = {".nef", ".raf", ".arw", ".cr2", ".cr3", ".dng", ".orf", ".rw2"}
# RAW formats are not in IMAGE_EXTS — Claude can't vision-read them, and the skill routes
# them by filename + parent folder via the Documents/RAW process instead.
SKIP_NAMES = {".DS_Store", ".localized", "desktop.ini", "thumbs.db", ".tidy-rules.json"}
SKIP_EXTS  = {".tmp", ".partial", ".lnk", ".ini"}

# Optional third-party libraries. Each enables a RICHER signal, but every call site
# guards its import and degrades cleanly when the library is absent (PDF/audio peek →
# None and the file routes by name/path/rule; EXIF → filename-date fallback; merge →
# a clean "not installed" exit). The probe below is purely informational: it surfaces
# which optional features are inactive ONCE at startup, so "why didn't it read the PDF
# text / audio tags?" is a visible one-line notice instead of a silent surprise.
# (`organize-tool` is deliberately NOT here: reconcile only *emits* a hand-written YAML
#  artifact for an optional manual cross-check — it never invokes the external tool, so
#  there is no runtime dependency to degrade.)
_OPTIONAL_DEPS = [
    ("fitz",    "pymupdf", "PDF text-peek + annotation merge"),
    ("mutagen", "mutagen", "audio tag reading (artist / album / title)"),
    ("PIL",     "pillow",  "EXIF date + camera for vision-off image routing"),
]


def _missing_optional_deps() -> list:
    """Return [(pip_name, what_it_enables), …] for each optional dep that is NOT
    importable. Pure check — each import is guarded, never raises."""
    missing = []
    for module, pip_name, enables in _OPTIONAL_DEPS:
        try:
            __import__(module)
        except Exception:
            missing.append((pip_name, enables))
    return missing


def _print_optional_deps_notice():
    """One-line stderr notice naming any inactive optional features (degraded, not
    broken). Silent when everything is present, so a fully-provisioned install sees
    nothing."""
    missing = _missing_optional_deps()
    if not missing:
        return
    items = "; ".join(f"{name} ({enables})" for name, enables in missing)
    pkgs = " ".join(name for name, _ in missing)
    print(f"Note: optional features degraded (the tool still works, just with weaker "
          f"signals) — not installed: {items}. To enable: "
          f"pip3 install --user --break-system-packages {pkgs}", file=sys.stderr)

# Special staging folders — never cleaned up, never re-scanned as fresh content
PARA_ROOTS = {"_Inbox", "_To Delete", "_Duplicates", "_Merged-Originals", "Archive"}

PEEK_CHARS = 300   # max chars to extract for content peek — ultimate fallback default;
                   # see _effective_peek_chars() for the config-aware value used at runtime.

# Classification fan-out batch size: cmd_propose partitions the to-classify
# residual into batches of this size, one classification sub-agent per batch.
# Ultimate fallback default — see _effective_batch_size() for the config-aware value.
BATCH = 25

# Inbox arbiter sweep trigger — soft guideline for when to reclaim _Inbox/ (see SKILL.md
# "Inbox arbiter sweep"). Ultimate fallback default — see _effective_inbox_arbiter_trigger().
INBOX_ARBITER_TRIGGER = 100

# Cloud-download polling. The scan used to do a single fixed 0.5s check after
# triggering a download and skip the file if it hadn't materialised yet — so any
# file slower than one tick was deferred to a future scan, which is the main
# cause of slow multi-pass cycles. Now scan polls up to a timeout so the file
# downloads within the same pass. Tunable via env (DRIVE_ORG_DL_TIMEOUT seconds) or,
# persistently per-drive, via config.json's "download_poll_timeout" — see
# _effective_download_poll_timeout() for the resolution order (env > config > default).
# NOT a module-level constant: it used to be computed once at import time (before
# _EFFECTIVE_ROOT is even known), which made a per-drive config value unreachable.
DOWNLOAD_POLL_INTERVAL = 0.5
_DOWNLOAD_POLL_TIMEOUT_DEFAULT = 30.0


def _effective_batch_size(root: "Path | None" = None) -> int:
    """Effective classification fan-out batch size: config.json's `classify_batch_size`
    when it validates, else BATCH (25). Defensive: a non-int or <1 value falls back to
    the safe default rather than corrupting the fan-out partitioning."""
    cfg = _read_user_config(root)
    raw = cfg.get("classify_batch_size")
    return raw if isinstance(raw, int) and not isinstance(raw, bool) and raw >= 1 else BATCH


def _effective_peek_chars(root: "Path | None" = None) -> int:
    """Effective content-peek character cap: config.json's `content_peek_chars` when it
    validates, else PEEK_CHARS (300). Defensive: a non-int or <1 value falls back to the
    safe default."""
    cfg = _read_user_config(root)
    raw = cfg.get("content_peek_chars")
    return raw if isinstance(raw, int) and not isinstance(raw, bool) and raw >= 1 else PEEK_CHARS


_PERIOD_BUFFER_DAYS_DEFAULT = 30  # mirrors date_range._expand_date_range's own default param


def _effective_period_buffer_days(root: "Path | None" = None) -> int:
    """Effective date_range buffer-days padding: config.json's `period_buffer_days` when
    it validates, else 30. Defensive: a non-int or <1 value falls back to the safe
    default. `_expand_date_range` keeps its own `buffer_days=30` parameter default too,
    so it stays safe if ever called without an explicit value."""
    cfg = _read_user_config(root)
    raw = cfg.get("period_buffer_days")
    return raw if isinstance(raw, int) and not isinstance(raw, bool) and raw >= 1 else _PERIOD_BUFFER_DAYS_DEFAULT


def _effective_inbox_arbiter_trigger(root: "Path | None" = None) -> int:
    """Effective inbox-arbiter-sweep trigger count: config.json's `inbox_arbiter_trigger`
    when it validates, else INBOX_ARBITER_TRIGGER (100). Defensive: a non-int or <1 value
    falls back to the safe default. Purely advisory — exposed to the orchestrator via
    `inbox-list`'s `arbiter_trigger` field; the backend never gates on it itself."""
    cfg = _read_user_config(root)
    raw = cfg.get("inbox_arbiter_trigger")
    return raw if isinstance(raw, int) and not isinstance(raw, bool) and raw >= 1 else INBOX_ARBITER_TRIGGER


def _effective_download_poll_timeout(root: "Path | None" = None) -> float:
    """Effective cloud-download poll timeout in seconds. Precedence: the
    DRIVE_ORG_DL_TIMEOUT env var (explicit per-run operator escape hatch) when set,
    else config.json's `download_poll_timeout` when it validates, else the 30s default.
    Called at point of use (not cached at import time) so a per-drive config value is
    reachable once _EFFECTIVE_ROOT is resolved. Defensive: a non-numeric or <=0 config
    value falls back to the safe default."""
    env = os.environ.get("DRIVE_ORG_DL_TIMEOUT")
    if env:
        try:
            return float(env)
        except ValueError:
            print(f"WARNING: DRIVE_ORG_DL_TIMEOUT={env!r} is not a number; ignoring it.",
                  file=sys.stderr)
    cfg = _read_user_config(root)
    raw = cfg.get("download_poll_timeout")
    if isinstance(raw, (int, float)) and not isinstance(raw, bool) and raw > 0:
        return float(raw)
    return _DOWNLOAD_POLL_TIMEOUT_DEFAULT


# Scan caps — per-batch ceiling on how much `scan`/`download-batch`/`propose`/`bootstrap`
# pull in one pass. Ultimate fallback defaults — see _effective_scan_file_limit() /
# _effective_scan_gb_limit() for the config-aware values. Mirrors today's argparse
# defaults exactly (250 files / 20.0 GB) so an unset config reproduces current behavior.
_SCAN_FILE_LIMIT_DEFAULT = 250
_SCAN_GB_LIMIT_DEFAULT = 20.0


def _effective_scan_file_limit(root: "Path | None" = None) -> int:
    """Effective per-batch file-count cap: config.json's `scan_file_limit` when it
    validates, else 250. Defensive: a non-int or <=0 value falls back to the safe
    default. Precedence at the call site is CLI flag > this config value > 250 — an
    explicit --limit always wins; this is only consulted when the flag is absent."""
    cfg = _read_user_config(root)
    raw = cfg.get("scan_file_limit")
    return raw if isinstance(raw, int) and not isinstance(raw, bool) and raw > 0 else _SCAN_FILE_LIMIT_DEFAULT


def _effective_scan_gb_limit(root: "Path | None" = None) -> float:
    """Effective per-batch cumulative-size cap in GB: config.json's `scan_gb_limit` when
    it validates, else 20.0. Defensive: a non-numeric or <=0 value falls back to the safe
    default. Precedence at the call site is CLI flag > this config value > 20.0."""
    cfg = _read_user_config(root)
    raw = cfg.get("scan_gb_limit")
    if isinstance(raw, (int, float)) and not isinstance(raw, bool) and raw > 0:
        return float(raw)
    return _SCAN_GB_LIMIT_DEFAULT


_VIEWER_PAGE_SIZE_DEFAULT = 25  # mirrors the hardcoded PAGE_SIZE/PAGE literals in
                                # viewer_propose.py / rules_viewer.py's generated HTML


def _effective_viewer_page_size(root: "Path | None" = None) -> int:
    """Effective rows-per-page for the proposal-review and rules viewers: config.json's
    `viewer_page_size` when it validates, else 25. Defensive: a non-int or <1 value falls
    back to the safe default. Does NOT affect rules_viewer.py's entity CAP (250, out of
    scope — that stays hardcoded)."""
    cfg = _read_user_config(root)
    raw = cfg.get("viewer_page_size")
    return raw if isinstance(raw, int) and not isinstance(raw, bool) and raw >= 1 else _VIEWER_PAGE_SIZE_DEFAULT


# date_range clamp bounds — a file date outside [floor, ceiling] is treated as
# unreliable metadata (pre-digital noise or a clock error) and ignored rather than
# widening a project's date_range. Ultimate fallback defaults — see
# _effective_date_floor() / _effective_date_ceiling_days() for the config-aware values.
# `date_ceiling_days` is a RELATIVE day-offset from "now" (not an absolute date) so the
# ceiling always tracks the current date, exactly like today's `datetime.now() + timedelta(days=365)`.
_DATE_FLOOR_DEFAULT = datetime(1990, 1, 1)
_DATE_CEILING_DAYS_DEFAULT = 365


def _effective_date_floor(root: "Path | None" = None) -> "datetime":
    """Effective lower bound for the date_range clamp: config.json's `date_floor`
    (an ISO date string, e.g. "1990-01-01") when it parses, else datetime(1990, 1, 1).
    Defensive: a missing, non-string, or unparseable value falls back to the safe
    default rather than corrupting the clamp."""
    cfg = _read_user_config(root)
    raw = cfg.get("date_floor")
    if isinstance(raw, str) and raw.strip():
        try:
            return datetime.fromisoformat(raw.strip()[:10])
        except (ValueError, TypeError):
            pass
    return _DATE_FLOOR_DEFAULT


def _effective_date_ceiling_days(root: "Path | None" = None) -> int:
    """Effective upper-bound offset (days from now) for the date_range clamp:
    config.json's `date_ceiling_days` when it validates, else 365. Defensive: a
    non-int or <1 value falls back to the safe default. Kept as a day-offset (not an
    absolute date) so the caller can compute `datetime.now() + timedelta(days=...)`
    and the ceiling always tracks "now"."""
    cfg = _read_user_config(root)
    raw = cfg.get("date_ceiling_days")
    return raw if isinstance(raw, int) and not isinstance(raw, bool) and raw >= 1 else _DATE_CEILING_DAYS_DEFAULT


# ---------------------------------------------------------------------------
# Shared safety helpers (Phase-0 baseline review: BL-A1 atomic writes, BL-A2 path containment)
# ---------------------------------------------------------------------------
def _atomic_write(path: "Path", text: str, encoding: str = "utf-8") -> None:
    """Write `text` to `path` atomically: write a temp file in the same directory
    then os.replace() it into place. A crash or full disk can never leave a
    truncated config / .tidy-rules.json / output file (BL-A1). Always UTF-8 (BL-A5)."""
    path = Path(path)
    tmp = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    try:
        tmp.write_text(text, encoding=encoding)
        os.replace(str(tmp), str(path))
    finally:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass


def _safe_dest(root: "Path", sub: str) -> "Path | None":
    """Resolve <root>/<sub> and return it ONLY if it stays inside `root`.

    Rejects absolute subpaths, '..' escapes, and symlink components that resolve
    outside root (BL-A2). Returns None when the destination would fall outside
    root — callers MUST treat None as 'reject this move/write', never fall back to
    an unchecked join. The returned path is the *resolved* path; use it for the
    actual filesystem operation so validation and write target are identical."""
    if sub is None:
        return None
    s = str(sub).strip()
    if not s:
        return None
    p = Path(s)
    if p.is_absolute():
        return None
    root_r = Path(root).resolve()
    cand = (root_r / p).resolve()
    try:
        cand.relative_to(root_r)
    except ValueError:
        return None
    return cand


# ---------------------------------------------------------------------------
# Config (saved active root)
# ---------------------------------------------------------------------------

def _read_config_root() -> "Path | None":
    # File-absent is fine (no saved root yet) -> return None silently.
    if not CONFIG_PATH.exists():
        return None
    # File present-but-corrupt/unreadable is a data-safety hazard: a silent fall
    # back to the default root could organize the WRONG drive. Warn loudly.
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        root = data.get("root")
        if root:
            return Path(root).expanduser().resolve()
    except Exception as e:
        print(f"WARNING: saved config root at {CONFIG_PATH} is corrupt/unreadable "
              f"({e}); ignoring it. Pass --root explicitly to be safe.", file=sys.stderr)
    return None


def _save_config_root(root: Path):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(CONFIG_PATH, json.dumps({"root": str(root)}, ensure_ascii=False, indent=2))


def _finalize_runtime_paths(root: "Path | None" = None):
    """Single source of truth for the per-drive registry/CSV paths. Resolves
    `_EFFECTIVE_ROOT` from (in order) the explicit `root`, the saved config, then
    DEFAULT_ONEDRIVE, and derives REGISTRY_DB / CSV_EXPORT_PATH from it. main() calls
    this once with the resolved `--root`; get_db() calls it lazily if main() has not run
    yet (e.g. the module imported and a helper invoked directly), so there is no window
    in which get_db() opens the bare module-level default while a configured drive is in
    effect — the formerly-silent wrong-DB path."""
    global REGISTRY_DB, CSV_EXPORT_PATH, _EFFECTIVE_ROOT, _PATHS_FINALIZED
    _EFFECTIVE_ROOT = root if root is not None else (_read_config_root() or DEFAULT_ONEDRIVE)
    REGISTRY_DB     = _EFFECTIVE_ROOT / ".organizer" / "registry.db"
    CSV_EXPORT_PATH = _EFFECTIVE_ROOT / ".organizer" / "registry.csv"
    _PATHS_FINALIZED = True


# ---------------------------------------------------------------------------
# Approved-folder detection (rules-based, no hardcoded prefixes)
# ---------------------------------------------------------------------------

@functools.lru_cache(maxsize=8)
def _root_rule_top_names(root_rules_str: str, _mtime_ns: int) -> frozenset:
    """Top-level folder names the root `.tidy-rules.json` routes into.

    Cached by (path, mtime) so a scan/download walk that calls `_has_rules` for every
    folder parses the root file once — not once per folder per pass. (The check used to
    be an O(1) name-prefix test; keeping it cheap matters in the hot walk.) `_mtime_ns`
    is only part of the cache key — it invalidates the entry when the file changes."""
    try:
        data = json.loads(Path(root_rules_str).read_text(encoding="utf-8"))
    except Exception as e:
        print(f"WARNING: could not parse {root_rules_str} ({e}); treating root as having "
              f"no rules.", file=sys.stderr)
        return frozenset()
    return frozenset(fn.split("/")[0]
                     for rule in data.get("rules", [])
                     if (fn := rule.get("folderName", "")))


def _has_rules(folder_path: Path, root: Path) -> bool:
    """
    Return True if this root-level folder is understood:
    - has its own .tidy-rules.json, OR
    - appears as a target in the root .tidy-rules.json
    """
    if (folder_path / ".tidy-rules.json").exists():
        return True
    root_rules = root / ".tidy-rules.json"
    try:
        mtime_ns = root_rules.stat().st_mtime_ns
    except OSError:
        return False  # no root rules file
    return folder_path.name in _root_rule_top_names(str(root_rules), mtime_ns)


def _is_external(folder_path: Path) -> bool:
    """
    Return True if this folder is marked external in its .tidy-rules.json.
    External folders are shared/owned by someone else — scan must never enter,
    propose must never target. The folder is treated as opaque.
    """
    rules_file = folder_path / ".tidy-rules.json"
    if not rules_file.exists():
        return False
    try:
        data = json.loads(rules_file.read_text(encoding="utf-8"))
    except Exception as e:
        # Fail CLOSED: if we can't read the rules we cannot prove the folder is
        # safe to enter, so treat it as external (opaque) rather than walking
        # into someone else's shared content.
        print(f"WARNING: could not parse {rules_file} ({e}); "
              f"treating '{folder_path.name}' as EXTERNAL (will not enter).", file=sys.stderr)
        return True
    if isinstance(data, dict) and data.get("external") is True:
        return True
    return False


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


def _read_user_config(root: "Path | None" = None) -> dict:
    """
    Per-user / per-drive settings that are NOT shipped with the skill — they live
    on the active drive at <root>/.organizer/config.json. Recognised keys:
      - memory_doc_path: absolute path to a supplementary context doc Claude reads
        when classification is ambiguous (replaces any hardcoded path)
      - profile: free-text note about the user's roles/context, fed to classification
    Returns {} when the file is absent or the root is unknown. Never raises.
    """
    root = root or _EFFECTIVE_ROOT
    # `not root` guard: _EFFECTIVE_ROOT can still be unset/empty very early in
    # startup (before main() resolves it) — with no drive there is nowhere to
    # read per-user config from, so return the empty default.
    if not root:
        return {}
    cfg = Path(root) / ".organizer" / "config.json"
    if not cfg.exists():
        return {}
    try:
        data = json.loads(cfg.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception as e:
        print(f"WARNING: could not parse user config {cfg} ({e}); "
              f"using defaults.", file=sys.stderr)
        return {}


# Settings the rules-viewer Settings panel exposes (Phase 3 gating feature). v1 covers the
# keys that are ALREADY config-backed; each later elevation item adds its control here, per
# the standing rule "no new config/property ships without its control wired into this panel".
def _settings_for_viewer(root: "Path | None" = None) -> dict:
    """Current effective values of the user-editable config keys, with defaults applied —
    the shape the Settings panel renders and POSTs back. Reads <root>/.organizer/config.json
    via _read_user_config (never raises)."""
    cfg = _read_user_config(root)
    caps = cfg.get("model_capabilities")
    if isinstance(caps, dict):
        peek = bool(caps.get("peek", True))
        vision = bool(caps.get("vision", cfg.get("vision", True)))
    else:
        peek = True
        vision = bool(cfg.get("vision", True))  # legacy top-level `vision`
    return {
        "peek": peek,
        "vision": vision,
        "auto_approve": bool(cfg.get("auto_approve", False)),
        "skip_types": list(cfg.get("skip_types", []) or []),
        "skip_over_mb": cfg.get("skip_over_mb"),  # number or null
        "variant_tokens": list(cfg.get("variant_tokens", []) or []),
        # Phase-3 Tier-2 dials — each reads through its _effective_*() helper so the
        # panel always shows the value the backend would actually use (defaults applied,
        # malformed overrides ignored), never the raw possibly-invalid config.json value.
        "classify_batch_size": _effective_batch_size(root),
        "period_buffer_days": _effective_period_buffer_days(root),
        "content_peek_chars": _effective_peek_chars(root),
        "download_poll_timeout": _effective_download_poll_timeout(root),
        "inbox_arbiter_trigger": _effective_inbox_arbiter_trigger(root),
        "scan_file_limit": _effective_scan_file_limit(root),
        "scan_gb_limit": _effective_scan_gb_limit(root),
        "date_floor": _effective_date_floor(root).date().isoformat(),
        "date_ceiling_days": _effective_date_ceiling_days(root),
        "viewer_page_size": _effective_viewer_page_size(root),
    }


def _write_user_config(updates: dict, root: "Path | None" = None) -> dict:
    """Merge `updates` (the Settings-panel shape from _settings_for_viewer) into
    <root>/.organizer/config.json, atomically, preserving every other key already in the
    file (e.g. `areas`, `root`, `profile`). Normalises into the canonical config shape the
    rest of the backend reads: capabilities under `model_capabilities`, the rest top-level.
    Returns the new effective settings. Raises only on an unwritable config dir."""
    root = root or _EFFECTIVE_ROOT
    if not root:
        raise RuntimeError("no active drive root — run `status` to set one before saving settings")
    cfg_path = Path(root) / ".organizer" / "config.json"
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cur = _read_user_config(root)  # {} if absent/unparseable
    caps = dict(cur.get("model_capabilities") or {})
    if "peek" in updates:
        caps["peek"] = bool(updates["peek"])
    if "vision" in updates:
        caps["vision"] = bool(updates["vision"])
        cur.pop("vision", None)  # collapse the legacy top-level `vision` into model_capabilities
    if caps:
        cur["model_capabilities"] = caps
    if "auto_approve" in updates:
        cur["auto_approve"] = bool(updates["auto_approve"])
    if "skip_types" in updates:
        # accept a list or a comma string; normalise to a deduped sorted list of '.ext'
        raw = updates["skip_types"]
        if isinstance(raw, str):
            raw = [t for t in raw.split(",")]
        exts = sorted({(t.strip().lower() if t.strip().startswith(".") else "." + t.strip().lower())
                       for t in (raw or []) if t and t.strip()})
        cur["skip_types"] = exts
    if "skip_over_mb" in updates:
        v = updates["skip_over_mb"]
        if v in (None, "", 0, "0"):
            cur.pop("skip_over_mb", None)
        else:
            cur["skip_over_mb"] = float(v) if not float(v).is_integer() else int(float(v))
    if "variant_tokens" in updates:
        # accept a list or a comma string; normalise to a deduped sorted list of plain words
        raw = updates["variant_tokens"]
        if isinstance(raw, str):
            raw = [t for t in raw.split(",")]
        tokens = sorted({t.strip().lower() for t in (raw or []) if t and t.strip()})
        cur["variant_tokens"] = tokens
    # Phase-3 Tier-2 numeric dials. Each: blank/None/0/"0" clears the override (falls
    # back to the hardcoded default at read time); a non-blank value is stored ONLY if
    # it validates for that dial's type — an invalid typed value is dropped (never
    # written), same effect as leaving it unset, so config.json can never persist a
    # value that would corrupt behavior at read time.
    # bool is a subclass of int in Python (int(True) == 1, float(True) == 1.0), so every
    # numeric dial below must explicitly reject bool BEFORE the int()/float() cast — a
    # bare int(v) would silently accept a stray JSON true/false as a valid 1/0 and write
    # a nonsense value to config.json. This guard is required on every branch, not just
    # some of them, since the /config POST handler forwards raw parsed JSON unchanged.
    if "classify_batch_size" in updates:
        v = updates["classify_batch_size"]
        if v in (None, "", 0, "0"):
            cur.pop("classify_batch_size", None)
        else:
            try:
                if isinstance(v, bool):
                    raise TypeError
                iv = int(v)
                if iv >= 1:
                    cur["classify_batch_size"] = iv
                else:
                    cur.pop("classify_batch_size", None)
            except (TypeError, ValueError):
                cur.pop("classify_batch_size", None)
    if "period_buffer_days" in updates:
        v = updates["period_buffer_days"]
        if v in (None, "", 0, "0"):
            cur.pop("period_buffer_days", None)
        else:
            try:
                if isinstance(v, bool):
                    raise TypeError
                iv = int(v)
                if iv >= 1:
                    cur["period_buffer_days"] = iv
                else:
                    cur.pop("period_buffer_days", None)
            except (TypeError, ValueError):
                cur.pop("period_buffer_days", None)
    if "content_peek_chars" in updates:
        v = updates["content_peek_chars"]
        if v in (None, "", 0, "0"):
            cur.pop("content_peek_chars", None)
        else:
            try:
                if isinstance(v, bool):
                    raise TypeError
                iv = int(v)
                if iv >= 1:
                    cur["content_peek_chars"] = iv
                else:
                    cur.pop("content_peek_chars", None)
            except (TypeError, ValueError):
                cur.pop("content_peek_chars", None)
    if "download_poll_timeout" in updates:
        v = updates["download_poll_timeout"]
        if v in (None, "", 0, "0"):
            cur.pop("download_poll_timeout", None)
        else:
            try:
                if isinstance(v, bool):
                    raise TypeError
                fv = float(v)
                if fv > 0:
                    cur["download_poll_timeout"] = fv if not fv.is_integer() else int(fv)
                else:
                    cur.pop("download_poll_timeout", None)
            except (TypeError, ValueError):
                cur.pop("download_poll_timeout", None)
    if "inbox_arbiter_trigger" in updates:
        v = updates["inbox_arbiter_trigger"]
        if v in (None, "", 0, "0"):
            cur.pop("inbox_arbiter_trigger", None)
        else:
            try:
                if isinstance(v, bool):
                    raise TypeError
                iv = int(v)
                if iv >= 1:
                    cur["inbox_arbiter_trigger"] = iv
                else:
                    cur.pop("inbox_arbiter_trigger", None)
            except (TypeError, ValueError):
                cur.pop("inbox_arbiter_trigger", None)
    if "scan_file_limit" in updates:
        v = updates["scan_file_limit"]
        if v in (None, "", 0, "0"):
            cur.pop("scan_file_limit", None)
        else:
            try:
                if isinstance(v, bool):
                    raise TypeError
                iv = int(v)
                if iv >= 1:
                    cur["scan_file_limit"] = iv
                else:
                    cur.pop("scan_file_limit", None)
            except (TypeError, ValueError):
                cur.pop("scan_file_limit", None)
    if "scan_gb_limit" in updates:
        v = updates["scan_gb_limit"]
        if v in (None, "", 0, "0"):
            cur.pop("scan_gb_limit", None)
        else:
            try:
                if isinstance(v, bool):
                    raise TypeError
                fv = float(v)
                if fv > 0:
                    cur["scan_gb_limit"] = fv if not fv.is_integer() else int(fv)
                else:
                    cur.pop("scan_gb_limit", None)
            except (TypeError, ValueError):
                cur.pop("scan_gb_limit", None)
    if "date_floor" in updates:
        v = updates["date_floor"]
        if v in (None, "", 0, "0"):
            cur.pop("date_floor", None)
        else:
            try:
                if isinstance(v, bool) or not isinstance(v, str):
                    raise TypeError
                datetime.fromisoformat(v.strip()[:10])  # validate only; store the raw ISO string
                cur["date_floor"] = v.strip()[:10]
            except (TypeError, ValueError):
                cur.pop("date_floor", None)
    if "date_ceiling_days" in updates:
        v = updates["date_ceiling_days"]
        if v in (None, "", 0, "0"):
            cur.pop("date_ceiling_days", None)
        else:
            try:
                if isinstance(v, bool):
                    raise TypeError
                iv = int(v)
                if iv >= 1:
                    cur["date_ceiling_days"] = iv
                else:
                    cur.pop("date_ceiling_days", None)
            except (TypeError, ValueError):
                cur.pop("date_ceiling_days", None)
    if "viewer_page_size" in updates:
        v = updates["viewer_page_size"]
        if v in (None, "", 0, "0"):
            cur.pop("viewer_page_size", None)
        else:
            try:
                if isinstance(v, bool):
                    raise TypeError
                iv = int(v)
                if iv >= 1:
                    cur["viewer_page_size"] = iv
                else:
                    cur.pop("viewer_page_size", None)
            except (TypeError, ValueError):
                cur.pop("viewer_page_size", None)
    _atomic_write(cfg_path, json.dumps(cur, ensure_ascii=False, indent=2))
    return _settings_for_viewer(root)


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
    if _EFFECTIVE_ROOT:
        override_path = Path(_EFFECTIVE_ROOT) / ".organizer" / "templates.json"
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


_FITZ_LOCK = threading.Lock()


_XML_PEEK_CAP = 5 * 1024 * 1024  # 5 MB


_UF_DATALESS = 0x40000000  # macOS flag set by NSFileProvider on not-yet-downloaded files

# Windows reparse/offline attributes signalling a not-yet-materialised placeholder.
_WIN_RECALL_ON_DATA_ACCESS = 0x00400000  # FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS
_WIN_OFFLINE              = 0x00001000  # FILE_ATTRIBUTE_OFFLINE


CSV_EXPORT_PATH = Path.home() / ".claude" / "drive-organizer" / "registry.csv"  # overridden at startup

_COMMON_CATEGORY_WORDS = {
    "finance", "financials", "notes", "feedback", "receipts", "invoices", "bills",
    "statements", "tax", "admin", "docs", "documents", "references", "scripts",
    "schedules", "drafts", "exports", "imports", "backups", "output", "outputs",
    "misc", "miscellaneous", "templates", "assets", "correspondence", "contracts",
    "legal", "planning", "research", "reports", "logs", "data", "code", "config",
    "scans", "attachments", "deliverables", "expenses", "payments", "agreements",
}


_CLUSTER_ORDER = ["area", "project", "person", "category", "policy", "atomic", "unknown"]
_CLUSTER_LABEL = {
    "area": "Areas", "project": "Projects", "person": "People",
    "category": "Subfolders / Categories", "policy": "Policies", "atomic": "Atomic units",
    "unknown": "Unknown / triage",
}


def _reset_caches():
    """Clear the process-level templates cache so a live (keepalive) save re-reads
    config + templates and the refreshed view reflects area changes. Groupings are
    derived from _load_templates() on every call and have no independent cache to clear."""
    global _TEMPLATES_CACHE
    _TEMPLATES_CACHE = None


_ATOMIC_DIR_NAMES = {"node_modules", ".git", "venv", ".venv", "env", "__pycache__",
                     ".tox", "site-packages", "Pods", "vendor"}
_ATOMIC_SUFFIXES = (".app", ".framework", ".bundle", ".xcodeproj", ".photoslibrary",
                    ".imovielibrary", ".tvlibrary", ".aplibrary")
# Must remain a tuple (not a set): str.endswith() requires a tuple for multi-suffix matching.

