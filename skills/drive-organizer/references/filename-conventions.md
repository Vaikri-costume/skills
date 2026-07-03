# Filename conventions + project metadata

Detailed naming patterns per grouping, plus the `filename_tag` / `date_range` metadata in each project's `.tidy-rules.json`, plus the on-disk shape of the `proposals_classified.json` Claude writes after each propose pass. Consulted by `propose` for every file.

## Grouping-specific patterns

| Grouping | Pattern | Example |
|---|---|---|
| **WORK** — Admin / Branding | `YYYYMMDD_<Company>_<descriptive>.ext` | `20240521_[COMPANY]_invoice_template_v2.pdf` |
| **WORK** — Projects | `YYYYMMDD_<Company>_<ProjectTag>_<descriptive>.ext` | `20240521_[COMPANY]_[PROJ]_[Person]_advance.pdf` |
| **PERSONAL** | `YYYYMMDD_<Issuer>_<Type>_<descriptive>.ext` *(Issuer + Type pulled from content_peek)* | `20240615_CityPower_Bill_electricity_jun24.pdf`, `20240315_FirstBank_Statement_mar24.pdf` |
| **EDUCATION** | `YYYYMMDD_<Entity>_<descriptive>.ext` *(Entity = institution / publication / author from content_peek)* | `20240601_SOAS_offer_letter.pdf`, `20240515_Nature_microplastics_review.pdf` |
| **ENTERTAINMENT** | `AlbumName - SongTitle - Artist.ext` (no date prefix; album folder carries the year) | `Album Name - Song Title - Artist.mp3` |
| **RESOURCES** | `<asset_name>.ext` (no date prefix; assets are timeless) | `Helvetica_Neue_Bold.ttf` |

The CONTEXT_TAG embeds enough identifying information that the file remains discoverable if it leaves its folder (email attachment, escaped to `_Inbox`, etc.).

## Always read `content_peek` before generating `new_filename`

When the filename is opaque (numeric prefix + nothing meaningful after stripping), `content_peek` is the primary source for the name. Extract from content: who/what is this document, what type is it, who issued it, any date inside it.

- **Date**: extract from filename first (e.g. `21.05.24`, `2024-06-08`) → convert to YYYYMMDD; fall back to a date in `content_peek`; use file mtime as last resort; omit if truly unknown
- **Issuer** (PERSONAL): bank / utility / institution name from content_peek (e.g. "FirstBank", "CityPower", "StateUniversity")
- **Type** (PERSONAL): bill / statement / invoice / receipt / form
- **Entity** (EDUCATION): institution / publication / author from content
- **Project tag** (WORK): pulled from the project folder's `.tidy-rules.json` `filename_tag` field — see "Project metadata" below
- **Clean name**: strip leading numeric prefix (`00001200-`); normalise to underscores (max ~5 words); strip duplicate-number suffixes like `(3)`

## Examples

| Original | Grouping | content_peek | New name |
|----------|----|-------------|----------|
| `00000936-[Project]_3rd_May_-_v2_Revision.docx` | WORK | — | `20240503_[COMPANY]_[PROJ]_[Project]_v2_Revision.docx` |
| `00001200-[Person] 21.05.24 advance.pdf` | WORK | "[Project] / [COMPANY] / advance ₹..." | `20240521_[COMPANY]_[PROJ]_[Person]_advance.pdf` |
| `CC_Statement_2025_06_25 (3).xlsx` | PERSONAL | "FirstBank credit card statement" | `20250625_FirstBank_Statement_jun25.xlsx` |
| `bill_jun24.pdf` | PERSONAL | "CityPower electricity bill, June 2024" | `20240615_CityPower_Bill_electricity_jun24.pdf` |
| `00000744-0.pdf` | WORK | "Invoice No. INV-2024-0042 \| Client: [COMPANY] \| ₹50,000" | `20240415_[COMPANY]_invoice_INV2024_0042.pdf` |
| `microplastics_review.pdf` | EDUCATION | "Nature journal article" | `20240901_Nature_microplastics_review.pdf` |
| `00000744-0.pdf` | unclear | (empty / unreadable) | `00000744-0.pdf` → `_Inbox/` |

## Project metadata (`filename_tag` + `date_range`)

Each project's `.tidy-rules.json` carries two metadata fields used by `propose` for naming and date-routing:

```json
{
  "filename_tag": "[COMPANY]_[PROJ]",
  "date_range": { "start": "2024-04-01", "end": "2024-08-15" },
  "rules": [ ... ]
}
```

- **`filename_tag`** — canonical tag inserted into `new_filename` for files routed into this project. For Admin / Branding folders the tag is just the company name (`[COMPANY]`, `[COMPANY]`, `[COMPANY]`) — Admin/Brand sub-tags add no information. For projects it's `<Company>_<ProjectTag>` (e.g. `[COMPANY]_[PROJ]`, `[COMPANY]_[PROJ]`).
- **`date_range`** — `{start, end}` date range. Used during propose to route loose bills, invoices, and receipts: if a file's date falls inside a project's date range, it's a candidate match for that project. Multiple matching projects → ask via the viewer.

**Entities can also carry a `filename_tag` (Phase-3).** A person, issuer, or bank entity in `<root>/.organizer/entities.json` may carry its own `filename_tag`, the same field with the same meaning — the canonical tag inserted into `new_filename` for files routed to that entity. This generalises the field off projects-only: a bill from the same bank gets a fixed, deterministic issuer tag instead of being re-inferred from `content_peek` every round. Just like an entity's `date_range` (see `references/classify-prompt.md`), it is read straight from `entities.json` — no project-folder `.tidy-rules.json` is involved. Set/edit it via the rules-viewer entity card.

**Learn-as-you-go:** `date_range` starts as `null` for any project where the dates aren't known yet. As files get approved into a project, `process-return` expands the period to span the min/max approved file dates (with a buffer at each end — the authoritative buffer value is the `buffer_days=30` default of `_expand_date_range` in `scripts/drive_organizer/date_range.py`; the code is the single source of truth). After a few approval rounds, every project has a calibrated date range without you ever specifying dates manually. If you do know a date range up front, set it in the rules file and propose will use it from the start.

## `proposals_classified.json` shape

Claude writes the enriched proposals to `~/.claude/drive-organizer/proposals_classified.json`. Every entry carries the base fields from `propose`'s stdout **plus** its lane fields. The two lanes are disjoint — a file is `auto_routed` OR `needs_classification`, never both.

**Base fields** (present on every entry):
```json
{
  "id": 1,
  "current_path": "/abs/path/to/file.jpg",
  "filename": "00000097-PHOTO-2024-04-17.jpg",
  "extension": ".jpg",
  "file_size": 2048576,
  "file_date": "2024-04-17",
  "is_image": true,
  "is_raw": false,
  "content_peek": null
}
```

**Auto-routed lane** (`auto_routed: true`):
```json
{
  "auto_routed": true,
  "para_subfolder": "PERSONAL/PERSONAL Photos/2024/April 24",
  "proposed_subfolder": "PERSONAL/PERSONAL Photos/2024/April 24",
  "auto_reason": "already in ruled folder",
  "auto_approved": true
}
```
(`auto_approved` only present when `auto_approve` is enabled in config.)

**Needs-classification lane** (`needs_classification: true`):
```json
{
  "needs_classification": true,
  "classify_batch": 0,
  "para_subfolder": "PERSONAL/PERSONAL Photos/2024/April 24",
  "new_filename": "20240417_outdoor_dinner_group.jpg",
  "vision_desc": "Group of people at an outdoor dinner celebration",
  "file_date": "2024-04-17",
  "reason": "personal photo",
  "signal": "personal-photo",
  "confidence": "high"
}
```
When the file was cost-toggle blocked, also include:
```json
{
  "route_by_name_only": true,
  "open_blocked_reason": ["vision-off"]
}
```

`para_subfolder` is the only routing field — it's a path relative to the drive root. No top-level category bucket is needed; the prefix on the path encodes everything. (`para_category` is **not** part of the verdict Claude writes: it's a derived registry column the viewer/execute set automatically from the path's top segment — so it's absent from the shape above by design, not omission.) `signal` and `confidence` are present on classified entries only — the backend never reads `confidence` to set `auto_approved` (that flag is W1 fast-path only).

---

## Writing a new subfolder rule (project-specific vs generalizable)

Subfolder rules always go in the **per-folder** `.tidy-rules.json`, never in root descriptions — the root `description` matches files to a *top-level* folder, so stuffing subfolder patterns into it pollutes that signal. Where the rule goes depends on scope:

- **Project-specific** → append to that one project's `.tidy-rules.json` (e.g. `WORK/[COMPANY]/[COMPANY] [Project]/.tidy-rules.json` only). **Write the CONCRETE folder name, not a `[Placeholder]` pattern** — a per-folder rule's `folderName` is the literal on-disk folder, and the matcher tokenises `folderName` directly (a literal `[Character]` would route on the token "character"). The `[Character]`/`[Project]` brackets are abstract notation used *only* in `subfolder-templates.json`; expand them to real names here. Example — for a folder `Acme Workshop Notes`: `folderName: "Acme Workshop Notes"`, `description: "Acme workshop notes for <project> in Acme Workshop Notes"` (description must end with `in <FolderName>`, space not comma — see SKILL.md "Description format").
- **Generalizable across a project type** → add/update the entry in `references/subfolder-templates.json` (the canonical place for cross-project shared structure) — e.g. a pattern that should apply to all project folders goes under `compound_children.References` or wherever it belongs in the cascade. Per-folder rules files only carry patterns that *don't* generalise.

---

## proposals_approved.json shape

The viewer writes `~/.claude/drive-organizer/proposals_approved.json` on submit — the same entry shape as `proposals_classified.json` plus an `action` field:

```json
[
  {
    "id": 1,
    "current_path": "/absolute/path/to/file.jpg",
    "filename": "original_filename.jpg",
    "is_image": true,
    "para_subfolder": "PERSONAL/PERSONAL Photos/2024/April 24",
    "new_filename": "20240417_outdoor_dinner_group.jpg",
    "vision_desc": "Group of people at an outdoor dinner celebration",
    "file_date": "2024-04-17",
    "reason": "personal photo",
    "action": "approved"
  }
]
```

`action` values are a **closed set**: exactly `"approved"` | `"rejected"` | `"inbox"` | `"delete"` — the viewer emits no others, and any other value is a contract violation (execute defaults an unrecognized/absent `action` to `"approved"` via `entry.get("action", "approved")`, so a malformed action silently routes by `para_subfolder` rather than erroring — don't rely on that). Flagged entries (`?`) are **not** in this file — they go directly to the registry as `status='flagged'`. The closed `action` set above applies to `proposals_approved.json` (post-viewer); entries in `proposals_classified.json` (pre-viewer — including arbiter `reroute_low` entries) carry **no** `action` field — the viewer assigns `action` on submit, so a classified entry must not carry one. Rejected entries must have their `para_subfolder` corrected and written back before execute. `new_filename` is populated when the classifier or arbiter assigns a clean name; it may be absent when the arbiter omits it (execute falls back to `src.name` — the basename of the entry's `current_path` at execute time, which reflects any prior move — not the scan-time `entry["filename"]`, which is never updated after the original scan).
