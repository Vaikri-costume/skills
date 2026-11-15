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


class SingleChallenger(unittest.TestCase):
    def run_main(self, *extra):
        import io
        import tempfile
        from contextlib import redirect_stdout
        from synthesise_verdicts import main
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 'a.md')
            with open(p, 'w') as fh:
                fh.write("## Challenger assessment: Finding 1\n\nVerdict: DISPUTED: conventional\n")
            buf = io.StringIO()
            with redirect_stdout(buf):
                main([p, *extra, '--findings', '1'])
            return buf.getvalue().splitlines()[0]

    def test_partial_flag_gives_partial_labels(self):
        self.assertEqual(self.run_main('--partial'), 'Finding 1: partial-disputed')

    def test_one_file_without_the_flag_keeps_the_plain_word(self):
        self.assertEqual(self.run_main(), 'Finding 1: disputed')


if __name__ == '__main__':
    unittest.main()
