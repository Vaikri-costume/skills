"""drive_organizer.category_words — split from paths_config.py (pure structural move, no behavior change).

Functional-subfolder word set derived from the shipped
references/tidy-builtin-categories.json, plus a small hand-labelled supplementary set."""
from __future__ import annotations
import json
import os
import sys

from drive_organizer.paths_config import _skill_references_dir


# Supplementary category words with NO analog anywhere in tidy-builtin-categories.json's
# `category` field or `keywords` arrays (computed once by diffing the old hand-typed
# 41-word _COMMON_CATEGORY_WORDS against that file's derived word set — these 20 are the
# words that matched nothing, exact or naive-plural-stemmed). Preserved deliberately as
# genuine supplementary signal, not duplicated from the JSON, since the JSON has no
# analog to fall back on for them.
_CATEGORY_WORDS_SUPPLEMENTARY = {
    "admin", "attachments", "correspondence", "deliverables", "docs", "drafts",
    "expenses", "exports", "feedback", "financials", "imports", "legal", "misc",
    "miscellaneous", "notes", "output", "outputs", "planning", "scans", "templates",
}


_CATEGORY_WORDS_CACHE = None


def _reset_cache():
    """Clear this module's process-level cache. Called by paths_config._reset_caches()."""
    global _CATEGORY_WORDS_CACHE
    _CATEGORY_WORDS_CACHE = None


def _load_category_words() -> set:
    """Derive the functional-subfolder word set from the shipped
    references/tidy-builtin-categories.json: lowercase every entry's `category` field
    and every string in its `keywords` array, union them all — PLUS the naive plural
    ('+s') of each single-word entry, since tidy-builtin-categories.json's keywords
    skew singular ("bill", "invoice", "receipt") while real folder names skew plural
    ("Bills", "Invoices", "Receipts"); without the stem-expansion those folders would
    silently stop matching (a real regression vs the old hardcoded plural-heavy list).
    mtime-cached, same degrade posture as every other references/ loader — an empty
    set (+ stderr WARNING) if the file is missing/malformed, never a crash."""
    global _CATEGORY_WORDS_CACHE
    cat_path = _skill_references_dir() / "tidy-builtin-categories.json"
    try:
        mtime = os.path.getmtime(cat_path) if cat_path.exists() else 0
    except OSError:
        mtime = 0
    if _CATEGORY_WORDS_CACHE is not None and _CATEGORY_WORDS_CACHE[0] == mtime:
        return _CATEGORY_WORDS_CACHE[1]
    words = set()
    if cat_path.exists():
        try:
            data = json.loads(cat_path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                for entry in data:
                    if not isinstance(entry, dict):
                        continue
                    cat = entry.get("category")
                    if isinstance(cat, str) and cat.strip():
                        words.add(cat.strip().lower())
                    kws = entry.get("keywords")
                    if isinstance(kws, list):
                        words |= {kw.strip().lower() for kw in kws if isinstance(kw, str) and kw.strip()}
            else:
                print(f"WARNING: shipped categories {cat_path} is not a JSON list; "
                      f"category-word signal will be empty (+ supplementary words).", file=sys.stderr)
        except Exception as e:
            print(f"WARNING: could not parse shipped categories {cat_path} "
                  f"({e}); category-word signal will be empty (+ supplementary words).", file=sys.stderr)
    # Naive plural stem: a single alphabetic word not already ending in 's' also gets
    # its '+s' form added (bill -> bills, invoice -> invoices). Multi-word phrases
    # ("job application", "birth certificate") are left alone — pluralizing a phrase
    # naively is unreliable and folder names for those are rarely bare plurals anyway.
    for w in list(words):
        if w.isalpha() and not w.endswith("s"):
            words.add(w + "s")
    _CATEGORY_WORDS_CACHE = (mtime, words)
    return words


def _effective_common_category_words() -> set:
    """Effective functional-subfolder word set consumed by entities_rules._infer_entity_type:
    the JSON-derived words (_load_category_words) unioned with the small hand-labelled
    _CATEGORY_WORDS_SUPPLEMENTARY constant. Replaces the old hand-typed 41-word
    _COMMON_CATEGORY_WORDS literal — computed once from shipped data instead, re-derived
    whenever the mtime-cache invalidates (never stale after a references/ file edit or a
    _reset_caches() call)."""
    return _load_category_words() | _CATEGORY_WORDS_SUPPLEMENTARY
