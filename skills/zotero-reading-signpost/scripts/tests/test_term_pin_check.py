import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

DIR = Path(__file__).resolve().parents[1]


def run(script, files, *extra):
    with tempfile.TemporaryDirectory() as d:
        paths = []
        for i, text in enumerate(files):
            p = Path(d, f"f{i}.txt")
            p.write_text(text)
            paths.append(str(p))
        r = subprocess.run([sys.executable, "-I", str(DIR / script), *paths, *extra], capture_output=True, text=True)
        return r.returncode, r.stdout


class TermCheck(unittest.TestCase):
    def test_swap_flagged(self):
        with tempfile.TemporaryDirectory() as d:
            s, m = Path(d, "s.txt"), Path(d, "m.txt")
            s.write_text("Everyday violence continues against women.")
            m.write_text("Everyday abuse continues against women.")
            r = subprocess.run([sys.executable, "-I", str(DIR / "term_check.py"), str(s), str(m)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 1)
            self.assertIn("abuse", r.stdout)

    def test_clean(self):
        code, out = run("term_check.py", ["Everyday violence continues against women.", "Everyday violence continues."])
        self.assertEqual(code, 0)

    def test_half_of_hyphenated_compound_counts_as_used(self):
        code, out = run("term_check.py", ["A market-driven economy grows.", "A driven market grows."])
        self.assertEqual(code, 0, out)


class TermLigature(unittest.TestCase):
    def test_ligature_in_source_reads_as_letters(self):
        code, out = run("term_check.py", ["The \ufb01rst claim holds.", "The first claim holds."])
        self.assertEqual(code, 0, out)


class TermPlanBadInput(unittest.TestCase):
    def _plan(self, plan_text):
        with tempfile.TemporaryDirectory() as d:
            s, m, pl = Path(d, "s.txt"), Path(d, "m.txt"), Path(d, "p.json")
            s.write_text("Everyday violence continues.")
            m.write_text("Everyday violence continues.")
            pl.write_text(plan_text)
            return subprocess.run([sys.executable, "-I", str(DIR / "term_check.py"), str(s), str(m), "--plan", str(pl)], capture_output=True, text=True)

    def test_not_json(self):
        r = self._plan("not json")
        self.assertEqual(r.returncode, 2)
        self.assertIn("bad plan file", r.stdout)
        self.assertNotIn("Traceback", r.stderr)
        self.assertNotIn("words not used", r.stdout)

    def test_missing_keys_and_wrong_shapes(self):
        for text in ('[{"comment": "x"}]', '[{"quote": "x"}]', '["abc"]', '{"a": 1}', '5'):
            r = self._plan(text)
            self.assertEqual(r.returncode, 2, text)
            self.assertIn("bad plan file", r.stdout)
            self.assertNotIn("Traceback", r.stderr)

    def test_good_plan_still_works(self):
        r = self._plan('[{"n": 1, "comment": "violence continues", "quote": "violence continues"}]')
        self.assertEqual(r.returncode, 0, r.stdout)


class CutVariants(unittest.TestCase):
    def test_pin_check_cuts_linebreak_and_curly(self):
        code, out = run("pin_check.py", ["The weak\nrecord of \u201cstate power\u201d", "weak record of \"State Power\""])
        self.assertEqual(code, 0, out)
        code, out = run("pin_check.py", ["The weak\nrecord of \u201cstate power\u201d extra claims about lasting violence", "weak record of \"State Power\""])
        self.assertEqual(code, 1)
        self.assertNotIn("weak", out)

    def test_term_check_cuts_linebreak_and_curly(self):
        src = "Everyday women's violence continues."
        summ = "Everyday women\u2019s violence continues. Zorbing\nglibness \u201cflux\u201d persists."
        with tempfile.TemporaryDirectory() as d:
            s, m, c = Path(d, "s.txt"), Path(d, "m.txt"), Path(d, "c.txt")
            s.write_text(src)
            m.write_text(summ)
            c.write_text("zorbing glibness \"flux\" persists")
            r = subprocess.run([sys.executable, "-I", str(DIR / "term_check.py"), str(s), str(m), "--comments", str(c)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout)
            c.write_text("unrelated")
            r = subprocess.run([sys.executable, "-I", str(DIR / "term_check.py"), str(s), str(m), "--comments", str(c)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 1)

    def test_term_check_joins_line_end_hyphenation(self):
        with tempfile.TemporaryDirectory() as d:
            s, m = Path(d, "s.txt"), Path(d, "m.txt")
            s.write_text("The gov-\nernment keeps records.")
            m.write_text("The government keeps records.")
            r = subprocess.run([sys.executable, "-I", str(DIR / "term_check.py"), str(s), str(m)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout)
            m.write_text("The cabinet keeps records.")
            r = subprocess.run([sys.executable, "-I", str(DIR / "term_check.py"), str(s), str(m)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 1)
            self.assertIn("cabinet", r.stdout)


    def test_term_check_keeps_compound_broken_at_line_end(self):
        with tempfile.TemporaryDirectory() as d:
            s, m = Path(d, "s.txt"), Path(d, "m.txt")
            s.write_text("A market-\ndriven economy grows.")
            m.write_text("A market-driven economy grows.")
            r = subprocess.run([sys.executable, "-I", str(DIR / "term_check.py"), str(s), str(m)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout)


class PinCheck(unittest.TestCase):
    def test_unpinned_flagged(self):
        code, out = run("pin_check.py", ["Women have faced harms. A society builds structures behind lasting violence.", "women have faced harms"])
        self.assertEqual(code, 1)
        self.assertIn("UNPINNED", out)

    def test_all_pinned(self):
        code, out = run("pin_check.py", ["The text finds weak record and political tool.", "weak record\npolitical tool"])
        self.assertEqual(code, 0)


class CutWordBoundaries(unittest.TestCase):
    def test_cuts_do_not_match_inside_longer_words(self):
        # pin_check: comment "weak record" must not cut "weak records", so the stretch stays unpinned
        code, out = run("pin_check.py", ["The text weak records political tools persist.", "weak record"])
        self.assertEqual(code, 1, out)
        # term_check: "abuse" must not be cut out of "abuses"
        with tempfile.TemporaryDirectory() as d:
            s, m, c = Path(d, "s.txt"), Path(d, "m.txt"), Path(d, "c.txt")
            s.write_text("Everyday violence continues.")
            m.write_text("Everyday zorbing glibnesses persist.")
            c.write_text("zorbing glibness")
            r = subprocess.run([sys.executable, "-I", str(DIR / "term_check.py"), str(s), str(m), "--comments", str(c)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 1, r.stdout)
            m.write_text("Everyday zorbing glibness persist.")
            r = subprocess.run([sys.executable, "-I", str(DIR / "term_check.py"), str(s), str(m), "--comments", str(c)], capture_output=True, text=True)
            self.assertNotIn("zorbing", r.stdout)


class WiredChecksBehaviour(unittest.TestCase):
    def test_term_plan_flags_comment_word_missing_from_its_quote(self):
        with tempfile.TemporaryDirectory() as d:
            s, m, pl = Path(d, "s.txt"), Path(d, "m.txt"), Path(d, "p.json")
            s.write_text("Everyday violence continues.")
            m.write_text("Everyday violence continues.")
            pl.write_text('[{"n": 1, "comment": "abuse continues", "quote": "violence continues"}]')
            r = subprocess.run([sys.executable, "-I", str(DIR / "term_check.py"), str(s), str(m), "--plan", str(pl)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 1, r.stdout)
            self.assertIn("COMMENT WORD NOT IN ITS QUOTE", r.stdout)

    def test_term_plan_reads_page_split_parts_together(self):
        with tempfile.TemporaryDirectory() as d:
            s, m, pl = Path(d, "s.txt"), Path(d, "m.txt"), Path(d, "p.json")
            s.write_text("Reform asks for far more radical change.")
            m.write_text("Reform asks for far more radical change.")
            pl.write_text('[{"n": 1, "comment": "more radical change", "quote": "Reform asks for far more"},'
                          ' {"n": 1, "comment": "more radical change", "quote": "radical change."}]')
            r = subprocess.run([sys.executable, "-I", str(DIR / "term_check.py"), str(s), str(m), "--plan", str(pl)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout)

    def test_term_bad_input_exits_2(self):
        code, out = run("term_check.py", ["Everyday violence continues."])
        self.assertEqual(code, 2)
        with tempfile.TemporaryDirectory() as d:
            s = Path(d, "s.txt")
            s.write_text("x")
            r = subprocess.run([sys.executable, "-I", str(DIR / "term_check.py"), str(s), str(Path(d, "none.txt"))], capture_output=True, text=True)
            self.assertEqual(r.returncode, 2)
            self.assertIn("missing input file", r.stdout)

    def test_pin_max_run_sets_the_threshold(self):
        summary = "A society builds structures behind lasting violence today."
        code, out = run("pin_check.py", [summary, "unrelated phrase"])
        self.assertEqual(code, 1, out)
        code, out = run("pin_check.py", [summary, "unrelated phrase"], "--max-run", "9")
        self.assertEqual(code, 0, out)

    def test_pin_bad_input_exits_2(self):
        code, out = run("pin_check.py", ["Some summary words here today."])
        self.assertEqual(code, 2)
        code, out = run("pin_check.py", ["Some summary words here today.", "\n"])
        self.assertEqual(code, 2)
        self.assertIn("no comments", out)
        code, out = run("pin_check.py", ["Some summary words here today.", "phrase"], "--max-run", "abc")
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
