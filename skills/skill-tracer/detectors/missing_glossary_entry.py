"""missing-glossary-entry — a stable named concept used without a glossary definition.

Mechanical, deterministic check: this skill's own naming convention (see
SKILL.md "## The four invariants" — `1. **Cold-read.** Every code-review agent...`,
and SKILL.md's fixer rule — `**Fixer dispatch.** The fixer-staging script (...`)
opens a bullet or a standalone paragraph with a bolded phrase immediately
followed by `.` or `:` to NAME a concept the rest of the sentence defines.
Every name coined this way — plus every backtick identifier used as a stable
reference (repeated 2+ times across the skill) — must have a standalone entry
in `references/glossary.md` per `references/how-to-fix.md` "Naming
discipline when a fix introduces a new stable name", rule 3 ("Mandatory,
standalone glossary entry").

Distinguishing a genuine skill concept from a label that only appears inside
a worked-example / output-format-template block (demonstrating literal text
rather than naming a concept — e.g. `File:`/`Claim:`/`Target:` labels shown
inside a worked example illustrating an ISSUE-format template) requires
context judgment that cannot be done mechanically. This check therefore only
surfaces candidates deterministically (the two detection patterns below), as an
ADVISORY lint: `scripts/doc_lint.py` reports them and the orchestrator decides
whether each is a real concept missing its definition or an example-only
occurrence. They never gate a tier.

Two detection signals:

  1. PRIMARY — a bolded phrase (`**...**`) that opens a bullet/numbered-list
     item or a standalone paragraph/section, with `.` or `:` immediately
     following the bold span (the punctuation may sit just inside the closing
     `**` — e.g. `**Cold-read.**` — or just outside — e.g. `**Cold-read**.` —
     both are the same naming convention). Ordinary mid-sentence emphasis
     bolding (e.g. "the fix **must** happen before...") does NOT match: the
     bolded span there is neither line-initial nor immediately followed by
     `.`/`:`.

  2. SECONDARY — a backtick-wrapped snake_case/kebab-case/`word:word`
     identifier (e.g. `` `blast_advisory` ``, `` `fill-address` ``,
     `` `fix:class` ``) that recurs 2+ times across the scanned file
     set. Repetition is the signal it names a stable reference rather than a
     one-off code snippet. File paths (contain `/` or end in a known
     extension) and bare CLI flags (`--foo` with no other structure) are
     already covered by `refs` / `argparse-flag-undocumented` respectively —
     both shapes are excluded automatically because the identifier pattern
     requires a leading letter, which flags (leading `-`) and paths never
     satisfy on their own within a single backtick span.

Glossary cross-check: `references/glossary.md`'s own `| **Term** | ... |`
table format is authoritative; the shared CCVW glossary is irrelevant here —
this skill's glossary must be self-contained. Matching is EXACT after
normalization (lowercase; `-`, `_`, and whitespace runs treated as
interchangeable and collapsed to a single space) — never substring, prefix,
or fuzzy. `no_orphan_flag` / `no-orphan-flag` / `no orphan flag` all
normalize to the identical string and match each other, but a candidate
normalizing to "no orphan flag" does NOT match a glossary entry that
normalizes to "no orphan flag invariant" — those are different full strings.
This is intentional per the compositional-honesty rule in
`references/how-to-fix.md` "Naming discipline when a fix introduces a new
stable name": a name and a longer phrase built from it are
different concepts, and one must never be treated as covering the other via
substring/contains matching (verified: a hypothetical `classify_prompt`
glossary entry does NOT cause `use_classify_prompt` to read as covered, since
"classify prompt" != "use classify prompt" as full strings).

Scope: SKILL.md, prompts/*.md, references/*.md (excluding glossary.md
itself — a term's own definition entry is not a "use" needing a definition),
templates/*.md. README.md/HISTORY.md/LICENSE are already excluded by
cascade_sweep.py's shared inscope_files() filter before detect() ever runs.

prompts/*.md files are read but never PROPOSE a new entry (forward signals
skip them; see _is_agent_prompt_file). A prompt file is the text of one
sub-agent's brief or one check's adjudication rubric: its bolded labels head
conditions local to that one prompt (CONFIRM-IF/REJECT-IF sub-classes,
input-field names, worked-example captions), not vocabulary the skill's
reader needs defined. A term that is genuinely shared vocabulary also appears
in SKILL.md / references / templates, where it is still caught. Prompt files
DO still count as places a glossary term is used (reverse signal), so an entry
referenced only from a rubric is not reported as orphaned.

Reverse signal (glossary.md only): a glossary entry is orphaned when its term
appears nowhere else in the scanned files — as a bolded label, a backtick
identifier, OR plain prose (whole-phrase match after the same normalization,
with backticks/asterisks removed). Prose counts because a term used in a
sentence or heading is in use; requiring bold/backtick form reported live
terms like "ledger" or "convergence" as orphans.

ABSTAIN cases: no SKILL.md found walking up from the scanned file (can't
locate the skill root to resolve references/glossary.md or the sibling file
set).

Level: advisory — reported by scripts/doc_lint.py, never a prepass gate (cascade_sweep.py
--level prepass skips it).
"""
from __future__ import annotations

import re
import sys as _sys
from pathlib import Path

_DET_DIR = Path(__file__).resolve().parent
if str(_DET_DIR) not in _sys.path:
    _sys.path.insert(0, str(_DET_DIR))
from _common import (  # noqa: E402
    find_skill_root_from_file as _find_skill_root,
    inscope_glob as _inscope_glob,
    line_of as _line_of,
)

CHECK_ID = "missing-glossary-entry"
LEVEL = "advisory"
FILE_GLOBS = ["SKILL.md", "prompts/*.md", "references/*.md", "templates/*.md"]

# PRIMARY: a bolded phrase opening a bullet/numbered-item or a standalone line,
# with `.`/`:` either just inside the closing `**` (captured in group 1, e.g.
# "Cold-read.") or just outside it (captured in group 2, e.g. "Score**:").
# The optional bullet prefix covers "-", "*", "+" bullets and "1." / "1)"
# numbered items; arbitrary leading whitespace covers nested/indented items.
_LABEL_RE = re.compile(
    r"^[ \t]*(?:[-*+]|\d+[.)])?[ \t]*\*\*([^*\n]+?)\*\*([.:]?)",
    re.MULTILINE,
)

# Structural tightening: a genuine name/concept-label reads as a short noun
# phrase or compact tag, not a full instructional sentence. Emphasized
# sentences ("**before doing any other work.**", "**There is nothing special
# about a 'last' round.**") use the identical bold-then-period markdown idiom
# as genuine names ("**Cold-read.**"), so the distinguishing signal has to be
# structural, not judgment-based:
#   - word count: a name stays short (~6 alphabetic tokens or fewer — e.g.
#     a label like "Exact label form (load-bearing)" is 5 words once the
#     parentheses and punctuation are excluded from the count);
#     instructional sentences run longer.
#   - function-word list: a small set of words that only ever appear inside a
#     finite-verb clause (auxiliaries/modals like "is"/"must"/"should", articles
#     "the"/"a"/"an", conjunctions/adverbs like "before"/"after"/"always") — any
#     of these appearing as a whole word marks the span as a clause, not a label.
_MAX_LABEL_WORDS = 6
_SENTENCE_WORDS = {
    "is", "are", "was", "were", "be", "been", "being",
    "must", "should", "shall", "will", "would", "can", "could", "may", "might",
    "do", "does", "did", "done",
    "the", "a", "an", "this", "that", "these", "those",
    "before", "after", "always", "never", "only", "here", "there",
    "when", "while", "if", "then", "so", "because", "since", "not", "also",
    "holds", "happens", "reads", "means", "gets", "occurs", "applies",
    "requires", "causes", "allows", "forbids", "forbidden", "required",
    "allowed", "have", "has", "had", "doing",
}
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'-]*")


def _looks_like_name(term: str) -> bool:
    """True if `term` structurally reads as a compact name/label rather than a
    full instructional sentence (see _MAX_LABEL_WORDS / _SENTENCE_WORDS above)."""
    words = _WORD_RE.findall(term)
    if not words:
        return False
    if len(words) > _MAX_LABEL_WORDS:
        return False
    if any(w.lower() in _SENTENCE_WORDS for w in words):
        return False
    return True


def _is_output_literal_label(term: str) -> bool:
    """True if `term` names a procedural branch keyed to a script's literal
    output rather than a concept — e.g. 'On output `{"status":"converged",...}`'
    or '`some_script.py` outputs'. These read as bolded labels structurally
    (short, no sentence words) but their content is a JSON blob or an
    "outputs" branch marker, not a stable name anything else in the skill
    would reference by that label."""
    if "{" in term:
        return True
    words = _WORD_RE.findall(term)
    return bool(words) and words[-1].lower() == "outputs"


# ---------------------------------------------------------------------------
# Rubric-local condition names (enumerated CONFIRM-IF/REJECT-IF siblings).
#
# A check-adjudication rubric names its own CONFIRM-IF/REJECT-IF conditions
# using the identical bold-then-period/colon markdown idiom a genuine
# skill-wide concept uses (see module docstring). Both are structurally
# indistinguishable at the single-label level; the distinguishing evidence is
# the ENCLOSING SECTION: a condition name is one of 2+ short, flat siblings
# directly under a heading that itself announces an enumerated
# CONFIRM-IF/REJECT-IF/worked-example/decision-procedure block — vocabulary
# this skill's own glossary already documents as the CCVW rubric convention's
# structural roles (CONFIRM-IF, REJECT-IF, Worked example, ...), not
# skill-tracer-specific wording. This generalizes to any target skill using
# the same convention.
#
# Verified 2026-07-11 against skill-tracer's own 114 residual candidates plus
# a canary set of confirmed-real terms (SKILL.md's "Recovery"/tier-name
# labels, the four invariants, DESC-SITE/CALL-SITE/RECOVERY-SITE, the
# structural-role terms CONFIRM-IF/REJECT-IF/Trigger/Scope/Worked example
# themselves) — none of the canary terms are suppressed. Two broader variants
# (also matching bold-only "the following:"-style intro lines; also matching
# dash-bulleted sibling lists regardless of heading) were tried and REJECTED
# during verification: both wrongly suppressed real terms (a literal-output
# label self-matching as an "intro", and DESC-SITE/CALL-SITE/RECOVERY-SITE
# presented as a dash-bulleted list) — dash-bulleted lists are a documented
# valid way to coin a real concept in this skill (see PRIMARY signal docstring
# above: "opens a bullet or a standalone paragraph"), so sibling-count alone
# is not safe evidence there; only the heading-scoped signal below is used.
# ---------------------------------------------------------------------------

_HEADING_RE = re.compile(r"(?m)^(#{1,6})[ \t]+(.*)$")
_ENUMERATION_HEADING_RE = re.compile(
    r"^\s*(confirm|reject|worked)\b|closed\s+.*question|decision\s+(rule|procedure|framework|question)",
    re.IGNORECASE,
)
_FENCE_RE = re.compile(r"```")
_PARA_BREAK_RE = re.compile(r"\n[ \t]*\n")
_MAX_CONDITION_WORDS = 150


def _enclosing_heading(src: str, pos: int) -> tuple[int, int, bool]:
    """(section_start, section_end, opened_by_enumeration_heading) for the
    heading-bounded block containing byte offset `pos` — the block runs from
    the nearest preceding heading (any level) to the next heading whose level
    is <= that heading's level."""
    prev = None
    for h in _HEADING_RE.finditer(src):
        if h.start() <= pos:
            prev = h
        else:
            break
    if prev is None:
        return 0, len(src), False
    level = len(prev.group(1))
    start = prev.end()
    end = len(src)
    for h in _HEADING_RE.finditer(src):
        if h.start() > start and len(h.group(1)) <= level:
            end = h.start()
            break
    return start, end, bool(_ENUMERATION_HEADING_RE.search(prev.group(2)))


def _rubric_local_condition_names(src: str, candidates: list[tuple[int, int, str]]) -> set[int]:
    """Positions (match-start offsets) of PRIMARY candidates that are 2+
    short, flat siblings directly under an enumeration-shaped heading — see
    module-level comment above for the full rationale and verification."""
    from collections import defaultdict

    groups: dict[tuple[int, int], list[tuple[int, int, str]]] = defaultdict(list)
    opened: dict[tuple[int, int], bool] = {}
    for start, end, term in candidates:
        s0, s1, is_enum = _enclosing_heading(src, start)
        groups[(s0, s1)].append((start, end, term))
        opened[(s0, s1)] = is_enum

    suppressed: set[int] = set()
    for key, items in groups.items():
        if not opened[key] or len(items) < 2:
            continue
        s0, s1 = key
        items_sorted = sorted(items)
        flat = True
        for i, (start, end, _term) in enumerate(items_sorted):
            nxt = items_sorted[i + 1][0] if i + 1 < len(items_sorted) else s1
            span = src[end:nxt]
            m = _PARA_BREAK_RE.search(span)
            owned = span[: m.start()] if m else span
            if _FENCE_RE.search(owned) or len(_WORD_RE.findall(owned)) > _MAX_CONDITION_WORDS:
                flat = False
                break
        if flat:
            suppressed.update(start for start, _end, _term in items_sorted)
    return suppressed

# SECONDARY: a backtick-wrapped identifier. Requires a leading letter so bare
# CLI flags (leading "-") and absolute/relative paths never satisfy the shape
# on their own; requires at least one of _/-/: so a plain word like `foo`
# (ordinary code-quoting, not a stable name) doesn't count.
_BACKTICK_RE = re.compile(r"`([^`\n]+)`")
_IDENTIFIER_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_:-]*$")
_SEPARATOR_RE = re.compile(r"[-_\s]+")

_PATH_EXTENSIONS = (".py", ".md", ".json", ".sh")

# Mechanical pre-filter for the SECONDARY signal (applied in the detector
# itself, so the orchestrator reading doc_lint.py output is not asked to judge it): an occurrence only counts as evidence of a genuine
# prose reference if it sits in a "referencing position" — immediately
# preceded by a determiner/demonstrative ("the", "a", "an", "this", "that",
# "these", "those") — OR it falls outside a fenced code block / inline
# command example / "Output Format"/"Input Format" demonstration block. A
# repeated identifier whose every occurrence is confined to code fences or
# format-demo sections is filtered here, before ever surfacing as a
# candidate; this does not touch the PRIMARY bolded-label signal.
_REFERENCING_WORD_RE = re.compile(
    r"\b(?:the|an?|this|that|these|those)\s*$", re.IGNORECASE
)
_FENCE_LINE_RE = re.compile(r"^[ \t]*```", re.MULTILINE)
_FORMAT_HEADING_RE = re.compile(
    r"^[ \t]*#{1,6}[ \t]*.*\b(?:input|output)\s*format\b.*$",
    re.IGNORECASE | re.MULTILINE,
)
_ANY_HEADING_RE = re.compile(r"^[ \t]*#{1,6}[ \t]", re.MULTILINE)
_COMMAND_LINE_RE = re.compile(r"^[ \t]*\$\s+\S")


def _excluded_spans(text: str) -> list[tuple[int, int]]:
    """Byte-offset [start, end) spans of fenced code blocks and
    "Input/Output Format" demonstration sections within `text`."""
    spans: list[tuple[int, int]] = []

    # Fenced code blocks: pair up ``` markers in order.
    fence_starts = [m.start() for m in _FENCE_LINE_RE.finditer(text)]
    i = 0
    while i + 1 < len(fence_starts):
        open_pos = fence_starts[i]
        close_pos = fence_starts[i + 1]
        line_end = text.find("\n", close_pos)
        end = len(text) if line_end == -1 else line_end + 1
        spans.append((open_pos, end))
        i += 2

    # "Input Format" / "Output Format" demonstration sections: from the
    # heading to the next heading of any level (or EOF).
    for hm in _FORMAT_HEADING_RE.finditer(text):
        start = hm.start()
        next_heading = _ANY_HEADING_RE.search(text, hm.end())
        end = next_heading.start() if next_heading else len(text)
        spans.append((start, end))

    return spans


def _in_span(pos: int, spans: list[tuple[int, int]]) -> bool:
    return any(s <= pos < e for s, e in spans)


def _is_referencing_occurrence(text: str, match_start: int, excluded: list[tuple[int, int]]) -> bool:
    """True if this backtick occurrence qualifies as a genuine prose reference:
    preceded by a determiner/demonstrative, or simply outside code fences /
    inline command examples / format-demo blocks."""
    line_start = text.rfind("\n", 0, match_start) + 1
    line_end = text.find("\n", match_start)
    if line_end == -1:
        line_end = len(text)
    full_line = text[line_start:line_end]
    preceding = text[line_start:match_start]

    if _COMMAND_LINE_RE.match(full_line):
        return False  # inline CLI-command demonstration line

    if _REFERENCING_WORD_RE.search(preceding):
        return True

    return not _in_span(match_start, excluded)

_GLOSSARY_ROW_RE = re.compile(r"^\|\s*\*\*(.+?)\*\*\s*\|", re.MULTILINE)

# Cross-file token counts, memoized per skill root so repeated detect() calls
# within one cascade_sweep.py run re-scan the file set only once.
_TOKEN_COUNT_CACHE: dict[Path, dict[str, int]] = {}
_TOKEN_QUALIFIES_CACHE: dict[Path, set[str]] = {}
_GLOSSARY_TERM_CACHE: dict[Path, set[str]] = {}
# Cross-file PRIMARY (bolded-label) occurrences, memoized per skill root. Maps
# normalized term -> list of (file, line, raw_term, context) in _skill_files()
# order. The same undefined label (e.g. "Scope") recurs verbatim across many
# rubric files as the same structural convention; without this aggregation
# each occurrence would surface as its own candidate — inflating raw volume
# without adding information, since they're all the same missing-definition
# question asked once per file instead of once per name.
_PRIMARY_OCCURRENCES_CACHE: dict[Path, dict[str, list[tuple[Path, int, str, str]]]] = {}


def _context_line(text: str, start: int, end: int) -> str:
    """The full source line containing [start, end), trimmed, for the fixer's context."""
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", end)
    if line_end == -1:
        line_end = len(text)
    return text[line_start:line_end].strip()


def _normalize(name: str) -> str:
    """lowercase; unify -, _, and whitespace runs into a single space. Colon is
    left untouched — it is meaningful (e.g. "fix" vs "fix:class"
    would be distinct glossary entries), not a separator variant."""
    name = name.strip().strip("`*")
    name = _SEPARATOR_RE.sub(" ", name)
    return name.strip().lower()


_PROSE_CACHE: dict[Path, str] = {}  # file -> _normalize_prose(text), reused across glossary terms


def _normalize_prose(text: str) -> str:
    """_normalize applied to running text for the reverse signal's prose
    match: backticks and asterisks removed everywhere (not just at the ends),
    then the same lowercase + separator collapsing."""
    return _SEPARATOR_RE.sub(" ", re.sub(r"[`*]", "", text)).lower()


def _load_glossary_terms(skill_root: Path) -> set[str]:
    if skill_root in _GLOSSARY_TERM_CACHE:
        return _GLOSSARY_TERM_CACHE[skill_root]
    gpath = skill_root / "references" / "glossary.md"
    try:
        gsrc = gpath.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        gsrc = ""
    terms = {_normalize(m.group(1)) for m in _GLOSSARY_ROW_RE.finditer(gsrc)}
    _GLOSSARY_TERM_CACHE[skill_root] = terms
    return terms


def _skill_files(skill_root: Path) -> list[Path]:
    """Every file in this detector's own scope, skill-root-relative — the same
    FILE_GLOBS cascade_sweep.py uses to call detect(), minus glossary.md."""
    out: list[Path] = []
    seen: set[Path] = set()
    for g in FILE_GLOBS:
        for f in _inscope_glob(skill_root, g):
            if f.name == "glossary.md":
                continue
            rf = f.resolve()
            if rf in seen:
                continue
            seen.add(rf)
            out.append(f)
    return out


def _is_candidate_identifier(tok: str) -> bool:
    if tok.endswith(_PATH_EXTENSIONS) or "/" in tok:
        return False  # file path — covered by `refs`
    if not _IDENTIFIER_RE.match(tok):
        return False  # leading char must be a letter — excludes bare `--flag` and paths
    if not re.search(r"[_:-]", tok.rstrip(":")):
        # plain word, not a snake/kebab/colon-style stable name. A colon only at
        # the END (`File:`, `else:`) is label punctuation of a literal field or
        # prefix, defined by the format it belongs to (e.g. the ISSUE block),
        # not an interior `word:word` name like `fix:class`.
        return False
    return True


_TOKEN_FIRST_OCCURRENCE_CACHE: dict[Path, dict[str, tuple[Path, int, str]]] = {}


def _is_agent_prompt_file(f: Path) -> bool:
    """True for a file under a `prompts/` directory — a sub-agent brief or
    adjudication rubric whose labels are prompt-local (see module docstring);
    such files never originate a forward candidate."""
    return f.parent.name == "prompts"


def _global_token_counts(skill_root: Path) -> dict[str, int]:
    if skill_root in _TOKEN_COUNT_CACHE:
        return _TOKEN_COUNT_CACHE[skill_root]
    counts: dict[str, int] = {}
    qualifying: set[str] = set()
    first_occurrence: dict[str, tuple[Path, int, str]] = {}
    for f in _skill_files(skill_root):
        try:
            text = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        excluded = _excluded_spans(text)
        is_prompt = _is_agent_prompt_file(f)
        for m in _BACKTICK_RE.finditer(text):
            tok = m.group(1)
            if not _is_candidate_identifier(tok):
                continue
            counts[tok] = counts.get(tok, 0) + 1
            if is_prompt:
                continue  # counts toward recurrence, never originates a candidate
            if _is_referencing_occurrence(text, m.start(), excluded):
                qualifying.add(tok)
                if tok not in first_occurrence:
                    first_occurrence[tok] = (
                        f, _line_of(text, m.start()),
                        _context_line(text, m.start(), m.end()),
                    )
    _TOKEN_COUNT_CACHE[skill_root] = counts
    _TOKEN_QUALIFIES_CACHE[skill_root] = qualifying
    _TOKEN_FIRST_OCCURRENCE_CACHE[skill_root] = first_occurrence
    return counts


def _primary_matches_raw(src: str) -> list[tuple[int, int, str]]:
    """(start, end, term) for every naming-convention bold match, before the
    rubric-local-condition suppression (which needs cross-file recurrence
    data — see _primary_candidates)."""
    out: list[tuple[int, int, str]] = []
    for m in _LABEL_RE.finditer(src):
        raw, trailing_punct = m.group(1), m.group(2)
        if raw and raw[-1] in ".:":
            term = raw[:-1].strip()
        elif trailing_punct:
            term = raw.strip()
        else:
            continue  # not immediately followed by . or : — ordinary mid-line emphasis
        if not term:
            continue
        if not _looks_like_name(term):
            continue  # reads as a full instructional sentence, not a name
        if _is_output_literal_label(term):
            continue  # a literal script-output branch label, not a concept name
        out.append((m.start(), m.end(), term))
    return out


def _primary_candidates(src: str, suppress_starts: frozenset[int] = frozenset()) -> list[tuple[int, str, str]]:
    """(line, term, context-line) for every naming-convention bold match,
    excluding any whose match-start offset is in `suppress_starts` (rubric-
    local condition names — see _rubric_local_condition_names). Callers that
    don't have cross-file recurrence data yet (e.g. _term_referenced_elsewhere)
    pass no suppress_starts, since ANY occurrence — suppressed-as-a-candidate
    or not — still counts as a real "reference" for the reverse check."""
    out: list[tuple[int, str, str]] = []
    for start, end, term in _primary_matches_raw(src):
        if start in suppress_starts:
            continue
        out.append((_line_of(src, start), term, _context_line(src, start, end)))
    return out


def _global_primary_occurrences(skill_root: Path) -> dict[str, list[tuple[Path, int, str, str]]]:
    """normalized term -> [(file, line, raw_term, context), ...] across every
    in-scope file, in _skill_files() order — the aggregation the PRIMARY
    signal needs so the same recurring label surfaces once, not once per
    occurrence (see _PRIMARY_OCCURRENCES_CACHE docstring above).

    The rubric-local-condition-name suppression (_rubric_local_condition_names)
    is applied HERE, after cross-file recurrence is known, and only to terms
    whose global occurrence count is exactly 1: a term that recurs verbatim
    in 2+ different files is real shared vocabulary by definition (a check's
    own local CONFIRM-IF/REJECT-IF condition name is never repeated in
    another check's rubric), so recurrence itself overrides the structural
    suppression signal — see _rubric_local_condition_names' module comment."""
    if skill_root in _PRIMARY_OCCURRENCES_CACHE:
        return _PRIMARY_OCCURRENCES_CACHE[skill_root]

    per_file: dict[Path, tuple[str, list[tuple[int, int, str]]]] = {}
    global_counts: dict[str, int] = {}
    for f in _skill_files(skill_root):
        try:
            text = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        matches = _primary_matches_raw(text)
        per_file[f] = (text, matches)
        for _start, _end, term in matches:
            global_counts[_normalize(term)] = global_counts.get(_normalize(term), 0) + 1

    by_term: dict[str, list[tuple[Path, int, str, str]]] = {}
    for f, (text, matches) in per_file.items():
        if _is_agent_prompt_file(f):
            continue  # counted in global_counts above; never originates a candidate
        single_occurrence_starts = {
            start for start, _end, term in matches if global_counts[_normalize(term)] == 1
        }
        suppress_starts = _rubric_local_condition_names(text, matches) & single_occurrence_starts
        for line, term, context in _primary_candidates(text, frozenset(suppress_starts)):
            by_term.setdefault(_normalize(term), []).append((f, line, term, context))
    _PRIMARY_OCCURRENCES_CACHE[skill_root] = by_term
    return by_term


def _term_referenced_elsewhere(term: str, skill_root: Path) -> bool:
    """True if the normalized glossary `term` appears anywhere in the skill's
    other files (backtick identifier or bolded label), using the same
    normalization the forward check uses. Uses the RAW (unsuppressed) match
    set — a rubric-local-shaped occurrence still counts as a real reference
    for the reverse check; suppression only controls whether the PRIMARY
    signal proposes a NEW glossary entry, not whether an existing entry is
    considered used."""
    norm = _normalize(term)
    prose_re = re.compile(
        r"(?<![a-z0-9])" + re.escape(_normalize_prose(term)) + r"(?![a-z0-9])"
    )
    for f in _skill_files(skill_root):
        try:
            text = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        prose = _PROSE_CACHE.get(f)
        if prose is None:
            prose = _PROSE_CACHE[f] = _normalize_prose(text)
        if prose_re.search(prose):
            return True
        for m in _BACKTICK_RE.finditer(text):
            if _normalize(m.group(1)) == norm:
                return True
        for _start, _end, cand_term in _primary_matches_raw(text):
            if _normalize(cand_term) == norm:
                return True
    return False


def _reverse_candidates(path: Path, src: str) -> list[dict]:
    """glossary.md-only pass: find defined terms with zero occurrences
    anywhere else in the skill's own text (orphaned/dead glossary entries)."""
    root = _find_skill_root(path)
    if root is None:
        return [{"line": 0, "detail": "abstain: no SKILL.md found walking up from file",
                 "abstain": True}]
    out: list[dict] = []
    for m in _GLOSSARY_ROW_RE.finditer(src):
        term = m.group(1).strip()
        if not term:
            continue
        if _term_referenced_elsewhere(term, root):
            continue
        out.append({
            "line": _line_of(src, m.start()),
            "detail": (
                f"glossary entry '{term}' is defined but never used/referenced "
                f"anywhere else in the skill"
            ),
            "check_variant": "glossary-entry-unused",
        })
    return out


def detect(path: Path, src: str) -> list[dict]:
    if path.name == "glossary.md":
        return _reverse_candidates(path, src)
    if _is_agent_prompt_file(path):
        return []  # prompt-local labels never propose an entry (module docstring)

    root = _find_skill_root(path)
    if root is None:
        return [{"line": 0, "detail": "abstain: no SKILL.md found walking up from file",
                 "abstain": True}]

    glossary_terms = _load_glossary_terms(root)
    out: list[dict] = []

    # PRIMARY: emit one candidate per distinct undefined term, from its FIRST
    # occurrence in _skill_files() order — never one per occurrence (see
    # _global_primary_occurrences docstring: the same recurring label like
    # "Scope" is one missing-definition question, not one per file it's in).
    primary_by_term = _global_primary_occurrences(root)
    for norm_term, occurrences in primary_by_term.items():
        if norm_term in glossary_terms:
            continue
        if " / " in norm_term:
            # A slash-joined label spanning two already-individually-defined
            # terms (e.g. "fix / fix:class") is not a new
            # concept — it's a combined reference to two existing ones.
            # Suppress only when EVERY half independently resolves; a half
            # that is itself undefined still needs to surface.
            halves = [h.strip() for h in norm_term.split(" / ") if h.strip()]
            if halves and all(h in glossary_terms for h in halves):
                continue
        first_file, first_line, first_term, first_context = occurrences[0]
        if first_file != path:
            continue  # emitted from the term's first-occurrence file only
        count = len(occurrences)
        count_note = f" (used as this label {count}x across the skill)" if count > 1 else ""
        out.append({
            "line": first_line,
            "detail": (
                f"name '{first_term}' is not defined in references/glossary.md"
                f"{count_note} — context: \"{first_context}\""
            ),
        })

    # SECONDARY: emit one candidate per distinct qualifying token, from its
    # FIRST qualifying occurrence in _skill_files() order — same dedup
    # rationale as PRIMARY above: a repeated identifier is one
    # missing-definition question, not one per occurrence.
    global_counts = _global_token_counts(root)
    qualifying_tokens = _TOKEN_QUALIFIES_CACHE.get(root, set())
    first_occurrence = _TOKEN_FIRST_OCCURRENCE_CACHE.get(root, {})
    for tok in qualifying_tokens:
        if global_counts.get(tok, 0) < 2:
            continue
        if _normalize(tok) in glossary_terms:
            continue
        occ = first_occurrence.get(tok)
        if occ is None or occ[0] != path:
            continue  # emitted from the token's first qualifying-occurrence file only
        _, first_line, context = occ
        out.append({
            "line": first_line,
            "detail": (
                f"name '{tok}' (backtick identifier, used {global_counts[tok]}x "
                f"across the skill) is not defined in references/glossary.md "
                f"— context: \"{context}\""
            ),
        })

    return out
