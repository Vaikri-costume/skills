import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import canonical_terms as ct  # noqa: E402


class Canonical(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.cur = os.path.join(self.d, 'cur.md')
        open(self.cur, 'w').write('# Terms\n\n## Canonical terms\n- dupatta\n- Ghoongat\n- Gita Govinda\n')
        self.other = os.path.join(self.d, 'other.md')
        open(self.other, 'w').write('- Mughal-e-Azam\n')

    def sets(self):
        return [('current', ct.load_terms(self.cur)), ('other:other.md', ct.load_terms(self.other))]

    def test_classes(self):
        s = self.sets()
        self.assertEqual(ct.classify('dupatta', s)['class'], 'matched-correct')
        r = ct.classify('Ghunghat', s)
        self.assertIn(r['class'], ('near-matched', 'unresolved'))
        self.assertEqual(ct.classify('ghoongat', s)['class'], 'matched-incorrect')   # case differs
        self.assertEqual(ct.classify('Mughal e Azam', s)['class'], 'matched-incorrect')  # hyphens ignored
        self.assertEqual(ct.classify('Mughal e Azam', s)['source'], 'other:other.md')
        self.assertEqual(ct.classify('Gita Govind', s)['class'], 'near-matched')
        self.assertEqual(ct.classify('banyan', s)['class'], 'unresolved')

    def test_collect_unions_and_dedupes(self):
        a, b = os.path.join(self.d, 'a.md'), os.path.join(self.d, 'b.md')
        open(a, 'w').write('## Finding 1\nx\n\n## Unrecognised terms\ndupatta\nghoongat\n')
        open(b, 'w').write('## Unrecognised terms\nDupatta\nNone identified\n')
        self.assertEqual(ct.collect([a, b]), ['dupatta', 'ghoongat'])

    def test_add_appends_only_new_terms(self):
        added = ct.add_terms(self.cur, ['dupatta', 'Banyan'])
        self.assertEqual(added, ['Banyan'])
        self.assertIn('- Banyan', open(self.cur).read())

    def test_add_creates_file(self):
        p = os.path.join(self.d, 'new.md')
        ct.add_terms(p, ['x1'])
        self.assertEqual(ct.load_terms(p), ['x1'])


if __name__ == '__main__':
    unittest.main()
