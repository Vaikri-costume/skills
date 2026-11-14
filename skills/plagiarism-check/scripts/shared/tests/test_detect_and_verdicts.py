"""Tests for full-scan source detection and verdict-line parsing. Run: python3 -m unittest discover -s ${CLAUDE_SKILL_DIR}/scripts/shared/tests"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SHARED = os.path.dirname(HERE)
sys.path.insert(0, SHARED)

from synthesise_verdicts import parse  # noqa: E402


class FullScanSources(unittest.TestCase):
    DRAFT = "# T\n\nIt is argued (Lindqvist 1999) that ports declined.\n\n## References\n\nLindqvist, A. (1999) The Silting of the Estuary Ports.\n"

    def run_scan(self, mode):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "sources")
            os.mkdir(src)
            for n in ("src-lindqvist-1999.txt", "src-okafor-2011.txt"):
                with open(os.path.join(src, n), "w") as f:
                    f.write("text")
            draft = os.path.join(d, "draft.md")
            with open(draft, "w") as f:
                f.write(self.DRAFT)
            p = subprocess.run([sys.executable, os.path.join(SHARED, "detect_sources.py"), "--mode", mode, "--draft-path", draft,
                                "--format", "author-date", "--sources-dir", src], capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            return json.loads(p.stdout)

    def test_full_scan_lists_the_uncited_source_file(self):
        ids = {r["id"]: r for r in self.run_scan("full-scan")}
        self.assertIn("src-okafor-2011", ids)
        self.assertFalse(ids["src-okafor-2011"]["cited"])
        self.assertTrue(ids["src-okafor-2011"]["resolved"])
        self.assertTrue(ids["lindqvist 1999"]["resolved"])

    def test_citation_check_lists_only_cited_works(self):
        ids = [r["id"] for r in self.run_scan("citation-check")]
        self.assertEqual(ids, ["lindqvist 1999"])


class VerdictLines(unittest.TestCase):
    def test_a_full_stop_after_the_label_is_not_part_of_the_question(self):
        t = '## Challenger assessment: Finding 5\nx\nVerdict: AMBIGUOUS. Did you read the papers yourself?\n'
        self.assertEqual(parse(t)[5], ('AMBIGUOUS', 'Did you read the papers yourself?'))

    def test_a_full_stop_after_a_disputed_label(self):
        t = '## Challenger assessment: Finding 6\nx\nVerdict: DISPUTED. The quotation is marked.\n'
        self.assertEqual(parse(t)[6], ('DISPUTED', 'The quotation is marked.'))


if __name__ == "__main__":
    unittest.main()
