"""drive_organizer.viewer_propose — split from the original organizer.py (pure structural move, no behavior change)."""
from __future__ import annotations
import json
import os
import sqlite3
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from drive_organizer import paths_config
from drive_organizer.paths_config import (
    PARA_ROOTS,
    _atomic_write,
    _effective_viewer_page_size,
)
from drive_organizer.viewer_propose_templates import (
    _STATIC_REVIEW_HTML_TEMPLATE,
    _VIEWER_HTML_TEMPLATE,
)


APPROVED_JSON_PATH = Path.home() / ".claude" / "drive-organizer" / "proposals_approved.json"


def _para_path_segments(para_subfolder: str) -> tuple[str, str, str]:
    """Split a stored subfolder path into up to 3 segments for the path-builder viewer."""
    parts = (para_subfolder or "").split("/", 2)
    return (
        parts[0] if len(parts) > 0 else "_Inbox",
        parts[1] if len(parts) > 1 else "",
        parts[2] if len(parts) > 2 else "",
    )


def _persist_vocab_from_approvals(db_path: str, approved: list) -> None:
    """Learn new path-vocab segments from approved proposal destinations.

    Inserts or increments `path_vocab` rows for each non-staging destination
    segment so the viewer's autocomplete reflects newly-seen paths.  Extracted
    from the HTTP handler so it can be called from process-return's learning
    loop or any future code path without going through the browser viewer.
    """
    if not approved or not db_path:
        return
    try:
        with sqlite3.connect(db_path) as _db:
            for entry in approved:
                subfolder = entry.get("para_subfolder", "")
                parts = subfolder.split("/", 2) if subfolder else []
                # Skip staging destinations entirely — they are not routing
                # vocab. That means a leading '_' (e.g. '_Inbox') AND any path
                # whose first segment is a PARA_ROOT (e.g. 'Archive/_To Delete',
                # the delete destination, which does NOT start with '_'); without
                # the latter check 'Archive' / '_To Delete' would be learned as
                # autocomplete destinations the next viewer round offers.
                if not subfolder or subfolder.startswith("_") or (parts and parts[0] in PARA_ROOTS):
                    continue
                for pos, seg in enumerate(parts, 1):
                    if seg:
                        _db.execute(
                            """INSERT INTO path_vocab (segment, position, use_count) VALUES (?,?,1)
                               ON CONFLICT(segment, position) DO UPDATE SET use_count = use_count + 1""",
                            (seg, pos),
                        )
    except Exception as e:
        print(f"Warning: could not save vocab: {e}", flush=True)


def _persist_flagged_status(db_path: str, flagged_ids: list) -> bool:
    """Write status='flagged' for the given file IDs in the SQLite registry.

    Extracted from the HTTP handler so the same update can be driven from
    process-return or any future non-HTTP code path.  Prints a success line
    on write (mutually exclusive with the warning line) so callers can branch
    on exactly one outcome.

    Returns True if the write succeeded (or there was nothing to write),
    False if the DB update failed — so callers can detect an un-persisted flag
    and react (e.g. warn the user to patch manually from proposals_flagged.json).
    """
    if not flagged_ids or not db_path:
        if flagged_ids and not db_path:
            # Files WERE flagged but the registry path was unavailable at viewer
            # launch (db absent). Emit the same warning shape so the executor reads
            # this as the flag-write-failed case (and applies the manual patch from
            # proposals_flagged.json) rather than the no-files-flagged case — those
            # flagged files would otherwise reappear as pending next round.
            print("Warning: could not mark flagged in DB: registry not found at viewer launch "
                  "(patch status='flagged' manually from proposals_flagged.json).", flush=True)
            return False
        return True
    try:
        placeholders = ",".join("?" * len(flagged_ids))
        with sqlite3.connect(db_path) as db:
            db.execute(
                f"UPDATE files SET status='flagged' WHERE id IN ({placeholders})",
                flagged_ids,
            )
        # Success line printed ONLY on a successful write — so the
        # success and warning lines are mutually exclusive (the executor
        # can branch on exactly one).
        print(f"{len(flagged_ids)} files marked flagged in registry.", flush=True)
        return True
    except Exception as e:
        print(f"Warning: could not mark flagged in DB: {e}", flush=True)
        return False


class _SilentHandler(BaseHTTPRequestHandler):
    """HTTP handler for the viewer; suppresses access logs."""

    _proposals: list = []
    _shutdown_event: threading.Event = None
    _db_path: str = None
    _vocab: dict = {}

    def log_message(self, format, *args):
        pass  # suppress access logs

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            proposals = self.__class__._proposals

            # Enrich proposals with derived keys for the viewer
            viewer_proposals = []
            for p in proposals:
                seg1, seg2, seg3 = _para_path_segments(p.get("para_subfolder", ""))
                vp = dict(p)
                vp["seg1"] = seg1
                vp["seg2"] = seg2
                vp["seg3"] = seg3
                viewer_proposals.append(vp)

            html = _VIEWER_HTML_TEMPLATE
            # Substitute the non-data placeholder first; do the proposal-data
            # replacement LAST so proposal text containing a literal placeholder
            # token can't be clobbered by a later replace().
            html = html.replace("__VOCAB_JSON__", json.dumps(self.__class__._vocab))
            html = html.replace("__PROPOSALS_JSON__", json.dumps(viewer_proposals))
            html = html.replace("__PAGE_SIZE__", str(_effective_viewer_page_size(paths_config._EFFECTIVE_ROOT)))
            body = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path != "/submit":
            self.send_response(404)
            self.end_headers()
            return

        # Parse Content-Length defensively: a malformed header must not crash
        # the handler, and an oversized body must not be read unbounded.
        try:
            length = int(self.headers.get("Content-Length", 0))
        except (TypeError, ValueError):
            self.send_response(400)
            self.end_headers()
            return
        if length < 0:
            self.send_response(400)
            self.end_headers()
            return
        MAX_BODY = 64 * 1024 * 1024  # 64 MB cap
        if length > MAX_BODY:
            self.send_response(413)
            self.end_headers()
            return
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            self.send_response(400)
            self.end_headers()
            return

        # Support both old flat-array format and new {approved, flagged} format
        if isinstance(payload, list):
            approved = payload
            flagged_ids = []
            skipped_ids = []
        else:
            approved = payload.get("approved", [])
            flagged_ids = payload.get("flagged", [])
            skipped_ids = payload.get("skipped", [])

        # Reject an empty submission rather than overwriting prior approvals
        # with nothing — an accidental/duplicate POST must not truncate output.
        if not approved and not flagged_ids:
            resp = json.dumps({"ok": False, "error": "empty submission"}).encode()
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp)))
            self.end_headers()
            self.wfile.write(resp)
            return

        # Persist both output files. A failure here (disk full, permissions, read-only
        # mount) must NOT crash the handler with a bare traceback and then fall through
        # to the success response + shutdown — that would tell the user their review was
        # saved when it was lost. Catch it, report it in the browser response AND on
        # stderr, and DON'T shut the server down so they can retry the submit.
        try:
            APPROVED_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
            # Write proposals_approved.json UNCONDITIONALLY (even an empty list):
            # process-return reads it every round, and a guarded skip on an
            # empty-approved-but-flagged submit would leave a STALE prior-round file the
            # consumer mistakes for this round's. An empty list is the correct signal —
            # execute then prints "Approved list is empty."
            _atomic_write(APPROVED_JSON_PATH, json.dumps(approved, indent=2))
            # Persist the EXACT flagged-ID set to a sidecar (the precise list
            # process-return's warning-branch fallback reads — never inferred by
            # set-difference, which catches unreviewed 'unset' rows too). Written
            # UNCONDITIONALLY (including []) so a flag-less submit CLEARS any prior-round
            # file instead of leaving stale IDs for the next round.
            _atomic_write(
                APPROVED_JSON_PATH.parent / "proposals_flagged.json",
                json.dumps(flagged_ids, indent=2),
            )
        except OSError as e:
            print(f"ERROR: could not write review output ({e}); submit NOT saved — "
                  f"resolve the disk/permission problem and re-submit.", file=sys.stderr, flush=True)
            err = json.dumps({"ok": False, "error": f"could not write output: {e}"}).encode()
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(err)))
            self.end_headers()
            self.wfile.write(err)
            return  # leave the server running so the user can retry

        # Surface deliberately-unreviewed ('unset') rows explicitly so downstream
        # knows which files were skipped rather than silently dropping them.
        if skipped_ids:
            print(
                f"{len(skipped_ids)} unreviewed files skipped (not written to "
                f"proposals_approved.json): ids {skipped_ids}",
                flush=True,
            )

        # Vocab-save and flag-write are data-layer operations; delegate to
        # module-level functions so the same logic is reachable from process-return
        # or any future non-HTTP path without coupling it to this transport layer.
        db_path = self.__class__._db_path
        _persist_vocab_from_approvals(db_path, approved)
        if not _persist_flagged_status(db_path, flagged_ids):
            print("Warning: flagged-status write failed in HTTP handler — "
                  "patch status='flagged' manually from proposals_flagged.json.", flush=True)

        try:
            resp = json.dumps({"ok": True, "path": str(APPROVED_JSON_PATH)}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp)))
            self.end_headers()
            self.wfile.write(resp)

            print(f"\nApproved proposals written to: {APPROVED_JSON_PATH}", flush=True)
            print("Server shutting down.", flush=True)
        finally:
            # Signal shutdown in a separate thread so response can be sent first.
            # In a finally so an unhandled exception in the response-send path
            # doesn't leave the server running indefinitely.
            if self.__class__._shutdown_event:
                threading.Timer(0.5, self.__class__._shutdown_event.set).start()


def _cowork_or_headless() -> bool:
    """True when the localhost browser viewer cannot be reached — a Cowork/remote
    session or an explicitly-headless run. The localhost HTTP viewer (port 5002/5003)
    is unreachable from Cowork (the user's browser is not on this host), so scan should
    fall back to the static review file instead of starting a server nobody can open.
    Signalled by DRIVE_ORG_HEADLESS=1, or any Cowork environment marker."""
    if os.environ.get("DRIVE_ORG_HEADLESS", "").strip().lower() in ("1", "true", "yes"):
        return True
    return any(os.environ.get(v) for v in ("CLAUDE_COWORK", "COWORK", "CLAUDE_CODE_COWORK"))


def _emit_static_review(proposals: list) -> Path:
    """Cowork-reachable fallback for the localhost viewer: write a self-contained,
    editable HTML review file (no server, no localhost POST) PLUS a pre-filled
    proposals_approved.json (every file defaulted to 'approved' at its proposed
    destination). The user reviews/edits in the HTML and clicks Download to produce an
    updated approved.json, OR edits the pre-filled JSON directly, then runs
    process-return. Returns the HTML path. The approved entry schema matches what the
    browser viewer POSTs (id / current_path / para_subfolder / new_filename / action),
    so the downstream consumer is identical — only the transport differs."""
    out_dir = APPROVED_JSON_PATH.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    # Pre-fill proposals_approved.json (all approved) so "accept everything" needs no
    # browser at all — the user can run process-return immediately, or edit first.
    prefilled = []
    for p in proposals:
        prefilled.append({
            "id": p.get("id"),
            "current_path": p.get("current_path") or p.get("original_path"),
            "para_subfolder": p.get("para_subfolder", ""),
            "new_filename": p.get("new_filename") or p.get("filename"),
            "action": "approved",
            "file_date": p.get("file_date"),
            "vision_desc": p.get("vision_desc"),
        })
    _atomic_write(APPROVED_JSON_PATH, json.dumps(prefilled, indent=2))

    # Self-contained editable HTML — the Download button builds the same
    # {approved, flagged, skipped} payload the localhost viewer POSTs, as a client-side
    # Blob the user saves over proposals_approved.json. No network, so it works wherever
    # the file can be opened (Cowork file preview, a copied-out browser, etc.).
    review_html = out_dir / "proposals_review.html"
    rows = json.dumps(proposals)
    appr_path_js = json.dumps(str(APPROVED_JSON_PATH))
    html = _STATIC_REVIEW_HTML_TEMPLATE
    html = html.replace("__ROWS__", rows).replace("__AP__", appr_path_js)
    _atomic_write(review_html, html)
    return review_html


def cmd_generate_viewer(args):
    from drive_organizer.classify_propose import _bubble_sort_proposals
    from drive_organizer.entities_rules import _read_entities
    proposals_path = Path(args.proposals)
    if not proposals_path.exists():
        sys.exit(f"Error: proposals file not found: {proposals_path}")

    with open(proposals_path, encoding="utf-8") as f:
        proposals = json.load(f)

    if not proposals:
        sys.exit("Error: proposals JSON is empty.")

    # Bubble-sort by destination so files going to the same leaf appear together
    proposals = _bubble_sort_proposals(proposals)

    # Cowork-reachable fallback: if asked for --static, or a Cowork/headless session is
    # detected, emit a static editable review file instead of a localhost server nobody
    # on this host can open.
    if getattr(args, "static", False) or _cowork_or_headless():
        review_html = _emit_static_review(proposals)
        print("Static review mode (localhost viewer not reachable here).")
        print(f"  Review + edit:        {review_html}")
        print(f"  Pre-filled approvals: {APPROVED_JSON_PATH}  ({len(proposals)} files, all 'approved')")
        print("  Edit in the HTML and Download, or edit the JSON directly, then run process-return.")
        print("  (To force the localhost server instead, re-run without --static and unset DRIVE_ORG_HEADLESS.)")
        return

    port = int(args.port) if args.port else 5002

    # Load path vocab from registry (+ built-in structural defaults)
    # Level 1 is seeded from .tidy-rules.json — never hardcoded here.
    # Level 2 = universal subfolder *types*; level 3 = common depth-3 structural names.
    # This is a curated seed list hand-aligned with subfolder-templates.json's
    # subfolder_definitions — it is NOT read from that file at runtime (autocomplete must
    # work before any templates are loaded), so it is only a convenience seed: the live,
    # authoritative vocabulary comes from the registry's actually-used path segments
    # (queried below), which always reflect the real taxonomy even as the templates grow.
    # Personal ENTITY names (people, joint owners, etc.) are NOT hardcoded here — they
    # are seeded per-drive from entities.json / the registry's used segments below, so a
    # shared install ships only generic types, never any individual's identity.
    BUILTIN_VOCAB: dict[int, list[str]] = {
        1: [],
        2: ["Schedules", "Docs", "References", "Legal", "Financials",
            "Templates", "Planning", "Admin", "Notes", "Reports",
            "Academic Papers", "Archived", "Deliverables"],
        3: ["Bills", "Invoices", "Receipts", "Bank Statements", "Tax Documents",
            "Expense Reports", "Payment Summaries", "Advances",
            "Contracts", "Agreements", "Backups", "Code", "Output"],
    }
    # NOTE: this is a small UNIVERSAL seed only. Any user's real, domain-specific
    # vocabulary reaches autocomplete from the registry's actually-used path segments
    # (path_vocab, queried below) and from entities.json — it is NOT hardcoded here, so
    # the shipped skill ships no individual's taxonomy.
    vocab: dict[int, list[str]] = {1: [], 2: [], 3: []}
    if paths_config.REGISTRY_DB.exists():
        try:
            with sqlite3.connect(str(paths_config.REGISTRY_DB)) as _db:
                _db.row_factory = sqlite3.Row
                for row in _db.execute(
                    "SELECT segment, position FROM path_vocab ORDER BY use_count DESC"
                ).fetchall():
                    pos = row["position"]
                    if pos in vocab:
                        vocab[pos].append(row["segment"])
        except (sqlite3.DatabaseError, OSError) as e:
            print(f"WARNING: could not read path_vocab from registry "
                  f"({type(e).__name__}: {e}); proposal-path autocomplete "
                  f"may be incomplete.", file=sys.stderr)
    # Seed level-1 directly from .tidy-rules.json (source of truth for top-level names)
    rules_file = paths_config._EFFECTIVE_ROOT / ".tidy-rules.json"
    if rules_file.exists():
        try:
            _rules_data = json.loads(rules_file.read_text(encoding="utf-8"))
            _seen_l1 = set(vocab[1])
            for _rule in _rules_data.get("rules", []):
                _top = _rule.get("folderName", "").split("/")[0].strip()
                if _top and _top not in _seen_l1:
                    vocab[1].append(_top)
                    _seen_l1.add(_top)
        except (json.JSONDecodeError, OSError) as e:
            print(f"WARNING: could not seed vocab[1] from {rules_file} "
                  f"({type(e).__name__}: {e}); level-1 autocomplete may be "
                  f"incomplete.", file=sys.stderr)
    # Seed entity names (people / joint owners / orgs) from this drive's entities.json —
    # the per-drive source of truth for identities. Replaces the formerly-hardcoded
    # personal names so a shared install carries none, yet a configured drive still
    # autocompletes its own entities. Entities sit at the "thing inside" depth (level 2).
    _seen_l2 = set(vocab[2])
    for _ent in _read_entities().keys():
        if _ent and _ent not in _seen_l2:
            vocab[2].append(_ent)
            _seen_l2.add(_ent)
    for pos in [2, 3]:
        seen = set(vocab[pos])
        for v in BUILTIN_VOCAB[pos]:
            if v not in seen:
                vocab[pos].append(v)
                seen.add(v)

    shutdown_event = threading.Event()
    _SilentHandler._proposals = proposals
    _SilentHandler._shutdown_event = shutdown_event
    if not paths_config.REGISTRY_DB.exists():
        print(
            "WARNING: Registry DB not found — flagged decisions submitted via viewer will be "
            "saved to proposals_flagged.json but NOT written to the registry. "
            "Run `organizer.py scan` to create the registry first, then re-open the viewer.",
            file=sys.stderr
        )
    _SilentHandler._db_path = str(paths_config.REGISTRY_DB) if paths_config.REGISTRY_DB.exists() else None
    _SilentHandler._vocab = {str(k): v for k, v in vocab.items()}

    import errno as _errno
    try:
        server = HTTPServer(("127.0.0.1", port), _SilentHandler)
    except OSError as e:
        if e.errno == _errno.EADDRINUSE:
            sys.exit(
                f"Error: port {port} is already in use. "
                f"Try another --port (e.g. --port {port + 1})."
            )
        raise
    server.timeout = 1.0

    server_thread = threading.Thread(target=_serve_until, args=(server, shutdown_event), daemon=True)
    server_thread.start()

    url = f"http://localhost:{port}/"
    print(f"Viewer running at {url}")
    print(f"Proposals: {len(proposals)} files")
    print(f"Approved output will be written to: {APPROVED_JSON_PATH}")
    print("Press Ctrl+C to stop.")

    if not getattr(args, "no_open", False):
        webbrowser.open(url)

    try:
        shutdown_event.wait()
    except KeyboardInterrupt:
        print("\nInterrupted — shutting down.")
    finally:
        server.shutdown()


def _serve_until(server: HTTPServer, stop_event: threading.Event):
    """Run the server, checking stop_event each timeout cycle."""
    while not stop_event.is_set():
        try:
            server.handle_request()
        except Exception as e:
            # A single handler exception must not kill the serve loop, or the
            # viewer would die mid-review and lose unsubmitted approvals.
            print(f"Warning: request handler error: {e}", flush=True)


# ---------------------------------------------------------------------------
# cleanup
# ---------------------------------------------------------------------------
