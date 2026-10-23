import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "tandem_check.py"


def run(summary, comments):
    with tempfile.TemporaryDirectory() as d:
        s, c = Path(d, "s.txt"), Path(d, "c.txt")
        s.write_text(summary)
        c.write_text("\n".join(comments))
        r = subprocess.run([sys.executable, "-I", str(SCRIPT), str(s), str(c)], capture_output=True, text=True)
        return r.returncode, r.stdout


class TandemCheck(unittest.TestCase):
    def test_all_present(self):
        self.assertEqual(run("It has a weak record, with vetting as a political tool.", ["weak record", "Vetting as a political tool"])[0], 0)

    def test_missing_is_reported(self):
        code, out = run("It has a weak record.", ["weak record", "mixed record"])
        self.assertEqual(code, 1)
        self.assertIn("NOT IN SUMMARY: mixed record", out)

    def test_line_break_and_quotes(self):
        self.assertEqual(run("the “passive\nvictim” again", ['"passive victim"'])[0], 0)


class WordBoundaries(unittest.TestCase):
    def test_man_not_in_woman(self):
        code, out = run("The woman spoke.", ["man"])
        self.assertEqual(code, 1)
        self.assertIn("NOT IN SUMMARY: man", out)

    def test_phrase_not_in_longer_word(self):
        code, out = run("It has weak records.", ["weak record"])
        self.assertEqual(code, 1)
        self.assertIn("NOT IN SUMMARY: weak record", out)

    def test_whole_word_still_passes(self):
        self.assertEqual(run("The man spoke. Weak\nrecord, again.", ["man", "WEAK record"])[0], 0)


if __name__ == "__main__":
    unittest.main()
