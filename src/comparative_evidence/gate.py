from __future__ import annotations

from pathlib import Path
import json

from .model import ObservationEnvelope, canonical_json


class AdmissionError(ValueError):
    """Admission returns the record to a named evidence-completion path."""


def validate_for_accepted(envelope: ObservationEnvelope) -> None:
    if envelope.evidence_mode != "observed":
        raise AdmissionError(
            "accepted evidence requires an observed execution; run the scenario in the named environment"
        )
    source_required = {"environment_id", "implementation_commit", "configuration_digest"}
    source_missing = sorted(source_required - envelope.source.keys())
    if source_missing:
        raise AdmissionError(
            "observed source requires " + ", ".join(source_missing) + "; capture them from the execution environment"
        )
    provenance_required = {"raw_artifact_digest", "governed_locator", "performed_by", "reviewed_by"}
    provenance_missing = sorted(provenance_required - envelope.provenance.keys())
    if provenance_missing:
        raise AdmissionError(
            "observed provenance requires "
            + ", ".join(provenance_missing)
            + "; complete the governed evidence manifest"
        )
    if envelope.provenance["performed_by"] == envelope.provenance["reviewed_by"]:
        raise AdmissionError("accepted evidence requires independent review; assign a distinct reviewer")
    if not str(envelope.provenance["raw_artifact_digest"]).startswith("sha256:"):
        raise AdmissionError("raw artifact provenance requires a sha256 digest; compute it in governed storage")
    if "://" not in str(envelope.provenance["governed_locator"]):
        raise AdmissionError("raw artifact provenance requires a protected locator; register it in governed storage")
    classification_required = {"data_class", "redaction_status"}
    classification_missing = sorted(classification_required - envelope.classification.keys())
    if classification_missing:
        raise AdmissionError(
            "classification requires "
            + ", ".join(classification_missing)
            + "; classify and redact through the approved evidence workflow"
        )
    if envelope.assurance_stage == "accepted":
        approval_domains = {
            approval.get("domain")
            for approval in envelope.approvals
            if approval.get("decision") == "accept"
        }
        required_domains = {"scientific", "quality", "regulatory"}
        missing_domains = sorted(required_domains - approval_domains)
        if missing_domains:
            raise AdmissionError(
                "acceptance-stage evidence requires accountable "
                + ", ".join(missing_domains)
                + " approval; route the packet to the named approvers"
            )


def admit(envelope: ObservationEnvelope, accepted_directory: Path) -> Path:
    validate_for_accepted(envelope)
    accepted_directory.mkdir(parents=True, exist_ok=True)
    destination = accepted_directory / f"{envelope.observation_id}.json"
    payload = {
        **envelope.as_dict(),
        "accepted_namespace": True,
        "envelope_digest": envelope.content_digest,
    }
    if destination.exists():
        existing = json.loads(destination.read_text())
        if canonical_json(existing) != canonical_json(payload):
            raise AdmissionError(
                "accepted manifests are immutable; create a superseding observation with a new observation_id"
            )
        return destination
    destination.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return destination
