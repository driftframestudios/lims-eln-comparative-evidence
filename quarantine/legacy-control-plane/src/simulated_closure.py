from __future__ import annotations

import json
import os
from pathlib import Path
import re
from typing import Any

from .model import canonical_json, digest
from .safety import (
    EvidenceSafetyError,
    validate_digest,
    validate_repository_safe_content,
)


BUNDLE_VERSION = "2.0.1"
TRUSTED_CLOSURE_ID = "CLOSURE-SIM-SUBSTANTIVE-2028-V1"
TRUSTED_FUTURE_REALITY_VERSION = "future-reality-2028-06-30-v1"
TRUSTED_FUTURE_REALITY_ID = "FUTURE-REALITY-LIMS-2028-001"
TRUSTED_GOVERNANCE_CLOSURE_DIGEST = (
    "sha256:c402e7a72d9066424d5b83c8fda51ca2fad43c025d017a5f5535126239c96ffb"
)
TRUSTED_SOURCE_COORDINATES = (
    {
        "release": "seed-forecast-2026-Q3-r2",
        "commit": "6194a1c3911a97aa5e29b1861819a55554019488",
        "digest": "sha256:35b3d9bcadea3ab95b9cf6f3bb26fd95049147f7fcc771815ff71060fae0937a",
    },
    {
        "release": "seed-implementation-v0.2.0",
        "commit": "c79f8727963a427164a11eacb14837d795cd757d",
        "digest": "sha256:3e9079af08ae3c153a8eebb438fb342ffd6313c34c0a53247e9f9c6b054d0494",
    },
)
REQUIRED_FAMILIES = {
    "configured_vendor_environments",
    "representative_migration_restore_rehearsals",
    "production_security_observability",
    "accountable_scientific_quality_regulatory_acceptance",
}
FUTURE_REALITY_PATTERN = re.compile(
    r"^future-reality-(?P<date>[0-9]{4}-[0-9]{2}-[0-9]{2})-v(?P<revision>[0-9]+)$"
)
FUTURE_REALITY_ID_PATTERN = re.compile(
    r"^FUTURE-REALITY-[A-Z0-9]+(?:-[A-Z0-9]+)*$"
)
GOVERNANCE_CLOSURE_FIELDS = {
    "closure_id",
    "future_reality",
    "evidence_mode",
    "closure_status",
    "environment_observed_closure",
    "production_authorization_effect",
    "receipt_closures",
    "executable_checks",
    "aggregate_outcome",
    "aggregate_artifacts",
    "limitations",
    "divergence_triggers",
    "metadata",
}


class SimulatedClosureError(ValueError):
    """The closure bundle receives a precise reconciliation path."""


def validate_simulated_closure_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    """Validate one governance closure and its executable detailed receipts.

    The governance projection carries the cross-repository closure contract. The
    detailed receipts retain enough evidence to independently verify vendor,
    migration, security, observability, and role-separated acceptance claims.
    """

    if set(bundle) != {
        "bundle_version",
        "future_reality_version",
        "governance_closure_digest",
        "governance_closure",
        "detailed_receipts",
        "source_result_digest",
    }:
        raise SimulatedClosureError(
            "closure bundle requires its released version, future reality, "
            "governance closure with digest, and detailed receipts"
        )
    if bundle["bundle_version"] != BUNDLE_VERSION:
        raise SimulatedClosureError(
            f"closure bundle requires the released {BUNDLE_VERSION} contract"
        )
    reality = _validate_future_reality_version(bundle["future_reality_version"])
    closure = _mapping(bundle["governance_closure"], "governance_closure")
    closure_digest = bundle["governance_closure_digest"]
    if closure_digest != digest(closure):
        raise SimulatedClosureError(
            "governance closure digest requires the exact canonical closure document"
        )

    closure_by_family = _validate_governance_closure(closure, reality)
    detailed_by_family = _validate_detailed_receipts(
        bundle["detailed_receipts"],
        reality,
    )
    source_result_digest = bundle["source_result_digest"]
    try:
        validate_digest(source_result_digest, "source_result_digest")
    except EvidenceSafetyError as error:
        raise SimulatedClosureError(str(error)) from error
    _validate_projection_links(
        closure,
        closure_by_family,
        detailed_by_family,
        source_result_digest,
    )
    validate_repository_safe_content(bundle)
    _validate_trusted_release_binding(closure, reality, closure_digest)

    result = {
        "comparison_contract_version": BUNDLE_VERSION,
        "future_reality_version": reality,
        "closure_id": closure["closure_id"],
        "governance_closure_digest": closure_digest,
        "aggregate_artifact_digest": closure["aggregate_artifacts"][0]["digest"],
        "source_result_digest": source_result_digest,
        "receipt_families": sorted(detailed_by_family),
        "families_closed": len(detailed_by_family),
        "closure_status": closure["closure_status"],
        "environment_observed_closure": closure["environment_observed_closure"],
        "production_authorization_effect": closure["production_authorization_effect"],
        "external_encounter_posture": "available_for_independent_comparison",
        "receipt_digests": {
            family: detailed_by_family[family]["closure_digest"]
            for family in sorted(detailed_by_family)
        },
    }
    result["comparison_digest"] = digest(result)
    return result


def admit_simulated_closure(bundle: dict[str, Any], directory: Path) -> Path:
    """Immutably admit one internally coherent selected-future closure."""

    summary = validate_simulated_closure_bundle(bundle)
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / f"{summary['future_reality_version']}.json"
    payload = {
        "namespace": "simulated-closures",
        "authority": "definitive_within_selected_future_reality",
        "production_authorization_effect": "none",
        "bundle": bundle,
        "summary": summary,
    }
    serialized = json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(destination, flags, 0o600)
    except FileExistsError:
        existing = json.loads(destination.read_text(encoding="utf-8"))
        if canonical_json(existing) != canonical_json(payload):
            raise SimulatedClosureError(
                "simulated closure is immutable; select a new future reality version"
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


def _validate_future_reality_version(value: Any) -> str:
    if not isinstance(value, str) or FUTURE_REALITY_PATTERN.fullmatch(value) is None:
        raise SimulatedClosureError(
            "future reality requires future-reality-YYYY-MM-DD-vN identity"
        )
    return value


def _validate_trusted_release_binding(
    closure: dict[str, Any],
    reality: str,
    closure_digest: str,
) -> None:
    """Bind admission to the closure identity released with this comparator."""

    if reality != TRUSTED_FUTURE_REALITY_VERSION:
        raise SimulatedClosureError(
            "selected-future admission requires the trusted release reality version"
        )
    if closure.get("closure_id") != TRUSTED_CLOSURE_ID:
        raise SimulatedClosureError(
            "selected-future admission requires the trusted release closure identity"
        )
    future_reality = _mapping(
        closure.get("future_reality"),
        "governance closure future reality",
    )
    if future_reality.get("future_reality_id") != TRUSTED_FUTURE_REALITY_ID:
        raise SimulatedClosureError(
            "selected-future admission requires the trusted future-reality identity"
        )
    if future_reality.get("source_coordinates") != list(TRUSTED_SOURCE_COORDINATES):
        raise SimulatedClosureError(
            "selected-future admission requires the trusted release source coordinates"
        )
    if closure_digest != TRUSTED_GOVERNANCE_CLOSURE_DIGEST:
        raise SimulatedClosureError(
            "selected-future admission requires the trusted release closure digest"
        )


def _validate_governance_closure(
    closure: dict[str, Any],
    reality: str,
) -> dict[str, dict[str, Any]]:
    if set(closure) != GOVERNANCE_CLOSURE_FIELDS:
        raise SimulatedClosureError(
            "governance closure fields require the released governance 2.0.0 contract"
        )
    expected = {
        "evidence_mode": "simulated",
        "closure_status": "closed_in_simulation",
        "environment_observed_closure": "separate_unasserted_state",
        "production_authorization_effect": "none",
    }
    for field, value in expected.items():
        if closure.get(field) != value:
            raise SimulatedClosureError(
                f"governance closure requires {field}={value}"
            )
    metadata = _mapping(closure.get("metadata"), "governance closure metadata")
    if metadata.get("schema_version") != "2.0.0":
        raise SimulatedClosureError(
            "governance closure requires schema_version=2.0.0"
        )

    future_reality = _mapping(
        closure.get("future_reality"),
        "governance closure future reality",
    )
    match = FUTURE_REALITY_PATTERN.fullmatch(reality)
    assert match is not None
    future_reality_id = future_reality.get("future_reality_id")
    if (
        not isinstance(future_reality_id, str)
        or FUTURE_REALITY_ID_PATTERN.fullmatch(future_reality_id) is None
    ):
        raise SimulatedClosureError(
            "governance closure requires a released future-reality identity"
        )
    if future_reality.get("as_of") != match.group("date"):
        raise SimulatedClosureError(
            "governance closure as_of differs from its future reality version"
        )
    if len(future_reality.get("source_coordinates", [])) < 2:
        raise SimulatedClosureError(
            "governance closure requires simulation and implementation coordinates"
        )
    modeled_roles = set(future_reality.get("modeled_authority_roles", []))
    if not {
        "Scientific authority",
        "Quality authority",
        "Regulatory authority",
    }.issubset(modeled_roles):
        raise SimulatedClosureError(
            "governance closure requires modeled Scientific, Quality, and Regulatory roles"
        )

    aggregate = _mapping(
        closure.get("aggregate_outcome"),
        "governance closure aggregate outcome",
    )
    if aggregate != {
        "result": "passed",
        "closed_family_count": 4,
        "expected_family_count": 4,
        "reproduction_statement": aggregate.get("reproduction_statement"),
    }:
        raise SimulatedClosureError(
            "governance closure aggregate requires four passed receipt families"
        )
    if not isinstance(aggregate.get("reproduction_statement"), str) or len(
        aggregate["reproduction_statement"]
    ) < 20:
        raise SimulatedClosureError(
            "governance closure requires a reproducible aggregate statement"
        )
    artifacts = closure.get("aggregate_artifacts")
    if not isinstance(artifacts, list) or len(artifacts) != 1:
        raise SimulatedClosureError(
            "governance closure requires one aggregate closure artifact"
        )

    projections = closure.get("receipt_closures")
    if not isinstance(projections, list) or len(projections) != 4:
        raise SimulatedClosureError(
            "governance closure requires exactly four receipt projections"
        )
    by_family: dict[str, dict[str, Any]] = {}
    for projection in projections:
        value = _mapping(projection, "governance receipt projection")
        family = value.get("family")
        if family not in REQUIRED_FAMILIES:
            raise SimulatedClosureError(
                f"governance closure has unreleased receipt family {family!r}"
            )
        if family in by_family:
            raise SimulatedClosureError(
                f"governance receipt family {family} requires one closure"
            )
        if value.get("outcome") != "passed":
            raise SimulatedClosureError(
                f"governance receipt family {family} requires outcome=passed"
            )
        projection_artifacts = value.get("artifacts")
        if not isinstance(projection_artifacts, list) or len(projection_artifacts) != 1:
            raise SimulatedClosureError(
                f"governance receipt family {family} requires one canonical artifact"
            )
        if not value.get("limitations"):
            raise SimulatedClosureError(
                f"governance receipt family {family} requires explicit limitations"
            )
        by_family[family] = value
    if set(by_family) != REQUIRED_FAMILIES:
        raise SimulatedClosureError(
            "governance closure requires every substantive receipt family"
        )

    checks = closure.get("executable_checks")
    if not isinstance(checks, list) or len(checks) < 4:
        raise SimulatedClosureError(
            "governance closure requires executable checks for every family"
        )
    projected_artifact_ids = {
        item["artifacts"][0]["artifact_id"] for item in by_family.values()
    }
    checked_artifact_ids = {
        artifact_id
        for check in checks
        for artifact_id in _mapping(check, "executable check").get("artifact_ids", [])
    }
    if checked_artifact_ids != projected_artifact_ids:
        raise SimulatedClosureError(
            "governance executable checks require every projected artifact exactly"
        )
    return by_family


def _validate_detailed_receipts(
    receipts: Any,
    reality: str,
) -> dict[str, dict[str, Any]]:
    if not isinstance(receipts, list) or len(receipts) != len(REQUIRED_FAMILIES):
        raise SimulatedClosureError(
            "closure bundle requires exactly four detailed receipt families"
        )
    by_family: dict[str, dict[str, Any]] = {}
    for item in receipts:
        receipt = _mapping(item, "detailed receipt")
        _validate_detailed_common(receipt, reality)
        family = receipt["receipt_family"]
        if family in by_family:
            raise SimulatedClosureError(
                f"detailed receipt family {family} requires one closure"
            )
        by_family[family] = receipt
    missing = sorted(REQUIRED_FAMILIES - set(by_family))
    if missing:
        raise SimulatedClosureError(
            "closure bundle requires receipt families: " + ", ".join(missing)
        )

    _validate_vendor(by_family["configured_vendor_environments"])
    _validate_migration(
        by_family["representative_migration_restore_rehearsals"]
    )
    _validate_security(by_family["production_security_observability"])
    _validate_acceptance(
        by_family["accountable_scientific_quality_regulatory_acceptance"]
    )
    return by_family


def _validate_detailed_common(receipt: dict[str, Any], reality: str) -> None:
    required = {
        "schema_version",
        "receipt_id",
        "receipt_family",
        "evidence_mode",
        "assurance_stage",
        "closure_status",
        "future_reality_version",
        "reality_basis",
        "claim_scope",
        "outcome",
        "closure_digest",
    }
    missing = sorted(required - receipt.keys())
    if missing:
        raise SimulatedClosureError(
            f"detailed receipt requires fields: {', '.join(missing)}"
        )
    expected = {
        "schema_version": "2.0.0",
        "evidence_mode": "simulated",
        "assurance_stage": "verified",
        "closure_status": "closed_in_simulation",
        "future_reality_version": reality,
        "outcome": "passed",
    }
    for field, value in expected.items():
        if receipt[field] != value:
            raise SimulatedClosureError(
                f"{receipt.get('receipt_id', 'receipt')} requires {field}={value}"
            )
    basis = _mapping(receipt["reality_basis"], "detailed receipt reality basis")
    if basis != {
        "kind": "selected_future_simulation",
        "selection_rule": basis.get("selection_rule"),
        "authority": "definitive_within_selected_future_reality",
        "environment_observed_closure": "separate_unasserted_state",
        "production_authorization_effect": "none",
    }:
        raise SimulatedClosureError(
            "detailed receipt requires the selected-future authority boundary"
        )
    if not isinstance(basis.get("selection_rule"), str) or not basis[
        "selection_rule"
    ].strip():
        raise SimulatedClosureError(
            "detailed receipt requires an explicit future-reality selection rule"
        )
    content = {key: value for key, value in receipt.items() if key != "closure_digest"}
    if receipt["closure_digest"] != digest(content):
        raise SimulatedClosureError(
            "detailed receipt closure digest requires canonical content"
        )


def _validate_projection_links(
    closure: dict[str, Any],
    projections: dict[str, dict[str, Any]],
    details: dict[str, dict[str, Any]],
    source_result_digest: str,
) -> None:
    for family in REQUIRED_FAMILIES:
        artifact = projections[family]["artifacts"][0]
        if artifact.get("digest") != details[family]["closure_digest"]:
            raise SimulatedClosureError(
                f"governance artifact digest for {family} differs from its detailed receipt"
            )

    vendor_environment = projections["configured_vendor_environments"][
        "simulated_environment"
    ]
    if vendor_environment.get("configuration_digest") != details[
        "configured_vendor_environments"
    ]["environment"].get("configuration_receipt_digest"):
        raise SimulatedClosureError(
            "configured-vendor projection requires the detailed configuration digest"
        )

    migration_environment = projections[
        "representative_migration_restore_rehearsals"
    ]["simulated_environment"]
    if migration_environment.get("configuration_digest") != digest(
        details["representative_migration_restore_rehearsals"]["corpus"]
    ):
        raise SimulatedClosureError(
            "migration projection requires the detailed corpus digest"
        )

    security_environment = projections["production_security_observability"][
        "simulated_environment"
    ]
    if security_environment.get("configuration_digest") != digest(
        details["production_security_observability"]["checks"]
    ):
        raise SimulatedClosureError(
            "security projection requires the detailed control-check digest"
        )

    acceptance = details[
        "accountable_scientific_quality_regulatory_acceptance"
    ]
    evidence_basis_digest = acceptance["independence"]["shared_basis_digest"]
    acceptance_environment = projections[
        "accountable_scientific_quality_regulatory_acceptance"
    ]["simulated_environment"]
    if acceptance_environment.get("configuration_digest") != evidence_basis_digest:
        raise SimulatedClosureError(
            "acceptance projection requires its shared evidence-basis digest"
        )

    projected_digests = [
        item["artifacts"][0]["digest"] for item in closure["receipt_closures"]
    ]
    expected_aggregate = digest(
        {
            "future_reality_version": details[
                "configured_vendor_environments"
            ]["future_reality_version"],
            "content_digest": source_result_digest,
            "receipt_digests": projected_digests,
        }
    )
    if closure["aggregate_artifacts"][0].get("digest") != expected_aggregate:
        raise SimulatedClosureError(
            "governance aggregate artifact requires the detailed evidence-basis "
            "and ordered receipt digests"
        )


def _validate_vendor(receipt: dict[str, Any]) -> None:
    checks = _mapping(receipt.get("checks"), "configured vendor checks")
    required_true = {
        "ambiguous_write_reconciled",
        "authoritative_identity_readback",
        "task_scoped_configuration",
        "version_bands_retained",
    }
    if set(checks) != required_true or any(
        checks[field] is not True for field in required_true
    ):
        raise SimulatedClosureError(
            "configured vendor closure requires every released conformance criterion"
        )
    bindings = receipt.get("vendor_bindings")
    if not isinstance(bindings, list) or {
        item.get("vendor") for item in bindings
    } != {"sapio", "benchling", "labkey"}:
        raise SimulatedClosureError(
            "configured vendor closure requires Sapio, Benchling, and LabKey bindings"
        )
    if any(item.get("conformance") != "passed" for item in bindings):
        raise SimulatedClosureError(
            "configured vendor bindings require passed conformance"
        )
    if receipt.get("environment", {}).get("configuration_provider") != (
        "aws-ssm-and-secrets-manager"
    ):
        raise SimulatedClosureError(
            "configured vendor closure requires the released AWS configuration provider"
        )


def _validate_migration(receipt: dict[str, Any]) -> None:
    checks = _mapping(receipt.get("checks"), "migration checks")
    required_true = (
        "semantic_parity",
        "clean_environment",
        "readback_parity",
        "data_exit_reconstructable",
        "migration_failure_twin_detected",
        "restore_failure_twin_detected",
        "representative_artifact_count",
        "representative_record_count",
        "recovery_objective_met",
        "rollback_ready",
    )
    if any(checks.get(field) is not True for field in required_true):
        raise SimulatedClosureError(
            "migration closure requires parity, clean restore, exit, and failure-twin checks"
        )
    if checks.get("observed_recovery_seconds", float("inf")) > checks.get(
        "recovery_objective_seconds",
        -1,
    ):
        raise SimulatedClosureError(
            "migration closure requires recovery within the selected objective"
        )


def _validate_security(receipt: dict[str, Any]) -> None:
    checks = _mapping(receipt.get("checks"), "security checks")
    for field in (
        "tenant_boundary",
        "protected_trace_projection",
        "parameter_store_reference",
        "credential_store_reference",
        "bounded_caller_failure_twins",
        "broad_write_approval_bound",
        "migration_parity_sli",
        "vendor_readback_sli",
    ):
        if checks.get(field) is not True:
            raise SimulatedClosureError(
                f"security closure requires {field}=true"
            )
    if not isinstance(checks.get("rotation_posture"), str) or not checks[
        "rotation_posture"
    ].strip():
        raise SimulatedClosureError(
            "security closure requires an explicit credential rotation posture"
        )
    bounded = _mapping(checks.get("bounded_caller"), "bounded caller summary")
    if (
        bounded.get("broad_write_approval_bound") is not True
        or bounded.get("allowed_operations") != 3
        or bounded.get("bounded_scenarios") != 3
    ):
        raise SimulatedClosureError(
            "security closure requires the released bounded-caller operation set"
        )
    if set(receipt.get("failure_twins", [])) != {
        "approval_required",
        "cross_tenant",
        "unreleased_operation",
    }:
        raise SimulatedClosureError(
            "security closure requires all released caller-boundary failure twins"
        )


def _validate_acceptance(receipt: dict[str, Any]) -> None:
    checks = _mapping(receipt.get("checks"), "acceptance checks")
    required_true = {
        "distinct_accountable_domains",
        "intended_use_released",
        "prerequisite_receipts_passed",
        "shared_basis",
        "simulated_evidence_declared",
    }
    if set(checks) != required_true or any(
        checks[field] is not True for field in required_true
    ):
        raise SimulatedClosureError(
            "acceptance closure requires every released acceptance criterion"
        )
    decisions = receipt.get("decisions")
    if not isinstance(decisions, list):
        raise SimulatedClosureError(
            "acceptance closure requires decision records"
        )
    domains = {
        item.get("domain")
        for item in decisions
        if item.get("decision") == "accept"
    }
    if domains != {"scientific", "quality", "regulatory"}:
        raise SimulatedClosureError(
            "acceptance closure requires Scientific, Quality, and Regulatory decisions"
        )
    roles = {item.get("simulated_accountable_role") for item in decisions}
    digests = {item.get("basis_digest") for item in decisions}
    if len(roles) != 3 or len(digests) != 1:
        raise SimulatedClosureError(
            "acceptance closure requires distinct simulated roles bound to one evidence basis"
        )
    independence = _mapping(receipt.get("independence"), "acceptance independence")
    if (
        independence.get("mode") != "distinct_simulated_accountable_roles"
        or independence.get("role_count") != 3
        or independence.get("shared_basis_digest") not in digests
    ):
        raise SimulatedClosureError(
            "acceptance closure requires an explicit independent-role summary"
        )


def _mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SimulatedClosureError(f"{field} requires a JSON object")
    return value
