import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)
sys.path.insert(0, SCRIPTS)
sys.path.insert(0, os.path.join(SCRIPTS, "shared"))
import reference_check as rc  # noqa: E402
import citelib  # noqa: E402
import citation_audit  # noqa: E402


def run(script, *args):
    return subprocess.run([sys.executable, os.path.join(SCRIPTS, script), *args], capture_output=True, text=True)


class RunTools(unittest.TestCase):
    def test_tofile_saves_stdout_and_passes_the_exit_code(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "s.py")
            open(src, "w").write("import sys\nprint('hello')\nsys.exit(3)\n")
            out = os.path.join(d, "o.txt")
            p = run("tofile.py", out, src)
            self.assertEqual(p.returncode, 3)
            self.assertEqual(open(out).read().strip(), "hello")
            self.assertIn("wrote", p.stdout)

    def test_tofile_rejects_a_missing_script(self):
        self.assertEqual(run("tofile.py", "/tmp/none.json", "/no/such/script.py").returncode, 2)

    def test_runfolder_new_then_remove(self):
        with tempfile.TemporaryDirectory() as base:
            p = run("runfolder.py", "new", base)
            self.assertEqual(p.returncode, 0)
            path = p.stdout.strip()
            self.assertTrue(os.path.isdir(path))
            self.assertTrue(os.path.basename(path).startswith("plagiarism-check-"))
            self.assertEqual(run("runfolder.py", "remove", path).returncode, 0)
            self.assertFalse(os.path.exists(path))

    def test_runfolder_refuses_other_folders(self):
        with tempfile.TemporaryDirectory() as base:
            self.assertEqual(run("runfolder.py", "remove", base).returncode, 2)
            self.assertTrue(os.path.isdir(base))
            self.assertEqual(run("runfolder.py", "remove", "relative/plagiarism-check-x").returncode, 2)


class NoDate(unittest.TestCase):
    DRAFT = "# T\n\nLocal memory is thin (Thorne n.d.) and Brandt (2015) disagrees.\n\n## References\n\nThorne, R. Hill farms in memory. Unpublished report.\n\nBrandt, E. (2015) Harbour dues. Press.\n"

    def test_undated_citation_and_entry_match(self):
        a = citation_audit.audit(self.DRAFT)
        self.assertEqual(a["citations"], 2)
        self.assertEqual(a["bibliography_entries"], 2)
        self.assertEqual(a["unmatched_citations"], [])
        self.assertEqual(a["uncited_bibliography"], [])

    def test_year_less_entry_keeps_its_first_author(self):
        e = rc.parse(self.DRAFT)[0]
        self.assertEqual(e["first_author"], "Thorne")
        self.assertEqual(e["title"], "Hill farms in memory")
        self.assertEqual(e["year"], "")
        self.assertIn("year", [m["field"] for m in e["fields_missing"]])

    def test_n_d_in_a_list_entry_counts_as_a_year(self):
        e = rc.parse("# T\n\n(A n.d.)\n\n## References\n\nA, B. (n.d.) A title here. Press.\n")[0]
        self.assertEqual(e["year"], "n.d.")


if __name__ == "__main__":
    unittest.main()
