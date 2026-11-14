import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import reference_check as rc  # noqa: E402
import report_lint  # noqa: E402

DRAFT = """# T

Grazing is shared (Hardin 1968; Watson and Crick 1954). Also (Quill 2011).

## References

Hardin, G. (1968) 'The Tragedy of the Commons', Science, 162(3859), pp. 1243-1248. doi:10.1126/science.162.3859.1243

Watson, J.D. and Crick, F.H.C. (1953) 'Molecular structure of nucleic acids', Nature, 171, pp. 737-738. doi:10.1038/171737a0

Quillfeather, M. (2011) 'Grazing and the ethics of pasture', Journal of Applied Pasture Studies, 14(2), pp. 55-71. doi:10.1016/j.japs.2011.04.009

Kuhn, T.S. (1962) The Structure of Scientific Revolutions. Chicago: University of Chicago Press.

Fenwick, A. (2004) Hill farms in memory. Unpublished report. Available at: https://example.org/report
"""

INDEX = {"doi": {"10.1126/science.162.3859.1243": {"title": "The Tragedy of the Commons", "year": "1968", "authors": ["Hardin"], "venue": "Science", "doi": "10.1126/science.162.3859.1243", "url": "https://doi.org/10.1126/science.162.3859.1243"},
                 "10.1038/171737a0": {"title": "Molecular Structure of Nucleic Acids: A Structure for Deoxyribose Nucleic Acid", "year": "1953", "authors": ["Watson", "Crick"], "venue": "Nature", "doi": "10.1038/171737a0", "url": "https://doi.org/10.1038/171737a0"}},
         "title": {"the structure of scientific revolutions": {"title": "The Structure of Scientific Revolutions", "year": "1962", "authors": ["Kuhn"], "type": "book"}}}


def run():
    ents = rc.parse(DRAFT)
    recs = {str(e["n"]): rc.lookup_one(e, INDEX) for e in ents}
    return ents, recs, rc.verdicts(ents, recs)


class ReferenceCheck(unittest.TestCase):
    def test_parse_fields_and_missing(self):
        ents = rc.parse(DRAFT)
        self.assertEqual(len(ents), 5)
        self.assertEqual(ents[0]["doi"], "10.1126/science.162.3859.1243")
        self.assertEqual(ents[3]["kind"], "book")
        self.assertIn("publisher", [m["field"] for m in ents[3]["fields_missing"]] + ["publisher"])
        missing = {m["field"] for m in ents[4]["fields_missing"]}
        self.assertEqual(ents[4]["kind"], "web")
        self.assertNotIn("doi", missing)
        self.assertTrue(all("look_in" in m for m in ents[4]["fields_missing"]))

    def test_outcomes(self):
        _, _, v = run()
        out = {e["n"]: e["outcome"] for e in v["entries"]}
        self.assertEqual(out[1], "Clean")
        self.assertEqual(out[2], "Clean")          # title is contained in the record title
        self.assertEqual(out[3], "Not found")      # DOI absent from the index, article
        self.assertEqual(out[4], "Clean")
        self.assertEqual(out[5], "Review")         # grey literature is never "Not found"

    def test_fabricated_never_fixed_no_doi_added(self):
        _, _, v = run()
        e3 = v["entries"][2]
        self.assertEqual(e3["patches"], [])
        for e in v["entries"]:
            for p in e["patches"]:
                self.assertNotEqual(p["field"], "doi")
        e4 = v["entries"][3]
        self.assertIn("none has been added", e4["note"])

    def test_wrong_year_fix_keeps_original(self):
        draft = DRAFT.replace("(1968)", "(1969)")
        ents = rc.parse(draft)
        recs = {str(e["n"]): rc.lookup_one(e, INDEX) for e in ents}
        v = rc.verdicts(ents, recs)
        e1 = v["entries"][0]
        self.assertEqual(e1["outcome"], "Fix")
        p = e1["patches"][0]
        self.assertEqual((p["field"], p["original"], p["proposed"]), ("year", "1969", "1968"))
        self.assertTrue(p["source"] and p["reason"])

    def test_frankenstein_doi_points_elsewhere(self):
        draft = DRAFT.replace("'The Tragedy of the Commons'", "'Pasture ethics and the household'")
        ents = rc.parse(draft)
        recs = {str(e["n"]): rc.lookup_one(e, INDEX) for e in ents}
        e1 = rc.verdicts(ents, recs)["entries"][0]
        self.assertEqual(e1["outcome"], "Review")
        self.assertIn("frankenstein", e1["flags"])
        self.assertEqual(e1["patches"], [])

    def test_cross_near_match(self):
        c = rc.cross(DRAFT)
        near = {u["citation"]: u["near_match"] for u in c["unmatched_citations"]}
        self.assertEqual(near["Watson and Crick 1954"]["list_year"], "1953")
        self.assertIsNone(near["Quill 2011"])

    def test_offline_all_review(self):
        e = rc.parse(DRAFT)[0]
        self.assertEqual(rc.lookup_one(e, None, True)["status"], "not looked up")
        v = rc.verdicts([e], {"1": {"status": "not looked up"}})
        self.assertEqual(v["entries"][0]["outcome"], "Review")

    def test_invalid_isbn_noted_on_book_year_review(self):
        draft = "# T\n\n(Kuhn 1962)\n\n## References\n\nKuhn, T.S. (1961) The Structure of Scientific Revolutions. Chicago: University of Chicago Press. ISBN 9780226458114\n"
        ents = rc.parse(draft)
        recs = {"1": {"status": "found", "title": "The Structure of Scientific Revolutions", "year": "1963", "authors": ["Kuhn"], "type": "book"}}
        e = rc.verdicts(ents, recs)["entries"][0]
        self.assertIn("checksum", e["note"])

    def test_isbn_of_a_different_book_is_flagged(self):
        draft = "# T\n\n(Kuhn 1962)\n\n## References\n\nKuhn, T.S. (1962) The Structure of Scientific Revolutions. Chicago: University of Chicago Press. ISBN 9780521405997\n"
        ents = rc.parse(draft)
        recs = {"1": {"status": "found", "title": "The Structure of Scientific Revolutions", "year": "1962", "authors": ["Kuhn"], "type": "book", "isbn_records": ["Governing the Commons"]}}
        e = rc.verdicts(ents, recs)["entries"][0]
        self.assertEqual(e["outcome"], "Review")
        self.assertIn("frankenstein", e["flags"])

    def test_shared_isbn_is_flagged_offline(self):
        draft = "# T\n\n(A 2000; B 2001)\n\n## References\n\nA, X. (2000) First title here. Press One. ISBN 9780226458113\n\nB, Y. (2001) Second title here. Press Two. ISBN 9780226458113\n"
        ents = rc.parse(draft)
        v = rc.verdicts(ents, {str(e["n"]): {"status": "not looked up"} for e in ents})
        self.assertTrue(all("shared-identifier" in e["flags"] for e in v["entries"]))
        self.assertIn("shares its ISBN with entry 2", v["entries"][0]["note"])

    def test_table_never_cuts_an_identifier(self):
        _, _, v = run()
        t = rc.table(v)
        self.assertIn("doi:10.1126/science.162.3859.1243", t)

    def test_table_has_required_lines(self):
        _, _, v = run()
        t = rc.table(v)
        self.assertIn("Entries are formatted or checked, not verified.", t)
        self.assertIn("nothing found through the search used", t)


class Lint(unittest.TestCase):
    OK = "Clean means nothing found through the search used.\n"

    def rules(self, text, refs=None):
        return {p["rule"] for p in report_lint.lint(text, refs)}

    def test_clean(self):
        self.assertEqual(self.rules(self.OK + "The writer should add a quotation mark."), set())

    def test_rules(self):
        self.assertIn("accuse", self.rules(self.OK + "You plagiarised this passage."))
        self.assertIn("evade", self.rules(self.OK + "Reword it to avoid detection."))
        self.assertIn("offer", self.rules(self.OK + "Would you like me to check the next one?"))
        self.assertIn("gendered", self.rules(self.OK + "She should cite it."))
        self.assertIn("limits", self.rules("Everything is fine."))
        self.assertIn("rewrite", self.rules(self.OK + "Suggested wording: the canal opened"))

    def test_a_refusal_to_advise_on_evasion_is_allowed(self):
        self.assertEqual(self.rules(self.OK + "This skill does not advise on how to avoid detection."), set())
        self.assertIn("evade", self.rules(self.OK + "Swap the synonyms to avoid detection."))

    def test_nested_quotation_marks_are_ignored(self):
        line = 'okafor: "Okafor argues that "the licence created the owner as much as it charged him" (Okafor 2011)" is disputed.'
        self.assertEqual(self.rules(self.OK + line), set())

    def test_quotes_ignored(self):
        self.assertEqual(self.rules(self.OK + 'The draft says "she would like to avoid detection" in a quotation.'), set())

    def test_invented_doi(self):
        refs = {"entries": [{"reference": "x 10.1126/science.162.3859.1243"}]}
        self.assertEqual(self.rules(self.OK + "DOI 10.1126/science.162.3859.1243 given.", refs), set())
        self.assertIn("invented-id", self.rules(self.OK + "Use DOI 10.9999/made.up.1 instead.", refs))


if __name__ == "__main__":
    unittest.main()
