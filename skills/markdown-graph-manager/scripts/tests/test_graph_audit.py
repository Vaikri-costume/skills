import json
import os
import sys
import tempfile
import unittest
import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import graph_audit as ga  # noqa: E402

ROOT = HERE.parents[1]
SCHEMA = {
    "type_vocab": ["Note", "Essay", "Vocabulary", "Module", "Reading Notes", "Draft"],
    "writer_vocab_plain": ["Alex", "Claude"],
    "status_vocab": ["TODO", "DOING", "DONE"],
    "zotero_only_properties": ["author", "citekey"],
    "required_properties": {"Module": ["type", "related"], "Reading Notes": ["type", "related", "citekey"]},
}
REL = {"verbs": ["extends", "complicates", "contradicts", "applies to a different case", "supplies the primary source for", "responds to", "reframes", "disputes the reading of"]}   # fixed copy: the shipped file is user-edited

PAGES = {
    "Hybridity.md": "type:: Vocabulary\nalias:: hybrid identity\nverified:: 2025-01-01\n\n- Mixed forms.\n",
    "Orientalism.md": "type:: Vocabulary\nwriter:: Alex\n\n- Said's term.\n",
    "Week 1.md": (
        "related:: [[Module X]]\ntype:: Module\n\n- Reading about orientalism and Hybridity.\n"
        "- Connections\n\t- extends [[Hybridity]]: builds on the term\n\t- [[Orientalism]]\n"
        "- see [[Nowhere Page]]\n"
    ),
    "Notes On Bhabha.md": "type:: Reading Notes\nrelated:: [[Week 1]]\nwriter:: Claude\n\n- Summary <module>\n",
    "Broken.md": "type:: Essay\nrelated:: [[Ghost]], Hybridity\ntitle::\n\n# Heading\n- [ ] task\n- ![img](a.png)\nsource:: https://x.org\n",
    "Frontmatter.md": "---\ntype: Note\n---\nbody\n",
    "Templates/Reading Notes Template.md": "type:: Reading Notes\nwriter:: Claude\n",
    "Mention.md": "type:: Note\nrelated:: [[Week 1]]\n\n- Orientalism shapes this; also [[Hybridity]].\n",
    "Dup A.md": "type:: Note\nalias:: Hybridity\n",
}


def make(tmp):
    for name, body in PAGES.items():
        p = Path(tmp) / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)


class T(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        make(self.d.name)
        self.r = ga.run(self.d.name, SCHEMA, REL, ga.ALL_CHECKS, 180, datetime.date(2026, 10, 6))

    def tearDown(self):
        self.d.cleanup()

    def codes(self, page=None):
        return {(f["page"], f["code"]) for f in self.r["findings"] if page in (None, f["page"])}

    def test_seeded_missing_type_caught(self):
        p = Path(self.d.name) / "No Type.md"
        p.write_text("type:: Reading Notes\nwriter:: Alex\n\n- x\n")
        r = ga.run(self.d.name, SCHEMA, REL, ["properties"], 180, datetime.date(2026, 10, 6))
        hit = [f for f in r["findings"] if f["page"] == "No Type" and f["code"] == "required-properties"]
        self.assertTrue(hit)
        self.assertIn("related", hit[0]["message"])
        self.assertEqual(hit[0]["line"], 1)

    def test_missing_type_property(self):
        (Path(self.d.name) / "Untyped.md").write_text("related:: [[Week 1]]\n\n- x\n")
        r = ga.run(self.d.name, SCHEMA, REL, ["properties"], 180, datetime.date(2026, 10, 6))
        hit = [f for f in r["findings"] if f["page"] == "Untyped" and f["code"] == "missing-type"]
        self.assertEqual(len(hit), 1)
        self.assertEqual(hit[0]["line"], 1)

    def test_broken_link_in_property(self):
        self.assertIn(("Broken", "bracketed-missing"), self.codes())

    def test_dead_end(self):
        self.assertIn(("Week 1", "dead-end-link"), self.codes())

    def test_claude_on_notes_flagged(self):
        self.assertIn(("Notes On Bhabha", "claude-on-notes"), self.codes())

    def test_template_writer(self):
        self.assertIn(("Reading Notes Template", "template-writer"), self.codes())

    def test_format_checks(self):
        c = self.codes("Broken")
        for code in ("md-heading", "checkbox", "image-embed", "url-property", "blank-title"):
            self.assertIn(("Broken", code), c)
        self.assertIn(("Frontmatter", "yaml-frontmatter"), self.codes())

    def test_plain_existing(self):
        self.assertIn(("Broken", "plain-existing"), self.codes())

    def test_collision(self):
        self.assertTrue(any(f["code"] == "name-collision" for f in self.r["findings"]))

    def test_unlinked_mention(self):
        self.assertFalse(any(f["code"] == "unlinked-mention" and f["page"] == "Week 1" for f in self.r["findings"]))  # already linked
        self.assertTrue(any(f["code"] == "unlinked-mention" and f["page"] == "Mention" and "orientalism" in f["message"].lower() for f in self.r["findings"]))

    def test_link_shown_only_in_code_does_not_count_as_linked(self):
        with tempfile.TemporaryDirectory() as d:
            for name, body in {"Target Page.md": "type:: Note\n", "Example.md": "type:: Note\n\n- Target Page appears here, and `[[Target Page]]` is only an example.\n"}.items():
                (Path(d) / name).write_text(body)
            r = ga.run(d, SCHEMA, REL, ga.ALL_CHECKS, 180, datetime.date(2026, 10, 6))
        self.assertTrue(any(f["code"] == "unlinked-mention" and f["page"] == "Example" for f in r["findings"]))

    def test_exclude_names_tolerate_a_space_after_the_comma(self):
        import subprocess
        out = subprocess.run([sys.executable, str(HERE.parent / "graph_audit.py"), self.d.name, "--exclude", "Broken, Mention", "--json"], capture_output=True, text=True).stdout
        pages = {f["page"] for f in json.loads(out)["findings"]}
        self.assertNotIn("Broken", pages)
        self.assertNotIn("Mention", pages)

    def test_relation_reason_must_follow_the_link(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "Said.md").write_text("type:: Note\n")
            (Path(d) / "Week.md").write_text("type:: Module\nrelated:: [[Said]]\n\n- Connections\n\t- extends [[Said]]\n\t- extends [[Said: Orientalism]]\n\t- extends [[Said]]: a reason\n")
            r = ga.run(d, SCHEMA, REL, ["relations"], 180, datetime.date(2026, 10, 6))
        self.assertEqual(sorted(f["line"] for f in r["findings"] if f["code"] == "relation-no-reason"), [5, 6])

    def test_writer_with_a_comma_inside_brackets_is_one_writer(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "P.md").write_text("type:: Note\nwriter:: [[Said, Edward]]\n\n- x\n")
            r = ga.run(d, SCHEMA, REL, ["properties"], 180, datetime.date(2026, 10, 6))
        self.assertFalse(any(f["code"] == "writer-vocab" for f in r["findings"]))

    def test_template_placeholder_link_and_code_span_example_are_not_findings(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "Templates").mkdir()
            (Path(d) / "Templates" / "Reading Notes Template.md").write_text("type:: Reading Notes\nrelated:: [[Module Name]]\n")
            (Path(d) / "Reference.md").write_text("type:: Note\n\n- | Image | `![caption](path or URL)` | Local or remote |\n- the variable `{{title}}` is filled in by the app\n")
            r = ga.run(d, SCHEMA, REL, ga.ALL_CHECKS, 180, datetime.date(2026, 10, 6))
        codes = {f["code"] for f in r["findings"]}
        self.assertNotIn("bracketed-missing", codes)
        self.assertNotIn("image-embed", codes)
        self.assertNotIn("placeholder", codes)

    def test_relations(self):
        rel = [f for f in self.r["findings"] if f["page"] == "Week 1" and f["code"].startswith("relation")]
        self.assertEqual(len(rel), 1)
        self.assertEqual(rel[0]["code"], "relation-missing")
        self.assertEqual(rel[0]["line"], 7)

    def test_placeholder(self):
        self.assertIn(("Notes On Bhabha", "placeholder"), self.codes())

    def test_stale(self):
        self.assertIn(("Hybridity", "stale"), self.codes())

    def test_orphans_and_hubs(self):
        self.assertIn(("Frontmatter", "orphan"), self.codes())
        self.assertNotIn(("Hybridity", "orphan"), self.codes())
        self.assertTrue(self.r["hubs"])

    def test_read_only(self):
        before = {p: (p.stat().st_mtime_ns, p.read_bytes()) for p in Path(self.d.name).rglob("*.md")}
        ga.run(self.d.name, SCHEMA, REL, ga.ALL_CHECKS, 180, datetime.date(2026, 10, 6))
        ga.main([self.d.name, "--json"])
        after = {p: (p.stat().st_mtime_ns, p.read_bytes()) for p in Path(self.d.name).rglob("*.md")}
        self.assertEqual(before, after)
        self.assertEqual(set(before), set(after))

    def test_cli_exit_codes(self):
        self.assertEqual(ga.main([self.d.name, "--checks", "stale", "--today", "2026-10-06"]), 1)
        self.assertEqual(ga.main(["/nonexistent"]), 2)
        self.assertEqual(ga.main([self.d.name, "--checks", "bogus"]), 2)
        empty = tempfile.mkdtemp()
        (Path(empty) / "A.md").write_text("type:: Note\n\n- x [[A]]\n")
        self.assertEqual(ga.main([empty, "--checks", "format"]), 0)

    def test_app_and_hidden_folders_skipped(self):
        for sub in (".obsidian/plugins", "copilot/prompts", "logseq"):
            d = Path(self.d.name) / sub
            d.mkdir(parents=True)
            (d / "Clip.md").write_text("- <page title> and <video url>\n")
        r = ga.run(self.d.name, SCHEMA, REL, ["placeholders"], 180, datetime.date(2026, 10, 6))
        self.assertNotIn("Clip", {f["page"] for f in r["findings"]})

    def test_nested_connections_heading(self):
        p = Path(self.d.name) / "Nested.md"
        p.write_text("type:: Reading Notes\nrelated:: [[Week 1]]\ncitekey:: x\n\n- Annotations\n\t- Connections\n\t\t- [[Hybridity]]\n")
        r = ga.run(self.d.name, SCHEMA, REL, ["relations"], 180, datetime.date(2026, 10, 6), only=["nested"])
        self.assertEqual([f["code"] for f in r["findings"]], ["relation-missing"])

    def test_only_pages_filter(self):
        r = ga.run(self.d.name, SCHEMA, REL, ga.ALL_CHECKS, 180, datetime.date(2026, 10, 6), only=["week 1"])
        self.assertTrue(r["findings"])
        self.assertTrue(all(f["page"] == "Week 1" for f in r["findings"]))

    def test_excluded_page_is_still_a_link_target(self):
        (Path(self.d.name) / "Draft Page.md").write_text("type:: Draft\n\n- x\n")
        (Path(self.d.name) / "Linker.md").write_text("type:: Note\nrelated:: [[Draft Page]]\n\n- see [[Draft Page]]\n")
        r = ga.run(self.d.name, SCHEMA, REL, ["links"], 180, datetime.date(2026, 10, 6), exclude=["draft page"])
        self.assertFalse([f for f in r["findings"] if "Draft Page" in f["message"]])
        self.assertNotIn("Draft Page", {f["page"] for f in r["findings"]})

    def test_logseq_bullet_fence_is_skipped(self):
        (Path(self.d.name) / "Fenced.md").write_text("type:: Note\n\n- ```python\n  # not a heading\n  <name>\n  ```\n")
        r = ga.run(self.d.name, SCHEMA, REL, ["format", "placeholders"], 180, datetime.date(2026, 10, 6), only=["fenced"])
        self.assertEqual(r["findings"], [])

    def test_writer_vocab_is_judged_per_part(self):
        (Path(self.d.name) / "Two Writers.md").write_text("type:: Note\nwriter:: Alex, [[Said]]\n\n- x\n")
        r = ga.run(self.d.name, SCHEMA, REL, ["properties"], 180, datetime.date(2026, 10, 6), only=["two writers"])
        self.assertEqual([f for f in r["findings"] if f["code"] == "writer-vocab"], [])

    def test_heading_attachment_url_and_namespaced_links_are_not_dead_ends(self):
        (Path(self.d.name) / "assets").mkdir(exist_ok=True)
        (Path(self.d.name) / "Links.md").write_text("type:: Note\n\n- [[#Intro]] [[photo.png]] [[http://x.org]] [[A/B]]\n")
        (Path(self.d.name) / "photo.png").write_text("x")
        r = ga.run(self.d.name, SCHEMA, REL, ["links"], 180, datetime.date(2026, 10, 6), only=["links"])
        self.assertEqual([f for f in r["findings"] if f["code"] in ("dead-end-link", "bracketed-missing")], [])

    def test_links_inside_code_are_ignored(self):
        (Path(self.d.name) / "Code.md").write_text("type:: Note\n\n- ```\n  [[Nowhere At All]]\n  ```\n- inline `[[Also Nowhere]]` here\n")
        r = ga.run(self.d.name, SCHEMA, REL, ["links"], 180, datetime.date(2026, 10, 6))
        self.assertFalse([f for f in r["findings"] if "Nowhere At All" in f["message"] or "Also Nowhere" in f["message"]])

    def test_shipped_relation_vocabulary_is_a_verb_list(self):
        shipped = json.loads((ROOT / "assets/relation-vocabulary.json").read_text())
        self.assertTrue(shipped["verbs"] and all(isinstance(v, str) for v in shipped["verbs"]))

    def test_html_tag_exempts_only_the_angle_bracket_pattern(self):
        (Path(self.d.name) / "Html.md").write_text("type:: Note\n\n- TBD <br> and <title here> and <b>\n")
        r = ga.run(self.d.name, SCHEMA, REL, ["placeholders"], 180, datetime.date(2026, 10, 6), only=["html"])
        self.assertEqual([f["code"] for f in r["findings"]], ["placeholder"])
        self.assertIn("TBD", r["findings"][0]["message"])

    def test_relation_verbs_match_whatever_their_case(self):
        rel = {"verbs": ["Extends"]}
        (Path(self.d.name) / "Rel.md").write_text("type:: Note\n\n- Connections\n\t- extends [[Hybridity]]: because\n")
        r = ga.run(self.d.name, SCHEMA, rel, ["relations"], 180, datetime.date(2026, 10, 6), only=["rel"])
        self.assertEqual(r["findings"], [])

    def test_hub_counts_each_link_once(self):
        d = Path(tempfile.mkdtemp())
        (d / "Hub.md").write_text("type:: Note\n\n- x\n")
        (d / "A.md").write_text("type:: Note\n\n- [[Hub]]\n")
        (d / "B.md").write_text("type:: Note\n\n- [[Hub]]\n")
        r = ga.run(str(d), SCHEMA, REL, ["links"], 180, datetime.date(2026, 10, 6))
        self.assertIn(("Hub", 2), [tuple(h) for h in r["hubs"]])

    def test_alias_with_a_comma_inside_brackets_is_one_alias(self):
        (Path(self.d.name) / "Said.md").write_text("type:: Note\nalias:: [[Said, Edward]]\n\n- x\n")
        pages = ga.load_pages(self.d.name, set())
        said = [p for p in pages if p.name == "Said"][0]
        self.assertEqual(said.aliases, ["Said, Edward"])

    def test_two_mentions_with_parentheses_are_both_kept(self):
        d = Path(tempfile.mkdtemp())
        (d / "Empire (Roman).md").write_text("type:: Note\n\n- x\n")
        (d / "Empire (British).md").write_text("type:: Note\n\n- x\n")
        (d / "Essay.md").write_text("type:: Note\n\n- Empire (Roman) and Empire (British) compared\n")
        r = ga.run(str(d), SCHEMA, REL, ["mentions"], 180, datetime.date(2026, 10, 6))
        self.assertEqual(len([f for f in r["findings"] if f["page"] == "Essay"]), 2)

    def test_blank_title_on_a_template_is_not_flagged(self):
        d = Path(tempfile.mkdtemp())
        (d / "Templates").mkdir()
        (d / "Templates" / "T Template.md").write_text("title::\n\n- x\n")
        (d / "Plain.md").write_text("type:: Note\ntitle::\n\n- x\n")
        r = ga.run(str(d), SCHEMA, REL, ["properties"], 180, datetime.date(2026, 10, 6))
        pages = {f["page"] for f in r["findings"] if f["code"] == "blank-title"}
        self.assertEqual(pages, {"Plain"})

    def test_flat_vault_does_not_read_a_sibling_assets_folder(self):
        parent = Path(tempfile.mkdtemp())
        (parent / "assets").mkdir()
        (parent / "assets" / "outside.png").write_text("x")
        vault = parent / "vault"
        vault.mkdir()
        self.assertNotIn("outside.png", ga.attachment_names(str(vault)))

    def test_default_run_leaves_out_stale(self):
        self.assertNotIn("stale", ga.DEFAULT_CHECKS)
        self.assertIn("stale", ga.ALL_CHECKS)

    def test_templates_folder_above_pages_dir_is_not_a_template(self):
        pages = Path(tempfile.mkdtemp()) / "Templates" / "graph" / "pages"
        pages.mkdir(parents=True)
        (pages / "Plain.md").write_text("related:: [[Week 1]]\n\n- x\n")
        r = ga.run(str(pages), SCHEMA, REL, ["properties"], 180, datetime.date(2026, 10, 6))
        self.assertIn(("Plain", "missing-type"), {(f["page"], f["code"]) for f in r["findings"]})


if __name__ == "__main__":
    unittest.main()
