import json
import os
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "scripts", "budget_check.py")


def run(text, *args):
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as handle:
        handle.write(text)
        path = handle.name
    try:
        result = subprocess.run([sys.executable, SCRIPT, path, *args], capture_output=True, text=True)
        return result.returncode, result.stdout
    finally:
        os.remove(path)


class BudgetCheckTests(unittest.TestCase):
    def test_sum_and_total_mismatch(self):
        code, out = run("1. Intro (200 words)\n2. Evidence (700 words)\n3. Counter (300 words)\n\nTotal: 1500 words\n", "--limit", "1500")
        data = json.loads(out)
        self.assertEqual(code, 0)
        self.assertEqual(data["sum"], 1200)
        self.assertEqual(data["stated_total"], 1500)
        self.assertFalse(data["sum_matches_limit"])
        self.assertFalse(data["sum_matches_stated_total"])

    def test_matching_sum(self):
        _, out = run("- A (500 words)\n- B (1,000 words)\n", "--limit", "1500")
        self.assertTrue(json.loads(out)["sum_matches_limit"])

    def test_no_budgets(self):
        _, out = run("no numbers here\n")
        data = json.loads(out)
        self.assertEqual(data["sections"], [])
        self.assertEqual(data["sum"], 0)
        self.assertIsNone(data["sum_matches_limit"])

    def test_count(self):
        _, out = run("one two three four\nfive", "--count")
        self.assertEqual(json.loads(out)["words"], 5)

    def test_missing_file(self):
        result = subprocess.run([sys.executable, SCRIPT, "/nonexistent/file.md"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)


if __name__ == "__main__":
    unittest.main()
