from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .model import ObservationEnvelope, digest
from .normalize import normalize, path_value


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

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "expected": self.expected,
            "actual": self.actual,
            "classification": self.classification,
            "rationale": self.rationale,
            "critical": self.critical,
        }


def compare(
    simulation: ObservationEnvelope,
    actual: ObservationEnvelope,
    profile: dict[str, Any],
) -> dict[str, Any]:
    if simulation.scenario_id != actual.scenario_id:
        raise ValueError("paired observations require the same scenario_id")

    ignored = set(profile.get("declared_nondeterminism", []))
    expected = normalize(simulation.result, ignored)
    observed = normalize(actual.result, ignored)
    critical_paths = set(profile.get("critical_exact_paths", []))
    tolerances = profile.get("numeric_tolerances", {})
    dispositions = profile.get("adjudications", {})

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
                expected=expected_value,
                actual=actual_value,
                classification=classification,
                rationale=disposition.get(
                    "rationale",
                    "Independent adjudication required for this material difference.",
                ),
                critical=path in critical_paths,
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
        "comparison_version": "1.0.0",
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

