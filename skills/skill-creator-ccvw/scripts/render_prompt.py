#!/usr/bin/env python3
"""Render one worker dispatch prompt from references/dispatch-prompts/<kind>.txt.

Input: --kind with_skill|baseline|grader|analyst and --var key=value pairs (repeatable).
helper_model defaults from skill_config (sonnet); scratch_dir must be given or configured, and an
empty scratch_dir counts as no value.
Output: the finished prompt on stdout. Exit 1, with a message on stderr, when a placeholder has no
value, a value contains an --forbid term (or the configured author identity), or helper_model
names Opus. The forbidden-term check skips the values that hold paths (PATH_KEYS: skill_path,
run_dir, input_files, scratch_dir, skill_creator_path, iteration_dir, baseline_source,
transcript_path, outputs_dir); it covers every other value, such as task and expectations. Every template starts with the framing line "You are the worker, no subagents,
cannot redelegate." so the dispatch rules live in one place; edit the template, not each prompt.
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import skill_config  # noqa: E402

KINDS = ("with_skill", "baseline", "grader", "analyst")
TEMPLATES = Path(__file__).resolve().parent.parent / "references" / "dispatch-prompts"
FRAME = "You are the worker, no subagents, cannot redelegate."
# Values that hold paths: an expanded home path can contain the login that author_identity
# names, and a path cannot be rewritten as "the user", so the forbidden-term check skips them.
PATH_KEYS = frozenset({"skill_path", "run_dir", "input_files", "scratch_dir", "skill_creator_path",
                       "iteration_dir", "baseline_source", "transcript_path", "outputs_dir"})


def render(kind, values, forbid=()):
    text = (TEMPLATES / f"{kind}.txt").read_text(encoding="utf-8")
    if not text.startswith(FRAME):
        raise ValueError(f"template {kind} lost the framing line")
    values = dict(values)
    values.setdefault("helper_model", skill_config.resolve("helper_model"))
    if "opus" in values["helper_model"].lower():
        raise ValueError("helper_model must not be Opus; helpers run on Sonnet")
    if kind == "baseline":
        values.setdefault("baseline_source", "")
    if kind == "grader":
        values.setdefault("inspection_hint", "")
    needed = set(re.findall(r"\{([a-z_]+)\}", text))
    missing = sorted(n for n in needed if n not in values or (n == "scratch_dir" and not values[n]))
    if missing:
        raise ValueError(f"no value for: {', '.join(missing)}")
    banned = [t for t in [*forbid, skill_config.resolve("author_identity")] if t]
    for k, v in values.items():
        if k in PATH_KEYS:
            continue
        for t in banned:
            if t.lower() in str(v).lower():
                raise ValueError(f"value of {k} contains forbidden term {t!r}; write 'the user' in its place")
    return re.sub(r"\{([a-z_]+)\}", lambda m: str(values[m.group(1)]), text)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--kind", required=True, choices=KINDS)
    ap.add_argument("--var", action="append", default=[], metavar="KEY=VALUE")
    ap.add_argument("--forbid", action="append", default=[])
    a = ap.parse_args(argv)
    values = {}
    for kv in a.var:
        if "=" not in kv:
            ap.error(f"--var needs KEY=VALUE, got {kv!r}")
        k, v = kv.split("=", 1)
        values[k] = v
    if not values.get("scratch_dir"):
        values["scratch_dir"] = skill_config.resolve("scratch_dir")
    try:
        sys.stdout.write(render(a.kind, values, a.forbid))
    except ValueError as exc:
        print(f"render_prompt: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
