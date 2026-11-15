import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from citelib import find_citations, parse_bibliography, keys_match, normalise_for_match, quotations  # noqa: E402

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


class Surnames(unittest.TestCase):
    def test_surnames_containing_and_are_not_split(self):
        from citelib import first_surname
        for name in ("Brandt", "Anderson", "Landis", "Sandhu", "Hand"):
            self.assertEqual(first_surname(name), name.casefold())
        self.assertEqual(first_surname("Hughes and Smith"), "hughes")


if __name__ == '__main__':
    unittest.main()
