import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import combine_findings as cf  # noqa: E402

ARG = '''## Finding 1
Location: paragraph 5 - "x"
Current text: "The claim stands alone."
Element: grounds
Layer: paragraph
Concern: c1.
Severity: Medium
Analysis confidence: HIGH

## Finding 2
Location: paragraph 1 - "y"
Current text: "The aim is vague."
Element: claim
Layer: foundation
Concern: c2.
Severity: Low
Analysis confidence: UNVERIFIED
'''
EVI = '''## Finding 1
Location: paragraph 3 - "z"
Current text: "A figure is given and left."
Layer: sentence
Concern: c3.
Severity: High
Analysis confidence: HIGH
'''
CLA = '''## Finding 1
Location: paragraph 5 - "x"
Current text: "the claim stands alone."
Sub-category: unclear pronoun
Layer: sentence
Concern: c4.
Severity: High
Analysis confidence: UNVERIFIED
'''


class Combine(unittest.TestCase):
    def run_combine(self):
        with tempfile.TemporaryDirectory() as d:
            for name, text in (("Argument", ARG), ("Evidence", EVI), ("Clarity", CLA)):
                open(os.path.join(d, name + "-merged.md"), "w", encoding="utf-8").write(text)
            return cf.combine(d)

    def test_count_and_order(self):
        text, n = self.run_combine()
        self.assertEqual(n, 3)
        self.assertLess(text.index("The aim is vague"), text.index("The claim stands alone"))
        self.assertLess(text.index("The claim stands alone"), text.index("A figure is given and left"))

    def test_cross_domain_merge_takes_higher_severity(self):
        text, _ = self.run_combine()
        self.assertIn("Domain: Cross-domain (merged)", text)
        block = text.split("## Finding 2")[1].split("## Finding 3")[0]
        self.assertIn("Severity: High", block)

    def test_domain_line_on_every_finding_and_numbering(self):
        text, n = self.run_combine()
        self.assertEqual(text.count("\nDomain: ") + (1 if text.startswith("Domain: ") else 0), n)
        for i in range(1, n + 1):
            self.assertIn(f"## Finding {i}", text)

    def test_fields_kept(self):
        text, _ = self.run_combine()
        self.assertIn("Layer: foundation", text)
        self.assertIn("Analysis confidence: UNVERIFIED", text)


if __name__ == "__main__":
    unittest.main()
