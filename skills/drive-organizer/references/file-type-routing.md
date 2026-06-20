# File-type routing reference

Per-file-type classification heuristics for the drive-organizer skill. Consult this file from SKILL.md's propose step whenever the file type's routing isn't obvious from path + filename alone, or when you need to confirm how to handle a specific extension or pattern.

The cascading-Q routing model in SKILL.md handles the *destination cascade* (Q1 grouping → Q2 thing → Q3 functional area → Q4 leaf type). The tables below handle the *file-type-specific decisions* that happen alongside that cascade: whether vision is needed, what filename to generate, what to do with sidecars / atomic folders / legacy formats / corrupted extensions.

## Table of contents
- [Images and Camera RAW](#images-and-camera-raw)
- [Documents (high level)](#documents-high-level)
- [External folders](#external-folders)
- [Atomic-unit folders](#atomic-unit-folders)
- [Scientific / medical time-series data](#scientific--medical-time-series-data)
- [Legacy / dead-format media](#legacy--dead-format-media)
- [Config / system / log files](#config--system--log-files)
- [Spreadsheets and Presentations](#spreadsheets-and-presentations)
- [Audio](#audio)
- [Video](#video)
- [Design source files](#design-source-files)
- [Templates and Fonts](#templates-and-fonts)
- [Archives](#archives)
- [eBooks](#ebooks)
- [Web links and snippets](#web-links-and-snippets)
- [Markdown](#markdown)
- [Code and config](#code-and-config)
- [Installers and executables](#installers-and-executables)
- [Sidecar files](#sidecar-files)
- [Lock files](#lock-files)
- [OneDrive conflict-suffixed extensions](#onedrive-conflict-suffixed-extensions)
- [Compound corruption](#compound-corruption)
- [Legacy / obscure formats](#legacy--obscure-formats)
- [Procreate](#procreate)

---

## Images and Camera RAW

**Image extensions**: `.jpg`, `.jpeg`, `.png`, `.gif`, `.heic`, `.heif`, `.webp`, `.tiff`, `.tif`, `.bmp`, `.jfif`

**Camera RAW extensions**: `.nef` Nikon, `.raf` Fuji, `.arw` Sony, `.cr2`/`.cr3` Canon, `.dng`, `.orf` Olympus, `.rw2` Panasonic

RAW files can't be vision-read (Claude can't decode proprietary RAW formats). Skip the Read tool for RAW always — classify by parent folder + filename alone, treat the same as you would treat the JPEG/HEIC version.

**First, decide whether vision is actually needed.** Most images can be classified from path + filename alone, and vision (Read tool on the image) is expensive. Observation from previous batches: of ~84 images in one batch, ~75 had path/filename signal strong enough to skip vision entirely — they got Read calls anyway, which was wasted time. Group images by `current_path` parent folder and inspect filenames before classifying. Skip vision when ANY of these are true:

| Condition | Example | Action |
|-----------|---------|--------|
| Folder is a known project AND filename is descriptive | `[COMPANY]/company_announcement_blog.png` | Classify by filename → `WORK/[COMPANY]/[COMPANY] Admin/Promotional Assets/`. Use filename slug as `vision_desc`. |
| Folder is a known project AND filenames are a numbered series | `BCF05 Parlour Didi/1.jpg`, `2.jpg`, `3.jpg` | Likely costume deck pages → `<Project>/Scene Breakdown/`. Number = page. No vision needed for any of them. |
| Folder path encodes the destination via `.tidy-rules.json` | `[COMPANY] [Project]/[Person]/anything.jpg` | The folder's rule says References → route there. Generic `[Project]_[Person]_reference_N.jfif` filename is fine. |
| Filename has a date pattern + clear subject | `20240417-PHOTO-2024-04-17.jpg` in `[Person] Photos/Holi 2024/` | Event folder preserves; date in filename. → `PERSONAL/PERSONAL Photos/Holi 2024/20240417_holi.jpg`. |

**Use vision only when:**
- Filename is opaque AND folder is generic/staging (`images.jfif` at root, `IMG_1234.jpg` in `_Inbox/`, photos in `[Person] Photos/` with no event subfolder)
- Path suggests one destination but filename suggests another, and you need to disambiguate (e.g. logo file in a character folder — could be misfiled)
- The classification routes via image content (e.g. is this a reference photo or a costume deck page? — content tells you)

When vision IS needed:
1. Read the image using the Read tool
2. Write a 1-sentence subject description → `vision_desc`

Either way:
3. Extract date from filename pattern `\d+-PHOTO-(\d{4}-\d{2}-\d{2})`; fall back to file mtime
4. Generate new filename per the grouping-specific convention in SKILL.md (PERSONAL → `YYYYMMDD_<Issuer>_<Type>_<descriptive>.ext`; WORK project → `YYYYMMDD_<Company>_<ProjectTag>_<descriptive>.ext`; etc.)
5. Classify via the cascading Q model:
   - **Primary signal for images is the parent folder in `current_path`** — it's almost always the project indicator. Walk the cascade from root → grouping → project.
   - If no project signal (loose photo, generic parent folder), check `references/tidy-builtin-categories.json` — Pictures / Screenshots / Personal categories cover faces, social, travel, screenshots.
   - Receipts / IDs / medical docs photographed: route through their respective categories (Finance / Government / Health) in the fallback JSON.
   - Anything unresolved: `_Inbox/`.

**Preserve event folders for personal photos**: If a photo's `current_path` shows it's already inside a named event subfolder (e.g. `[Person] Photos/Holi 2024/IMG_1234.jpg`, `[Person] Photos/Diwali 2023/`, `[Person] Photos/Goa Trip Feb 2024/`), keep that event folder structure under `PERSONAL/PERSONAL Photos/`. Route the file to `PERSONAL/PERSONAL Photos/Holi 2024/`, not `PERSONAL/PERSONAL Photos/2024/March 24/`. Only photos that arrive **loose** (no meaningful parent folder, or only inside a year/date-named container) get bucketed into the `PERSONAL/PERSONAL Photos/YYYY/Month YY/` structure. The event folder name carries information the year/month bucket loses.

---

## Documents (high level)

`.pdf`, `.docx`, `.doc`, `.xlsx`, `.fdx`, etc. — use filename heuristics **and** `content_peek`. If the filename is ambiguous but the content peek clearly signals a type (e.g. "Invoice No. INV-2024-0042"), trust the content over the filename.

Apply the cascading-Q model from SKILL.md "Routing model". For documents specifically the cascade walks like this:

- **Q1** — root rules' descriptions discriminate between ENTERTAINMENT / PERSONAL / WORK / EDUCATION / RESOURCES. Match by filename, content_peek, and parent of current_path. Project / character / cast / company name in content_peek is the strongest signal for WORK.
- **Q2** — inside the grouping, match against that grouping's `.tidy-rules.json`. For WORK, this distinguishes the individual companies (e.g. `[COMPANY A]` / `[COMPANY B]` / `[COMPANY C]` — the actual company folders that exist in this user's WORK rules; the bracketed names are placeholders for whatever real companies the on-disk rules define). For PERSONAL, this distinguishes Financial / Medical / Admin / ID / Resumes / Writing. For EDUCATION, Masters Applications / Research. For ENTERTAINMENT, Music / Movies / Books / Comics / RPGs / Sewing. For RESOURCES, Fonts / Templates / Film Stills.
- **Q3** — inside the thing, the question narrows further. For a WORK production, it's the production type (project name, Admin, CLIENT). For a PERSONAL tree, it's the person. For Research, it's Academic Papers / Film Coverage / Notes / Lyrics Research.
- **Q4** — inside compound subfolders (References / Financials / Legal / Docs / Film Coverage), the leaf-type question selects the specific child.

If at any level the on-disk rules don't match but the templates file shows the matched signal corresponds to a valid child for this parent type, **propose the new subfolder and queue a rule addition** (lazy-growth learning loop).

Fall through to `references/tidy-builtin-categories.json` only when no Q*n* match is found anywhere — Pictures, Finance, Government, Health, Career, etc. give a domain hint that can re-enter the cascade at the right level.

If still no match, `_Inbox/` at the current level with `?`. Don't invent new subfolder names.

---

## External folders

Folders owned by someone else — never touch:

- The folder contains a `.tidy-rules.json` with the top-level field `"external": true`. Example: `logseq-journals/.tidy-rules.json` declares `external: true` because the folder is a shared Logseq journal owned by someone else.
- The backend's `_is_external()` check makes scan skip these folders entirely — files inside never enter the registry. Propose never targets these folders either.

When the user says a folder is "shared from someone else" or "don't touch", create a `.tidy-rules.json` inside it with:
```json
{
  "external": true,
  "note": "Why this folder is external — who owns it, what it holds",
  "rules": []
}
```
Then add a corresponding root `.tidy-rules.json` entry noting it's external (so other Claude sessions don't try to re-process it).

---

## Atomic-unit folders

Folders where the folder IS the unit. Before classifying any individual file, check whether the file's parent (or ancestor) folder is an atomic unit. If it is, **propose moving the whole folder as one entity**, not each file. Per-file moves would shatter datasets that only make sense as a tree.

| Pattern | Marker / structure | Atomic destination |
|---|---|---|
| **Python virtual environment** | folder contains `pyvenv.cfg` at root, or `lib/pythonX.Y/site-packages/` | Recommend delete (venvs are recreatable from `requirements.txt`); else route the whole venv folder to `_Inbox/` for review |
| **OSCAR / CPAP data backup** | folder structure `Profiles/<name>/ResMed_<serial>/Backup/DATALOG/YYYY/` with `.edf` + `.crc` files | Whole `OSCAR_Data/` tree → `PERSONAL/PERSONAL Medical/<Person>/CPAP Data/` — preserve every subfolder, do not re-bucket the files |
| **Zotero data folder** | contains `zotero.sqlite` or `storage/` with `.zotero-ft-cache` files | Whole folder → `EDUCATION/EDUCATION Research/Zotero/` — keep its internal structure intact |
| **Unity / Unreal game project** | contains `Assets/`, `ProjectSettings/`, or any `.unity`/`.uproject` file | Whole project folder → `Archive/Old Projects/<Game Name>/` |
| **node_modules** | folder named exactly `node_modules` | Delete or `_Inbox/` — never organise individually |
| **macOS application bundle** | folder name ending `.app`, `.framework`, `.bundle`, `.photoslibrary`, `.imovielibrary`, `.musiclibrary` | These are technically single files even though Finder shows them as folders; route by filename like any other file (or `_Inbox/` if loose) |
| **iCloud / Time Machine snapshot** | folders named `Time Machine Backups`, `Backups.backupdb`, `.MobileBackups` | `_Inbox/` — the user inspects before any move |
| **Software / installer bundle** | contains `__MACOSX/`, `Contents/MacOS/`, or has `.framework`/`.dylib` files | `_Inbox/` |

Detection happens at the parent-folder level — when scanning files in a folder, check if the folder matches an atomic pattern before processing any individual file. If it does, generate a single proposal entry for the whole folder. The viewer treats it as one row even though it represents many files.

If a file's grandparent is the atomic root (e.g. a single `.edf` deep inside `OSCAR_Data/.../DATALOG/2024/`), still route it as part of the atomic unit — only the root folder appears as a proposal, all children follow.

---

## Scientific / medical time-series data

Extensions: `.edf` European Data Format, `.crc` checksum sidecar, `.000`/`.001` OSCAR summary, `.mat` MATLAB, `.npy` NumPy, `.edn` Clojure data, `.f`/`.f90` Fortran source, `.h` C header.

Almost always part of an atomic-unit folder (see above). If you see these files loose (no atomic parent), check the path — they're usually from a research / medical / academic source. Route to `EDUCATION/EDUCATION Research/<Topic>/Data/` if research-tied, or `PERSONAL/PERSONAL Medical/<Person>/` if medical. Never propose per-file moves for these — they're rarely meaningful alone.

---

## Legacy / dead-format media

Extensions: `.swf` Flash, `.fla` Flash source, `.dxr` Director, `.au` Sun audio, `.x32` various, `.asp` classic ASP, `.wma` Windows Media Audio.

These are formats from obsolete software (Flash retired 2020, Director retired 2017). Process:
1. If inside an atomic-unit "Old Projects" folder, route the whole folder.
2. If loose, `_Inbox/` with a `?` — most of these are unreadable on modern machines and worth deleting after review.

---

## Config / system / log files

Extensions: `.plist` Apple preferences, `.ini` config, `.log` log, `.json`/`.xml` data, `.url`/`.webloc` shortcuts, `.sample` git pack samples.

- `.plist`, `.ini`, `.log`: app/system files that rarely belong in OneDrive. `_Inbox/` with a `?`.
- `.json`/`.xml`: data files. If inside a project folder, route to that project's `Docs/` or `References/`. If standalone with no context, `_Inbox/`.
- `.url`/`.webloc`: see "Web links and snippets" below.
- `.sample`: typically git pack sample files; part of a `.git/` directory which is hidden and skipped anyway. If they surface, `_Inbox/`.

---

## Spreadsheets and Presentations

Spreadsheet extensions: `.xlsx`, `.xls`, `.csv`, `.tsv`, `.ods`. Presentation extensions: `.pptx`, `.ppt`, `.key`, `.odp`.

Treat exactly like Documents — apply the cascading-Q model. The backend extracts `content_peek` from cells and slide text for `.xlsx`/`.pptx`. Per-folder rules typically route spreadsheets to `Scene Breakdown/`, `Financials/Bills/`, or `Docs/` depending on signals (e.g. "scene 1, scene 2…" rows → Scene Breakdown; "invoice amount, GST" → Financials/Bills; cast list → Docs). Presentations usually go to `<Project>/Docs/` (pitches, decks) or `<Project>/References/` (mood decks). Templates (`.pptx` with "template" in name or already in a Templates folder) → see Templates section below.

---

## Audio

Extensions: `.mp3`, `.m4a`, `.m4b`, `.flac`, `.aac`, `.aif`, `.aiff`, `.wav`, `.ogg`, `.opus`, `.wma`.

**`content_peek` IS populated for audio** — the backend uses `mutagen` to extract embedded metadata (ID3 for mp3, MP4 atoms for m4a/m4b/aac, Vorbis Comment for flac/ogg/opus, ASF for wma, RIFF/AIFF tags for wav/aiff). When present, it surfaces as a one-line key=value blob:

```
artist=Mohd. Rafi | album=Junglee | title=Ehsan Tera Hoga Mujhpar | date=1969 | tracknumber=3/0 | genre=Film | length=206s
```

If `mutagen` is not installed (`pip3 install --user --break-system-packages mutagen` on macOS PEP-668 systems) the backend returns `None` and audio falls back to filename + parent-folder classification. Either way the cascade still works.

**Classify with metadata + filename + parent folder together:**

1. **Embedded metadata identifies album/film soundtrack** (`album=Junglee`, `date=1969`) → `ENTERTAINMENT/ENTERTAINMENT Music/(1969) Junglee/`. Filename: `Junglee - Ehsan Tera Hoga Mujhpar - Mohd. Rafi.mp3` (use `album - title - artist` reconstructed from metadata if the existing filename is messier).
2. **Metadata is sparse** (only title, no album) → look at filename and parent folder for the album/film name. If parent folder is `(YYYY) AlbumName/`, route there.
3. **`length` < ~60s** + filename like `Scene_3_take_2.m4a` + parent is a project → `<Project>/References/` (production voice memo / take).
4. **No metadata, no project signal, no clear music name** → `_Inbox/` for review.

**Conflicts between filename and metadata**: trust metadata when it's complete (artist + album + title all present), but check for nonsense — some files have placeholder metadata (e.g. `artist=Mere Yaar Ki Shaadi Hai` is the album name in the artist field; `album=YRF Top 50` is a compilation hint, not the source film). Use filename to disambiguate when metadata smells wrong.

**Audiobooks** (`.m4b`, occasionally `.m4a` or `.mp3` collections): metadata may have a `book` or chapter tag. Route to `ENTERTAINMENT/ENTERTAINMENT Books and Audiobooks/<Series Title>/`.

---

## Video

Extensions: `.mov`, `.mp4`, `.mkv`, `.avi`, `.m4v`, `.wmv`, `.flv`, `.3gp`, `.mxf` broadcast.

No `content_peek` — classify by filename + parent folder.
1. Parent folder is a project + filename suggests reference/shoot (`look_test_zara.mov`, `scene_5_blocking.mp4`) → `<Project>/References/`.
2. Parent folder is a `PERSONAL Photos/<event>/` or filename has personal date+subject → `PERSONAL/PERSONAL Photos/<event>/` (preserve event folder).
3. Screen recordings (filename has "screencast" / "screen recording" / "cleanshot") → `_Inbox/` — video screen recordings are rarely worth organising; flag for review.
4. Movies / TV → `ENTERTAINMENT/ENTERTAINMENT Movies and TV Shows/<Title>/`. Music videos → `ENTERTAINMENT/ENTERTAINMENT Music/(YYYY) AlbumName/`.
5. No signal → `_Inbox/`.

---

## Design source files

Extensions: `.psd`, `.ai`, `.afdesign`, `.afphoto`, `.indd`, `.idml`, `.idlk`, `.cdr`, `.eps`, `.svg`, `.sketch`, `.procreate`.

The InDesign trio is grouped: `.indd` is the file, `.idml` is its exchange format, `.idlk` is the lock file — keep all three together when routing (same destination). Procreate files are iPad illustrations; route like .psd.

These are the user's working design files (Affinity Designer, Photoshop, Illustrator, etc.) — never auto-classify by content. Classify by filename + parent folder:
1. Parent folder is a project → `<Project>/Branding Materials/` (logos, banners, marketing) or `<Project>/References/` (mood boards, costume design source).
2. Filename clearly names a company logo (`[Client] logo final.afdesign`, `[COMPANY] letterhead.psd`) → that company's `Branding Materials/` folder (e.g. `WORK/[COMPANY]/[COMPANY] Admin/Branding Materials/` or `WORK/[COMPANY]/[COMPANY] [Client]/Branding Materials/`).
3. Generic templates (filename has "template", "blank", "master") → `RESOURCES/RESOURCES Templates/`.
4. No project/company signal → `_Inbox/` — design source files are too valuable to bury.

---

## Templates and Fonts

Template extensions: `.dotx`, `.xltx`, `.potx`, `.dotm`. Font extensions: `.ttf`, `.otf`, `.ttc`, `.woff`, `.woff2`.

- Templates: filename usually has company or document type. Company signal → `WORK/<Company>/<Company> Admin/Templates/`. Generic blank → `RESOURCES/RESOURCES Templates/`. Skip `content_peek` — these are blank shells.
- Fonts: route directly to `RESOURCES/RESOURCES Fonts/`. No filename analysis needed — the file is the asset. Filename slug = font family name (e.g. `Helvetica_Neue_Bold.ttf`).

---

## Archives

Extensions: `.zip`, `.rar`, `.7z`, `.tar`, `.gz`, `.bz2`.

The backend peeks the file listing for `.zip` only — other archive formats have no peek. Process:
1. Filename names a project asset bundle (`[Client] logo final.zip`, `[COMPANY]_promotional_material.zip`) → route to that project's `References/` or `Branding Materials/`.
2. Zip file listing (when available in `content_peek`) confirms project content → route accordingly.
3. Generic backup / unclear contents → `_Inbox/` — let the user inspect before any routing. Never extract automatically.

---

## eBooks

Extensions: `.epub`, `.azw`, `.azw3`, `.mobi`, `.djvu`.

No `content_peek` for these formats. Classify by filename (book title is usually clear):
1. Fiction / casual reading → `ENTERTAINMENT/ENTERTAINMENT Books and Audiobooks/<Series Title>/`.
2. Academic, theoretical, research-relevant (title mentions "theory", "studies", author is academic) → `EDUCATION/EDUCATION Research/Academic Papers/` or a more specific `EDUCATION/EDUCATION Research/<Topic>/` folder if one matches.
3. Unclear → `_Inbox/`.

---

## Web links and snippets

Extensions: `.url`, `.webloc`, `.html`, `.htm`.

- `.html` / `.htm`: usually saved web pages or article exports. Backend extracts text via `_peek_text`. Treat like Documents — project ID via content/filename, route to `EDUCATION/EDUCATION Research/Film Coverage/<Film Title>/` for press about a film, `EDUCATION/EDUCATION Research/Notes/` for general saves, or `<Project>/References/` if project-tied.
- `.url` / `.webloc`: a one-line pointer to a URL. No real text. Route to `_Inbox/` for review — these are rarely worth organising automatically.

---

## Markdown

Extension: `.md`. Backend extracts text. Two common cases:

1. **Notion exports** (filename has hex UUID suffix like `[Person Name] bb50f7290c35822fa15d815349a4ef8a.md`) — these are Notion task/note exports. Route via project signal in filename (e.g. `[COMPANY] Co-ordinate work with [Person]` → `WORK/[COMPANY]/[COMPANY] Admin/Tasks from Notion export/`) or `PERSONAL/PERSONAL Admin/<Person>/Tasks from Notion export/`.
2. **Other markdown** — treat as Documents (project ID via content_peek, then route).
3. Skill files / code-adjacent `.md` (filename ends in `SKILL.md`, content looks like a skill prompt) → `_Inbox/` — these shouldn't be in OneDrive.

---

## Code and config

Extensions: **code** — `.py`, `.js`, `.ts`, `.env`, `.gitignore`, `.go`; **data/config** — `.json`, `.yaml`, `.yml`, `.xml`.

**Code** files always route to `_Inbox/` with a `?` flag noting "code file — shouldn't be in OneDrive; confirm before routing". Never silently route to a project folder.

**Precedence for `.json`/`.yaml`/`.yml`/`.xml` (data/config, not code):** these are governed by the data-file rule above — *if inside a project folder, route to that project's `Docs/` or `References/`; if standalone with no context, `_Inbox/`*. They are listed here only to note they are NOT treated as code. So a `config.json` inside a project follows the project (Docs/References); a loose `.json` at the root goes to `_Inbox/`. Pure code (`.py`/`.js`/`.ts`/`.go`) is always `_Inbox/` regardless of location.

---

## Installers and executables

Extensions: `.dmg`, `.exe`, `.pkg`, `.app`, `.deb`.

Always route to `_Inbox/` with a `?` flag noting "installer — review and consider deleting; shouldn't live in OneDrive".

---

## Sidecar files

Extensions: `.srt` subtitles, `.pfl` Premiere Pro waveforms, `.xmp` metadata sidecars, `.thm` thumbnails.

Sidecars belong with their parent file — they encode metadata or auxiliary data tied to a specific media file. Process:
1. Look for the parent file in the same folder (e.g. `clip.mp4.pfl` parents to `clip.mp4`; `movie.srt` parents to `movie.mp4`/`movie.mkv` by basename match).
2. If the parent exists and has been classified, route the sidecar to the **same destination** as the parent.
3. If the parent doesn't exist (orphan sidecar), route to `_Inbox/` and flag — the sidecar is meaningless without its parent.
4. Never propose a sidecar as a separate filename; preserve the original filename so it still parents to the media file after the move.

---

## Lock files

Extensions: `.afdesign~lock~`, `.psd.lock`, `~$*.docx`, `~$*.xlsx`, `.~lock.*#`.

Application lock files from editing sessions that ended without closing the app. Always safe to delete — they have no content of their own. Process: delete immediately, no proposal needed. If found inside a project folder, deleting is the right action regardless of project.

---

## OneDrive conflict-suffixed extensions

Patterns: `.jpg-April`, `.mp4-april`, `.srt-april`, etc. — any extension ending in `-<month>` or `-<date>`.

OneDrive's sync conflict resolution sometimes appends a date suffix to the file extension. The clean version of the file is the one without the suffix. Process:
1. Strip the conflict suffix to get the canonical extension.
2. If the canonical name doesn't exist in the same folder, just rename (e.g. `foo.jpg-April` → `foo.jpg`).
3. If the canonical name already exists, the suffixed version is a duplicate from the conflict — rename to `<stem> (<month>-conflict).<ext>` and let the `duplicates` command resolve later.

---

## Compound corruption

Filenames with embedded artist/cast credits inside the extension chain, e.g. `Episode 1. badri chavan, farzeen ali.mp4-april`.

Same as conflict-suffixed — strip the trailing `-<month>` and treat the result as the real filename. The dot-separated credits embedded mid-name aren't a real extension boundary; just the final `.mp4-april` is. Don't try to parse the credits out — leave them in the stem.

---

## Legacy / obscure formats

Extensions: `.dxr`, `.cxt` Adobe Director; `.swf`, `.fla` Flash; `.pfm`, `.pfb` PostScript fonts; `.physicmaterial`, `.prefab`, `.unity` Unity game engine; `.inf` Windows installer info; `.au` Sun audio.

These are project-internal files for obsolete or specialized software. **The file type itself doesn't determine routing** — these files are almost always part of an atomic-unit folder (Unity project, Director bundle, archived software dump). If the file appears loose at root, route to `_Inbox/`. **Path takes precedence over file type**: if the parent folder is marked `external: true`, the folder rule wins and the file is never touched, regardless of its extension.

---

## Procreate

Extension: `.procreate`. Valid iPad illustration file. Treat like design source files — route to project's `References/` or `Branding Materials/` based on parent folder, or `_Inbox/` if loose.
