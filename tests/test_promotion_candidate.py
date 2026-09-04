"""Focused checks for the content-addressed 0.3.2 comparison candidate."""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sys
import unittest

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from comparative_evidence.compare import compare_synthetic_contract  # noqa: E402
from comparative_evidence.contract_v1 import canonical_digest  # noqa: E402
from comparative_evidence.golden_verification import compare_golden_specimen  # noqa: E402
from comparative_evidence.model import ObservationEnvelope  # noqa: E402
from comparative_evidence.promotion_candidate import (  # noqa: E402
    CANDIDATE_COORDINATE,
    PRIOR_RELEASE_COORDINATE,
    PromotionCandidateError,
    validate_promotion_candidate,
)


def load(relative: str) -> dict:
    value = json.loads((ROOT / relative).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


class PromotionCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.candidate = load("receipts/promotion-candidate.json")
        cls.schema = load("schemas/promotion-candidate.schema.json")

    def test_candidate_and_schema_agree_on_the_bounded_state(self) -> None:
        Draft202012Validator.check_schema(self.schema)
        errors = list(Draft202012Validator(self.schema).iter_errors(self.candidate))
        self.assertEqual(errors, [])
        validate_promotion_candidate(self.candidate)
        self.assertEqual(
            self.candidate["candidate_coordinate"],
            CANDIDATE_COORDINATE,
        )
        self.assertEqual(
            self.candidate["prior_release_coordinate"],
            PRIOR_RELEASE_COORDINATE,
        )

    def test_candidate_identities_are_derived_from_current_sources(self) -> None:
        profile = load("specification/golden-specimen-verification-profile.json")
        implementation = load(
            "fixtures/pairs/enterprise-postgresql-observation.json"
        )
        simulation = load(
            "fixtures/pairs/simulation-golden-specimen-observation.json"
        )
        constellation = load("constellation.lock.json")
        golden = compare_golden_specimen(
            implementation,
            simulation,
            profile,
            constellation,
        )
        contract_shape = compare_synthetic_contract(
            ObservationEnvelope.from_dict(
                load("fixtures/pairs/simulation-observation.json")
            ),
            ObservationEnvelope.from_dict(
                load("fixtures/contracts/planned-observation.json")
            ),
            load("specification/comparison-profile.json"),
        )
        expected = {
            "release": "candidate-comparison-v0.3.2",
            "repository_release": "0.3.2",
            "constellation_lock": "constellation.lock.json",
            "constellation_lock_canonical_json_digest": canonical_digest(
                constellation
            ),
            "synthetic_contract_report_digest": contract_shape["report_digest"],
            "golden_specimen_report_digest": golden["report_digest"],
            "golden_source_constellation_digest": golden[
                "source_constellation_digest"
            ],
        }
        self.assertEqual(self.candidate["candidate_coordinate"], expected)

    def test_prior_release_receipt_remains_exact(self) -> None:
        prior = self.candidate["prior_release_coordinate"]
        receipt_bytes = (ROOT / prior["promotion_receipt"]).read_bytes()
        self.assertEqual(
            "sha256:" + sha256(receipt_bytes).hexdigest(),
            "sha256:733261cf52339f7f6b3e650302ab4b8b51c37eef57c752b0f5e2d2c4e27485ff",
        )
        self.assertEqual(prior["tag"], "comparison-v0.3.1")
        self.assertEqual(
            prior["promotion_receipt_file_sha256"],
            "sha256:" + sha256(receipt_bytes).hexdigest(),
        )

    def test_lineage_drift_returns_to_source_reconciliation(self) -> None:
        changed = deepcopy(self.candidate)
        changed["candidate_coordinate"]["golden_specimen_report_digest"] = (
            "sha256:" + "7" * 64
        )
        with self.assertRaisesRegex(
            PromotionCandidateError,
            "candidate_coordinate",
        ):
            validate_promotion_candidate(changed)

    def test_material_statements_share_the_schema_boundaries(self) -> None:
        for name, value in (
            ("non-text", {}),
            ("overlong", "x" * 501),
            ("padded-overlong", " " + "x" * 500),
        ):
            with self.subTest(name=name):
                changed = deepcopy(self.candidate)
                changed["limitations"] = [value]
                schema_errors = list(
                    Draft202012Validator(self.schema).iter_errors(changed)
                )
                self.assertTrue(schema_errors)
                with self.assertRaisesRegex(
                    PromotionCandidateError,
                    "limitations carries unique material statements",
                ):
                    validate_promotion_candidate(changed)

        changed = deepcopy(self.candidate)
        changed["accountable_role"] = " " + "x" * 120
        schema_errors = list(
            Draft202012Validator(self.schema).iter_errors(changed)
        )
        self.assertTrue(schema_errors)
        with self.assertRaisesRegex(
            PromotionCandidateError,
            "accountable_role carries meaningful text",
        ):
            validate_promotion_candidate(changed)


if __name__ == "__main__":
    unittest.main()
