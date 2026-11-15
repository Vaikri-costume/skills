import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)
sys.path.insert(0, SCRIPTS)
import report_lint  # noqa: E402


def run(script, *args):
    return subprocess.run([sys.executable, os.path.join(SCRIPTS, script), *args], capture_output=True, text=True)


class RunTools(unittest.TestCase):
    def test_tofile_saves_stdout_and_passes_the_exit_code(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "s.py")
            with open(src, "w") as f:
                f.write("import sys\nprint('hello')\nsys.exit(3)\n")
            out = os.path.join(d, "o.txt")
            p = run("tofile.py", out, src)
            self.assertEqual(p.returncode, 3)
            with open(out) as f:
                self.assertEqual(f.read().strip(), "hello")

    def test_tofile_rejects_a_missing_script(self):
        self.assertEqual(run("tofile.py", "/tmp/none.json", "/no/such/script.py").returncode, 2)

    def test_runfolder_new_then_remove(self):
        with tempfile.TemporaryDirectory() as base:
            p = run("runfolder.py", "new", base)
            self.assertEqual(p.returncode, 0)
            path = p.stdout.strip()
            self.assertTrue(os.path.basename(path).startswith("proofread-"))
            self.assertEqual(run("runfolder.py", "remove", path).returncode, 0)
            self.assertFalse(os.path.exists(path))

    def test_runfolder_refuses_other_folders(self):
        with tempfile.TemporaryDirectory() as base:
            self.assertEqual(run("runfolder.py", "remove", base).returncode, 2)
            self.assertTrue(os.path.isdir(base))


class WordCount(unittest.TestCase):
    def test_under_by_and_over_by(self):
        import word_count
        text = "One two three four five six seven eight nine ten."
        under = word_count.analyse(text, 25)
        self.assertEqual((under["over_by"], under["under_by"]), (0, 15))
        over = word_count.analyse(text, 4)
        self.assertEqual((over["over_by"], over["under_by"]), (6, 0))
        self.assertIsNone(word_count.analyse(text)["under_by"])


class Lint(unittest.TestCase):
    def rules(self, text):
        return {p["rule"] for p in report_lint.lint(text)}

    def test_clean_report_with_a_table(self):
        t = "Report for the writer.\n\n| 2 | organize the garden | organise the garden | -ise spelling |\n\nThe writer decides each change."
        self.assertEqual(self.rules(t), set())

    def test_rules(self):
        self.assertIn("offer", self.rules("Would you like me to check the references too?"))
        self.assertIn("next-line", self.rules("Next: run review-writing."))
        self.assertIn("gendered", self.rules("She should hyphenate it."))
        self.assertIn("american", self.rules("The report will organize the changes."))
        self.assertIn("tldr", self.rules("TLDR: three changes."))

    def test_allowed_ize_words_and_quotes(self):
        self.assertEqual(self.rules("The size of the prize is fixed; the word limit is 1,500."), set())
        self.assertEqual(self.rules('The draft says "she would organize it" in a quotation.'), set())


if __name__ == "__main__":
    unittest.main()
