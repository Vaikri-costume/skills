import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

DIR = Path(__file__).resolve().parent.parent


def run(script, *args):
    r = subprocess.run([sys.executable, "-I", str(DIR / script), *args], capture_output=True, text=True)
    return r.returncode, r.stdout


class CapCheck(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.page = Path(self.d.name, "p2.txt")
        self.page.write_text(" ".join(["word"] * 100))

    def tearDown(self):
        self.d.cleanup()

    def test_within(self):
        s = Path(self.d.name, "s.txt")
        s.write_text("one two three [1] four five.")
        code, out = run("cap_check.py", str(s), str(self.page))
        self.assertEqual(code, 0, out)
        self.assertIn("summary 5 words; pages 100 words; cap 15% = 15 words", out)

    def test_over(self):
        s = Path(self.d.name, "s.txt")
        s.write_text(" ".join(["w"] * 20))
        code, out = run("cap_check.py", str(s), str(self.page), "--cap", "10")
        self.assertEqual(code, 1)
        self.assertIn("over the cap by 10 words", out)

    def test_bad_input(self):
        code, _ = run("cap_check.py", str(self.page))
        self.assertEqual(code, 2)
        code, _ = run("cap_check.py", str(self.page), str(self.page), "--cap", "x")
        self.assertEqual(code, 2)


class NoteHtml(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.s = Path(self.d.name, "s.txt")
        self.s.write_text("First claim [1] & more.\n\nSecond <para> [2].\n")

    def tearDown(self):
        self.d.cleanup()

    def test_layout(self):
        code, out = run("note_html.py", str(self.s), "--related", "Module", "--citekey", "key2003", "--author", "A B")
        self.assertEqual(code, 0, out)
        self.assertEqual(out.strip(),
                         "<p>related:: &#91;&#91;Module&#93;&#93;<br>type:: Signpost Summary<br>writer:: Claude"
                         "<br>citekey:: key2003<br>author:: A B</p><p>Notes / Summary</p>"
                         "<p>First claim &amp; more.</p><p>Second &lt;para&gt;.</p>")

    def test_apostrophe_in_author_is_kept(self):
        code, out = run("note_html.py", str(self.s), "--author", "M O'Brien")
        self.assertIn("author:: M O'Brien</p>", out)

    def test_empty_related_and_no_citekey(self):
        code, out = run("note_html.py", str(self.s))
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("<p>related::<br>type:: Signpost Summary<br>writer:: Claude</p>"))
        self.assertNotIn("citekey::", out)

    def test_bad_input(self):
        code, _ = run("note_html.py")
        self.assertEqual(code, 2)
        code, _ = run("note_html.py", str(self.s), "--related")
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
