from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from comparative_evidence.artifact_boundary import (
    ReportArtifactError,
    verify_reproducible_reports,
)
from comparative_evidence.calibration import CalibrationError, score_calibration
from comparative_evidence.compare import compare, compare_synthetic_contract
from comparative_evidence.database_release import (
    TRUSTED_SIMULATED_DATABASE_RELEASE,
)
from comparative_evidence.cli import _load
from comparative_evidence import __version__
from comparative_evidence.gate import AdmissionError, admit
from comparative_evidence.model import ObservationEnvelope, canonical_json, digest
from comparative_evidence.report import render_html, write_reports
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
from validate_repository import validate_json_contract


def load(path: str) -> dict:
    return json.loads((ROOT / path).read_text())


def planned_contract_value() -> dict:
    return load("fixtures/contracts/planned-observation.json")


def observed_envelope_value() -> dict:
    """Create qualified observed evidence inside the test boundary."""

    value = planned_contract_value()
    value.update(
        {
            "observation_id": "OBS-TEST-GOLDEN-001",
            "evidence_mode": "observed",
            "assurance_stage": "qualified",
        }
    )
    value["source"].update(
        {
            "environment_id": "test-qualification-environment",
            "implementation_commit": "a" * 40,
            "configuration_digest": "sha256:" + "b" * 64,
        }
    )
    value["source"]["database_release"] = (
        TRUSTED_SIMULATED_DATABASE_RELEASE.as_dict()
    )
    value["source"]["database_release"].update(
        {
            "migration_manifest_id": "IMPLEMENTATION-DATABASE-MIGRATIONS-TEST-001",
            "migration_manifest_digest": "sha256:" + "c" * 64,
            "migration_receipt_id": "RECEIPT-DATABASE-MIGRATION-TEST-001",
            "migration_receipt_digest": "sha256:" + "d" * 64,
            "release_receipt_id": "RECEIPT-DATABASE-RELEASE-TEST-001",
            "release_receipt_digest": "sha256:" + "e" * 64,
        }
    )
    value["provenance"] = {
        "raw_artifact_digest": "sha256:" + "f" * 64,
        "governed_locator": "evidence-vault://qualification/OBS-TEST-GOLDEN-001",
        "performed_by": "test-qualification-operator",
        "reviewed_by": "test-independent-reviewer",
    }
    value["approvals"] = [
        {
            "domain": "engineering",
            "decision": "accept",
            "approver": "test-engineering-owner",
        }
    ]
    value["classification"] = {
        "data_class": "approved-synthetic-qualification",
        "redaction_status": "reviewed-redacted-manifest",
    }
    return value


def accepted_envelope_value() -> dict:
    """Create accountable acceptance evidence inside the test boundary."""

    value = load("fixtures/contracts/planned-acceptance-envelope.json")
    value.update(
        {
            "observation_id": "OBS-TEST-ACCEPTANCE-001",
            "evidence_mode": "observed",
            "assurance_stage": "accepted",
        }
    )
    observed_source = observed_envelope_value()["source"]
    value["source"] = deepcopy(observed_source)
    value["result"] = {
        "intended_use": "bounded generated test",
        "scientific_fitness": "accepted",
        "quality_disposition": "accepted",
        "regulatory_applicability": "accepted_for_named_test_scope",
    }
    value["provenance"] = {
        "raw_artifact_digest": "sha256:" + "1" * 64,
        "governed_locator": "evidence-vault://acceptance/OBS-TEST-ACCEPTANCE-001",
        "performed_by": "test-validation-operator",
        "reviewed_by": "test-independent-validation-reviewer",
    }
    value["approvals"] = [
        {
            "domain": domain,
            "decision": "accept",
            "approver": f"test-{domain}-owner",
        }
        for domain in ("scientific", "quality", "regulatory")
    ]
    value["classification"] = {
        "data_class": "approved-synthetic-exemplar",
        "redaction_status": "reviewed-redacted-manifest",
    }
    return value


class ComparativeEvidenceTests(unittest.TestCase):
    def test_released_comparison_profile_executes_its_bound_schema(self) -> None:
        schema = load("schemas/comparison-profile.schema.json")
        profile = load("specification/comparison-profile.json")
        expected_version = load("release/repository-role.json")[
            "contract_bindings"
        ]["comparison_profile_schema"]

        validate_json_contract(
            schema=schema,
            instance=profile,
            version_property="profile_version",
            expected_version=expected_version,
            contract_name="comparison profile",
        )

        stale_instance = deepcopy(profile)
        stale_instance["profile_version"] = "1.1.0"
        with self.assertRaisesRegex(ValueError, "schema conformance"):
            validate_json_contract(
                schema=schema,
                instance=stale_instance,
                version_property="profile_version",
                expected_version=expected_version,
                contract_name="comparison profile",
            )

        stale_schema = deepcopy(schema)
        stale_schema["properties"]["profile_version"]["const"] = "1.1.0"
        with self.assertRaisesRegex(ValueError, "release binding"):
            validate_json_contract(
                schema=stale_schema,
                instance=profile,
                version_property="profile_version",
                expected_version=expected_version,
                contract_name="comparison profile",
            )

    def test_released_observation_envelopes_execute_their_bound_schema(
        self,
    ) -> None:
        schema = load("schemas/observation-envelope.schema.json")
        manifest = load("release/repository-role.json")
        expected_version = manifest["contract_bindings"][
            "observation_envelope_schema"
        ]
        observations = (
            load("fixtures/pairs/simulation-observation.json"),
            planned_contract_value(),
            load("fixtures/contracts/planned-acceptance-envelope.json"),
        )

        for observation in observations:
            validate_json_contract(
                schema=schema,
                instance=observation,
                version_property="envelope_version",
                expected_version=expected_version,
                contract_name="observation envelope",
            )

        stale_instance = deepcopy(observations[0])
        stale_instance["envelope_version"] = "1.1.0"
        with self.assertRaisesRegex(ValueError, "schema conformance"):
            validate_json_contract(
                schema=schema,
                instance=stale_instance,
                version_property="envelope_version",
                expected_version=expected_version,
                contract_name="observation envelope",
            )

        stale_schema = deepcopy(schema)
        stale_schema["properties"]["envelope_version"]["const"] = "1.1.0"
        with self.assertRaisesRegex(ValueError, "release binding"):
            validate_json_contract(
                schema=stale_schema,
                instance=observations[0],
                version_property="envelope_version",
                expected_version=expected_version,
                contract_name="observation envelope",
            )

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
            "sha256:33bcc14da24309b7716728b3f0204008e8f7ebf58de75f9e40a5986b421f06b5",
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

    def test_persisted_contract_inputs_make_no_observed_evidence_claim(self) -> None:
        claimed_modes = []
        for root in (ROOT / "fixtures", ROOT / "receipts" / "redacted"):
            for path in root.rglob("*.json"):
                document = load(str(path.relative_to(ROOT)))
                if "evidence_mode" in document:
                    claimed_modes.append((path.name, document["evidence_mode"]))
        self.assertTrue(claimed_modes)
        self.assertTrue(
            all(mode in {"planned", "simulated"} for _, mode in claimed_modes)
        )

    def test_synthetic_contract_mode_is_explicit_and_non_authorizing(self) -> None:
        simulation = ObservationEnvelope.from_dict(
            load("fixtures/pairs/simulation-observation.json")
        )
        candidate = ObservationEnvelope.from_dict(planned_contract_value())
        profile = load("specification/comparison-profile.json")

        with self.assertRaisesRegex(ValueError, "requires observed evidence"):
            compare(simulation, candidate, profile)

        report = compare_synthetic_contract(simulation, candidate, profile)
        self.assertEqual(report["comparison_mode"], "synthetic_contract")
        self.assertEqual(
            report["authority_posture"]["environment_observed_closure"],
            "separate_unasserted_state",
        )
        self.assertEqual(
            report["authority_posture"]["production_authorization_effect"],
            "none",
        )
        self.assertEqual(
            report["synthetic_contract"]["evidence_mode"], "planned"
        )
        self.assertIn(
            "planned_receipt_shapes", report["database_release_alignment"]
        )
        self.assertTrue(
            all("candidate" in item and "actual" not in item for item in report["differences"])
        )
        self.assertEqual(
            {item["classification"] for item in report["differences"]},
            {"comparison_inconclusive"},
        )
        self.assertEqual(
            {
                item["contract_exercise_classification"]
                for item in report["differences"]
            },
            {"actual_gap", "desired_divergence"},
        )
        html = render_html(report)
        self.assertIn("Synthetic contract exercise", html)
        self.assertIn("Planned contract shape", html)
        self.assertNotIn("Observed evidence comparison", html)

    def test_pair_comparison_classifies_material_differences(self) -> None:
        report = compare(
            ObservationEnvelope.from_dict(load("fixtures/pairs/simulation-observation.json")),
            ObservationEnvelope.from_dict(observed_envelope_value()),
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
        self.assertEqual(
            report["simulation"]["database_release"],
            TRUSTED_SIMULATED_DATABASE_RELEASE.as_dict(),
        )
        self.assertEqual(
            report["database_release_alignment"]["target_status"],
            "aligned_target_distinct_release_path",
        )
        self.assertTrue(
            report["database_release_alignment"]["target_state_aligned"]
        )
        self.assertFalse(
            report["database_release_alignment"]["release_path_aligned"]
        )
        self.assertFalse(
            report["database_release_alignment"]["migration_manifest_aligned"]
        )
        self.assertTrue(
            report["database_release_alignment"]["migration_mechanism_aligned"]
        )
        self.assertEqual(
            report["simulation"]["database_release"]["migration_mechanism_id"],
            "FLYWAY",
        )
        self.assertEqual(
            report["actual"]["database_release"]["migration_mechanism_id"],
            "FLYWAY",
        )
        self.assertTrue(
            report["database_release_alignment"]["schema_aligned"]
        )
        self.assertNotEqual(
            report["database_release_alignment"]["simulated_receipts"],
            report["database_release_alignment"]["observed_receipts"],
        )

    def test_boolean_and_number_are_distinct_json_primitives(self) -> None:
        actual_value = observed_envelope_value()
        actual_value["result"]["migration"]["semantic_parity"] = 1
        report = compare(
            ObservationEnvelope.from_dict(
                load("fixtures/pairs/simulation-observation.json")
            ),
            ObservationEnvelope.from_dict(actual_value),
            load("specification/comparison-profile.json"),
        )
        difference = next(
            item
            for item in report["differences"]
            if item["path"] == "$.migration.semantic_parity"
        )
        self.assertEqual(difference["classification"], "actual_defect")
        self.assertTrue(difference["critical"])

    def test_exact_release_path_alignment_preserves_distinct_receipts(self) -> None:
        simulation_value = load("fixtures/pairs/simulation-observation.json")
        actual_value = observed_envelope_value()
        release_path_fields = (
            "migration_manifest_id",
            "migration_manifest_version",
            "migration_manifest_digest",
            "migration_mechanism_id",
            "migration_mechanism_version",
            "migration_mechanism_digest",
            "migration_history_relation",
            "migration_lock_strategy",
            "migration_transaction_strategy",
        )
        for field in release_path_fields:
            actual_value["source"]["database_release"][field] = (
                simulation_value["source"]["database_release"][field]
            )
        report = compare(
            ObservationEnvelope.from_dict(simulation_value),
            ObservationEnvelope.from_dict(actual_value),
            load("specification/comparison-profile.json"),
        )
        alignment = report["database_release_alignment"]
        self.assertEqual(alignment["target_status"], "aligned_target")
        self.assertTrue(alignment["release_path_aligned"])
        self.assertNotEqual(
            alignment["simulated_receipts"], alignment["observed_receipts"]
        )

    def test_boolean_remains_outside_numeric_tolerance(self) -> None:
        actual_value = observed_envelope_value()
        actual_value["result"]["restore"]["observed_recovery_seconds"] = True
        report = compare(
            ObservationEnvelope.from_dict(
                load("fixtures/pairs/simulation-observation.json")
            ),
            ObservationEnvelope.from_dict(actual_value),
            load("specification/comparison-profile.json"),
        )
        difference = next(
            item
            for item in report["differences"]
            if item["path"] == "$.restore.observed_recovery_seconds"
        )
        self.assertEqual(
            difference["comparison"]["outcome"],
            "non_numeric",
        )

    def test_observation_envelope_is_deeply_immutable_and_detached(self) -> None:
        source_value = observed_envelope_value()
        envelope = ObservationEnvelope.from_dict(source_value)
        original_digest = envelope.content_digest

        source_value["result"]["specimen"]["status"] = "changed-at-source"
        source_value["approvals"][0]["decision"] = "revise"
        self.assertEqual(envelope.content_digest, original_digest)
        self.assertEqual(envelope.result["specimen"]["status"], "released")

        with self.assertRaises(TypeError):
            envelope.result["specimen"]["status"] = "changed-in-envelope"
        with self.assertRaises(TypeError):
            envelope.approvals[0]["decision"] = "revise"

        detached = envelope.as_dict()
        detached["source"]["database_release"]["schema_digest"] = "changed"
        detached["approvals"][0]["decision"] = "revise"
        self.assertEqual(envelope.content_digest, original_digest)

    def test_observed_admission_requires_database_release_coordinates(self) -> None:
        value = observed_envelope_value()
        del value["source"]["database_release"]
        with tempfile.TemporaryDirectory() as directory, self.assertRaisesRegex(
            AdmissionError, "database_release"
        ):
            admit(ObservationEnvelope.from_dict(value), Path(directory))

        value = observed_envelope_value()
        value["source"]["database_release"]["schema_digest"] = "sha256:short"
        with tempfile.TemporaryDirectory() as directory, self.assertRaisesRegex(
            AdmissionError, "64 lowercase"
        ):
            admit(ObservationEnvelope.from_dict(value), Path(directory))

        value = observed_envelope_value()
        del value["source"]["database_release"]["migration_mechanism_id"]
        with (
            tempfile.TemporaryDirectory(
                prefix="mechanism-coordinate-"
            ) as directory,
            self.assertRaisesRegex(
                AdmissionError, "released database coordinate fields"
            ),
        ):
            admit(ObservationEnvelope.from_dict(value), Path(directory))

        value = observed_envelope_value()
        value["source"]["database_release"]["migration_history_relation"] = (
            "unqualified_history"
        )
        with (
            tempfile.TemporaryDirectory(
                prefix="mechanism-coordinate-"
            ) as directory,
            self.assertRaisesRegex(
                AdmissionError, "qualified PostgreSQL relation"
            ),
        ):
            admit(ObservationEnvelope.from_dict(value), Path(directory))

    def test_missing_required_path_is_a_critical_specification_violation(self) -> None:
        simulation_value = load("fixtures/pairs/simulation-observation.json")
        actual_value = observed_envelope_value()
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
        actual_value = observed_envelope_value()
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
            ObservationEnvelope.from_dict(observed_envelope_value()),
            load("specification/comparison-profile.json"),
        )
        paths = {item["path"] for item in report["differences"]}
        self.assertNotIn("$.execution.completed_at", paths)
        self.assertNotIn("$.execution.trace_id", paths)

    def test_array_paths_share_one_bracketed_comparison_grammar(self) -> None:
        simulation_value = load("fixtures/pairs/simulation-observation.json")
        actual_value = observed_envelope_value()
        simulation_value["result"]["replicates"] = [
            {"value": 1.0},
            {"value": 2.0},
        ]
        actual_value["result"]["replicates"] = [
            {"value": 3.0},
            {"value": 9.0},
        ]
        profile = load("specification/comparison-profile.json")
        profile["declared_nondeterminism"].append("$.replicates[1].value")

        report = compare(
            ObservationEnvelope.from_dict(simulation_value),
            ObservationEnvelope.from_dict(actual_value),
            profile,
        )

        paths = {item["path"] for item in report["differences"]}
        self.assertIn("$.replicates[0].value", paths)
        self.assertNotIn("$.replicates[1].value", paths)
        self.assertTrue(
            all(".0" not in path and ".1" not in path for path in paths)
        )

    def test_empty_containers_remain_material_comparison_values(self) -> None:
        simulation_value = load("fixtures/pairs/simulation-observation.json")
        actual_value = observed_envelope_value()
        simulation_value["result"]["extension"] = {}

        report = compare(
            ObservationEnvelope.from_dict(simulation_value),
            ObservationEnvelope.from_dict(actual_value),
            load("specification/comparison-profile.json"),
        )

        self.assertIn(
            "$.extension",
            {item["path"] for item in report["differences"]},
        )

    def test_numeric_tolerances_preserve_boolean_meaning(self) -> None:
        simulation_value = load("fixtures/pairs/simulation-observation.json")
        actual_value = observed_envelope_value()
        simulation_value["result"]["feature_ready"] = True
        actual_value["result"]["feature_ready"] = False
        profile = load("specification/comparison-profile.json")
        profile["numeric_tolerances"]["$.feature_ready"] = {
            "absolute": 1,
            "relative": 0,
        }
        profile["required_paths"].append("$.feature_ready")

        report = compare(
            ObservationEnvelope.from_dict(simulation_value),
            ObservationEnvelope.from_dict(actual_value),
            profile,
        )

        self.assertIn(
            "$.feature_ready",
            {item["path"] for item in report["differences"]},
        )

    def test_result_keys_return_to_the_released_path_grammar(self) -> None:
        simulation_value = load("fixtures/pairs/simulation-observation.json")
        actual_value = observed_envelope_value()
        simulation_value["result"]["ambiguous.key"] = 1
        actual_value["result"]["ambiguous.key"] = 1

        with self.assertRaisesRegex(ValueError, "comparison path grammar"):
            compare(
                ObservationEnvelope.from_dict(simulation_value),
                ObservationEnvelope.from_dict(actual_value),
                load("specification/comparison-profile.json"),
            )

    def test_html_contains_portable_adjudication_surface(self) -> None:
        report = compare(
            ObservationEnvelope.from_dict(load("fixtures/pairs/simulation-observation.json")),
            ObservationEnvelope.from_dict(observed_envelope_value()),
            load("specification/comparison-profile.json"),
        )
        html = render_html(report)
        self.assertIn("<!doctype html>", html)
        self.assertIn("actual_gap", html)
        self.assertIn("Database release alignment", html)
        self.assertIn("migration mechanism", html)
        self.assertIn("aligned_target", html)
        self.assertIn(report["report_digest"], html)

    def test_html_contains_a_bounded_keyboard_and_touch_table_scroller(self) -> None:
        report = compare(
            ObservationEnvelope.from_dict(load("fixtures/pairs/simulation-observation.json")),
            ObservationEnvelope.from_dict(observed_envelope_value()),
            load("specification/comparison-profile.json"),
        )
        html = render_html(report)
        self.assertIn(
            '<div class="table-scroll" role="region" '
            'aria-labelledby="adjudication-heading" '
            'aria-describedby="adjudication-instructions" tabindex="0">',
            html,
        )
        self.assertIn(
            ".table-scroll { width:100%; max-width:100%; overflow-x:auto;",
            html,
        )
        self.assertIn("overscroll-behavior-inline:contain", html)
        self.assertIn("-webkit-overflow-scrolling:touch", html)
        self.assertIn("table { width:100%; min-width:72rem;", html)

    def test_report_values_require_explicit_profile_visibility(self) -> None:
        profile = load("specification/comparison-profile.json")
        profile["reportable_paths"] = []
        report = compare(
            ObservationEnvelope.from_dict(load("fixtures/pairs/simulation-observation.json")),
            ObservationEnvelope.from_dict(observed_envelope_value()),
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

    def test_nonreportable_values_remain_digest_bound_in_json_and_html(self) -> None:
        simulation_value = load("fixtures/pairs/simulation-observation.json")
        actual_value = observed_envelope_value()
        simulation_marker = "forecast-only-synthetic-detail"
        observed_marker = "governed-observed-detail"
        simulation_value["result"]["unlisted_detail"] = simulation_marker
        actual_value["result"]["unlisted_detail"] = observed_marker
        report = compare(
            ObservationEnvelope.from_dict(simulation_value),
            ObservationEnvelope.from_dict(actual_value),
            load("specification/comparison-profile.json"),
        )

        report_json = canonical_json(report)
        html = render_html(report)
        for protected_value in (
            simulation_marker,
            observed_marker,
            actual_value["provenance"]["governed_locator"],
        ):
            self.assertNotIn(protected_value, report_json)
            self.assertNotIn(protected_value, html)
        self.assertIn(digest(simulation_marker), report_json)
        self.assertIn(digest(observed_marker), report_json)
        self.assertEqual(
            report["actual"]["provenance_digest"],
            digest(actual_value["provenance"]),
        )

    def test_isolated_report_runs_are_byte_identical(self) -> None:
        def reference_report() -> dict:
            return compare_synthetic_contract(
                ObservationEnvelope.from_dict(
                    load("fixtures/pairs/simulation-observation.json")
                ),
                ObservationEnvelope.from_dict(planned_contract_value()),
                load("specification/comparison-profile.json"),
            )

        with (
            tempfile.TemporaryDirectory(prefix="comparison-first-") as first,
            tempfile.TemporaryDirectory(prefix="comparison-replay-") as replay,
        ):
            first_path = Path(first)
            replay_path = Path(replay)
            write_reports(reference_report(), first_path)
            write_reports(reference_report(), replay_path)
            inventory = verify_reproducible_reports(first_path, replay_path)

            self.assertEqual(
                set(inventory),
                {"comparison.json", "comparison.html"},
            )

            (replay_path / "comparison.html").write_text(
                "<!doctype html>\n<p>changed</p>\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                ReportArtifactError,
                "human-readable projection",
            ):
                verify_reproducible_reports(first_path, replay_path)

            write_reports(reference_report(), replay_path)
            (replay_path / "comparison.json").write_text(
                '{"report_digest":"one","report_digest":"two"}\n',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ReportArtifactError, "strict JSON"):
                verify_reproducible_reports(first_path, replay_path)

            for encoding in ("utf-16", "utf-32"):
                with self.subTest(encoding=encoding):
                    write_reports(reference_report(), replay_path)
                    replay_json = replay_path / "comparison.json"
                    report_text = replay_json.read_text(encoding="utf-8")
                    replay_json.write_bytes(report_text.encode(encoding))
                    with self.assertRaisesRegex(ReportArtifactError, "UTF-8"):
                        verify_reproducible_reports(first_path, replay_path)

            write_reports(reference_report(), replay_path)
            replay_json = replay_path / "comparison.json"
            replay_json.write_bytes(b"\xef\xbb\xbf" + replay_json.read_bytes())
            with self.assertRaisesRegex(ReportArtifactError, "UTF-8"):
                verify_reproducible_reports(first_path, replay_path)

            write_reports(reference_report(), replay_path)
            replay_html = replay_path / "comparison.html"
            replay_html.unlink()
            replay_html.symlink_to(first_path / "comparison.html")
            with self.assertRaisesRegex(ReportArtifactError, "regular file"):
                verify_reproducible_reports(first_path, replay_path)

            write_reports(reference_report(), replay_path)
            with (
                patch(
                    "comparative_evidence.artifact_boundary.O_NOFOLLOW",
                    None,
                ),
                self.assertRaisesRegex(ReportArtifactError, "O_NOFOLLOW"),
            ):
                verify_reproducible_reports(first_path, replay_path)

    def test_profile_rejects_noncanonical_comparison_paths(self) -> None:
        for malformed_path in (
            "$.specimen..status",
            "$.replicates[01].value",
            "$.replicates[one].value",
        ):
            with self.subTest(path=malformed_path):
                profile = load("specification/comparison-profile.json")
                profile["required_paths"].append(malformed_path)
                with self.assertRaisesRegex(
                    ValueError,
                    "released comparison path grammar",
                ):
                    compare_synthetic_contract(
                        ObservationEnvelope.from_dict(
                            load("fixtures/pairs/simulation-observation.json")
                        ),
                        ObservationEnvelope.from_dict(planned_contract_value()),
                        profile,
                    )

    def test_simulated_evidence_returns_to_observation_path(self) -> None:
        envelope = ObservationEnvelope.from_dict(load("fixtures/pairs/simulation-observation.json"))
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(AdmissionError, "named environment"):
                admit(envelope, Path(directory))

    def test_observed_qualified_evidence_enters_accepted_namespace(self) -> None:
        envelope = ObservationEnvelope.from_dict(observed_envelope_value())
        with tempfile.TemporaryDirectory() as directory:
            destination = admit(envelope, Path(directory))
            admitted = json.loads(destination.read_text())
            self.assertTrue(admitted["accepted_namespace"])
            self.assertEqual(admitted["evidence_mode"], "observed")
            self.assertEqual(destination.stat().st_mode & 0o777, 0o600)

    def test_observed_prequalification_evidence_returns_to_review(self) -> None:
        value = observed_envelope_value()
        for stage in ("specified", "verified"):
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as directory:
                value["assurance_stage"] = stage
                with self.assertRaisesRegex(AdmissionError, "qualified"):
                    admit(
                        ObservationEnvelope.from_dict(value),
                        Path(directory),
                    )

    def test_accepted_manifest_is_immutable_and_supports_supersession(self) -> None:
        envelope = ObservationEnvelope.from_dict(observed_envelope_value())
        with tempfile.TemporaryDirectory() as directory:
            destination = admit(envelope, Path(directory))
            existing = json.loads(destination.read_text())
            existing["result"]["specimen"]["revision"] = 99
            destination.write_text(json.dumps(existing))
            with self.assertRaisesRegex(AdmissionError, "superseding observation"):
                admit(envelope, Path(directory))

    def test_acceptance_requires_separate_accountable_domains(self) -> None:
        value = accepted_envelope_value()
        value["approvals"] = value["approvals"][:1]
        envelope = ObservationEnvelope.from_dict(value)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(AdmissionError, "quality, regulatory"):
                admit(envelope, Path(directory))

    def test_acceptance_example_enters_with_three_accountable_decisions(self) -> None:
        envelope = ObservationEnvelope.from_dict(
            accepted_envelope_value()
        )
        with tempfile.TemporaryDirectory() as directory:
            destination = admit(envelope, Path(directory))
            admitted = json.loads(destination.read_text())
            self.assertEqual(len(admitted["approvals"]), 3)

    def test_admission_confines_repository_safe_identity(self) -> None:
        value = observed_envelope_value()
        value["observation_id"] = "../ESCAPED"
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "released contract shape"):
                ObservationEnvelope.from_dict(value)
            self.assertEqual(list(Path(directory).glob("*.json")), [])

    def test_admission_returns_protected_keys_to_governed_projection(self) -> None:
        value = observed_envelope_value()
        value["result"]["api_key"] = "SYNTHETIC-CREDENTIAL-SHAPE"
        envelope = ObservationEnvelope.from_dict(value)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(AdmissionError, "protected content"):
                admit(envelope, Path(directory))

    def test_admission_requires_exact_provenance_identities(self) -> None:
        cases = (
            ("implementation_commit", "latest", "observed implementation_commit"),
            ("configuration_digest", "sha256:", "configuration_digest"),
            ("raw_artifact_digest", "sha256:example", "raw_artifact_digest"),
            (
                "governed_locator",
                "https://user:" + "password@example.invalid/evidence",
                "observed governed_locator",
            ),
        )
        for field, value, message in cases:
            with self.subTest(field=field):
                document = observed_envelope_value()
                target = document["source"] if field in document["source"] else document["provenance"]
                target[field] = value
                with self.assertRaisesRegex(ValueError, message):
                    ObservationEnvelope.from_dict(document)

    def test_locator_requires_a_plain_protected_object_path(self) -> None:
        for locator in (
            "s3://evidence-bucket",
            "evidence-vault://acceptance/%0Aobject",
        ):
            with self.subTest(locator=locator):
                value = observed_envelope_value()
                value["provenance"]["governed_locator"] = locator
                with self.assertRaisesRegex(ValueError, "observed governed_locator"):
                    ObservationEnvelope.from_dict(value)

    def test_reviewer_independence_uses_normalized_identity(self) -> None:
        value = observed_envelope_value()
        value["provenance"]["performed_by"] = "Validation-Operator"
        value["provenance"]["reviewed_by"] = "validation-operator"
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(AdmissionError, "independent review"):
                admit(ObservationEnvelope.from_dict(value), Path(directory))

    def test_comparison_binds_authority_and_profile(self) -> None:
        simulation = ObservationEnvelope.from_dict(
            load("fixtures/pairs/simulation-observation.json")
        )
        actual = ObservationEnvelope.from_dict(observed_envelope_value())
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

        changed_simulation = deepcopy(
            load("fixtures/pairs/simulation-observation.json")
        )
        changed_simulation["source"]["database_release"]["schema_digest"] = (
            "sha256:" + "f" * 64
        )
        with self.assertRaisesRegex(ValueError, "trusted selected-future"):
            compare(
                ObservationEnvelope.from_dict(changed_simulation),
                actual,
                profile,
            )

    def test_json_ingress_rejects_duplicate_and_nonfinite_values(self) -> None:
        examples = (
            ('{"scenario_id":"A","scenario_id":"B"}', "single definition"),
            ('{"value":Infinity}', "finite representation"),
            ('{"value":1e400}', "finite representation"),
            ('{"value":-1e400}', "finite representation"),
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
            "1.2.0",
        )
        self.assertEqual(
            manifest["contract_bindings"]["observation_envelope_schema"],
            "1.2.0",
        )
        self.assertEqual(
            manifest["contract_bindings"]["database_release_coordinate"],
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
            manifest["trusted_simulated_database_release"],
            TRUSTED_SIMULATED_DATABASE_RELEASE.as_dict(),
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
        expected_profile_contract = {
            "contract_id": "CONTRACT-COMPARISON-PROFILE-001",
            "version": manifest["contract_bindings"][
                "comparison_profile_schema"
            ],
            "digest": manifest["comparison_profile_digest"],
        }
        self.assertIn(expected_profile_contract, machine_node["contracts"])
        self.assertIn(expected_profile_contract, first_receipt["contract_state"])
        self.assertEqual(
            manifest["first_receipt_contract"]["persisted_evidence_modes"],
            ["simulated", "planned"],
        )
        self.assertEqual(
            manifest["first_receipt_contract"]["observed_admission_status"],
            "caller_supplied_only_unexercised",
        )
        self.assertEqual(
            machine_node["current_provenance"],
            {
                "release": "comparison-v0.3.1",
                "commit": "b5c13689a32739d29437e209816bf0cd6a878976",
                "digest": "sha256:92c2d57bd9e75c650365db4b481a22a6580b201926ba1c666fcf8cb8c9311a2e",
            },
        )
        self.assertEqual(machine_node["lifecycle_state"], "reference_ready")
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
            [],
        )
        self.assertEqual(
            first_receipt["open_receipts"],
            machine_node["open_receipts"],
        )
        self.assertEqual(
            {
                machine_node["metadata"]["updated_at"],
                first_receipt["as_of"],
                first_receipt["metadata"]["updated_at"],
                coordination_horizon["as_of"],
                coordination_horizon["metadata"]["updated_at"],
            },
            {"2026-09-02T06:59:11Z"},
        )
        source_permissions = {
            item["source"]: item for item in first_receipt["source_permissions"]
        }
        publication_source = source_permissions[
            "accepted-main-observation-carrier"
        ]
        self.assertEqual(publication_source["permission"], "execute_bounded")
        self.assertGreaterEqual(len(publication_source["verification"].strip()), 40)
        self.assertEqual(
            coordination_horizon["reentry_capsule"]["next_safe_action"],
            first_receipt["handoff"]["next_safe_action"],
        )
        promotion_items = {
            item["item_id"]: item
            for item in coordination_horizon["work_items"]
            if "promotion" in item["horizon_label"].lower()
        }
        self.assertEqual(
            coordination_horizon["current_item_ids"],
            ["WORK-COMPARATIVE-PUBLICATION-017"],
        )
        self.assertEqual(
            promotion_items["WORK-COMPARATIVE-PROMOTION-003"]["state"],
            "complete",
        )
        publication_item = next(
            item
            for item in coordination_horizon["work_items"]
            if item["item_id"] == "WORK-COMPARATIVE-PUBLICATION-017"
        )
        self.assertEqual(publication_item["state"], "ready")
        self.assertGreaterEqual(len(publication_item["completion_evidence"]), 3)
        self.assertEqual(
            manifest["promotion_coordinates"]["settled_receipt_id"],
            "RCP-COMPARATIVE-PROMOTION-003",
        )
        self.assertEqual(
            manifest["publication_coordinates"]["source_coordinate_kind"],
            "first_parent_main_commit_carrying_receipt_blob",
        )
        self.assertEqual(
            manifest["publication_coordinates"]["receipt_blob_oid"],
            "4b2f41fe86fb4050d2d3f7da984baa78463c0c12",
        )
        self.assertEqual(
            manifest["publication_coordinates"]["release_subject_commit_oid"],
            machine_node["current_provenance"]["commit"],
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
        report = compare_synthetic_contract(
            ObservationEnvelope.from_dict(load("fixtures/pairs/simulation-observation.json")),
            ObservationEnvelope.from_dict(planned_contract_value()),
            load("specification/comparison-profile.json"),
        )
        self.assertEqual(
            manifest["synthetic_contract_report_digest"],
            report["report_digest"],
        )
        self.assertEqual(
            {
                item["external_release"]
                for item in manifest["historical_external_releases"]
            },
            {"comparison-v0.1.0", "comparison-v0.2.0"},
        )

    def test_redacted_receipt_uses_canonical_family_vocabulary(self) -> None:
        receipt = {
            "receipt_schema": "1.0.0",
            "receipt_id": "RECEIPT-VENDOR-TEST-001",
            "receipt_family": "configured_vendor_environments",
            "evidence_mode": "observed",
            "assurance_stage": "qualified",
            "claim": "Generated test receipt exercises the redacted contract.",
            "environment": {"environment_id": "test-vendor-environment"},
            "implementation_commit": "a" * 40,
            "scenario_ids": ["SPEC-VENDOR-TEST-001"],
            "result": "qualified_in_test_boundary",
            "raw_artifact_digest": "sha256:" + "b" * 64,
            "governed_locator": "evidence-vault://test/RECEIPT-VENDOR-TEST-001",
            "limitations": ["generated test data"],
            "performed_by": "test-operator",
            "reviewed_by": "test-independent-reviewer",
            "approvals": [
                {
                    "domain": "engineering",
                    "decision": "accept",
                    "approver": "test-platform-owner",
                }
            ],
            "classification": {
                "data_class": "approved-synthetic-qualification",
                "redaction_status": "reviewed-redacted-manifest",
            },
            "retest_triggers": ["vendor build"],
        }
        schema = load("schemas/redacted-receipt.schema.json")
        validate_json_contract(
            schema=schema,
            instance=receipt,
            version_property="receipt_schema",
            expected_version="1.0.0",
            contract_name="redacted receipt",
        )
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
