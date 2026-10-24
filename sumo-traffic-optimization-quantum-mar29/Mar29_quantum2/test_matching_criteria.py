"""Ensure matching cannot pass on recovery alone or tiny absolute gaps."""
import unittest

from refine_stochastic_matching import compare


class MatchingCriteriaTests(unittest.TestCase):
    def test_identical_distribution_passes(self):
        target = [0., 0., 2., 8.]
        self.assertTrue(compare(target * 3, target)['passes_screen'])

    def test_same_recovery_wrong_mistake_sizes_fails(self):
        result = compare([0., 0., .02, .08] * 3, [0., 0., .2, .8])
        self.assertTrue(result['checks']['recovery'])
        self.assertFalse(result['checks']['mean_gap'])
        self.assertFalse(result['checks']['mistake_sizes'])
        self.assertFalse(result['passes_screen'])

    def test_missing_mistakes_cannot_certify_distribution_match(self):
        self.assertFalse(compare([0.] * 12, [0.] * 4)['passes_screen'])

    def test_recovery_difference_has_own_requirement(self):
        result = compare([0., 0., 0., 8.] * 3, [0., 0., 2., 6.])
        self.assertFalse(result['checks']['recovery'])
        self.assertFalse(result['passes_screen'])


if __name__ == '__main__':
    unittest.main()
