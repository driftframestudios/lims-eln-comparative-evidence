from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from comparative_evidence.compare import compare
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


if __name__ == "__main__":
    unittest.main()
