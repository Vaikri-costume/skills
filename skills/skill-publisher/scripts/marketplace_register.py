#!/usr/bin/env python3
"""Register a shipped skill in the upstream repo's Claude Code marketplace catalog.

Pure-stdlib. Imported by github_pr.py (so the registration lands in the SAME commit
as the skill copy, and the dry-run shows it); also usable standalone to inspect a
clone:

    python3 marketplace_register.py <clone-dir> --repo-path skills/<name> [--json]

Catalog location: <clone>/.claude-plugin/marketplace.json (the layout Claude Code
marketplaces use). A skill is "listed" when some plugin's `skills` array holds its
path (`./<repo-path>`, compared with a leading "./" and trailing "/" normalised).

Why registration is separate from the skill copy: copying the folder makes the skill
exist in the repo, but `claude plugins install` only offers what the catalog lists —
an unlisted skill ships "successfully" and is still uninstallable.

States returned by plan():
  absent        no marketplace.json in the clone — nothing to do
  listed        already registered (no change; idempotent on re-ships)
  needs_choice  catalog exists, skill not listed — the orchestrator must pick an
                existing plugin, a new plugin, or opt out
"""

import argparse
import json
import re
import sys
from pathlib import Path

CATALOG_REL = Path(".claude-plugin") / "marketplace.json"


def _norm(p: str) -> str:
    p = p.strip().replace("\\", "/")
    if p.startswith("./"):
        p = p[2:]
    return p.strip("/")


def skill_entry(repo_path: str) -> str:
    """The string a plugin's `skills` array holds for this skill."""
    return "./" + _norm(repo_path)


def _load(clone_dir: Path):
    path = clone_dir / CATALOG_REL
    raw = path.read_text(encoding="utf-8")
    return path, raw, json.loads(raw)


def plan(clone_dir: Path, repo_path: str) -> dict:
    """Inspect the catalog; never writes."""
    path = clone_dir / CATALOG_REL
    if not path.is_file():
        return {"state": "absent", "detail": f"no {CATALOG_REL} in the upstream repo"}
    try:
        _, _, data = _load(clone_dir)
    except (OSError, ValueError) as e:
        return {"state": "error", "detail": f"{CATALOG_REL} unreadable or invalid JSON: {e}"}
    plugins = data.get("plugins")
    if not isinstance(plugins, list):
        return {"state": "error", "detail": f"{CATALOG_REL} has no plugins[] array"}
    want = _norm(repo_path)
    for pl in plugins:
        skills = pl.get("skills") if isinstance(pl, dict) else None
        if isinstance(skills, list) and any(isinstance(s, str) and _norm(s) == want for s in skills):
            return {"state": "listed", "plugin": pl.get("name"), "entry": skill_entry(repo_path)}
    appendable = [pl["name"] for pl in plugins
                  if isinstance(pl, dict) and isinstance(pl.get("skills"), list) and pl.get("name")]
    return {"state": "needs_choice", "entry": skill_entry(repo_path),
            "existing_plugins": appendable,
            "detail": "skill is not listed in any plugin; choose an existing plugin, a new plugin, or opt out"}


def apply(clone_dir: Path, repo_path: str, plugin: str | None = None,
          new_plugin: str | None = None, description: str | None = None) -> dict:
    """Write the registration. Exactly one of `plugin` / `new_plugin`. Raises ValueError
    on a bad choice (unknown plugin, name clash, missing description)."""
    path, raw, data = _load(clone_dir)
    entry = skill_entry(repo_path)
    plugins = data["plugins"]
    if plugin:
        target = next((pl for pl in plugins if isinstance(pl, dict) and pl.get("name") == plugin), None)
        if target is None or not isinstance(target.get("skills"), list):
            raise ValueError(f"no plugin named {plugin!r} with a skills[] list "
                             f"(have: {[p.get('name') for p in plugins if isinstance(p, dict)]})")
        target["skills"].append(entry)
        result = {"state": "registered", "plugin": plugin, "entry": entry, "created_plugin": False}
    else:
        if any(isinstance(pl, dict) and pl.get("name") == new_plugin for pl in plugins):
            raise ValueError(f"a plugin named {new_plugin!r} already exists; pass it as the existing-plugin choice instead")
        if not description:
            raise ValueError("a new plugin needs a description (--marketplace-description)")
        plugins.append({"name": new_plugin, "description": description, "source": "./",
                        "strict": False, "skills": [entry]})
        result = {"state": "registered", "plugin": new_plugin, "entry": entry, "created_plugin": True}
    # Preserve the file's own indent + trailing newline so the diff is just the registration.
    m = re.search(r'\n( +|\t)"', raw)
    indent = m.group(1) if m else "  "
    out = json.dumps(data, indent=indent, ensure_ascii=False)
    path.write_text(out + ("\n" if raw.endswith("\n") else ""), encoding="utf-8")
    return result


def main():
    ap = argparse.ArgumentParser(description="Inspect a clone's marketplace catalog for a skill")
    ap.add_argument("clone_dir")
    ap.add_argument("--repo-path", required=True)
    ap.add_argument("--json", action="store_true", help="(default) print the plan as JSON")
    args = ap.parse_args()
    print(json.dumps(plan(Path(args.clone_dir), args.repo_path), indent=2))
    sys.exit(0)


if __name__ == "__main__":
    main()
