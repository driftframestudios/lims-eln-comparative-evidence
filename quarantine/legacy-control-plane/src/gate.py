from __future__ import annotations

import json
import os
from pathlib import Path
import stat

from .model import ObservationEnvelope, canonical_json, strict_json_loads
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
        accepted_approvals = [
            approval for approval in envelope.approvals if approval.get("decision") == "accept"
        ]
        approval_domains = {approval.get("domain") for approval in accepted_approvals}
        required_domains = {"scientific", "quality", "regulatory"}
        missing_domains = sorted(required_domains - approval_domains)
        if missing_domains:
            raise AdmissionError(
                "acceptance-stage evidence requires accountable "
                + ", ".join(missing_domains)
                + " approval; route the packet to the named approvers"
            )
        approver_identities = [
            normalize_identity(approval.get("approver"), f"{approval.get('domain')}_approver")
            for approval in accepted_approvals
            if approval.get("domain") in required_domains
        ]
        if len(set(approver_identities)) != len(required_domains):
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
    accepted_directory.mkdir(parents=True, exist_ok=True)
    accepted_root = accepted_directory.resolve()
    destination = accepted_root / f"{observation_id}.json"
    if destination.resolve(strict=False).parent != accepted_root:
        raise AdmissionError("accepted manifest identity requires containment in the accepted namespace")
    payload = {
        **envelope.as_dict(),
        "accepted_namespace": True,
        "envelope_digest": envelope.content_digest,
    }
    serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(destination, flags, 0o600)
    except FileExistsError:
        existing = _read_existing_manifest(destination)
        if canonical_json(existing) != canonical_json(payload):
            raise AdmissionError(
                "accepted manifests are immutable; create a superseding observation with a new observation_id"
            )
        return destination
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(serialized)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    return destination


def _read_existing_manifest(path: Path) -> dict:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise AdmissionError(
            "accepted manifest requires a regular repository file; preserve the namespace and inspect the entry"
        ) from error
    with os.fdopen(descriptor, encoding="utf-8") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise AdmissionError("accepted manifest requires a regular repository file")
        value = strict_json_loads(stream.read())
        if not isinstance(value, dict):
            raise AdmissionError("accepted manifest requires a JSON object")
        return value
