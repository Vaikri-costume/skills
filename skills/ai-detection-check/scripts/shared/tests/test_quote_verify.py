import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from quote_verify import verify  # noqa: E402

DRAFT = ('The author writes that "the channel silted faster than any survey predicted" in the early years. '
         'Later, "the council quietly abandoned the scheme in 2015" according to the same account (Mortimer 2012).\n\n'
         '## References\n\nMortimer, D. (2012) The river station. Leeds: Calder Books.\n')
SOURCE = {'Mortimer': 'Within a season it was clear that the channel silted faster than any survey predicted.'}


class QuoteVerify(unittest.TestCase):
    def test_uncited_quote_found_with_fallback(self):
        r = verify(DRAFT, SOURCE, True)['results']
        self.assertEqual(r[0]['status'], 'verified-elsewhere')

    def test_uncited_quote_not_in_any_source_is_reported(self):
        r = verify(DRAFT, {'Mortimer': 'Nothing relevant here at all, only a different sentence of text.'}, True)['results']
        self.assertEqual(r[0]['status'], 'not-found-in-supplied-sources')

    def test_without_fallback_an_uncited_quote_stays_uncited(self):
        r = verify(DRAFT, SOURCE, False)['results']
        self.assertEqual(r[0]['status'], 'uncited')


if __name__ == '__main__':
    unittest.main()
