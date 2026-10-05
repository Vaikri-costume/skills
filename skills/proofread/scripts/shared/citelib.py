#!/usr/bin/env python3
"""
citelib.py — citation parsing shared by citation_audit.py, quote_verify.py,
detect_sources.py and build_citation_map.py.

Supported in-text forms (SOAS lists Harvard author-date and footnotes as the two
main systems; Logseq/Obsidian drafts also use links):
  harvard    (Jones 2002)  (Jones 2002:34)  (Jones 2002, p. 34)  (Hughes and Smith 2005)
             (Gardner et al. 2007)  (Jones 2002; Hughes and Smith 2005)  (Simons 1980; cited in James 1990:67)
  narrative  Jones (2002) argues…   Stubbs (1980:89)
  footnote   markers [^1] in the body, definitions `[^1]: Jones 2002, 34.`
  wikilink   [[citekey or Page Title]]
  citekey    [@smith2002]

Everything is deterministic and regex-based; none of it needs an LLM.
"""
import re

YEAR = r'(?:1[5-9]\d\d|20\d\d)[a-z]?'
NAME = r"[A-Z][\w'’\-]+(?:\s+(?:de|van|von|al|el|bin|ibn|le|la|di|da)\s+[A-Z][\w'’\-]+)?"
AUTHORS = rf"{NAME}(?:\s*(?:,|and|&)\s*{NAME})*(?:\s+et\s+al\.?)?"
PAGE = r"(?:\s*[:,]\s*(?:pp?\.\s*)?(?P<page>[\divxlc][\divxlc\-–, ]*))?"

_PAREN_RE = re.compile(r'\(([^()]*?\b' + YEAR + r'\b[^()]*?)\)')
_PART_RE = re.compile(rf'^\s*(?:see\s+|cf\.\s*|e\.g\.,?\s*|also\s+)?(?:[^;]*?cited in\s+)?(?P<authors>{AUTHORS})[,\s]+(?P<year>{YEAR}\b){PAGE}',
                      re.IGNORECASE)
_NARR_RE = re.compile(rf'(?P<authors>{AUTHORS})\s*\((?P<year>{YEAR})\b{PAGE}\)')
_FN_REF_RE = re.compile(r'\[\^([^\]\s]+)\](?!:)')
_FN_DEF_RE = re.compile(r'^\[\^([^\]\s]+)\]:\s*(.+)$', re.MULTILINE)
_WIKI_RE = re.compile(r'\[\[([^\]]+)\]\]')
_CITEKEY_RE = re.compile(r'\[@([^\]]+)\]')
_BIB_HEAD_RE = re.compile(r'^\s{0,3}(?:#{1,6}\s*)?(references|bibliography|works cited|sources|select bibliography|literature cited)\s*:?\s*$',
                          re.IGNORECASE | re.MULTILINE)


def first_surname(authors):
    """'Hughes and Smith' -> 'hughes'; 'Gardner et al.' -> 'gardner'; 'de Souza' -> 'de souza'."""
    a = re.split(r'\s*(?:,|and|&)\s*|\s+et\s+al', authors.strip(), maxsplit=1)[0]
    return a.strip().casefold()


def split_body_and_bibliography(text):
    """Return (body, bibliography_text). Bibliography starts at the last matching heading."""
    heads = list(_BIB_HEAD_RE.finditer(text))
    if not heads:
        return text, ''
    h = heads[-1]
    return text[:h.start()], text[h.end():]


def _mk(kind, authors, year, page, raw, start):
    return {'kind': kind, 'surname': first_surname(authors) if authors else '',
            'authors': authors or '', 'year': year or '', 'page': (page or '').strip(),
            'raw': raw, 'start': start}


def find_citations(text):
    """All in-text citations in `text`, in order of appearance."""
    out = []
    covered = []
    for m in _PAREN_RE.finditer(text):
        content = m.group(1)
        offset = m.start(1)
        pos = 0
        for part in content.split(';'):
            pm = _PART_RE.match(part)
            if pm:
                out.append(_mk('harvard', pm.group('authors'), pm.group('year'), pm.group('page'),
                               part.strip(), offset + pos))
            pos += len(part) + 1
        covered.append((m.start(), m.end()))
    for m in _NARR_RE.finditer(text):
        if any(s <= m.start() < e for s, e in covered):
            continue
        out.append(_mk('narrative', m.group('authors'), m.group('year'), m.group('page'), m.group(0), m.start()))
    for m in _FN_REF_RE.finditer(text):
        out.append(_mk('footnote', '', '', '', m.group(0), m.start()))
    for m in _WIKI_RE.finditer(text):
        out.append(_mk('wikilink', m.group(1), '', '', m.group(0), m.start()))
    for m in _CITEKEY_RE.finditer(text):
        out.append(_mk('citekey', m.group(1), '', '', m.group(0), m.start()))
    out.sort(key=lambda c: c['start'])
    return out


def footnote_definitions(text):
    return {m.group(1): m.group(2).strip() for m in _FN_DEF_RE.finditer(text)}


def citation_from_note(note):
    """Parse a footnote definition like 'Jones 2002, 34.' or 'Michael Jones, 2002. "Title"…'."""
    m = re.search(rf'(?P<authors>{AUTHORS})[,\s]+(?P<year>{YEAR})\b{PAGE}', note)
    if m:
        return _mk('footnote-note', m.group('authors'), m.group('year'), m.group('page'), note, 0)
    m = re.search(rf'(?P<first>[A-Z][\w\'’\-]+)\s+(?P<last>{NAME})[,.]?\s+(?P<year>{YEAR})\b', note)
    if m:
        return _mk('footnote-note', m.group('last'), m.group('year'), '', note, 0)
    return None


def parse_bibliography(bib_text):
    """Entries like 'Bohlman, Philip V. 1988. The study…' or 'Jones, M. (2002) Title'.
    Returns [{surname, year, raw}] keyed on the first author's surname and the year."""
    entries = []
    chunks = [c.strip() for c in re.split(r'\n\s*\n|\n(?=\s*[-*]\s|\s*[A-Z][\w\'’\-]+,)', bib_text) if c.strip()]
    for c in chunks:
        c1 = re.sub(r'^\s*[-*]\s*', '', c)
        m = re.match(rf"(?P<sur>{NAME}),\s*[^\n]*?\(?(?P<year>{YEAR})\b", c1)
        if m:
            entries.append({'surname': m.group('sur').casefold(), 'year': m.group('year'),
                            'raw': ' '.join(c1.split())[:160]})
    return entries


def keys_match(cite, entry):
    """Does an in-text citation refer to a bibliography entry? Year suffix is optional on either side."""
    if cite['surname'] != entry['surname']:
        return False
    cy, ey = cite['year'], entry['year']
    return cy == ey or cy.rstrip('abcdefghijklmnopqrstuvwxyz') == ey.rstrip('abcdefghijklmnopqrstuvwxyz')


_QUOTE_RE = re.compile(r'["“]([^"“”]{10,}?)["”]')


def quotations(text, min_words=4):
    """Quoted passages (inline double quotes and `>` block lines) with the citation that follows, if any."""
    out = []
    for m in _QUOTE_RE.finditer(text):
        q = m.group(1).strip()
        if len(q.split()) < min_words:
            continue
        tail = text[m.end(): m.end() + 90]
        cite = None
        pm = re.match(r'\s*\(([^()]*)\)', tail)
        if pm:
            cs = find_citations('(' + pm.group(1) + ')')
            cite = cs[0] if cs else None
        else:
            nm = re.match(r'\s*(\[\^[^\]]+\])', tail)
            if nm:
                cite = {'kind': 'footnote', 'raw': nm.group(1), 'surname': '', 'year': ''}
        out.append({'quote': q, 'cite': cite, 'start': m.start()})
    for m in re.finditer(r'^>\s*(.+)$', text, re.MULTILINE):
        q = m.group(1).strip()
        if len(q.split()) >= min_words:
            out.append({'quote': q, 'cite': None, 'start': m.start()})
    out.sort(key=lambda x: x['start'])
    return out


def normalise_for_match(s):
    """Fold a passage for quote verification: case, quote styles, dashes, whitespace,
    ellipses, editorial [brackets] and punctuation are all ignored."""
    s = s.replace('’', "'").replace('‘', "'").replace('“', '"').replace('”', '"')
    s = re.sub(r'\[[^\]]*\]', ' ', s)           # editorial insertions
    s = re.sub(r'\.\.\.|…', ' ', s)         # ellipses
    s = re.sub(r'[‐-―\-]', ' ', s)
    s = re.sub(r"[^\w\s']", ' ', s)
    return re.sub(r'\s+', ' ', s).strip().casefold()
