"""Focused behavior checks for the comparative-evidence promotion carrier."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import unittest

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from comparative_evidence.contract_v1 import strict_json_loads  # noqa: E402
from comparative_evidence.promotion_receipt import (  # noqa: E402
    CANDIDATE_SOURCE,
    PromotionReceiptError,
    canonical_digest,
    file_digest,
    validate_promotion_receipt,
)


class PromotionLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.candidate = strict_json_loads(
            (ROOT / "receipts/promotion-receipt.json").read_text(
                encoding="utf-8"
            )
        )
        cls.schema = strict_json_loads(
            (ROOT / "schemas/promotion-receipt.schema.json").read_text(
                encoding="utf-8"
            )
        )
        assert isinstance(cls.candidate, dict)
        assert isinstance(cls.schema, dict)

    def observed(self) -> dict:
        receipt = deepcopy(self.candidate)
        receipt["promotion_state"] = "release_observed"
        receipt["release_event_evidence"] = {
            "evidence_mode": "observed",
            "assurance_stage": "verified",
        }
        receipt["release_subject"] = {
            "git_object_format": "sha1",
            "tag": "comparison-v0.3.1",
            "tag_object_oid": "1" * 40,
            "commit_oid": "2" * 40,
            "tree_oid": "3" * 40,
            "archive_format": "git-tar",
            "archive_digest": "sha256:" + "4" * 64,
            "promoted_at": "2026-09-02T12:00:00Z",
            "tag_signature_verification": "valid",
            "hosted_check_contexts": [
                {
                    "name": "Repository validation",
                    "run_id": "33600000001",
                    "conclusion": "success",
                },
                {
                    "name": "branch-shape",
                    "run_id": "33600000002",
                    "conclusion": "success",
                },
            ],
            "local_verification_signals": [
                "complete Python 3.12 regression suite passed",
                "repository validation reproduced both comparison bundles",
            ],
        }
        return receipt

    def test_candidate_keeps_release_event_planned_and_subject_open(self) -> None:
        validate_promotion_receipt(self.candidate)
        self.assertEqual(self.candidate["promotion_state"], "candidate_ready")
        self.assertEqual(
            self.candidate["release_event_evidence"],
            {"evidence_mode": "planned", "assurance_stage": "specified"},
        )
        self.assertIsNone(self.candidate["release_subject"])

    def test_candidate_source_is_a_typed_non_self_referential_coordinate(self) -> None:
        self.assertEqual(self.candidate["candidate_source"], CANDIDATE_SOURCE)
        self.assertEqual(
            CANDIDATE_SOURCE["coordinate_kind"],
            "accepted_develop_merge_source",
        )
        self.assertEqual(len(CANDIDATE_SOURCE["commit_oid"]), 40)
        self.assertEqual(len(CANDIDATE_SOURCE["tree_oid"]), 40)
        self.assertNotEqual(CANDIDATE_SOURCE["commit_oid"], "0" * 40)
        self.assertNotEqual(CANDIDATE_SOURCE["tree_oid"], "0" * 40)

        changed = deepcopy(self.candidate)
        changed["candidate_source"]["commit_oid"] = "5" * 40
        with self.assertRaisesRegex(
            PromotionReceiptError,
            "accepted develop merge source",
        ):
            validate_promotion_receipt(changed)

    def test_schema_names_candidate_and_later_observed_states(self) -> None:
        Draft202012Validator.check_schema(self.schema)
        validator = Draft202012Validator(self.schema)
        self.assertEqual(list(validator.iter_errors(self.candidate)), [])
        self.assertEqual(list(validator.iter_errors(self.observed())), [])
        self.assertEqual(
            self.schema["properties"]["promotion_state"]["enum"],
            ["candidate_ready", "release_observed"],
        )
        self.assertEqual(
            self.schema["properties"]["target_release"]["const"],
            "comparison-v0.3.1",
        )
        self.assertEqual(
            set(self.schema["$defs"]["observedReleaseSubject"]["required"]),
            {
                "git_object_format",
                "tag",
                "tag_object_oid",
                "commit_oid",
                "tree_oid",
                "archive_format",
                "archive_digest",
                "promoted_at",
                "tag_signature_verification",
                "hosted_check_contexts",
                "local_verification_signals",
            },
        )

    def test_comparison_authority_stays_simulated_and_non_authorizing(self) -> None:
        self.assertEqual(
            self.candidate["comparison_authority"],
            {
                "evidence_mode": "simulated",
                "assurance_stage": "verified",
                "comparison_mode": "simulated_verification",
                "environment_observed_closure": "separate_unasserted_state",
                "production_authorization_effect": "none",
            },
        )
        changed = deepcopy(self.candidate)
        changed["comparison_authority"]["evidence_mode"] = "observed"
        with self.assertRaisesRegex(
            PromotionReceiptError,
            "comparison_authority uses simulated-verification authority",
        ):
            validate_promotion_receipt(changed)

    def test_observed_release_requires_complete_immutable_subject(self) -> None:
        receipt = self.observed()
        validate_promotion_receipt(receipt)

        mutations = (
            (
                "missing-tree",
                lambda value: value["release_subject"].pop("tree_oid"),
                "release_subject carries exactly",
            ),
            (
                "unsigned-tag",
                lambda value: value["release_subject"].__setitem__(
                    "tag_signature_verification", "unverified"
                ),
                "tag_signature_verification",
            ),
            (
                "zero-archive",
                lambda value: value["release_subject"].__setitem__(
                    "archive_digest", "sha256:" + "0" * 64
                ),
                "nonzero SHA-256",
            ),
            (
                "undated-promotion",
                lambda value: value["release_subject"].__setitem__(
                    "promoted_at", "2026-09-02T12:00:00"
                ),
                "explicit UTC offset",
            ),
            (
                "duplicate-check",
                lambda value: value["release_subject"][
                    "hosted_check_contexts"
                ].append(
                    deepcopy(
                        value["release_subject"]["hosted_check_contexts"][0]
                    )
                ),
                "check names and run IDs unique",
            ),
        )
        for name, mutate, message in mutations:
            with self.subTest(name=name):
                changed = deepcopy(receipt)
                mutate(changed)
                with self.assertRaisesRegex(PromotionReceiptError, message):
                    validate_promotion_receipt(changed)

    def test_candidate_cannot_carry_an_observed_release_subject(self) -> None:
        changed = deepcopy(self.candidate)
        changed["release_subject"] = self.observed()["release_subject"]
        with self.assertRaisesRegex(
            PromotionReceiptError,
            "keeps release_subject null",
        ):
            validate_promotion_receipt(changed)

    def test_manifest_binding_inputs_have_stable_carrier_identities(self) -> None:
        schema_path = ROOT / "schemas/promotion-receipt.schema.json"
        receipt_path = ROOT / "receipts/promotion-receipt.json"
        manifest = strict_json_loads(
            (ROOT / "release/repository-role.json").read_text(encoding="utf-8")
        )
        assert isinstance(manifest, dict)
        self.assertRegex(file_digest(schema_path), r"^sha256:[a-f0-9]{64}$")
        self.assertRegex(
            canonical_digest(self.candidate),
            r"^sha256:[a-f0-9]{64}$",
        )
        self.assertTrue(receipt_path.is_file())
        self.assertEqual(
            manifest["promotion_receipt_contract"],
            {
                "schema_path": "schemas/promotion-receipt.schema.json",
                "schema_version": self.candidate["schema_version"],
                "schema_file_sha256": file_digest(schema_path),
                "receipt_path": "receipts/promotion-receipt.json",
                "receipt_canonical_json_digest": canonical_digest(
                    self.candidate
                ),
            },
        )
        self.assertEqual(
            manifest["promotion_coordinates"],
            {
                "status": "candidate_ready",
                "open_receipt_id": self.candidate["promotion_receipt_id"],
                "candidate_source": self.candidate["candidate_source"],
                "required_roles": [
                    "site_reading_governance",
                    "program_specification",
                    "enterprise_implementation",
                    "simulated_final_state",
                    "comparative_evidence",
                ],
            },
        )


if __name__ == "__main__":
    unittest.main()
