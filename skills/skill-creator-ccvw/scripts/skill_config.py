#!/usr/bin/env python3
"""Resolve per-user settings for skill-creator-ccvw without hard-coding any person's data.

Contract: `skill_config.py get <key>` prints one resolved value (or nothing) and exits 0.
Lookup order for every key: environment variable, then the user-profile file, then the
safe default (none of the defaults names a person).

Keys and their environment variables:
  eval_workspace  CCVW_EVAL_WORKSPACE  default ${XDG_DATA_HOME:-~/.claude}/skill-creator-evals-ledger
  session_log_dir CCVW_SESSION_LOG_DIR default empty = session logging off ("off" also means off)
  scratch_dir     CCVW_SCRATCH_DIR     default empty (caller uses a fresh temporary directory)
  author_identity CCVW_AUTHOR          default empty (caller asks the user once)
  helper_model    CCVW_HELPER_MODEL    default sonnet

Profile file: --profile PATH, else $CCVW_USER_PROFILE, else the first config/user-profile.md
found walking up from the current directory. It is a markdown file with bullets of the form
    - `key`: value
Missing file or missing key is not an error: the default applies.
"""
import argparse
import os
import re
import sys
from pathlib import Path

KEYS = {
    "eval_workspace": ("CCVW_EVAL_WORKSPACE", None),
    "session_log_dir": ("CCVW_SESSION_LOG_DIR", ""),
    "scratch_dir": ("CCVW_SCRATCH_DIR", ""),
    "author_identity": ("CCVW_AUTHOR", ""),
    "helper_model": ("CCVW_HELPER_MODEL", "sonnet"),
}
BULLET = re.compile(r"^\s*[-*]\s+`([a-z_]+)`\s*:\s*(.+?)\s*$")


def find_profile(explicit):
    if explicit:
        return Path(explicit)
    env = os.environ.get("CCVW_USER_PROFILE")
    if env:
        return Path(env)
    here = Path.cwd().resolve()
    for d in [here, *here.parents]:
        cand = d / "config" / "user-profile.md"
        if cand.is_file():
            return cand
    return None


def read_profile(path):
    values = {}
    if path is None or not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        m = BULLET.match(line)
        if m and m.group(1) in KEYS:
            values.setdefault(m.group(1), m.group(2).strip("`"))
    return values


def default_workspace():
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".claude")
    return str(Path(base) / "skill-creator-evals-ledger")


def resolve(key, profile_path=None):
    env_name, default = KEYS[key]
    value = os.environ.get(env_name)
    if not value:
        value = read_profile(find_profile(profile_path)).get(key)
    if not value:
        value = default if default is not None else default_workspace()
    return os.path.expanduser(value) if value else ""


def session_log_enabled(profile_path=None):
    v = resolve("session_log_dir", profile_path)
    return bool(v) and v.lower() != "off"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=["get", "all"])
    ap.add_argument("key", nargs="?", choices=sorted(KEYS))
    ap.add_argument("--profile")
    a = ap.parse_args(argv)
    if a.action == "get":
        if not a.key:
            ap.error("get needs a key")
        print(resolve(a.key, a.profile))
    else:
        for k in sorted(KEYS):
            print(f"{k}={resolve(k, a.profile)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
