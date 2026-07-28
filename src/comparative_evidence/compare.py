from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

from .gate import validate_for_accepted
from .model import ObservationEnvelope, digest
from .normalize import normalize, path_value
from .safety import (
    EvidenceSafetyError,
    validate_commit,
    validate_digest,
    validate_observation_id,
    validate_repository_safe_content,
)
from .simulated_closure import (
    TRUSTED_CLOSURE_ID,
    TRUSTED_FUTURE_REALITY_VERSION,
    TRUSTED_GOVERNANCE_CLOSURE_DIGEST,
    TRUSTED_SOURCE_COORDINATES,
)


COMPARATOR_RELEASE = "0.3.1"
COMPARISON_CONTRACT_VERSION = "1.1.0"
TRUSTED_AGGREGATE_ARTIFACT_DIGEST = (
    "sha256:2d8e67ec2da8236fc23de7943e7727d2b74e0e6ee2b15afd9c765443b9c52b61"
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
    comparison: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "expected": self.expected,
            "actual": self.actual,
            "classification": self.classification,
            "rationale": self.rationale,
            "critical": self.critical,
            "value_visibility": self.value_visibility,
            "comparison": self.comparison,
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
    required_paths = set(profile["required_paths"])
    critical_paths = set(profile["critical_exact_paths"])
    tolerances = profile.get("numeric_tolerances", {})
    dispositions = profile.get("adjudications", {})
    reportable_paths = set(profile.get("reportable_paths", []))

    paths = sorted(
        set(_leaf_paths(expected))
        | set(_leaf_paths(observed))
        | required_paths
    )
    differences: list[Difference] = []
    converged = 0
    for path in paths:
        expected_present, expected_value = _optional_path(expected, path)
        actual_present, actual_value = _optional_path(observed, path)
        if path in required_paths and not (expected_present and actual_present):
            missing_sides = [
                side
                for side, present in (
                    ("simulation", expected_present),
                    ("observed", actual_present),
                )
                if not present
            ]
            differences.append(
                Difference(
                    path=path,
                    expected=_report_value(path, expected_value, reportable_paths),
                    actual=_report_value(path, actual_value, reportable_paths),
                    classification="shared_specification_violation",
                    rationale=(
                        "Required comparison evidence is absent from "
                        + " and ".join(missing_sides)
                        + "; restore the released result path before adjudication."
                    ),
                    critical=path in critical_paths,
                    value_visibility=(
                        "explicit" if path in reportable_paths else "digest_only"
                    ),
                    comparison={
                        "mode": "required_presence",
                        "missing_sides": missing_sides,
                    },
                )
            )
            continue
        if _equivalent(expected_value, actual_value, tolerances.get(path)):
            converged += 1
            continue
        disposition = dispositions.get(path, {})
        classification, rationale, comparison = _classify_difference(
            path,
            expected_value,
            actual_value,
            disposition,
            critical=path in critical_paths,
        )
        if classification not in CLASSIFICATIONS:
            raise ValueError(f"comparison classification {classification!r} requires a released value")
        differences.append(
            Difference(
                path=path,
                expected=_report_value(path, expected_value, reportable_paths),
                actual=_report_value(path, actual_value, reportable_paths),
                classification=classification,
                rationale=rationale,
                critical=path in critical_paths,
                value_visibility="explicit" if path in reportable_paths else "digest_only",
                comparison=(
                    comparison
                    if path in reportable_paths
                    else {
                        key: value
                        for key, value in comparison.items()
                        if key not in {"delta", "relative_delta"}
                    }
                ),
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
        "comparator_release": COMPARATOR_RELEASE,
        "comparison_contract_version": COMPARISON_CONTRACT_VERSION,
        "scenario_id": actual.scenario_id,
        "simulation": {
            "observation_id": simulation.observation_id,
            "evidence_mode": simulation.evidence_mode,
            "digest": simulation.content_digest,
            "future_reality_version": simulation.source["future_reality_version"],
            "closure_id": simulation.source["closure_id"],
            "governance_closure_digest": simulation.source[
                "governance_closure_digest"
            ],
            "aggregate_artifact_digest": simulation.source[
                "aggregate_artifact_digest"
            ],
            "simulation_commit": simulation.source["simulation_commit"],
            "implementation_commit": simulation.source[
                "implementation_commit"
            ],
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
    _validate_profile(profile)
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
    _validate_simulation_binding(simulation)


def _validate_profile(profile: dict[str, Any]) -> None:
    allowed = {
        "profile_version",
        "scenario_id",
        "required_paths",
        "critical_exact_paths",
        "declared_nondeterminism",
        "numeric_tolerances",
        "reportable_paths",
        "adjudications",
    }
    if set(profile) != allowed:
        unexpected = sorted(set(profile) - allowed)
        missing = sorted(allowed - set(profile))
        detail = []
        if missing:
            detail.append("missing " + ", ".join(missing))
        if unexpected:
            detail.append("unreleased " + ", ".join(unexpected))
        raise ValueError("comparison profile fields require " + "; ".join(detail))
    if profile["profile_version"] != COMPARISON_CONTRACT_VERSION:
        raise ValueError(
            f"comparison profile requires the released {COMPARISON_CONTRACT_VERSION} contract"
        )
    for field in (
        "required_paths",
        "critical_exact_paths",
        "declared_nondeterminism",
        "reportable_paths",
    ):
        paths = profile[field]
        if (
            not isinstance(paths, list)
            or len(paths) != len(set(paths))
            or not all(isinstance(path, str) and path.startswith("$.") for path in paths)
        ):
            raise ValueError(f"{field} requires unique released result paths")
    if not isinstance(profile["numeric_tolerances"], dict):
        raise ValueError("numeric_tolerances requires an object")
    if not isinstance(profile["adjudications"], dict):
        raise ValueError("adjudications requires an object")
    configured = (
        set(profile["critical_exact_paths"])
        | set(profile["numeric_tolerances"])
        | set(profile["reportable_paths"])
        | set(profile["adjudications"])
    )
    missing_required = sorted(configured - set(profile["required_paths"]))
    if missing_required:
        raise ValueError(
            "required_paths requires every governed comparison path: "
            + ", ".join(missing_required)
        )
    for path, disposition in profile["adjudications"].items():
        if not isinstance(disposition, dict):
            raise ValueError(f"adjudication {path} requires an object")
        expected_fields = {
            "direction",
            "favorable_classification",
            "unfavorable_classification",
            "favorable_rationale",
            "unfavorable_rationale",
        }
        if set(disposition) != expected_fields:
            raise ValueError(
                f"adjudication {path} requires directional released fields"
            )
        if disposition["direction"] not in {"lower_is_better", "higher_is_better"}:
            raise ValueError(
                f"adjudication {path}.direction requires lower_is_better or higher_is_better"
            )
        for field in ("favorable_classification", "unfavorable_classification"):
            if disposition[field] not in CLASSIFICATIONS:
                raise ValueError(
                    f"adjudication {path}.{field} requires a released classification"
                )
        for field in ("favorable_rationale", "unfavorable_rationale"):
            if not isinstance(disposition[field], str) or not disposition[field].strip():
                raise ValueError(
                    f"adjudication {path}.{field} requires accountable rationale"
                )


def _validate_simulation_binding(simulation: ObservationEnvelope) -> None:
    expected = {
        "environment_id": "simulated-final-state",
        "simulation_commit": TRUSTED_SOURCE_COORDINATES[0]["commit"],
        "implementation_commit": TRUSTED_SOURCE_COORDINATES[1]["commit"],
        "future_reality_version": TRUSTED_FUTURE_REALITY_VERSION,
        "closure_id": TRUSTED_CLOSURE_ID,
        "governance_closure_digest": TRUSTED_GOVERNANCE_CLOSURE_DIGEST,
        "aggregate_artifact_digest": TRUSTED_AGGREGATE_ARTIFACT_DIGEST,
    }
    missing = sorted(set(expected) - simulation.source.keys())
    if missing:
        raise ValueError(
            "simulation source requires canonical selected-future binding: "
            + ", ".join(missing)
        )
    for field, value in expected.items():
        if simulation.source.get(field) != value:
            raise ValueError(
                f"simulation source {field} differs from the trusted selected-future release"
            )
    validate_commit(simulation.source["simulation_commit"])
    validate_commit(simulation.source["implementation_commit"])
    for field in (
        "configuration_digest",
        "governance_closure_digest",
        "aggregate_artifact_digest",
    ):
        validate_digest(simulation.source[field], field)
    if (
        simulation.provenance.get("raw_artifact_digest")
        != TRUSTED_AGGREGATE_ARTIFACT_DIGEST
    ):
        raise ValueError(
            "simulation provenance requires the trusted aggregate artifact digest"
        )


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


def _optional_path(value: dict[str, Any], path: str) -> tuple[bool, Any]:
    try:
        return True, path_value(value, path)
    except (KeyError, IndexError, TypeError):
        return False, {"comparison_disposition": "value_absent"}


def _equivalent(expected: Any, actual: Any, tolerance: dict[str, float] | None) -> bool:
    if tolerance and isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        absolute = tolerance.get("absolute", 0.0)
        relative = tolerance.get("relative", 0.0)
        return abs(actual - expected) <= max(absolute, relative * abs(expected))
    return expected == actual


def _classify_difference(
    path: str,
    expected: Any,
    actual: Any,
    disposition: dict[str, Any],
    *,
    critical: bool,
) -> tuple[str, str, dict[str, Any]]:
    if not disposition:
        return (
            "actual_defect" if critical else "comparison_inconclusive",
            "Independent adjudication is required for this material difference.",
            {"mode": "exact"},
        )
    if (
        not isinstance(expected, (int, float))
        or isinstance(expected, bool)
        or not isinstance(actual, (int, float))
        or isinstance(actual, bool)
    ):
        return (
            "comparison_inconclusive",
            f"Directional adjudication at {path} requires finite numeric values.",
            {"mode": disposition["direction"], "outcome": "non_numeric"},
        )
    direction = disposition["direction"]
    favorable = (
        actual < expected
        if direction == "lower_is_better"
        else actual > expected
    )
    delta = actual - expected
    relative_delta = None if expected == 0 else delta / abs(expected)
    side = "favorable" if favorable else "unfavorable"
    return (
        disposition[f"{side}_classification"],
        disposition[f"{side}_rationale"],
        {
            "mode": direction,
            "outcome": side,
            "delta": delta,
            "relative_delta": relative_delta,
        },
    )
