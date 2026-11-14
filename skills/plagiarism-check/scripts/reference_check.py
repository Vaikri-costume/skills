#!/usr/bin/env python3
"""reference_check.py - reference-list checks for the reference-check mode.

Subcommands (all print JSON, or a table for `table`; exit 1 with {"error": ...} on bad input):
  parse   <draft>                         reference entries, fields given, fields missing
  cross   <draft>                         in-text citations against the list, document-wide, with near matches
  lookup  <entries.json> [--offline] [--index FILE]
                                          one record per entry from Crossref or OpenAlex
  verdicts <entries.json> <records.json>  field verdicts, outcome per entry, patch log
  table   <verdicts.json>                 the markdown outcome table and the patch log

Only reference strings (title, first author, year, DOI, ISBN) are ever sent to Crossref or OpenAlex,
never draft text, and no personal contact detail goes in the request. `--offline` sends nothing;
`--index FILE` answers from a local JSON file (tests and fixtures) instead of the network.

Outcomes: Clean, Fix, Not found, Review. A missing DOI is never filled in, a not-found entry is
never "fixed", and the script never edits the draft or the list.
"""
import argparse
import difflib
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "shared"))
from citelib import split_body_and_bibliography, find_citations, keys_match  # noqa: E402
from citation_audit import _isbn_ok, audit  # noqa: E402

UA = "reference-check-skill/2.1 (open-source writing checker)"
TIMEOUT = 12
TYPO = 0.85       # title similarity at or above this counts as the same title
DOI_RE = re.compile(r"\b(10\.\d{4,9}/[^\s\"<>]+)", re.I)
ISBN_RE = re.compile(r"ISBN(?:-1[03])?[:\s]*([\dXx][\dXx\- ]{8,16}[\dXx])", re.I)
URL_RE = re.compile(r"https?://[^\s\"<>]+", re.I)
YEAR_RE = re.compile(r"\(?(?<![\w])((?:1[5-9]|20)\d\d[a-z]?|n\.d\.)(?![\w])\)?")
PUBLISHER_RE = re.compile(r"\b(Press|Publishers?|Publishing|Books|University|Verlag|Routledge|Penguin|Sage|Wiley|Blackwell)\b", re.I)
PAGES_RE = re.compile(r"\bpp?\.?\s*(\d+\s*[-–]\s*\d+|\d+)|\b\d+\s*\(\d+\)\s*[,:]?\s*(\d+\s*[-–]\s*\d+)|:\s*(\d+\s*[-–]\s*\d+)")
LOOK_IN = {
    "authors": "the title page or the article's first page",
    "year": "the title page, the copyright page or the article's first page",
    "title": "the title page or the article's first page",
    "venue": "the article's first page or the journal's contents page",
    "publisher": "the title page or its reverse",
    "pages": "the article's first page or the journal's contents page",
    "url": "the page itself",
}
NEEDED = {"article": ["authors", "year", "title", "venue", "pages"],
          "book": ["authors", "year", "title", "publisher"],
          "web": ["authors", "year", "title", "url"],
          "other": ["authors", "year", "title"]}


def fold(s):
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^\w\s]", " ", s.casefold())
    return re.sub(r"\s+", " ", s).strip()


def sim(a, b):
    a, b = fold(a), fold(b)
    return difflib.SequenceMatcher(None, a, b).ratio() if a and b else 0.0


def isbn_digits(s):
    return re.sub(r"[^0-9Xx]", "", s or "").upper()


def split_entries(bib_text):
    out = []
    for chunk in re.split(r"\n\s*\n|\n(?=\s*[-*]\s+\S|\s*[A-Z][\w'’\-]+,\s)", bib_text):
        c = " ".join(re.sub(r"^\s*[-*]\s*", "", chunk).split())
        if len(c) > 12:
            out.append(c)
    return out


def parse_entry(n, raw):
    e = {"n": n, "raw": raw}
    doi = DOI_RE.search(raw)
    e["doi"] = doi.group(1).rstrip(".,;)") if doi else ""
    isbn = ISBN_RE.search(raw)
    e["isbn"] = isbn.group(1).strip() if isbn else ""
    url = URL_RE.search(raw)
    e["url"] = url.group(0).rstrip(".,;)") if url and not (doi and "doi.org" in url.group(0)) else ""
    m = YEAR_RE.search(raw)
    e["year"] = m.group(1) if m else ""
    head = raw[:m.start()] if m else ""
    tail = raw[m.end():] if m else raw
    if not m:
        a = re.match(r"([A-Z][\w'’\-]+,\s*(?:[A-Z]\.\s?)+(?:(?:and|&)\s+[A-Z][\w'’\-]+,\s*(?:[A-Z]\.\s?)+)*)(.*)", raw)
        if a:
            head, tail = a.group(1), a.group(2)
    e["authors"] = head.strip(" .,(")
    e["first_author"] = e["authors"].split(",")[0].strip() if e["authors"] else ""
    tail = tail.lstrip(" .,)(")
    q = re.match(r"""[‘'"“*_]\s*(.+?)\s*[’'"”*_]\s*[,.]?\s*(.*)""", tail)
    if q:
        e["title"], rest = q.group(1).strip(" ."), q.group(2)
    else:
        parts = re.split(r"(?<=[a-z0-9\)])\.\s+", tail, maxsplit=1)
        e["title"] = parts[0].strip(" .")
        rest = parts[1] if len(parts) > 1 else ""
    rest = re.sub(r"\s+", " ", rest)
    pm = PAGES_RE.search(rest)
    e["pages"] = next((g for g in (pm.groups() if pm else []) if g), "").replace(" ", "") if pm else ""
    venue = re.split(r"[,:]|\b\d+\s*\(|\bvol\.|\bpp?\.|https?://|\bdoi\b|\bISBN", rest, maxsplit=1)[0].strip(" .*_")
    pub = PUBLISHER_RE.search(rest)
    if e["isbn"] or (pub and not pm and not e["doi"]):
        e["kind"], e["publisher"], e["venue"] = "book", venue if pub else "", ""
        e["publisher"] = e["publisher"] or (pub.group(0) if pub else "")
    elif e["doi"] or pm or q:
        e["kind"], e["venue"], e["publisher"] = "article", venue, ""
    elif e["url"]:
        e["kind"], e["venue"], e["publisher"] = "web", venue, ""
    else:
        e["kind"], e["venue"], e["publisher"] = "other", venue, ""
    e["fields_given"] = [f for f in ("authors", "year", "title", "venue", "publisher", "pages", "doi", "isbn", "url") if e.get(f)]
    e["fields_missing"] = [{"field": f, "look_in": LOOK_IN[f]} for f in NEEDED[e["kind"]] if not e.get(f)]
    e["artefacts"] = []
    if e["isbn"] and not _isbn_ok(e["isbn"]):
        e["artefacts"].append("ISBN checksum is invalid")
    if e["doi"] and not re.fullmatch(r"10\.\d{4,9}/\S+", e["doi"]):
        e["artefacts"].append("DOI is malformed")
    return e


def parse(text):
    _, bib = split_body_and_bibliography(text)
    if not bib.strip():
        bib = text
    return [parse_entry(i + 1, r) for i, r in enumerate(split_entries(bib))]


def near_surname(a, b):
    return a != b and difflib.SequenceMatcher(None, a, b).ratio() >= 0.8


def cross(text):
    a = audit(text)
    body, bib_text = split_body_and_bibliography(text)
    entries = parse(text) if bib_text.strip() else []
    ents = [{"surname": fold(e["first_author"]), "year": e["year"], "n": e["n"], "raw": e["raw"][:100]} for e in entries]
    near = []
    for u in a["unmatched_citations"]:
        c = (find_citations(u["citation"]) or find_citations("(" + u["citation"] + ")") or [None])[0]
        if not c:
            continue
        hit = None
        for e in ents:
            if e["surname"] == c["surname"] and e["year"] != c["year"]:
                hit = {"why": "same author, different year", "entry": e["n"], "list_year": e["year"]}
            elif e["year"] == c["year"] and near_surname(e["surname"], c["surname"]):
                hit = {"why": "same year, spelling of the author differs", "entry": e["n"], "list_author": e["surname"]}
            if hit:
                break
        near.append(dict(u, near_match=hit))
    return {"in_text_citations": a["citations"], "list_entries": a["bibliography_entries"],
            "unmatched_citations": near, "uncited_list_entries": a["uncited_bibliography"],
            "duplicate_list_entries": a["duplicate_bibliography"], "artefacts": a["artefacts"]}


# ---- lookup -------------------------------------------------------------------------------

def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8"))


def _crossref_item(it, src):
    return {"source": src, "title": (it.get("title") or [""])[0], "year": str(((it.get("issued") or {}).get("date-parts") or [[""]])[0][0] or ""),
            "authors": [a.get("family", "") for a in it.get("author", [])], "venue": (it.get("container-title") or [""])[0],
            "publisher": it.get("publisher", ""), "pages": it.get("page", ""), "doi": it.get("DOI", ""), "type": it.get("type", ""),
            "url": "https://doi.org/" + it["DOI"] if it.get("DOI") else ""}


def _openalex_item(w):
    loc = (w.get("primary_location") or {}).get("source") or {}
    return {"source": "openalex", "title": w.get("display_name") or "", "year": str(w.get("publication_year") or ""),
            "authors": [(a.get("author") or {}).get("display_name", "").split(" ")[-1] for a in w.get("authorships", [])],
            "venue": loc.get("display_name") or "", "publisher": "", "pages": "", "doi": (w.get("doi") or "").replace("https://doi.org/", ""),
            "type": w.get("type", ""), "url": w.get("id", ""), "open_access": (w.get("open_access") or {}).get("oa_url") or ""}


def _score(c, e):
    """Prefer the candidate that agrees with the entry on first author, year and kind, then on title."""
    ra = c.get("authors") or []
    au = 0.5 if ra and e["first_author"] and fold(ra[0]) in fold(e["first_author"]) else 0.0
    yr = 0.2 if c.get("year") == e["year"].rstrip("abcdefghijklmnopqrstuvwxyz") else 0.0
    kd = 0.2 if (e["kind"] == "book") == (c.get("type", "") in ("book", "monograph", "edited-book", "reference-book")) else 0.0
    return sim(c["title"], e["title"]) + au + yr + kd


def lookup_one(e, index=None, offline=False):
    keys = [("doi", e["doi"].lower()), ("isbn", isbn_digits(e["isbn"])), ("title", fold(e["title"]))]
    if index is not None:
        for k, v in keys:
            if v and v in index.get(k, {}):
                return dict(index[k][v], source="index", status="found")
        return {"status": "none", "searched": [k for k, v in keys if v]}
    if offline:
        return {"status": "not looked up"}
    try:
        if e["doi"]:
            try:
                return dict(_crossref_item(_get("https://api.crossref.org/works/" + urllib.parse.quote(e["doi"], safe="/"))["message"], "crossref"), status="found")
            except urllib.error.HTTPError as err:
                if err.code != 404:
                    raise
                return {"status": "none", "searched": ["doi"], "doi_resolves": False}
        cands = []
        if isbn_digits(e["isbn"]) and _isbn_ok(e["isbn"]):
            for it in _get("https://api.crossref.org/works?rows=5&filter=isbn:" + isbn_digits(e["isbn"]))["message"]["items"]:
                if it.get("type", "").startswith("book-") and it.get("type") != "book-series":
                    continue  # chapters, parts and front matter carry the book's ISBN but are not the book
                cands.append(dict(_crossref_item(it, "crossref"), status="found", via="isbn"))
        if e["title"]:
            time.sleep(0.15)
            for w in _get("https://api.openalex.org/works?per-page=10&search=" + urllib.parse.quote(e["title"]))["results"]:
                cands.append(dict(_openalex_item(w), status="found", via="title"))
        good = [c for c in cands if sim(c["title"], e["title"]) >= TYPO]
        if good:
            best = dict(max(good, key=lambda c: _score(c, e)))
            if any(c["via"] == "isbn" for c in cands):
                best["isbn_records"] = [c["title"] for c in cands if c["via"] == "isbn"]
            return best
        isbn_hits = [c for c in cands if c["via"] == "isbn"]
        if isbn_hits:
            return isbn_hits[0]
        return {"status": "none", "searched": [k for k, v in keys if v]}
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, KeyError) as err:
        return {"status": "unreachable", "reason": str(err)[:100]}


# ---- verdicts -----------------------------------------------------------------------------

def field_verdict(given, rec, kind):
    if not given:
        return "ABSENT"
    if not rec:
        return "ABSENT"
    g, r = fold(given), fold(rec)
    if g == r:
        return "MATCH"
    if kind == "title" and (g in r or r in g) and min(len(g), len(r)) >= 12:
        return "CONTAINS"
    if kind == "title" and sim(given, rec) >= TYPO:
        return "TYPO"
    if kind in ("venue",) and (g in r or r in g):
        return "CONTAINS"
    return "CONTRADICTION"


def judge(e, rec):
    out = {"n": e["n"], "reference": e["raw"], "kind": e["kind"], "flags": [], "fields": {}, "patches": [], "note": ""}
    out["missing"] = e["fields_missing"]
    out["artefacts"] = e["artefacts"]
    status = rec.get("status") if rec else "none"
    if status in ("unreachable", "not looked up"):
        out["outcome"], out["note"] = "Review", ("lookup unreachable: " + rec.get("reason", "")) if status == "unreachable" else "not looked up (offline)"
        return out
    if status != "found":
        if e["kind"] == "article" and (e["doi"] or e["title"]) and not e["artefacts"]:
            out["outcome"] = "Not found"
            out["note"] = ("the DOI does not resolve in Crossref" if rec.get("doi_resolves") is False else "no match by DOI or title in Crossref or OpenAlex") + "; possibly fabricated or mis-cited"
        else:
            out["outcome"] = "Review"
            out["note"] = "not in the indexes searched; books, chapters, reports, archives and web pages are often absent from them, so this is not evidence the work is invented"
        if e["artefacts"]:
            out["note"] += "; " + "; ".join(e["artefacts"])
        return out
    out["record"] = {k: rec.get(k, "") for k in ("source", "title", "year", "authors", "venue", "doi", "url", "open_access")}
    ra = rec.get("authors") or []
    if e["isbn"] and rec.get("isbn_records") and not any(sim(t, e["title"]) >= TYPO or fold(t) in fold(e["title"]) or fold(e["title"]) in fold(t) for t in rec["isbn_records"]):
        out["outcome"] = "Review"
        out["flags"].append("frankenstein")
        out["note"] = "the ISBN belongs to a different work in Crossref ('%s'), not to the title given; the entry may join parts of different works" % rec["isbn_records"][0][:80]
        return out
    f = out["fields"]
    f["title"] = field_verdict(e["title"], rec.get("title", ""), "title")
    f["first_author"] = "ABSENT" if not e["first_author"] or not ra else ("MATCH" if fold(e["first_author"]) == fold(ra[0]) or fold(ra[0]) in fold(e["first_author"]) else "CONTRADICTION")
    f["year"] = field_verdict(e["year"].rstrip("abcdefghijklmnopqrstuvwxyz"), rec.get("year", ""), "year")
    if e["venue"] and rec.get("venue"):
        f["venue"] = field_verdict(e["venue"], rec["venue"], "venue")
    f["doi"] = "ABSENT" if not e["doi"] else ("MATCH" if fold(e["doi"]) == fold(rec.get("doi", "")) else ("ABSENT" if not rec.get("doi") else "CONTRADICTION"))
    if f["title"] == "CONTRADICTION" or (f["first_author"] == "CONTRADICTION" and f["year"] == "CONTRADICTION" and f["title"] in ("MATCH", "CONTAINS")):
        out["outcome"] = "Review"
        out["flags"].append("frankenstein")
        via = "DOI" if e["doi"] else ("ISBN" if rec.get("via") == "isbn" else "title search")
        why = "the %s gave a record that differs from the entry" % via
        out["note"] = f"{why}: the index record is '{rec.get('title','')[:80]}' ({', '.join(ra[:2])} {rec.get('year','')}); the entry may join parts of different works"
        return out
    bad = [k for k, v in f.items() if v == "CONTRADICTION"]
    typo = f["title"] == "TYPO"
    if e["kind"] == "book" and bad == ["year"]:
        out["outcome"] = "Review"
        out["note"] = "year differs from the index record (%s); editions and reprints carry different years, so no correction is proposed" % rec.get("year", "")
        return out
    if bad or typo:
        out["outcome"] = "Fix"
        src = rec.get("url") or rec.get("source")
        if typo:
            out["patches"].append({"entry": e["n"], "field": "title", "original": e["title"], "proposed": rec["title"], "source": src, "reason": "title differs slightly from the index record"})
        for k in bad:
            if k == "first_author":
                prop, orig = (ra[0] if ra else ""), e["first_author"]
            elif k == "doi":
                continue
            else:
                prop, orig = rec.get(k, ""), e.get(k, "")
            if prop:
                out["patches"].append({"entry": e["n"], "field": k, "original": orig, "proposed": prop, "source": src, "reason": f"{k} in the list differs from the index record"})
        if not out["patches"]:
            out["outcome"] = "Review"
            out["note"] = "fields disagree with the index record but no safe single correction exists"
    else:
        out["outcome"] = "Clean"
    if not e["doi"]:
        out["note"] = (out["note"] + "; " if out["note"] else "") + "no DOI is given in the list; none has been added"
    return out


def judge_with_artefacts(e, rec):
    out = judge(e, rec)
    if e["artefacts"]:
        add = "; ".join(e["artefacts"])
        if add not in out["note"]:
            out["note"] = (out["note"] + "; " if out["note"] else "") + add
        if out["outcome"] == "Clean":
            out["outcome"] = "Review"
    return out


def shared_identifiers(entries):
    seen, out = {}, {}
    for e in entries:
        for kind in ("doi", "isbn"):
            key = fold(e[kind]) if kind == "doi" else isbn_digits(e[kind])
            if key:
                seen.setdefault((kind, key), []).append(e["n"])
    for (kind, _), ns in seen.items():
        if len(ns) > 1:
            for n in ns:
                out.setdefault(n, []).append("shares its %s with entry %s" % (kind.upper(), ", ".join(str(m) for m in ns if m != n)))
    return out


def verdicts(entries, records):
    res = [judge_with_artefacts(e, records.get(str(e["n"]), {"status": "none"})) for e in entries]
    for r, msgs in ((r, shared_identifiers(entries).get(r["n"], [])) for r in res):
        if msgs:
            r["note"] = (r["note"] + "; " if r["note"] else "") + "; ".join(msgs) + " (two different works cannot share one identifier)"
            r["flags"].append("shared-identifier")
            if r["outcome"] == "Clean":
                r["outcome"] = "Review"
    counts = {k: sum(1 for r in res if r["outcome"] == k) for k in ("Clean", "Fix", "Not found", "Review")}
    n = len(res)
    warn = ""
    if n >= 5 and counts["Not found"] / n > 0.7 and not any("frankenstein" in r["flags"] for r in res):
        warn = "more than 70% of entries are Not found: suspect a parsing problem before suspecting fabrication"
    return {"entries": res, "counts": counts, "parsing_warning": warn}


def table(v):
    lines = ["| # | Reference as given | Outcome | Field verdicts | Note |", "|---|---|---|---|---|"]
    for r in v["entries"]:
        fv = ", ".join(f"{k} {x}" for k, x in r["fields"].items()) or "none"
        note = r["note"] or ""
        if r["missing"]:
            note += ("; " if note else "") + "not given: " + ", ".join(f"{m['field']} (look in {m['look_in']})" for m in r["missing"])
        lines.append(f"| {r['n']} | {r['reference'].replace('|', '/')} | {r['outcome']} | {fv} | {note.replace('|', '/')} |")
    out = ["\n".join(lines), ""]
    pl = [p for r in v["entries"] for p in r["patches"]]
    if pl:
        out += ["Patch log (proposed corrections; nothing has been applied):", "", "| Entry | Field | Original | Proposed | Source | Reason |", "|---|---|---|---|---|---|"]
        out += [f"| {p['entry']} | {p['field']} | {p['original']} | {p['proposed']} | {p['source']} | {p['reason']} |" for p in pl]
        out.append("")
    if v["parsing_warning"]:
        out += [v["parsing_warning"] + ".", ""]
    out += ["Entries are formatted or checked, not verified.", "Clean means nothing found through the search used."]
    return "\n".join(out)


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    for c in ("parse", "cross"):
        sp.add_parser(c).add_argument("draft")
    lk = sp.add_parser("lookup")
    lk.add_argument("entries")
    lk.add_argument("--offline", action="store_true")
    lk.add_argument("--index")
    vd = sp.add_parser("verdicts")
    vd.add_argument("entries")
    vd.add_argument("records")
    sp.add_parser("table").add_argument("verdicts")
    try:
        a = ap.parse_args(argv)
        rd = lambda p: json.load(open(p, encoding="utf-8")) if p.endswith(".json") else open(p, encoding="utf-8").read()
        if a.cmd == "parse":
            print(json.dumps(parse(open(a.draft, encoding="utf-8").read()), indent=2, ensure_ascii=False))
        elif a.cmd == "cross":
            print(json.dumps(cross(open(a.draft, encoding="utf-8").read()), indent=2, ensure_ascii=False))
        elif a.cmd == "lookup":
            ents = rd(a.entries)
            idx = json.load(open(a.index, encoding="utf-8")) if a.index else None
            print(json.dumps({str(e["n"]): lookup_one(e, idx, a.offline) for e in ents}, indent=2, ensure_ascii=False))
        elif a.cmd == "verdicts":
            print(json.dumps(verdicts(rd(a.entries), rd(a.records)), indent=2, ensure_ascii=False))
        else:
            print(table(rd(a.verdicts)))
        return 0
    except SystemExit:
        raise
    except (OSError, ValueError, KeyError) as err:
        print(json.dumps({"error": str(err)}))
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
