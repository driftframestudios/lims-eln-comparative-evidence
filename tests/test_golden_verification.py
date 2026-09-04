from __future__ import annotations

from copy import deepcopy
from contextlib import redirect_stdout
from hashlib import sha256
from io import StringIO
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from comparative_evidence.contract_v1 import canonical_digest
from comparative_evidence.artifact_boundary import verify_reproducible_reports
from comparative_evidence.cli import main as cli_main
from comparative_evidence.golden_verification import (
    AGREEMENT,
    EXPLAINABLE_VARIATION,
    MATERIAL_DIVERGENCE,
    PROJECTION_PATHS,
    compare_golden_specimen,
)
from comparative_evidence.report import render_html


def implementation_projection() -> dict:
    return {
        "projection_id": "urn:driftframe:lims-eln:golden-specimen-result",
        "projection_version": "1.0.0",
        "comparison_compatibility": "exact-version",
        "tenant_id": "TENANT-SYN-GENOMICS",
        "specimen_id": "SPM-SYN-0001",
        "lifecycle": {"state": "released", "aggregate_version": 5},
        "custody": {"current_location": "SYN-LAB-A/RECEIVING"},
        "measurement": {
            "analyte": "SYNTHETIC-DNA",
            "value": 12.5,
            "unit": "ng/uL",
            "quality_flag": "pass",
        },
        "review_resolution": {
            "review_id": "RUN-SHARED-GOLDEN-001:scientific-review",
            "decision": "accepted",
            "resolved_at": "2026-08-17T14:30:00Z",
        },
        "release": {
            "approval_receipt_id": "RUN-SHARED-GOLDEN-001:quality-approval",
            "released_at": "2026-08-17T14:30:00Z",
        },
    }


def simulation_projection() -> dict:
    projection = implementation_projection()
    projection["measurement"] = {
        "analyte": "synthetic-copy-number-marker",
        "value": 2.0,
        "unit": "copies",
        "quality_flag": "pass",
    }
    projection["review_resolution"] = {
        "review_id": "REVIEW-SYN-001",
        "decision": "accepted",
        "resolved_at": "2026-08-17T14:35:00Z",
    }
    projection["release"] = {
        "approval_receipt_id": "APPROVAL-SYN-QUALITY-001",
        "released_at": "2026-08-17T14:35:00Z",
    }
    return projection


def observation(*, producer: str) -> dict:
    common = {
        "envelope_version": "1.0.0",
        "evidence_mode": "simulated",
        "scenario_id": "SCN-GOLDEN-SPECIMEN-001",
        "scenario_version": "1.0.0",
        "scenario_digest": (
            "sha256:fea95444dbbfbd3e26f5fb8d3975038541bf75bb1e4a7ffb748dd2cefdf173e9"
        ),
        "approvals": [],
    }
    if producer == "implementation":
        return {
            **common,
            "observation_id": "OBS-WORKBENCH-A33FB9285DFF11B6",
            "assurance_stage": "verified",
            "source": {
                "environment_id": "WORKBENCH-SYNTHETIC",
                "implementation_commit": (
                    "lims-eln-enterprise-implementation@0.3.2"
                ),
                "configuration_digest": "sha256:" + "4" * 64,
            },
            "result": {
                "projection": implementation_projection(),
                "producer_detail": {
                    "durable_context": "implementation-only-marker"
                },
            },
            "provenance": {
                "raw_artifact_digest": "sha256:" + "3" * 64,
                "governed_locator": (
                    "postgresql://workbench/TENANT-SYN-GENOMICS/"
                    "RUN-SHARED-GOLDEN-001"
                ),
                "performed_by": "ACTOR-SYN-TECH-01",
                "reviewed_by": "ACTOR-SYN-SCIENTIST-01",
            },
            "classification": {
                "data_class": "approved-synthetic-exemplar",
                "redaction_status": "generated-identities",
            },
        }
    if producer == "simulation":
        return {
            **common,
            "observation_id": "SIM-OBS-GOLDEN-001",
            "assurance_stage": "specified",
            "source": {
                "environment_id": "simulated-final-state",
                "implementation_commit": "forecast-2028-FR-v1",
                "configuration_digest": "sha256:" + "f" * 64,
            },
            "result": {
                "projection": simulation_projection(),
                "producer_detail": {
                    "selected_future_context": "simulation-only-marker"
                },
            },
            "provenance": {
                "raw_artifact_digest": "sha256:" + "f" * 64,
                "governed_locator": (
                    "simulation://forecast-2028-FR-v1/golden-specimen"
                ),
                "performed_by": "simulation-runner",
                "reviewed_by": "simulation-reviewer",
            },
            "classification": {
                "data_class": "synthetic",
                "redaction_status": "generated-identities",
            },
        }
    raise AssertionError(f"unknown producer {producer!r}")


def constellation() -> dict:
    return {
        "constellation_version": "0.3.2",
        "specification": {
            "package_version": "0.3.1",
            "commit": "4d06eeb7f96910311fbcb7f51547c978b6a07290",
            "digest": "git-tree-sha1:887e2c12a699105994097e4e9094270453de16ba",
            "coordinate_status": "accepted_package_source",
        },
        "governance": {
            "release": "governance-v2.1.0",
            "commit": "8469c2a6b2c7f4445523cee262b961ffe3d2523b",
            "digest": "git-tree-sha1:aed5d57120e15ceabe77d7bba700a43097200b19",
            "coordinate_status": "release_observed",
        },
        "implementation": {
            "release": "v0.3.2",
            "tag_object_oid": "c3db01079b88622f06e8714c8bcbdf0dc1803a10",
            "commit": "fe0bd2a08ac1697ce18ca583d9631faae7db7132",
            "digest": "git-tree-sha1:eb8eadb27a9e07c6069a1946f115a0083d94af5c",
            "archive_digest": (
                "sha256:0ea3db3099e3485f65d238fb2e194c6bfd9b9a90f6642431c4a96974ebcc3c16"
            ),
            "coordinate_status": "release_observed",
            "observation_digest": canonical_digest(
                observation(producer="implementation")
            ),
            "projection_digest": canonical_digest(implementation_projection()),
        },
        "simulation": {
            "release": "forecast-2028-FR-v1",
            "tag_object_oid": "73fc89690b6cc9df7a99ea495e580e7f4e2caedc",
            "commit": "37c3861b5411db8e772feedf41e4abf1fb7829bc",
            "digest": "git-tree-sha1:595ae59f25f522732577c5f8e00709f023464a6d",
            "archive_digest": (
                "sha256:c6a062a6efb6786c53dc9e7298a9dd881fcc2301d807db5cecf84663c98438e2"
            ),
            "coordinate_status": "release_observed",
            "reference_observation_digest": canonical_digest(
                observation(producer="simulation")
            ),
            "projection_digest": canonical_digest(simulation_projection()),
        },
        "comparison": {
            "release": "comparison-v0.3.1",
            "tag_object_oid": "4c29f6ca410eb4400c55ad77fc34ada2960d1972",
            "commit": "b5c13689a32739d29437e209816bf0cd6a878976",
            "digest": "git-tree-sha1:10a784b8a677ee6eb524d2860ff5ee7151d6050b",
            "archive_digest": (
                "sha256:92c2d57bd9e75c650365db4b481a22a6580b201926ba1c666fcf8cb8c9311a2e"
            ),
            "coordinate_status": "release_observed",
        },
    }


class GoldenSpecimenVerificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.profile = json.loads(
            (
                ROOT
                / "specification"
                / "golden-specimen-verification-profile.json"
            ).read_text(encoding="utf-8")
        )

    def compare(
        self,
        implementation: dict | None = None,
        simulation: dict | None = None,
        profile: dict | None = None,
        constellation_value: dict | None = None,
    ) -> dict:
        return compare_golden_specimen(
            implementation or observation(producer="implementation"),
            simulation or observation(producer="simulation"),
            profile or deepcopy(self.profile),
            constellation_value or constellation(),
        )

    def test_compares_every_closed_projection_leaf(self) -> None:
        report = self.compare()

        self.assertEqual(report["comparison_mode"], "simulated_verification")
        self.assertEqual(report["summary"]["leaf_paths_compared"], 17)
        self.assertEqual(
            report["summary"]["classification_counts"],
            {
                AGREEMENT: 10,
                EXPLAINABLE_VARIATION: 4,
                MATERIAL_DIVERGENCE: 3,
            },
        )
        self.assertEqual(
            {item["path"] for item in report["comparisons"]},
            set(PROJECTION_PATHS),
        )
        classifications = {
            item["path"]: item["classification"]
            for item in report["comparisons"]
        }
        for path in (
            "$.measurement.analyte",
            "$.measurement.value",
            "$.measurement.unit",
        ):
            self.assertEqual(classifications[path], MATERIAL_DIVERGENCE)
        for path in (
            "$.review_resolution.review_id",
            "$.review_resolution.resolved_at",
            "$.release.approval_receipt_id",
            "$.release.released_at",
        ):
            self.assertEqual(classifications[path], EXPLAINABLE_VARIATION)
        self.assertEqual(
            report["implementation"]["projection_digest"],
            canonical_digest(implementation_projection()),
        )
        self.assertEqual(
            report["simulation"]["projection_digest"],
            canonical_digest(simulation_projection()),
        )
        unsigned = deepcopy(report)
        digest = unsigned.pop("report_digest")
        self.assertEqual(digest, canonical_digest(unsigned))

    def test_producer_detail_changes_lineage_without_changing_adjudication(self) -> None:
        baseline = self.compare()
        changed_implementation = observation(producer="implementation")
        changed_implementation["result"]["producer_detail"]["new_local_fact"] = {
            "retained": True
        }
        changed_constellation = constellation()
        changed_constellation["implementation"]["observation_digest"] = (
            canonical_digest(changed_implementation)
        )

        changed = self.compare(
            implementation=changed_implementation,
            constellation_value=changed_constellation,
        )

        self.assertEqual(changed["comparisons"], baseline["comparisons"])
        self.assertEqual(changed["summary"], baseline["summary"])
        self.assertNotEqual(
            changed["implementation"]["producer_detail_digest"],
            baseline["implementation"]["producer_detail_digest"],
        )
        self.assertNotEqual(changed["report_digest"], baseline["report_digest"])
        rendered_comparisons = json.dumps(changed["comparisons"], sort_keys=True)
        self.assertNotIn("implementation-only-marker", rendered_comparisons)
        self.assertNotIn("new_local_fact", rendered_comparisons)

    def test_source_release_advance_preserves_the_compared_result(self) -> None:
        current_implementation = observation(producer="implementation")
        current_coordinate = constellation()
        current = self.compare(
            implementation=current_implementation,
            constellation_value=current_coordinate,
        )

        prior_implementation = deepcopy(current_implementation)
        prior_implementation["source"]["implementation_commit"] = (
            "lims-eln-enterprise-implementation@0.3.1"
        )
        prior_coordinate = deepcopy(current_coordinate)
        prior_coordinate["constellation_version"] = "0.3.1"
        prior_coordinate["implementation"].update(
            {
                "release": "v0.3.1",
                "tag_object_oid": "8b1013ff6a116b64e5d31c2870b574f641ee88f6",
                "commit": "44a4b8e67ff2e6af232b12daf3692bee8e8f3a3a",
                "digest": "git-tree-sha1:cc1bb335c0cdd1a37d1b6554480b3afdb9c9f360",
                "archive_digest": (
                    "sha256:00da1be41bdf23a21124d600f3788464bfd8f590c819f6a9c74b98671edb2174"
                ),
                "observation_digest": canonical_digest(prior_implementation),
            }
        )
        prior = self.compare(
            implementation=prior_implementation,
            constellation_value=prior_coordinate,
        )

        self.assertEqual(current["comparisons"], prior["comparisons"])
        self.assertEqual(current["summary"], prior["summary"])
        self.assertEqual(
            current["implementation"]["projection_digest"],
            prior["implementation"]["projection_digest"],
        )
        self.assertNotEqual(
            current["implementation"]["source_digest"],
            prior["implementation"]["source_digest"],
        )
        self.assertNotEqual(
            current["source_constellation_digest"],
            prior["source_constellation_digest"],
        )
        self.assertNotEqual(current["report_digest"], prior["report_digest"])

    def test_implementation_source_must_match_its_release_coordinate(self) -> None:
        implementation = observation(producer="implementation")
        implementation["source"]["implementation_commit"] = (
            "lims-eln-enterprise-implementation@0.3.1"
        )

        with self.assertRaisesRegex(
            ValueError,
            "implementation observation source differs from the accepted release",
        ):
            self.compare(implementation=implementation)

    def test_report_retains_source_and_accepted_coordinate_context(self) -> None:
        implementation = observation(producer="implementation")
        simulation = observation(producer="simulation")
        coordinate = constellation()

        report = self.compare(
            implementation=implementation,
            simulation=simulation,
            constellation_value=coordinate,
        )

        self.assertEqual(report["implementation"]["source"], implementation["source"])
        self.assertEqual(report["simulation"]["source"], simulation["source"])
        self.assertEqual(
            report["implementation"]["coordinate"],
            coordinate["implementation"],
        )
        self.assertEqual(
            report["simulation"]["coordinate"],
            coordinate["simulation"],
        )
        source_constellation = {
            "constellation_version": coordinate["constellation_version"],
            **{
                role: coordinate[role]
                for role in (
                    "specification",
                    "governance",
                    "implementation",
                    "simulation",
                )
            },
        }
        self.assertEqual(
            report["source_constellation_digest"],
            canonical_digest(source_constellation),
        )

    def test_receiving_coordinate_stays_outside_source_report_identity(self) -> None:
        prior = constellation()
        pending = deepcopy(prior)
        pending["comparison"] = {
            "release": "comparison-v0.3.2",
            "commit": "0" * 40,
            "digest": "git-tree-sha1:" + "0" * 40,
            "coordinate_status": "pending_release_commit",
        }
        accepted = deepcopy(pending)
        accepted["comparison"] = {
            "release": "comparison-v0.3.2",
            "commit": "a" * 40,
            "digest": "git-tree-sha1:" + "b" * 40,
            "coordinate_status": "release_observed",
        }

        prior_report = self.compare(constellation_value=prior)
        pending_report = self.compare(constellation_value=pending)
        accepted_report = self.compare(constellation_value=accepted)

        self.assertEqual(prior_report, pending_report)
        self.assertEqual(pending_report, accepted_report)

        changed_source = deepcopy(pending)
        changed_source["governance"]["commit"] = "c" * 40
        changed_source_report = self.compare(constellation_value=changed_source)
        self.assertNotEqual(
            pending_report["source_constellation_digest"],
            changed_source_report["source_constellation_digest"],
        )
        self.assertNotEqual(
            pending_report["report_digest"],
            changed_source_report["report_digest"],
        )

    def test_profile_is_exactly_the_closed_seventeen_leaf_contract(self) -> None:
        missing = deepcopy(self.profile)
        missing["comparison_paths"].pop()
        with self.assertRaisesRegex(ValueError, "exactly 17"):
            self.compare(profile=missing)

        duplicate = deepcopy(self.profile)
        duplicate["comparison_paths"][-1]["path"] = duplicate[
            "comparison_paths"
        ][-2]["path"]
        with self.assertRaisesRegex(ValueError, "each projection path once"):
            self.compare(profile=duplicate)

        agreement_as_difference = deepcopy(self.profile)
        agreement_as_difference["comparison_paths"][0][
            "divergence_classification"
        ] = AGREEMENT
        with self.assertRaisesRegex(ValueError, "variation or divergence"):
            self.compare(profile=agreement_as_difference)

        extra = deepcopy(self.profile)
        extra["comparison_paths"][0]["tolerance"] = 1
        with self.assertRaisesRegex(ValueError, "unreleased tolerance"):
            self.compare(profile=extra)

    def test_authority_postures_remain_distinct_and_simulated(self) -> None:
        planned_implementation = observation(producer="implementation")
        planned_implementation["evidence_mode"] = "planned"
        with self.assertRaisesRegex(ValueError, "implementation input requires"):
            self.compare(implementation=planned_implementation)

        verified_simulation = observation(producer="simulation")
        verified_simulation["assurance_stage"] = "verified"
        with self.assertRaisesRegex(ValueError, "simulation input requires"):
            self.compare(simulation=verified_simulation)

    def test_constellation_requires_observed_nonzero_coordinates(self) -> None:
        pending = constellation()
        pending["simulation"]["coordinate_status"] = "pending_release_commit"
        pending["simulation"]["commit"] = "0" * 40
        with self.assertRaisesRegex(ValueError, "accepted Git object"):
            self.compare(constellation_value=pending)

        changed_release = constellation()
        changed_release["simulation"]["release"] = "forecast-2028-FR-v2"
        with self.assertRaisesRegex(ValueError, "source differs"):
            self.compare(constellation_value=changed_release)

    def test_optional_constellation_instance_digests_fail_closed(self) -> None:
        implementation = observation(producer="implementation")
        simulation = observation(producer="simulation")
        coordinate = constellation()
        coordinate["implementation"]["observation_digest"] = canonical_digest(
            implementation
        )
        coordinate["simulation"]["reference_observation_digest"] = canonical_digest(
            simulation
        )
        self.compare(
            implementation=implementation,
            simulation=simulation,
            constellation_value=coordinate,
        )

        coordinate["simulation"]["reference_observation_digest"] = "sha256:" + (
            "0" * 64
        )
        with self.assertRaisesRegex(ValueError, "differs from its observation"):
            self.compare(
                implementation=implementation,
                simulation=simulation,
                constellation_value=coordinate,
            )

    def test_inputs_remain_caller_owned(self) -> None:
        implementation = observation(producer="implementation")
        simulation = observation(producer="simulation")
        profile = deepcopy(self.profile)
        coordinate = constellation()
        before = deepcopy((implementation, simulation, profile, coordinate))

        self.compare(
            implementation=implementation,
            simulation=simulation,
            profile=profile,
            constellation_value=coordinate,
        )

        self.assertEqual(
            (implementation, simulation, profile, coordinate),
            before,
        )

    def test_checked_in_inputs_bind_the_report_and_constellation(self) -> None:
        implementation_path = (
            ROOT / "fixtures/pairs/enterprise-postgresql-observation.json"
        )
        simulation_path = (
            ROOT / "fixtures/pairs/simulation-golden-specimen-observation.json"
        )
        coordinate = json.loads(
            (ROOT / "constellation.lock.json").read_text(encoding="utf-8")
        )
        implementation = json.loads(
            implementation_path.read_text(encoding="utf-8")
        )
        simulation = json.loads(simulation_path.read_text(encoding="utf-8"))

        report = compare_golden_specimen(
            implementation,
            simulation,
            deepcopy(self.profile),
            coordinate,
        )

        self.assertEqual(
            report["summary"]["classification_counts"],
            {
                AGREEMENT: 10,
                EXPLAINABLE_VARIATION: 4,
                MATERIAL_DIVERGENCE: 3,
            },
        )
        self.assertEqual(
            coordinate["implementation"]["fixture_file_sha256"],
            "sha256:" + sha256(implementation_path.read_bytes()).hexdigest(),
        )
        self.assertEqual(
            coordinate["simulation"]["fixture_file_sha256"],
            "sha256:" + sha256(simulation_path.read_bytes()).hexdigest(),
        )
        self.assertEqual(
            coordinate["implementation"]["observation_digest"],
            canonical_digest(implementation),
        )
        self.assertEqual(
            coordinate["simulation"]["reference_observation_digest"],
            canonical_digest(simulation),
        )

        html = render_html(report)
        self.assertIn("Shared-result verification", html)
        self.assertIn("Comparator-owned snapshot", html)
        self.assertIn("material_divergence", html)
        self.assertIn("MAPS EVALS DATA SHOULD NEVER APPEAR", html)
        self.assertIn("BENCHMARK DATA SHOULD NEVER APPEAR", html)
        self.assertIn(report["report_digest"], html)

    def test_cli_replay_produces_byte_identical_json_and_html(self) -> None:
        with (
            tempfile.TemporaryDirectory(prefix="golden-cli-first-") as first,
            tempfile.TemporaryDirectory(prefix="golden-cli-replay-") as replay,
        ):
            outputs = []
            for output in (first, replay):
                arguments = [
                    "lims-eln-compare",
                    "compare-simulated-verification",
                    "--profile",
                    str(
                        ROOT
                        / "specification/golden-specimen-verification-profile.json"
                    ),
                    "--implementation",
                    str(
                        ROOT
                        / "fixtures/pairs/enterprise-postgresql-observation.json"
                    ),
                    "--simulation",
                    str(
                        ROOT
                        / "fixtures/pairs/simulation-golden-specimen-observation.json"
                    ),
                    "--constellation",
                    str(ROOT / "constellation.lock.json"),
                    "--output",
                    output,
                ]
                stream = StringIO()
                with patch.object(sys, "argv", arguments), redirect_stdout(stream):
                    cli_main()
                outputs.append(json.loads(stream.getvalue()))

            self.assertEqual(outputs[0], outputs[1])
            self.assertEqual(outputs[0]["comparison_mode"], "simulated_verification")
            self.assertEqual(
                outputs[0]["summary"]["classification_counts"],
                {
                    AGREEMENT: 10,
                    EXPLAINABLE_VARIATION: 4,
                    MATERIAL_DIVERGENCE: 3,
                },
            )
            inventory = verify_reproducible_reports(Path(first), Path(replay))
            self.assertEqual(set(inventory), {"comparison.json", "comparison.html"})


if __name__ == "__main__":
    unittest.main()
