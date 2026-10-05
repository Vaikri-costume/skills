#!/usr/bin/env python3
"""
check_british_spelling.py — strict British spelling prescan for the proofread skill.

Usage: check_british_spelling.py <draft_file> [--allow word[,word...]]
Output: JSON on stdout: {"total_findings": n, "findings": [...]} or {"error": "..."}.

Policy: strict British -ise, not Oxford -ize.
  * Every -ize / -ization / -izing / -izer / -izable and every -yze form is an
    error, whether or not it is used consistently, EXCEPT words spelt -ize in
    every English spelling system (size, prize, seize, capsize, maize, baize,
    assize and their inflections/compounds listed in ISE_EXCEPTIONS).
  * The other standard British spellings are preferred too (WORD_MAP below).

What is scanned: the writer's own prose only. Text inside "..." or curly quotes,
URLs, [[wikilinks]], markdown link targets, and everything after a
References/Bibliography/Works cited/Sources heading are excluded. Paragraphs are
numbered exactly as extract_paragraphs.py numbers them.

Finding fields: paragraph, sentence, sentence_opening_words, american_form,
british_form, rule (ise-rule | yse-rule | word-list), severity_hint, note.
`note` is "verify: ..." for context-dependent words (program, practice, licence,
meter, judgment, curb) that must not be auto-corrected.
"""
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(_HERE, 'shared')))
try:
    from extract_paragraphs import prose_paragraphs
except ImportError:  # shared helper not found: fall back to plain blank-line paragraphs
    def prose_paragraphs(text):
        return [(i, p.strip()) for i, p in
                enumerate([p for p in re.split(r'\n\s*\n', text.strip()) if p.strip()], 1)]

# ---------------------------------------------------------------------------
# 1. Words that are spelt -ize / -yze in EVERY system. The only way an -ize word
#    may stay. Built from stems; inflections and prefixed forms are generated so
#    that "synthesize", "emphasize", "hypothesize" (genuine -ize verbs from a
#    Greek -s- stem) are NOT caught by a naive "ends in size" rule.
# ---------------------------------------------------------------------------
_SIZE_PREFIXES = ("", "re", "over", "under", "down", "up", "super", "out", "mid", "pint", "king", "queen", "full", "life", "bite", "pocket")
_ISE_EXCEPTION_STEMS = {
    "size": _SIZE_PREFIXES,
    "prize": ("",),
    "seize": ("",),
    "capsize": ("",),
}
ISE_EXCEPTIONS = set()
for _stem, _prefixes in _ISE_EXCEPTION_STEMS.items():
    for _pre in _prefixes:
        _base = _pre + _stem
        ISE_EXCEPTIONS.update({_base, _base + "s", _base[:-1] + "ed", _base[:-1] + "ing"})
ISE_EXCEPTIONS.update({"sizable", "sizeable", "maize", "baize", "assize", "assizes", "brize", "sizer", "sizers", "seizer"})

# ---------------------------------------------------------------------------
# 2. Strict suffix rule: -iz- / -yz- before a verb or noun ending.
# ---------------------------------------------------------------------------
_ISE_RE = re.compile(
    r"\b([A-Za-z]*?)(iz|yz)(e|es|ed|er|ers|ing|ation|ations|ational|ationally|able|ability)\b",
    re.IGNORECASE)


def _anglicise(word, z_pos):
    """Swap the z at z_pos for s, keeping the case of the original letter."""
    s = 'S' if word[z_pos].isupper() else 's'
    return word[:z_pos] + s + word[z_pos + 1:]


# ---------------------------------------------------------------------------
# 3. Explicit word list: American spelling -> preferred British spelling.
#    Built from lemma tables so inflections are covered once, consistently.
# ---------------------------------------------------------------------------
def _forms(pairs, suffixes):
    out = {}
    for am, br in pairs:
        for suf in suffixes:
            out[am + suf] = br + suf
    return out


WORD_MAP = {}
# -or -> -our
WORD_MAP.update(_forms(
    [("color", "colour"), ("honor", "honour"), ("behavior", "behaviour"), ("labor", "labour"),
     ("favor", "favour"), ("neighbor", "neighbour"), ("harbor", "harbour"), ("humor", "humour"),
     ("rumor", "rumour"), ("vapor", "vapour"), ("flavor", "flavour"), ("odor", "odour"),
     ("endeavor", "endeavour"), ("armor", "armour"), ("parlor", "parlour"), ("splendor", "splendour"),
     ("tumor", "tumour"), ("valor", "valour"), ("savior", "saviour"), ("clamor", "clamour"),
     ("fervor", "fervour"), ("glamor", "glamour"), ("candor", "candour")],
    ["", "s", "ed", "ing", "ful", "less"]))
WORD_MAP.update({
    "colorful": "colourful", "colorless": "colourless", "colorfully": "colourfully",
    "honorable": "honourable", "honorably": "honourably", "favorable": "favourable", "favorably": "favourably",
    "favorite": "favourite", "favorites": "favourites", "neighborhood": "neighbourhood",
    "neighborhoods": "neighbourhoods", "neighboring": "neighbouring", "behavioral": "behavioural",
    "behaviorally": "behaviourally", "laborer": "labourer", "laborers": "labourers",
})
# -er -> -re
WORD_MAP.update(_forms(
    [("center", "centre"), ("fiber", "fibre"), ("theater", "theatre"), ("liter", "litre"),
     ("caliber", "calibre"), ("somber", "sombre"), ("specter", "spectre"), ("luster", "lustre"),
     ("saber", "sabre")],
    ["", "s", "ed"]))
WORD_MAP.update({"centering": "centring", "centered": "centred", "centers": "centres"})
# -ense -> -ence
WORD_MAP.update(_forms([("defense", "defence"), ("offense", "offence"), ("pretense", "pretence")], ["", "s"]))
WORD_MAP.update({"defenseless": "defenceless"})
# -og -> -ogue
WORD_MAP.update(_forms([("catalog", "catalogue"), ("dialog", "dialogue"), ("analog", "analogue")], ["", "s", "ed"]))
WORD_MAP.update({"cataloging": "cataloguing"})
# -yze -> -yse is handled by the strict rule, not listed here.
# single l -> ll before a suffix, and -ll- -> -l- verbs
for _am, _br in [("traveled", "travelled"), ("traveling", "travelling"), ("traveler", "traveller"),
                 ("travelers", "travellers"), ("canceled", "cancelled"), ("canceling", "cancelling"),
                 ("cancelation", "cancellation"), ("labeled", "labelled"), ("labeling", "labelling"),
                 ("modeled", "modelled"), ("modeling", "modelling"), ("leveled", "levelled"),
                 ("leveling", "levelling"), ("fueled", "fuelled"), ("fueling", "fuelling"),
                 ("signaled", "signalled"), ("signaling", "signalling"), ("totaled", "totalled"),
                 ("totaling", "totalling"), ("counselor", "counsellor"), ("counselors", "counsellors"),
                 ("jewelry", "jewellery"), ("marvelous", "marvellous"), ("woolen", "woollen"),
                 ("skillful", "skilful"), ("willful", "wilful"), ("fulfill", "fulfil"),
                 ("fulfills", "fulfils"), ("fulfillment", "fulfilment"), ("enroll", "enrol"),
                 ("enrollment", "enrolment"), ("installment", "instalment"),
                 ("distill", "distil"), ("instill", "instil"), ("appall", "appal")]:
    if _am != _br:
        WORD_MAP[_am] = _br
# ae / oe / other standard British forms
WORD_MAP.update({
    "aging": "ageing", "esthetic": "aesthetic", "esthetics": "aesthetics",
    "encyclopedia": "encyclopaedia", "pediatric": "paediatric", "anesthesia": "anaesthesia",
    "anesthetic": "anaesthetic", "orthopedic": "orthopaedic", "leukemia": "leukaemia",
    "hemorrhage": "haemorrhage", "diarrhea": "diarrhoea", "maneuver": "manoeuvre",
    "maneuvers": "manoeuvres", "maneuvered": "manoeuvred", "mold": "mould", "molds": "moulds",
    "molded": "moulded", "plow": "plough", "plows": "ploughs", "skeptic": "sceptic", "skeptics": "sceptics",
    "skeptical": "sceptical", "skepticism": "scepticism", "gray": "grey", "pajamas": "pyjamas",
    "aluminum": "aluminium", "mom": "mum", "cozy": "cosy", "sulfur": "sulphur", "artifact": "artefact",
    "artifacts": "artefacts", "tidbit": "titbit", "airplane": "aeroplane", "airplanes": "aeroplanes",
    "acknowledgment": "acknowledgement", "acknowledgments": "acknowledgements",
    "toward": "towards", "ax": "axe", "program": "programme", "programs": "programmes",
    "practice": "practise", "judgment": "judgement", "judgments": "judgements", "license": "licence",
    "licenses": "licences", "curb": "kerb", "meter": "metre", "meters": "metres",
})
# Context-dependent: never auto-correct, surface for a decision.
AMBIGUOUS = {
    "program": "program is correct for software; programme for a plan/series",
    "programs": "programs is correct for software; programmes for plans/series",
    "practice": "practice is the noun in British English; practise is the verb",
    "license": "licence is the noun, license the verb in British English",
    "licenses": "licences is the noun plural, licenses the verb",
    "judgment": "judgement is standard; judgment is accepted in legal contexts",
    "judgments": "judgements is standard; judgments is accepted in legal contexts",
    "curb": "kerb is the roadside edge; curb (to restrain) is the same in British English",
    "meter": "metre is the unit; meter is correct for an instrument",
    "meters": "metres is the unit; meters is correct for instruments",
    "toward": "towards is the British preference; low priority",
    "mold": "mould (fungus/shape); mold is not used in British English",
}


# ---------------------------------------------------------------------------
# Scan
# ---------------------------------------------------------------------------
_QUOTE_RE = re.compile(r'["“][^"“”]*["”]')
_URL_RE = re.compile(r'https?://\S+|www\.\S+')
_WIKILINK_RE = re.compile(r'\[\[[^\]]*\]\]')
_MDLINK_TARGET_RE = re.compile(r'\]\([^)]*\)')
_REF_HEADING_RE = re.compile(r'^\s{0,3}#{1,6}\s*(references|bibliography|works cited|sources|select bibliography)\b',
                             re.IGNORECASE | re.MULTILINE)


def _mask(match):
    return ' ' * len(match.group())


def strip_noise(text):
    """Blank out quoted material, URLs, wikilinks and link targets, preserving offsets."""
    for rx in (_QUOTE_RE, _URL_RE, _WIKILINK_RE, _MDLINK_TARGET_RE):
        text = rx.sub(_mask, text)
    return text


def cut_at_references(text):
    m = _REF_HEADING_RE.search(text)
    return text[:m.start()] if m else text


def _sentence_index(clean_para, pos):
    """1-based sentence number and its first words, for the report Location line."""
    starts = [0] + [m.end() for m in re.finditer(r'[.!?]["\')\]]*\s+', clean_para)]
    idx = max(i for i, s in enumerate(starts) if s <= pos)
    words = clean_para[starts[idx]:].split()[:6]
    return idx + 1, ' '.join(words)


def find_british_violations(text, allow=()):
    allow = {w.casefold() for w in allow}
    scan_text = cut_at_references(text)
    findings = []
    for num, para in prose_paragraphs(scan_text):
        clean = strip_noise(para)
        seen = set()

        def add(m, british, rule, note=''):
            if m.span() in seen:
                return
            seen.add(m.span())
            sent, opening = _sentence_index(clean, m.start())
            findings.append({
                'paragraph': num, 'sentence': sent, 'sentence_opening_words': opening,
                'american_form': m.group(0), 'british_form': british, 'rule': rule,
                'severity_hint': 'Medium', 'note': note,
            })

        # strict -ize / -yze rule
        for m in _ISE_RE.finditer(clean):
            word = m.group(0)
            low = word.casefold()
            if low in ISE_EXCEPTIONS or low in allow:
                continue
            z = m.start(2) + 1 - m.start()  # index of the z within the word
            british = _anglicise(word, z)
            add(m, british, 'yse-rule' if m.group(2).casefold() == 'yz' else 'ise-rule')

        # explicit word list
        for m in re.finditer(r"\b[A-Za-z]+\b", clean):
            low = m.group(0).casefold()
            if low in allow or low not in WORD_MAP:
                continue
            br = WORD_MAP[low]
            if m.group(0).isupper():
                br = br.upper()
            elif m.group(0)[0].isupper():
                br = br[0].upper() + br[1:]
            note = ('verify: ' + AMBIGUOUS[low]) if low in AMBIGUOUS else ''
            add(m, br, 'word-list', note)
    findings.sort(key=lambda f: (f['paragraph'], f['sentence']))
    return {'total_findings': len(findings), 'findings': findings}


def main(argv):
    allow = []
    args = []
    i = 0
    while i < len(argv):
        if argv[i] == '--allow' and i + 1 < len(argv):
            allow += [w for w in argv[i + 1].split(',') if w]
            i += 2
        else:
            args.append(argv[i])
            i += 1
    if len(args) != 1:
        print(json.dumps({'error': 'Usage: check_british_spelling.py <draft_file> [--allow word,word]'}))
        return 1
    try:
        with open(args[0], 'r', encoding='utf-8') as f:
            text = f.read()
    except OSError as e:
        print(json.dumps({'error': str(e)}))
        return 1
    print(json.dumps(find_british_violations(text, allow), indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
