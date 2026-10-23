"""Shared by the maintenance scripts in this folder (imported, never run on its own)."""
import re

# A line that opens or closes a fenced code block; Logseq bullets prefix fences with "- ```".
# A line that carries both fences ("- ```x```") opens nothing, so it does not match.
FENCE_OPEN_RE = re.compile(r'^\s*-?\s*```(?!.*```)')
