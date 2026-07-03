"""drive_organizer.duplicates_variants — split from the original organizer.py (pure structural move, no behavior change)."""
from __future__ import annotations
import hashlib
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

from drive_organizer.content_peek import (
    get_db,
)
from drive_organizer.csv_export import (
    export_csv,
)
from drive_organizer import paths_config


def _pick_keeper(files: list) -> dict:
    """Choose the 'keeper' from a duplicate group — the best-placed copy to keep
    in place. `files` is a list of dicts with at least 'id', 'path', 'status'.
    Prefer organized status, then a path outside _Inbox/Archive, then the
    most-specific (deepest) path."""
    def score(r):
        p = r.get("path") or ""
        organized = 1 if r.get("status") == "organized" else 0
        not_staging = 0 if ("/_Inbox/" in p or "/Archive/" in p) else 1
        depth = min(p.count("/"), 20)   # cap depth so a deeply-nested staging path
                                        # can never out-rank a real destination
        # Tuple ordering: prefer organized, then non-staging, then deeper, then the
        # lowest id as a deterministic final tiebreak (input order is not guaranteed
        # stable). NOTE: the keeper is chosen with max(), so the id term is NEGATED
        # (-id) — a smaller id yields a larger -id, so max() lands on the lowest id.
        return (organized, not_staging, depth, -int(r.get("id", 0)))
    return max(files, key=score)


def cmd_duplicates(args):
    conn = get_db()

    # --colocate ID (or the deprecated --archive ID): move this duplicate so it sits
    # BESIDE the group's keeper, renamed <keeper-stem>_dupN, instead of being archived.
    target = getattr(args, "colocate", None)
    if target is None:
        target = getattr(args, "archive", None)   # deprecated alias — now co-locates too
    if target is not None:
        row = conn.execute("SELECT * FROM files WHERE id=?", (target,)).fetchone()
        if not row:
            conn.close(); sys.exit(f"File id {target} not found in registry.")
        src = Path(row["current_path"])
        if not src.exists():
            conn.close(); sys.exit(f"File not found on disk: {src}")
        # Use the SAME status filter as the main keeper selection below so the keeper
        # chosen here matches the one the user reviewed in the duplicates listing —
        # an unfiltered query could include rows the listing excluded and pick a
        # different keeper, co-locating beside a copy the user never saw.
        group = conn.execute(
            "SELECT id, current_path, status FROM files "
            "WHERE sha256=? AND sha256 IS NOT NULL "
            "AND status IN ('organized','pending','duplicate')",
            (row["sha256"],)
        ).fetchall()
        if len(group) < 2:
            conn.close(); sys.exit(f"File id {target} has no duplicates in the registry.")
        group_files = [{"id": g["id"], "path": g["current_path"], "status": g["status"]} for g in group]
        keeper = _pick_keeper(group_files)
        if keeper["id"] == target:
            conn.close()
            sys.exit(f"File id {target} is the keeper (best-placed copy of this group); "
                     f"co-locate a different copy instead.")
        keeper_path = Path(keeper["path"])
        # Verify the keeper actually exists on disk before co-locating beside it —
        # if it has been moved/deleted out from under the registry, co-locating into
        # a phantom directory would strand the duplicate. Abort cleanly instead.
        if not keeper_path.exists():
            conn.close()
            sys.exit(f"Keeper id {keeper['id']} not found on disk: {keeper_path}. "
                     f"Re-run duplicates to refresh the registry before co-locating.")
        keeper_dir = keeper_path.parent
        keeper_dir.mkdir(parents=True, exist_ok=True)
        # next _dupN beside the keeper, using the keeper's stem so they sort adjacent
        n = 1
        while (keeper_dir / f"{keeper_path.stem}_dup{n}{src.suffix}").exists():
            n += 1
        dest = keeper_dir / f"{keeper_path.stem}_dup{n}{src.suffix}"
        try:
            shutil.move(str(src), str(dest))
        except OSError as e:
            conn.close()
            sys.exit(f"Failed to co-locate id {target} ({src} -> {dest}): {e}")
        conn.execute(
            "UPDATE files SET current_path=?, status='duplicate', processed_at=? WHERE id=?",
            (str(dest), datetime.now().isoformat(), target)
        )
        conn.commit()
        conn.close()
        print(f"Co-located dup id {target} → {dest}  (beside keeper id {keeper['id']}: {keeper_path})")
        export_csv()
        return

    # Group in Python rather than via parallel GROUP_CONCAT calls: SQLite's
    # GROUP_CONCAT gives no cross-column ordering guarantee AND silently omits
    # NULLs, so a single NULL file_size used to shift every later column and
    # zip() mis-paired id/path/size — co-locating the wrong file. Per-row
    # grouping is exact.
    from collections import defaultdict
    by_hash: dict = defaultdict(list)
    for row in conn.execute(
        """SELECT id, sha256, current_path, file_size, file_date, status
           FROM files
           WHERE sha256 IS NOT NULL
             AND status IN ('organized','pending','duplicate')"""
    ):
        by_hash[row["sha256"]].append({
            "id": row["id"], "path": row["current_path"],
            "size": row["file_size"], "date": row["file_date"],
            "status": row["status"],
        })
    conn.close()

    groups = []
    for sha, files in by_hash.items():
        if len(files) < 2:
            continue
        files.sort(key=lambda f: f["id"])   # stable, readable order
        keeper = _pick_keeper(files)
        groups.append({
            "sha256": sha[:16] + "...",
            "_sha_full": sha,                   # full digest, used only for a stable sort
            "keeper_id": keeper["id"],          # the copy to keep in place; co-locate the rest
            "files": files,
        })

    if not groups:
        print("No exact duplicates found.")
        return

    # Sort by the FULL sha256 — the truncated display string ('<16hex>...') collides
    # for any two groups sharing a 16-hex prefix, making the order non-deterministic.
    groups.sort(key=lambda g: g["_sha_full"])
    for g in groups:
        g.pop("_sha_full", None)
    print(json.dumps(groups, indent=2))


# ---------------------------------------------------------------------------
# variants
# ---------------------------------------------------------------------------

def cmd_variants(args):
    from collections import defaultdict

    conn = get_db()
    rows = conn.execute(
        """SELECT id, current_path, filename, extension, file_size, file_date
           FROM files WHERE status IN ('organized','pending')"""
    ).fetchall()
    conn.close()

    groups: dict[str, list] = defaultdict(list)

    # variant_tokens: drive-wide config dial (config.json / Settings panel) that lets
    # domain-specific vocab (legal: executed/redlined; screenwriting: draft/revision)
    # extend the built-in variant-token list. Purely additive — user tokens are escaped
    # (plain vocab, not regex) and appended to the builtin alternation, never replace it.
    cfg = paths_config._read_user_config(paths_config._EFFECTIVE_ROOT)
    user_tokens = cfg.get("variant_tokens", []) or []
    builtin_tokens = ["v\\d+", "final", "copy", "highlighted?", "annotated?", "marked?"]
    all_tokens = builtin_tokens + [re.escape(t) for t in user_tokens]
    variant_token_pattern = "|".join(all_tokens)

    for row in rows:
        fname = row["filename"] or ""
        ext   = (row["extension"] or "").lower()
        base  = Path(fname).stem                       # drop the extension FIRST, otherwise the
        base  = re.sub(r"^\d+[-_]\s*", "", base)       # $-anchored variant-token strip below can
        # Strip trailing variant tokens repeatedly — "report_final_v2" carries two,
        # and a single re.sub would leave one behind, splitting variants that should group.
        while True:
            stripped = re.sub(
                rf"[\s_-]*({variant_token_pattern})$",
                "", base, flags=re.IGNORECASE
            )
            if stripped == base:
                break
            base = stripped
        base = base.lower().strip(" ._-")              # drop stray trailing separators/dots too
        key  = f"{ext}:{base}"
        groups[key].append({
            "id":        row["id"],
            "path":      row["current_path"],
            "filename":  fname,
            "file_size": row["file_size"],
            "file_date": row["file_date"],
        })

    variant_groups = []
    for key, members in groups.items():
        if len(members) < 2:
            continue
        # Do NOT drop a group because a member lacks file_size (missing => unknown
        # => include it) and do NOT gate on a size ratio: a highlighted/annotated PDF
        # can legitimately exceed 2x the plain original, so a ratio cap would split
        # exactly the variant pairs this command exists to surface.
        # Stable, content-derived id — Python's builtin hash() is salted per process
        # (PYTHONHASHSEED), so it produced a different group_id every run and could
        # collide mod 100000. A hashlib digest of the key is deterministic. (sha256,
        # not sha1 — the digest is just a grouping label, but sha256 matches the
        # file's other hashing and avoids the weak-crypto lint.)
        group_id = "grp_" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:10]
        variant_groups.append({"group_id": group_id, "key": key, "files": members})

    if not variant_groups:
        print("No variant groups found.")
        return

    conn = get_db()
    for group in variant_groups:
        for member in group["files"]:
            conn.execute(
                "UPDATE files SET variant_group=? WHERE id=?",
                (group["group_id"], member["id"])
            )
    conn.commit()
    conn.close()

    print(json.dumps(variant_groups, indent=2))


# ---------------------------------------------------------------------------
# merge
# ---------------------------------------------------------------------------

def _copy_pdf_annot(src, page_dst) -> bool:
    """Re-create a source annotation on the destination page. PyMuPDF has no direct
    cross-document annot copy (the old `page.add_annot(annot)` call is invalid and
    silently fails), so we rebuild the common markup types from the source's
    geometry + colour + content. Returns True if an annotation was created."""
    import fitz
    t = src.type[0]
    quad_types = {
        fitz.PDF_ANNOT_HIGHLIGHT: "add_highlight_annot",
        fitz.PDF_ANNOT_UNDERLINE: "add_underline_annot",
        fitz.PDF_ANNOT_STRIKE_OUT: "add_strikeout_annot",
        fitz.PDF_ANNOT_SQUIGGLY: "add_squiggly_annot",
    }
    try:
        if t in quad_types:
            # Quad-based markup must be created from QUADS, not the flat vertices
            # list. Prefer src.quads (already grouped 4 points per quad); fall back
            # to reconstructing quads from src.vertices in groups of 4. Passing the
            # flat vertices as quads= is wrong and silently drops the annotation.
            quads = getattr(src, "quads", None)
            if not quads:
                verts = list(src.vertices or [])
                quads = [verts[i:i + 4] for i in range(0, len(verts) - 3, 4)]
            if not quads:
                return False
            new = getattr(page_dst, quad_types[t])(quads=quads)
        elif t == fitz.PDF_ANNOT_TEXT:
            new = page_dst.add_text_annot(src.rect.tl, (src.info or {}).get("content", ""))
        elif t == fitz.PDF_ANNOT_FREE_TEXT:
            new = page_dst.add_freetext_annot(src.rect, (src.info or {}).get("content", ""))
        elif t == fitz.PDF_ANNOT_INK:
            new = page_dst.add_ink_annot(src.vertices)
        elif t == fitz.PDF_ANNOT_SQUARE:
            new = page_dst.add_rect_annot(src.rect)
        elif t == fitz.PDF_ANNOT_CIRCLE:
            new = page_dst.add_circle_annot(src.rect)
        else:
            return False
        try:
            colors = src.colors or {}
            if colors.get("stroke"):
                new.set_colors(stroke=colors["stroke"])
            if colors.get("fill"):
                new.set_colors(fill=colors["fill"])
            if src.opacity is not None and 0 <= src.opacity <= 1:
                new.set_opacity(src.opacity)
            content = (src.info or {}).get("content")
            if content:
                new.set_info(content=content)
            new.update()
        except Exception as e:
            import warnings
            warnings.warn(f"_copy_annot: annotation styling (new.update) failed: {e}", stacklevel=2)
        return True
    except Exception:
        return False


def cmd_merge(args):
    try:
        import fitz
    except ImportError:
        sys.exit("PyMuPDF is not installed.\nInstall with:  pip install pymupdf")
    try:
        fitz.TOOLS.mupdf_display_errors(False)   # silence noisy non-fatal MuPDF internal warnings
    except Exception:
        pass

    group_id     = args.group
    canonical_id = int(args.canonical)
    drive     = paths_config._EFFECTIVE_ROOT
    conn         = get_db()

    canonical_row = conn.execute(
        "SELECT * FROM files WHERE id=?", (canonical_id,)
    ).fetchone()
    if not canonical_row:
        conn.close()
        sys.exit(f"Canonical file id {canonical_id} not found.")

    others = conn.execute(
        "SELECT * FROM files WHERE variant_group=? AND id != ?",
        (group_id, canonical_id)
    ).fetchall()

    if not others:
        print("No other files in this variant group.")
        conn.close()
        return

    canonical_path = Path(canonical_row["current_path"])
    if not canonical_path.exists():
        conn.close()
        sys.exit(f"Canonical file not found: {canonical_path}")

    try:
        doc_canonical = fitz.open(str(canonical_path))
    except Exception as e:
        conn.close()
        sys.exit(f"Could not open canonical PDF {canonical_path}: {e}\n"
                 f"Nothing was changed — no originals archived.")
    to_archive = []   # (id, other_path) — archived only AFTER a successful save

    for other_row in others:
        other_path = Path(other_row["current_path"])
        if not other_path.exists():
            print(f"  skip missing: {other_path}", file=sys.stderr)
            continue
        try:
            doc_other = fitz.open(str(other_path))
        except Exception as e:
            print(f"  skip {other_path}: {e}", file=sys.stderr)
            continue

        src_pages = len(doc_other)
        more_pages = src_pages > len(doc_canonical)

        src_annots = copied = 0
        for page_num in range(min(len(doc_canonical), len(doc_other))):
            page_src = doc_other[page_num]
            page_dst = doc_canonical[page_num]
            for annot in (page_src.annots() or []):
                src_annots += 1
                if _copy_pdf_annot(annot, page_dst):
                    copied += 1

        doc_other.close()

        # Safety (a): the source has MORE pages than the canonical, so any annotation
        # on its trailing pages can't be merged (those pages don't exist in canonical).
        # Archiving would silently drop them — keep the original in place instead.
        if more_pages:
            print(f"  WARNING: {other_path.name} has {src_pages} pages vs canonical "
                  f"{len(doc_canonical)} — trailing-page annotations cannot merge; "
                  f"left in place (not archived).", file=sys.stderr)
            continue

        # Safety (b): the no-data-loss guard compares COPIED to the SOURCE annotation
        # count. Any shortfall (copied < src_annots) is partial loss = loss — keep the
        # original. (Covers the all-failed case too.)
        if src_annots > 0 and copied < src_annots:
            print(f"  WARNING: {other_path.name} has {src_annots} annotation(s) but only "
                  f"{copied} could be copied — left in place (not archived) to avoid data loss.",
                  file=sys.stderr)
            continue

        to_archive.append((other_row["id"], other_path))

    # Persist the merged canonical FIRST. Never save(incremental=True) OVER the
    # canonical in place — a crash or error mid-write would corrupt the only copy.
    # Instead: save to a TEMP path, verify it re-opens, then os.replace() it over the
    # canonical atomically. Only once that succeeds do we archive the originals.
    import os as _os
    tmp_path = canonical_path.with_name(f".{canonical_path.name}.merge.tmp.{_os.getpid()}")

    def _save_to_tmp():
        # Prefer a non-incremental full save to the temp file (a temp file has no
        # existing bytes to append to, so incremental is not meaningful here).
        try:
            doc_canonical.save(str(tmp_path), incremental=False, encryption=0)
        except Exception:
            # Retry with deflate off in case the source is encrypted/linearised and
            # the first attempt raised — keep it simple, one fallback attempt.
            doc_canonical.save(str(tmp_path), incremental=False)

    try:
        _save_to_tmp()
        doc_canonical.close()
        # Verify the temp file re-opens (and has pages) before we trust it.
        _verify = fitz.open(str(tmp_path))
        if _verify.page_count < 1:
            _verify.close()
            raise RuntimeError("merged temp PDF has no pages")
        _verify.close()
        _os.replace(str(tmp_path), str(canonical_path))
    except Exception as e:
        try:
            doc_canonical.close()
        except Exception:
            pass
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass
        conn.close()
        sys.exit(f"Failed to save merged canonical {canonical_path}: {e}\n"
                 f"Canonical left untouched; no originals were archived — nothing lost.")

    archive_dir = drive / "Archive" / "_Merged-Originals"
    archive_dir.mkdir(parents=True, exist_ok=True)
    merged_count = 0
    archive_failures = 0
    for other_id, other_path in to_archive:
        dest = archive_dir / other_path.name
        n = 1
        while dest.exists():            # counter loop — a single `_dup` could clobber a prior archive
            dest = archive_dir / f"{other_path.stem}_dup{n}{other_path.suffix}"
            n += 1
        # Wrap each archive move so one failure doesn't abort the whole merge
        # mid-way (the canonical is already saved; the rest should still archive).
        try:
            shutil.move(str(other_path), str(dest))
        except OSError as e:
            print(f"  WARNING: could not archive original {other_path}: {e}", file=sys.stderr)
            archive_failures += 1
            continue
        conn.execute(
            "UPDATE files SET current_path=?, status='archived', processed_at=? WHERE id=?",
            (str(dest), datetime.now().isoformat(), other_id)
        )
        merged_count += 1

    conn.execute(
        "UPDATE files SET processed_at=? WHERE id=?",
        (datetime.now().isoformat(), canonical_id)
    )
    conn.commit()
    conn.close()

    print(f"Merge complete: {merged_count} files merged into {canonical_path.name}.")
    print(f"Originals archived to Archive/_Merged-Originals/")
    if archive_failures:
        print(f"  ({archive_failures} original(s) could not be archived — see warnings above; "
              f"left in place, not lost.)")
    export_csv()


# ---------------------------------------------------------------------------
# generate-viewer
# ---------------------------------------------------------------------------
