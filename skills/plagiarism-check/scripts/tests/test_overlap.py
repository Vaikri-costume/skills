import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from overlap_check import check, source_passages, find_blocks  # noqa: E402

SRC_PAGE = '''title:: Jones 2002
type:: source

- "Different colleges in the University of London use different referencing systems and conventions" (jones2002, p. 37)
- author:: Claude  Different colleges in the University of London use different referencing systems here
- "Spelling errors are rarely a serious barrier to communication in practice" (jones2002, p. 40)
'''


class Overlap(unittest.TestCase):
    def passages(self):
        return [('jones2002', source_passages(SRC_PAGE))]

    def test_only_quoted_source_lines_are_source_material(self):
        p = source_passages(SRC_PAGE)
        self.assertEqual(len(p), 2)
        self.assertTrue(all('author::' not in x for x in p))

    def test_verbatim_run_flagged(self):
        draft = 'In my view different colleges in the University of London use different referencing systems as a rule.'
        r = check(draft, self.passages())
        kinds = [(m['kind'], m['words']) for m in r['matches']]
        self.assertTrue(any(k == 'verbatim-run' and w >= 10 for k, w in kinds), kinds)
        self.assertGreater(r['coverage']['jones2002'], 0.5)

    def test_marked_quotation_is_not_flagged(self):
        draft = 'He notes that "different colleges in the University of London use different referencing systems" (Jones 2002).'
        r = check(draft, self.passages())
        self.assertEqual(r['matches'], [])
        self.assertEqual(r['quoted_matches'], 1)

    def test_blockquote_is_not_flagged(self):
        draft = 'Intro.\n\n> Different colleges in the University of London use different referencing systems and conventions\n'
        self.assertEqual(check(draft, self.passages())['matches'], [])

    def test_three_content_words_alone_do_not_flag(self):
        # three content words in a row ("colleges university london") but only a 3-word run
        draft = 'The colleges university london are discussed elsewhere in other terms.'
        self.assertEqual(check(draft, [('s', ['Many colleges university london partners exist today'])])['matches'], [])

    def test_short_match_needs_three_content_words_and_respects_common_terms(self):
        draft = 'We study spelling errors rarely matter here.'
        src = [('s', ['Spelling errors rarely matter in practice'])]
        r = check(draft, src)
        self.assertEqual([m['kind'] for m in r['matches']], ['short-match'])
        r2 = check(draft, src, common=['spelling errors rarely matter'])
        self.assertEqual(r2['matches'], [])

    def test_find_blocks_extends_to_maximal_run(self):
        d = 'a b c d e f g h'.split()
        s = 'x b c d e f y'.split()
        self.assertEqual(find_blocks(d, s, 4), [(1, 1, 5)])

    def test_reference_list_is_ignored(self):
        draft = 'Short text.\n\n## References\n\nDifferent colleges in the University of London use different referencing systems and conventions.\n'
        self.assertEqual(check(draft, self.passages())['matches'], [])


if __name__ == '__main__':
    unittest.main()
