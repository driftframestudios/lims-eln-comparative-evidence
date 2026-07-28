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
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


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
        if value["evidence_mode"] not in EVIDENCE_MODES:
            raise EnvelopeError("evidence_mode requires planned, simulated, or observed")
        if value["assurance_stage"] not in ASSURANCE_STAGES:
            raise EnvelopeError("assurance_stage requires a released assurance-stage value")
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

