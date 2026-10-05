import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from compute_metrics import compute_metrics, compare_baseline, mattr, features, _split_sentences  # noqa: E402
from find_ai_patterns import find_patterns  # noqa: E402

HUMAN = ("The dupatta appears in twelve of the fifteen scenes. I counted them twice. "
         "That surprised me, because the film barely mentions it in dialogue; yet the camera keeps returning to it. "
         "Short. A much longer sentence follows, which wanders through the argument and refuses, for a while, to arrive anywhere definite. ") * 8
LLM = ("This analysis underscores the importance of the dupatta, highlighting its role in the narrative, "
       "showcasing the interplay of tradition and modernity. The implementation of reforms was initiated by the state. "
       "It is worth noting that the continuation of this tradition stands as a testament to resilience. ") * 6


class Metrics(unittest.TestCase):
    def test_no_ratings_anywhere(self):
        m = compute_metrics(HUMAN)
        self.assertNotIn('RED', str(m))
        self.assertNotIn('YELLOW', str(m))
        self.assertNotIn('cv_rating', m)
        self.assertIn('cv', m['sentence_length'])

    def test_guard_on_short_text(self):
        m = compute_metrics("A short text. Only two sentences here.")
        self.assertFalse(m['guard']['sufficient'])
        self.assertIsNone(m['mattr_100'])

    def test_features_distinguish_llm_style(self):
        h, l = features(HUMAN), features(LLM)
        self.assertGreater(l['present_participle_clauses'], h['present_participle_clauses'])
        self.assertGreater(l['nominalisations'], h['nominalisations'])
        self.assertGreater(l['passives'], h['passives'])

    def test_participle_proxy_ignores_prepositions(self):
        self.assertEqual(features('We met, including Anna and Tom, at noon today.')['present_participle_clauses'], 0)

    def test_baseline_requires_enough_words(self):
        c = compare_baseline(HUMAN, ['short baseline text'])
        self.assertFalse(c['sufficient'])
        c = compare_baseline(LLM, [HUMAN * 3])
        self.assertTrue(c['sufficient'])
        self.assertIsNone(c['features']['present_participle_clauses']['ratio'])   # zero baseline rate: no ratio
        c = compare_baseline(LLM, [LLM * 10])
        self.assertAlmostEqual(c['features']['passives']['ratio'], 1.0, places=1)

    def test_mattr_between_zero_and_one(self):
        v = mattr(HUMAN.split())
        self.assertTrue(0 < v <= 1)

    def test_sentence_splitter_keeps_abbreviations(self):
        self.assertEqual(len(_split_sentences('See Dr. Rao et al. for details. Then stop.')), 2)

    def test_reference_list_is_not_prose(self):
        text = 'First real sentence here. Second real sentence here.\n\n## References\n\nSmith, J. 2001. A very long reference title that should not count. London: Press.\n'
        self.assertEqual(compute_metrics(text)['sentences'], 2)
        self.assertEqual(find_patterns('Body text.\n\n## References\n\nSmith 2001. Delve into the tapestry.\n')['total_exact_matches'], 0)

    def test_markup_is_ignored(self):
        m = compute_metrics('# Heading\n\ntitle:: x\n\n- A real sentence here. And another one here.')
        self.assertEqual(m['sentences'], 2)


class Patterns(unittest.TestCase):
    def test_new_patterns_found_and_quotes_excluded(self):
        r = find_patterns('It stands as a testament to craft. He wrote "it plays a vital role" in 1990.')
        phrases = {i['phrase'] for i in r['patterns']['1']['instances']}
        self.assertIn('stands as a testament', phrases)
        self.assertNotIn('plays a vital role', phrases)   # inside quotation marks
        self.assertEqual(r['list_last_reviewed'], '2026-10-04')

    def test_formatting_signals_are_descriptive(self):
        r = find_patterns('One — two — three words **bold** here.')
        self.assertEqual(r['formatting_signals']['em_dashes'], 2)
        self.assertEqual(r['formatting_signals']['bold_spans'], 1)


if __name__ == '__main__':
    unittest.main()
