import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from check_british_spelling import find_british_violations, ISE_EXCEPTIONS  # noqa: E402


def flagged(text, **kw):
    return {f['american_form'].casefold(): f['british_form'].casefold() for f in find_british_violations(text, **kw)['findings']}


class StrictIse(unittest.TestCase):
    def test_ize_family_is_always_an_error(self):
        got = flagged("We organize, realize and specialize; organization and organizing follow. Organizer too.")
        self.assertEqual(got['organize'], 'organise')
        self.assertEqual(got['organization'], 'organisation')
        self.assertEqual(got['organizing'], 'organising')
        self.assertEqual(got['organizer'], 'organiser')
        self.assertEqual(got['realize'], 'realise')

    def test_greek_s_stem_verbs_are_still_ize_errors(self):
        got = flagged("They synthesize, emphasize and hypothesize.")
        self.assertEqual(got, {'synthesize': 'synthesise', 'emphasize': 'emphasise', 'hypothesize': 'hypothesise'})

    def test_yze_family(self):
        got = flagged("Analyze and paralyze; analyzing, catalyzed.")
        self.assertEqual(got['analyze'], 'analyse')
        self.assertEqual(got['paralyze'], 'paralyse')
        self.assertEqual(got['analyzing'], 'analysing')
        self.assertEqual(got['catalyzed'], 'catalysed')

    def test_words_that_are_ize_in_every_system_are_allowed(self):
        text = ("The size and prize; he seized it; it capsized; maize and baize; a sizable crowd; "
                "downsized, resizing, oversized, seizing the prize.")
        self.assertEqual(flagged(text), {})

    def test_exception_list_contents(self):
        for w in ('size', 'sized', 'sizing', 'seize', 'seized', 'seizing', 'prize', 'prized', 'capsize', 'capsized', 'maize'):
            self.assertIn(w, ISE_EXCEPTIONS)
        for w in ('synthesize', 'emphasize', 'organize'):
            self.assertNotIn(w, ISE_EXCEPTIONS)

    def test_ise_spellings_are_never_flagged(self):
        self.assertEqual(flagged("organise realise advise exercise comprise surprise supervise analyse recognised organisation"), {})

    def test_no_false_hits_on_other_iz_words(self):
        self.assertEqual(flagged("A pizza, a lizard, a citizen and a bizarre quiz at the Ritz."), {})

    def test_case_is_preserved(self):
        got = flagged("Organize. ORGANIZE.")
        self.assertEqual(got['organize'], 'organise')  # last wins in dict; check both below
        fs = find_british_violations("Organize. ORGANIZE.")['findings']
        self.assertEqual([f['british_form'] for f in fs], ['Organise', 'ORGANISE'])

    def test_allow_list_for_proper_names(self):
        self.assertEqual(flagged("The Organization of African Unity", allow=['organization']), {})


class Exclusions(unittest.TestCase):
    def test_quotes_urls_wikilinks_and_references_are_skipped(self):
        text = ('She wrote that "we organize and analyze the color" in her book. '
                'See https://example.org/organize-color and [[Organization Studies]].\n\n'
                '## References\n\nSmith, J. 2001. Cataloging and Organizing.\n')
        self.assertEqual(flagged(text), {})
        curly = 'He said “the color of organizing” and nothing else.'
        self.assertEqual(flagged(curly), {})

    def test_paragraph_numbers_match_the_shared_map(self):
        text = '# Title\n\nThe first.\n\nWe organize here.\n'
        f = find_british_violations(text)['findings'][0]
        self.assertEqual(f['paragraph'], 2)
        self.assertEqual(f['sentence'], 1)
        self.assertTrue(f['sentence_opening_words'].startswith('We organize'))


class OtherBritishSpellings(unittest.TestCase):
    def test_word_list(self):
        got = flagged("The color of the favorite center was traveled to; a defense, a catalog, the labeling, gray aluminum.")
        self.assertEqual(got['color'], 'colour')
        self.assertEqual(got['favorite'], 'favourite')
        self.assertEqual(got['center'], 'centre')
        self.assertEqual(got['traveled'], 'travelled')
        self.assertEqual(got['defense'], 'defence')
        self.assertEqual(got['catalog'], 'catalogue')
        self.assertEqual(got['labeling'], 'labelling')
        self.assertEqual(got['gray'], 'grey')
        self.assertEqual(got['aluminum'], 'aluminium')

    def test_same_in_both_systems_not_flagged(self):
        self.assertEqual(flagged("humoral immunity, a humorist, rigorous, vigorous, enrolled, aesthetic"), {})

    def test_ambiguous_words_carry_a_verify_note(self):
        f = find_british_violations("She runs the program and will practice daily.")['findings']
        self.assertTrue(all(x['note'].startswith('verify:') for x in f))
        self.assertEqual({x['american_form'] for x in f}, {'program', 'practice'})


if __name__ == '__main__':
    unittest.main()
