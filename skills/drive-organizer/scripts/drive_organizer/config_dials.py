"""drive_organizer.config_dials — the config-dial subsystem split out of paths_config.py.

Every simple scalar "Phase-3 Tier-2" dial (an int/float/date config.json key with a
hardcoded fallback default) is described ONCE in the DIALS table below. The reader
(`_effective_dial` / the per-dial `_effective_*` wrappers), the write-side validator
(`_apply_dial_update`, driven from `_write_user_config`), and the Settings-panel row
generator (`_dial_settings_rows`) all iterate this table instead of hand-writing the
same reject-bool / cast-type / pop-on-invalid block per dial. Adding a new dial means
adding one row here — not copy-pasting a ~15-line validation block.

Deliberately OUT of this table (stay in paths_config.py, unchanged): `_read_user_config`
itself, the non-scalar dials `_effective_atomic_signatures` (dict-merge shape) and
`_effective_common_category_words` (derived-from-shipped-JSON, no config.json key of its
own), and the non-dial Settings-panel keys (peek/vision/auto_approve/skip_types/
skip_over_mb/variant_tokens/atomic_signatures_extra) which have bespoke shapes that don't
fit the scalar-dial pattern.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Optional


# ---------------------------------------------------------------------------
# Ultimate fallback defaults (module-level constants, same values/semantics as
# the originals in paths_config.py — moved here since they exist only to feed
# their dial's default).
# ---------------------------------------------------------------------------
PEEK_CHARS = 300
BATCH = 25
INBOX_ARBITER_TRIGGER = 100
DOWNLOAD_POLL_INTERVAL = 0.5
_DOWNLOAD_POLL_TIMEOUT_DEFAULT = 30.0
_PERIOD_BUFFER_DAYS_DEFAULT = 30
_SCAN_FILE_LIMIT_DEFAULT = 250
_SCAN_GB_LIMIT_DEFAULT = 20.0
_VIEWER_PAGE_SIZE_DEFAULT = 25
_DATE_FLOOR_DEFAULT = datetime(1990, 1, 1)
_DATE_CEILING_DAYS_DEFAULT = 365


# ---------------------------------------------------------------------------
# Casters — each takes the raw config.json value and either returns the valid
# typed value or raises (TypeError/ValueError), same contract as the original
# hand-written `try/except (TypeError, ValueError)` blocks.
# ---------------------------------------------------------------------------
def _cast_pos_int(v: Any) -> int:
    """int, >= 1. Rejects bool (bool is an int subclass in Python)."""
    if isinstance(v, bool):
        raise TypeError
    iv = int(v)
    if iv < 1:
        raise ValueError
    return iv


def _cast_pos_float(v: Any) -> float:
    """float, > 0. Rejects bool. Returned as int when it has no fractional part,
    matching the original dials' `fv if not fv.is_integer() else int(fv)` storage."""
    if isinstance(v, bool):
        raise TypeError
    fv = float(v)
    if fv <= 0:
        raise ValueError
    return fv if not fv.is_integer() else int(fv)


def _cast_iso_date_str(v: Any) -> str:
    """A string parseable as an ISO date (only the first 10 chars are used/stored)."""
    if isinstance(v, bool) or not isinstance(v, str):
        raise TypeError
    s = v.strip()[:10]
    datetime.fromisoformat(s)  # validate only
    return s


# ---------------------------------------------------------------------------
# Readers — how to turn a validated raw value into the effective runtime value.
# Most dials are identity (the stored value IS the effective value); date_floor
# is the one exception (stored as an ISO string, read back as a datetime).
# ---------------------------------------------------------------------------
def _read_identity(raw: Any) -> Any:
    return raw


def _read_date_floor(raw: str) -> datetime:
    return datetime.fromisoformat(raw)


@dataclass(frozen=True)
class Dial:
    """One config-dial descriptor.

    name: attribute-ish name, used to build the `_effective_<name>` wrapper name
          and the Settings-panel dict key (both are `config_key` normally, but kept
          separate since e.g. the panel key isn't always identical to a Python
          identifier — here they happen to match for every dial).
    config_key: the key read from / written to config.json.
    default: the ultimate fallback value.
    cast: raw JSON value -> validated typed value, or raises TypeError/ValueError.
    read: validated typed value -> effective runtime value (identity for all but
          date_floor).
    to_panel: effective runtime value -> JSON-safe value for the Settings panel
              (identity for all but date_floor, which the panel wants as a plain
              ISO date string).
    """
    name: str
    config_key: str
    default: Any
    cast: Callable[[Any], Any] = _cast_pos_int
    read: Callable[[Any], Any] = _read_identity
    to_panel: Callable[[Any], Any] = _read_identity


DIALS = [
    Dial("batch_size", "classify_batch_size", BATCH),
    Dial("peek_chars", "content_peek_chars", PEEK_CHARS),
    Dial("period_buffer_days", "period_buffer_days", _PERIOD_BUFFER_DAYS_DEFAULT),
    Dial("inbox_arbiter_trigger", "inbox_arbiter_trigger", INBOX_ARBITER_TRIGGER),
    Dial("download_poll_timeout", "download_poll_timeout", _DOWNLOAD_POLL_TIMEOUT_DEFAULT,
         cast=_cast_pos_float),
    Dial("scan_file_limit", "scan_file_limit", _SCAN_FILE_LIMIT_DEFAULT),
    Dial("scan_gb_limit", "scan_gb_limit", _SCAN_GB_LIMIT_DEFAULT, cast=_cast_pos_float),
    Dial("date_floor", "date_floor", _DATE_FLOOR_DEFAULT, cast=_cast_iso_date_str,
         read=_read_date_floor, to_panel=lambda dt: dt.date().isoformat()),
    Dial("date_ceiling_days", "date_ceiling_days", _DATE_CEILING_DAYS_DEFAULT),
    Dial("viewer_page_size", "viewer_page_size", _VIEWER_PAGE_SIZE_DEFAULT),
]

_DIALS_BY_NAME = {d.name: d for d in DIALS}


# `download_poll_timeout` has its own extra precedence layer (env var wins over
# config) applied by its `_effective_*` wrapper below — everything else is the
# plain "config.json value if it validates, else default" pattern.
def _effective_dial(dial: Dial, read_user_config: Callable[[Any], dict], root=None) -> Any:
    """Generic reader: config.json[dial.config_key] if present and it casts/validates,
    else dial.default (already in "read" form for the caller)."""
    cfg = read_user_config(root)
    raw = cfg.get(dial.config_key)
    if raw is not None:
        try:
            validated = dial.cast(raw)
            return dial.read(validated)
        except (TypeError, ValueError):
            pass
    default = dial.default
    # date_floor's default is already a datetime (its "read" form); every other
    # dial's default is already in read form too (identity), so no extra read() call.
    return default


def make_effective_readers(read_user_config: Callable[[Any], dict]) -> dict:
    """Build the `_effective_<name>(root=None)` wrapper functions, one per dial, bound
    to `read_user_config` (paths_config._read_user_config). paths_config.py assigns
    each of these to its original module-level name so every existing call site
    (`from .paths_config import _effective_batch_size`, etc.) keeps working unchanged."""
    wrappers = {}
    for dial in DIALS:
        def _wrapper(root=None, _dial=dial):
            return _effective_dial(_dial, read_user_config, root)
        _wrapper.__name__ = f"_effective_{dial.name}"
        wrappers[dial.name] = _wrapper
    return wrappers


# ---------------------------------------------------------------------------
# Write-side: one generic validation/apply step per dial, replacing the ~12x
# copy-pasted "blank clears / cast-and-validate / drop-if-invalid" block.
# ---------------------------------------------------------------------------
def apply_dial_update(dial: Dial, updates: dict, cur: dict) -> None:
    """Mutate `cur` (the in-progress config.json dict) per `updates[dial.config_key]`,
    if that key is present in `updates`. Semantics identical to the original
    hand-written per-dial blocks:
      - value in (None, "", 0, "0") -> pop the key (falls back to default at read time)
      - value casts/validates -> store the cast value
      - value present but invalid -> pop the key (never store a corrupting value)
    """
    key = dial.config_key
    if key not in updates:
        return
    v = updates[key]
    if v in (None, "", 0, "0"):
        cur.pop(key, None)
        return
    try:
        cur[key] = dial.cast(v)
    except (TypeError, ValueError):
        cur.pop(key, None)


def apply_all_dial_updates(updates: dict, cur: dict) -> None:
    """Apply every dial's write-side validation in one pass — the single call site
    `_write_user_config` uses instead of ~12 hand-copied if-blocks."""
    for dial in DIALS:
        apply_dial_update(dial, updates, cur)


# ---------------------------------------------------------------------------
# Settings-panel rows: the dial slice of `_settings_for_viewer`'s returned dict.
# ---------------------------------------------------------------------------
def dial_settings_rows(effective_readers: dict, root=None) -> dict:
    """{config_key: panel-safe effective value} for every dial — the Phase-3 Tier-2
    slice of _settings_for_viewer's returned dict. `effective_readers` is the dict
    built by make_effective_readers (or equivalently, paths_config's per-dial
    `_effective_*` attributes), keyed by dial.name."""
    rows = {}
    for dial in DIALS:
        value = effective_readers[dial.name](root)
        rows[dial.config_key] = dial.to_panel(value)
    return rows
