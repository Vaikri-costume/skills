"""Tests for the shared writing-skill scripts. Run: python3 -m unittest discover -s ${CLAUDE_SKILL_DIR}/scripts/shared/tests"""
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from synthesise_pairs import synthesise  # noqa: E402
from synthesise_verdicts import parse, label  # noqa: E402
from correct_finding_locations import correct_agent_output  # noqa: E402
from extract_paragraphs import extract_paragraphs  # noqa: E402

A = '''## Finding 1
Location: paragraph 2, sentence 1, The garden
Current text: "organise the gardens"
Proposed fix: "organise the gardens"
Check: 3
Severity: High

## Finding 2
Location: paragraph 3, sentence 1, Walls
Current text: "teh walls"
Proposed fix: "the walls"
Check: 2
Severity: High
'''
B = '''## Finding 1
Location: paragraph 2
Current text: "the gardens"
Proposed fix: "x"
Check: 3
Severity: High

## [QUOTE-UNMATCHED] Finding 2
Location: paragraph 9
Current text: "something invented"
Check: 2
Severity: Low
'''


class PairSynthesis(unittest.TestCase):
    def test_match_by_check_and_substring(self):
        m = synthesise(A, B, ['Check'], ['Current text'])
        self.assertEqual(m[0][1], 'HIGH')            # substring match, same check
        self.assertEqual(m[0][2], 'description differs between agents')
        self.assertEqual(m[1][1], 'UNVERIFIED')      # only A has "teh walls"
        self.assertEqual(m[2][1], 'UNVERIFIED')      # B-only, and quote unmatched
        self.assertEqual(len(m), 3)

    def test_different_check_does_not_match(self):
        b = B.replace('Check: 3', 'Check: 1')
        m = synthesise(A, b, ['Check'], ['Current text'])
        self.assertEqual(m[0][1], 'UNVERIFIED')

    def test_unmatched_marker_survives_rendering(self):
        from findings_lib import render
        m = synthesise(A, B, ['Check'], ['Current text'])
        self.assertTrue(render(m[2][0], 3, m[2][1]).startswith('## [QUOTE-UNMATCHED] Finding 3'))

    def test_single_agent_is_all_unverified(self):
        m = synthesise(A, '', ['Check'], ['Current text'], single=True)
        self.assertTrue(all(c == 'UNVERIFIED' for _, c, _ in m))

    def test_unmatched_marker_forces_unverified_even_if_matched(self):
        a = A.replace('"teh walls"', '"something invented"')
        m = synthesise(a, B, ['Check'], ['Current text'])
        self.assertEqual([c for _, c, _ in m][1], 'UNVERIFIED')


class VerdictSynthesis(unittest.TestCase):
    def test_labels(self):
        self.assertEqual(label('UPHELD', 'UPHELD'), 'confirmed')
        self.assertEqual(label('DISPUTED', 'DISPUTED'), 'confirmed-disputed')
        self.assertEqual(label('UPHELD', 'DISPUTED'), 'split')
        self.assertEqual(label('AMBIGUOUS', 'UPHELD'), 'ambiguous')
        self.assertEqual(label('UPHELD', None), 'partial-upheld')
        self.assertEqual(label(None, 'DISPUTED'), 'partial-disputed')
        self.assertEqual(label('AMBIGUOUS', None), 'partial-ambiguous')
        self.assertEqual(label('NONE', None), 'partial-unaddressed')
        self.assertEqual(label(None, None), 'unverified-challenger')
        self.assertEqual(label('UPHELD', 'NONE'), 'partial-upheld')

    def test_parse_uses_last_verdict_line(self):
        t = ('## Challenger assessment: Finding 1\nVerdict: UPHELD would be tempting.\n'
             'Reasoning here.\nVerdict: DISPUTED: it is inside a quotation\n')
        self.assertEqual(parse(t)[1], ('DISPUTED', 'it is inside a quotation'))

    def test_parse_ambiguous_question(self):
        t = '## Challenger assessment: Finding 2\nx\nVerdict: AMBIGUOUS: Is this intentional?\n'
        self.assertEqual(parse(t)[2], ('AMBIGUOUS', 'Is this intentional?'))


class ParagraphNumbering(unittest.TestCase):
    DRAFT = '# Title\n\nproperty:: x\n\nFirst paragraph here.\n\nSecond paragraph here.\n'

    def test_location_matches_paragraph_map(self):
        pm = extract_paragraphs(self.DRAFT)
        self.assertEqual(pm['total_paragraphs'], 2)
        agent = '## Finding 1\nLocation: paragraph 4, sentence 1, Second\nCurrent text: "Second paragraph here."\n'
        out, warns = correct_agent_output(self.DRAFT, agent)
        self.assertIn('paragraph 2', out)   # not 4: headings and properties are not paragraphs

    def test_flag_unmatched(self):
        agent = '## Finding 1\nLocation: paragraph 1, sentence 1, X\nCurrent text: "not in the draft at all"\n'
        out, warns = correct_agent_output(self.DRAFT, agent, flag_unmatched=True)
        self.assertTrue(out.startswith('## [QUOTE-UNMATCHED] Finding 1'))
        self.assertTrue(any(w.startswith('unmatched-quote') for w in warns))


if __name__ == '__main__':
    unittest.main()
