"""Unit tests for the eval helper scripts. Run: python3 -m unittest discover -s tests (from the skill root)."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import aggregate_benchmark  # noqa: E402
import check_isolation  # noqa: E402
import eval_workspace  # noqa: E402
import loop_ledger  # noqa: E402
import merge_notes  # noqa: E402
import render_prompt  # noqa: E402
import skill_config  # noqa: E402
import validate_eval_set  # noqa: E402
import write_timing  # noqa: E402


class SkillConfig(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("CCVW_")}
        self._old = dict(os.environ)
        os.environ.clear()
        os.environ.update(self.env)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._old)

    def test_defaults_name_no_person(self):
        self.assertEqual(skill_config.resolve("helper_model", self.tmp / "none.md"), "sonnet")
        self.assertEqual(skill_config.resolve("author_identity", self.tmp / "none.md"), "")
        self.assertFalse(skill_config.session_log_enabled(self.tmp / "none.md"))

    def test_profile_then_env_override(self):
        prof = self.tmp / "p.md"
        prof.write_text("- `session_log_dir`: ~/logs\n- `helper_model`: haiku\n")
        self.assertTrue(skill_config.session_log_enabled(prof))
        self.assertEqual(skill_config.resolve("helper_model", prof), "haiku")
        os.environ["CCVW_HELPER_MODEL"] = "sonnet"
        self.assertEqual(skill_config.resolve("helper_model", prof), "sonnet")

    def test_off_switch(self):
        prof = self.tmp / "p.md"
        prof.write_text("- `session_log_dir`: off\n")
        self.assertFalse(skill_config.session_log_enabled(prof))

    def test_workspace_default_honours_xdg(self):
        os.environ["XDG_DATA_HOME"] = str(self.tmp)
        self.assertEqual(skill_config.resolve("eval_workspace", self.tmp / "none.md"),
                         str(self.tmp / "skill-creator-evals-ledger"))


class EvalWorkspace(unittest.TestCase):
    def setUp(self):
        self.ws = tempfile.mkdtemp()

    def test_creates_tree_with_integer_ids(self):
        evals = [{"id": 0, "prompt": "Make a chart of sales"}, {"id": 1, "prompt": "Fix typos", "name": "typos"}]
        r = eval_workspace.build(self.ws, 1, evals, ["with_skill", "without_skill"])
        self.assertTrue(r["ok"])
        meta = json.loads((Path(self.ws) / "iteration-1" / "eval-typos" / "eval_metadata.json").read_text())
        self.assertEqual(meta["eval_id"], 1)
        self.assertIsInstance(meta["eval_id"], int)
        self.assertTrue((Path(self.ws) / "iteration-1" / "eval-typos" / "without_skill" / "run-1" / "outputs").is_dir())

    def test_refuses_duplicate_ids_and_string_ids(self):
        self.assertFalse(eval_workspace.build(self.ws, 1, [{"id": 0, "prompt": "a"}, {"id": 0, "prompt": "b"}], [])["ok"])
        self.assertFalse(eval_workspace.build(self.ws, 1, [{"id": "0", "prompt": "a"}], [])["ok"])

    def test_refuses_existing_eval_in_iteration(self):
        evals = [{"id": 0, "prompt": "a", "name": "one"}]
        self.assertTrue(eval_workspace.build(self.ws, 1, evals, [])["ok"])
        self.assertFalse(eval_workspace.build(self.ws, 1, evals, [])["ok"])
        self.assertTrue(eval_workspace.build(self.ws, 2, evals, [])["ok"])

    def test_pilot_only_and_bad_config(self):
        evals = [{"id": 0, "prompt": "a", "name": "one"}, {"id": 1, "prompt": "b", "name": "two"}]
        r = eval_workspace.build(self.ws, 1, evals, ["with_skill", "old_skill"], only={0})
        self.assertTrue(r["ok"])
        self.assertEqual(len(r["created"]), 1)
        self.assertFalse((Path(self.ws) / "iteration-1" / "eval-one" / "without_skill").exists())
        self.assertTrue(eval_workspace.build(self.ws, 1, evals, ["with_skill", "old_skill"], only={1})["ok"])
        self.assertFalse(eval_workspace.build(self.ws, 5, evals, ["new_skill-prev"])["ok"])
        self.assertFalse(eval_workspace.build(self.ws, 3, evals, ["treatment"])["ok"])
        self.assertFalse(eval_workspace.build(self.ws, 4, evals, [], only={9})["ok"])


class CheckIsolation(unittest.TestCase):
    CLEAN = "## Eval Prompt\n\nDo X\n\n## Isolation Check\n- /tmp/work/input.txt\n"

    def test_clean(self):
        hits, problems = check_isolation.check(self.CLEAN, "my-skill")
        self.assertEqual((hits, problems), ([], []))

    def test_hits_name_skillmd_and_skills_path(self):
        t = self.CLEAN + "- /home/u/.claude/skills/other/SKILL.md\n- /w/my-skill/notes.md\n"
        hits, _ = check_isolation.check(t, "My-Skill")
        self.assertEqual({h["kind"] for h in hits}, {"skill name", "SKILL.md path", "/skills/ path"})

    def test_prose_naming_strings_is_not_a_hit(self):
        t = self.CLEAN + "No zzz path and no /skills/ path was accessed; zzz stayed untouched.\n"
        self.assertEqual(check_isolation.check(t, "zzz")[0], [])

    def test_quoted_constraint_is_not_a_hit(self):
        t = self.CLEAN + "Hard constraints: do not read, list, grep or otherwise access any file or directory whose path contains `/skills/` or `zzz`\n"
        self.assertEqual(check_isolation.check(t, "zzz")[0], [])

    def test_own_skill_md_is_not_a_hit(self):
        t = self.CLEAN + "- wrote SKILL.md and meeting/SKILL.md\n- /w/run/outputs/skill/x/SKILL.md\n"
        self.assertEqual(check_isolation.check(t, "zzz", own_dir="/w/run")[0], [])
        self.assertTrue(check_isolation.check(t, "zzz")[0])

    def test_allow_and_missing_section(self):
        t = "## Isolation Check\n- /x/skills/proofread\n"
        hits, _ = check_isolation.check(t, "zzz", allow=["/x/skills/proofread"])
        self.assertEqual(hits, [])
        _, problems = check_isolation.check("no section here", "zzz")
        self.assertTrue(problems)

    def test_allow_covers_the_whole_path_token(self):
        t = "## Isolation Check\n- /ws/zzz/skill-snapshot/SKILL.md\n- /x/skills/proofread/SKILL.md\n"
        self.assertTrue(check_isolation.check(t, "zzz")[0])
        hits, _ = check_isolation.check(t, "zzz", allow=["/ws/zzz/skill-snapshot", "/x/skills/proofread"])
        self.assertEqual(hits, [])
        hits, _ = check_isolation.check(t, "zzz", allow=["/ws/zzz/skill-snapshot"])
        self.assertEqual({h["line"] for h in hits}, {"/x/skills/proofread/SKILL.md"})

    def test_cli_attempt_cap(self):
        d = Path(tempfile.mkdtemp())
        (d / "transcript.md").write_text("## Isolation Check\n- /a/skills/x\n")
        out = None
        for _ in range(3):
            p = subprocess.run([sys.executable, str(ROOT / "scripts" / "check_isolation.py"), "--transcript",
                                str(d / "transcript.md"), "--skill-name", "q", "--run-dir", str(d)],
                               capture_output=True, text=True)
            self.assertEqual(p.returncode, 1)
            out = json.loads(p.stdout)
        self.assertTrue(out["cap_reached"])
        self.assertEqual(out["failures"], 3)

    def test_cli_missing_file_exit_2(self):
        p = subprocess.run([sys.executable, str(ROOT / "scripts" / "check_isolation.py"), "--transcript",
                            "/nonexistent/t.md", "--skill-name", "q"], capture_output=True, text=True)
        self.assertEqual(p.returncode, 2)

    def test_cli_missing_file_counts_toward_cap(self):
        d = Path(tempfile.mkdtemp())
        out = None
        for _ in range(3):
            p = subprocess.run([sys.executable, str(ROOT / "scripts" / "check_isolation.py"), "--transcript",
                                str(d / "transcript.md"), "--skill-name", "q", "--run-dir", str(d)],
                               capture_output=True, text=True)
            self.assertEqual(p.returncode, 2)
            out = json.loads(p.stdout)
        self.assertTrue(out["cap_reached"])
        self.assertEqual(out["failures"], 3)


class WriteTiming(unittest.TestCase):
    def test_values_and_zero_fallback(self):
        self.assertEqual(write_timing.build(84852, 23332),
                         {"total_tokens": 84852, "duration_ms": 23332, "total_duration_seconds": 23.332})
        self.assertEqual(write_timing.build(None, None)["duration_ms"], 0)
        self.assertEqual(write_timing.build(5, None), {"total_tokens": 5, "duration_ms": 0, "total_duration_seconds": 0.0})
        with self.assertRaises(ValueError):
            write_timing.build(-1, 0)

    def test_cli_writes_file_and_rejects_missing_dir(self):
        d = tempfile.mkdtemp()
        self.assertEqual(write_timing.main(["--run-dir", d, "--duration-ms", "1500"]), 0)
        self.assertEqual(json.loads((Path(d) / "timing.json").read_text())["total_duration_seconds"], 1.5)
        self.assertEqual(write_timing.main(["--run-dir", d + "/nope"]), 1)


class MergeNotes(unittest.TestCase):
    def mk(self, bench, notes):
        d = Path(tempfile.mkdtemp())
        (d / "benchmark.json").write_text(json.dumps(bench))
        if notes is not None:
            (d / "analyst-notes.json").write_text(notes if isinstance(notes, str) else json.dumps(notes))
        return d

    def test_merge(self):
        d = self.mk({"runs": [{}], "notes": []}, ["a", "b"])
        self.assertEqual(merge_notes.merge(d)[0], True)
        self.assertEqual(json.loads((d / "benchmark.json").read_text())["notes"], ["a", "b"])

    def test_empty_valid_only_with_runs(self):
        self.assertTrue(merge_notes.merge(self.mk({"runs": [{}]}, []))[0])
        self.assertFalse(merge_notes.merge(self.mk({"runs": []}, []))[0])
        self.assertFalse(merge_notes.merge(self.mk({}, []))[0])

    def test_bad_shapes(self):
        self.assertFalse(merge_notes.merge(self.mk({"runs": [{}]}, {}))[0])
        self.assertFalse(merge_notes.merge(self.mk({"runs": [{}]}, "not json"))[0])
        self.assertFalse(merge_notes.merge(self.mk({"runs": [{}]}, None))[0])
        self.assertFalse(merge_notes.merge(self.mk({"runs": [{}]}, [1, 2]))[0])


class RenderPrompt(unittest.TestCase):
    BASE = {"scratch_dir": "/scratch", "run_dir": "/ws/r1", "skill_path": "/s", "task": "t",
            "input_files": "none", "outputs_wanted": "a file", "skill_name": "foo", "helper_model": "sonnet"}

    def test_every_prompt_has_framing_and_sonnet(self):
        for kind, extra in (("with_skill", {}), ("baseline", {}),
                            ("grader", {"skill_creator_path": "/c", "expectations": "[]", "transcript_path": "/t",
                                        "outputs_dir": "/o"}),
                            ("analyst", {"skill_creator_path": "/c", "iteration_dir": "/i"})):
            out = render_prompt.render(kind, {**self.BASE, **extra})
            self.assertTrue(out.startswith("You are the worker, no subagents, cannot redelegate."), kind)
            self.assertIn("sonnet", out)

    def test_baseline_has_isolation_section_instruction(self):
        out = render_prompt.render("baseline", self.BASE)
        self.assertIn("## Isolation Check", out)
        self.assertIn("`/skills/`", out)

    def test_refusals(self):
        with self.assertRaises(ValueError):
            render_prompt.render("with_skill", {k: v for k, v in self.BASE.items() if k != "task"})
        with self.assertRaises(ValueError):
            render_prompt.render("with_skill", {**self.BASE, "helper_model": "Opus"})
        with self.assertRaises(ValueError):
            render_prompt.render("with_skill", {**self.BASE, "scratch_dir": ""})
        with self.assertRaises(ValueError):
            render_prompt.render("with_skill", {**self.BASE, "task": "email Jane Doe"}, forbid=["jane doe"])

    def test_forbidden_term_skips_path_values(self):
        out = render_prompt.render("with_skill", {**self.BASE, "run_dir": "/Users/jdoe/ws/r1"}, forbid=["jdoe"])
        self.assertIn("/Users/jdoe/ws/r1", out)
        with self.assertRaises(ValueError):
            render_prompt.render("with_skill", {**self.BASE, "task": "ask jdoe"}, forbid=["jdoe"])


class LoopLedger(unittest.TestCase):
    def run_rounds(self, rounds, cap=3):
        led = {"cap": cap, "rounds": []}
        out = None
        for i, (findings, resolved) in enumerate(rounds, 1):
            led["rounds"].append({"round": i, "findings": findings, "resolved": resolved})
            out = loop_ledger.decide(led)
        return out

    def f(self, text):
        return {"text": text, "where": "x"}

    def test_ids_are_stable(self):
        a = loop_ledger.finding_id({"text": "Bad  thing", "where": "A"})
        self.assertEqual(a, loop_ledger.finding_id({"text": "bad thing", "where": "a"}))

    def test_clean_pass(self):
        self.assertEqual(self.run_rounds([([self.f("a")], []), ([], [])])["reason"], "clean_pass")

    def test_cap(self):
        r = self.run_rounds([([self.f("a")], []), ([self.f("b")], []), ([self.f("c")], [])])
        self.assertEqual((r["stop"], r["reason"]), (True, "cap"))

    def test_regressed(self):
        fa = self.f("a")
        fid = loop_ledger.finding_id(fa)
        r = self.run_rounds([([fa], [fid]), ([fa], [])])
        self.assertEqual(r["regressed"], [fid])
        self.assertFalse(r["stop"])

    def test_no_progress(self):
        fa = self.f("a")
        r = self.run_rounds([([fa], []), ([fa], [])], cap=5)
        self.assertEqual(r["reason"], "no_progress")

    def test_cli_record_and_duplicate_round(self):
        d = Path(tempfile.mkdtemp())
        (d / "f.json").write_text(json.dumps([self.f("a")]))
        args = ["--ledger", str(d / "l.json"), "--round", "1", "--findings", str(d / "f.json")]
        self.assertEqual(loop_ledger.main(["record", *args]), 0)
        self.assertEqual(loop_ledger.main(["record", *args]), 1)


class AggregateBenchmark(unittest.TestCase):
    def test_runs_per_configuration_counts_runs_per_eval(self):
        d = Path(tempfile.mkdtemp())
        grading = {"summary": {"pass_rate": 1.0, "passed": 1, "failed": 0, "total": 1}, "expectations": []}
        for i in range(3):
            for config in ("with_skill", "without_skill"):
                run = d / f"eval-{i}" / config / "run-1"
                run.mkdir(parents=True)
                (run / "grading.json").write_text(json.dumps(grading))
        bench = aggregate_benchmark.generate_benchmark(d)
        self.assertEqual(bench["metadata"]["runs_per_configuration"], 1)
        self.assertEqual(bench["metadata"]["evals_run"], [0, 1, 2])


class ValidateEvalSet(unittest.TestCase):
    def test_duplicate_query_is_an_error(self):
        data = [{"query": "make a chart", "should_trigger": True},
                {"query": "other", "should_trigger": False},
                {"query": "make a chart", "should_trigger": False}]
        out = validate_eval_set.validate(data)
        self.assertFalse(out["valid"])
        self.assertTrue(any("duplicate" in e and "item[0]" in e and "make a chart" in e for e in out["errors"]))

    def test_unique_queries_have_no_duplicate_error(self):
        out = validate_eval_set.validate([{"query": "a", "should_trigger": True},
                                          {"query": "b", "should_trigger": False}])
        self.assertFalse(any("duplicate" in e for e in out["errors"]))


if __name__ == "__main__":
    unittest.main()
