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
        cls.receipt = strict_json_loads(
            (ROOT / "receipts/promotion-receipt.json").read_text(
                encoding="utf-8"
            )
        )
        cls.schema = strict_json_loads(
            (ROOT / "schemas/promotion-receipt.schema.json").read_text(
                encoding="utf-8"
            )
        )
        assert isinstance(cls.receipt, dict)
        assert isinstance(cls.schema, dict)

    def candidate(self) -> dict:
        receipt = deepcopy(self.receipt)
        receipt["promotion_state"] = "candidate_ready"
        receipt["release_event_evidence"] = {
            "evidence_mode": "planned",
            "assurance_stage": "specified",
        }
        receipt["release_subject"] = None
        return receipt

    def observed(self) -> dict:
        return deepcopy(self.receipt)

    def test_candidate_state_keeps_release_event_planned_and_subject_open(self) -> None:
        candidate = self.candidate()
        validate_promotion_receipt(candidate)
        self.assertEqual(candidate["promotion_state"], "candidate_ready")
        self.assertEqual(
            candidate["release_event_evidence"],
            {"evidence_mode": "planned", "assurance_stage": "specified"},
        )
        self.assertIsNone(candidate["release_subject"])

    def test_repository_receipt_records_the_observed_release(self) -> None:
        validate_promotion_receipt(self.receipt)
        self.assertEqual(self.receipt["promotion_state"], "release_observed")
        self.assertEqual(
            self.receipt["release_event_evidence"],
            {"evidence_mode": "observed", "assurance_stage": "verified"},
        )
        self.assertEqual(
            self.receipt["release_subject"]["commit_oid"],
            "b5c13689a32739d29437e209816bf0cd6a878976",
        )

    def test_candidate_source_is_a_typed_non_self_referential_coordinate(self) -> None:
        self.assertEqual(self.receipt["candidate_source"], CANDIDATE_SOURCE)
        self.assertEqual(
            CANDIDATE_SOURCE["coordinate_kind"],
            "accepted_develop_merge_source",
        )
        self.assertEqual(len(CANDIDATE_SOURCE["commit_oid"]), 40)
        self.assertEqual(len(CANDIDATE_SOURCE["tree_oid"]), 40)
        self.assertNotEqual(CANDIDATE_SOURCE["commit_oid"], "0" * 40)
        self.assertNotEqual(CANDIDATE_SOURCE["tree_oid"], "0" * 40)

        changed = deepcopy(self.receipt)
        changed["candidate_source"]["commit_oid"] = "5" * 40
        with self.assertRaisesRegex(
            PromotionReceiptError,
            "accepted develop merge source",
        ):
            validate_promotion_receipt(changed)

    def test_schema_names_candidate_and_later_observed_states(self) -> None:
        Draft202012Validator.check_schema(self.schema)
        validator = Draft202012Validator(self.schema)
        self.assertEqual(list(validator.iter_errors(self.candidate())), [])
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
            self.receipt["comparison_authority"],
            {
                "evidence_mode": "simulated",
                "assurance_stage": "verified",
                "comparison_mode": "simulated_verification",
                "environment_observed_closure": "separate_unasserted_state",
                "production_authorization_effect": "none",
            },
        )
        changed = deepcopy(self.receipt)
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
        changed = self.candidate()
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
            canonical_digest(self.receipt),
            r"^sha256:[a-f0-9]{64}$",
        )
        self.assertTrue(receipt_path.is_file())
        self.assertEqual(
            manifest["promotion_receipt_contract"],
            {
                "schema_path": "schemas/promotion-receipt.schema.json",
                "schema_version": self.receipt["schema_version"],
                "schema_file_sha256": file_digest(schema_path),
                "receipt_path": "receipts/promotion-receipt.json",
                "receipt_canonical_json_digest": canonical_digest(
                    self.receipt
                ),
            },
        )
        self.assertEqual(
            manifest["promotion_coordinates"],
            {
                "status": "settled",
                "settled_receipt_id": self.receipt["promotion_receipt_id"],
                "receipt_path": "receipts/promotion-receipt.json",
                "candidate_source": self.receipt["candidate_source"],
                "reviewed_candidate": {
                    "commit_oid": "59d58c46d27a77150d399870ecebef2635c38dc5",
                    "tree_oid": "10a784b8a677ee6eb524d2860ff5ee7151d6050b",
                },
                "observed_release": {
                    field: self.receipt["release_subject"][field]
                    for field in (
                        "tag",
                        "tag_object_oid",
                        "commit_oid",
                        "tree_oid",
                        "archive_digest",
                        "promoted_at",
                    )
                },
                "required_roles": [
                    "site_reading_governance",
                    "program_specification",
                    "enterprise_implementation",
                    "simulated_final_state",
                    "comparative_evidence",
                ],
            },
        )

    def test_control_plane_closes_the_promotion_and_routes_publication(self) -> None:
        constellation = strict_json_loads(
            (ROOT / "constellation.lock.json").read_text(encoding="utf-8")
        )
        machine = strict_json_loads(
            (ROOT / "machine-node.json").read_text(encoding="utf-8")
        )
        first_receipt = strict_json_loads(
            (ROOT / "first-receipt.json").read_text(encoding="utf-8")
        )
        horizon = strict_json_loads(
            (ROOT / "COORDINATION-HORIZON.json").read_text(encoding="utf-8")
        )
        repository_role = strict_json_loads(
            (ROOT / "release/repository-role.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            constellation["comparison"],
            {
                "release": "comparison-v0.3.1",
                "tag_object_oid": "4c29f6ca410eb4400c55ad77fc34ada2960d1972",
                "commit": "b5c13689a32739d29437e209816bf0cd6a878976",
                "digest": "git-tree-sha1:10a784b8a677ee6eb524d2860ff5ee7151d6050b",
                "archive_digest": "sha256:92c2d57bd9e75c650365db4b481a22a6580b201926ba1c666fcf8cb8c9311a2e",
                "coordinate_status": "release_observed",
                "canonical_closure_digest": "sha256:33bcc14da24309b7716728b3f0204008e8f7ebf58de75f9e40a5986b421f06b5",
                "receipt_schema": "2.0.1",
            },
        )
        self.assertEqual(machine["lifecycle_state"], "reference_ready")
        self.assertEqual(machine["open_receipts"], [])
        self.assertEqual(first_receipt["open_receipts"], [])
        self.assertEqual(
            horizon["current_item_ids"],
            ["WORK-COMPARATIVE-PUBLICATION-017"],
        )
        self.assertEqual(
            {
                machine["metadata"]["updated_at"],
                first_receipt["as_of"],
                first_receipt["metadata"]["updated_at"],
                horizon["as_of"],
                horizon["metadata"]["updated_at"],
            },
            {"2026-09-02T06:59:11Z"},
        )
        self.assertEqual(
            self.receipt["release_subject"]["promoted_at"],
            "2026-09-02T06:27:41Z",
        )
        self.assertGreaterEqual(len(horizon["objective"].strip()), 40)
        expected_next_action = horizon["reentry_capsule"]["next_safe_action"]
        self.assertEqual(
            first_receipt["handoff"]["next_safe_action"],
            expected_next_action,
        )
        self.assertGreaterEqual(len(expected_next_action.strip()), 40)
        publication_source = [
            item
            for item in first_receipt["source_permissions"]
            if item["source"] == "accepted-main-observation-carrier"
        ]
        self.assertEqual(1, len(publication_source))
        self.assertEqual("execute_bounded", publication_source[0]["permission"])
        self.assertGreaterEqual(
            len(publication_source[0]["verification"].strip()),
            40,
        )
        publication_items = {
            item["item_id"]: item for item in horizon["work_items"]
        }
        publication_item = publication_items["WORK-COMPARATIVE-PUBLICATION-017"]
        self.assertEqual("ready", publication_item["state"])
        self.assertGreaterEqual(len(publication_item["completion_evidence"]), 3)
        self.assertTrue(
            all(
                len(value.strip()) >= 40
                for value in publication_item["completion_evidence"]
            )
        )
        self.assertEqual(
            repository_role["publication_coordinates"],
            {
                "status": "awaiting_accepted_carrier",
                "source_coordinate_kind": (
                    "first_parent_main_commit_carrying_receipt_blob"
                ),
                "accepted_branch_ref": "refs/remotes/origin/main",
                "release_subject_commit_oid": (
                    "b5c13689a32739d29437e209816bf0cd6a878976"
                ),
                "receipt_path": "receipts/promotion-receipt.json",
                "receipt_state": "release_observed",
                "receipt_blob_oid": (
                    "4b2f41fe86fb4050d2d3f7da984baa78463c0c12"
                ),
                "receipt_file_sha256": (
                    "sha256:733261cf52339f7f6b3e650302ab4b8b51c37eef57c752b0f5e2d2c4e27485ff"
                ),
                "publication_revision_role": "pages_source_revision",
                "projection_manifest_field": "sourceRevision",
                "receiver_issue": 17,
                "target_branch": "docs",
            },
        )


if __name__ == "__main__":
    unittest.main()
