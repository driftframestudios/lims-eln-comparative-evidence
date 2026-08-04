from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
import json
from types import MappingProxyType
from typing import Any

from .contracts import validate_document


class RecordError(ValueError):
    """An evidence record receives a precise contract correction."""


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
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def digest(value: Any) -> str:
    return f"sha256:{sha256(canonical_json(value).encode()).hexdigest()}"


def strict_json_loads(content: str) -> Any:
    return json.loads(
        content,
        parse_constant=_reject_nonfinite,
        object_pairs_hook=_unique_object,
    )


def _reject_nonfinite(value: str) -> None:
    raise RecordError(f"JSON numeric value {value} requires a finite representation")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise RecordError(f"JSON object key {key!r} requires one definition")
        result[key] = value
    return result


@dataclass(frozen=True)
class EvidenceRecord:
    record_version: str
    record_id: str
    scenario_id: str
    vendor: str
    product_version: str
    context: Mapping[str, Any]
    observed_at: str
    source_refs: tuple[Mapping[str, Any], ...]
    result: Mapping[str, Any]
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "context", _deep_freeze(self.context))
        object.__setattr__(self, "source_refs", _deep_freeze(self.source_refs))
        object.__setattr__(self, "result", _deep_freeze(self.result))
        object.__setattr__(self, "limitations", tuple(self.limitations))

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "EvidenceRecord":
        validate_document(value, "evidence-record.schema.json")
        return cls(
            record_version=value["record_version"],
            record_id=value["record_id"],
            scenario_id=value["scenario_id"],
            vendor=value["vendor"],
            product_version=value["product_version"],
            context=value["context"],
            observed_at=value["observed_at"],
            source_refs=tuple(value["source_refs"]),
            result=value["result"],
            limitations=tuple(value["limitations"]),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "record_version": self.record_version,
            "record_id": self.record_id,
            "scenario_id": self.scenario_id,
            "vendor": self.vendor,
            "product_version": self.product_version,
            "context": _deep_thaw(self.context),
            "observed_at": self.observed_at,
            "source_refs": _deep_thaw(self.source_refs),
            "result": _deep_thaw(self.result),
            "limitations": list(self.limitations),
        }

    @property
    def content_digest(self) -> str:
        return digest(self.as_dict())
