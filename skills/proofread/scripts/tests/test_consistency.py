import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from check_consistency import find_variants  # noqa: E402


class Consistency(unittest.TestCase):
    TEXT = ('# Title with Lantern\n\nThe lantern was hung. A torch too.\n\n'
            'Later the Lantern returned; they said "lanternn" in quotes.\n\n## References\n\nLantern, A. 2001. Lanterns.\n')

    def test_paragraph_numbers_follow_shared_map_and_references_are_excluded(self):
        g = {x['stem']: x for x in find_variants(self.TEXT)['groups']}
        self.assertEqual(g['lantern']['type'], 'capitalisation')
        self.assertEqual(g['lantern']['forms'], {'lantern': [1], 'Lantern': [2]})   # heading and reference list ignored

    def test_curly_quotes_are_skipped(self):
        t = 'Plain text here.\n\nHe said “Colour” aloud, then colour again and colour once more.\n'
        self.assertEqual(find_variants(t)['total_variant_groups'], 0)


class FunctionWordTests(unittest.TestCase):
    def test_sentence_initial_pronouns_are_not_variant_groups(self):
        text = 'She went home. Then she left. Her bag was heavy and her coat wet.\n\nHe asked. Then he waited, and his hat fell.\n'
        self.assertEqual(find_variants(text)['total_variant_groups'], 0)


if __name__ == '__main__':
    unittest.main()
