from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

from .gate import validate_for_accepted
from .model import ObservationEnvelope, digest
from .normalize import normalize, path_value
from .safety import (
    EvidenceSafetyError,
    validate_observation_id,
    validate_repository_safe_content,
)


CLASSIFICATIONS = {
    "converged",
    "desired_divergence",
    "actual_gap",
    "actual_defect",
    "simulation_fault",
    "shared_specification_violation",
    "context_changed",
    "receipt_pending",
    "comparison_inconclusive",
}


@dataclass(frozen=True)
class Difference:
    path: str
    expected: Any
    actual: Any
    classification: str
    rationale: str
    critical: bool
    value_visibility: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "expected": self.expected,
            "actual": self.actual,
            "classification": self.classification,
            "rationale": self.rationale,
            "critical": self.critical,
            "value_visibility": self.value_visibility,
        }


def compare(
    simulation: ObservationEnvelope,
    actual: ObservationEnvelope,
    profile: dict[str, Any],
) -> dict[str, Any]:
    _validate_authority(simulation, actual, profile)
    if simulation.scenario_id != actual.scenario_id:
        raise ValueError("paired observations require the same scenario_id")

    ignored = set(profile.get("declared_nondeterminism", []))
    expected = normalize(simulation.result, ignored)
    observed = normalize(actual.result, ignored)
    critical_paths = set(profile.get("critical_exact_paths", []))
    tolerances = profile.get("numeric_tolerances", {})
    dispositions = profile.get("adjudications", {})
    reportable_paths = set(profile.get("reportable_paths", []))

    paths = sorted(set(_leaf_paths(expected)) | set(_leaf_paths(observed)))
    differences: list[Difference] = []
    converged = 0
    for path in paths:
        expected_value = _optional_path(expected, path)
        actual_value = _optional_path(observed, path)
        if _equivalent(expected_value, actual_value, tolerances.get(path)):
            converged += 1
            continue
        disposition = dispositions.get(path, {})
        classification = disposition.get(
            "classification",
            "actual_defect" if path in critical_paths else "comparison_inconclusive",
        )
        if classification not in CLASSIFICATIONS:
            raise ValueError(f"comparison classification {classification!r} requires a released value")
        differences.append(
            Difference(
                path=path,
                expected=_report_value(path, expected_value, reportable_paths),
                actual=_report_value(path, actual_value, reportable_paths),
                classification=classification,
                rationale=disposition.get(
                    "rationale",
                    "Independent adjudication required for this material difference.",
                ),
                critical=path in critical_paths,
                value_visibility="explicit" if path in reportable_paths else "digest_only",
            )
        )

    summary = {
        "leaf_paths_compared": len(paths),
        "converged_paths": converged,
        "material_differences": len(differences),
        "critical_differences": sum(item.critical for item in differences),
        "classification_counts": {
            name: sum(item.classification == name for item in differences)
            for name in sorted(CLASSIFICATIONS)
            if any(item.classification == name for item in differences)
        },
    }
    report = {
        "comparator_release": "0.3.0",
        "comparison_contract_version": "1.0.0",
        "scenario_id": actual.scenario_id,
        "simulation": {
            "observation_id": simulation.observation_id,
            "evidence_mode": simulation.evidence_mode,
            "digest": simulation.content_digest,
        },
        "actual": {
            "observation_id": actual.observation_id,
            "evidence_mode": actual.evidence_mode,
            "assurance_stage": actual.assurance_stage,
            "digest": actual.content_digest,
        },
        "profile_digest": digest(profile),
        "summary": summary,
        "differences": [item.as_dict() for item in differences],
    }
    report["report_digest"] = digest(report)
    return report


def _validate_authority(
    simulation: ObservationEnvelope,
    actual: ObservationEnvelope,
    profile: dict[str, Any],
) -> None:
    if simulation.evidence_mode != "simulated" or simulation.assurance_stage != "specified":
        raise ValueError("forecast input requires simulated evidence at the specified assurance stage")
    if actual.evidence_mode != "observed":
        raise ValueError("actual input requires observed evidence")
    if actual.assurance_stage not in {"verified", "qualified", "validated", "accepted"}:
        raise ValueError("actual input requires an observed assurance stage")
    if profile.get("profile_version") != "1.0.0":
        raise ValueError("comparison profile requires the released 1.0.0 contract")
    if profile.get("scenario_id") != simulation.scenario_id or profile.get("scenario_id") != actual.scenario_id:
        raise ValueError("comparison profile requires the paired scenario_id")

    critical = set(profile.get("critical_exact_paths", []))
    ignored = set(profile.get("declared_nondeterminism", []))
    tolerances = set(profile.get("numeric_tolerances", {}))
    if critical & ignored:
        raise ValueError("critical exact paths require deterministic comparison")
    if critical & tolerances:
        raise ValueError("critical exact paths require exact comparison")
    for path, tolerance in profile.get("numeric_tolerances", {}).items():
        if not isinstance(tolerance, dict):
            raise ValueError(f"numeric tolerance {path} requires an object")
        for name in ("absolute", "relative"):
            amount = tolerance.get(name, 0.0)
            if not isinstance(amount, (int, float)) or isinstance(amount, bool):
                raise ValueError(f"numeric tolerance {path}.{name} requires a number")
            if amount < 0 or not math.isfinite(amount):
                raise ValueError(f"numeric tolerance {path}.{name} requires a finite, nonnegative value")
    try:
        validate_observation_id(simulation.observation_id)
        validate_repository_safe_content(simulation.as_dict())
        validate_for_accepted(actual)
    except EvidenceSafetyError as error:
        raise ValueError(str(error)) from error


def _report_value(path: str, value: Any, reportable_paths: set[str]) -> Any:
    if path in reportable_paths:
        return value
    return {
        "classification": "redacted-comparison-value",
        "digest": digest(value),
    }


def _leaf_paths(value: Any, path: str = "$") -> list[str]:
    if isinstance(value, dict):
        paths: list[str] = []
        for key, item in value.items():
            paths.extend(_leaf_paths(item, f"{path}.{key}"))
        return paths
    if isinstance(value, list):
        paths = []
        for index, item in enumerate(value):
            paths.extend(_leaf_paths(item, f"{path}.{index}"))
        return paths
    return [path]


def _optional_path(value: dict[str, Any], path: str) -> Any:
    try:
        return path_value(value, path)
    except (KeyError, IndexError, TypeError):
        return {"comparison_disposition": "value_absent"}


def _equivalent(expected: Any, actual: Any, tolerance: dict[str, float] | None) -> bool:
    if tolerance and isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        absolute = tolerance.get("absolute", 0.0)
        relative = tolerance.get("relative", 0.0)
        return abs(actual - expected) <= max(absolute, relative * abs(expected))
    return expected == actual
