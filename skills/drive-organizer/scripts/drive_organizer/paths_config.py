"""drive_organizer.paths_config — split from the original organizer.py (pure structural move, no behavior change)."""
from __future__ import annotations
import copy
import functools
import json
import os
import sys
import threading
from datetime import datetime
from pathlib import Path

from . import config_dials


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

# Config-dial subsystem (constants, _effective_*() readers, write-side validation,
# Settings-panel row generation) now lives in config_dials.py, driven by its DIALS
# descriptor table — see that module's docstring. The names below are re-exported
# unchanged so every existing `from .paths_config import _effective_batch_size` (etc.)
# call site across the package keeps working without modification.
#
# `download_poll_timeout` keeps its DRIVE_ORG_DL_TIMEOUT env-var precedence layer
# here (env > config > default) since that's a paths_config-level concern (env
# resolution), not a generic dial-table concern.
PEEK_CHARS = config_dials.PEEK_CHARS
BATCH = config_dials.BATCH
INBOX_ARBITER_TRIGGER = config_dials.INBOX_ARBITER_TRIGGER
DOWNLOAD_POLL_INTERVAL = config_dials.DOWNLOAD_POLL_INTERVAL
_DOWNLOAD_POLL_TIMEOUT_DEFAULT = config_dials._DOWNLOAD_POLL_TIMEOUT_DEFAULT

_dial_readers = config_dials.make_effective_readers(lambda root: _read_user_config(root))

_effective_batch_size = _dial_readers["batch_size"]
_effective_peek_chars = _dial_readers["peek_chars"]
_effective_period_buffer_days = _dial_readers["period_buffer_days"]
_effective_inbox_arbiter_trigger = _dial_readers["inbox_arbiter_trigger"]
_effective_scan_file_limit = _dial_readers["scan_file_limit"]
_effective_scan_gb_limit = _dial_readers["scan_gb_limit"]
_effective_date_floor = _dial_readers["date_floor"]
_effective_date_ceiling_days = _dial_readers["date_ceiling_days"]
_effective_viewer_page_size = _dial_readers["viewer_page_size"]


def _effective_download_poll_timeout(root: "Path | None" = None) -> float:
    """Effective cloud-download poll timeout in seconds. Precedence: the
    DRIVE_ORG_DL_TIMEOUT env var (explicit per-run operator escape hatch) when set,
    else config.json's `download_poll_timeout` when it validates, else the 30s default
    (config_dials.DIALS's "download_poll_timeout" row). Called at point of use (not
    cached at import time) so a per-drive config value is reachable once
    _EFFECTIVE_ROOT is resolved."""
    env = os.environ.get("DRIVE_ORG_DL_TIMEOUT")
    if env:
        try:
            return float(env)
        except ValueError:
            print(f"WARNING: DRIVE_ORG_DL_TIMEOUT={env!r} is not a number; ignoring it.",
                  file=sys.stderr)
    return _dial_readers["download_poll_timeout"](root)


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


def _read_user_config(root: "Path | None" = None) -> dict:
    """
    Per-user / per-drive settings that are NOT shipped with the skill — they live
    on the active drive at <root>/.organizer/config.json. Recognised keys:
      - memory_doc_path: absolute path to a supplementary context doc Claude reads
        when classification is ambiguous (replaces any hardcoded path)
      - profile: free-text note about the user's roles/context, fed to classification
    Returns {} when the file is absent or the root is unknown. Never raises.

    NOT cached (deliberately — no _USER_CONFIG_CACHE exists): every call re-reads
    config.json fresh from disk, so an edit made by any process (rules-viewer's /save,
    process-return, a manual hand-edit) is visible to the very next call in every process,
    including a long-running rules-viewer server. This is distinct from the SHIPPED
    references/ loaders (_load_templates, _load_atomic_signatures, _load_category_words),
    which ARE mtime-cached — but those self-invalidate automatically the moment the
    underlying shipped file's mtime changes (every call re-checks current mtime before
    deciding whether to serve cached data), so no staleness window exists there either.
    _reset_caches() exists only as a defensive belt-and-suspenders call for the rare case
    where a shipped file changes in the same tick as a config.json edit — not because
    either cache is otherwise capable of serving stale data.
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
    result = {
        "peek": peek,
        "vision": vision,
        "auto_approve": bool(cfg.get("auto_approve", False)),
        "skip_types": list(cfg.get("skip_types", []) or []),
        "skip_over_mb": cfg.get("skip_over_mb"),  # number or null
        "variant_tokens": list(cfg.get("variant_tokens", []) or []),
        # dir_names/suffixes ONLY (marker_files/marker_pairs are shipped-file-only —
        # see _effective_atomic_signatures). Raw config.json value, not the merged set —
        # the panel edits the USER'S extra list, not the shipped+extra union.
        "atomic_signatures_extra": (cfg.get("atomic_signatures_extra")
                                     if isinstance(cfg.get("atomic_signatures_extra"), dict) else {}),
    }
    # Phase-3 Tier-2 dials — generated from config_dials.DIALS in one pass (each reads
    # through its _effective_*() wrapper so the panel always shows the value the backend
    # would actually use — defaults applied, malformed overrides ignored — never the raw
    # possibly-invalid config.json value). download_poll_timeout uses the paths_config
    # wrapper (env-var precedence) rather than the raw dial reader.
    dial_readers = dict(_dial_readers)
    dial_readers["download_poll_timeout"] = _effective_download_poll_timeout
    result.update(config_dials.dial_settings_rows(dial_readers, root))
    return result


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
    # Phase-3 Tier-2 numeric/date dials. Each: blank/None/0/"0" clears the override
    # (falls back to the hardcoded default at read time); a non-blank value is stored
    # ONLY if it validates for that dial's type — an invalid typed value is dropped
    # (never written), same effect as leaving it unset, so config.json can never
    # persist a value that would corrupt behavior at read time. Generated in one pass
    # from config_dials.DIALS instead of one hand-copied if-block per dial — every
    # dial's caster (config_dials._cast_pos_int / _cast_pos_float / _cast_iso_date_str)
    # explicitly rejects bool BEFORE the int()/float() cast (bool is an int subclass in
    # Python, so a bare int(v) would silently accept a stray JSON true/false as 1/0).
    config_dials.apply_all_dial_updates(updates, cur)
    if "atomic_signatures_extra" in updates:
        v = updates["atomic_signatures_extra"]
        # dir_names/suffixes ONLY — marker_files/marker_pairs are deliberately NOT
        # accepted here (executable-probe logic stays shipped-file-only; see the
        # _effective_atomic_signatures docstring). Defensive posture matches every
        # other dial: a stray JSON boolean or malformed shape is dropped, never crashes,
        # and never silently corrupts the merged atomic-signature set.
        if v in (None, "", {}) or isinstance(v, bool):
            cur.pop("atomic_signatures_extra", None)
        elif isinstance(v, dict):
            dir_names = v.get("dir_names")
            suffixes = v.get("suffixes")
            clean_dirs = (sorted({x.strip() for x in dir_names if isinstance(x, str) and x.strip()})
                          if isinstance(dir_names, list) else [])
            clean_suffixes = (sorted({x.strip() for x in suffixes if isinstance(x, str) and x.strip()})
                              if isinstance(suffixes, list) else [])
            if clean_dirs or clean_suffixes:
                cur["atomic_signatures_extra"] = {"dir_names": clean_dirs, "suffixes": clean_suffixes}
            else:
                cur.pop("atomic_signatures_extra", None)
        else:
            cur.pop("atomic_signatures_extra", None)
    _atomic_write(cfg_path, json.dumps(cur, ensure_ascii=False, indent=2))
    return _settings_for_viewer(root)


def _skill_references_dir() -> Path:
    """Resolve the skill's references/ directory: DRIVE_ORG_SKILL_DIR env override,
    else the canonical Claude Code skills install path. Shared by every references/
    loader (_load_templates, _load_atomic_signatures, _load_category_words) so the
    resolution rule lives in exactly one place."""
    skill_dir = os.environ.get("DRIVE_ORG_SKILL_DIR")
    base_dir = Path(skill_dir) if skill_dir else (Path.home() / ".claude" / "skills" / "drive-organizer")
    return base_dir / "references"


_FITZ_LOCK = threading.Lock()


_XML_PEEK_CAP = 5 * 1024 * 1024  # 5 MB


CSV_EXPORT_PATH = Path.home() / ".claude" / "drive-organizer" / "registry.csv"  # overridden at startup


_CLUSTER_ORDER = ["area", "project", "person", "category", "policy", "atomic", "unknown"]
_CLUSTER_LABEL = {
    "area": "Areas", "project": "Projects", "person": "People",
    "category": "Subfolders / Categories", "policy": "Policies", "atomic": "Atomic units",
    "unknown": "Unknown / triage",
}


def _reset_caches():
    """Clear the process-level templates + atomic-signatures + category-words caches so a
    live (keepalive) save re-reads config + shipped references and the refreshed view
    reflects area/config changes. Groupings are derived from _load_templates() on every
    call and have no independent cache to clear. atomic-signatures is included because
    _effective_atomic_signatures() reads config.json's atomic_signatures_extra on every
    call (never cached) but the SHIPPED half (_load_atomic_signatures) is mtime-cached —
    a keepalive-refresh after editing config.json's extra list still needs the shipped
    half fresh in the (rare) case the shipped file also changed underfoot.

    Each cache now lives in its own module (templates.py, atomic_signatures.py,
    category_words.py); this delegates to each module's own _reset_cache() helper since
    module-level globals must be cleared through the module namespace, not a rebound
    local import."""
    from drive_organizer import atomic_signatures, category_words, templates
    templates._reset_cache()
    atomic_signatures._reset_cache()
    category_words._reset_cache()

