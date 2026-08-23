from __future__ import annotations

from copy import deepcopy
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from .contract_v1 import (
    ASSURANCE_STAGES,
    ContractBoundaryError,
    EVIDENCE_MODES,
    canonical_digest,
    canonical_json_bytes,
    strict_json_loads,
    validate_observation_compatibility,
)


class EnvelopeError(ContractBoundaryError):
    """An envelope receives a precise correction requirement."""


def _deep_freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {key: _deep_freeze(item) for key, item in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_deep_freeze(item) for item in value)
    return deepcopy(value)


def _deep_thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _deep_thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_deep_thaw(item) for item in value]
    return deepcopy(value)


def canonical_json(value: Any) -> str:
    return canonical_json_bytes(value).decode("utf-8")


def digest(value: Any) -> str:
    return canonical_digest(value)


@dataclass(frozen=True)
class ObservationEnvelope:
    envelope_version: str
    observation_id: str
    evidence_mode: str
    assurance_stage: str
    scenario_id: str
    source: Mapping[str, Any]
    result: Mapping[str, Any]
    provenance: Mapping[str, Any]
    approvals: tuple[Mapping[str, Any], ...]
    classification: Mapping[str, Any]

    def __post_init__(self) -> None:
        for field in ("source", "result", "provenance", "classification"):
            object.__setattr__(self, field, _deep_freeze(getattr(self, field)))
        object.__setattr__(self, "approvals", _deep_freeze(self.approvals))

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ObservationEnvelope":
        if not isinstance(value, dict):
            raise EnvelopeError("envelope requires a JSON object")
        required = {
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
        missing = sorted(required - value.keys())
        if missing:
            raise EnvelopeError(f"envelope requires fields: {', '.join(missing)}")
        extra = sorted(value.keys() - required)
        if extra:
            raise EnvelopeError(f"envelope fields require a released definition: {', '.join(extra)}")
        if value["envelope_version"] != "1.2.0":
            raise EnvelopeError("envelope_version requires the released 1.2.0 contract")
        if value["evidence_mode"] not in EVIDENCE_MODES:
            raise EnvelopeError("evidence_mode requires planned, simulated, or observed")
        if value["assurance_stage"] not in ASSURANCE_STAGES:
            raise EnvelopeError("assurance_stage requires a released assurance-stage value")
        for field in ("observation_id", "scenario_id"):
            if not isinstance(value[field], str) or not value[field].strip():
                raise EnvelopeError(f"{field} requires a bounded textual identity")
        for field in ("source", "result", "provenance", "classification"):
            if not isinstance(value[field], dict):
                raise EnvelopeError(f"{field} requires a JSON object")
        source_fields = {
            "environment_id",
            "implementation_commit",
            "simulation_commit",
            "configuration_digest",
            "database_release",
            "future_reality_version",
            "closure_id",
            "governance_closure_digest",
            "aggregate_artifact_digest",
        }
        extra_source_fields = sorted(value["source"].keys() - source_fields)
        if extra_source_fields:
            raise EnvelopeError(
                "source fields use the released contract: "
                + ", ".join(extra_source_fields)
            )
        if not isinstance(value["approvals"], list) or not all(
            isinstance(item, dict) for item in value["approvals"]
        ):
            raise EnvelopeError("approvals requires an array of decision objects")
        try:
            document = validate_observation_compatibility(value)
        except ContractBoundaryError as error:
            raise EnvelopeError(str(error)) from error
        return cls(
            envelope_version=document["envelope_version"],
            observation_id=document["observation_id"],
            evidence_mode=document["evidence_mode"],
            assurance_stage=document["assurance_stage"],
            scenario_id=document["scenario_id"],
            source=document["source"],
            result=document["result"],
            provenance=document["provenance"],
            approvals=tuple(document["approvals"]),
            classification=document["classification"],
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "envelope_version": self.envelope_version,
            "observation_id": self.observation_id,
            "evidence_mode": self.evidence_mode,
            "assurance_stage": self.assurance_stage,
            "scenario_id": self.scenario_id,
            "source": _deep_thaw(self.source),
            "result": _deep_thaw(self.result),
            "provenance": _deep_thaw(self.provenance),
            "approvals": _deep_thaw(self.approvals),
            "classification": _deep_thaw(self.classification),
        }

    @property
    def content_digest(self) -> str:
        return digest(self.as_dict())
