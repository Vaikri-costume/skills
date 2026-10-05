#!/usr/bin/env python3
"""
extract_paragraphs.py — Produce a numbered paragraph map for a draft essay.
Usage: python extract_paragraphs.py <draft_file_path>
Output: JSON to stdout. All agents in a run receive this map and must use
these paragraph numbers — ensures consistent cross-agent paragraph references.
"""
import sys, re, json

_SKIP_RE = re.compile(
    r'^\s*(?:'
    r'#{1,6} '           # Markdown headings
    r'|[a-zA-Z][\w-]*::' # Logseq/YAML property lines (key:: value)
    r'|```'              # Code fence delimiters
    r')',
    re.MULTILINE,
)


def _is_non_prose(para):
    """Return True if this block should be skipped (heading, property line, code fence)."""
    first_line = para.strip().split('\n')[0]
    return bool(_SKIP_RE.match(first_line))



def prose_paragraphs(text):
    """Return [(paragraph_number, paragraph_text)] using the same skip rules as
    extract_paragraphs(), so every script numbers paragraphs identically."""
    out = []
    in_code_fence = False
    num = 0
    for para in re.split(r'\n\s*\n', text.strip()):
        stripped = para.strip()
        if not stripped:
            continue
        fence_count = stripped.count('```')
        if in_code_fence:
            if fence_count % 2 == 1:
                in_code_fence = False
            continue
        if stripped.startswith('```'):
            if fence_count % 2 == 1:
                in_code_fence = True
            continue
        if _is_non_prose(stripped):
            continue
        num += 1
        out.append((num, stripped))
    return out


def extract_paragraphs(text):
    # Strip any leading/trailing code-fence blocks as whole units first
    paragraphs = re.split(r'\n\s*\n', text.strip())
    result = []
    para_num = 0
    in_code_fence = False
    for para in paragraphs:
        stripped = para.strip()
        if not stripped:
            continue
        # Track multi-paragraph code fences (``` ... ``` spanning blank lines)
        fence_count = stripped.count('```')
        if in_code_fence:
            if fence_count % 2 == 1:
                in_code_fence = False
            continue
        if stripped.startswith('```'):
            if fence_count % 2 == 0:
                # Opening and closing fence in same block — skip it
                pass
            else:
                in_code_fence = True
            continue
        # Skip headings and Logseq property lines
        if _is_non_prose(stripped):
            continue
        para_num += 1
        words = stripped.split()
        opening = ' '.join(words[:8]) + ('...' if len(words) > 8 else '')
        result.append({
            "paragraph": para_num,
            "opening_words": opening,
            "word_count": len(words)
        })
    return {"total_paragraphs": len(result), "paragraphs": result}

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(json.dumps({"error": "Usage: extract_paragraphs.py <draft_file>"}))
        sys.exit(1)
    with open(sys.argv[1], 'r', encoding='utf-8') as f:
        text = f.read()
    print(json.dumps(extract_paragraphs(text), indent=2))
