# Drive Organizer

## What this skill does

Drive Organizer sorts the files on a drive — cloud-synced (OneDrive, iCloud, Dropbox, Google Drive), external, or local — into a nested folder structure of top-level groupings (by default ENTERTAINMENT, PERSONAL, WORK, EDUCATION, RESOURCES — the set is user-configurable) that *you* define and that the skill *learns* from your corrections over time. It reads file content (and images, via vision) to decide where each file belongs, proposes a destination + a clean filename for every file, and lets you approve or correct them in a browser before anything moves. A Python backend keeps a SQLite registry (mirrored to a human-readable CSV) so nothing is ever lost and duplicates are caught across batches.

Concrete use cases:

- **Rolling batch organise** — trigger: "organise my drive" / `/drive-organizer` → steps: scan a 250-file/20GB batch, classify each file via the cascading-Q model, review proposals in the browser viewer, execute the approved moves, clean up empty folders, repeat → result: an inbox-zero drive sorted into your taxonomy.
- **Reconcile a drifted structure** — trigger: "my folders got messed up" / `/drive-organizer reconcile` → steps: detect misplaced files, stale registry rows, and a mangled folder tree; report everything; apply fixes only on confirmation → result: the on-disk + registry state realigned to your intended structure.
- **Find and co-locate duplicates** — trigger: "find duplicates" / `/drive-organizer duplicates` → steps: group byte-identical files, keep the best-named copy, place the others beside it suffixed `_dupN` → result: duplicates sitting next to their original for easy visual checking.

## Intent

This skill exists to route files **into a folder taxonomy the user has designed**, not to invent one. That is the load-bearing design choice and what separates it from every off-the-shelf organiser: AI organisers generate their own categories; rule engines can't read content. Drive Organizer does neither — it classifies by content *and* respects a fixed, user-evolved structure.

It deliberately prioritises, and a fix that trades any of these away should be surfaced for human judgment rather than applied automatically:

- **Human approval + a learning loop over full automation.** Every file passes a browser review; approvals with edited destinations teach new rules. Speed is sacrificed for correctness and for the structure staying *the user's*.
- **Semantic classification (vision + content-entity matching) over pure rule-matching.** Most of the real library is generically-named (photos, scans, RAW); routing depends on content and parent-folder context, which mechanical rules cannot resolve.
- **Safety over speed.** Files are never deleted (only moved to staging); destructive operations (reconcile `--apply`, duplicates) are dry-run-then-confirm; every mutation mirrors to a CSV the user can audit.
- **A user-defined, evolving taxonomy over a fixed preset.** Rules live in per-folder `.tidy-rules.json` files that grow lazily; the shipped skill is a bare skeleton each user grows into their own structure.

## When to use / When NOT to use

**Use when:** you have a drive (cloud-synced, external, or local) with many unsorted files and a target folder structure you want them sorted *into*; you want to review/correct classifications before files move; you need to detect duplicates or variant files (e.g. plain vs highlighted PDF); or your organised structure has drifted and needs reconciling.

**Don't use when:** you want a tool to *invent* a folder structure for you with zero setup (use an AI auto-organiser instead — this skill routes into *your* taxonomy); you need fully-unattended sorting with no review step (this is human-in-the-loop by design); or you only need a one-off move of a handful of files (just move them — the batch machinery is overkill).

## How to install

**Claude Code:** copy this folder to `~/.claude/skills/drive-organizer/`. On first run the skill installs its Python backend to `~/.claude/drive-organizer/organizer.py` automatically. Point it at your drive once: `python3 ~/.claude/drive-organizer/organizer.py --root /path/to/your/drive status` (defaults to `~/Library/CloudStorage/OneDrive-Personal` on macOS).

**Cowork / Claude Desktop:** zip the `drive-organizer/` folder and add it via **Settings → Capabilities → Skills**.

**Requirements:** Python 3.9+ (standard library). Optional: `mutagen` (audio metadata), `PyMuPDF` (PDF annotation merge), `organize-tool` (reconcile drift cross-check) — `pip3 install --user --break-system-packages mutagen pymupdf organize-tool`.

(Not yet on a marketplace — install manually as above; a `claude plugins install` command will replace this once published.)

## How to invoke

- Slash command: `/drive-organizer` (no subcommand = backend check + status + scan), or a subcommand: `status`, `scan`, `propose`, `generate-viewer`, `process-return`, `execute`, `cleanup`, `reconcile`, `duplicates`, `variants`, `merge`, `mark-unapproved`, `flagged`, `csv-export`.
- Natural language: "organise my drive", "sort these files into folders", "my folder structure got messed up — fix it", "find duplicate files", "show me the folder tree".

Example:
```
/drive-organizer
→ verifies the backend, confirms the active root, scans a 250-file batch,
  classifies each file, and tells you "247 files classified, 10 pages — say
  'launch the viewer' when ready to review."
```

## Quick start

1. **Set your drive root once:** `python3 ~/.claude/drive-organizer/organizer.py --root /path/to/drive status` (macOS OneDrive is the default if you skip this).
2. **Scan a batch:** `/drive-organizer` (or `scan`) — hashes up to 250 files / 20 GB, pulling cloud-only files down as needed.
3. **Review in the browser:** say "launch the viewer" — approve / reject / flag / inbox / delete each proposed move, and edit any destination or filename inline.
4. **Apply + repeat:** the skill executes approved moves, *learns rules from your edits*, removes empty folders, and refills the next batch. Repeat until the drive is sorted.
5. **Maintain:** run `reconcile` if the structure ever drifts; do the final pass `duplicates` → `variants` → `merge` once organising is done.

Other things you can do: `reconcile` (detect/repair drift), `duplicates --colocate`, `variants` + `merge` (combine annotated PDFs), `mark-unapproved` (quarantine legacy folders). Full reference: [`SKILL.md`](SKILL.md).

## Sibling skills

- `claude-code-cowork-skills-file-organizer` (smithjoshua) — the PARA-method organiser that inspired this skill's grouping/inbox model. Drive Organizer diverges with a five-grouping taxonomy, vision/semantic routing, cloud-drive handling, and a learning loop.

## For developers

> **v1.3.1 status:** Hardened by two whole-file code reviews — a 19-fix pass (1.3.0) and a 140-fix Phase-0 baseline review (1.3.1, incl. path-traversal/atomic-write/dedup/cross-platform fixes) — and verified on a >25 GB four-loop sandbox gate (all invariants passed). It has been through the multi-agent `simplify` polish, but **not yet a cold `/skill-tracer` run to convergence** — that full trace is planned. Treat it as code-reviewed and gate-verified, but not yet formally trace-converged.

The runtime workflow lives in [`SKILL.md`](SKILL.md). Provenance and changelog live in [`HISTORY.md`](HISTORY.md). To trace this skill for bugs: `/skill-tracer drive-organizer`. To ship a new version: `/skill-publisher drive-organizer`.
