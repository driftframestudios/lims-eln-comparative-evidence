from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

from .contracts import validate_document
from .model import EvidenceRecord, digest
from .normalize import normalize


COMPARATOR_RELEASE = "0.4.0"
CLASSIFICATIONS = {
    "candidate_advantage",
    "candidate_gap",
    "context_difference",
    "missing_measurement",
}


@dataclass(frozen=True)
class Difference:
    path: str
    reference: Any
    candidate: Any
    classification: str
    rationale: str
    critical: bool
    value_visibility: str
    comparison: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "reference": self.reference,
            "candidate": self.candidate,
            "classification": self.classification,
            "rationale": self.rationale,
            "critical": self.critical,
            "value_visibility": self.value_visibility,
            "comparison": self.comparison,
        }


def compare(
    reference: EvidenceRecord,
    candidate: EvidenceRecord,
    profile: dict[str, Any],
) -> dict[str, Any]:
    """Compare two caller-supplied records against one released profile."""

    validate_document(profile, "comparison-profile.schema.json")
    _validate_pair(reference, candidate, profile)

    ignored = set(profile["ignored_paths"])
    expected = normalize(reference.result, ignored)
    observed = normalize(candidate.result, ignored)
    required_paths = set(profile["required_paths"])
    critical_paths = set(profile["critical_exact_paths"])
    tolerances = profile["numeric_tolerances"]
    adjudications = profile["adjudications"]
    reportable_paths = set(profile["reportable_paths"])

    paths = sorted(
        _leaf_paths(expected) | _leaf_paths(observed) | required_paths
    )
    differences: list[Difference] = []
    matched = 0

    for path in paths:
        reference_present, reference_value = _optional_path(expected, path)
        candidate_present, candidate_value = _optional_path(observed, path)
        if path in required_paths and not (
            reference_present and candidate_present
        ):
            missing = [
                side
                for side, present in (
                    ("reference", reference_present),
                    ("candidate", candidate_present),
                )
                if not present
            ]
            differences.append(
                Difference(
                    path=path,
                    reference=_report_value(
                        path,
                        reference_value,
                        reference_present,
                        reportable_paths,
                    ),
                    candidate=_report_value(
                        path,
                        candidate_value,
                        candidate_present,
                        reportable_paths,
                    ),
                    classification="missing_measurement",
                    rationale=(
                        "The released comparison profile requires this measurement. "
                        "Required input pending from: "
                        + " and ".join(missing)
                        + "."
                    ),
                    critical=path in critical_paths,
                    value_visibility=_visibility(path, reportable_paths),
                    comparison={"mode": "required_presence", "missing": missing},
                )
            )
            continue

        if not reference_present or not candidate_present:
            differences.append(
                Difference(
                    path=path,
                    reference=_report_value(
                        path,
                        reference_value,
                        reference_present,
                        reportable_paths,
                    ),
                    candidate=_report_value(
                        path,
                        candidate_value,
                        candidate_present,
                        reportable_paths,
                    ),
                    classification="context_difference",
                    rationale="This optional result appears on one comparison side.",
                    critical=False,
                    value_visibility=_visibility(path, reportable_paths),
                    comparison={"mode": "optional_presence"},
                )
            )
            continue

        tolerance = tolerances.get(path)
        if _equivalent(reference_value, candidate_value, tolerance):
            matched += 1
            continue

        classification, rationale, comparison = _classify_difference(
            reference_value,
            candidate_value,
            adjudications.get(path),
            critical=path in critical_paths,
        )
        differences.append(
            Difference(
                path=path,
                reference=_report_value(
                    path,
                    reference_value,
                    True,
                    reportable_paths,
                ),
                candidate=_report_value(
                    path,
                    candidate_value,
                    True,
                    reportable_paths,
                ),
                classification=classification,
                rationale=rationale,
                critical=path in critical_paths,
                value_visibility=_visibility(path, reportable_paths),
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
        "matched_paths": matched,
        "material_differences": len(differences),
        "critical_differences": sum(item.critical for item in differences),
        "classification_counts": {
            name: sum(item.classification == name for item in differences)
            for name in sorted(CLASSIFICATIONS)
            if any(item.classification == name for item in differences)
        },
    }
    report: dict[str, Any] = {
        "comparator_release": COMPARATOR_RELEASE,
        "profile_version": profile["profile_version"],
        "profile_digest": digest(profile),
        "scenario_id": reference.scenario_id,
        "reference": _record_summary(reference),
        "candidate": _record_summary(candidate),
        "summary": summary,
        "differences": [item.as_dict() for item in differences],
    }
    report["report_digest"] = digest(report)
    return report


def _validate_pair(
    reference: EvidenceRecord,
    candidate: EvidenceRecord,
    profile: dict[str, Any],
) -> None:
    if reference.scenario_id != candidate.scenario_id:
        raise ValueError("reference and candidate require the same scenario_id")
    if profile["scenario_id"] != reference.scenario_id:
        raise ValueError("comparison profile requires the paired scenario_id")
    required = set(profile["required_paths"])
    critical = set(profile["critical_exact_paths"])
    ignored = set(profile["ignored_paths"])
    tolerated = set(profile["numeric_tolerances"])
    reportable = set(profile["reportable_paths"])
    adjudicated = set(profile["adjudications"])
    if not critical <= required:
        raise ValueError("critical paths require membership in required_paths")
    if critical & (ignored | tolerated):
        raise ValueError("critical paths require deterministic exact comparison")
    if not (tolerated | adjudicated | reportable) <= required:
        raise ValueError(
            "tolerance, adjudication, and reportable paths require membership "
            "in required_paths"
        )
    if set(profile["numeric_tolerances"]) != set(profile["adjudications"]):
        raise ValueError("numeric tolerance paths require an adjudication direction")


def _record_summary(record: EvidenceRecord) -> dict[str, Any]:
    return {
        "record_id": record.record_id,
        "vendor": record.vendor,
        "product_version": record.product_version,
        "evidence_level": record.context["evidence_level"],
        "environment_id": record.context["environment_id"],
        "observed_at": record.observed_at,
        "record_digest": record.content_digest,
        "limitations": list(record.limitations),
        "source_refs": [
            {
                "source_kind": item["source_kind"],
                "title": item["title"],
                "locator": item["locator"],
            }
            for item in record.source_refs
        ],
    }


def _leaf_paths(value: Any, path: str = "$") -> set[str]:
    if isinstance(value, dict):
        paths: set[str] = set()
        for key, item in value.items():
            paths |= _leaf_paths(item, f"{path}.{key}")
        return paths
    if isinstance(value, (list, tuple)):
        paths = set()
        for index, item in enumerate(value):
            paths |= _leaf_paths(item, f"{path}.{index}")
        return paths
    return {path}


def _optional_path(value: Any, path: str) -> tuple[bool, Any]:
    current = value
    for segment in path.removeprefix("$.").split("."):
        if isinstance(current, dict) and segment in current:
            current = current[segment]
            continue
        if isinstance(current, (list, tuple)) and segment.isdigit():
            index = int(segment)
            if index < len(current):
                current = current[index]
                continue
        return False, None
    return True, current


def _equivalent(
    reference: Any,
    candidate: Any,
    tolerance: dict[str, float] | None,
) -> bool:
    if tolerance is None:
        return type(reference) is type(candidate) and reference == candidate
    if not (_is_json_number(reference) and _is_json_number(candidate)):
        return False
    reference_number = float(reference)
    candidate_number = float(candidate)
    if not (math.isfinite(reference_number) and math.isfinite(candidate_number)):
        return False
    delta = abs(candidate_number - reference_number)
    scale = abs(reference_number)
    return delta <= max(
        float(tolerance["absolute"]),
        float(tolerance["relative"]) * scale,
    )


def _is_json_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _classify_difference(
    reference: Any,
    candidate: Any,
    adjudication: dict[str, Any] | None,
    *,
    critical: bool,
) -> tuple[str, str, dict[str, Any]]:
    if adjudication and _is_json_number(reference) and _is_json_number(candidate):
        reference_number = float(reference)
        candidate_number = float(candidate)
        delta = candidate_number - reference_number
        relative_delta = (
            delta / abs(reference_number) if reference_number else None
        )
        direction = adjudication["direction"]
        advantage = (
            candidate_number < reference_number
            if direction == "lower_is_better"
            else candidate_number > reference_number
        )
        return (
            "candidate_advantage" if advantage else "candidate_gap",
            (
                adjudication["advantage_rationale"]
                if advantage
                else adjudication["gap_rationale"]
            ),
            {
                "mode": direction,
                "delta": delta,
                "relative_delta": relative_delta,
            },
        )
    if critical:
        return (
            "candidate_gap",
            "The candidate differs from a required exact data or behavior contract.",
            {"mode": "critical_exact"},
        )
    return (
        "context_difference",
        "The records differ on a standard comparison path; source context and "
        "limitation notes support interpretation.",
        {"mode": "exact"},
    )


def _visibility(path: str, reportable_paths: set[str]) -> str:
    return "explicit" if path in reportable_paths else "digest_only"


def _report_value(
    path: str,
    value: Any,
    present: bool,
    reportable_paths: set[str],
) -> Any:
    if not present:
        return {"state": "missing"}
    if path in reportable_paths:
        return value
    return {"content_digest": digest(value)}
