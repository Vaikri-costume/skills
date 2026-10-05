#!/usr/bin/env python3
"""
check_consistency.py — Detect word/phrase variant groups across a draft.
Usage: python check_consistency.py <draft_file_path>
Output: JSON to stdout with grouped variants and locations.
Agents assess which variants are intentional; the script only finds them.
Quoted material (text in "...") is excluded from scanning so that variations
between a writer's prose and a quoted source are not flagged.
"""
import sys, re, json
from collections import defaultdict
import os
sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'shared')))
try:
    from extract_paragraphs import prose_paragraphs
    from citelib import split_body_and_bibliography
except ImportError:  # shared helpers missing: fall back to plain blank-line paragraphs
    prose_paragraphs = None
    split_body_and_bibliography = None


# Common English function words. When the only difference between variants is
# initial-letter case for one of these (e.g. "the" vs "The"), the variation is
# almost always sentence-start capitalisation, not an inconsistency. Filtering
# these reduces noise dramatically without losing real findings — proper nouns,
# domain terms, and content words still surface.
STOPWORDS = {
    "a", "an", "and", "as", "at", "be", "been", "being", "but", "by", "can",
    "could", "did", "do", "does", "even", "for", "from", "had", "has", "have",
    "he", "her", "here", "his", "how", "i", "if", "in", "is", "it", "its",
    "just", "may", "might", "more", "most", "must", "my", "no", "not", "now",
    "of", "on", "one", "only", "or", "our", "out", "over", "own", "same",
    "she", "should", "so", "some", "such", "than", "that", "the", "their",
    "them", "then", "there", "these", "they", "this", "those", "to", "too",
    "under", "up", "very", "was", "we", "were", "what", "when", "where",
    "which", "while", "who", "whom", "whose", "why", "will", "with", "would",
    "yes", "you", "your", "yours", "first", "last", "next", "also", "still",
    "yet", "again", "any", "all", "each", "every", "both", "many", "much",
    "few", "less", "least", "ever", "never", "always", "sometimes", "often",
}


def extract_paragraphs(text):
    return [p.strip() for p in re.split(r'\n\s*\n', text.strip()) if p.strip()]

def find_variants(text):
    # Same paragraph numbering as the shared paragraph map (headings, property lines and
    # code fences are not paragraphs) and the reference list is excluded.
    if prose_paragraphs is not None:
        body = split_body_and_bibliography(text)[0]
        numbered = prose_paragraphs(body)
    else:
        numbered = list(enumerate(extract_paragraphs(text), 1))
    word_locations = defaultdict(list)
    for para_num, para in numbered:
        # Skip quoted material (straight or curly double quotes)
        clean_para = re.sub(r'["\u201c][^"\u201c\u201d]*["\u201d]', '', para)
        words = re.findall(r"\b[A-Za-z][\w'-]*\b", clean_para)
        for word in words:
            stem = word.lower().replace('-', '')
            word_locations[stem].append((word, para_num))

    variant_groups = []
    seen_stems = set()
    for stem, occurrences in word_locations.items():
        if stem in seen_stems or len(occurrences) < 2:
            continue
        surface_forms = {}
        for form, para in occurrences:
            if form not in surface_forms:
                surface_forms[form] = []
            surface_forms[form].append(para)
        # Only flag if there are 2+ distinct surface forms
        if len(surface_forms) > 1:
            seen_stems.add(stem)
            lower_forms = {f.lower() for f in surface_forms}
            dehyphen = {f.replace('-', '') for f in surface_forms}
            variant_type = ("capitalisation" if len(lower_forms) == 1 else
                            "hyphenation" if len(dehyphen) == 1 else "spelling/name")
            # Skip sentence-start capitalisation noise on common function words.
            # Hyphenation and spelling/name variants on stopwords are still flagged
            # because those would be genuine inconsistencies.
            if variant_type == "capitalisation" and stem in STOPWORDS:
                continue
            variant_groups.append({
                "stem": stem,
                "forms": {form: sorted(set(paras)) for form, paras in surface_forms.items()},
                "type": variant_type
            })

    return {"total_variant_groups": len(variant_groups), "groups": variant_groups}

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(json.dumps({"error": "Usage: check_consistency.py <draft_file>"}))
        sys.exit(1)
    with open(sys.argv[1], 'r', encoding='utf-8') as f:
        text = f.read()
    print(json.dumps(find_variants(text), indent=2))
