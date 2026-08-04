from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import unittest

from comparative_evidence.calibration import score_calibration
from comparative_evidence.compare import compare
from comparative_evidence.contracts import validate_document
from comparative_evidence.model import EvidenceRecord, RecordError, strict_json_loads
from comparative_evidence.report import render_html


ROOT = Path(__file__).resolve().parents[1]


def load(relative_path: str) -> dict:
    return json.loads((ROOT / relative_path).read_text(encoding="utf-8"))


def paired() -> tuple[dict, dict, dict]:
    return (
        load("fixtures/reference/golden-specimen.json"),
        load("fixtures/candidates/labkey-configured-example.json"),
        load("specification/comparison-profile.json"),
    )


class ComparativeEvidenceTests(unittest.TestCase):
    def test_released_records_and_profile_validate(self) -> None:
        reference, candidate, profile = paired()
        validate_document(reference, "evidence-record.schema.json")
        validate_document(candidate, "evidence-record.schema.json")
        validate_document(profile, "comparison-profile.schema.json")

    def test_factual_comparison_identifies_advantage_and_gaps(self) -> None:
        reference, candidate, profile = paired()
        report = compare(
            EvidenceRecord.from_dict(reference),
            EvidenceRecord.from_dict(candidate),
            profile,
        )

        by_path = {item["path"]: item for item in report["differences"]}
        self.assertEqual(
            by_path["$.restore.observed_recovery_seconds"]["classification"],
            "candidate_advantage",
        )
        self.assertEqual(
            by_path["$.event_delivery.publication_lag_seconds"]["classification"],
            "candidate_gap",
        )
        self.assertEqual(
            by_path["$.operations.manual_steps"]["classification"],
            "candidate_gap",
        )
        self.assertNotIn("$.vendor.normalized_readback_ratio", by_path)
        self.assertEqual(report["summary"]["material_differences"], 3)
        self.assertEqual(report["summary"]["critical_differences"], 0)

    def test_non_reportable_values_are_digest_only(self) -> None:
        reference, candidate, profile = paired()
        report = compare(
            EvidenceRecord.from_dict(reference),
            EvidenceRecord.from_dict(candidate),
            profile,
        )
        serialized = json.dumps(report, sort_keys=True)
        self.assertNotIn("SPM-SYN-0001", serialized)
        self.assertEqual(
            next(
                item
                for item in report["differences"]
                if item["path"] == "$.operations.manual_steps"
            )["candidate"],
            3,
        )

    def test_critical_contract_difference_is_candidate_gap(self) -> None:
        reference, candidate, profile = paired()
        candidate["result"]["migration"]["tool"] = "custom-migration-runner"
        report = compare(
            EvidenceRecord.from_dict(reference),
            EvidenceRecord.from_dict(candidate),
            profile,
        )
        difference = next(
            item for item in report["differences"] if item["path"] == "$.migration.tool"
        )
        self.assertTrue(difference["critical"])
        self.assertEqual(difference["classification"], "candidate_gap")

    def test_missing_required_measurement_stays_visible(self) -> None:
        reference, candidate, profile = paired()
        del candidate["result"]["restore"]["observed_recovery_seconds"]
        report = compare(
            EvidenceRecord.from_dict(reference),
            EvidenceRecord.from_dict(candidate),
            profile,
        )
        difference = next(
            item
            for item in report["differences"]
            if item["path"] == "$.restore.observed_recovery_seconds"
        )
        self.assertEqual(difference["classification"], "missing_measurement")
        self.assertEqual(difference["candidate"], {"state": "missing"})

    def test_boolean_and_number_remain_distinct(self) -> None:
        reference, candidate, profile = paired()
        candidate["result"]["data_contract"]["tenant_isolation"] = 1
        report = compare(
            EvidenceRecord.from_dict(reference),
            EvidenceRecord.from_dict(candidate),
            profile,
        )
        difference = next(
            item
            for item in report["differences"]
            if item["path"] == "$.data_contract.tenant_isolation"
        )
        self.assertEqual(difference["classification"], "candidate_gap")

    def test_record_detaches_from_mutable_caller_input(self) -> None:
        reference, _, _ = paired()
        record = EvidenceRecord.from_dict(reference)
        before = record.content_digest
        reference["result"]["specimen"]["status"] = "changed-after-construction"
        self.assertEqual(record.content_digest, before)
        self.assertEqual(record.result["specimen"]["status"], "released")

    def test_strict_json_rejects_duplicate_keys(self) -> None:
        with self.assertRaises(RecordError):
            strict_json_loads('{"record_id":"A","record_id":"B"}')

    def test_html_escapes_caller_supplied_labels(self) -> None:
        reference, candidate, profile = paired()
        candidate["vendor"] = "<script>alert(1)</script>"
        report = compare(
            EvidenceRecord.from_dict(reference),
            EvidenceRecord.from_dict(candidate),
            profile,
        )
        html = render_html(report)
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)

    def test_calibration_scores_only_resolved_entries(self) -> None:
        empty = load("fixtures/calibration/observed-outcomes.json")
        self.assertIsNone(score_calibration(empty)["brier_score"])

        resolved = deepcopy(empty)
        resolved["entries"] = [
            {
                "forecast_id": "FORECAST-001",
                "event": "The configured candidate preserves the specimen graph.",
                "probability": 0.8,
                "outcome": 1,
                "forecasted_at": "2026-08-01T00:00:00Z",
                "resolved_at": "2026-08-04T00:00:00Z",
                "resolution_mode": "observed",
                "resolution_evidence_digest": "sha256:" + "a" * 64,
            }
        ]
        self.assertAlmostEqual(score_calibration(resolved)["brier_score"], 0.04)


if __name__ == "__main__":
    unittest.main()
