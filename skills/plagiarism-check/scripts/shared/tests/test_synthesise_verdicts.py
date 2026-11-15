import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from synthesise_verdicts import parse  # noqa: E402

CHALLENGER = (
    "## Challenger assessment: Finding 1\n\nReasoning: the sentence is specific.\n\nVerdict: DISPUTED\n\n"
    "## Challenger assessment: Finding 2\n\nReasoning: the context is silent.\n\nVerdict: AMBIGUOUS: is this the writer's habit?\n\n"
    "## Suggested vocabulary register\n\nlandscape, framework, tenure\n"
)


class SynthesiseVerdicts(unittest.TestCase):
    def test_trailing_section_does_not_become_a_reason(self):
        got = parse(CHALLENGER)
        self.assertEqual(got[1], ('DISPUTED', ''))
        self.assertEqual(got[2][0], 'AMBIGUOUS')
        self.assertNotIn('Suggested', got[1][1])
        self.assertNotIn('Suggested', got[2][1])

    def test_reason_on_the_same_line_is_kept(self):
        got = parse("## Challenger assessment: Finding 3\n\nVerdict: DISPUTED: conventional signposting\n")
        self.assertEqual(got[3], ('DISPUTED', 'conventional signposting'))


if __name__ == '__main__':
    unittest.main()
