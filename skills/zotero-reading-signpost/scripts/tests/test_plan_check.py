import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

DIR = Path(__file__).resolve().parent.parent

PAGE = ("Much of women's experiences are informed by pre-existing, peacetime, inequalities. "
        "Violence is not extraordinary events in war. Transformation suggests far more radical change.")
PLAN = [
    {"n": 1, "comment": "informed by peacetime inequalities", "page": 2,
     "quote": "Much of women's experiences are informed by pre-existing, peacetime, inequalities."},
    {"n": 2, "comment": "not extraordinary events", "page": 2,
     "quote": "Violence is not extraordinary events in war."},
    {"n": 3, "comment": "far more radical change", "page": 2, "term": True,
     "quote": "Transformation suggests far more radical change."},
]
SUMMARY = ("Women's experiences are informed by peacetime inequalities [1]. Violence is not extraordinary "
           "events [2] in war, and transformation suggests far more radical change [3].")


def run(plan, summary, pages=None):
    with tempfile.TemporaryDirectory() as d:
        p, s = Path(d, "plan.json"), Path(d, "summary.txt")
        p.write_text(json.dumps(plan))
        s.write_text(summary)
        args = [sys.executable, "-I", str(DIR / "plan_check.py"), str(p), str(s)]
        if pages is not None:
            pd = Path(d, "pages")
            pd.mkdir()
            for n, text in pages.items():
                Path(pd, f"p{n}.txt").write_text(text)
            args += ["--pages", str(pd)]
        r = subprocess.run(args, capture_output=True, text=True)
        return r.returncode, r.stdout


class Clean(unittest.TestCase):
    def test_clean_plan_and_summary(self):
        code, out = run(PLAN, SUMMARY, {2: PAGE})
        self.assertEqual(code, 0, out)
        self.assertIn("nothing flagged", out)


class PlanFlags(unittest.TestCase):
    def test_long_comment(self):
        plan = [dict(PLAN[0], comment="informed by pre-existing peacetime inequalities of women")]
        code, out = run(plan, "informed by pre-existing peacetime inequalities of women [1].")
        self.assertIn("LONG COMMENT: 1", out)
        self.assertIn("[check: short label]", out)

    def test_negation_dropped(self):
        plan = [dict(PLAN[1], n=1, comment="extraordinary events")]
        code, out = run(plan, "Violence is not extraordinary events [1] in war.")
        self.assertIn("NEGATION: 1", out)

    def test_same_claim(self):
        plan = [{"n": 1, "comment": "yet to be clarified", "page": 6, "quote": "this is yet to be clarified."}]
        code, out = run(plan, "It is yet to be clarified [1].")
        self.assertIn("SAME CLAIM: 1", out)

    def test_inside(self):
        plan = [PLAN[0], dict(PLAN[0], n=2, quote="informed by pre-existing, peacetime, inequalities.")]
        code, out = run(plan, "Experiences are informed by peacetime inequalities [1] and informed by peacetime inequalities [2].")
        self.assertIn("INSIDE: 2 sits inside 1", out)

    def test_inside_on_placed_pages_is_reported_as_inside(self):
        plan = [PLAN[0], dict(PLAN[0], n=2, comment="peacetime inequalities", quote="peacetime, inequalities.")]
        code, out = run(plan, "Experiences are informed by peacetime inequalities [1], peacetime inequalities [2].", {2: PAGE})
        self.assertIn("INSIDE: 2 sits inside 1", out)

    def test_number_in_comment_is_matched(self):
        plan = [{"n": 1, "comment": "2008 crisis", "page": 2, "quote": "The 2008 crisis changed lending."}]
        code, out = run(plan, "The 2008 crisis [1] changed lending.")
        self.assertNotIn("TANDEM", out)
        code, out = run(plan, "The crisis [1] changed lending.")
        self.assertIn("TANDEM: 1", out)

    def test_by_design_link_needs_the_text(self):
        plan = [{"n": 1, "comment": "exclude women", "page": 2, "quote": "These mechanisms exclude women."}]
        code, out = run(plan, "These mechanisms exclude women [1] by design.")
        self.assertIn("LINK: 'by design'", out)

    def test_same_quote_twice_is_inside_with_or_without_pages(self):
        plan = [PLAN[0], dict(PLAN[0], n=2, comment="peacetime inequalities")]
        summary = "Experiences are informed by peacetime inequalities [1], peacetime inequalities [2]."
        for pages in (None, {2: PAGE}):
            code, out = run(plan, summary, pages)
            self.assertIn("INSIDE: 2 sits inside 1", out)

    def test_quote_split_at_a_line_end_is_placed(self):
        page = "Women face gender-\nbased violence in war and peace."
        plan = [{"n": 1, "comment": "gender-based violence", "page": 2, "quote": "Women face gender-based violence in war and peace."}]
        code, out = run(plan, "Women face gender-based violence [1] in war and peace.", {2: page})
        self.assertNotIn("NOT PLACED", out)

    def test_sentence_ending_in_a_closing_quote_is_counted(self):
        plan = [{"n": 1, "comment": "she said stop", "page": 2, "quote": 'She said "stop."'}]
        code, out = run(plan, 'She said stop [1] "now." Then the protest ended.')
        self.assertIn("WORDING: no highlight behind this sentence | Then the protest ended.", out)

    def test_number_with_comma_is_one_word(self):
        plan = [{"n": 1, "comment": "over 1,000 cases in 2020", "page": 2, "quote": "There were over 1,000 cases in 2020."}]
        code, out = run(plan, "There were over 1,000 cases in 2020 [1].")
        self.assertNotIn("LONG COMMENT", out)

    def test_unreadable_page_file_is_bad_input(self):
        with tempfile.TemporaryDirectory() as d:
            pd = Path(d, "pages"); pd.mkdir()
            Path(pd, "p2.txt").write_bytes(b"\xff\xfe\xfa not utf-8")
            p, s = Path(d, "plan.json"), Path(d, "summary.txt")
            p.write_text(json.dumps(PLAN[:1])); s.write_text(SUMMARY)
            r = subprocess.run([sys.executable, "-I", str(DIR / "plan_check.py"), str(p), str(s), "--pages", str(pd)],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)

    def test_non_text_comment_is_bad_input(self):
        code, out = run([dict(PLAN[0], comment=5)], "x [1].")
        self.assertEqual(code, 2, out)

    def test_order_by_position(self):
        plan = [dict(PLAN[2], n=1), dict(PLAN[0], n=2)]
        code, out = run(plan, "Far more radical change [1]. Informed by peacetime inequalities [2].", {2: PAGE})
        self.assertIn("ORDER", out)

    def test_page_split_parts_share_a_number(self):
        page3 = "Violence is not extraordinary events in war."
        plan = [PLAN[0], dict(PLAN[2], n=2, page=2, quote="Transformation suggests"),
                dict(PLAN[2], n=2, page=3, quote="Violence is not extraordinary events in war.")]
        code, out = run(plan, "Women's experiences are informed by peacetime inequalities [1], and transformation "
                              "suggests far more radical change [2].", {2: PAGE, 3: page3})
        self.assertNotIn("ORDER", out)
        self.assertNotIn("INSIDE", out)

    def test_long_quote_is_not_flagged_by_its_sentence_count(self):
        # No sentence limit: a highlight is as long as its point needs (a wall is graded, not counted).
        quote = "One claim here. A second sentence follows. A third sentence too."
        plan = [{"n": 1, "comment": "one claim", "page": 2, "quote": quote}]
        code, out = run(plan, "One claim [1] is made.")
        self.assertEqual(code, 0, out)

    def test_mid_sentence_start_is_not_flagged(self):
        plan = [{"n": 1, "comment": "radical change", "page": 2, "quote": "suggests far more radical change."}]
        code, out = run(plan, "Transformation suggests far more radical change [1].")
        self.assertEqual(code, 0, out)

    def test_hyphenated_compound_is_one_word(self):
        plan = [{"n": 1, "comment": "long-term state-led peace-building programmes", "page": 2,
                 "quote": "They fund long-term state-led peace-building programmes in the region."}]
        code, out = run(plan, "They fund long-term state-led peace-building programmes [1] in the region.")
        self.assertNotIn("LONG COMMENT", out)

    def test_term_across_a_page_break(self):
        plan = [{"n": 1, "comment": "far more radical change", "page": 2, "term": True, "quote": "suggests far more"},
                {"n": 1, "comment": "far more radical change", "page": 3, "term": True, "quote": "radical change at the roots."}]
        code, out = run(plan, "Transformation suggests far more radical change [1].")
        self.assertNotIn("TERM", out)

    def test_abbreviation_is_not_a_sentence_end(self):
        plan = [{"n": 1, "comment": "cases differ", "page": 2, "quote": "Cases differ, e.g. Peru and Congo."}]
        code, out = run(plan, "Cases differ [1], e.g. Peru and Congo.")
        self.assertNotIn("WORDING", out)

    def test_sentence_ending_in_no_is_a_sentence_end(self):
        plan = [{"n": 1, "comment": "told no", "page": 2, "quote": "Survivors were told no."}]
        # The cited sentence ends on the word "no." itself, which the splitter must not read as "No." (number).
        code, out = run(plan, "Survivors were told no [1] at first, and later again no. War changes everything.")
        self.assertIn("WORDING: no highlight behind this sentence | War changes everything.", out)

    def test_term_without_its_passage(self):
        plan = [dict(PLAN[2], n=1, comment="liberal peace")]
        code, out = run(plan, "Liberal peace [1].")
        self.assertIn("TERM: 1", out)


class SummaryFlags(unittest.TestCase):
    def test_missing_number(self):
        code, out = run(PLAN, "Informed by peacetime inequalities [1].")
        self.assertIn("MISSING: highlight 2", out)

    def test_tandem_needs_whole_words(self):
        plan = [{"n": 1, "comment": "man", "page": 2, "quote": "The woman spoke."}]
        code, out = run(plan, "The woman [1] spoke.")
        self.assertIn("TANDEM: 1", out)

    def test_tandem(self):
        code, out = run(PLAN[:1], "Women's experiences come out of peacetime inequalities [1].")
        self.assertIn("TANDEM: 1", out)

    def test_wording_swap(self):
        code, out = run(PLAN[:1], "Women's experiences in war are informed by peacetime inequalities [1].")
        self.assertNotIn("WORDING", out)

    def test_sentence_with_no_highlight_is_flagged(self):
        code, out = run(PLAN[:1], "Women's experiences are informed by peacetime inequalities [1]. War changes everything.")
        self.assertIn("WORDING: no highlight behind this sentence", out)

    def test_role_words_are_not_wording(self):
        code, out = run(PLAN[:1], "As evidence for the claim, women's experiences are informed by peacetime inequalities [1].")
        self.assertNotIn("WORDING", out)

    def test_link_not_in_text(self):
        code, out = run(PLAN[:2], "Experiences are informed by peacetime inequalities [1], because violence is not extraordinary events [2].")
        self.assertIn("LINK: 'because'", out)

    def test_short_part_of_page_split_passage_is_not_same_claim(self):
        plan = [{"n": 1, "comment": "far more radical change", "page": 2, "quote": "Reform asks for far more"},
                {"n": 1, "comment": "far more radical change", "page": 3, "quote": "radical change."}]
        code, out = run(plan, "Reform asks for far more radical change [1].")
        self.assertNotIn("SAME CLAIM", out)

    def test_contraction_counts_as_negation(self):
        plan = [{"n": 1, "comment": "extraordinary events", "page": 2, "quote": "Sexual violence in war isn't extraordinary events."}]
        code, out = run(plan, "Sexual violence in war is extraordinary events [1].")
        self.assertIn("NEGATION", out)

    def test_intensifier_so_is_not_a_link_but_clause_so_is(self):
        code, out = run(PLAN[:1], "Experiences are so often informed by peacetime inequalities [1].")
        self.assertNotIn("LINK", out)
        code, out = run(PLAN[:1], "War ends, so experiences are informed by peacetime inequalities [1].")
        self.assertIn("LINK: 'so'", out)

    def test_so_called_and_time_since_are_not_links(self):
        code, out = run(PLAN[:2], "The so-called peacetime inequalities [1] have shaped events since 1990, as violence is not extraordinary events [2].")
        self.assertNotIn("LINK", out)

    def test_bad_input_exits_2(self):
        with tempfile.TemporaryDirectory() as d:
            r = subprocess.run([sys.executable, "-I", str(DIR / "plan_check.py"), str(Path(d, "none.json")), str(Path(d, "x.txt"))],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
    unittest.main()
