#!/usr/bin/env python3
"""
Thin entrypoint for the Drive Organizer backend.

The actual implementation lives in the sibling `drive_organizer/` package (split
from the original single-file organizer.py into per-concern modules). This file
exists so every existing invocation of
    python3 ~/.claude/drive-organizer/organizer.py <subcommand> ...
keeps working unchanged after the install step copies both this file AND the
`drive_organizer/` package directory side-by-side into ~/.claude/drive-organizer/.

It does nothing but put its own directory on sys.path (so `drive_organizer` is
importable as a sibling package) and hand off to drive_organizer.cli.main().
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from drive_organizer.cli import main

if __name__ == "__main__":
    main()
