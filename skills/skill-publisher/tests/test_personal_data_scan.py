"""Unit tests for scripts/personal_data_scan.py (run: python3 -m unittest discover -s tests)."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "personal_data_scan.py"
sys.path.insert(0, str(SCRIPT.parent))
import personal_data_scan as pds  # noqa: E402


# Test data is assembled at run time so this file itself holds no scannable personal-looking strings.
CODE = "QRX" + "4821"
LABEL = "PS" + "1"
LEAK = "/Users/" + "jsmith"
PLACEHOLDER = "/Users/" + "priya"
VENDOR = "type.author@" + "fonts-example.org"
GMAIL = "someone@" + "gmail.com"
SUPPORT = "support@" + "example-vendor.org"


def run(args, stdin=None):
    r = subprocess.run([sys.executable, str(SCRIPT), *args], input=stdin, capture_output=True, text=True)
    return r.returncode, json.loads(r.stdout) if r.stdout.strip() else {}


class ScanText(unittest.TestCase):
    def kinds(self, text, label="x.md", terms=(), patterns=()):
        return sorted({f["kind"] for f in pds.scan_text(text, label, list(terms), None, list(patterns))})

    def test_module_code_and_assessment_label(self):
        self.assertEqual(self.kinds(f"see {CODE} {LABEL}"), ["module-assessment", "module-code"])

    def test_assessment_label_alone_is_not_flagged(self):
        self.assertEqual(self.kinds(f"{LABEL} is fine alone"), [])

    def test_standards_names_are_exempt(self):
        self.assertEqual(self.kinds("ISO8601 and RFC3339 and AAA0000"), [])

    def test_gendered_pronouns_in_markdown_only(self):
        self.assertEqual(self.kinds("she said", "a.md"), ["gendered-pronoun"])
        self.assertEqual(self.kinds("she said", "a.py"), [])

    def test_higher_education_acronym_is_not_a_pronoun(self):
        self.assertEqual(self.kinds("UK HE sector"), [])

    def test_home_path_and_placeholder(self):
        self.assertEqual(self.kinds(f"at {LEAK}/x"), ["home-path"])
        self.assertEqual(self.kinds(f"at {PLACEHOLDER}/x"), [])

    def test_profile_pattern_is_case_sensitive(self):
        import re
        pat = [re.compile(r"\b[A-Z]{3}\d{4}\b")]
        self.assertEqual(self.kinds("the 2026", patterns=pat), [])


class Allowlist(unittest.TestCase):
    """The allowlist must be applied by the scan itself (it was defined but never called once)."""

    def test_allowlisted_file_and_placeholder_are_not_reported(self):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            (t / "skill" / "references").mkdir(parents=True)
            (t / "skill" / "THIRD_PARTY_NOTICES.md").write_text(f"Credit: {VENDOR}\n")
            (t / "skill" / "references" / "leak.md").write_text(f"Left in: {LEAK}/thesis\n")
            (t / "skill" / "references" / "example.md").write_text(f"Example {PLACEHOLDER}/project\n")
            profile = t / "profile.md"
            profile.write_text("- `scan_allowlist`: path:THIRD_PARTY_NOTICES.md\n")
            code, out = run([str(t / "skill"), "--profile", str(profile)])
            self.assertEqual(code, 1)
            found = {(f["file"], f["match"]) for f in out["findings"]}
            self.assertEqual(found, {("references/leak.md", LEAK)})

    def test_exact_match_allowlist_entry(self):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            profile = t / "p.md"
            profile.write_text(f"- `scan_allowlist`: {SUPPORT}\n")
            code, out = run(["-", "--profile", str(profile)], stdin=f"Mail {SUPPORT}\n")
            self.assertEqual(code, 0)
            self.assertTrue(out["clean"])

    def test_no_profile_reports_everything(self):
        code, out = run(["-"], stdin=f"Mail {GMAIL}\n")
        self.assertEqual(code, 1)
        self.assertEqual(out["findings"][0]["kind"], "email")


if __name__ == "__main__":
    unittest.main()
