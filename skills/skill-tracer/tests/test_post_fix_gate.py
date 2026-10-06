"""Post-fix gate (scripts/post_fix_gate.py): snapshot / check, merge-check and survival.
Run: python3 -m unittest discover -s tests   (from the skill root)."""
import json, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import post_fix_gate as pfg  # noqa: E402

TOOL = '''"""tool.py: a small fixture script.

Usage:
    tool.py --alpha <value>

Exit 0 = done, 1 = nothing found.
"""
import argparse
import sys


def count_items(values):
    return len(values)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--alpha", required=True)
    args = ap.parse_args()
    if not args.alpha:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''

GUIDE = """# Guide

Run `scripts/tool.py --alpha x` to count items with `count_items`.

Notes for the reader.
"""

OTHER = """# Other

Two things:
- one
- two
- three
"""


def gate(*args):
    return subprocess.run([sys.executable, str(SCRIPTS / "post_fix_gate.py"), *args],
                          capture_output=True, text=True)


class GateCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.root = self.tmp / "skill"
        (self.root / "references").mkdir(parents=True)
        (self.root / "scripts").mkdir()
        (self.root / "SKILL.md").write_text("---\nname: fixture\n---\n# Fixture\n\nSee references/guide.md.\n")
        (self.root / "references" / "guide.md").write_text(GUIDE)
        (self.root / "references" / "other.md").write_text(OTHER)  # pre-existing list-count finding
        (self.root / "scripts" / "tool.py").write_text(TOOL)
        self.snap = self.tmp / "snap.json"
        r = gate("snapshot", "--target", str(self.root), "--out", str(self.snap))
        self.assertEqual(r.returncode, 0, r.stderr)

    def edit(self, rel, old, new):
        p = self.root / rel
        text = p.read_text()
        self.assertIn(old, text)
        p.write_text(text.replace(old, new, 1))

    def check(self):
        r = gate("check", "--target", str(self.root), "--snapshot", str(self.snap))
        return r.returncode, (json.loads(r.stdout) if r.stdout.strip() else {"stderr": r.stderr})

    def kinds(self, report):
        return {p["kind"] for p in report.get("problems", [])}


class Check(GateCase):
    def test_untouched_tree_passes(self):
        rc, rep = self.check()
        self.assertEqual((rc, rep["ok"]), (0, True))

    def test_unrelated_pre_existing_finding_does_not_block(self):
        self.edit("references/guide.md", "Notes for the reader.", "Notes for every reader.")
        rc, rep = self.check()
        self.assertEqual(rc, 0, rep)
        self.assertGreaterEqual(rep["pre_existing_findings"], 1)

    def test_new_lint_finding_blocks(self):
        self.edit("references/guide.md", "Notes for the reader.", "Three steps:\n- a\n- b\n")
        rc, rep = self.check()
        self.assertEqual(rc, 1)
        self.assertIn("lint:list-count", self.kinds(rep))

    def test_touched_stale_flag_blocks(self):
        self.edit("references/guide.md", "--alpha x", "--beta x")
        rc, rep = self.check()
        self.assertEqual(rc, 1)
        self.assertIn("unresolved-flag", self.kinds(rep))
        self.assertEqual(rep["problems"][0]["file"], "references/guide.md")

    def test_touched_missing_path_and_identifier_block(self):
        self.edit("references/guide.md", "Notes for the reader.",
                  "Then run scripts/gone.py and call `missing_helper()`.")
        rc, rep = self.check()
        self.assertEqual(rc, 1)
        self.assertTrue({"unresolved-path", "unresolved-identifier"} <= self.kinds(rep), rep)

    def test_new_raise_in_python_blocks(self):
        self.edit("scripts/tool.py", "    return len(values)",
                  "    if not values:\n        raise ValueError(\"empty\")\n    return len(values)")
        rc, rep = self.check()
        self.assertEqual(rc, 1)
        pause = [p for p in rep["problems"] if p["kind"] == "new-behaviour"]
        self.assertTrue(any("raise count 0 -> 1" in p["problem"] for p in pause), rep)
        self.assertTrue(all("ORCHESTRATOR-PAUSE" in p["problem"] for p in pause))

    def test_new_conditional_expression_and_or_block(self):
        self.edit("scripts/tool.py", "    return len(values)",
                  "    return len(values) if values else 0")
        rc, rep = self.check()
        self.assertEqual(rc, 1)
        self.assertTrue(any("ifexp count" in p["problem"] for p in rep["problems"]), rep)

    def test_accepted_refactor_waiver_passes(self):
        self.edit("scripts/tool.py", "    return len(values)",
                  "    return len(values) if values else 0")
        r = gate("check", "--target", str(self.root), "--snapshot", str(self.snap),
                 "--accept-new-behaviour", "scripts/tool.py:ifexp")
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_reworded_python_line_passes(self):
        self.edit("scripts/tool.py", "a small fixture script", "a fixture script used by the tests")
        rc, rep = self.check()
        self.assertEqual(rc, 0, rep)

    def test_renamed_function_with_stale_sibling_blocks(self):
        self.edit("scripts/tool.py", "def count_items(", "def tally_items(")
        rc, rep = self.check()
        self.assertEqual(rc, 1)
        stale = [p for p in rep["problems"] if p["kind"] == "stale-sibling"]
        self.assertEqual([(p["file"], p["line"]) for p in stale], [("references/guide.md", 3)])

    def test_siblings_lists_untouched_lines_naming_a_touched_term(self):
        self.edit("references/guide.md", "Notes for the reader.", "Notes: pass `--alpha` once.")
        rc, rep = self.check()
        self.assertEqual(rc, 0, rep)  # non-blocking
        [sib] = rep["siblings"]
        self.assertEqual((sib["term"], sib["touched"]), ("--alpha", ["references/guide.md:5"]))
        self.assertEqual(sib["others"], ["references/guide.md:3", "scripts/tool.py:4", "scripts/tool.py:18"])
        self.assertLessEqual(len(sib["others"]), pfg.SIBLING_CAP)

    def test_siblings_ignore_python_code_lines(self):
        self.edit("scripts/tool.py", "    return len(values)", "    return len(list(values))")
        rc, rep = self.check()
        self.assertEqual((rc, rep["siblings"]), (0, []), rep)

    def write_second_script(self):
        (self.root / "scripts" / "example.py").write_text(
            'import argparse\nap = argparse.ArgumentParser()\nap.add_argument("--token")\n')
        r = gate("snapshot", "--target", str(self.root), "--out", str(self.snap))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_flag_in_a_script_resolves_against_that_script(self):
        self.write_second_script()
        self.edit("scripts/tool.py", "Exit 0 = done, 1 = nothing found.",
                  "Exit 0 = done, 1 = nothing found: supply --token.")
        rc, rep = self.check()
        self.assertEqual(rc, 1, rep)
        [p] = [p for p in rep["problems"] if p["kind"] == "unresolved-flag"]
        self.assertEqual((p["file"], p["problem"]), ("scripts/tool.py",
                                                     "--token is not registered by argparse in tool.py"))

    def test_flag_in_a_script_naming_its_owner_passes(self):
        self.write_second_script()
        self.edit("scripts/tool.py", "Exit 0 = done, 1 = nothing found.",
                  "Exit 0 = done, 1 = nothing found: re-run example.py with --token.")
        rc, rep = self.check()
        self.assertEqual(rc, 0, rep)

    def test_unreadable_snapshot_exits_2(self):
        self.snap.write_text("{not json")
        self.assertEqual(self.check()[0], 2)
        self.snap.unlink()
        self.assertEqual(self.check()[0], 2)

    def test_snapshot_without_lint_rebuilds_baseline(self):
        data = json.loads(self.snap.read_text())
        del data["lint"]
        self.snap.write_text(json.dumps(data))
        rc, rep = self.check()
        self.assertEqual(rc, 0, rep)


class MergeCheck(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        for side in ("src", "aud"):
            (self.tmp / side / "scripts").mkdir(parents=True)
            (self.tmp / side / "scripts" / "a.py").write_text("x = 1\ny = 2\n")
        (self.tmp / "aud" / "scripts" / "__pycache__").mkdir()
        (self.tmp / "aud" / "scripts" / "__pycache__" / "a.cpython-311.pyc").write_bytes(b"\0")

    def run_merge(self):
        r = gate("merge-check", "--source", str(self.tmp / "src"), "--audited", str(self.tmp / "aud"))
        return r.returncode, json.loads(r.stdout)

    def test_identical_trees_pass(self):
        self.assertEqual(self.run_merge(), (0, {"ok": True, "differences": []}))

    def test_differing_trees_fail(self):
        (self.tmp / "aud" / "scripts" / "a.py").write_text("x = 1\ny = 3\n")
        (self.tmp / "aud" / "extra.md").write_text("new\n")
        rc, rep = self.run_merge()
        self.assertEqual(rc, 1)
        by_file = {d["file"]: d for d in rep["differences"]}
        self.assertEqual(by_file["extra.md"]["status"], "only-in-audited")
        self.assertIn("+y = 3", by_file["scripts/a.py"]["hunks"][0])

    def test_missing_directory_exits_2(self):
        r = gate("merge-check", "--source", str(self.tmp / "nope"), "--audited", str(self.tmp / "aud"))
        self.assertEqual(r.returncode, 2)


class Survival(unittest.TestCase):
    def test_cause_line_written_under_row_once(self):
        with tempfile.TemporaryDirectory() as d:
            ledger = Path(d) / "ledger.md"
            ledger.write_text("# Audit ledger\n\n| Runtime | Round | Phase | Cluster | Root cause | Address | Flags |\n"
                              "|---|---|---|---|---|---|---|\n"
                              "| 2026-10-05T10:00:00 | 2 | Code Review | C3 | r | FIX (scripts/a.py) | G1,G2 |\n")
            for _ in range(2):
                r = gate("survival", "--ledger", str(ledger), "--row", "G2", "--cause", "cascade")
                self.assertEqual(r.returncode, 0, r.stderr)
            lines = ledger.read_text().splitlines()
            self.assertEqual(lines[-1], "<!-- survival:: round 2 C3 flags G1,G2 cause=cascade -->")
            self.assertEqual(sum("survival::" in x for x in lines), 1)
            self.assertEqual(gate("survival", "--ledger", str(ledger), "--row", "C9",
                                  "--cause", "cascade").returncode, 2)


BLOCK = """# Guide

A cause paragraph that a fixer rewrites as one:
first the missing-directory case gets its remedy here,
then the unreadable-file case gets its remedy here,
then the lint-failure case gets its remedy here,
and the paragraph ends with one closing sentence.

Notes for the reader.
"""


class Blocks(GateCase):
    def rewrite(self, stem="REWRITTEN"):
        p = self.root / "references" / "guide.md"
        p.write_text(p.read_text().replace("first the missing-directory", f"{stem} one the missing-directory")
                     .replace("then the unreadable-file", f"{stem} two the unreadable-file")
                     .replace("then the lint-failure", f"{stem} three the lint-failure"))

    def setUp(self):
        super().setUp()
        (self.root / "references" / "guide.md").write_text(BLOCK)
        r = gate("snapshot", "--target", str(self.root), "--out", str(self.snap))
        self.assertEqual(r.returncode, 0, r.stderr)

    def transcript(self, closure):
        t = self.tmp / "t.jsonl"
        text = json.dumps({"decisions": [{"cluster": "C1", "decision": "FIX", "address": "FIX (references/guide.md: x)",
                                          "touched_files": ["references/guide.md"], "closure": closure}]})
        t.write_text(json.dumps({"type": "assistant", "message": {"role": "assistant",
                                                                   "content": [{"type": "text", "text": text}]}}) + "\n")
        return str(t)

    def check_with(self, *transcripts):
        args = ["check", "--target", str(self.root), "--snapshot", str(self.snap)]
        for t in transcripts:
            args += ["--fixer-transcript", t]
        r = gate(*args)
        return r.returncode, json.loads(r.stdout)

    def test_block_rewrite_needs_a_blocks_line_and_names_the_range(self):
        self.rewrite()
        rc, rep = self.check_with()
        self.assertEqual(rc, 1)
        self.assertEqual(rep["rewritten_blocks"], [{"file": "references/guide.md", "start": 3, "end": 7}])
        self.assertEqual([p["kind"] for p in rep["problems"]], ["block-reread"])
        self.assertIn("references/guide.md:3-7", rep["problems"][0]["problem"])

    def test_blocks_line_in_the_transcript_clears_it(self):
        self.rewrite()
        t = self.transcript(["Siblings: none found", "Bound: none added", "Claims: none", "Blocks: references/guide.md:3-7 re-read"])
        rc, rep = self.check_with(t)
        self.assertEqual((rc, rep["problems"] if rc else []), (0, []), rep)

    def test_blocks_line_for_another_block_does_not_clear_it(self):
        self.rewrite()
        t = self.transcript(["Siblings: none", "Bound: none added", "Claims: none", "Blocks: references/other.md:1-9"])
        self.assertEqual(self.check_with(t)[0], 1)

    def test_one_line_edit_is_not_a_rewritten_block(self):
        self.edit("references/guide.md", "closing sentence", "final sentence")
        rc, rep = self.check_with()
        self.assertEqual((rc, rep["rewritten_blocks"]), (0, []))

    def test_untouched_line_of_a_rewritten_block_is_name_checked(self):
        p = self.root / "references" / "guide.md"
        p.write_text(p.read_text().replace("and the paragraph ends", "and `scripts/gone.py` ends"))
        self.snap.unlink()
        r = gate("snapshot", "--target", str(self.root), "--out", str(self.snap))
        self.assertEqual(r.returncode, 0, r.stderr)
        p.write_text(p.read_text().replace("`scripts/gone.py`", "`scripts/missing.py`"))
        self.rewrite()
        rc, rep = self.check_with()
        self.assertIn("unresolved-path", {x["kind"] for x in rep["problems"]})


class Siblings(unittest.TestCase):
    def test_plain_words_and_very_common_terms_are_not_listed(self):
        texts = {"a.md": "Use `for` and `return` and `my_term` here.\n" + "".join(f"Line {i} names `my_term` and `for`.\n" for i in range(3))
                 + "".join(f"Common {i} names `common_term`.\n" for i in range(20))
                 + "Edited line names `common_term` and `my_term`.\n"}
        tree = pfg.Tree(texts, set(texts))
        entries, omitted = pfg.siblings(tree, {"a.md": {1, 25}})
        self.assertEqual([e["term"] for e in entries], ["my_term"])
        self.assertEqual(entries[0]["total"], 3)
        self.assertEqual(omitted, 1)


class Exit2Causes(unittest.TestCase):
    def test_every_raise_names_a_registered_cause_and_every_cause_is_raised(self):
        import ast
        src = (SCRIPTS / "post_fix_gate.py").read_text()
        tree = ast.parse(src)
        calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "GateInputError"]
        self.assertTrue(calls)
        used = set()
        for c in calls:
            self.assertEqual(len(c.args), 2, f"line {c.lineno}: GateInputError needs a message and a cause")
            if isinstance(c.args[1], ast.Constant):
                used.add(c.args[1].value)
        for n in ast.walk(tree):  # causes handed through normalise_lint(data, "<cause>") or re-raised
            if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "normalise_lint" and len(n.args) > 1:
                used.add(n.args[1].value)
            if isinstance(n, ast.IfExp) and isinstance(n.body, ast.Constant) and n.body.value in pfg.EXIT2_IDS:
                used.update({n.body.value, n.orelse.value})
        for c in calls:
            if isinstance(c.args[1], ast.Constant):
                self.assertIn(c.args[1].value, pfg.EXIT2_IDS)
        used.add("snapshot-lint-failed")  # re-raised by cmd_snapshot from a lint-run-failed error
        self.assertEqual(set(pfg.EXIT2_IDS) - used, set())

    def test_docs_carry_the_generated_table(self):
        root = SCRIPTS.parent
        for rel in ("SKILL.md", "references/script-contract.md"):
            r = gate("causes", "--check", str(root / rel))
            self.assertEqual(r.returncode, 0, f"{rel}: {r.stderr}")

    def test_check_flags_a_doc_that_differs_and_write_repairs_it(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "doc.md"
            f.write_text(f"intro\n{pfg.EXIT2_BEGIN}\nstale\n{pfg.EXIT2_END}\n")
            self.assertEqual(gate("causes", "--check", str(f)).returncode, 1)
            self.assertEqual(gate("causes", "--write", str(f)).returncode, 0)
            self.assertEqual(gate("causes", "--check", str(f)).returncode, 0)
            self.assertEqual(gate("causes", "--check", str(Path(d) / "absent.md")).returncode, 1)

    def test_error_json_carries_cause_and_remedy(self):
        cases = [(["snapshot", "--target", "/nonexistent-dir", "--out", "x.json"], "not-a-directory"),
                 (["check", "--target", str(SCRIPTS.parent), "--snapshot", "/nonexistent.json"], "snapshot-unusable"),
                 (["survival", "--ledger", "/nonexistent.md", "--row", "C1", "--cause", "cascade"], "ledger-unreadable")]
        for args, cause in cases:
            r = gate(*args)
            self.assertEqual(r.returncode, 2, r.stdout)
            err = json.loads(r.stderr)
            self.assertEqual(err["cause"], cause)
            self.assertEqual(err["remedy"], next(f for c, _, f in pfg.EXIT2 if c == cause))


class TouchedLines(unittest.TestCase):
    def test_replace_and_insert_lines_are_touched(self):
        touched, removed = pfg.touched_lines("a\nb\nc\n", "a\nB\nc\nd\n")
        self.assertEqual((touched, removed), ({2, 4}, ["b"]))


if __name__ == "__main__":
    unittest.main()
