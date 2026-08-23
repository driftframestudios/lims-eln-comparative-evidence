"""Standalone-safe binding to the shared LIMS/ELN contract nucleus."""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import importlib
from importlib import resources
import json
import math
import re
from typing import Any


CONTRACT_VERSION = "1.0.0"
CONTRACT_DISTRIBUTION_VERSION = "0.3.1"
GOLDEN_SCENARIO_RESOURCE = "golden-specimen.v1.json"
OBSERVATION_SCHEMA_RESOURCE = "observation-envelope.v1.schema.json"

EVIDENCE_MODES = frozenset({"planned", "simulated", "observed"})
ASSURANCE_STAGES = frozenset(
    {"specified", "verified", "qualified", "validated", "accepted"}
)
APPROVAL_DOMAINS = frozenset(
    {"engineering", "operations", "quality", "regulatory", "scientific", "security"}
)
APPROVAL_DECISIONS = frozenset({"accept", "revise", "escalate"})
DATA_CLASSES = frozenset(
    {
        "approved-synthetic-exemplar",
        "approved-synthetic-qualification",
        "redacted-confidential-manifest",
        "redacted-regulated-manifest",
        "synthetic",
    }
)
REDACTION_STATES = frozenset(
    {"generated-identities", "reviewed-redacted-manifest"}
)

_UPPER_IDENTIFIER = re.compile(
    r"^(?=.{3,128}$)[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*$"
)
_IDENTIFIER = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{1,126}[A-Za-z0-9]$"
)
_SHA256 = re.compile(r"^sha256:[a-f0-9]{64}$")
_URI = re.compile(r"^[a-z][a-z0-9+.-]*://[^?#]+$")
_OBSERVED_LOCATOR = re.compile(r"^(?:evidence-vault|s3)://[^/?#]+/[^?#%]+$")
_OBSERVED_COMMIT = re.compile(r"^(?:[a-f0-9]{40}|[a-f0-9]{64})$")


class ContractBoundaryError(ValueError):
    """A value returns to the named contract-completion path."""


def strict_json_loads(content: str | bytes) -> Any:
    """Read one finite JSON document with unique object keys."""

    return json.loads(
        content,
        parse_constant=_reject_nonfinite,
        object_pairs_hook=_unique_object,
    )


def _reject_nonfinite(value: str) -> None:
    raise ContractBoundaryError(
        f"JSON numeric value {value} requires a finite representation"
    )


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ContractBoundaryError(
                f"JSON object key {key!r} requires a single definition"
            )
        result[key] = value
    return result


def canonical_json_bytes(value: Any) -> bytes:
    _validate_json_value(value)
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def canonical_digest(value: Any) -> str:
    return "sha256:" + sha256(canonical_json_bytes(value)).hexdigest()


def _resource_bytes(name: str) -> bytes:
    return (
        resources.files(__package__)
        .joinpath("contract_resources")
        .joinpath(name)
        .read_bytes()
    )


def load_contract_binding() -> dict[str, Any]:
    document = strict_json_loads(_resource_bytes("contract-binding.v1.json"))
    if not isinstance(document, dict):
        raise ContractBoundaryError("contract binding carries one JSON object")
    if document.get("contract_version") != CONTRACT_VERSION:
        raise ContractBoundaryError(
            "contract binding uses version 1.0.0; restore the released binding snapshot"
        )
    distribution = document.get("distribution")
    if not isinstance(distribution, dict) or distribution.get("version") != (
        CONTRACT_DISTRIBUTION_VERSION
    ):
        raise ContractBoundaryError(
            "contract binding names distribution version "
            f"{CONTRACT_DISTRIBUTION_VERSION}; restore that source boundary"
        )
    _verify_local_resource(document, "golden_scenario", GOLDEN_SCENARIO_RESOURCE)
    _verify_local_resource(
        document,
        "observation_schema",
        OBSERVATION_SCHEMA_RESOURCE,
    )
    return deepcopy(document)


def _verify_local_resource(
    binding: dict[str, Any],
    resource_key: str,
    filename: str,
) -> None:
    resources_by_name = binding.get("resources")
    if not isinstance(resources_by_name, dict):
        raise ContractBoundaryError("contract binding carries a resource map")
    resource = resources_by_name.get(resource_key)
    if not isinstance(resource, dict):
        raise ContractBoundaryError(f"contract binding carries {resource_key}")
    raw = _resource_bytes(filename)
    observed_digest = "sha256:" + sha256(raw).hexdigest()
    if observed_digest != resource.get("sha256"):
        raise ContractBoundaryError(
            f"{resource_key} matches its released byte digest; restore the bound snapshot"
        )
    document = strict_json_loads(raw)
    if canonical_digest(document) != resource.get("canonical_digest"):
        raise ContractBoundaryError(
            f"{resource_key} matches its released canonical digest; restore the bound snapshot"
        )


def load_golden_specimen_scenario() -> dict[str, Any]:
    binding = load_contract_binding()
    value = strict_json_loads(_resource_bytes(GOLDEN_SCENARIO_RESOURCE))
    if not isinstance(value, dict):
        raise ContractBoundaryError("golden scenario carries one JSON object")
    if value.get("scenario_version") != binding["contract_version"]:
        raise ContractBoundaryError("golden scenario uses contract version 1.0.0")
    if value.get("scenario_id") != "SCN-GOLDEN-SPECIMEN-001":
        raise ContractBoundaryError(
            "golden scenario retains SCN-GOLDEN-SPECIMEN-001 as its shared identity"
        )
    return value


def load_observation_schema() -> dict[str, Any]:
    load_contract_binding()
    value = strict_json_loads(_resource_bytes(OBSERVATION_SCHEMA_RESOURCE))
    if not isinstance(value, dict):
        raise ContractBoundaryError("observation schema carries one JSON object")
    return value


def contract_reference() -> dict[str, Any]:
    binding = load_contract_binding()
    return {
        "contract_version": binding["contract_version"],
        "distribution_version": binding["distribution"]["version"],
        "golden_scenario_document_digest": binding["resources"]["golden_scenario"][
            "canonical_digest"
        ],
        "golden_scenario_validated_model_digest": binding["resources"][
            "golden_scenario"
        ]["validated_model_digest"],
        "observation_schema_document_digest": binding["resources"][
            "observation_schema"
        ]["canonical_digest"],
    }


def project_observation_v1(value: Any) -> dict[str, Any]:
    """Project a local envelope onto the shared contract-v1 nucleus."""

    if not isinstance(value, dict):
        raise ContractBoundaryError("observation envelope requires one JSON object")
    _validate_json_value(value)
    document = deepcopy(value)
    version = document.get("envelope_version")
    if version not in {None, CONTRACT_VERSION, "1.2.0"}:
        raise ContractBoundaryError(
            "envelope_version maps through the released 1.0.0 compatibility boundary"
        )
    document["envelope_version"] = CONTRACT_VERSION
    source = document.get("source")
    if isinstance(source, dict):
        shared_source_fields = (
            "environment_id",
            "implementation_commit",
            "configuration_digest",
        )
        document["source"] = {
            field: source[field]
            for field in shared_source_fields
            if field in source
        }
    return document


def validate_observation_compatibility(value: Any) -> dict[str, Any]:
    """Validate shared fields while retaining the richer local envelope."""

    validate_observation_v1(project_observation_v1(value))
    return deepcopy(value)


def validate_observation_v1(value: Any) -> dict[str, Any]:
    """Validate the standalone compatibility surface for envelope contract v1."""

    if not isinstance(value, dict):
        raise ContractBoundaryError("observation envelope requires one JSON object")
    _validate_json_value(value)
    document = deepcopy(value)
    document.setdefault("envelope_version", CONTRACT_VERSION)
    document.setdefault("approvals", [])
    fields = {
        "envelope_version",
        "observation_id",
        "evidence_mode",
        "assurance_stage",
        "scenario_id",
        "source",
        "result",
        "provenance",
        "approvals",
        "classification",
    }
    _require_exact_fields(document, fields, "observation envelope")
    if document["envelope_version"] != CONTRACT_VERSION:
        raise ContractBoundaryError("envelope_version uses the released 1.0.0 contract")
    _require_pattern(document["observation_id"], _UPPER_IDENTIFIER, "observation_id")
    _require_pattern(document["scenario_id"], _UPPER_IDENTIFIER, "scenario_id")
    _require_member(document["evidence_mode"], EVIDENCE_MODES, "evidence_mode")
    _require_member(document["assurance_stage"], ASSURANCE_STAGES, "assurance_stage")
    if not isinstance(document["result"], dict):
        raise ContractBoundaryError("result carries one JSON object")

    source = _require_object(document["source"], "source")
    _require_exact_fields(
        source,
        {"environment_id", "implementation_commit", "configuration_digest"},
        "source",
    )
    _require_pattern(source["environment_id"], _IDENTIFIER, "environment_id")
    if not isinstance(source["implementation_commit"], str):
        raise ContractBoundaryError("implementation_commit carries a source identity")
    source["implementation_commit"] = source["implementation_commit"].strip()
    if not source["implementation_commit"]:
        raise ContractBoundaryError("implementation_commit carries a source identity")
    _require_pattern(source["configuration_digest"], _SHA256, "configuration_digest")

    provenance = _require_object(document["provenance"], "provenance")
    _require_exact_fields(
        provenance,
        {"raw_artifact_digest", "governed_locator", "performed_by", "reviewed_by"},
        "provenance",
    )
    _require_pattern(provenance["raw_artifact_digest"], _SHA256, "raw_artifact_digest")
    if isinstance(provenance["governed_locator"], str):
        provenance["governed_locator"] = provenance["governed_locator"].strip()
    _require_pattern(provenance["governed_locator"], _URI, "governed_locator")
    _require_pattern(provenance["performed_by"], _IDENTIFIER, "performed_by")
    _require_pattern(provenance["reviewed_by"], _IDENTIFIER, "reviewed_by")
    if provenance["performed_by"] == provenance["reviewed_by"]:
        raise ContractBoundaryError(
            "performed_by and reviewed_by carry distinct accountable identities"
        )

    approvals = document["approvals"]
    if not isinstance(approvals, list) or len(approvals) > 24:
        raise ContractBoundaryError("approvals carries at most 24 decision objects")
    for index, approval_value in enumerate(approvals):
        approval = _require_object(approval_value, f"approvals[{index}]")
        _require_exact_fields(
            approval,
            {"domain", "decision", "approver"},
            f"approvals[{index}]",
        )
        _require_member(
            approval["domain"],
            APPROVAL_DOMAINS,
            f"approvals[{index}].domain",
        )
        _require_member(
            approval["decision"],
            APPROVAL_DECISIONS,
            f"approvals[{index}].decision",
        )
        _require_pattern(
            approval["approver"],
            _IDENTIFIER,
            f"approvals[{index}].approver",
        )

    classification = _require_object(document["classification"], "classification")
    _require_exact_fields(
        classification,
        {"data_class", "redaction_status"},
        "classification",
    )
    _require_member(
        classification["data_class"],
        DATA_CLASSES,
        "classification.data_class",
    )
    _require_member(
        classification["redaction_status"],
        REDACTION_STATES,
        "classification.redaction_status",
    )

    if document["evidence_mode"] == "observed":
        _require_pattern(
            source["implementation_commit"],
            _OBSERVED_COMMIT,
            "observed implementation_commit",
        )
        _require_pattern(
            provenance["governed_locator"],
            _OBSERVED_LOCATOR,
            "observed governed_locator",
        )
        if classification["redaction_status"] != "reviewed-redacted-manifest":
            raise ContractBoundaryError(
                "observed evidence carries a reviewed-redacted manifest"
            )
    if document["assurance_stage"] == "accepted" and not approvals:
        raise ContractBoundaryError(
            "accepted evidence carries at least one accountable approval"
        )
    return document


def verify_shared_package() -> dict[str, Any]:
    """Prove the optional installed package matches the standalone snapshots."""

    shared = importlib.import_module("lims_eln_contracts")
    if getattr(shared, "__version__", None) != CONTRACT_DISTRIBUTION_VERSION:
        raise ContractBoundaryError(
            "installed contract distribution matches version "
            f"{CONTRACT_DISTRIBUTION_VERSION}"
        )
    if getattr(shared, "CONTRACT_VERSION", None) != CONTRACT_VERSION:
        raise ContractBoundaryError("installed contract API matches version 1.0.0")
    shared_resources = importlib.import_module("lims_eln_contracts.resources")
    shared_root = resources.files("lims_eln_contracts").joinpath("resources")
    shared_scenario = shared_root.joinpath("scenarios").joinpath(
        GOLDEN_SCENARIO_RESOURCE
    )
    shared_schema = shared_resources.generated_schema_bytes(
        "observation-envelope.v1.schema.json"
    )
    if shared_scenario.read_bytes() != _resource_bytes(GOLDEN_SCENARIO_RESOURCE):
        raise ContractBoundaryError(
            "installed golden scenario matches the bound standalone snapshot"
        )
    if shared_schema != _resource_bytes(OBSERVATION_SCHEMA_RESOURCE):
        raise ContractBoundaryError(
            "installed observation schema matches the bound standalone snapshot"
        )
    shared_model = shared_resources.load_golden_specimen_scenario()
    expected_model_digest = load_contract_binding()["resources"]["golden_scenario"][
        "validated_model_digest"
    ]
    if shared.canonical_sha256(shared_model) != expected_model_digest:
        raise ContractBoundaryError(
            "installed golden scenario validates to the released model digest"
        )
    return contract_reference()


def validate_with_shared_package(value: dict[str, Any]) -> dict[str, Any]:
    """Validate one value through the optional authoritative Pydantic boundary."""

    verify_shared_package()
    shared = importlib.import_module("lims_eln_contracts")
    projection = project_observation_v1(value)
    model = shared.ObservationEnvelope.model_validate_json(
        canonical_json_bytes(projection),
        strict=True,
    )
    return model.model_dump(mode="json")


def _require_object(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ContractBoundaryError(f"{field} carries one JSON object")
    return value


def _require_exact_fields(
    value: dict[str, Any],
    required: set[str],
    field: str,
) -> None:
    missing = sorted(required - value.keys())
    extra = sorted(value.keys() - required)
    if missing:
        raise ContractBoundaryError(f"{field} requires fields: {', '.join(missing)}")
    if extra:
        raise ContractBoundaryError(
            f"{field} fields use the released contract: {', '.join(extra)}"
        )


def _require_pattern(value: Any, pattern: re.Pattern[str], field: str) -> None:
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise ContractBoundaryError(f"{field} uses the released contract shape")


def _require_member(value: Any, choices: frozenset[str], field: str) -> None:
    if not isinstance(value, str) or value not in choices:
        raise ContractBoundaryError(f"{field} uses a released contract value")


def _validate_json_value(value: Any, path: str = "$") -> None:
    if value is None or isinstance(value, (bool, int, str)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ContractBoundaryError(f"{path} carries a finite JSON number")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_json_value(item, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ContractBoundaryError(f"{path} carries textual JSON object keys")
            _validate_json_value(item, f"{path}.{key}")
        return
    raise ContractBoundaryError(f"{path} carries a JSON-compatible value")
