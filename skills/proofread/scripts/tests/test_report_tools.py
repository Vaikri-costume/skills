import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.normpath(os.path.join(HERE, '..'))
sys.path.insert(0, SCRIPTS)
sys.path.insert(0, os.path.join(SCRIPTS, 'shared'))

import word_count as wc  # noqa: E402
import annotate_copy as ac  # noqa: E402
import change_table as ct  # noqa: E402

DRAFT = ('# Title\n\nThe harbour was very quiet. It was really a calm morning.\n\n'
         'She said "it was very, very cold" and left.\n\n## References\n\nSmith, A. 2001. Tides. Press.\n')

FINDINGS = '''## Finding 1
Location: paragraph 1, sentence 1 of the paragraph, The harbour was
Current text: "The harbour was very quiet"
Proposed fix: "The harbor was quiet"
Check: 3
Severity: Low
Reason: American spelling

## Finding 2
Location: paragraph 2, sentence 1 of the paragraph, She said
Current text: "left"
Pattern: tense shift
Concern: reader may lose the thread
Check: 5
Severity: Low

## Finding 3
Location: paragraph 1, sentence 2 of the paragraph, It was
Current text: "really a calm"
Proposed fix: "a calm"
Check: 1
Severity: Low
'''


class WordCountTests(unittest.TestCase):
    def test_reference_list_excluded_and_limit(self):
        r = wc.analyse(DRAFT, limit=10)
        self.assertEqual(r['words'], 20)
        self.assertGreater(r['words_with_references'], r['words'])
        self.assertEqual(r['over_by'], 10)

    def test_after_all_candidates(self):
        r = wc.analyse(DRAFT, limit=19)
        self.assertEqual(r['words_after_all_candidates'], 18)
        self.assertTrue(r['meets_limit_if_all_applied'])
        self.assertIsNone(wc.analyse(DRAFT)['meets_limit_if_all_applied'])

    def test_no_limit_gives_null(self):
        r = wc.analyse(DRAFT)
        self.assertIsNone(r['limit'])
        self.assertIsNone(r['over_by'])

    def test_candidates_skip_quotations(self):
        r = wc.analyse(DRAFT)
        words = [c['delete'].lower() for c in r['cut_candidates']]
        self.assertEqual(words, ['very', 'really'])      # the two "very" inside the quotation are not listed
        self.assertEqual(r['candidate_words_saved'], 2)

    def test_cli_error_on_missing_file(self):
        p = subprocess.run([sys.executable, os.path.join(SCRIPTS, 'word_count.py'), '/no/such/file'],
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 1)
        self.assertIn('error', json.loads(p.stdout))


class AnnotateCopyTests(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.draft = os.path.join(self.d, 'draft.md')
        self.findings = os.path.join(self.d, 'f.md')
        with open(self.draft, 'w') as fh:
            fh.write(DRAFT)
        with open(self.findings, 'w') as fh:
            fh.write(FINDINGS)

    def run_tool(self, out):
        return subprocess.run([sys.executable, os.path.join(SCRIPTS, 'annotate_copy.py'),
                               self.draft, self.findings, '--out', out], capture_output=True, text=True)

    def test_copy_has_comments_and_draft_untouched(self):
        out = os.path.join(self.d, 'copy.md')
        p = self.run_tool(out)
        self.assertEqual(p.returncode, 0, p.stdout)
        self.assertEqual(json.loads(p.stdout)['placed'], 3)
        with open(self.draft) as fh:
            self.assertEqual(fh.read(), DRAFT)
        with open(out) as fh:
            copy = fh.read()
        self.assertIn('<!-- proofread: Check 3', copy)
        self.assertEqual(ac.strip_comments(copy).rstrip('\n'), DRAFT.rstrip('\n'))

    def test_refuses_draft_path_and_existing_file(self):
        p = self.run_tool(self.draft)
        self.assertEqual(p.returncode, 1)
        self.assertIn('draft itself', p.stdout)
        link = os.path.join(self.d, 'link.md')
        os.symlink(self.draft, link)
        self.assertEqual(self.run_tool(link).returncode, 1)
        out = os.path.join(self.d, 'copy.md')
        self.assertEqual(self.run_tool(out).returncode, 0)
        again = self.run_tool(out)
        self.assertEqual(again.returncode, 1)
        self.assertIn('already exists', again.stdout)

    def test_unplaced_finding_goes_to_end(self):
        with open(self.findings, 'w') as fh:
            fh.write('## Finding 1\nCurrent text: "nowhere in the draft"\nProposed fix: "x"\nCheck: 2\n')
        out = os.path.join(self.d, 'copy.md')
        p = self.run_tool(out)
        self.assertEqual(p.returncode, 0, p.stdout)
        self.assertEqual(json.loads(p.stdout)['unplaced'], 1)


class ChangeTableTests(unittest.TestCase):
    def test_split_between_changes_and_flagged(self):
        findings = ct.parse_findings(FINDINGS)
        text = ct.build(findings, {1: 'confirmed', 2: 'ambiguous', 3: 'split'})
        change, flagged = text.split('## Flagged, not changed')
        self.assertIn('The harbor was quiet', change)
        self.assertIn('American spelling', change)
        self.assertNotIn('a calm', change)               # split finding is not a proposed change
        self.assertIn('really a calm', flagged)
        self.assertIn('tense shift', flagged)

    def test_single_challenger_plain_labels(self):
        text = ct.build(ct.parse_findings(FINDINGS), {1: 'upheld', 2: 'ambiguous', 3: 'disputed'})
        change, flagged = text.split('## Flagged, not changed')
        self.assertIn('The harbor was quiet', change)
        self.assertNotIn('a calm', change)
        self.assertIn('disputed by the single challenger', flagged)

    def test_without_verdicts_all_fixes_are_changes(self):
        text = ct.build(ct.parse_findings(FINDINGS), {})
        self.assertIn('really a calm', text.split('## Flagged, not changed')[0])

    def test_register_audit_counts_tagged_types(self):
        f = ct.parse_findings(
            '## Finding 1\nLocation: paragraph 2\nCurrent text: "a lot of"\nPattern: [vague-quantifier] x\nCheck: 5\n\n'
            '## Finding 2\nLocation: paragraph 4\nCurrent text: "it\'s"\nPattern: [contraction] x\nCheck: 5\n\n'
            '## Finding 3\nLocation: paragraph 2\nCurrent text: "kids"\nPattern: [vague-quantifier] y\nCheck: 5\n')
        text = ct.build(f, {})
        self.assertIn('| vague-quantifier | 2 | 2 |', text)
        self.assertIn('| contraction | 1 | 4 |', text)
        self.assertNotIn('## Register audit', ct.build(ct.parse_findings(FINDINGS.replace('Check: 5', 'Check: 4')), {}))

    def test_pipe_in_text_is_escaped(self):
        f = ct.parse_findings('## Finding 1\nLocation: paragraph 1\nCurrent text: "a|b"\nProposed fix: "ab"\nCheck: 2\n')
        self.assertIn('a\\|b', ct.build(f, {}))


if __name__ == '__main__':
    unittest.main()


class OverlapAndBulletTests(unittest.TestCase):
    def test_overlap_is_marked(self):
        f = ct.parse_findings(
            '## Finding 1\nLocation: paragraph 1\nCurrent text: "recieve"\nProposed fix: "receive"\nCheck: 2\n\n'
            '## Finding 2\nLocation: paragraph 1\nCurrent text: "they recieve it"\nProposed fix: "they received it"\nCheck: 1\n')
        t = ct.build(f, {})
        self.assertIn('overlaps finding 1', t)
        self.assertNotIn('overlaps finding 2', t)

    def test_bullet_comment_follows_its_bullet(self):
        draft = '- First bullet has a typo recieve here.\n- Second bullet is fine.\n- Third.\n'
        f = ac.parse_findings('## Finding 1\nCurrent text: "recieve"\nProposed fix: "receive"\nCheck: 2\n')
        text, placed, unplaced = ac.build_copy(draft, f)
        lines = text.split('\n')
        self.assertTrue(lines[1].startswith('<!-- proofread:'))
        self.assertEqual(lines[2], '- Second bullet is fine.')
        self.assertEqual(ac.strip_comments(text), draft)


class StyleCheckTests(unittest.TestCase):
    PROFILE = '# Style\n\n## Quick Reference\n\n- prefer: per cent | avoid: %, percent\n- note only\n\n## Detail\n\n- prefer: x | avoid: harbour\n'

    def test_reads_only_quick_reference(self):
        import style_check as sc
        self.assertEqual(sc.read_conventions(self.PROFILE), [('per cent', ['%', 'percent'])])

    def test_finds_departures_outside_quotes_and_references(self):
        import style_check as sc
        text = 'Rates rose 5% and then 7 percent.\n\nHe wrote "9 percent" once and 3 per cent.\n\n## References\n\nA. 2000. 50% of it.\n'
        f = sc.find_departures(text, sc.read_conventions(self.PROFILE))
        self.assertEqual([(x['paragraph'], x['found']) for x in f], [(1, '%'), (1, 'percent')])
