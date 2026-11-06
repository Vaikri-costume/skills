import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import presentation_stats as ps  # noqa: E402
import report_lint as rl  # noqa: E402
import revision_diff as rd  # noqa: E402
import verdict_table as vt  # noqa: E402

FEEDBACK = '''## Finding 1
Location: paragraph 1 - "The harbour"
Current text: "The harbour was important to the town."
Severity: High

## Finding 2
Location: paragraph 2 - "Trade"
Current text: "Trade grew quickly after the canal opened."
Severity: Medium

## Finding 3
Location: paragraph 3 - "Nobody"
Current text: "Nobody disputes the figures."
Severity: Low
'''

DRAFT = '''The harbour was important to the town.

Trade grew rapidly once the canal had opened.

A short closing paragraph with something else.
'''


class RevisionDiff(unittest.TestCase):
    def test_states(self):
        res = rd.diff(FEEDBACK, DRAFT)
        self.assertEqual([r["n"] for r in res], [1, 2, 3])
        self.assertEqual(res[0]["state"], "unchanged")
        self.assertEqual(res[0]["paragraph"], 1)
        self.assertEqual(res[1]["state"], "reworded")
        self.assertEqual(res[2]["state"], "absent")

    def test_curly_quotes_fold(self):
        fb = 'Current text: "It’s fine."\n'
        self.assertEqual(rd.diff(fb, "It's fine.\n")[0]["state"], "unchanged")


class PresentationStats(unittest.TestCase):
    TEXT = "# Intro\none two three\n---\nfour five six seven eight nine ten eleven twelve\n---\nReferences\nSmith 2020\n"

    def test_counts_and_reference_slide(self):
        s = ps.stats(self.TEXT)
        self.assertEqual(s["slides"], 3)
        self.assertEqual(s["reference_slide"], [3])
        self.assertEqual(s["per_slide"][1]["words"], 9)

    def test_pace(self):
        long_text = "word " * 1000
        s = ps.stats(long_text, minutes=5)
        self.assertEqual(s["pace"]["fits"], "long")
        s = ps.stats(long_text, minutes=7)
        self.assertEqual(s["pace"]["fits"], "within")
        s = ps.stats(long_text, minutes=20)
        self.assertEqual(s["pace"]["fits"], "short")


RUBRIC = "- Sets out a clear argument\n- Engages with counter-arguments\n- Uses a range of sources\n"


class VerdictTable(unittest.TestCase):
    def good(self):
        return ("| Criterion | Verdict | Quoted line |\n|---|---|---|\n"
                '| Sets out a clear argument | met | "The harbour was important to the town." |\n'
                "| Engages with counter-arguments | not found in the draft | — |\n"
                '| Uses a range of sources | partly | "Trade grew quickly after the canal opened." |\n')

    def test_clean(self):
        self.assertEqual(vt.check(RUBRIC, self.good())["problems"], [])

    def test_partly_for_missing_is_flagged_as_wrong_word(self):
        bad = self.good().replace("not found in the draft", "mostly")
        rules = [p["rule"] for p in vt.check(RUBRIC, bad)["problems"]]
        self.assertIn("verdict-word", rules)

    def test_other_tables_ignored(self):
        extra = "| Finding | Severity | Para |\n|---|---|---|\n| 1 | High | 2 |\n\n" + self.good()
        self.assertEqual(vt.check(RUBRIC, extra)["problems"], [])

    def test_order_and_missing(self):
        lines = self.good().splitlines()
        swapped = "\n".join([lines[0], lines[1], lines[3], lines[2], lines[4]]) + "\n"
        self.assertIn("order", [p["rule"] for p in vt.check(RUBRIC, swapped)["problems"]])
        missing = "\n".join(lines[:4]) + "\n"
        self.assertIn("missing-criterion", [p["rule"] for p in vt.check(RUBRIC, missing)["problems"]])

    def test_quote_rules(self):
        noquote = self.good().replace('"The harbour was important to the town."', "")
        self.assertIn("quote-missing", [p["rule"] for p in vt.check(RUBRIC, noquote)["problems"]])
        nf = self.good().replace("— |", '"Trade" |')
        self.assertIn("not-found-quote", [p["rule"] for p in vt.check(RUBRIC, nf)["problems"]])
        r = vt.check(RUBRIC, self.good(), "The harbour only.")
        self.assertIn("quote-not-in-draft", [p["rule"] for p in r["problems"]])


class ReportLint(unittest.TestCase):
    def rules(self, text):
        return {p["rule"] for p in rl.lint(text)}

    def test_clean_report(self):
        self.assertEqual(self.rules('The writer says "she left early" and then they move on.\n> She said so.\n'), set())

    def test_each_rule(self):
        self.assertIn("tldr", self.rules("TL;DR: fine\n"))
        self.assertIn("offer", self.rules("Would you like me to look again?\n"))
        self.assertIn("gendered", self.rules("The writer shows her warrant.\n"))
        self.assertIn("rewrite", self.rules("Suggested wording: the harbour mattered.\n"))
        self.assertIn("rewrite", self.rules("You could write a clearer claim.\n"))
        self.assertIn("grade", self.rules("Overall 7/10.\n"))
        self.assertIn("next-line", self.rules("Next: revise paragraph 2.\n"))

    def test_where_to_next_heading_is_allowed(self):
        self.assertEqual(self.rules("### Where to next\n- Which sentence states the warrant?\n"), set())


if __name__ == "__main__":
    unittest.main()
