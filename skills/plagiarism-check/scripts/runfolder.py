#!/usr/bin/env python3
"""runfolder.py new [SCRATCH_DIR] | remove PATH: make and delete the run folder without shell tricks.

new      creates a fresh folder named plagiarism-check-XXXXXX under SCRATCH_DIR (default: the system
         temporary directory) and prints its absolute path. Use that path literally in later steps.
remove   deletes a run folder by its literal absolute path. It refuses anything that is not a real
         (non-symlink) directory whose name starts with plagiarism-check-.
"""
import os
import shutil
import sys
import tempfile

PREFIX = "plagiarism-check-"


def main(argv):
    if argv and argv[0] == "new" and len(argv) <= 2:
        base = argv[1] if len(argv) == 2 else tempfile.gettempdir()
        if not os.path.isdir(base):
            print(f"runfolder: scratch folder does not exist: {base}", file=sys.stderr)
            return 2
        print(os.path.realpath(tempfile.mkdtemp(prefix=PREFIX, dir=base)))
        return 0
    if len(argv) == 2 and argv[0] == "remove":
        path = argv[1]
        if (not os.path.isabs(path) or os.path.islink(path) or not os.path.isdir(path)
                or not os.path.basename(path).startswith(PREFIX)):
            print(f"runfolder: refusing to remove {path}", file=sys.stderr)
            return 2
        shutil.rmtree(path)
        print(f"removed {path}")
        return 0
    print("Usage: runfolder.py new [SCRATCH_DIR] | remove PATH", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
