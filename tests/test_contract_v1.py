from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sys
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from comparative_evidence.compare import compare
from comparative_evidence.contract_v1 import (
    CONTRACT_ACCEPTANCE_LINEAGE_COMMIT,
    CONTRACT_DISTRIBUTION_VERSION,
    CONTRACT_DISTRIBUTION_STATE,
    CONTRACT_REQUIREMENT,
    CONTRACT_SOURCE_COMMIT,
    CONTRACT_SOURCE_IDENTITY_DIGEST,
    CONTRACT_SOURCE_TREE,
    GOLDEN_SPECIMEN_RESULT_COMPATIBILITY,
    GOLDEN_SPECIMEN_RESULT_PROJECTION_ID,
    GOLDEN_SPECIMEN_RESULT_PROJECTION_VERSION,
    GOLDEN_SPECIMEN_SCENARIO_DIGEST,
    GOLDEN_SPECIMEN_SCENARIO_VERSION,
    ContractBoundaryError,
    canonical_digest,
    contract_reference,
    load_contract_binding,
    load_golden_specimen_result_projection_schema,
    load_golden_specimen_scenario,
    load_observation_schema,
    project_observation_v1,
    validate_golden_specimen_observation,
    validate_golden_specimen_projection,
    validate_golden_specimen_with_shared_package,
    validate_observation_v1,
    validate_with_shared_package,
    verify_shared_package,
)
from comparative_evidence.database_release import TRUSTED_SIMULATED_DATABASE_RELEASE
from comparative_evidence.model import ObservationEnvelope


SPECIFICATION_SOURCE = (
    ROOT.parent / "lims-eln-program-specification" / "src"
)


def load(path: str) -> dict:
    return json.loads((ROOT / path).read_text())


def observed_envelope_value() -> dict:
    """Create qualified observed evidence inside the test boundary."""

    value = deepcopy(load("fixtures/contracts/planned-observation.json"))
    value.update(
        {
            "observation_id": "OBS-CONTRACT-GOLDEN-001",
            "evidence_mode": "observed",
            "assurance_stage": "qualified",
        }
    )
    value["source"].update(
        {
            "environment_id": "contract-qualification-environment",
            "implementation_commit": "a" * 40,
            "configuration_digest": "sha256:" + "b" * 64,
            "database_release": TRUSTED_SIMULATED_DATABASE_RELEASE.as_dict(),
        }
    )
    value["provenance"] = {
        "raw_artifact_digest": "sha256:" + "f" * 64,
        "governed_locator": "evidence-vault://qualification/OBS-CONTRACT-GOLDEN-001",
        "performed_by": "contract-qualification-operator",
        "reviewed_by": "contract-independent-reviewer",
    }
    value["approvals"] = [
        {
            "domain": "engineering",
            "decision": "accept",
            "approver": "contract-engineering-owner",
        }
    ]
    value["classification"] = {
        "data_class": "approved-synthetic-qualification",
        "redaction_status": "reviewed-redacted-manifest",
    }
    return value


def golden_specimen_observation_value() -> dict:
    """Create one standalone exact-version producer observation."""

    return {
        "envelope_version": "1.0.0",
        "observation_id": "SIM-OBS-GOLDEN-COMPARATIVE-001",
        "evidence_mode": "simulated",
        "assurance_stage": "verified",
        "scenario_id": "SCN-GOLDEN-SPECIMEN-001",
        "scenario_version": GOLDEN_SPECIMEN_SCENARIO_VERSION,
        "scenario_digest": GOLDEN_SPECIMEN_SCENARIO_DIGEST,
        "source": {
            "environment_id": "simulated-final-state",
            "implementation_commit": "forecast-2028-FR-v1",
            "configuration_digest": "sha256:" + "1" * 64,
        },
        "result": {
            "projection": {
                "projection_id": GOLDEN_SPECIMEN_RESULT_PROJECTION_ID,
                "projection_version": GOLDEN_SPECIMEN_RESULT_PROJECTION_VERSION,
                "comparison_compatibility": GOLDEN_SPECIMEN_RESULT_COMPATIBILITY,
                "tenant_id": "TENANT-SYN-GENOMICS",
                "specimen_id": "SPM-SYN-0001",
                "lifecycle": {
                    "state": "released",
                    "aggregate_version": 5,
                },
                "custody": {
                    "current_location": "SYN-LAB-A/RECEIVING",
                },
                "measurement": {
                    "analyte": "synthetic-copy-number-marker",
                    "value": 2.0,
                    "unit": "copies",
                    "quality_flag": "pass",
                },
                "review_resolution": {
                    "review_id": "REVIEW-SYN-001",
                    "decision": "accepted",
                    "resolved_at": "2026-08-17T14:35:00Z",
                },
                "release": {
                    "approval_receipt_id": "APPROVAL-SYN-QUALITY-001",
                    "released_at": "2026-08-17T14:35:00Z",
                },
            },
            "producer_detail": {
                "execution_trace_id": "SIMULATION-TRACE-001",
            },
        },
        "provenance": {
            "raw_artifact_digest": "sha256:" + "2" * 64,
            "governed_locator": (
                "simulation://forecast-2028-FR-v1/golden-specimen"
            ),
            "performed_by": "simulation-runner",
            "reviewed_by": "simulation-reviewer",
        },
        "approvals": [],
        "classification": {
            "data_class": "synthetic",
            "redaction_status": "generated-identities",
        },
    }


class ContractV1Tests(unittest.TestCase):
    def test_bound_snapshots_retain_released_version_and_digests(self) -> None:
        binding = load_contract_binding()
        scenario = load_golden_specimen_scenario()
        schema = load_observation_schema()
        projection_schema = load_golden_specimen_result_projection_schema()
        release = load("release/repository-role.json")

        self.assertEqual(binding["contract_version"], "1.0.0")
        self.assertEqual(scenario["scenario_id"], "SCN-GOLDEN-SPECIMEN-001")
        self.assertEqual(
            schema["$id"],
            "urn:driftframe:lims-eln:observation-envelope:1.0.0",
        )
        self.assertEqual(
            projection_schema["$id"],
            "urn:driftframe:lims-eln:golden-specimen-result:1.0.0",
        )
        self.assertEqual(
            binding["resources"]["golden_result_projection_schema"],
            {
                "package_path": (
                    "resources/schemas/"
                    "golden-specimen-result-projection.v1.schema.json"
                ),
                "local_path": (
                    "contract_resources/"
                    "golden-specimen-result-projection.v1.schema.json"
                ),
                "sha256": (
                    "sha256:ab2f3200045b5521b5c9da29c6f2e03a69ced3d5e8531a3107e20d06728f2696"
                ),
                "canonical_digest": (
                    "sha256:0519835a178742d52994b1342f3fdf38281b982feca9283782d45489123871fb"
                ),
            },
        )
        self.assertEqual(
            binding["resources"]["golden_result_projection_schema"][
                "canonical_digest"
            ],
            canonical_digest(projection_schema),
        )
        self.assertEqual(
            contract_reference()["golden_scenario_document_digest"],
            canonical_digest(scenario),
        )
        self.assertEqual(
            release["external_contract_bindings"]["shared_contract_nucleus"][
                "observation_schema_document_digest"
            ],
            contract_reference()["observation_schema_document_digest"],
        )
        self.assertEqual(
            release["contract_bindings"]["observation_envelope_schema"],
            "1.2.0",
        )
        self.assertEqual(schema["$id"], "urn:driftframe:lims-eln:observation-envelope:1.0.0")

    def test_shared_distribution_coordinates_remain_aligned(self) -> None:
        binding = load_contract_binding()
        release = load("release/repository-role.json")
        project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
        distribution = binding["distribution"]
        received_distribution = CONTRACT_REQUIREMENT

        self.assertEqual(distribution["version"], CONTRACT_DISTRIBUTION_VERSION)
        self.assertEqual(distribution["state"], CONTRACT_DISTRIBUTION_STATE)
        self.assertEqual(distribution["source_commit"], CONTRACT_SOURCE_COMMIT)
        self.assertEqual(distribution["source_tree"], CONTRACT_SOURCE_TREE)
        self.assertEqual(
            distribution["acceptance_lineage_commit"],
            CONTRACT_ACCEPTANCE_LINEAGE_COMMIT,
        )
        self.assertEqual(
            distribution["source_identity"]["digest"],
            CONTRACT_SOURCE_IDENTITY_DIGEST,
        )
        self.assertEqual(distribution["requirement"], CONTRACT_REQUIREMENT)
        self.assertEqual(
            project["optional-dependencies"]["contract-conformance"],
            [received_distribution],
        )
        self.assertEqual(
            release["external_contract_bindings"]["shared_contract_nucleus"][
                "distribution"
            ],
            received_distribution,
        )

        scenario_path = (
            ROOT
            / "src"
            / "comparative_evidence"
            / "contract_resources"
            / "golden-specimen.v1.json"
        )
        scenario_bytes = scenario_path.read_bytes()
        self.assertTrue(scenario_bytes.endswith(b"}\n"))
        self.assertFalse(scenario_bytes.endswith(b"}\n\n"))
        self.assertEqual(
            binding["resources"]["golden_scenario"]["sha256"],
            f"sha256:{sha256(scenario_bytes).hexdigest()}",
        )

        projection_schema_path = (
            ROOT
            / "src"
            / "comparative_evidence"
            / "contract_resources"
            / "golden-specimen-result-projection.v1.schema.json"
        )
        projection_schema_bytes = projection_schema_path.read_bytes()
        self.assertTrue(projection_schema_bytes.endswith(b"}\n"))
        self.assertEqual(
            binding["resources"]["golden_result_projection_schema"]["sha256"],
            f"sha256:{sha256(projection_schema_bytes).hexdigest()}",
        )

    def test_golden_observation_and_projection_are_strict_and_detached(self) -> None:
        original = golden_specimen_observation_value()
        validated = validate_golden_specimen_observation(original)
        projection = validate_golden_specimen_projection(
            original["result"]["projection"]
        )

        self.assertEqual(validated, original)
        self.assertEqual(projection, original["result"]["projection"])
        self.assertIsNot(validated, original)
        self.assertIsNot(projection, original["result"]["projection"])

        validated["result"]["producer_detail"]["execution_trace_id"] = "changed"
        projection["custody"]["current_location"] = "changed"
        self.assertEqual(
            original["result"]["producer_detail"]["execution_trace_id"],
            "SIMULATION-TRACE-001",
        )
        self.assertEqual(
            original["result"]["projection"]["custody"]["current_location"],
            "SYN-LAB-A/RECEIVING",
        )

        defaulted = golden_specimen_observation_value()
        del defaulted["result"]["producer_detail"]
        self.assertEqual(
            validate_golden_specimen_observation(defaulted)["result"][
                "producer_detail"
            ],
            {},
        )

    def test_golden_observation_rejects_coordinate_shape_and_chronology_drift(
        self,
    ) -> None:
        invalid_cases = []

        wrong_scenario_digest = golden_specimen_observation_value()
        wrong_scenario_digest["scenario_digest"] = "sha256:" + "0" * 64
        invalid_cases.append(
            (
                "scenario digest",
                wrong_scenario_digest,
                "released scenario model digest",
            )
        )

        wrong_projection_version = golden_specimen_observation_value()
        wrong_projection_version["result"]["projection"][
            "projection_version"
        ] = "1.1.0"
        invalid_cases.append(
            (
                "projection version",
                wrong_projection_version,
                "projection version 1.0.0",
            )
        )

        extra_projection_field = golden_specimen_observation_value()
        extra_projection_field["result"]["projection"]["display_label"] = (
            "Golden specimen"
        )
        invalid_cases.append(
            (
                "closed projection",
                extra_projection_field,
                "fields use the released contract",
            )
        )

        boolean_aggregate_version = golden_specimen_observation_value()
        boolean_aggregate_version["result"]["projection"]["lifecycle"][
            "aggregate_version"
        ] = True
        invalid_cases.append(
            (
                "boolean aggregate version",
                boolean_aggregate_version,
                "carries a positive integer",
            )
        )

        nonfinite_measurement = golden_specimen_observation_value()
        nonfinite_measurement["result"]["projection"]["measurement"][
            "value"
        ] = float("inf")
        invalid_cases.append(
            (
                "non-finite measurement",
                nonfinite_measurement,
                "carries a finite JSON number",
            )
        )

        invalid_calendar_date = golden_specimen_observation_value()
        invalid_calendar_date["result"]["projection"]["review_resolution"][
            "resolved_at"
        ] = "2026-02-30T14:35:00Z"
        invalid_cases.append(
            (
                "invalid calendar date",
                invalid_calendar_date,
                "names a valid UTC calendar instant",
            )
        )

        release_before_review = golden_specimen_observation_value()
        release_before_review["result"]["projection"]["release"][
            "released_at"
        ] = "2026-08-17T14:34:59Z"
        invalid_cases.append(
            (
                "release before review",
                release_before_review,
                "review resolution precedes release",
            )
        )

        for label, value, message in invalid_cases:
            with self.subTest(label=label):
                with self.assertRaisesRegex(ContractBoundaryError, message):
                    validate_golden_specimen_observation(value)

    def test_golden_scenario_drives_existing_comparison_slice(self) -> None:
        scenario = load_golden_specimen_scenario()
        simulation_value = load("fixtures/pairs/simulation-observation.json")
        actual_value = observed_envelope_value()
        profile = load("specification/comparison-profile.json")
        simulation = ObservationEnvelope.from_dict(simulation_value)
        actual = ObservationEnvelope.from_dict(actual_value)
        release = load("release/repository-role.json")

        self.assertEqual(
            {simulation.scenario_id, actual.scenario_id, profile["scenario_id"]},
            {scenario["scenario_id"]},
        )
        self.assertEqual(
            simulation.result["specimen"]["revision"],
            scenario["expected_state"]["aggregate_version"],
        )
        self.assertEqual(
            simulation.result["specimen"]["result"]["quality_flag"],
            scenario["expected_state"]["result"]["quality_flag"],
        )
        self.assertEqual(
            release["reference_simulation_observation_digest"],
            simulation.content_digest,
        )
        report = compare(simulation, actual, profile)
        self.assertEqual(report["observation_contract"], contract_reference())
        self.assertEqual(
            {item["classification"] for item in report["differences"]},
            {"desired_divergence", "actual_gap"},
        )

        defaulted = project_observation_v1(simulation_value)
        defaulted.pop("envelope_version")
        defaulted.pop("approvals")
        restored_defaults = validate_observation_v1(defaulted)
        self.assertEqual(restored_defaults["envelope_version"], "1.0.0")
        self.assertEqual(restored_defaults["approvals"], [])

        expanded = deepcopy(simulation_value)
        expanded["source"]["floating_revision"] = "latest"
        with self.assertRaisesRegex(ValueError, "source fields use the released contract"):
            ObservationEnvelope.from_dict(expanded)

    @unittest.skipUnless(
        SPECIFICATION_SOURCE.is_dir(),
        "authoritative sibling source is available through the focused conformance path",
    )
    def test_authoritative_package_accepts_compared_observations(self) -> None:
        sys.path.insert(0, str(SPECIFICATION_SOURCE))
        try:
            summary = verify_shared_package()
            simulation_value = load("fixtures/pairs/simulation-observation.json")
            simulation = validate_with_shared_package(simulation_value)
            actual = validate_with_shared_package(observed_envelope_value())
            golden = validate_golden_specimen_with_shared_package(
                golden_specimen_observation_value()
            )
            defaulted = project_observation_v1(simulation_value)
            defaulted.pop("envelope_version")
            defaulted.pop("approvals")
            shared_defaults = validate_with_shared_package(defaulted)
        finally:
            sys.path.remove(str(SPECIFICATION_SOURCE))

        self.assertEqual(summary, contract_reference())
        self.assertEqual(simulation["evidence_mode"], "simulated")
        self.assertEqual(actual["evidence_mode"], "observed")
        self.assertEqual(golden, golden_specimen_observation_value())
        self.assertEqual(shared_defaults["envelope_version"], "1.0.0")
        self.assertEqual(shared_defaults["approvals"], [])


if __name__ == "__main__":
    unittest.main()
