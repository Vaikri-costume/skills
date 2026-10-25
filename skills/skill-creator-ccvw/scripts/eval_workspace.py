#!/usr/bin/env python3
"""Create one iteration's eval tree and its eval_metadata.json files.

Input: --workspace DIR --iteration N and an evals file (--evals PATH, the skill's
evals/evals.json: {"evals": [{"id": 0, "prompt": "...", "name": "optional-slug"}]}).
Output: DIR/iteration-N/eval-<name>/eval_metadata.json ({"eval_id": int, "eval_name", "prompt"})
and, for each --configs entry, eval-<name>/<config>/run-1/outputs/. Prints a JSON summary.

Refusals (exit 1, nothing partly written): duplicate or non-integer ids, duplicate names,
an iteration directory that already holds an eval with the same id or name, an unusable
config name. --only 0,1 limits the build to those ids (the one-item pilot before a batch).
"""
import argparse
import json
import re
import sys
from pathlib import Path

RECOGNISED = ("with_skill", "without_skill", "new_skill", "old_skill")
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,60}$")


def slugify(text):
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:40].strip("-") or "eval"


def config_ok(name):
    return name in RECOGNISED


def plan(evals, only=None):
    problems, items, seen_ids, seen_names = [], [], set(), set()
    for i, e in enumerate(evals):
        eid = e.get("id")
        if isinstance(eid, bool) or not isinstance(eid, int):
            problems.append(f"entry {i}: id must be a JSON integer, got {eid!r}")
            continue
        if eid in seen_ids:
            problems.append(f"duplicate id {eid}")
        seen_ids.add(eid)
        name = e.get("name") or slugify(e.get("prompt", ""))
        if not SLUG.match(name):
            problems.append(f"id {eid}: name {name!r} is not a lowercase slug")
        if name in seen_names:
            problems.append(f"duplicate name {name}")
        seen_names.add(name)
        if not e.get("prompt"):
            problems.append(f"id {eid}: empty prompt")
        items.append({"eval_id": eid, "eval_name": name, "prompt": e.get("prompt", "")})
    if only is not None:
        missing = only - seen_ids
        if missing:
            problems.append(f"--only names ids not in the evals file: {sorted(missing)}")
        items = [x for x in items if x["eval_id"] in only]
    return items, problems


def build(workspace, iteration, evals, configs, only=None):
    problems = [f"config {c!r} is not a recognised name (with_skill, without_skill, new_skill, old_skill)"
                for c in configs if not config_ok(c)]
    items, more = plan(evals, only)
    problems += more
    it_dir = Path(workspace) / f"iteration-{iteration}"
    if it_dir.is_dir():
        for x in items:
            for meta in it_dir.glob("eval-*/eval_metadata.json"):
                try:
                    old = json.loads(meta.read_text())
                except ValueError:
                    continue
                if old.get("eval_id") == x["eval_id"] or old.get("eval_name") == x["eval_name"]:
                    problems.append(f"{meta.parent.name} already holds eval id {old.get('eval_id')} / name {old.get('eval_name')}")
    if problems:
        return {"ok": False, "problems": problems}
    created = []
    for x in items:
        d = it_dir / f"eval-{x['eval_name']}"
        d.mkdir(parents=True, exist_ok=True)
        (d / "eval_metadata.json").write_text(json.dumps(x, indent=2) + "\n")
        for c in configs:
            (d / c / "run-1" / "outputs").mkdir(parents=True, exist_ok=True)
        created.append(str(d))
    return {"ok": True, "iteration_dir": str(it_dir), "created": created}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workspace", required=True)
    ap.add_argument("--iteration", type=int, required=True)
    ap.add_argument("--evals", required=True)
    ap.add_argument("--configs", default="with_skill,without_skill")
    ap.add_argument("--only", help="comma-separated eval ids (pilot)")
    a = ap.parse_args(argv)
    try:
        data = json.loads(Path(a.evals).read_text())
    except (OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "problems": [f"cannot read evals file: {exc}"]}))
        return 1
    only = {int(x) for x in a.only.split(",")} if a.only else None
    result = build(a.workspace, a.iteration, data.get("evals", []), [c for c in a.configs.split(",") if c], only)
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
