#!/usr/bin/env python3
"""Read-only audit of a dual-format Logseq/Obsidian graph.

Usage:
  graph_audit.py PAGES_DIR [--schema SCHEMA.json] [--relations RELATIONS.json]
                 [--checks properties,format,links,mentions,relations,placeholders,stale]  (default: all but stale)
                 [--stale-days N] [--today YYYY-MM-DD] [--only-pages NAME[,NAME...]]
                 [--exclude NAME[,NAME...]] [--json]

Never writes, renames or deletes anything: it only reads the pages and prints a report.
Every finding names the page and line. Fixes are proposed by the caller and confirmed
one at a time; this script has no fix mode.

Checks:
  properties    missing type::, type/writer/status vocab, required properties per type, Zotero-only
                properties, blank title::, writer:: on templates, writer:: Claude on notes
  format        YAML frontmatter, markdown # headings, [ ] checkboxes, image embeds,
                URL as a property value
  links         bracket rule for link-type properties, dead-end links (cited, no page),
                duplicate titles/aliases, self-alias, orphans, hubs
  mentions      page titles, filenames and aliases mentioned in other pages without a link
  relations     links under Connections that lack a relation verb from the vocabulary
                or a one-line reason after a colon
  placeholders  leftover template text (<angle placeholders>, the unfilled {{title}}, {{date}}, {{citekey}},
                {{module}} and {{name}} variables, TBD / FILL IN / INSERT HERE / PLACEHOLDER wording,
                blank writer::)
  stale         pages whose verified:: date is older than --stale-days (default 180)

Exit codes: 0 no findings, 1 findings reported, 2 bad input.
"""
import argparse
import datetime
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))   # also runs under python3 -I, which leaves the script folder off the path
from _common import FENCE_OPEN_RE

ALL_CHECKS = ["properties", "format", "links", "mentions", "relations", "placeholders", "stale"]
# stale verified:: dates run only when asked for (--checks stale), never in the default or weekly run
DEFAULT_CHECKS = [c for c in ALL_CHECKS if c != "stale"]
PROP_RE = re.compile(r"^\s*(?:-\s+)?([A-Za-z][\w.\-]*)::\s?(.*)$")
LINK_RE = re.compile(r"\[\[([^\[\]]+?)\]\]")
URL_RE = re.compile(r"https?://", re.I)
MIN_MENTION_LEN = 5
HUB_TOP = 10
# App and plugin folders, never graph pages (same list as graph-link-audit.py); hidden folders are skipped too.
SKIP_DIRS = {"assets", "copilot", "logseq", "bak"}


def split_values(s):
    """Split a comma-separated property value, ignoring commas inside [[...]] (as graph-link-audit.py does)."""
    out, buf, depth, i = [], "", 0, 0
    while i < len(s):
        two = s[i:i + 2]
        if two == "[[":
            depth += 1; buf += two; i += 2; continue
        if two == "]]" and depth:
            depth -= 1; buf += two; i += 2; continue
        if s[i] == "," and depth == 0:
            out.append(buf); buf = ""
        else:
            buf += s[i]
        i += 1
    out.append(buf)
    return [v.strip() for v in out if v.strip()]


class Page:
    def __init__(self, path, root=None):
        self.path = path
        self.name = path.stem
        self.lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        self.props = []  # (key, value, lineno) from the first block
        self._read_props()
        self.title = self.name
        self.aliases = []
        for k, v, _ in self.props:
            if k == "title" and v.strip():
                self.title = v.strip().strip('"')
            if k == "alias":
                self.aliases += [a.strip().strip("[]") for a in split_values(v) if a.strip()]   # same reading as graph-link-audit.py
        # judge the folders below the pages root only, never the folders above it
        below_root = path.relative_to(root).parts if root else path.parts
        self.is_template = "Templates" in below_root or self.name.endswith(" Template")

    def _read_props(self):
        for i, line in enumerate(self.lines, 1):
            m = PROP_RE.match(line)
            if m:
                self.props.append((m.group(1).lower(), m.group(2).strip(), i))
            elif line.strip() == "" and not self.props:
                continue
            else:
                break

    def prop(self, key):
        for k, v, ln in self.props:
            if k == key:
                return v, ln
        return None, None

    def types(self):
        v, _ = self.prop("type")
        return [t.strip() for t in v.split(",") if t.strip()] if v else []


def load_pages(pages_dir, exclude):
    pages = []
    root = Path(pages_dir)
    for p in sorted(root.rglob("*.md")):
        rel_dirs = p.relative_to(root).parts[:-1]
        if any(d.startswith(".") or d in SKIP_DIRS for d in rel_dirs):
            continue
        if p.stem.lower() in exclude:
            continue
        pages.append(Page(p, root))
    return pages


def link_target(raw):
    return raw.split("|")[0].split("#")[0].strip()


def build_index(pages):
    idx = defaultdict(list)
    for pg in pages:
        for n in [pg.name, pg.title] + pg.aliases:
            if pg not in idx[n.lower()]:     # a page whose title equals its name is indexed once
                idx[n.lower()].append(pg)
    return idx


def find(pg, ln, code, sev, msg):
    return {"page": pg.name, "line": ln, "code": code, "severity": sev, "message": msg}


def check_properties(pages, schema):
    out = []
    if not schema:
        return out
    tv = set(schema.get("type_vocab", []))
    wv = set(schema.get("writer_vocab_plain", []))
    sv = set(schema.get("status_vocab", []))
    zo = set(schema.get("zotero_only_properties", []))
    req = schema.get("required_properties", {})
    for pg in pages:
        keys = {k for k, _, _ in pg.props}
        for k, v, ln in pg.props:
            if k == "title" and not v and not pg.is_template:   # a template keeps its blank lines, as graph-link-audit.py does
                out.append(find(pg, ln, "blank-title", "error", "title:: is present but blank; delete the line (a blank title collides with other blank titles)"))
            if k == "type" and v:
                for t in [x.strip() for x in v.split(",") if x.strip()]:
                    if t not in tv:
                        out.append(find(pg, ln, "type-vocab", "warn", f"type '{t}' is not in the type vocabulary"))
            if k == "writer" and v:
                for raw_w in [x.strip() for x in split_values(v) if x.strip()]:
                    w = raw_w.strip("[]")
                    if w not in wv and not (raw_w.startswith("[[") and w):   # each part judged alone, as schema-lint.py does
                        out.append(find(pg, ln, "writer-vocab", "warn", f"writer '{w}' is not in the writer vocabulary"))
            if k == "status" and v and v not in sv:
                out.append(find(pg, ln, "status-vocab", "warn", f"status '{v}' is not a task keyword"))
            if k in zo and "Reading Notes" not in pg.types() and "Primary Source" not in pg.types():
                out.append(find(pg, ln, "zotero-only-property", "info", f"'{k}::' is reserved for Zotero-generated pages; confirm this page came from Zotero"))
        if not pg.is_template and "type" not in keys:
            out.append(find(pg, 1, "missing-type", "error", "page has no type:: property"))
        if not pg.is_template:
            for t in pg.types():
                missing = [r for r in req.get(t, []) if r not in keys]
                if missing:
                    out.append(find(pg, 1, "required-properties", "error", f"type {t} requires {', '.join(missing)}"))
        wval, wln = pg.prop("writer")
        if pg.is_template and wval:
            out.append(find(pg, wln, "template-writer", "error", f"template carries writer:: {wval}; templates keep writer:: blank"))
        if wval and wval.strip().strip("[]") == "Claude" and not pg.is_template and any(t in ("Note", "Reading Notes") for t in pg.types()):
            out.append(find(pg, wln, "claude-on-notes", "info", "writer:: Claude on a notes page; confirm Claude wrote it (never on the user's own notes)"))
    return out


def check_format(pages):
    out = []
    for pg in pages:
        if pg.lines and pg.lines[0].strip() == "---":
            out.append(find(pg, 1, "yaml-frontmatter", "error", "YAML frontmatter; page metadata is property:: lines"))
        in_fence = False
        for i, line in enumerate(pg.lines, 1):
            if FENCE_OPEN_RE.match(line):   # a Logseq bullet may carry the fence: "- ```"
                in_fence = not in_fence
            if in_fence:
                continue
            if re.match(r"^\s*(?:-\s+)?#{1,6}\s+\S", line):
                out.append(find(pg, i, "md-heading", "warn", "markdown # heading; use a bullet with heading:: true on a child line"))
            if re.match(r"^\s*-\s+\[[ xX]\]\s", line):
                out.append(find(pg, i, "checkbox", "warn", "checkbox task; use TODO/DOING/DONE/WAITING/CANCELLED"))
            code_free = re.sub(r"`[^`]*`", lambda mc: "`" * len(mc.group(0)), line)   # an example in a code span is not an embed
            if re.search(r"!\[[^\]]*\]\([^)]+\)", code_free):
                out.append(find(pg, i, "image-embed", "warn", "markdown image embed; keep asset references as plain text"))
            m = PROP_RE.match(line)
            if m and URL_RE.search(re.sub(r"`[^`]*`", "", m.group(2))):
                out.append(find(pg, i, "url-property", "warn", f"URL as a property value on '{m.group(1)}::'; put the URL in body text"))
    return out


LINK_PROPS = {"related", "project", "lens", "period", "thread"}


def code_free_lines(lines):
    """The lines with fenced code dropped and inline code blanked, so a link shown as an example is not a link."""
    out, in_fence = [], False
    for line in lines:
        if FENCE_OPEN_RE.match(line):
            in_fence = not in_fence
            continue
        if not in_fence:
            out.append(re.sub(r"`[^`]*`", lambda mc: "`" * len(mc.group(0)), line))
    return out


def check_links(pages, idx, schema, files=()):
    out = []
    lp = set(schema.get("link_type_properties", LINK_PROPS)) if schema else LINK_PROPS
    inbound = defaultdict(int)
    names_seen = defaultdict(list)
    for pg in pages:
        for n, kind in [(pg.name, "filename")] + [(pg.title, "title")] * (pg.title != pg.name) + [(a, "alias") for a in pg.aliases]:
            names_seen[n.lower()].append((pg, kind))
        for a in pg.aliases:
            if a.lower() in (pg.name.lower(), pg.title.lower()):
                ln = pg.prop("alias")[1]
                out.append(find(pg, ln, "self-alias", "warn", f"alias '{a}' repeats the page's own name"))
    for key, hits in names_seen.items():
        owners = {id(h[0]) for h in hits}
        if len(owners) > 1:
            first = hits[0][0]
            others = sorted({h[0].name for h in hits[1:] if h[0] is not first})
            out.append(find(first, 1, "name-collision", "error", f"'{key}' is also a title, filename or alias of: {', '.join(others)}"))
    dead = defaultdict(list)
    for pg in pages:
        in_fence = False
        for i, line in enumerate(pg.lines, 1):
            if FENCE_OPEN_RE.match(line):   # links inside fenced code are examples, as in graph-link-audit.py
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            m = PROP_RE.match(line) if i <= (pg.props[-1][2] if pg.props else 0) else None
            prop_key = m.group(1).lower() if m else None
            for lm in LINK_RE.finditer(re.sub(r"`[^`]*`", lambda mc: "`" * len(mc.group(0)), line)):
                target = link_target(lm.group(1))
                # same exemptions as graph-link-audit.py: a same-page [[#Heading]], a URL, a namespaced "/"
                # link and an attachment name are not page links
                if target == "" or target.startswith("http") or "/" in target or target.lower() in files:
                    continue
                hits = idx.get(target.lower())
                if hits:
                    for h in hits:
                        if h is not pg:
                            inbound[id(h)] += 1
                elif not pg.is_template:   # a template's links are placeholders, not links to missing pages
                    if prop_key in lp:
                        out.append(find(pg, i, "bracketed-missing", "error", f"[[{target}]] in {prop_key}:: has no page; unbracket it so no phantom page is created"))
                    else:
                        dead[target.lower()].append((pg, i, target))
            if prop_key in lp and m:
                for part in [p.strip() for p in m.group(2).split(",") if p.strip()]:
                    if "[[" not in part and idx.get(part.lower()):
                        out.append(find(pg, i, "plain-existing", "info", f"'{part}' in {prop_key}:: names an existing page; link values are bracketed when the target exists"))
    for key, refs in dead.items():
        pg, ln, target = refs[0]
        out.append(find(pg, ln, "dead-end-link", "warn", f"[[{target}]] is cited {len(refs)} time(s) in {len({r[0].name for r in refs})} page(s) but never defined"))
    for pg in pages:
        if pg.is_template:
            continue
        if inbound[id(pg)] == 0:
            out.append(find(pg, 1, "orphan", "info", "no page links to this page"))
    hubs = sorted(pages, key=lambda p: -inbound[id(p)])[:HUB_TOP]
    hubs = [h for h in hubs if inbound[id(h)] > 0]
    return out, [(h.name, inbound[id(h)]) for h in hubs]


def check_mentions(pages):
    out = []
    targets = []
    for pg in pages:
        for n in {pg.title, pg.name} | set(pg.aliases):
            if len(n) >= MIN_MENTION_LEN:
                targets.append((n, pg))
    for n, tgt in targets:
        rx = re.compile(r"(?<![\w\[])" + re.escape(n) + r"(?![\w\]])", re.I)
        for pg in pages:
            if pg is tgt or pg.is_template:
                continue
            count, first = 0, None
            linked_here = any(link_target(m.group(1)).lower() in {x.lower() for x in [tgt.name, tgt.title] + tgt.aliases}
                              for line in code_free_lines(pg.lines) for m in LINK_RE.finditer(line))
            if linked_here:
                continue
            for i, line in enumerate(pg.lines, 1):
                if PROP_RE.match(line) and i <= (pg.props[-1][2] if pg.props else 0):
                    continue
                stripped = LINK_RE.sub(" ", line)
                if rx.search(stripped):
                    count += 1
                    first = first or i
            if count:
                out.append(find(pg, first, "unlinked-mention", "info", f"mentions '{n}' ({count} line(s)) without linking [[{tgt.name}]]; a candidate only, check the sense"))
    seen, dedup = set(), []
    for f in out:
        key = (f["page"], f["code"], f["message"], f["line"])   # identical findings only
        if key not in seen:
            seen.add(key)
            dedup.append(f)
    return dedup


def check_relations(pages, relations):
    out = []
    verbs = sorted((v.lower() for v in relations.get("verbs", [])), key=len, reverse=True)   # compared with the lowercased line
    heads = [h.lower() for h in relations.get("connections_headings", ["Connections"])]
    for pg in pages:
        if pg.is_template:
            continue
        in_conn, depth = False, 0
        for i, line in enumerate(pg.lines, 1):
            text = re.sub(r"^\s*-\s*", "", line).strip()
            indent = len(line) - len(line.lstrip("\t "))
            if text.lower() in heads:
                in_conn, depth = True, indent
                continue
            if in_conn:
                if text and indent <= depth and not PROP_RE.match(line):
                    in_conn = False
                    continue
                if LINK_RE.search(text) and not PROP_RE.match(line):
                    low = text.lower()
                    if not any(low.startswith(v + " ") for v in verbs):
                        out.append(find(pg, i, "relation-missing", "warn", "link under Connections has no relation verb first; start with one of: " + "; ".join(verbs)))
                    elif ":" not in text[LINK_RE.search(text).end():]:   # the reason follows the link
                        out.append(find(pg, i, "relation-no-reason", "info", "relation has no one-line reason after a colon"))
    return out


PLACEHOLDER_RES = [
    (re.compile(r"<[A-Za-z][A-Za-z0-9 _/\-]{1,40}>"), "angle-bracket placeholder"),
    (re.compile(r"\{\{\s*(?:title|date|citekey|module|name)\s*\}\}", re.I), "unfilled template variable"),
    (re.compile(r"\b(?:TBD|FILL IN|INSERT HERE|PLACEHOLDER)\b"), "placeholder wording"),
]


def check_placeholders(pages):
    out = []
    for pg in pages:
        if pg.is_template:
            continue
        in_fence = False
        for i, line in enumerate(pg.lines, 1):
            if FENCE_OPEN_RE.match(line):   # a Logseq bullet may carry the fence: "- ```"
                in_fence = not in_fence
            if in_fence:
                continue
            visible = re.sub(r"`[^`]*`", lambda mc: "`" * len(mc.group(0)), line)   # placeholder wording shown in a code span is an example
            for rx, label in PLACEHOLDER_RES:
                # a line with an HTML tag is exempt from the angle-bracket pattern only
                html_line = label == "angle-bracket placeholder" and re.search(r"<(?:br|hr|sup|sub|a|em|strong|code|p|ul|li)\b", visible, re.I)
                if rx.search(visible) and not html_line:
                    out.append(find(pg, i, "placeholder", "warn", f"leftover {label}: {rx.search(visible).group(0)!r}"))
                    break
        for k, v, ln in pg.props:
            if k == "writer" and not v:
                out.append(find(pg, ln, "blank-writer", "warn", "writer:: is blank on a page made from a template; fill in who wrote it"))
    return out


def check_stale(pages, days, today):
    out = []
    for pg in pages:
        v, ln = pg.prop("verified")
        if not v:
            continue
        try:
            d = datetime.date.fromisoformat(v.strip().strip("[]")[:10])
        except ValueError:
            out.append(find(pg, ln, "verified-date", "warn", f"verified:: '{v}' is not an ISO date"))
            continue
        age = (today - d).days
        if age > days:
            out.append(find(pg, ln, "stale", "info", f"verified {v} is {age} days old (limit {days})"))
    return out


def attachment_names(pages_dir):
    """Lower-case file names under the pages folder and the graph's assets folder (attachments)."""
    root = Path(pages_dir)
    names = {p.name.lower() for p in root.rglob("*") if p.is_file()}
    assets = root.resolve().parent / "assets"
    if root.resolve().name == "pages" and assets.is_dir():     # a flat vault has no sibling assets folder of its own
        names |= {p.name.lower() for p in assets.rglob("*") if p.is_file()}
    return names


def run(pages_dir, schema, relations, checks, stale_days, today, only=None, exclude=()):
    skip = {e.lower() for e in exclude}
    all_pages = load_pages(pages_dir, set())
    pages = [p for p in all_pages if p.name.lower() not in skip]   # excluded pages get no findings ...
    idx = build_index(all_pages)                                   # ... but still count as link targets
    findings, hubs = [], []
    if "properties" in checks:
        findings += check_properties(pages, schema)
    if "format" in checks:
        findings += check_format(pages)
    if "links" in checks:
        f, hubs = check_links(pages, idx, schema, attachment_names(pages_dir))
        findings += f
    if "mentions" in checks:
        findings += check_mentions(pages)
    if "relations" in checks:
        findings += check_relations(pages, relations)
    if "placeholders" in checks:
        findings += check_placeholders(pages)
    if "stale" in checks:
        findings += check_stale(pages, stale_days, today)
    if only:
        keep = {o.lower() for o in only}
        findings = [f for f in findings if f["page"].lower() in keep]
    order = {"error": 0, "warn": 1, "info": 2}
    findings.sort(key=lambda f: (order[f["severity"]], f["page"].lower(), f["line"] or 0, f["code"]))
    return {"pages": len(pages), "findings": findings, "hubs": hubs}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pages_dir")
    ap.add_argument("--schema")
    ap.add_argument("--relations")
    ap.add_argument("--checks", default=",".join(DEFAULT_CHECKS))
    ap.add_argument("--stale-days", type=int, default=180)
    ap.add_argument("--today")
    ap.add_argument("--only-pages")
    ap.add_argument("--exclude", default="")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if not Path(a.pages_dir).is_dir():
        print(f"error: {a.pages_dir} is not a directory", file=sys.stderr)
        return 2
    checks = [c.strip() for c in a.checks.split(",") if c.strip()]
    bad = [c for c in checks if c not in ALL_CHECKS]
    if bad:
        print(f"error: unknown check(s): {', '.join(bad)}", file=sys.stderr)
        return 2
    try:
        schema = json.loads(Path(a.schema).read_text()) if a.schema else None
        relations = json.loads(Path(a.relations).read_text()) if a.relations else None
        today = datetime.date.fromisoformat(a.today) if a.today else datetime.date.today()
    except (OSError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    skipped = []
    if "properties" in checks and not schema:
        skipped.append("properties (no --schema)")
        checks.remove("properties")
    if "relations" in checks and not relations:
        skipped.append("relations (no --relations)")
        checks.remove("relations")
    res = run(a.pages_dir, schema, relations, checks, a.stale_days, today,
              [x.strip() for x in (a.only_pages or "").split(",") if x.strip()], [x.strip() for x in a.exclude.split(",") if x.strip()])
    res["skipped_checks"] = skipped
    if a.json:
        print(json.dumps(res, indent=2, ensure_ascii=False))
    else:
        print(f"{res['pages']} pages, {len(res['findings'])} findings (read-only; nothing was changed)")
        for s in skipped:
            print(f"skipped: {s}")
        for f in res["findings"]:
            print(f"{f['page']}:{f['line']}: [{f['severity']}] {f['code']}: {f['message']}")
        if res["hubs"]:
            print("hubs (most linked-to): " + "; ".join(f"{n} ({c})" for n, c in res["hubs"]))
    return 1 if res["findings"] else 0


if __name__ == "__main__":
    sys.exit(main())
