import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

DIR = Path(__file__).resolve().parent.parent
PAGE = ("Violence persists after war. The claim is made here in full. "
        "For example, studies in Peru show it. A later point follows.")


def run(plan, pages):
    with tempfile.TemporaryDirectory() as d:
        p = Path(d, "plan.json")
        p.write_text(json.dumps(plan))
        pd = Path(d, "pages")
        pd.mkdir()
        for n, text in pages.items():
            Path(pd, f"p{n}.txt").write_text(text)
        r = subprocess.run([sys.executable, "-I", str(DIR / "context_check.py"), str(p), str(pd)],
                           capture_output=True, text=True)
        return r.returncode, r.stdout


class ContextCheck(unittest.TestCase):
    def test_quote_split_at_a_line_end_is_placed(self):
        page = "Wars end. Women face gender-\nbased violence in peace. Then more."
        plan = [{"n": 1, "comment": "gender-based violence", "page": 2, "quote": "Women face gender-based violence in peace."}]
        code, out = run(plan, {2: page})
        self.assertEqual(code, 0, out)
        self.assertNotIn("NOT PLACED", out)

    def test_before_and_after(self):
        plan = [{"n": 1, "comment": "made here", "page": 2, "quote": "The claim is made here in full."}]
        code, out = run(plan, {2: PAGE})
        self.assertEqual(code, 0, out)
        self.assertIn("BEFORE: Violence persists after war.", out)
        self.assertIn("AFTER:  For example, studies in Peru show it.", out)

    def test_line_end_hyphen(self):
        plan = [{"n": 1, "comment": "interpretation", "page": 2, "quote": "the interpretation holds."}]
        code, out = run(plan, {2: "First sentence. Then the inter-\npretation holds. Last one."})
        self.assertEqual(code, 0, out)
        self.assertIn("AFTER:  Last one.", out)

    def test_not_placed(self):
        plan = [{"n": 1, "comment": "x", "page": 2, "quote": "Not on the page."}]
        code, out = run(plan, {2: PAGE})
        self.assertEqual(code, 1)
        self.assertIn("NOT PLACED", out)

    def test_bad_input(self):
        code, _ = run([{"n": 1}], {2: PAGE})
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
