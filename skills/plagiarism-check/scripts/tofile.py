#!/usr/bin/env python3
"""tofile.py OUT SCRIPT [ARGS...]: run SCRIPT with this Python and save its standard output to OUT.

Replaces the shell redirect (`python3 script.py args > out.json`), so every step is one plain
`python3` command with absolute paths. The script's own standard error is passed through and its
exit code is returned. Prints one line, `wrote OUT (N bytes)`, on success.
"""
import os
import subprocess
import sys


def main(argv):
    if len(argv) < 2:
        print("Usage: tofile.py OUT SCRIPT [ARGS...]", file=sys.stderr)
        return 2
    out, script, args = argv[0], argv[1], argv[2:]
    if not os.path.isfile(script):
        print(f"tofile: no such script: {script}", file=sys.stderr)
        return 2
    p = subprocess.run([sys.executable, script, *args], capture_output=True, text=True)
    try:
        with open(out, "w", encoding="utf-8") as f:
            f.write(p.stdout)
    except OSError as e:
        print(f"tofile: cannot write {out}: {e}", file=sys.stderr)
        return 2
    sys.stderr.write(p.stderr)
    print(f"wrote {out} ({len(p.stdout.encode('utf-8'))} bytes)")
    return p.returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
