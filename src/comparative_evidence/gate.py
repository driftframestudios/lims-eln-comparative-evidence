from __future__ import annotations

import json
from pathlib import Path

from .model import ObservationEnvelope
from .filesystem_publication import PublicationError, publish_manifest
from .database_release import (
    DatabaseReleaseError,
    validate_database_release_coordinate,
)
from .safety import (
    EvidenceSafetyError,
    normalize_identity,
    validate_classification,
    validate_commit,
    validate_digest,
    validate_locator,
    validate_observation_id,
    validate_repository_safe_content,
)


class AdmissionError(ValueError):
    """Admission returns the record to a named evidence-completion path."""


def validate_for_accepted(envelope: ObservationEnvelope) -> None:
    validate_observation_id(envelope.observation_id)
    if envelope.evidence_mode != "observed":
        raise AdmissionError(
            "accepted evidence requires an observed execution; run the scenario in the named environment"
        )
    if envelope.assurance_stage not in {"qualified", "validated", "accepted"}:
        raise AdmissionError(
            "accepted evidence requires qualified, validated, or accepted assurance; "
            "complete independent evidence review before admission"
        )
    source_required = {
        "environment_id",
        "implementation_commit",
        "configuration_digest",
        "database_release",
    }
    source_missing = sorted(source_required - envelope.source.keys())
    if source_missing:
        raise AdmissionError(
            "observed source requires " + ", ".join(source_missing) + "; capture them from the execution environment"
        )
    normalize_identity(envelope.source["environment_id"], "environment_id")
    validate_commit(envelope.source["implementation_commit"])
    validate_digest(envelope.source["configuration_digest"], "configuration_digest")
    try:
        validate_database_release_coordinate(
            envelope.source["database_release"],
            label="source.database_release",
        )
    except DatabaseReleaseError as error:
        raise AdmissionError(str(error)) from error
    provenance_required = {"raw_artifact_digest", "governed_locator", "performed_by", "reviewed_by"}
    provenance_missing = sorted(provenance_required - envelope.provenance.keys())
    if provenance_missing:
        raise AdmissionError(
            "observed provenance requires "
            + ", ".join(provenance_missing)
            + "; complete the governed evidence manifest"
        )
    performer = normalize_identity(envelope.provenance["performed_by"], "performed_by")
    reviewer = normalize_identity(envelope.provenance["reviewed_by"], "reviewed_by")
    if performer == reviewer:
        raise AdmissionError("accepted evidence requires independent review; assign a distinct reviewer")
    validate_digest(envelope.provenance["raw_artifact_digest"], "raw_artifact_digest")
    validate_locator(envelope.provenance["governed_locator"])
    classification_required = {"data_class", "redaction_status"}
    classification_missing = sorted(classification_required - envelope.classification.keys())
    if classification_missing:
        raise AdmissionError(
            "classification requires "
            + ", ".join(classification_missing)
            + "; classify and redact through the approved evidence workflow"
        )
    validate_classification(envelope.classification)
    validate_repository_safe_content(envelope.as_dict())
    if envelope.assurance_stage == "accepted":
        required_domains = {"scientific", "quality", "regulatory"}
        # One decision per required domain preserves the role-to-person relation.
        approvers_by_domain: dict[str, str] = {}
        for approval in envelope.approvals:
            domain = approval.get("domain")
            if approval.get("decision") != "accept" or domain not in required_domains:
                continue
            if domain in approvers_by_domain:
                raise AdmissionError(
                    "acceptance-stage evidence requires one accepting decision per accountable domain"
                )
            approvers_by_domain[domain] = normalize_identity(
                approval.get("approver"), f"{domain}_approver"
            )
        missing_domains = sorted(required_domains - approvers_by_domain.keys())
        if missing_domains:
            raise AdmissionError(
                "acceptance-stage evidence requires accountable "
                + ", ".join(missing_domains)
                + " approval; route the packet to the named approvers"
            )
        approver_identities = set(approvers_by_domain.values())
        if len(approver_identities) != len(required_domains):
            raise AdmissionError(
                "acceptance-stage evidence requires distinct accountable scientific, quality, and regulatory approvers"
            )
        if performer in approver_identities or reviewer in approver_identities:
            raise AdmissionError(
                "acceptance-stage decisions require accountable approvers distinct from execution and review"
            )


def admit(envelope: ObservationEnvelope, accepted_directory: Path) -> Path:
    try:
        validate_for_accepted(envelope)
        observation_id = validate_observation_id(envelope.observation_id)
    except EvidenceSafetyError as error:
        raise AdmissionError(str(error)) from error
    destination = accepted_directory.absolute() / f"{observation_id}.json"
    payload = {
        **envelope.as_dict(),
        "accepted_namespace": True,
        "envelope_digest": envelope.content_digest,
    }
    serialized = (json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    try:
        publish_manifest(serialized, destination)
    except PublicationError as error:
        action = (
            "accepted manifests are immutable; create a superseding observation with a new observation_id; "
            if error.stage == "destination_exists" else "accepted manifest publication: "
        )
        raise AdmissionError(action + str(error)) from error
    return destination
