#!/usr/bin/env python3
"""
quotes.py — blank out quoted material so spelling and consistency scans judge only the writer's own words.

mask_quotes(text) -> text of the same length with these spans replaced by spaces:
  * "straight" and “curly” double-quoted spans
  * ‘single’ curly-quoted spans, and 'straight single' spans written the British way: an opening
    ' that follows a space, bracket or line start and is followed by a letter, closed by the next
    ' that follows a letter or punctuation and is not followed by a letter. This leaves apostrophes
    (don't, the dogs' bowls, 'tis) alone in all but the rare possessive-plural-then-space case.
  * Markdown block-quote lines (a line starting with >)
Offsets are preserved, so locations computed on the masked text map onto the original.
"""
import re

_DOUBLE = re.compile(r'["“][^"“”]*["”]')
_SINGLE_CURLY = re.compile(r'‘[^‘’]*’')
_SINGLE_STRAIGHT = re.compile(r"(?:(?<=\s)|(?<=[(\[])|(?<=^))'(?=[A-Za-z])[^'\n]{2,}?(?<=[A-Za-z0-9.,!?;:)])'(?![A-Za-z])", re.MULTILINE)
_BLOCK = re.compile(r'^[ \t]*>.*$', re.MULTILINE)


def _blank(m):
    return re.sub(r'[^\n]', ' ', m.group())


def mask_quotes(text):
    for rx in (_BLOCK, _DOUBLE, _SINGLE_CURLY, _SINGLE_STRAIGHT):
        text = rx.sub(_blank, text)
    return text
