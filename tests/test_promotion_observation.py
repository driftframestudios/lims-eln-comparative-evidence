"""Focused checks for the observed Comparative Evidence 0.3.2 release."""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import unittest

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from comparative_evidence.contract_v1 import canonical_digest  # noqa: E402
from comparative_evidence.promotion_observation import (  # noqa: E402
    CANDIDATE_COORDINATE,
    PromotionObservationError,
    RELEASE_COORDINATE,
    validate_promotion_observation,
)
from tools.verify_promotion_observation import (  # noqa: E402
    verify_promotion_observation,
)


def load(relative: str) -> dict:
    value = json.loads((ROOT / relative).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def git(*arguments: str) -> str:
    return subprocess.run(
        ["git", "--no-pager", "--no-replace-objects", *arguments],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


class PromotionObservationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.observation = load("receipts/promotion-observation-v0.3.2.json")
        cls.schema = load("schemas/promotion-observation-v0.3.2.schema.json")

    def test_observation_and_schema_agree_on_the_release(self) -> None:
        Draft202012Validator.check_schema(self.schema)
        self.assertEqual(
            list(Draft202012Validator(self.schema).iter_errors(self.observation)),
            [],
        )
        validate_promotion_observation(self.observation)
        self.assertEqual(self.observation["candidate_coordinate"], CANDIDATE_COORDINATE)
        self.assertEqual(self.observation["release_coordinate"], RELEASE_COORDINATE)

    def test_candidate_link_is_derived_from_the_accepted_source(self) -> None:
        candidate = self.observation["candidate_coordinate"]
        candidate_path = candidate["candidate_receipt"]
        candidate_bytes = subprocess.run(
            [
                "git",
                "--no-pager",
                "--no-replace-objects",
                "show",
                f"{candidate['commit_oid']}:{candidate_path}",
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
        ).stdout
        self.assertEqual(
            candidate["tree_oid"],
            git("rev-parse", f"{candidate['commit_oid']}^{{tree}}"),
        )
        self.assertEqual(
            candidate["candidate_receipt_file_sha256"],
            "sha256:" + sha256(candidate_bytes).hexdigest(),
        )
        self.assertEqual(
            candidate["candidate_receipt_canonical_json_digest"],
            canonical_digest(json.loads(candidate_bytes)),
        )

    def test_candidate_and_release_share_one_tree(self) -> None:
        candidate = self.observation["candidate_coordinate"]
        release = self.observation["release_coordinate"]
        self.assertEqual(candidate["tree_oid"], release["tree_oid"])
        self.assertEqual(
            release["tree_oid"],
            git("rev-parse", f"{release['commit_oid']}^{{tree}}"),
        )

    def test_coordinate_and_material_statement_drift_is_typed(self) -> None:
        changed = deepcopy(self.observation)
        changed["release_coordinate"]["archive_digest"] = "sha256:" + "7" * 64
        with self.assertRaisesRegex(
            PromotionObservationError,
            "release_coordinate",
        ):
            validate_promotion_observation(changed)

        for value in ({}, " " + "x" * 500):
            with self.subTest(value_type=type(value).__name__):
                changed = deepcopy(self.observation)
                changed["limitations"] = [value]
                self.assertTrue(
                    list(Draft202012Validator(self.schema).iter_errors(changed))
                )
                with self.assertRaisesRegex(
                    PromotionObservationError,
                    "limitations carries unique material statements",
                ):
                    validate_promotion_observation(changed)

    def test_current_observation_matches_its_signed_release_and_head_carrier(self) -> None:
        result = verify_promotion_observation(ROOT)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["tag"], "comparison-v0.3.2")

    def test_historical_release_verifier_family_remains_exact(self) -> None:
        expected = {
            "receipts/promotion-receipt.json": "733261cf52339f7f6b3e650302ab4b8b51c37eef57c752b0f5e2d2c4e27485ff",
            "schemas/promotion-receipt.schema.json": "8ebce65f823acb91b459049b2692bf05261c78d5346034e9603319c85de1b594",
            "src/comparative_evidence/promotion_receipt.py": "377b6a771089bbda1fcdb50cfbc6f2e6ce802ddd2354362e671fb57b11e8c05e",
            "tools/verify_release_coordinate.py": "f0f4b4ba851069ce94880df06ddd9f01cb9936579d6fee17a590795cb7f2069f",
            "tests/test_release_coordinate.py": "0af1acf1f505444ef4aebad24835b47922c28246f96bd569615dc99af21c1edb",
        }
        for relative, digest in expected.items():
            with self.subTest(path=relative):
                self.assertEqual(
                    sha256((ROOT / relative).read_bytes()).hexdigest(),
                    digest,
                )


if __name__ == "__main__":
    unittest.main()
