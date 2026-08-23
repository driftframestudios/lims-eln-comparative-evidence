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
    CONTRACT_DISTRIBUTION_VERSION,
    canonical_digest,
    contract_reference,
    load_contract_binding,
    load_golden_specimen_scenario,
    load_observation_schema,
    project_observation_v1,
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


class ContractV1Tests(unittest.TestCase):
    def test_bound_snapshots_retain_released_version_and_digests(self) -> None:
        binding = load_contract_binding()
        scenario = load_golden_specimen_scenario()
        schema = load_observation_schema()
        release = load("release/repository-role.json")

        self.assertEqual(binding["contract_version"], "1.0.0")
        self.assertEqual(scenario["scenario_id"], "SCN-GOLDEN-SPECIMEN-001")
        self.assertEqual(
            schema["$id"],
            "urn:driftframe:lims-eln:observation-envelope:1.0.0",
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
        pinned_distribution = (
            f"{distribution['name']}=={CONTRACT_DISTRIBUTION_VERSION}"
        )

        self.assertEqual(distribution["version"], CONTRACT_DISTRIBUTION_VERSION)
        self.assertEqual(
            project["optional-dependencies"]["contract-conformance"],
            [pinned_distribution],
        )
        self.assertEqual(
            release["external_contract_bindings"]["shared_contract_nucleus"][
                "distribution"
            ],
            pinned_distribution,
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
            defaulted = project_observation_v1(simulation_value)
            defaulted.pop("envelope_version")
            defaulted.pop("approvals")
            shared_defaults = validate_with_shared_package(defaulted)
        finally:
            sys.path.remove(str(SPECIFICATION_SOURCE))

        self.assertEqual(summary, contract_reference())
        self.assertEqual(simulation["evidence_mode"], "simulated")
        self.assertEqual(actual["evidence_mode"], "observed")
        self.assertEqual(shared_defaults["envelope_version"], "1.0.0")
        self.assertEqual(shared_defaults["approvals"], [])


if __name__ == "__main__":
    unittest.main()
