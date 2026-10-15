from __future__ import annotations

import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from comparative_evidence.compare import ComparisonArithmeticError, _equivalent, compare_synthetic_contract
from comparative_evidence.model import ObservationEnvelope
from comparative_evidence.report import write_reports
from comparative_evidence.artifact_boundary import report_artifact_inventory

PATH = '$.restore.observed_recovery_seconds'


def comparison(expected, actual, relative=0, absolute=0):
    def load(name):
        return json.loads((ROOT / name).read_text())
    simulation = load('fixtures/pairs/simulation-observation.json')
    candidate = load('fixtures/contracts/planned-observation.json')
    profile = load('specification/comparison-profile.json')
    simulation['result']['restore']['observed_recovery_seconds'] = expected
    candidate['result']['restore']['observed_recovery_seconds'] = actual
    profile['numeric_tolerances'][PATH] = {'relative': relative, 'absolute': absolute}
    return compare_synthetic_contract(ObservationEnvelope.from_dict(simulation),
                                      ObservationEnvelope.from_dict(candidate), profile)


class NumericComparisonTests(unittest.TestCase):
    def test_exact_ratio_tolerance_cases(self):
        cases = [
            (0, -0.0, 0, 0, True), (0, 1, 0, 0, False),
            (10, 11, 0, 1, True), (10, 12, 0, 1, False),
            (8, 10, .25, 0, True), (8, 11, .25, 0, False),
            (-8, -10, .25, 0, True), (-8, 8, 1.5, 0, False),
            (1.7e308, -1.7e308, 1.5, 0, False),
            (1.7e308, -1.7e308, 2, 0, True),
            (5e-324, 0, .5, 0, False), (5e-324, 0, 1, 0, True),
            (2**1000, 2**1000 + 1, 0, 0, False),
            (2**1000, 2**1000 + 1, 0, 1, True),
            (2**1000 + 1, float(2**1000), 0, 0, False),
            (10**400, -10**400, 1.5, 0, False),
            (10**400, -10**400, 2, 0, True),
        ]
        for expected, actual, relative, absolute, result in cases:
            with self.subTest(expected_type=type(expected), relative=relative, result=result):
                self.assertIs(_equivalent(expected, actual, {'relative': relative, 'absolute': absolute}), result)

    def test_relative_tolerance_uses_expected_magnitude(self):
        self.assertTrue(math.isclose(8, 10, rel_tol=.2))
        self.assertFalse(_equivalent(8, 10, {'relative': .2}))
        self.assertFalse(_equivalent(True, 1, {'absolute': 1}))

    def test_unrepresentable_directional_values_stop_before_report_digest(self):
        for expected, actual, relative in [(1.7e308, -1.7e308, 1.5),
                                           (1.7e308, -1.7e308, .25),
                                           (5e-324, 1.0, 0),
                                           (10**400, 1.0, 0)]:
            with self.subTest(relative=relative), patch('comparative_evidence.compare.digest') as digest:
                with self.assertRaises(ComparisonArithmeticError) as caught:
                    comparison(expected, actual, relative)
                self.assertEqual(caught.exception.code, 'comparison_arithmetic_capacity')
                self.assertNotIn(str(expected), str(caught.exception))
                digest.assert_not_called()

    def test_large_integer_tolerance_and_report_roundtrip(self):
        report = comparison(1, 2, absolute=10**400)
        self.assertFalse(any(item['path'] == PATH for item in report['differences']))
        report = comparison(2**1000, 2**1000 + 1)
        difference = next(item for item in report['differences'] if item['path'] == PATH)
        self.assertEqual(difference['comparison']['delta'], 1)
        self.assertTrue(math.isfinite(difference['comparison']['relative_delta']))
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / 'result'
            write_reports(report, destination)
            self.assertEqual(set(report_artifact_inventory(destination)), {'comparison.json', 'comparison.html'})
            parsed = json.loads((destination / 'comparison.json').read_text(), parse_constant=lambda v: self.fail(v))
            self.assertEqual(parsed['differences'], report['differences'])

    def test_mixed_numeric_delta_retains_the_integer_difference(self):
        report = comparison(2**1000 + 1, float(2**1000))
        difference = next(item for item in report['differences'] if item['path'] == PATH)
        self.assertEqual(difference['comparison']['delta'], -1.0)
        self.assertLess(difference['comparison']['relative_delta'], 0)

    def test_ordinary_directional_values_remain_stable(self):
        # Existing complete released report identities are exercised by the aggregate
        # validator; this control keeps the ordinary directional result legible here.
        report = comparison(100, 75)
        difference = next(item for item in report['differences'] if item['path'] == PATH)
        self.assertEqual(difference['comparison']['delta'], -25)
        self.assertEqual(difference['comparison']['relative_delta'], -.25)


if __name__ == '__main__':
    unittest.main()
