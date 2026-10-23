import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
SCHEMA = {
    "link_type_properties": ["related"],
    "canonicalization": {"type": {"reading notes": "Reading Notes", "note": "Note"}},
    "writer_vocab_plain": ["Claude"],
    "zotero_itemtypes": [],
}


def run(script, *args):
    return subprocess.run([sys.executable, "-I", str(SCRIPTS / script), *args], capture_output=True, text=True)


class MaintenanceScripts(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.root = Path(self.d.name)
        self.schema = self.root / "schema.json"
        self.schema.write_text(json.dumps(SCHEMA))

    def tearDown(self):
        self.d.cleanup()

    def test_flat_vault_journals_scanned_once(self):
        (self.root / "journals").mkdir()
        (self.root / "A.md").write_text("- see [[Gone]]\n")
        (self.root / "journals" / "J.md").write_text("- see [[Gone Too]]\n")
        r = run("graph-link-audit.py", str(self.root), str(self.schema), "--pages-dir", ".")
        self.assertIn("scanned 2 files", r.stdout)

    def test_links_only_leaves_bold_alone(self):
        (self.root / "A.md").write_text("- **bold** [[Gone]]\n")
        r = run("graph-link-audit.py", str(self.root), str(self.schema), "--pages-dir", ".", "--links-only")
        self.assertNotIn("bold-markdown", r.stdout)
        self.assertIn("dangling-link", r.stdout)

    def test_dangling_bracket_in_non_link_property(self):
        (self.root / "pages").mkdir()
        (self.root / "pages" / "A.md").write_text("source:: [[Gone]]\n\n- x\n")
        run("graph-link-audit.py", str(self.root), str(self.schema), "--apply-safe-fixes")
        self.assertIn("source:: Gone", (self.root / "pages" / "A.md").read_text())

    def test_schema_pass_comma_types_and_reading_notes_author(self):
        (self.root / "pages").mkdir()
        p = self.root / "pages" / "A.md"
        p.write_text("type:: reading notes, note\nwriter:: Claude\nauthor:: [[Said]]\n\n- x\n")
        run("schema-pass.py", str(self.root), str(self.schema), "--apply")
        self.assertEqual(p.read_text(), "type:: Reading Notes, Note\nwriter:: Claude\nauthor:: [[Said]]\n\n- x\n")

    def test_alias_and_heading_links_to_existing_pages_are_kept(self):
        (self.root / "A.md").write_text("- see [[B|the b page]] and [[B#Intro]] and [[Gone|shown]]\n")
        (self.root / "B.md").write_text("- b\n")
        run("graph-link-audit.py", str(self.root), str(self.schema), "--pages-dir", ".", "--apply-safe-fixes")
        self.assertEqual((self.root / "A.md").read_text(), "- see [[B|the b page]] and [[B#Intro]] and shown\n")

    def test_generic_type_dropped_from_comma_form_and_primary_source_author_kept(self):
        schema = dict(SCHEMA, drop_type_when_specific_present={"Concept": ["Vocabulary"]})
        schema["canonicalization"] = {"type": {"concept": "Concept", "vocabulary": "Vocabulary", "primary source": "Primary Source"}}
        sp = self.root / "s2.json"
        sp.write_text(json.dumps(schema))
        (self.root / "pages").mkdir()
        a = self.root / "pages" / "A.md"
        a.write_text("type:: concept, vocabulary\n\n- x\n")
        b = self.root / "pages" / "B.md"
        b.write_text("type:: primary source\nauthor:: [[Said]]\n\n- x\n")
        run("schema-pass.py", str(self.root), str(sp), "--apply")
        self.assertEqual(a.read_text(), "type:: Vocabulary\n\n- x\n")
        self.assertEqual(b.read_text(), "type:: Primary Source\nauthor:: [[Said]]\n\n- x\n")

    def test_property_normalize_runs_on_a_schema_without_canonicalization(self):
        (self.root / "pages").mkdir()
        (self.root / "pages" / "A.md").write_text("type:: note\n\n- x\n")
        bare = self.root / "bare.json"
        bare.write_text("{}")
        r = run("property-normalize.py", str(self.root), str(bare))
        self.assertEqual(r.returncode, 0)

    def test_namespaced_link_in_link_property_is_left_alone(self):
        (self.root / "A.md").write_text("related:: [[A/B]]\n\n- x\n")
        r = run("graph-link-audit.py", str(self.root), str(self.schema), "--pages-dir", ".")
        self.assertNotIn("dangling-bracketed-link", r.stdout)

    def test_two_links_in_one_property_value_are_left_alone(self):
        (self.root / "pages").mkdir()
        (self.root / "pages" / "A.md").write_text("related:: [[B]] [[C]]\n\n- x\n")
        (self.root / "pages" / "B.md").write_text("- b\n")
        (self.root / "pages" / "C.md").write_text("- c\n")
        run("graph-link-audit.py", str(self.root), str(self.schema), "--apply-safe-fixes")
        self.assertEqual((self.root / "pages" / "A.md").read_text(), "related:: [[B]] [[C]]\n\n- x\n")

    def test_link_inside_bold_is_unbolded_then_unbracketed(self):
        (self.root / "A.md").write_text("- **[[Gone]]** text and **see [[Gone2]] now**\n")
        run("graph-link-audit.py", str(self.root), str(self.schema), "--pages-dir", ".", "--apply-safe-fixes")
        self.assertEqual((self.root / "A.md").read_text(), "- Gone text and see Gone2 now\n")

    def test_blank_writer_on_a_template_is_kept(self):
        (self.root / "pages" / "Templates").mkdir(parents=True)
        t = self.root / "pages" / "Templates" / "Notes Template.md"
        t.write_text("type:: Reading Notes\nwriter::\nstatus::\n\n- x\n")
        run("graph-link-audit.py", str(self.root), str(self.schema), "--apply-safe-fixes")
        self.assertEqual(t.read_text(), "type:: Reading Notes\nwriter::\nstatus::\n\n- x\n")
        n = self.root / "pages" / "Made From It.md"
        n.write_text("type:: Reading Notes\nwriter::\n\n- x\n")
        run("graph-link-audit.py", str(self.root), str(self.schema), "--apply-safe-fixes")
        self.assertEqual(n.read_text(), "type:: Reading Notes\nwriter::\n\n- x\n")

    def test_dangling_link_inside_a_compound_link_property_value(self):
        (self.root / "pages").mkdir(exist_ok=True)
        (self.root / "pages" / "B.md").write_text("- b\n")
        a = self.root / "pages" / "A.md"
        a.write_text("related:: [[B]] [[Gone]]\n\n- x\n")
        run("graph-link-audit.py", str(self.root), str(self.schema), "--apply-safe-fixes")
        self.assertEqual(a.read_text(), "related:: [[B]] Gone\n\n- x\n")

    def test_same_page_heading_and_attachment_links_are_kept(self):
        (self.root / "assets").mkdir()
        (self.root / "assets" / "photo.png").write_text("x")
        a = self.root / "A.md"
        a.write_text("- see [[#Intro]] and [[photo.png]] and [[Gone]]\n")
        run("graph-link-audit.py", str(self.root), str(self.schema), "--pages-dir", ".", "--apply-safe-fixes")
        self.assertEqual(a.read_text(), "- see [[#Intro]] and [[photo.png]] and Gone\n")

    def test_one_line_fence_does_not_hide_the_rest_of_the_page(self):
        a = self.root / "A.md"
        a.write_text("- ```x```\n- see [[Gone]]\n")
        run("graph-link-audit.py", str(self.root), str(self.schema), "--pages-dir", ".", "--apply-safe-fixes")
        self.assertEqual(a.read_text(), "- ```x```\n- see Gone\n")

    def test_block_level_type_survives_a_generic_type_drop_and_zotero_types_match_any_case(self):
        schema = dict(SCHEMA, drop_type_when_specific_present={"Concept": ["Vocabulary"]}, zotero_itemtypes=["journalArticle"])
        schema["canonicalization"] = {"type": {"concept": "Concept", "vocabulary": "Vocabulary"}}
        sp = self.root / "s3.json"
        sp.write_text(json.dumps(schema))
        (self.root / "pages").mkdir()
        a = self.root / "pages" / "A.md"
        a.write_text("type:: vocabulary\nitem-type:: journalArticle\n\n- block\n  type:: concept\n")
        run("schema-pass.py", str(self.root), str(sp), "--apply")
        self.assertEqual(a.read_text(), "type:: Vocabulary\nitem-type:: journalArticle\n\n- block\n  type:: Concept\n")

    def test_bold_strip_keeps_inline_code_text(self):
        a = self.root / "A.md"
        a.write_text("- **use `x` here**\n")
        run("graph-link-audit.py", str(self.root), str(self.schema), "--pages-dir", ".", "--apply-safe-fixes")
        self.assertEqual(a.read_text(), "- use `x` here\n")

    def test_fenced_example_lines_are_not_rewritten(self):
        (self.root / "pages").mkdir()
        a = self.root / "pages" / "A.md"
        body = "type:: note\n\n- ```\n  type:: reading notes\n  ```\n"
        a.write_text(body)
        run("schema-pass.py", str(self.root), str(self.schema), "--apply")
        run("property-normalize.py", str(self.root), str(self.schema), "--apply")
        self.assertEqual(a.read_text(), body.replace("type:: note", "type:: Note"))

    def test_fenced_type_line_survives_a_generic_type_drop(self):
        schema = dict(SCHEMA, drop_type_when_specific_present={"Concept": ["Vocabulary"]})
        schema["canonicalization"] = {"type": {"concept": "Concept", "vocabulary": "Vocabulary"}}
        sp = self.root / "s4.json"
        sp.write_text(json.dumps(schema))
        (self.root / "pages").mkdir()
        a = self.root / "pages" / "A.md"
        a.write_text("type:: Concept, Vocabulary\n\n- ```\ntype:: Concept, Vocabulary\n```\n")
        run("schema-pass.py", str(self.root), str(sp), "--apply")
        self.assertEqual(a.read_text(), "type:: Vocabulary\n\n- ```\ntype:: Concept, Vocabulary\n```\n")

    def test_quoted_title_and_bracketed_alias_resolve(self):
        (self.root / "pages").mkdir()
        (self.root / "pages" / "Page One.md").write_text('title:: "Quoted Title"\nalias:: [[Other Name]]\n\n- x\n')
        a = self.root / "pages" / "A.md"
        a.write_text("- see [[Quoted Title]] and [[Other Name]]\n")
        run("graph-link-audit.py", str(self.root), str(self.schema), "--apply-safe-fixes")
        self.assertEqual(a.read_text(), "- see [[Quoted Title]] and [[Other Name]]\n")

    def test_blank_title_collision_remains_only_for_kept_template_lines(self):
        (self.root / "pages" / "Templates").mkdir(parents=True)
        for name in ("A Template.md", "B Template.md"):
            (self.root / "pages" / "Templates" / name).write_text("title::\n\n- x\n")
        r = run("graph-link-audit.py", str(self.root), str(self.schema), "--apply-safe-fixes")
        self.assertIn("blank-title-collision", r.stdout)
        for name in ("C.md", "D.md"):
            (self.root / "pages" / name).write_text("title::\n\n- x\n")
        r = run("graph-link-audit.py", str(self.root), str(self.schema), "--apply-safe-fixes")
        collision = [l for l in r.stdout.splitlines() if "fight for the same blank identity" in l]
        self.assertTrue(collision)
        self.assertFalse([l for l in collision if "C.md" in l or "D.md" in l])

    def test_space_indented_heading_candidates_are_found(self):
        (self.root / "pages").mkdir()
        a = self.root / "pages" / "A.md"
        a.write_text("- parent\n  - **Label** — content\n")
        r = run("graph-heading-extract.py", str(self.root))
        self.assertIn("Label", r.stdout)

    def test_colon_after_the_bold_label_is_not_left_in_the_content(self):
        (self.root / "pages").mkdir()
        a = self.root / "pages" / "A.md"
        a.write_text("- **Term**: definition here\n")
        run("graph-heading-extract.py", str(self.root), "--apply")
        self.assertNotIn("- : ", a.read_text())
        self.assertIn("definition here", a.read_text())

    def test_lone_colon_after_the_bold_label_with_children_adds_no_content_bullet(self):
        (self.root / "pages").mkdir()
        a = self.root / "pages" / "A.md"
        a.write_text("- **Definition**:\n\t- child text\n")
        run("graph-heading-extract.py", str(self.root), "--apply")
        self.assertNotIn("- :", a.read_text())
        self.assertIn("heading:: true", a.read_text())

    def test_space_indented_candidate_gets_a_space_indented_child(self):
        (self.root / "pages").mkdir()
        a = self.root / "pages" / "A.md"
        a.write_text("- parent\n  - **Label** — content\n")
        run("graph-heading-extract.py", str(self.root), "--apply")
        self.assertNotIn("\t", a.read_text())
        self.assertIn("    - content", a.read_text())

    def test_top_level_candidate_in_a_space_indented_file_gets_a_space_child(self):
        (self.root / "pages").mkdir()
        a = self.root / "pages" / "A.md"
        a.write_text("- **Label** — content\n  - sibling\n")
        run("graph-heading-extract.py", str(self.root), "--apply")
        self.assertNotIn("\t", a.read_text())

    def test_bold_inside_inline_code_in_a_property_value_is_kept(self):
        a = self.root / "A.md"
        a.write_text("example:: use `**x**` here and **y** there\n\n- x\n")
        run("graph-link-audit.py", str(self.root), str(self.schema), "--pages-dir", ".", "--apply-safe-fixes")
        self.assertEqual(a.read_text(), "example:: use `**x**` here and y there\n\n- x\n")

    def test_unmapped_type_already_in_the_vocabulary_is_not_title_cased(self):
        (self.root / "pages").mkdir()
        a = self.root / "pages" / "A.md"
        a.write_text("type:: Entity or Person\n\n- x\n")
        schema = dict(SCHEMA, type_vocab=["Entity or Person"])
        sp = self.root / "s4.json"
        sp.write_text(json.dumps(schema))
        run("schema-pass.py", str(self.root), str(sp), "--apply")
        self.assertEqual(a.read_text(), "type:: Entity or Person\n\n- x\n")

    def test_schema_lint_reads_a_comma_inside_a_bracketed_writer_as_one_writer(self):
        (self.root / "pages").mkdir()
        (self.root / "pages" / "A.md").write_text("type:: Note\nwriter:: [[Said, Edward]]\n\n- x\n")
        r = run("schema-lint.py", str(self.root), str(self.schema))
        self.assertNotIn("Edward", r.stdout + r.stderr)

    def test_template_placeholder_link_is_not_unbracketed(self):
        (self.root / "pages" / "Templates").mkdir(parents=True)
        t = self.root / "pages" / "Templates" / "Reading Notes Template.md"
        t.write_text("template:: Reading Notes\n\t  related:: [[Module Name]]\n\t- see [[Another Placeholder]]\n")
        run("graph-link-audit.py", str(self.root), str(self.schema), "--apply-safe-fixes")
        self.assertEqual(t.read_text(), "template:: Reading Notes\n\t  related:: [[Module Name]]\n\t- see [[Another Placeholder]]\n")

    def test_digit_prefixed_key_is_not_a_type_line(self):
        (self.root / "pages").mkdir()
        a = self.root / "pages" / "A.md"
        a.write_text("2type:: x\n\n- body\n")
        run("schema-pass.py", str(self.root), str(self.schema), "--apply")
        self.assertEqual(a.read_text(), "2type:: x\n\n- body\n")

    def test_assets_audit_stops_on_name_clash(self):
        (self.root / "pages" / "assets").mkdir(parents=True)
        (self.root / "assets").mkdir()
        (self.root / "assets" / "a.png").write_text("new")
        (self.root / "pages" / "assets" / "a.png").write_text("old")
        r = run("assets-audit.py", str(self.root))
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual((self.root / "pages" / "assets" / "a.png").read_text(), "old")
        self.assertEqual((self.root / "assets" / "a.png").read_text(), "new")


if __name__ == "__main__":
    unittest.main()
