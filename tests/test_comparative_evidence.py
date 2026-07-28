from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from comparative_evidence.compare import compare
from comparative_evidence.cli import _load
from comparative_evidence import __version__
from comparative_evidence.gate import AdmissionError, admit
from comparative_evidence.model import ObservationEnvelope
from comparative_evidence.report import render_html


def load(path: str) -> dict:
    return json.loads((ROOT / path).read_text())


class ComparativeEvidenceTests(unittest.TestCase):
    def test_pair_comparison_classifies_material_differences(self) -> None:
        report = compare(
            ObservationEnvelope.from_dict(load("fixtures/pairs/simulation-observation.json")),
            ObservationEnvelope.from_dict(load("fixtures/pairs/actual-observation.json")),
            load("specification/comparison-profile.json"),
        )
        classifications = {item["classification"] for item in report["differences"]}
        self.assertEqual(classifications, {"desired_divergence", "actual_gap"})
        self.assertEqual(report["summary"]["critical_differences"], 0)

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
        self.assertEqual(__version__, "0.2.0")
        self.assertEqual(manifest["repository_release"], __version__)
        self.assertEqual(manifest["repository_role"], "comparative_evidence")
        self.assertEqual(manifest["contract_bindings"]["governance_schema"], "1.0.0")
        report = compare(
            ObservationEnvelope.from_dict(load("fixtures/pairs/simulation-observation.json")),
            ObservationEnvelope.from_dict(load("fixtures/pairs/actual-observation.json")),
            load("specification/comparison-profile.json"),
        )
        self.assertEqual(manifest["reference_report_digest"], report["report_digest"])
        self.assertEqual(
            manifest["historical_external_releases"][0]["external_release"],
            "comparison-v0.1.0",
        )


if __name__ == "__main__":
    unittest.main()
