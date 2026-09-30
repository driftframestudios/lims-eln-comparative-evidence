"""Focused behavior checks for the comparative-evidence promotion carrier."""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
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
from comparative_evidence.promotion_candidate import (  # noqa: E402
    PRIOR_RELEASE_COORDINATE,
)
from comparative_evidence.promotion_observation import (  # noqa: E402
    CANDIDATE_COORDINATE as OBSERVED_CANDIDATE_COORDINATE,
    RELEASE_COORDINATE,
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
        promotion_candidate_path = ROOT / "receipts/promotion-candidate.json"
        promotion_candidate = strict_json_loads(
            promotion_candidate_path.read_text(encoding="utf-8")
        )
        promotion_observation_path = (
            ROOT / "receipts/promotion-observation-v0.3.2.json"
        )
        promotion_observation_schema_path = (
            ROOT / "schemas/promotion-observation-v0.3.2.schema.json"
        )
        promotion_observation = strict_json_loads(
            promotion_observation_path.read_text(encoding="utf-8")
        )
        assert isinstance(manifest, dict)
        assert isinstance(promotion_candidate, dict)
        assert isinstance(promotion_observation, dict)
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
            manifest["promotion_observation_contract"],
            {
                "schema_path": (
                    "schemas/promotion-observation-v0.3.2.schema.json"
                ),
                "schema_version": "1.0.0",
                "schema_file_sha256": (
                    "sha256:"
                    + sha256(
                        promotion_observation_schema_path.read_bytes()
                    ).hexdigest()
                ),
                "receipt_path": (
                    "receipts/promotion-observation-v0.3.2.json"
                ),
                "receipt_file_sha256": (
                    "sha256:"
                    + sha256(promotion_observation_path.read_bytes()).hexdigest()
                ),
                "receipt_canonical_json_digest": canonical_digest(
                    promotion_observation
                ),
            },
        )
        self.assertEqual(
            manifest["promotion_coordinates"],
            {
                "status": "release_observed",
                "settled_receipt_id": "RCP-COMPARATIVE-PROMOTION-004",
                "observation_receipt": (
                    "receipts/promotion-observation-v0.3.2.json"
                ),
                "observation_receipt_file_sha256": (
                    "sha256:"
                    + sha256(promotion_observation_path.read_bytes()).hexdigest()
                ),
                "observation_receipt_canonical_json_digest": canonical_digest(
                    promotion_observation
                ),
                "candidate_receipt": "receipts/promotion-candidate.json",
                "candidate_receipt_file_sha256": (
                    "sha256:"
                    + sha256(promotion_candidate_path.read_bytes()).hexdigest()
                ),
                "candidate_receipt_canonical_json_digest": canonical_digest(
                    promotion_candidate
                ),
                "target_release": "comparison-v0.3.2",
                "candidate_coordinate": OBSERVED_CANDIDATE_COORDINATE,
                "release_subject": RELEASE_COORDINATE,
                "prior_release": PRIOR_RELEASE_COORDINATE,
                "required_roles": [
                    "site_reading_governance",
                    "program_specification",
                    "enterprise_implementation",
                    "simulated_final_state",
                    "comparative_evidence",
                ],
            },
        )

    def test_control_plane_records_publication_and_program_handoff(self) -> None:
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
        self.assertEqual(machine["lifecycle_state"], "settling")
        self.assertEqual(machine["open_receipts"], [])
        self.assertEqual(first_receipt["open_receipts"], machine["open_receipts"])
        self.assertEqual(
            horizon["current_item_ids"],
            ["WORK-PROGRAM-CONSTELLATION-HANDOFF-001"],
        )
        self.assertEqual(
            {
                machine["metadata"]["updated_at"],
                first_receipt["as_of"],
                first_receipt["metadata"]["updated_at"],
                horizon["as_of"],
                horizon["metadata"]["updated_at"],
            },
            {"2026-09-30T15:07:07Z"},
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
        self.assertEqual(
            first_receipt["handoff"]["recipient_role"],
            "Program specification constellation receiver",
        )
        self.assertGreaterEqual(len(expected_next_action.strip()), 40)
        publication_source = [
            item
            for item in first_receipt["source_permissions"]
            if item["source"] == "accepted-main-observation-carrier"
        ]
        self.assertEqual(1, len(publication_source))
        self.assertEqual("read", publication_source[0]["permission"])
        self.assertGreaterEqual(
            len(publication_source[0]["verification"].strip()),
            40,
        )
        publication_items = {
            item["item_id"]: item for item in horizon["work_items"]
        }
        publication_item = publication_items["WORK-COMPARATIVE-PUBLICATION-017"]
        candidate_item = publication_items["WORK-COMPARATIVE-PROMOTION-004"]
        successor_publication_item = publication_items[
            "WORK-COMPARATIVE-PUBLICATION-031"
        ]
        living_orientation_item = publication_items[
            "WORK-GOVERNANCE-LIVING-ORIENTATION-038"
        ]
        program_handoff_item = publication_items[
            "WORK-PROGRAM-CONSTELLATION-HANDOFF-001"
        ]
        self.assertEqual("complete", publication_item["state"])
        self.assertEqual("complete", candidate_item["state"])
        self.assertEqual("complete", successor_publication_item["state"])
        self.assertEqual("complete", living_orientation_item["state"])
        self.assertEqual("ready", program_handoff_item["state"])
        self.assertEqual(
            ["WORK-COMPARATIVE-PUBLICATION-017"],
            candidate_item["dependency_ids"],
        )
        self.assertEqual(
            ["WORK-COMPARATIVE-PROMOTION-004"],
            successor_publication_item["dependency_ids"],
        )
        self.assertGreaterEqual(
            len(successor_publication_item["completion_evidence"]),
            3,
        )
        self.assertEqual(
            ["WORK-COMPARATIVE-PUBLICATION-031"],
            living_orientation_item["dependency_ids"],
        )
        self.assertEqual(
            ["WORK-GOVERNANCE-LIVING-ORIENTATION-038"],
            program_handoff_item["dependency_ids"],
        )
        self.assertGreaterEqual(
            len(program_handoff_item["completion_evidence"]),
            3,
        )
        self.assertTrue(
            all(
                len(value.strip()) >= 40
                for value in successor_publication_item["completion_evidence"]
            )
        )
        self.assertEqual(
            repository_role["publication_coordinates"],
            {
                "status": "published",
                "source_coordinate_kind": "accepted_main_publication_carrier",
                "accepted_branch_ref": "refs/remotes/origin/main",
                "release_subject_commit_oid": (
                    "0289ff835c790693a769347e69da0abdcfaa47de"
                ),
                "receipt_path": "receipts/promotion-observation-v0.3.2.json",
                "receipt_state": "release_observed",
                "receipt_blob_oid": (
                    "c6318597b4d038cd59c897d4041c7e0178e60e15"
                ),
                "receipt_file_sha256": (
                    "sha256:acccb507f0675cdc079aa56bc12299bd4ce533344cb150e42dba1c991c024fd4"
                ),
                "source_revision": (
                    "2cca88982444ebc8280f9eb2891d97bf25dbeb95"
                ),
                "source_revision_relation": (
                    "accepted_observation_carrier_descending_from_signed_release"
                ),
                "publication_revision_role": "pages_source_revision",
                "projection_manifest_field": "sourceRevision",
                "docs_revision": (
                    "6ccc087875b439eb70304771f534434acae3f01c"
                ),
                "projection_manifest_blob_oid": (
                    "2c701af256c74c5ec73dd266c0e62aeb554b11a6"
                ),
                "projection_manifest_sha256": (
                    "sha256:38d01a78be6804d04bc4f24c412777b8cb08fe2c65372e278480c106b4bcbeea"
                ),
                "canonical_origin": "https://cometspectrum.io/",
                "observed_at": "2026-09-04T05:24:33Z",
                "receiver_issue": 31,
                "target_branch": "docs",
                "hosted_observation": {
                    "pages_run_id": "33839764767",
                    "deploy_job_id": "100919655445",
                    "pages_run_head_revision": (
                        "6ccc087875b439eb70304771f534434acae3f01c"
                    ),
                    "pages_run_conclusion": "success",
                    "pages_run_completed_at": "2026-09-04T05:15:41Z",
                    "verified_at": "2026-09-04T05:24:33Z",
                    "byte_parity": "verified_against_docs_projection",
                    "responsive_report_surface": "narrow_and_desktop_verified",
                },
            },
        )
        prior_publication = repository_role["historical_external_releases"][0][
            "publication_coordinates"
        ]
        self.assertEqual(
            prior_publication,
            {
                "status": "published",
                "source_coordinate_kind": "accepted_main_publication_carrier",
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
                "initial_source_revision": (
                    "9012a03d1e5175c7794c4c8d5c5e620b5943a430"
                ),
                "initial_docs_revision": (
                    "17636bb3587ad768d5422439af57240141d5cb9c"
                ),
                "initial_projection_manifest_sha256": (
                    "sha256:0e5e73f183b993aa740f2979a463518ec65f9dcce8405f17ffa5b910e22ed221"
                ),
                "source_revision": (
                    "fadbb1aba21a828eb56ee35c0abb4bb32b7f498c"
                ),
                "source_revision_relation": (
                    "presentation_follow_up_preserving_golden_report_digest"
                ),
                "publication_revision_role": "pages_source_revision",
                "projection_manifest_field": "sourceRevision",
                "docs_revision": (
                    "ff9a82f78b15b07ab90774032d2ec7a7bfd2bcd1"
                ),
                "projection_manifest_blob_oid": (
                    "c7ba848af3920b4d6b4d8d67d71778595b643d53"
                ),
                "projection_manifest_sha256": (
                    "sha256:9a577fc95c31f4cffa40ebce51dd6b9f1738a3f70c595c3de59e9d80de4a69bf"
                ),
                "canonical_origin": "https://cometspectrum.io/",
                "observed_at": "2026-09-02T17:18:30Z",
                "receiver_issue": 17,
                "target_branch": "docs",
            },
        )


if __name__ == "__main__":
    unittest.main()
