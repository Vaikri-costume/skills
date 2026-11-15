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
            self.assertTrue(os.path.basename(path).startswith("ai-detection-"))
            self.assertEqual(run("runfolder.py", "remove", path).returncode, 0)
            self.assertFalse(os.path.exists(path))

    def test_runfolder_refuses_other_folders(self):
        with tempfile.TemporaryDirectory() as base:
            self.assertEqual(run("runfolder.py", "remove", base).returncode, 2)
            self.assertTrue(os.path.isdir(base))


class Lint(unittest.TestCase):
    def rules(self, text):
        return {p["rule"] for p in report_lint.lint(text)}

    def test_clean_report_describing_features(self):
        t = "Sentence length varies little in paragraphs 2 and 3.\n\n| 2 | the draft | a quoted line | feature |\n\nThe writer decides what to revise."
        self.assertEqual(self.rules(t), set())

    def test_score_verdict_and_evasion_rules(self):
        self.assertIn("ai-score", self.rules("There is a 72% chance this is machine text."))
        self.assertIn("ai-score", self.rules("The likelihood of AI authorship is high."))
        self.assertIn("verdict", self.rules("The essay was written by an AI."))
        self.assertIn("verdict", self.rules("This draft is human-written."))
        self.assertIn("evasion", self.rules("You can lower the detector score by varying sentences."))
        self.assertIn("evasion", self.rules("Humanise the text before submitting."))

    def test_inherited_rules(self):
        self.assertIn("offer", self.rules("Would you like me to run the citation check?"))
        self.assertIn("gendered", self.rules("She should add a source."))
        self.assertIn("tldr", self.rules("TLDR: three flags."))

    def test_quoted_text_is_ignored(self):
        self.assertEqual(self.rules('The draft says "this was written by a machine" in a quotation.'), set())


if __name__ == "__main__":
    unittest.main()
