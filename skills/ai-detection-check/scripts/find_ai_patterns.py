#!/usr/bin/env python3
"""
find_ai_patterns.py — Exact-match prescan for AI-typical language patterns.
Usage: python find_ai_patterns.py <draft_file_path>
Output: JSON to stdout.

The pattern list is perishable: model habits drift and writers adopt them. It was last
reviewed on LAST_REVIEWED against the Wikipedia guide "Signs of AI writing" (WikiProject
AI Cleanup, advice page, not policy). A hit is a prompt to look at the sentence, never
evidence of machine authorship; human judges do no better than chance on such signs.

Per cross-skill lesson #2 from proofread (scripts pre-filter deterministic noise),
this scan EXCLUDES patterns appearing inside directly quoted source material —
"..." regions are masked before scanning. The B (pattern) agents receive the
remaining real-prose hits and focus on context-judgment + semantic equivalents,
not re-doing the keyword search.
"""
import sys, re, json

LAST_REVIEWED = "2026-10-04"

import os as _os
sys.path.insert(0, _os.path.normpath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), 'shared')))
try:
    from citelib import split_body_and_bibliography as _split_body
except ImportError:  # shared helper missing: scan the whole text
    def _split_body(t):
        return t, ''

PATTERNS = {
    1: {"name": "Significance inflation", "phrases": [
        "groundbreaking", "revolutionary", "transformative", "unprecedented",
        "paradigm shift", "seminal", "pivotal contribution",
        "stands as a testament", "a testament to", "plays a vital role", "plays a crucial role",
        "plays a pivotal role", "underscores the importance", "enduring legacy", "pivotal moment"]},
    2: {"name": "Hollow generalisations", "phrases": [
        "throughout history", "in today's world", "society has always",
        "since time immemorial", "across cultures"]},
    3: {"name": "False-balance framing", "phrases": [
        "while some argue", "there are those who believe",
        "this essay will examine both sides", "on one hand", "on the other hand"]},
    4: {"name": "Unearned conclusions", "phrases": [
        "this shows the importance of", "further research is needed",
        "ultimately, this reveals the complexity",
        "it is clear that more work must be done"]},
    5: {"name": "AI vocabulary cluster", "phrases": [
        "delve", "intricate", "tapestry", "nuanced", "nuanced tapestry",
        "navigate", "landscape", "realm", "comprehensive", "robust",
        "multifaceted", "multitude", "crucially", "pivotal", "underscore", "underscores",
        "intricacies", "interplay", "showcase", "showcasing", "vibrant", "garner", "foster"]},
    6: {"name": "Copula avoidance", "phrases": [
        "serves as", "functions as", "operates as", "proves to be",
        "emerges as", "comes to represent"]},
    7: {"name": "Vague attributions", "phrases": [
        "experts say", "scholars note", "research suggests",
        "studies show", "critics argue", "many have observed"]},
    8: {"name": "Promotional lexicon", "phrases": [
        "powerful", "striking", "compelling", "rich", "innovative",
        "fascinating", "remarkable", "eloquent", "insightful"],
        "density_threshold": 3,
        "note": "Standard analytical vocabulary in film/cultural-studies essays. Agents should only flag when density >= density_threshold occurrences per paragraph."},
    9: {"name": "Excessive hedging", "phrases": [
        "it could be argued that", "it might be suggested that",
        "one could possibly say", "this may indicate",
        "it would seem that", "it appears as though"]},
    10: {"name": "Negative parallelisms", "phrases": [
        "not only", "not merely", "not simply"]},
    11: {"name": "Rule of three (triadic lists)", "phrases": [],
         "structural": True,
         "note": "Triadic lists ('X, Y, and Z' / 'X, Y, Z' parallel constructions) are structural, not exact-phrase. The script reports exact-match count = 0; the agent must scan semantically for triplet patterns where the rhetorical effect substitutes for specificity (e.g. 'embroidery, weaving, and dyeing techniques' is content-bearing; 'compelling, powerful, and transformative' is filler triadic lift)."},
    12: {"name": "Uniform sentence length", "phrases": [],
         "structural": True,
         "note": "Judged from the sentence inventory and sentence_length.cv in compute_metrics.py (descriptive, no threshold). The script reports exact-match count = 0 here; agents judge runs of similar-length sentences themselves and may cite the cv value as context."},
    13: {"name": "Filler openings", "phrases": [
        "it is worth noting that",
        "it is important to recognise that", "it is important to recognize that",
        "it should be noted that", "one must consider", "it bears mentioning that"]},
    14: {"name": "Announcement sentences", "phrases": [
        "this essay will examine", "in this section, i will discuss",
        "having established", "i now turn to", "this paper argues that"]},
}


def strip_quoted(text):
    """Replace text inside "..." or curly "..." with spaces so positions are
    preserved but quoted source material is excluded from pattern scanning.
    Handles both ASCII straight quotes and Unicode curly quotes (U+201C/U+201D).
    """
    return re.sub(r'["“][^"“”]*["”]',
                  lambda m: ' ' * len(m.group()), text)


def formatting_signals(text):
    """Descriptive counts of formatting habits the Wikipedia guide lists. Not scored."""
    clean = strip_quoted(text)
    words = max(len(re.findall(r"\w+", clean)), 1)
    return {
        "em_dashes": clean.count("\u2014"),
        "em_dashes_per_1000_words": round(clean.count("\u2014") / words * 1000, 2),
        "bold_spans": len(re.findall(r"\*\*[^*]+\*\*", clean)),
        "emoji": len(re.findall("[\U0001F300-\U0001FAFF\u2600-\u27BF]", clean)),
    }


def find_patterns(text):
    text = _split_body(text)[0]                                       # reference list is not prose
    clean_text = strip_quoted(text)
    text_lower = clean_text.lower()
    results = {}
    for pattern_num, pattern in PATTERNS.items():
        instances = []
        for phrase in pattern["phrases"]:
            for match in re.finditer(re.escape(phrase), text_lower):
                start = max(0, match.start() - 40)
                end = min(len(clean_text), match.end() + 40)
                # Pull context from the original (un-masked) text, since position
                # is preserved by the space-fill in strip_quoted.
                context = text[start:end].replace('\n', ' ')
                instances.append({
                    "phrase": phrase,
                    "context": f"...{context}...",
                })
        results[str(pattern_num)] = {
            "name": pattern["name"],
            "exact_match_count": len(instances),
            "instances": instances,
        }
    return {
        "patterns": results,
        "total_exact_matches": sum(r["exact_match_count"] for r in results.values()),
        "formatting_signals": formatting_signals(text),
        "list_last_reviewed": LAST_REVIEWED,
        "note": "Inside-quoted-material patterns are excluded from this scan.",
    }


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(json.dumps({"error": "Usage: find_ai_patterns.py <draft_file>"}))
        sys.exit(1)
    with open(sys.argv[1], 'r', encoding='utf-8') as f:
        text = f.read()
    print(json.dumps(find_patterns(text), indent=2))
