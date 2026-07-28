from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any


EVIDENCE_MODES = {"planned", "simulated", "observed"}
ASSURANCE_STAGES = {"specified", "verified", "qualified", "validated", "accepted"}


class EnvelopeError(ValueError):
    """An envelope receives a precise correction requirement."""


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def strict_json_loads(content: str) -> Any:
    return json.loads(
        content,
        parse_constant=_reject_nonfinite,
        object_pairs_hook=_unique_object,
    )


def _reject_nonfinite(value: str) -> None:
    raise EnvelopeError(f"JSON numeric value {value} requires a finite representation")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise EnvelopeError(f"JSON object key {key!r} requires a single definition")
        result[key] = value
    return result


def digest(value: Any) -> str:
    return f"sha256:{sha256(canonical_json(value).encode()).hexdigest()}"


@dataclass(frozen=True)
class ObservationEnvelope:
    envelope_version: str
    observation_id: str
    evidence_mode: str
    assurance_stage: str
    scenario_id: str
    source: dict[str, Any]
    result: dict[str, Any]
    provenance: dict[str, Any]
    approvals: tuple[dict[str, Any], ...]
    classification: dict[str, Any]

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
        if value["envelope_version"] != "1.1.0":
            raise EnvelopeError("envelope_version requires the released 1.1.0 contract")
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
        if not isinstance(value["approvals"], list) or not all(
            isinstance(item, dict) for item in value["approvals"]
        ):
            raise EnvelopeError("approvals requires an array of decision objects")
        return cls(
            envelope_version=value["envelope_version"],
            observation_id=value["observation_id"],
            evidence_mode=value["evidence_mode"],
            assurance_stage=value["assurance_stage"],
            scenario_id=value["scenario_id"],
            source=value["source"],
            result=value["result"],
            provenance=value["provenance"],
            approvals=tuple(value["approvals"]),
            classification=value["classification"],
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "envelope_version": self.envelope_version,
            "observation_id": self.observation_id,
            "evidence_mode": self.evidence_mode,
            "assurance_stage": self.assurance_stage,
            "scenario_id": self.scenario_id,
            "source": self.source,
            "result": self.result,
            "provenance": self.provenance,
            "approvals": list(self.approvals),
            "classification": self.classification,
        }

    @property
    def content_digest(self) -> str:
        return digest(self.as_dict())
