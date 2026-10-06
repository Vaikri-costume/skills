"""Code-review scope (scripts/code_review_run.py), the collector's block-count contract and scope-aware
convergence (scripts/code_review_collect.py), and the advisory doc lint (scripts/doc_lint.py).
Run: python3 -m unittest discover -s tests   (from the skill root)."""
import json, subprocess, sys, tempfile, unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import ledger_common as lc  # noqa: E402
import code_review_run as crr  # noqa: E402

RT = "2026-10-05T10:00:00"


def run(script, *args, stdin=None):
    return subprocess.run([sys.executable, str(SCRIPTS / script), *args], input=stdin,
                          capture_output=True, text=True)


def transcript(path: Path, reads: list, final: str) -> str:
    """A minimal agent JSONL transcript: one whole-file Read per path, then the final text."""
    lines = [json.dumps({"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "tool_use", "id": f"r{i}", "name": "Read", "input": {"file_path": str(f)}}]}})
        for i, f in enumerate(reads)]
    lines.append(json.dumps({"type": "assistant", "message": {"role": "assistant",
                                                               "content": [{"type": "text", "text": final}]}}))
    path.write_text("\n".join(lines) + "\n")
    return str(path)


def issue(n: int) -> str:
    return (f"ISSUE [stale-ref]: finding {n}\nFile: a.md\nClaim: a.md:1 \"alpha\"\n"
            f"Target: b.py:1 \"x = {n}\"\n")


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name).resolve()
        self.tgt = base / "target"
        self.tgt.mkdir()
        (self.tgt / "SKILL.md").write_text("---\nname: t\n---\n# T\n")
        (self.tgt / "a.md").write_text("alpha\n")
        (self.tgt / "b.py").write_text("x = 1\n")
        self.led = base / "t.md"
        self.out = base / "out"
        self.out.mkdir()
        r = run("append_ledger.py", "begin-round", str(self.led), "--round", "1", "--runtime", RT,
                "--target", str(self.tgt), "--set", "run-start-round=1")
        self.assertEqual(r.returncode, 0, r.stderr)

    def tearDown(self):
        self._tmp.cleanup()

    def fix_row(self, rnd, cid, address):
        r = run("append_ledger.py", "append", str(self.led), "--runtime", RT, "--round", str(rnd),
                "--phase", "Code Review", "--cluster", cid, "--root-cause", "x", "--flags", "G11",
                "--address", address, "--blast-radius-status", "n/a: single-site change, no shared token")
        self.assertEqual(r.returncode, 0, r.stderr)


class Scope(Base):
    def test_rounds_1_and_2_are_full(self):
        self.fix_row(1, "C1", "FIX (a.md: edit)")
        for rnd in (1, 2):
            self.assertEqual(crr.decide_scope("auto", self.led, self.tgt, rnd)["scope"], "full")

    def test_round_3_reviews_only_changed_files(self):
        self.fix_row(2, "C1", "FIX (a.md: edit)")
        s = crr.decide_scope("auto", self.led, self.tgt, 3)
        self.assertEqual(s["scope"], "changed")
        self.assertEqual([p.name for p in s["files"]], ["a.md"])
        self.assertEqual(crr.decide_scope("full", self.led, self.tgt, 3)["scope"], "full")

    def test_round_3_with_no_named_file_falls_back_to_full(self):
        self.fix_row(2, "C1", "FIX (elsewhere.txt: edit)")
        self.assertEqual(crr.decide_scope("auto", self.led, self.tgt, 3)["scope"], "full")

    def test_run_writes_scope_record_and_two_generalists(self):
        self.fix_row(2, "C1", "FIX (b.py: edit)")
        r = run("code_review_run.py", "--target", str(self.tgt), "--ledger", str(self.led), "--round", "3",
                "--runtime", RT, "--out-dir", str(self.out))
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual(out["scope"]["scope"], "changed")
        self.assertEqual([(d["flag"], d["model"]) for d in out["dispatch"]], [("G1", "sonnet"), ("G2", "sonnet")])
        rec = json.loads(crr.scope_path(self.out, 3, RT).read_text())
        self.assertEqual([Path(f).name for f in rec["files"]], ["b.py"])
        self.assertIn("code-review dispatched round-3", self.led.read_text())

    def test_g2_reads_in_reverse_order_from_round_2_only(self):
        def prompts(rnd):
            r = run("code_review_run.py", "--target", str(self.tgt), "--ledger", str(self.led), "--round",
                    str(rnd), "--runtime", RT, "--out-dir", str(self.out))
            self.assertEqual(r.returncode, 0, r.stderr)
            return {d["flag"]: Path(d["prompt"]).read_text() for d in json.loads(r.stdout)["dispatch"]}
        first = prompts(1)
        self.assertEqual(first["G1"], first["G2"])
        self.assertNotIn(crr.G2_REVERSE_ORDER_LINE, first["G2"])
        second = prompts(2)
        self.assertNotIn(crr.G2_REVERSE_ORDER_LINE, second["G1"])
        self.assertIn(crr.G2_REVERSE_ORDER_LINE, second["G2"])
        self.assertEqual(second["G2"].replace("\n\n" + crr.G2_REVERSE_ORDER_LINE, ""), second["G1"])


class Collector(Base):
    def collect(self, rnd, finals, reads):
        paths = [transcript(Path(self._tmp.name) / f"g{i}.jsonl", reads, f) for i, f in enumerate(finals, 1)]
        return run("code_review_collect.py", "--agent-transcripts", ",".join(paths), "--agent-flags", "G1,G2",
                   "--target", str(self.tgt), "--ledger", str(self.led), "--round", str(rnd),
                   "--runtime", RT, "--out-dir", str(self.out))

    def all_files(self):
        return [self.tgt / "SKILL.md", self.tgt / "a.md", self.tgt / "b.py"]

    def test_more_blocks_than_declared_is_a_contract_violation(self):
        r = self.collect(1, [issue(1) + issue(2) + "No of issues found:: 1", "No issues found"], self.all_files())
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("more", r.stderr)

    def test_fewer_blocks_than_declared_is_a_contract_violation(self):
        r = self.collect(1, [issue(1) + "No of issues found:: 2", "No issues found"], self.all_files())
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("fewer", r.stderr)

    def test_full_sweep_clean_is_code_review_clean(self):
        r = self.collect(1, ["No issues found", "No issues found"], self.all_files())
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["status"], "code-review-clean")

    def test_changed_scope_clean_is_not_convergence(self):
        self.fix_row(2, "C1", "FIX (a.md: edit)")
        self.assertEqual(run("code_review_run.py", "--target", str(self.tgt), "--ledger", str(self.led),
                             "--round", "3", "--runtime", RT, "--out-dir", str(self.out)).returncode, 0)
        # The changed-scope coverage gate needs only the listed file.
        r = self.collect(3, ["No issues found", "No issues found"], [self.tgt / "a.md"])
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual((out["status"], out["next"]), ("changed-scope-clean", "full-sweep"))

    def test_withdrawn_block_is_not_counted(self):
        withdrawn = ("ISSUE [stale-ref]: candidate\nFile: a.md\nClaim: a.md:1 \"alpha\"\n"
                     "Target: Withdrawn — the script agrees.\n")
        r = self.collect(1, [issue(1) + withdrawn + "No of issues found:: 1", "No issues found"], self.all_files())
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len(json.loads(r.stdout)["flags"]), 1)

    def test_template_and_alllens_framing(self):
        tpl = (SCRIPTS.parent / "templates" / "agent-cold-code-review.md").read_text()
        self.assertIn("counts the surviving `ISSUE` blocks only", tpl)
        prompt = crr._build_alllens_prompt("x", "y", tpl)
        self.assertIn("3-4 times the defects per line", prompt)
        self.assertNotIn("### Lens F", prompt)

    def test_verified_flags_numbered_per_agent(self):
        r = self.collect(1, [issue(1) + "No of issues found:: 1", "No issues found"], self.all_files())
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["status"], "verified-flags")


class DocLint(unittest.TestCase):
    def test_fixed_checks_fire(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "references").mkdir()
            (root / "scripts").mkdir()
            (root / "SKILL.md").write_text(
                "# S\n\nSee references/x.md \"Missing Section\".\n\nPer rule 4 below.\n\n"
                "The three steps:\n- one\n- two\n\n1. first\n2. second\n")
            (root / "references" / "x.md").write_text("# X\n\n## Present\n")
            (root / "references" / "glossary.md").write_text("# G\n\n| Term | Definition |\n|---|---|\n")
            (root / "scripts" / "s.py").write_text(
                '"""s.\n\nUsage:\n    s.py --real --ghost\n"""\nimport argparse, sys\n'
                'def main():\n    ap = argparse.ArgumentParser()\n    ap.add_argument("--real")\n'
                '    ap.parse_args()\n    return 3\n\nsys.exit(main())\n')
            (root / "references" / "script-contract.md").write_text(
                "| Script | Exit | Action |\n|---|---|---|\n| `s.py` | 1 = never | x |\n")
            r = run("doc_lint.py", "--target", str(root))
            self.assertEqual(r.returncode, 0, r.stderr)
            checks = {f["check"] for f in json.loads(r.stdout)["findings"]}
            for c in ("section-ref", "ordinal-ref", "list-count", "exit-codes", "usage-flags"):
                self.assertIn(c, checks)

    def test_retired_term_doc_count_and_dollar_var(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "scripts").mkdir()
            (root / "tests").mkdir()
            (root / "SKILL.md").write_text("---\nname: skill-tracer\n---\n`$KNOWN_VAR` is the base.\n")
            (root / "notes.md").write_text("Use $KNOWN_VAR and $MYSTERY_VAR and $HOME.\n"
                                           "The minor-bugs tier runs here.\n\n\n\n"
                                           "Legacy compatibility: a minor-bugs marker still parses.\n")
            (root / "tests" / "t.py").write_text("# minor-bugs fixture\n")
            (root / "scripts" / "s.py").write_text('"""s.\n\nTwo checks:\n  a  one\n  b  two\n  c  three\n"""\n')
            r = run("doc_lint.py", "--target", str(root))
            self.assertEqual(r.returncode, 0, r.stderr)
            found = [(f["check"], f["file"], f["line"]) for f in json.loads(r.stdout)["findings"]]
            self.assertIn(("retired-term", "notes.md", 2), found)
            self.assertNotIn(("retired-term", "notes.md", 6), found)  # says it is legacy compatibility
            self.assertFalse(any(c == "retired-term" and f.startswith("tests/") for c, f, _ in found))
            self.assertIn(("doc-count", "scripts/s.py", 3), found)
            dollars = [f["detail"] for f in json.loads(r.stdout)["findings"] if f["check"] == "dollar-var"]
            self.assertEqual(len(dollars), 1)
            self.assertIn("MYSTERY_VAR", dollars[0])
            # another skill's text is not held to skill-tracer's retired terms
            (root / "SKILL.md").write_text("---\nname: other\n---\n")
            r = run("doc_lint.py", "--target", str(root), "--checks", "retired-term")
            self.assertEqual(json.loads(r.stdout)["count"], 0)

    def test_code_hygiene_checks(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "scripts").mkdir()
            (root / "tests").mkdir()
            (root / "SKILL.md").write_text("---\nname: other\n---\n")
            (root / "scripts" / "s.py").write_text(
                '"""s.\n\nFix applied: the parser now skips blanks.\n"""\n'
                "import sys\n\n\n"
                "def ok(a, _b, *args, **kw):\n"
                '    """Raises ValueError on a bad value."""\n'
                "    if a or args or kw:\n        raise ValueError(a)\n\n\n"
                "def lies(path, text):\n"
                '    """Read it.\n\n    Raises KeyError when absent.\n    """\n'
                "    # C3 fix: strip the text first\n"
                "    return text.strip()\n\n\n"
                "def stub(x):\n    raise NotImplementedError\n\n\n"
                "def nested(y):\n"
                '    """Raises OSError."""\n'
                "    def inner():\n        raise OSError(y)\n    return inner\n\n\n"
                "class K:\n    def m(self, cls_arg):\n        return 1\n")
            (root / "tests" / "t.py").write_text("def f(unused):\n    return 1  # fix applied\n")
            r = run("doc_lint.py", "--target", str(root),
                    "--checks", "fix-narration,raises-no-raise,unused-param")
            self.assertEqual(r.returncode, 0, r.stderr)
            found = {(f["check"], f["line"], f["detail"].split("(")[0].split(":")[0])
                     for f in json.loads(r.stdout)["findings"]}
            checks = sorted((c, n) for c, n, _ in found)
            self.assertEqual(checks, [("fix-narration", 1), ("fix-narration", 19), ("raises-no-raise", 14),
                                      ("raises-no-raise", 27), ("unused-param", 14), ("unused-param", 35)])
            details = " ".join(f["detail"] for f in json.loads(r.stdout)["findings"])
            self.assertIn("'path'", details)
            self.assertIn("'cls_arg'", details)
            self.assertNotIn("'_b'", details)
            self.assertNotIn("'x'", details)  # a raise-only stub is skipped

    def test_bad_target_exits_2(self):
        self.assertEqual(run("doc_lint.py", "--target", "/nonexistent/x").returncode, 2)


if __name__ == "__main__":
    unittest.main()
