#!/usr/bin/env python3
"""
strip_markers.py — Convert Logseq bullet-block draft text into paragraph-separated prose.
Usage: python strip_markers.py <input_file> [output_file]

In Logseq, each top-level `- ` line is its own block (i.e. paragraph). The pasted-text
form of a draft therefore looks like:

    - First paragraph.
    - Second paragraph.
    -
      > quoted line
    -
    Final paragraph.

The downstream paragraph map / synthesis assumes prose paragraphs separated by blank
lines. This script:
  * Strips the leading `- ` from each bulleted line and inserts a blank line before
    it (unless one is already present), so consecutive bullets become consecutive
    paragraphs.
  * Replaces lone `-` lines (Logseq blank blocks / spacers) with blank lines.
  * Leaves `---` horizontal rules and all other lines untouched.

If no output_file is given the input file is rewritten in place.
"""
import sys


def strip_markers(text):
    lines = text.split('\n')
    out = []
    for line in lines:
        # Lone "-" line → Logseq blank-block spacer. Emit a blank line.
        if line.rstrip() == '-':
            if not out or out[-1] != '':
                out.append('')
            continue
        # Bulleted line "- ..." → strip prefix, ensure a blank line precedes it
        if line.startswith('- ') and not line.startswith('---'):
            if out and out[-1] != '':
                out.append('')
            out.append(line[2:])
            continue
        out.append(line)
    # Collapse runs of blank lines to a single blank line for cleanliness
    cleaned = []
    prev_blank = False
    for ln in out:
        if ln == '':
            if prev_blank:
                continue
            prev_blank = True
        else:
            prev_blank = False
        cleaned.append(ln)
    return '\n'.join(cleaned).strip() + '\n'


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: strip_markers.py <input_file> [output_file]")
        sys.exit(1)
    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else input_file
    with open(input_file, 'r', encoding='utf-8') as f:
        text = f.read()
    result = strip_markers(text)
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(result)
