import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SHARED = os.path.dirname(HERE)

DRAFT = """Public ownership is usually defended on grounds of reliability. Brandt (2015) argues that the stronger case is about route planning. Anderson (2018) reaches a similar conclusion from the opposite direction, and Sandhu (2020) asked the islanders themselves.

## References

Anderson, P. (2018) Subsidy and the island route. Glasgow: Clyde Press. ISBN 978-0-306-40615-9.

Brandt, K. (2015) Routes and ownership. Retrieved from https://example.org/report?utm_source=chatgpt.com

Sandhu, N. (2020) What islanders value. Journal of Rural Transport 12(2): 33-49. https://doi.org/10.1000/

Okonkwo, E. (2019) Timetables and trust. Cardiff: Taff Books.
"""


def audit(text):
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "draft.md")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(text)
        out = subprocess.run([sys.executable, os.path.join(SHARED, "citation_audit.py"), p], capture_output=True, text=True)
    return json.loads(out.stdout)


class CitationAudit(unittest.TestCase):
    def test_surnames_containing_and_are_matched(self):
        r = audit(DRAFT)
        self.assertEqual(r["unmatched_citations"], [])

    def test_uncited_entry_is_listed(self):
        r = audit(DRAFT)
        self.assertTrue(any("Okonkwo" in e for e in r["uncited_bibliography"]))

    def test_reference_artefacts_are_found(self):
        kinds = {a["kind"] for a in audit(DRAFT)["artefacts"]}
        self.assertTrue({"utm-parameter", "malformed-doi", "invalid-isbn-checksum"} <= kinds)

    def test_clean_draft_has_no_artefacts(self):
        r = audit("Brandt (2015) argues the point.\n\n## References\n\nBrandt, K. (2015) Routes and ownership. Leeds: Calder Books.\n")
        self.assertEqual(r["artefacts"], [])
        self.assertEqual(r["uncited_bibliography"], [])


if __name__ == "__main__":
    unittest.main()
