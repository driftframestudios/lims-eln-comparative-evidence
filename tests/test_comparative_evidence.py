from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from comparative_evidence.calibration import CalibrationError, score_calibration
from comparative_evidence.compare import compare
from comparative_evidence.cli import _load
from comparative_evidence import __version__
from comparative_evidence.gate import AdmissionError, admit
from comparative_evidence.model import ObservationEnvelope, digest
from comparative_evidence.report import render_html
from comparative_evidence.safety import EvidenceSafetyError
from comparative_evidence.simulated_closure import (
    SimulatedClosureError,
    TRUSTED_CLOSURE_ID,
    TRUSTED_FUTURE_REALITY_ID,
    TRUSTED_FUTURE_REALITY_VERSION,
    TRUSTED_GOVERNANCE_CLOSURE_DIGEST,
    TRUSTED_SOURCE_COORDINATES,
    admit_simulated_closure,
    validate_simulated_closure_bundle,
)


def load(path: str) -> dict:
    return json.loads((ROOT / path).read_text())


class ComparativeEvidenceTests(unittest.TestCase):
    def test_calibration_ledger_preserves_honest_empty_state(self) -> None:
        result = score_calibration(
            load("fixtures/calibration/observed-outcomes.json")
        )
        self.assertEqual(result["resolved_forecast_count"], 0)
        self.assertIsNone(result["brier_score"])
        self.assertEqual(
            result["status"],
            "awaiting_independently_observed_outcomes",
        )

    def test_calibration_scores_only_independently_observed_resolutions(self) -> None:
        ledger = load("fixtures/calibration/observed-outcomes.json")
        ledger["entries"] = [
            {
                "forecast_id": "FORECAST-CLOSURE-001",
                "event": "The released migration rehearsal meets its recovery objective.",
                "probability": 0.8,
                "outcome": 1,
                "forecasted_at": "2026-07-28T10:00:00Z",
                "resolved_at": "2026-08-28T10:00:00Z",
                "resolution_mode": "observed",
                "resolution_evidence_digest": "sha256:" + "a" * 64,
            },
            {
                "forecast_id": "FORECAST-VENDOR-001",
                "event": "The qualified vendor environment passes the released contract.",
                "probability": 0.25,
                "outcome": 0,
                "forecasted_at": "2026-07-28T10:00:00Z",
                "resolved_at": "2026-08-29T10:00:00Z",
                "resolution_mode": "observed",
                "resolution_evidence_digest": "sha256:" + "b" * 64,
            },
        ]
        result = score_calibration(ledger)
        self.assertEqual(result["status"], "scored")
        self.assertEqual(result["resolved_forecast_count"], 2)
        self.assertAlmostEqual(result["brier_score"], 0.05125)

    def test_calibration_rejects_simulated_resolution_and_duplicate_identity(
        self,
    ) -> None:
        entry = {
            "forecast_id": "FORECAST-CLOSURE-001",
            "event": "The released migration rehearsal meets its recovery objective.",
            "probability": 0.8,
            "outcome": 1,
            "forecasted_at": "2026-07-28T10:00:00Z",
            "resolved_at": "2026-08-28T10:00:00Z",
            "resolution_mode": "simulated",
            "resolution_evidence_digest": "sha256:" + "a" * 64,
        }
        ledger = load("fixtures/calibration/observed-outcomes.json")
        ledger["entries"] = [entry]
        with self.assertRaisesRegex(CalibrationError, "independently observed"):
            score_calibration(ledger)

        entry["resolution_mode"] = "observed"
        ledger["entries"] = [entry, deepcopy(entry)]
        with self.assertRaisesRegex(CalibrationError, "one resolution"):
            score_calibration(ledger)

    def test_selected_future_closes_all_four_receipt_families(self) -> None:
        bundle = load(
            "fixtures/simulated-closures/future-reality-2028-06-30-v1.json"
        )
        summary = validate_simulated_closure_bundle(bundle)
        self.assertEqual(summary["families_closed"], 4)
        self.assertEqual(summary["closure_status"], "closed_in_simulation")
        self.assertEqual(
            summary["governance_closure_digest"],
            "sha256:c402e7a72d9066424d5b83c8fda51ca2fad43c025d017a5f5535126239c96ffb",
        )
        self.assertEqual(
            summary["environment_observed_closure"],
            "separate_unasserted_state",
        )
        self.assertEqual(summary["production_authorization_effect"], "none")
        self.assertEqual(
            summary["external_encounter_posture"],
            "available_for_independent_comparison",
        )

    def test_selected_future_closure_rejects_digest_drift(self) -> None:
        bundle = load(
            "fixtures/simulated-closures/future-reality-2028-06-30-v1.json"
        )
        bundle["governance_closure"]["closure_status"] = "revised"
        with self.assertRaisesRegex(
            SimulatedClosureError,
            "exact canonical closure document",
        ):
            validate_simulated_closure_bundle(bundle)

    def test_selected_future_requires_source_result_digest(self) -> None:
        bundle = load(
            "fixtures/simulated-closures/future-reality-2028-06-30-v1.json"
        )
        bundle["source_result_digest"] = "sha256:short"
        with self.assertRaisesRegex(
            SimulatedClosureError,
            "source_result_digest requires sha256",
        ):
            validate_simulated_closure_bundle(bundle)

    def test_selected_future_rejects_recomputed_noncanonical_closure(self) -> None:
        bundle = load(
            "fixtures/simulated-closures/future-reality-2028-06-30-v1.json"
        )
        bundle["governance_closure"]["future_reality"]["narrative"] = (
            "This alternative remains internally coherent while representing a "
            "different, unpromoted release document."
        )
        bundle["governance_closure_digest"] = digest(
            bundle["governance_closure"]
        )
        with self.assertRaisesRegex(
            SimulatedClosureError,
            "trusted release closure digest",
        ):
            validate_simulated_closure_bundle(bundle)

    def test_selected_future_rejects_untrusted_source_coordinate(self) -> None:
        bundle = load(
            "fixtures/simulated-closures/future-reality-2028-06-30-v1.json"
        )
        bundle["governance_closure"]["future_reality"]["source_coordinates"][0][
            "commit"
        ] = "0" * 40
        bundle["governance_closure_digest"] = digest(
            bundle["governance_closure"]
        )
        with self.assertRaisesRegex(
            SimulatedClosureError,
            "trusted release source coordinates",
        ):
            validate_simulated_closure_bundle(bundle)

    def test_selected_future_rejects_projection_detail_digest_drift(self) -> None:
        bundle = load(
            "fixtures/simulated-closures/future-reality-2028-06-30-v1.json"
        )
        projection = bundle["governance_closure"]["receipt_closures"][0]
        projection["artifacts"][0]["digest"] = (
            "sha256:" + "0" * 64
        )
        bundle["governance_closure_digest"] = digest(
            bundle["governance_closure"]
        )
        with self.assertRaisesRegex(
            SimulatedClosureError,
            "differs from its detailed receipt",
        ):
            validate_simulated_closure_bundle(bundle)

    def test_selected_future_preserves_non_authorizing_boundary(self) -> None:
        bundle = load(
            "fixtures/simulated-closures/future-reality-2028-06-30-v1.json"
        )
        bundle["governance_closure"]["production_authorization_effect"] = (
            "production_write"
        )
        bundle["governance_closure_digest"] = digest(
            bundle["governance_closure"]
        )
        with self.assertRaisesRegex(
            SimulatedClosureError,
            "production_authorization_effect=none",
        ):
            validate_simulated_closure_bundle(bundle)

    def test_selected_future_metadata_keeps_role_identity_repository_safe(self) -> None:
        bundle = load(
            "fixtures/simulated-closures/future-reality-2028-06-30-v1.json"
        )
        bundle["governance_closure"]["metadata"]["owner"]["display_name"] = (
            "Named Person"
        )
        bundle["governance_closure_digest"] = digest(
            bundle["governance_closure"]
        )
        with self.assertRaisesRegex(
            EvidenceSafetyError,
            "protected content",
        ):
            validate_simulated_closure_bundle(bundle)

    def test_selected_future_closure_admission_is_immutable(self) -> None:
        bundle = load(
            "fixtures/simulated-closures/future-reality-2028-06-30-v1.json"
        )
        with tempfile.TemporaryDirectory() as directory:
            destination = admit_simulated_closure(bundle, Path(directory))
            replay = admit_simulated_closure(bundle, Path(directory))
            self.assertEqual(destination, replay)
            changed = deepcopy(bundle)
            changed["detailed_receipts"][0]["claim_scope"] = (
                "A changed future claim"
            )
            with self.assertRaisesRegex(
                SimulatedClosureError,
                "canonical content|immutable",
            ):
                admit_simulated_closure(changed, Path(directory))

    def test_pair_comparison_classifies_material_differences(self) -> None:
        report = compare(
            ObservationEnvelope.from_dict(load("fixtures/pairs/simulation-observation.json")),
            ObservationEnvelope.from_dict(load("fixtures/pairs/actual-observation.json")),
            load("specification/comparison-profile.json"),
        )
        classifications = {item["classification"] for item in report["differences"]}
        self.assertEqual(classifications, {"desired_divergence", "actual_gap"})
        self.assertEqual(report["summary"]["critical_differences"], 0)
        recovery = next(
            item
            for item in report["differences"]
            if item["path"] == "$.restore.observed_recovery_seconds"
        )
        self.assertEqual(recovery["comparison"]["outcome"], "favorable")
        self.assertEqual(recovery["comparison"]["delta"], -31)
        self.assertEqual(
            report["simulation"]["simulation_commit"],
            TRUSTED_SOURCE_COORDINATES[0]["commit"],
        )
        self.assertEqual(
            report["simulation"]["implementation_commit"],
            TRUSTED_SOURCE_COORDINATES[1]["commit"],
        )

    def test_missing_required_path_is_a_critical_specification_violation(self) -> None:
        simulation_value = load("fixtures/pairs/simulation-observation.json")
        actual_value = load("fixtures/pairs/actual-observation.json")
        del simulation_value["result"]["security"]["tenant_boundary"]
        del actual_value["result"]["security"]["tenant_boundary"]
        report = compare(
            ObservationEnvelope.from_dict(simulation_value),
            ObservationEnvelope.from_dict(actual_value),
            load("specification/comparison-profile.json"),
        )
        difference = next(
            item
            for item in report["differences"]
            if item["path"] == "$.security.tenant_boundary"
        )
        self.assertEqual(
            difference["classification"],
            "shared_specification_violation",
        )
        self.assertTrue(difference["critical"])
        self.assertEqual(report["summary"]["critical_differences"], 1)

    def test_directional_adjudication_distinguishes_slower_recovery(self) -> None:
        actual_value = load("fixtures/pairs/actual-observation.json")
        actual_value["result"]["restore"]["observed_recovery_seconds"] = 1000
        report = compare(
            ObservationEnvelope.from_dict(
                load("fixtures/pairs/simulation-observation.json")
            ),
            ObservationEnvelope.from_dict(actual_value),
            load("specification/comparison-profile.json"),
        )
        recovery = next(
            item
            for item in report["differences"]
            if item["path"] == "$.restore.observed_recovery_seconds"
        )
        self.assertEqual(recovery["classification"], "actual_gap")
        self.assertEqual(recovery["comparison"]["outcome"], "unfavorable")
        self.assertIn("slower", recovery["rationale"])

    def test_declared_nondeterminism_converges(self) -> None:
        report = compare(
            ObservationEnvelope.from_dict(load("fixtures/pairs/simulation-observation.json")),
            ObservationEnvelope.from_dict(load("fixtures/pairs/actual-observation.json")),
            load("specification/comparison-profile.json"),
        )
        paths = {item["path"] for item in report["differences"]}
        self.assertNotIn("$.execution.completed_at", paths)
        self.assertNotIn("$.execution.trace_id", paths)

    def test_html_contains_portable_adjudication_surface(self) -> None:
        report = compare(
            ObservationEnvelope.from_dict(load("fixtures/pairs/simulation-observation.json")),
            ObservationEnvelope.from_dict(load("fixtures/pairs/actual-observation.json")),
            load("specification/comparison-profile.json"),
        )
        html = render_html(report)
        self.assertIn("<!doctype html>", html)
        self.assertIn("actual_gap", html)
        self.assertIn(report["report_digest"], html)

    def test_report_values_require_explicit_profile_visibility(self) -> None:
        profile = load("specification/comparison-profile.json")
        profile["reportable_paths"] = []
        report = compare(
            ObservationEnvelope.from_dict(load("fixtures/pairs/simulation-observation.json")),
            ObservationEnvelope.from_dict(load("fixtures/pairs/actual-observation.json")),
            profile,
        )
        self.assertTrue(
            all(item["value_visibility"] == "digest_only" for item in report["differences"])
        )
        self.assertTrue(
            all(
                item["actual"]["classification"] == "redacted-comparison-value"
                for item in report["differences"]
            )
        )

    def test_simulated_evidence_returns_to_observation_path(self) -> None:
        envelope = ObservationEnvelope.from_dict(load("fixtures/pairs/simulation-observation.json"))
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(AdmissionError, "named environment"):
                admit(envelope, Path(directory))

    def test_observed_qualified_evidence_enters_accepted_namespace(self) -> None:
        envelope = ObservationEnvelope.from_dict(load("fixtures/pairs/actual-observation.json"))
        with tempfile.TemporaryDirectory() as directory:
            destination = admit(envelope, Path(directory))
            admitted = json.loads(destination.read_text())
            self.assertTrue(admitted["accepted_namespace"])
            self.assertEqual(admitted["evidence_mode"], "observed")
            self.assertEqual(destination.stat().st_mode & 0o777, 0o600)

    def test_observed_prequalification_evidence_returns_to_review(self) -> None:
        value = load("fixtures/pairs/actual-observation.json")
        for stage in ("specified", "verified"):
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as directory:
                value["assurance_stage"] = stage
                with self.assertRaisesRegex(AdmissionError, "qualified"):
                    admit(
                        ObservationEnvelope.from_dict(value),
                        Path(directory),
                    )

    def test_accepted_manifest_is_immutable_and_supports_supersession(self) -> None:
        envelope = ObservationEnvelope.from_dict(load("fixtures/pairs/actual-observation.json"))
        with tempfile.TemporaryDirectory() as directory:
            destination = admit(envelope, Path(directory))
            existing = json.loads(destination.read_text())
            existing["result"]["specimen"]["revision"] = 99
            destination.write_text(json.dumps(existing))
            with self.assertRaisesRegex(AdmissionError, "superseding observation"):
                admit(envelope, Path(directory))

    def test_acceptance_requires_separate_accountable_domains(self) -> None:
        value = load("fixtures/acceptance/observed-accepted-example.json")
        value["approvals"] = value["approvals"][:1]
        envelope = ObservationEnvelope.from_dict(value)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(AdmissionError, "quality, regulatory"):
                admit(envelope, Path(directory))

    def test_acceptance_example_enters_with_three_accountable_decisions(self) -> None:
        envelope = ObservationEnvelope.from_dict(
            load("fixtures/acceptance/observed-accepted-example.json")
        )
        with tempfile.TemporaryDirectory() as directory:
            destination = admit(envelope, Path(directory))
            admitted = json.loads(destination.read_text())
            self.assertEqual(len(admitted["approvals"]), 3)

    def test_admission_confines_repository_safe_identity(self) -> None:
        value = load("fixtures/pairs/actual-observation.json")
        value["observation_id"] = "../ESCAPED"
        envelope = ObservationEnvelope.from_dict(value)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(AdmissionError, "repository-safe identity"):
                admit(envelope, Path(directory) / "accepted")
            self.assertEqual(list(Path(directory).glob("*.json")), [])

    def test_admission_returns_protected_keys_to_governed_projection(self) -> None:
        value = load("fixtures/pairs/actual-observation.json")
        value["result"]["api_key"] = "SYNTHETIC-CREDENTIAL-SHAPE"
        envelope = ObservationEnvelope.from_dict(value)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(AdmissionError, "protected content"):
                admit(envelope, Path(directory))

    def test_admission_requires_exact_provenance_identities(self) -> None:
        cases = (
            ("implementation_commit", "latest", "immutable"),
            ("configuration_digest", "sha256:", "64 lowercase"),
            ("raw_artifact_digest", "sha256:example", "64 lowercase"),
            (
                "governed_locator",
                "https://user:" + "password@example.invalid/evidence",
                "protected-storage",
            ),
        )
        for field, value, message in cases:
            with self.subTest(field=field):
                document = load("fixtures/pairs/actual-observation.json")
                target = document["source"] if field in document["source"] else document["provenance"]
                target[field] = value
                with tempfile.TemporaryDirectory() as directory:
                    with self.assertRaisesRegex(AdmissionError, message):
                        admit(ObservationEnvelope.from_dict(document), Path(directory))

    def test_locator_requires_a_plain_protected_object_path(self) -> None:
        for locator in (
            "s3://evidence-bucket",
            "evidence-vault://acceptance/%0Aobject",
        ):
            with self.subTest(locator=locator):
                value = load("fixtures/pairs/actual-observation.json")
                value["provenance"]["governed_locator"] = locator
                with tempfile.TemporaryDirectory() as directory:
                    with self.assertRaisesRegex(AdmissionError, "object path"):
                        admit(ObservationEnvelope.from_dict(value), Path(directory))

    def test_reviewer_independence_uses_normalized_identity(self) -> None:
        value = load("fixtures/pairs/actual-observation.json")
        value["provenance"]["performed_by"] = "Validation-Operator"
        value["provenance"]["reviewed_by"] = " validation-operator "
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(AdmissionError, "independent review"):
                admit(ObservationEnvelope.from_dict(value), Path(directory))

    def test_comparison_binds_authority_and_profile(self) -> None:
        simulation = ObservationEnvelope.from_dict(
            load("fixtures/pairs/simulation-observation.json")
        )
        actual = ObservationEnvelope.from_dict(load("fixtures/pairs/actual-observation.json"))
        profile = load("specification/comparison-profile.json")

        with self.assertRaisesRegex(ValueError, "simulated evidence"):
            compare(replace(simulation, evidence_mode="observed"), actual, profile)

        changed_profile = deepcopy(profile)
        changed_profile["scenario_id"] = "SPEC-OTHER-001"
        with self.assertRaisesRegex(ValueError, "paired scenario_id"):
            compare(simulation, actual, changed_profile)

        changed_profile = deepcopy(profile)
        changed_profile["declared_nondeterminism"].append("$.specimen.status")
        with self.assertRaisesRegex(ValueError, "deterministic comparison"):
            compare(simulation, actual, changed_profile)

        changed_profile = deepcopy(profile)
        changed_profile["numeric_tolerances"]["$.specimen.revision"] = {"absolute": 1}
        with self.assertRaisesRegex(ValueError, "exact comparison"):
            compare(simulation, actual, changed_profile)

        changed_profile = deepcopy(profile)
        changed_profile["unreleased_extension"] = True
        with self.assertRaisesRegex(ValueError, "unreleased"):
            compare(simulation, actual, changed_profile)

        changed_simulation = deepcopy(
            load("fixtures/pairs/simulation-observation.json")
        )
        changed_simulation["source"]["governance_closure_digest"] = (
            "sha256:" + "0" * 64
        )
        with self.assertRaisesRegex(ValueError, "trusted selected-future"):
            compare(
                ObservationEnvelope.from_dict(changed_simulation),
                actual,
                profile,
            )
        for field in ("simulation_commit", "implementation_commit"):
            with self.subTest(field=field):
                changed_simulation = deepcopy(
                    load("fixtures/pairs/simulation-observation.json")
                )
                changed_simulation["source"][field] = "0" * 40
                with self.assertRaisesRegex(
                    ValueError,
                    f"simulation source {field} differs",
                ):
                    compare(
                        ObservationEnvelope.from_dict(changed_simulation),
                        actual,
                        profile,
                    )

    def test_json_ingress_rejects_duplicate_and_nonfinite_values(self) -> None:
        examples = (
            ('{"scenario_id":"A","scenario_id":"B"}', "single definition"),
            ('{"value":Infinity}', "finite representation"),
        )
        for content, message in examples:
            with self.subTest(message=message), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "envelope.json"
                path.write_text(content, encoding="utf-8")
                with self.assertRaisesRegex(ValueError, message):
                    _load(path)

    def test_repository_release_binds_role_and_contracts(self) -> None:
        manifest = load("release/repository-role.json")
        bundle = load(
            "fixtures/simulated-closures/future-reality-2028-06-30-v1.json"
        )
        closure_summary = validate_simulated_closure_bundle(bundle)
        machine_node = load("machine-node.json")
        first_receipt = load("first-receipt.json")
        coordination_horizon = load("COORDINATION-HORIZON.json")
        self.assertEqual(__version__, "0.3.1")
        self.assertEqual(manifest["repository_release"], __version__)
        self.assertEqual(manifest["repository_role"], "comparative_evidence")
        self.assertEqual(manifest["contract_bindings"]["governance_schema"], "2.0.1")
        self.assertEqual(
            manifest["contract_bindings"]["simulated_closure_bundle_schema"],
            "2.0.1",
        )
        self.assertEqual(
            manifest["canonical_governance_closure_digest"],
            closure_summary["governance_closure_digest"],
        )
        self.assertEqual(
            manifest["source_result_digest"],
            closure_summary["source_result_digest"],
        )
        self.assertEqual(
            manifest["canonical_closure_bundle_digest"],
            digest(bundle),
        )
        bundle_path = (
            ROOT
            / "fixtures/simulated-closures/future-reality-2028-06-30-v1.json"
        )
        self.assertEqual(
            manifest["canonical_closure_bundle_file_sha256"],
            f"sha256:{sha256(bundle_path.read_bytes()).hexdigest()}",
        )
        self.assertEqual(
            manifest["contract_bindings"]["comparison_profile_schema"],
            "1.1.0",
        )
        self.assertEqual(
            manifest["contract_bindings"]["observation_envelope_schema"],
            "1.1.0",
        )
        self.assertEqual(
            manifest["contract_bindings"]["calibration_ledger_schema"],
            "1.0.0",
        )
        trusted_binding = manifest["trusted_simulated_closure"]
        self.assertEqual(trusted_binding["closure_id"], TRUSTED_CLOSURE_ID)
        self.assertEqual(
            trusted_binding["future_reality_version"],
            TRUSTED_FUTURE_REALITY_VERSION,
        )
        self.assertEqual(
            trusted_binding["future_reality_id"],
            TRUSTED_FUTURE_REALITY_ID,
        )
        self.assertEqual(
            trusted_binding["governance_closure_digest"],
            TRUSTED_GOVERNANCE_CLOSURE_DIGEST,
        )
        self.assertEqual(
            trusted_binding["source_coordinates"],
            list(TRUSTED_SOURCE_COORDINATES),
        )
        self.assertEqual(
            manifest["simulated_closure_comparison_digest"],
            closure_summary["comparison_digest"],
        )
        self.assertEqual(
            manifest["aggregate_closure_artifact_digest"],
            closure_summary["aggregate_artifact_digest"],
        )
        self.assertEqual(machine_node["authority"]["mode"], "orientation_only")
        self.assertEqual(
            first_receipt["authority_posture"]["mode"],
            "orientation_only",
        )
        self.assertEqual(
            machine_node["coordination_horizon_id"],
            coordination_horizon["horizon_id"],
        )
        self.assertEqual(
            first_receipt["coordination_horizon_id"],
            coordination_horizon["horizon_id"],
        )
        closure_contracts = {
            item["digest"]
            for item in machine_node["contracts"]
            if item["contract_id"] == "CONTRACT-SIMULATED-CLOSURE-001"
        }
        self.assertEqual(
            closure_contracts,
            {closure_summary["governance_closure_digest"]},
        )
        self.assertEqual(
            {
                item["digest"]
                for item in first_receipt["contract_state"]
                if item["contract_id"] == "CONTRACT-SIMULATED-CLOSURE-001"
            },
            closure_contracts,
        )
        self.assertEqual(
            machine_node["current_provenance"],
            {
                "release": "candidate-comparison-v0.3.1",
                "commit": "0" * 40,
                "digest": "sha256:" + ("0" * 64),
            },
        )
        self.assertEqual(machine_node["lifecycle_state"], "settling")
        self.assertEqual(
            {
                (item["campaign_id"], item["marking_schema_version"])
                for item in machine_node["campaigns"]
            },
            {
                ("LIMS-ELN-OPEN-RECEIPTS", "2.0.1"),
                ("COMPARATIVE-LITERACY-COLLABORATION", "2.0.1"),
                ("SITE-READING-SYSTEM", "2.0.1"),
            },
        )
        self.assertEqual(
            machine_node["open_receipts"],
            ["RCP-COMPARATIVE-PROMOTION-003"],
        )
        self.assertEqual(
            first_receipt["open_receipts"],
            machine_node["open_receipts"],
        )
        promotion_items = {
            item["item_id"]: item
            for item in coordination_horizon["work_items"]
            if "promotion" in item["horizon_label"].lower()
        }
        self.assertEqual(
            coordination_horizon["current_item_ids"],
            ["WORK-COMPARATIVE-PROMOTION-003"],
        )
        self.assertEqual(
            promotion_items["WORK-COMPARATIVE-PROMOTION-003"]["state"],
            "settling",
        )
        self.assertEqual(
            manifest["promotion_coordinates"]["open_receipt_id"],
            machine_node["open_receipts"][0],
        )
        vocabulary_binding = manifest["external_contract_bindings"][
            "receipt_family_vocabulary_map"
        ]
        self.assertEqual(
            vocabulary_binding["contract_id"],
            "RECEIPT-VOCABULARY-MAP-001",
        )
        self.assertEqual(vocabulary_binding["version"], "1.0.0")
        self.assertEqual(
            vocabulary_binding["authority"],
            "driftframestudios/lims-eln-program-specification",
        )
        self.assertEqual(
            vocabulary_binding["coordinate_kind"],
            "external_repository_path",
        )
        self.assertEqual(
            vocabulary_binding["path"],
            "specifications/receipt-vocabulary-map.v1.json",
        )
        self.assertEqual(
            vocabulary_binding["digest"],
            "sha256:0f3be9ab956877281f9261c69a5f099547b048c1c878541a7c9c47edc5e03280",
        )
        report = compare(
            ObservationEnvelope.from_dict(load("fixtures/pairs/simulation-observation.json")),
            ObservationEnvelope.from_dict(load("fixtures/pairs/actual-observation.json")),
            load("specification/comparison-profile.json"),
        )
        self.assertEqual(manifest["reference_report_digest"], report["report_digest"])
        self.assertEqual(
            {
                item["external_release"]
                for item in manifest["historical_external_releases"]
            },
            {"comparison-v0.1.0", "comparison-v0.2.0"},
        )

    def test_redacted_receipt_uses_canonical_family_vocabulary(self) -> None:
        receipt = load("receipts/redacted/qualified-vendor-example.json")
        schema = load("schemas/redacted-receipt.schema.json")
        canonical_families = set(schema["properties"]["receipt_family"]["enum"])
        self.assertEqual(
            canonical_families,
            {
                "configured_vendor_environments",
                "representative_migration_restore_rehearsals",
                "production_security_observability",
                "accountable_scientific_quality_regulatory_acceptance",
            },
        )
        self.assertIn(receipt["receipt_family"], canonical_families)
        self.assertEqual(
            receipt["receipt_family"],
            "configured_vendor_environments",
        )


if __name__ == "__main__":
    unittest.main()
