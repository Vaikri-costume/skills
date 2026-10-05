import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from check_consistency import find_variants  # noqa: E402


class Consistency(unittest.TestCase):
    TEXT = ('# Title with Dupatta\n\nThe dupatta was draped. A scarf too.\n\n'
            'Later the Dupatta returned; he said "dupattaa" in quotes.\n\n## References\n\nDupatta, A. 2001. Dupattas.\n')

    def test_paragraph_numbers_follow_shared_map_and_references_are_excluded(self):
        g = {x['stem']: x for x in find_variants(self.TEXT)['groups']}
        self.assertEqual(g['dupatta']['type'], 'capitalisation')
        self.assertEqual(g['dupatta']['forms'], {'dupatta': [1], 'Dupatta': [2]})   # heading and reference list ignored

    def test_curly_quotes_are_skipped(self):
        t = 'Plain text here.\n\nHe said “Colour” aloud, then colour again and colour once more.\n'
        self.assertEqual(find_variants(t)['total_variant_groups'], 0)


if __name__ == '__main__':
    unittest.main()
