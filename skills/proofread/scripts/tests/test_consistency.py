import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from check_consistency import find_variants  # noqa: E402


class Consistency(unittest.TestCase):
    TEXT = ('# Title with Bandana\n\nThe bandana was draped. A scarf too.\n\n'
            'Later the Bandana returned; he said "bandanaa" in quotes.\n\n## References\n\nBandana, A. 2001. Bandanas.\n')

    def test_paragraph_numbers_follow_shared_map_and_references_are_excluded(self):
        g = {x['stem']: x for x in find_variants(self.TEXT)['groups']}
        self.assertEqual(g['bandana']['type'], 'capitalisation')
        self.assertEqual(g['bandana']['forms'], {'bandana': [1], 'Bandana': [2]})   # heading and reference list ignored

    def test_curly_quotes_are_skipped(self):
        t = 'Plain text here.\n\nHe said “Colour” aloud, then colour again and colour once more.\n'
        self.assertEqual(find_variants(t)['total_variant_groups'], 0)


if __name__ == '__main__':
    unittest.main()
