import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "anchor_check.py"


def run(page, parts, *flags):
    with tempfile.TemporaryDirectory() as d:
        p, q = Path(d, "page.txt"), Path(d, "parts.txt")
        p.write_text(page)
        q.write_text("\n".join(parts))
        r = subprocess.run([sys.executable, "-I", str(SCRIPT), str(p), str(q), *flags], capture_output=True, text=True)
        return r.returncode, r.stdout


class AnchorCheck(unittest.TestCase):
    def test_exact(self):
        self.assertEqual(run("The state remembers selectively.", ["remembers selectively"])[0], 0)

    def test_hyphen_linebreak(self):
        code, out = run("Contested memory-\nscapes are produced by power.", ["memoryscapes are produced"])
        self.assertEqual(code, 0, out)

    def test_ligature_and_quotes(self):
        code, out = run("The ﬁrst “claim” holds.", ['first "claim" holds'])
        self.assertEqual(code, 0, out)

    def test_linebreak_space(self):
        self.assertEqual(run("power\nshapes   recall", ["power shapes recall"])[0], 0)

    def test_missing(self):
        code, out = run("Nothing relevant here.", ["something else"])
        self.assertEqual(code, 1)
        self.assertIn("NOT FOUND", out)

    def test_paraphrase_not_found(self):
        self.assertEqual(run("Power shapes recall.", ["power influences recall"])[0], 1)

    def test_ambiguous(self):
        code, out = run("it works. it works.", ["it works"])
        self.assertEqual(code, 1)
        self.assertIn("AMBIGUOUS", out)

    def test_bad_input(self):
        r = subprocess.run([sys.executable, "-I", str(SCRIPT)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)

    def test_real_hyphen_kept(self):
        # a genuine hyphen before a capital or digit at a line end is kept, the break dropped
        self.assertEqual(run("Anglo-\nSaxon rule", ["Anglo-Saxon"])[0], 0)
        self.assertEqual(run("by ChatGPT-\n4o itself", ["ChatGPT-4o itself"])[0], 0)

    def test_soft_hyphen_linebreak(self):
        self.assertEqual(run("the inter\u00ad\npretation of", ["interpretation of"])[0], 0)


class CaseCheck(unittest.TestCase):
    def test_case_difference_flagged(self):
        code, out = run("The state remembers.", ["the state remembers"])
        self.assertEqual(code, 1)
        self.assertIn("CASE DIFFERS", out)


class AllowRepeatCase(unittest.TestCase):
    def _run(self, page, part, *extra):
        with tempfile.TemporaryDirectory() as d:
            pg, q = Path(d, "page.txt"), Path(d, "parts.txt")
            pg.write_text(page)
            q.write_text(part)
            r = subprocess.run([sys.executable, "-I", str(SCRIPT), str(pg), str(q), *extra], capture_output=True, text=True)
            return r.returncode, r.stdout

    LONG = "The State remembers what it chooses to remember and forgets whatever does not serve the story it tells of itself"

    def test_allow_repeat_still_flags_case(self):
        code, out = self._run(f"{self.LONG}. {self.LONG}.", self.LONG.lower(), "--allow-repeat")
        self.assertEqual(code, 1)
        self.assertIn("CASE DIFFERS", out)

    def test_allow_repeat_accepts_repeat_with_right_case(self):
        code, out = self._run(f"{self.LONG}. {self.LONG}.", self.LONG, "--allow-repeat")
        self.assertEqual(code, 0)
        self.assertIn("2 matches", out)

    def test_allow_repeat_refuses_a_short_repeat(self):
        code, out = self._run("The State remembers. The State remembers.", "The State remembers", "--allow-repeat")
        self.assertEqual(code, 1)
        self.assertIn("highlighted at every copy", out)

    def test_repeat_without_flag_is_ambiguous(self):
        code, out = self._run("The State remembers. The State remembers.", "The State remembers")
        self.assertEqual(code, 1)
        self.assertIn("AMBIGUOUS", out)


class CaseCheckNormalised(unittest.TestCase):
    def test_case_differs_across_line_end_hyphen(self):
        code, out = run("Contested memory-\nscapes are produced.", ["Memoryscapes are produced"])
        self.assertEqual(code, 1)
        self.assertIn("CASE DIFFERS", out)

    def test_case_differs_across_ligature(self):
        code, out = run("The \ufb01rst claim holds.", ["The First claim holds"])
        self.assertEqual(code, 1)
        self.assertIn("CASE DIFFERS", out)

    def test_same_case_across_ligature_and_hyphen_found(self):
        self.assertEqual(run("The \ufb01rst memory-\nscapes", ["first memoryscapes"])[0], 0)


class LooseAmbiguous(unittest.TestCase):
    def test_loose_multi_match_is_ambiguous(self):
        code, out = run("the city-\nwoman walked. the city woman ran.", ["city-woman"])
        self.assertEqual(code, 1)
        self.assertIn("AMBIGUOUS", out)
        self.assertNotIn("NOT FOUND", out)


class LooseAllowRepeat(unittest.TestCase):
    TAIL = "walked through streets the state had renamed after the war and that nobody now remembered at all"
    PAGE = f"the city-\nwoman {TAIL}. the city woman {TAIL}."

    def test_allow_repeat_accepts_loose_repeat(self):
        code, out = run(self.PAGE, [f"city-woman {self.TAIL}"], "--allow-repeat")
        self.assertEqual(code, 0, out)
        self.assertIn("repeats this phrase", out)

    def test_allow_repeat_keeps_case_check_on_loose_repeat(self):
        code, out = run(self.PAGE, [f"City-woman {self.TAIL}"], "--allow-repeat")
        self.assertEqual(code, 1, out)
        self.assertIn("CASE DIFFERS", out)


class LooseMatch(unittest.TestCase):
    def test_compound_split_at_line_end(self):
        self.assertEqual(run("the city-\nwoman walked", ["city-woman walked"])[0], 0)


    def test_repeating_start_is_flagged(self):
        page = ("Transitional justice has become a globally dominant lens through which to approach states. An industry has emerged.\n"
                "Introduction\nTransitional justice has become a globally dominant lens through which to approach states, most often implemented widely.")
        part = "Transitional justice has become a globally dominant lens through which to approach states, most often implemented widely."
        code, out = run(page, [part])
        self.assertEqual(code, 1, out)
        self.assertIn("EDGE REPEATS", out)

    def test_first_copy_of_a_repeated_sentence_passes(self):
        abstract = "The seamless continuity between colonialism, racism, and patriarchy makes it imperative to question the category of gender."
        body = "The seamless continuity between colonialism, racism, and patriarchy makes it imperative to call into question the category of gender."
        page = abstract + " Keywords.\nIntroduction\n" + body
        self.assertEqual(run(page, [abstract])[0], 0)
        code, out = run(page, [body])
        self.assertEqual(code, 1, out)
        self.assertIn("EDGE REPEATS", out)

    def test_short_part_with_repeated_opening_passes(self):
        # 100 characters or fewer: the tool's exact search finds the part itself, not its opening words.
        page = "Delta epsilon zeta eta theta iota once. Delta epsilon zeta eta theta iota kappa lambda mu."
        self.assertEqual(run(page, ["Delta epsilon zeta eta theta iota kappa lambda mu."])[0], 0)

    def test_span_after_dotted_capital_i_is_printed_exactly(self):
        # "İ" lowercases to two characters; the printed span must still be the page's own words.
        code, out = run("İstanbul was the setting. The state remembers selectively.", ["remembers selectively"])
        self.assertEqual(code, 0, out)
        self.assertIn("found: 'remembers selectively'", out)

    def test_short_quote_measured_on_the_printed_span(self):
        # A part of 101 characters whose page span has a ligature is 100 characters as given to the tool,
        # so a repeat under --allow-repeat stays AMBIGUOUS.
        span = "The ﬁrst " + "x" * 91
        part = "The first " + "x" * 91
        self.assertEqual((len(part), len(span)), (101, 100))
        code, out = run(span + " and. " + span + " again.", [part], "--allow-repeat")
        self.assertEqual(code, 1, out)
        self.assertIn("AMBIGUOUS", out)

    def test_unique_part_of_40_characters_passes(self):
        page = "Alpha beta gamma. Delta epsilon zeta eta theta iota kappa. Lambda mu."
        self.assertEqual(run(page, ["Delta epsilon zeta eta theta iota kappa."])[0], 0)

    def test_undecodable_page_is_bad_input(self):
        with tempfile.TemporaryDirectory() as d:
            pg, pt = Path(d, "page.txt"), Path(d, "parts.txt")
            pg.write_bytes(b"\xff\xfe\xfa not utf-8")
            pt.write_text("some part")
            r = subprocess.run([sys.executable, "-I", str(SCRIPT), str(pg), str(pt)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)

    def test_unique_edges_pass(self):
        page = "Alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi omicron pi."
        self.assertEqual(run(page, ["gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi"])[0], 0)

class LooseMatchChecks(unittest.TestCase):
    def test_loose_case_difference_flagged(self):
        code, out = run("the city-\nwoman walked", ["City-woman walked"])
        self.assertEqual(code, 1, out)
        self.assertIn("CASE DIFFERS", out)

    def test_loose_repeating_edge_flagged(self):
        lead = "Alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi omicron pi rho sigma"
        page = lead + " one. Elsewhere, " + lead + " two city-\nwoman walked"
        code, out = run(page, [lead + " two city-woman walked"])
        self.assertEqual(code, 1, out)
        self.assertIn("EDGE REPEATS", out)
        # An end that repeats only after the part's own end is harmless: the tool takes the first end after the start.
        # Over 100 characters, so edge_repeat reaches its end search.
        tail = "mu nu xi omicron pi rho sigma tau upsilon phi chi psi omega alpha beta gamma delta epsilon zeta"
        page = "city-\nwoman walked first " + tail + ". Later " + tail + "."
        code, out = run(page, ["city-woman walked first " + tail])
        self.assertEqual(code, 0, out)

    def test_loose_clean_match_found(self):
        code, out = run("the city-\nwoman walked", ["city-woman walked"])
        self.assertEqual(code, 0, out)
        self.assertIn("found", out)


if __name__ == "__main__":
    unittest.main()
