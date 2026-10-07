import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from citelib import find_citations, parse_bibliography, keys_match, normalise_for_match, quotations  # noqa: E402
from citation_audit import audit, _isbn_ok  # noqa: E402
from quote_verify import verify  # noqa: E402

DRAFT = '''# Essay

Jones argues that gardens matter (Jones 2002:34). Many agree (Hughes and Smith 2005, p. 65; Gardner et al. 2007).

Jones (2002) also says "different colleges in the University of London use different referencing systems" (Jones 2002:37).

Jones (2002) repeats the point. Jones (2002) returns again.

Smith claimed "an invented sentence that appears nowhere" (Hughes and Smith 2005).

## References

Bohlman, Philip V. 1988. The study of folk music. Bloomington: Indiana University Press.

Jones, Michael. 2002. Referencing systems at a university. Fake Journal 23 (2): 34-9.

Hughes, Anna, and Smith, Tom. 2005. Referencing is boring. London: Press.

Gardner, Peter. 2007. Perfect systems. Oxford: OUP.
'''


class Lib(unittest.TestCase):
    def test_harvard_variants(self):
        cs = find_citations('(Jones 2002:34) (Jones 2002, p. 34) (Jones 2002; Hughes and Smith 2005) (Gardner et al. 2007)')
        got = [(c['surname'], c['year']) for c in cs]
        self.assertEqual(got, [('jones', '2002'), ('jones', '2002'), ('jones', '2002'), ('hughes', '2005'), ('gardner', '2007')])
        self.assertEqual(cs[0]['page'], '34')

    def test_narrative_and_wikilink_and_citekey(self):
        cs = find_citations('Stubbs (1980:89) argues [[smith2002]] and [@lee1999].')
        self.assertEqual([c['kind'] for c in cs], ['narrative', 'wikilink', 'citekey'])

    def test_year_suffix_matches_bibliography_year(self):
        bib = parse_bibliography('Simons, A. 1980a. Title.\n')
        cite = find_citations('(Simons 1980)')[0]
        self.assertTrue(keys_match(cite, bib[0]))

    def test_normalise_ignores_ellipsis_brackets_and_quote_style(self):
        a = normalise_for_match('“unless spelling errors are [particularly] gross… there are rarely problems”')
        b = normalise_for_match('unless spelling errors are gross there are rarely problems')
        self.assertEqual(a.replace('particularly ', ''), b)

    def test_quotation_followed_by_citation(self):
        q = quotations('He wrote "different colleges use different systems" (Jones 2002:37) here.')
        self.assertEqual(q[0]['cite']['surname'], 'jones')


class Audit(unittest.TestCase):
    def test_audit(self):
        a = audit(DRAFT)
        self.assertEqual(a['bibliography_entries'], 4)
        self.assertEqual([u['citation'][:6] for u in a['unmatched_citations']], [])       # all cited works are listed
        self.assertTrue(any('Bohlman' in e for e in a['uncited_bibliography']))            # Bohlman never cited
        self.assertEqual(a['author_reintroductions'], [{'author': 'jones', 'times': 3}])
        self.assertEqual(a['sources_per_paragraph']['1'], ['jones 2002', 'hughes 2005', 'gardner 2007'][:0] + a['sources_per_paragraph']['1'])

    def test_unmatched_citation(self):
        a = audit('Text (Nobody 1999).\n\n## References\n\nJones, M. 2002. Title.\n')
        self.assertEqual(len(a['unmatched_citations']), 1)

    def test_dominance_and_artefacts(self):
        paras = '\n\n'.join(f'Paragraph {i} says so (Jones 2002).' for i in range(5))
        a = audit(paras + '\n\nSee https://x.org/a?utm_source=chatgpt.com and ISBN 978-0-306-40615-7 and ISBN 978-0-306-40615-9.')
        self.assertTrue(a['dominance'] and a['dominance'][0]['paragraphs'] >= 4)
        kinds = [x['kind'] for x in a['artefacts']]
        self.assertIn('utm-parameter', kinds)
        self.assertEqual(kinds.count('invalid-isbn-checksum'), 1)

    def test_isbn_checksums(self):
        self.assertTrue(_isbn_ok('978-0-306-40615-7'))
        self.assertFalse(_isbn_ok('978-0-306-40615-8'))
        self.assertTrue(_isbn_ok('0-306-40615-2'))


class Quotes(unittest.TestCase):
    SRC = {'jones': 'Intro. Different colleges in the University of London use different referencing systems. More.',
           'hughes': 'Nothing relevant here at all.'}

    def test_statuses(self):
        r = verify(DRAFT, self.SRC)
        by = {x['quote'][:9]: x['status'] for x in r['results']}
        self.assertEqual(by['different'], 'verified')
        self.assertEqual(by['an invent'], 'not-found')

    def test_no_source_supplied(self):
        r = verify(DRAFT, {'jones': self.SRC['jones']})
        self.assertIn('no-source-supplied', r['summary'])


if __name__ == '__main__':
    unittest.main()
