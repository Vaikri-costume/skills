"""drive_organizer.paths_config — split from the original organizer.py (pure structural move, no behavior change)."""
from __future__ import annotations
import functools
import json
import os
import sys
import threading
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

PEEK_CHARS = 300   # max chars to extract for content peek

# Classification fan-out batch size: cmd_propose partitions the to-classify
# residual into batches of this size, one classification sub-agent per batch.
BATCH = 25

# Cloud-download polling. The scan used to do a single fixed 0.5s check after
# triggering a download and skip the file if it hadn't materialised yet — so any
# file slower than one tick was deferred to a future scan, which is the main
# cause of slow multi-pass cycles. Now scan polls up to a timeout so the file
# downloads within the same pass. Tunable via env (DRIVE_ORG_DL_TIMEOUT seconds).
DOWNLOAD_POLL_INTERVAL = 0.5
DOWNLOAD_POLL_TIMEOUT  = float(os.environ.get("DRIVE_ORG_DL_TIMEOUT", "30"))


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

