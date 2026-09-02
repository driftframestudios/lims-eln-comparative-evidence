from __future__ import annotations

from datetime import datetime
from hashlib import sha1, sha256
import json
from pathlib import Path
import sys
import tempfile

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from comparative_evidence.artifact_boundary import verify_reproducible_reports
from comparative_evidence.calibration import score_calibration
from comparative_evidence.compare import compare_synthetic_contract
from comparative_evidence.contract_v1 import (
    load_golden_specimen_result_projection_schema,
    validate_golden_specimen_observation,
)
from comparative_evidence.database_release import (
    TRUSTED_SIMULATED_DATABASE_RELEASE,
)
from comparative_evidence.model import ObservationEnvelope, digest, strict_json_loads
from comparative_evidence.golden_verification import compare_golden_specimen
from comparative_evidence.promotion_receipt import (
    canonical_digest as promotion_receipt_digest,
    file_digest as promotion_file_digest,
    validate_promotion_receipt,
)
from comparative_evidence.report import write_reports
from comparative_evidence.simulated_closure import validate_simulated_closure_bundle
from check_automation_contract import validate_automation_contract
from check_artifacts import PATTERNS
from build_pages import (
    ValidationFixtureSourceProof,
    build_projection,
    verify_reproducible_projections,
)


def _load(relative: str) -> dict:
    value = strict_json_loads((ROOT / relative).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{relative} requires a JSON object")
    return value


def _repository_json_documents() -> int:
    count = 0
    for path in sorted(ROOT.rglob("*.json")):
        if any(part in {".git", "build", "__pycache__"} for part in path.parts):
            continue
        strict_json_loads(path.read_text(encoding="utf-8"))
        count += 1
    return count


def _repository_secret_shape_findings() -> list[str]:
    findings: list[str] = []
    for path in sorted(ROOT.rglob("*")):
        if (
            not path.is_file()
            or any(part in {".git", "build", "__pycache__"} for part in path.parts)
            or path.suffix in {".pyc", ".png", ".jpg", ".jpeg", ".gif", ".pdf"}
        ):
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if any(pattern.search(content) for pattern in PATTERNS):
            findings.append(str(path.relative_to(ROOT)))
    return findings


def _persisted_environment_claims() -> list[str]:
    findings: list[str] = []
    for relative_root in ("fixtures", "receipts/redacted"):
        for path in sorted((ROOT / relative_root).rglob("*.json")):
            document = strict_json_loads(path.read_text(encoding="utf-8"))
            if isinstance(document, dict) and (
                document.get("evidence_mode") == "observed"
                or document.get("assurance_stage") == "accepted"
            ):
                findings.append(str(path.relative_to(ROOT)))
    return findings


def validate_json_contract(
    *,
    schema: dict,
    instance: dict,
    version_property: str,
    expected_version: str,
    contract_name: str,
) -> None:
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise ValueError(
            f"{contract_name} schema requires a valid Draft 2020-12 contract: "
            f"{exc.message}"
        ) from exc

    declared_version = (
        schema.get("properties", {})
        .get(version_property, {})
        .get("const")
    )
    if declared_version != expected_version:
        raise ValueError(
            f"{contract_name} schema release binding requires "
            f"{expected_version!r}; schema declares {declared_version!r}"
        )

    errors = sorted(
        Draft202012Validator(schema).iter_errors(instance),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    if errors:
        details = []
        for error in errors:
            location = "$" + "".join(
                f"[{part}]" if isinstance(part, int) else f".{part}"
                for part in error.absolute_path
            )
            details.append(f"{location}: {error.message}")
        raise ValueError(
            f"{contract_name} instance requires schema conformance: "
            + "; ".join(details)
        )


def main() -> int:
    json_count = _repository_json_documents()
    bundle_path = (
        ROOT
        / "fixtures/simulated-closures/future-reality-2028-06-30-v1.json"
    )
    bundle = _load(
        "fixtures/simulated-closures/future-reality-2028-06-30-v1.json"
    )
    bundle_summary = validate_simulated_closure_bundle(bundle)
    manifest = _load("release/repository-role.json")
    promotion_schema_path = ROOT / "schemas/promotion-receipt.schema.json"
    promotion_receipt_path = ROOT / "receipts/promotion-receipt.json"
    promotion_schema = _load("schemas/promotion-receipt.schema.json")
    promotion_receipt = _load("receipts/promotion-receipt.json")
    validate_json_contract(
        schema=promotion_schema,
        instance=promotion_receipt,
        version_property="schema_version",
        expected_version="1.0.0",
        contract_name="promotion receipt",
    )
    validate_promotion_receipt(promotion_receipt)
    expected_promotion_binding = {
        "schema_path": "schemas/promotion-receipt.schema.json",
        "schema_version": "1.0.0",
        "schema_file_sha256": promotion_file_digest(promotion_schema_path),
        "receipt_path": "receipts/promotion-receipt.json",
        "receipt_canonical_json_digest": promotion_receipt_digest(
            promotion_receipt
        ),
    }
    release_subject = promotion_receipt["release_subject"]
    if not isinstance(release_subject, dict):
        raise ValueError("observed promotion requires one immutable release subject")
    expected_release_subject = {
        "git_object_format": "sha1",
        "tag": "comparison-v0.3.1",
        "tag_object_oid": "4c29f6ca410eb4400c55ad77fc34ada2960d1972",
        "commit_oid": "b5c13689a32739d29437e209816bf0cd6a878976",
        "tree_oid": "10a784b8a677ee6eb524d2860ff5ee7151d6050b",
        "archive_format": "git-tar",
        "archive_digest": (
            "sha256:92c2d57bd9e75c650365db4b481a22a6580b201926ba1c666fcf8cb8c9311a2e"
        ),
        "promoted_at": "2026-09-02T06:27:41Z",
        "tag_signature_verification": "valid",
        "hosted_check_contexts": [
            {
                "name": "Repository validation",
                "run_id": "33597969223",
                "conclusion": "success",
            },
            {
                "name": "branch-shape",
                "run_id": "33597969333",
                "conclusion": "success",
            },
        ],
        "local_verification_signals": [
            "git rev-parse verified reviewed candidate 59d58c46d27a77150d399870ecebef2635c38dc5 and accepted commit b5c13689a32739d29437e209816bf0cd6a878976 share tree 10a784b8a677ee6eb524d2860ff5ee7151d6050b",
            "git archive --format=tar comparison-v0.3.1 reproduced sha256:92c2d57bd9e75c650365db4b481a22a6580b201926ba1c666fcf8cb8c9311a2e",
        ],
    }
    if release_subject != expected_release_subject:
        raise ValueError(
            "promotion receipt requires the reviewed comparison-v0.3.1 release evidence"
        )
    carrier_observation_time = "2026-09-02T06:59:11Z"
    publication_source_name = "accepted-main-observation-carrier"
    release_commit = release_subject["commit_oid"]
    golden_report_digest = (
        "sha256:64535e1005db533037d2d5fea434f2c750294b50258bf6c2ed23237847ff2efa"
    )
    expected_promotion_coordinates = {
        "status": "settled",
        "settled_receipt_id": promotion_receipt["promotion_receipt_id"],
        "receipt_path": "receipts/promotion-receipt.json",
        "candidate_source": promotion_receipt["candidate_source"],
        "reviewed_candidate": {
            "commit_oid": "59d58c46d27a77150d399870ecebef2635c38dc5",
            "tree_oid": release_subject["tree_oid"],
        },
        "observed_release": {
            field: release_subject[field]
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
    }
    receipt_file_bytes = (ROOT / "receipts/promotion-receipt.json").read_bytes()
    receipt_blob_header = f"blob {len(receipt_file_bytes)}\0".encode("ascii")
    expected_publication_coordinates = {
        "status": "awaiting_accepted_carrier",
        "source_coordinate_kind": (
            "first_parent_main_commit_carrying_receipt_blob"
        ),
        "accepted_branch_ref": "refs/remotes/origin/main",
        "release_subject_commit_oid": release_commit,
        "receipt_path": "receipts/promotion-receipt.json",
        "receipt_state": "release_observed",
        "receipt_blob_oid": sha1(
            receipt_blob_header + receipt_file_bytes,
            usedforsecurity=False,
        ).hexdigest(),
        "receipt_file_sha256": (
            "sha256:" + sha256(receipt_file_bytes).hexdigest()
        ),
        "publication_revision_role": "pages_source_revision",
        "projection_manifest_field": "sourceRevision",
        "receiver_issue": 17,
        "target_branch": "docs",
    }
    if manifest.get("automation_controls") != {
        "pull_request_workflow": ".github/workflows/pull-request.yml",
        "pull_request_targets": ["develop", "main"],
        "pull_request_runner": "ubuntu-24.04",
        "pull_request_python": "3.12",
        "pull_request_timeout_minutes": 10,
        "pull_request_permissions": {"contents": "read"},
        "pull_request_concurrency_cancellation": True,
        "manual_full_proof_workflow": ".github/workflows/verify.yml",
        "dependabot_configuration": ".github/dependabot.yml",
        "dependabot_target": "develop",
        "dependabot_interval": "monthly",
        "dependabot_open_pull_requests_per_ecosystem": 2,
        "dependabot_grouped_update_types": ["minor", "patch"],
        "monthly_budget_minutes": {"minimum": 100, "maximum": 300},
        "settings_state": "pending_source_acceptance_and_observed_check_name",
    }:
        raise ValueError(
            "release automation controls require the bounded hosted source contract"
        )
    validate_automation_contract(
        ROOT,
        declared_controls=manifest["automation_controls"],
    )
    profile = _load("specification/comparison-profile.json")
    profile_schema = _load("schemas/comparison-profile.schema.json")
    observation_schema = _load("schemas/observation-envelope.schema.json")
    validate_json_contract(
        schema=profile_schema,
        instance=profile,
        version_property="profile_version",
        expected_version=manifest["contract_bindings"][
            "comparison_profile_schema"
        ],
        contract_name="comparison profile",
    )
    simulation_observation = _load("fixtures/pairs/simulation-observation.json")
    planned_observation = _load("fixtures/contracts/planned-observation.json")
    planned_acceptance = _load(
        "fixtures/contracts/planned-acceptance-envelope.json"
    )
    for contract_name, observation in (
        ("simulated observation envelope", simulation_observation),
        ("planned synthetic contract envelope", planned_observation),
        ("planned acceptance contract envelope", planned_acceptance),
    ):
        validate_json_contract(
            schema=observation_schema,
            instance=observation,
            version_property="envelope_version",
            expected_version=manifest["contract_bindings"][
                "observation_envelope_schema"
            ],
            contract_name=contract_name,
        )
    golden_profile = _load(
        "specification/golden-specimen-verification-profile.json"
    )
    constellation = _load("constellation.lock.json")
    machine_node = _load("machine-node.json")
    first_receipt = _load("first-receipt.json")
    coordination_horizon = _load("COORDINATION-HORIZON.json")
    expected_comparison_coordinate = {
        "release": release_subject["tag"],
        "tag_object_oid": release_subject["tag_object_oid"],
        "commit": release_subject["commit_oid"],
        "digest": f"git-tree-sha1:{release_subject['tree_oid']}",
        "archive_digest": release_subject["archive_digest"],
        "coordinate_status": "release_observed",
        "canonical_closure_digest": manifest[
            "canonical_governance_closure_digest"
        ],
        "receipt_schema": manifest["contract_bindings"]["governance_schema"],
    }
    if constellation.get("comparison") != expected_comparison_coordinate:
        raise ValueError(
            "constellation comparison coordinate requires the observed release subject"
        )
    expected_provenance = {
        "release": release_subject["tag"],
        "commit": release_subject["commit_oid"],
        "digest": release_subject["archive_digest"],
    }
    campaign_states = {
        item["campaign_id"]: item["status"]
        for item in machine_node.get("campaigns", [])
    }
    if (
        machine_node.get("lifecycle_state") != "reference_ready"
        or machine_node.get("current_provenance") != expected_provenance
        or machine_node.get("open_receipts") != []
        or first_receipt.get("open_receipts") != []
        or campaign_states.get("LIMS-ELN-OPEN-RECEIPTS") != "active"
    ):
        raise ValueError(
            "release observation requires reference-ready provenance and one closed promotion receipt"
        )
    if datetime.fromisoformat(carrier_observation_time) <= datetime.fromisoformat(
        release_subject["promoted_at"]
    ):
        raise ValueError(
            "the observation carrier timestamp follows the signed release promotion"
        )
    if (
        machine_node.get("metadata", {}).get("updated_at")
        != carrier_observation_time
        or first_receipt.get("as_of") != carrier_observation_time
        or first_receipt.get("metadata", {}).get("updated_at")
        != carrier_observation_time
        or coordination_horizon.get("as_of") != carrier_observation_time
        or coordination_horizon.get("metadata", {}).get("updated_at")
        != carrier_observation_time
    ):
        raise ValueError(
            "control-plane carriers require one later observation timestamp"
        )
    horizon_items = {
        item["item_id"]: item
        for item in coordination_horizon.get("work_items", [])
    }
    publication_sources = [
        item
        for item in first_receipt.get("source_permissions", [])
        if isinstance(item, dict)
        and item.get("source") == publication_source_name
    ]
    publication_item = horizon_items.get("WORK-COMPARATIVE-PUBLICATION-017", {})
    reentry = coordination_horizon.get("reentry_capsule", {})
    handoff = first_receipt.get("handoff", {})
    publication_source = (
        publication_sources[0] if len(publication_sources) == 1 else {}
    )
    source_verification = (
        publication_source.get("verification", "")
    )
    next_action = reentry.get("next_safe_action", "")
    success_evidence = handoff.get("success_evidence", "")
    completion_evidence = (
        publication_item.get("completion_evidence", [])
        if isinstance(publication_item, dict)
        else []
    )

    def meaningful_text(value: object) -> bool:
        return isinstance(value, str) and len(value.strip()) >= 40

    if (
        coordination_horizon.get("current_item_ids")
        != ["WORK-COMPARATIVE-PUBLICATION-017"]
        or not meaningful_text(coordination_horizon.get("objective"))
        or horizon_items.get("WORK-COMPARATIVE-PROMOTION-003", {}).get(
            "state"
        )
        != "complete"
        or not isinstance(publication_item, dict)
        or publication_item.get("sequence") != 4
        or publication_item.get("state") != "ready"
        or publication_item.get("owner_role")
        != "Comparative evidence publication receiver"
        or publication_item.get("dependency_ids")
        != ["WORK-COMPARATIVE-PROMOTION-003"]
        or len(publication_sources) != 1
        or publication_source.get("permission") != "execute_bounded"
        or not meaningful_text(source_verification)
        or handoff.get("recipient_role") != "GitHub Pages publication receiver"
        or handoff.get("next_safe_action") != next_action
        or not meaningful_text(next_action)
        or not meaningful_text(reentry.get("current_state"))
        or not meaningful_text(reentry.get("verification"))
        or not meaningful_text(first_receipt.get("current_horizon_summary"))
        or not meaningful_text(success_evidence)
        or not isinstance(completion_evidence, list)
        or len(completion_evidence) < 3
        or any(not meaningful_text(value) for value in completion_evidence)
    ):
        raise ValueError(
            "Coordination Horizon requires the typed observation-carrier publication handoff"
        )
    implementation_golden_path = (
        ROOT / "fixtures/pairs/enterprise-postgresql-observation.json"
    )
    simulation_golden_path = (
        ROOT / "fixtures/pairs/simulation-golden-specimen-observation.json"
    )
    implementation_golden = validate_golden_specimen_observation(
        _load("fixtures/pairs/enterprise-postgresql-observation.json")
    )
    simulation_golden = validate_golden_specimen_observation(
        _load("fixtures/pairs/simulation-golden-specimen-observation.json")
    )
    golden_projection_schema = load_golden_specimen_result_projection_schema()
    for contract_name, observation in (
        ("durable Golden Specimen projection", implementation_golden),
        ("selected-future Golden Specimen projection", simulation_golden),
    ):
        validate_json_contract(
            schema=golden_projection_schema,
            instance=observation["result"]["projection"],
            version_property="projection_version",
            expected_version="1.0.0",
            contract_name=contract_name,
        )
    golden_report = compare_golden_specimen(
        implementation_golden,
        simulation_golden,
        golden_profile,
        constellation,
    )
    if golden_report.get("report_digest") != golden_report_digest:
        raise ValueError(
            "Golden report digest requires the reviewed source-constellation identity"
        )
    golden_replay_report = compare_golden_specimen(
        validate_golden_specimen_observation(
            _load("fixtures/pairs/enterprise-postgresql-observation.json")
        ),
        validate_golden_specimen_observation(
            _load("fixtures/pairs/simulation-golden-specimen-observation.json")
        ),
        _load("specification/golden-specimen-verification-profile.json"),
        _load("constellation.lock.json"),
    )
    report = compare_synthetic_contract(
        ObservationEnvelope.from_dict(simulation_observation),
        ObservationEnvelope.from_dict(planned_observation),
        profile,
    )
    replay_report = compare_synthetic_contract(
        ObservationEnvelope.from_dict(
            _load("fixtures/pairs/simulation-observation.json")
        ),
        ObservationEnvelope.from_dict(
            _load("fixtures/contracts/planned-observation.json")
        ),
        _load("specification/comparison-profile.json"),
    )
    with (
        tempfile.TemporaryDirectory(prefix="comparison-first-") as first_directory,
        tempfile.TemporaryDirectory(prefix="comparison-replay-") as replay_directory,
    ):
        first_path = Path(first_directory)
        replay_path = Path(replay_directory)
        write_reports(report, first_path)
        write_reports(replay_report, replay_path)
        report_artifact_inventory = verify_reproducible_reports(
            first_path,
            replay_path,
        )
    with (
        tempfile.TemporaryDirectory(prefix="golden-first-") as first_directory,
        tempfile.TemporaryDirectory(prefix="golden-replay-") as replay_directory,
    ):
        first_path = Path(first_directory)
        replay_path = Path(replay_directory)
        write_reports(golden_report, first_path)
        write_reports(golden_replay_report, replay_path)
        golden_report_artifact_inventory = verify_reproducible_reports(
            first_path,
            replay_path,
        )
    with (
        tempfile.TemporaryDirectory(prefix="pages-first-") as first_directory,
        tempfile.TemporaryDirectory(prefix="pages-replay-") as replay_directory,
    ):
        first_pages = Path(first_directory) / "site"
        replay_pages = Path(replay_directory) / "site"
        pages_revision = "0" * 40
        pages_source = ValidationFixtureSourceProof(pages_revision)
        build_projection(
            ROOT,
            first_pages,
            source_proof=pages_source,
        )
        build_projection(
            ROOT,
            replay_pages,
            source_proof=pages_source,
        )
        pages_inventory = verify_reproducible_projections(
            first_pages,
            replay_pages,
        )
    if report.get("comparison_mode") != "synthetic_contract" or report.get(
        "authority_posture"
    ) != {
        "evidence_claim": "synthetic_contract_shape_only",
        "environment_observed_closure": "separate_unasserted_state",
        "production_authorization_effect": "none",
    }:
        raise ValueError(
            "reference report requires the released non-authorizing synthetic "
            "contract posture"
        )
    calibration = score_calibration(
        _load("fixtures/calibration/observed-outcomes.json")
    )
    expected = {
        "synthetic_contract_report_digest": report["report_digest"],
        "canonical_governance_closure_digest": bundle_summary[
            "governance_closure_digest"
        ],
        "simulated_closure_comparison_digest": bundle_summary[
            "comparison_digest"
        ],
        "aggregate_closure_artifact_digest": bundle_summary[
            "aggregate_artifact_digest"
        ],
        "source_result_digest": bundle_summary["source_result_digest"],
        "comparison_profile_digest": digest(profile),
        "calibration_ledger_digest": calibration["ledger_digest"],
        "canonical_closure_bundle_digest": digest(bundle),
        "canonical_closure_bundle_file_sha256": (
            f"sha256:{sha256(bundle_path.read_bytes()).hexdigest()}"
        ),
        "golden_specimen_verification": {
            "profile_digest": digest(golden_profile),
            "report_digest": golden_report["report_digest"],
            "constellation_lock_digest": digest(constellation),
            "source_constellation_digest": golden_report[
                "source_constellation_digest"
            ],
            "classification_counts": golden_report["summary"][
                "classification_counts"
            ],
            "implementation": {
                "fixture_path": (
                    "fixtures/pairs/enterprise-postgresql-observation.json"
                ),
                "fixture_authority": (
                    "comparative_owned_snapshot_from_accepted_enterprise_source"
                ),
                "file_sha256": (
                    "sha256:"
                    + sha256(implementation_golden_path.read_bytes()).hexdigest()
                ),
                "observation_digest": digest(implementation_golden),
                "projection_digest": digest(
                    implementation_golden["result"]["projection"]
                ),
            },
            "simulation": {
                "fixture_path": (
                    "fixtures/pairs/simulation-golden-specimen-observation.json"
                ),
                "fixture_authority": "accepted_simulation_release_observation",
                "file_sha256": (
                    "sha256:"
                    + sha256(simulation_golden_path.read_bytes()).hexdigest()
                ),
                "observation_digest": digest(simulation_golden),
                "projection_digest": digest(
                    simulation_golden["result"]["projection"]
                ),
            },
        },
    }
    drift = {
        field: {"manifest": manifest.get(field), "derived": value}
        for field, value in expected.items()
        if manifest.get(field) != value
    }
    promotion_binding = manifest.get("promotion_receipt_contract")
    if promotion_binding != expected_promotion_binding:
        drift["promotion_receipt_contract"] = {
            "manifest": promotion_binding,
            "derived": expected_promotion_binding,
        }
    if manifest.get("promotion_coordinates") != expected_promotion_coordinates:
        drift["promotion_coordinates"] = {
            "manifest": manifest.get("promotion_coordinates"),
            "derived": expected_promotion_coordinates,
        }
    if manifest.get("publication_coordinates") != expected_publication_coordinates:
        drift["publication_coordinates"] = {
            "manifest": manifest.get("publication_coordinates"),
            "derived": expected_publication_coordinates,
        }
    for label, observation_field in (
        ("implementation", "observation_digest"),
        ("simulation", "reference_observation_digest"),
    ):
        expected_fixture = expected["golden_specimen_verification"][label]
        expected_lock = {
            "fixture_path": expected_fixture["fixture_path"],
            "fixture_authority": expected_fixture["fixture_authority"],
            "fixture_file_sha256": expected_fixture["file_sha256"],
            observation_field: expected_fixture["observation_digest"],
            "projection_digest": expected_fixture["projection_digest"],
        }
        observed_lock = {
            field: constellation[label].get(field) for field in expected_lock
        }
        if observed_lock != expected_lock:
            drift[f"constellation.{label}.fixture_binding"] = {
                "lock": observed_lock,
                "derived": expected_lock,
            }
    if (
        manifest.get("trusted_simulated_database_release")
        != TRUSTED_SIMULATED_DATABASE_RELEASE.as_dict()
    ):
        drift["trusted_simulated_database_release"] = {
            "manifest": manifest.get("trusted_simulated_database_release"),
            "derived": TRUSTED_SIMULATED_DATABASE_RELEASE.as_dict(),
        }
    if drift:
        raise ValueError(
            "release manifest differs from derived evidence: "
            + json.dumps(drift, sort_keys=True)
        )
    environment_claims = _persisted_environment_claims()
    if environment_claims:
        raise ValueError(
            "repository fixtures require planned or simulated authority: "
            + ", ".join(environment_claims)
        )
    findings = _repository_secret_shape_findings()
    if findings:
        raise ValueError(
            "repository files require governed credential storage: "
            + ", ".join(findings)
        )
    print(
        json.dumps(
            {
                "status": "passed",
                "json_documents": json_count,
                "comparison_profile_schema": manifest["contract_bindings"][
                    "comparison_profile_schema"
                ],
                "observation_envelope_schema": manifest["contract_bindings"][
                    "observation_envelope_schema"
                ],
                "synthetic_contract_report_digest": report["report_digest"],
                "golden_specimen_verification_report_digest": golden_report[
                    "report_digest"
                ],
                "closure_comparison_digest": bundle_summary[
                    "comparison_digest"
                ],
                "calibration_status": calibration["status"],
                "report_artifact_inventory_digest": digest(
                    report_artifact_inventory
                ),
                "golden_report_artifact_inventory_digest": digest(
                    golden_report_artifact_inventory
                ),
                "pages_projection_inventory_digest": digest(pages_inventory),
                "promotion_receipt_digest": promotion_receipt_digest(
                    promotion_receipt
                ),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
