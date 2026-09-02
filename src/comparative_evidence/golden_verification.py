"""Compare the shared Golden Specimen projection from two simulated producers."""

from __future__ import annotations

from copy import deepcopy
import math
import re
from typing import Any

from .contract_v1 import (
    canonical_digest,
    validate_golden_specimen_observation,
)
from .normalize import path_value


COMPARISON_CONTRACT_VERSION = "1.0.0"
COMPARISON_MODE = "simulated_verification"

AGREEMENT = "agreement"
EXPLAINABLE_VARIATION = "explainable_variation"
MATERIAL_DIVERGENCE = "material_divergence"

PROJECTION_PATHS = frozenset(
    {
        "$.projection_id",
        "$.projection_version",
        "$.comparison_compatibility",
        "$.tenant_id",
        "$.specimen_id",
        "$.lifecycle.state",
        "$.lifecycle.aggregate_version",
        "$.custody.current_location",
        "$.measurement.analyte",
        "$.measurement.value",
        "$.measurement.unit",
        "$.measurement.quality_flag",
        "$.review_resolution.review_id",
        "$.review_resolution.decision",
        "$.review_resolution.resolved_at",
        "$.release.approval_receipt_id",
        "$.release.released_at",
    }
)

_PROFILE_FIELDS = {
    "profile_version",
    "scenario_id",
    "scenario_version",
    "scenario_digest",
    "projection_id",
    "projection_version",
    "comparison_compatibility",
    "comparison_paths",
}
_RULE_FIELDS = {"path", "divergence_classification", "rationale"}
_COMMIT = re.compile(r"^[a-f0-9]{40}$")
_TREE_DIGEST = re.compile(r"^git-tree-sha1:[a-f0-9]{40}$")
_SHA256 = re.compile(r"^sha256:[a-f0-9]{64}$")


def compare_golden_specimen(
    implementation: dict[str, Any],
    simulation: dict[str, Any],
    profile: dict[str, Any],
    constellation: dict[str, Any],
) -> dict[str, Any]:
    """Compare every closed shared-projection leaf under one explicit policy.

    Producer-owned detail is retained by canonical digest only. The report carries
    the source and accepted repository coordinate needed to recover that detail,
    while adjudication remains limited to ``result.projection``.
    """

    rules = _validate_profile(profile)
    implementation_document = validate_golden_specimen_observation(implementation)
    simulation_document = validate_golden_specimen_observation(simulation)
    _validate_authority(implementation_document, simulation_document)
    _validate_contract_coordinates(
        implementation_document,
        simulation_document,
        profile,
    )
    implementation_coordinate, simulation_coordinate = _validate_constellation(
        constellation,
        implementation_document,
        simulation_document,
    )

    implementation_projection = implementation_document["result"]["projection"]
    simulation_projection = simulation_document["result"]["projection"]
    comparisons: list[dict[str, Any]] = []
    for rule in rules:
        path = rule["path"]
        implementation_value = path_value(implementation_projection, path)
        simulation_value = path_value(simulation_projection, path)
        if _json_equal(implementation_value, simulation_value):
            classification = AGREEMENT
            rationale = (
                "Both producers report the same released projection value."
            )
        else:
            classification = rule["divergence_classification"]
            rationale = rule["rationale"]
        comparisons.append(
            {
                "path": path,
                "implementation": deepcopy(implementation_value),
                "simulation": deepcopy(simulation_value),
                "classification": classification,
                "rationale": rationale,
            }
        )

    classification_counts = {
        classification: sum(
            item["classification"] == classification for item in comparisons
        )
        for classification in (
            AGREEMENT,
            EXPLAINABLE_VARIATION,
            MATERIAL_DIVERGENCE,
        )
    }
    report = {
        "comparison_mode": COMPARISON_MODE,
        "comparison_contract_version": COMPARISON_CONTRACT_VERSION,
        "authority_posture": {
            "evidence_claim": "simulated_producer_verification",
            "environment_observed_closure": "separate_unasserted_state",
            "production_authorization_effect": "none",
        },
        "scenario_id": profile["scenario_id"],
        "scenario_version": profile["scenario_version"],
        "scenario_digest": profile["scenario_digest"],
        "projection_id": profile["projection_id"],
        "projection_version": profile["projection_version"],
        "comparison_compatibility": profile["comparison_compatibility"],
        "profile_digest": canonical_digest(profile),
        "constellation_digest": canonical_digest(constellation),
        "implementation": _producer_context(
            implementation_document,
            implementation_coordinate,
        ),
        "simulation": _producer_context(
            simulation_document,
            simulation_coordinate,
        ),
        "summary": {
            "leaf_paths_compared": len(comparisons),
            "classification_counts": classification_counts,
        },
        "comparisons": comparisons,
    }
    report["report_digest"] = canonical_digest(report)
    return report


def _validate_profile(profile: Any) -> list[dict[str, str]]:
    if not isinstance(profile, dict):
        raise ValueError("Golden Specimen profile requires one JSON object")
    if set(profile) != _PROFILE_FIELDS:
        _raise_field_difference(profile, _PROFILE_FIELDS, "Golden Specimen profile")
    expected = {
        "profile_version": COMPARISON_CONTRACT_VERSION,
        "scenario_id": "SCN-GOLDEN-SPECIMEN-001",
        "scenario_version": "1.0.0",
        "scenario_digest": (
            "sha256:fea95444dbbfbd3e26f5fb8d3975038541bf75bb1e4a7ffb748dd2cefdf173e9"
        ),
        "projection_id": "urn:driftframe:lims-eln:golden-specimen-result",
        "projection_version": "1.0.0",
        "comparison_compatibility": "exact-version",
    }
    for field, expected_value in expected.items():
        if profile.get(field) != expected_value:
            raise ValueError(
                f"Golden Specimen profile {field} requires {expected_value!r}"
            )

    values = profile["comparison_paths"]
    if not isinstance(values, list) or len(values) != len(PROJECTION_PATHS):
        raise ValueError(
            "Golden Specimen profile requires exactly 17 closed projection paths"
        )
    rules: list[dict[str, str]] = []
    for index, value in enumerate(values):
        label = f"Golden Specimen comparison_paths[{index}]"
        if not isinstance(value, dict):
            raise ValueError(f"{label} requires one JSON object")
        if set(value) != _RULE_FIELDS:
            _raise_field_difference(value, _RULE_FIELDS, label)
        path = value["path"]
        classification = value["divergence_classification"]
        rationale = value["rationale"]
        if path not in PROJECTION_PATHS:
            raise ValueError(f"{label}.path uses one released projection leaf")
        if classification not in {
            EXPLAINABLE_VARIATION,
            MATERIAL_DIVERGENCE,
        }:
            raise ValueError(
                f"{label}.divergence_classification requires an explicit "
                "variation or divergence"
            )
        if not isinstance(rationale, str) or not rationale.strip():
            raise ValueError(f"{label}.rationale requires a substantive explanation")
        rules.append(
            {
                "path": path,
                "divergence_classification": classification,
                "rationale": rationale.strip(),
            }
        )
    observed_paths = [rule["path"] for rule in rules]
    if len(set(observed_paths)) != len(observed_paths):
        raise ValueError("Golden Specimen profile requires each projection path once")
    if set(observed_paths) != PROJECTION_PATHS:
        missing = sorted(PROJECTION_PATHS - set(observed_paths))
        raise ValueError(
            "Golden Specimen profile requires every closed projection leaf: "
            + ", ".join(missing)
        )
    return rules


def _validate_authority(
    implementation: dict[str, Any],
    simulation: dict[str, Any],
) -> None:
    if (
        implementation["evidence_mode"] != "simulated"
        or implementation["assurance_stage"] != "verified"
    ):
        raise ValueError(
            "implementation input requires simulated evidence at the verified stage"
        )
    if (
        simulation["evidence_mode"] != "simulated"
        or simulation["assurance_stage"] != "specified"
    ):
        raise ValueError(
            "simulation input requires simulated evidence at the specified stage"
        )


def _validate_contract_coordinates(
    implementation: dict[str, Any],
    simulation: dict[str, Any],
    profile: dict[str, Any],
) -> None:
    for label, document in (
        ("implementation", implementation),
        ("simulation", simulation),
    ):
        for field in ("scenario_id", "scenario_version", "scenario_digest"):
            if document[field] != profile[field]:
                raise ValueError(
                    f"{label} {field} differs from the released comparison profile"
                )
        projection = document["result"]["projection"]
        for field in (
            "projection_id",
            "projection_version",
            "comparison_compatibility",
        ):
            if projection[field] != profile[field]:
                raise ValueError(
                    f"{label} {field} differs from the released comparison profile"
                )


def _validate_constellation(
    constellation: Any,
    implementation: dict[str, Any],
    simulation: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not isinstance(constellation, dict):
        raise ValueError("constellation requires one JSON object")
    implementation_coordinate = _accepted_coordinate(
        constellation.get("implementation"),
        "implementation",
    )
    simulation_coordinate = _accepted_coordinate(
        constellation.get("simulation"),
        "simulation",
    )

    simulation_source = simulation["source"].get("implementation_commit")
    if simulation_source != simulation_coordinate["release"]:
        raise ValueError(
            "simulation observation source differs from the accepted release"
        )
    implementation_release = implementation_coordinate["release"]
    version = implementation_release
    for prefix in ("implementation-v", "v"):
        if version.startswith(prefix):
            version = version.removeprefix(prefix)
            break
    accepted_implementation_sources = {
        implementation_release,
        f"lims-eln-enterprise-implementation@{version}",
    }
    if implementation["source"].get("implementation_commit") not in (
        accepted_implementation_sources
    ):
        raise ValueError(
            "implementation observation source differs from the accepted release"
        )

    _validate_optional_instance_binding(
        implementation_coordinate,
        implementation,
        "implementation",
    )
    _validate_optional_instance_binding(
        simulation_coordinate,
        simulation,
        "simulation",
    )
    return implementation_coordinate, simulation_coordinate


def _accepted_coordinate(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"constellation {label} requires one coordinate object")
    required = {"release", "commit", "digest", "coordinate_status"}
    missing = sorted(required - value.keys())
    if missing:
        raise ValueError(
            f"constellation {label} requires fields: {', '.join(missing)}"
        )
    if not isinstance(value["release"], str) or not value["release"].strip():
        raise ValueError(f"constellation {label} release requires text")
    if (
        not isinstance(value["commit"], str)
        or _COMMIT.fullmatch(value["commit"]) is None
        or value["commit"] == "0" * 40
    ):
        raise ValueError(f"constellation {label} commit requires an accepted Git object")
    if (
        not isinstance(value["digest"], str)
        or _TREE_DIGEST.fullmatch(value["digest"]) is None
        or value["digest"] == "git-tree-sha1:" + "0" * 40
    ):
        raise ValueError(f"constellation {label} digest requires an accepted Git tree")
    if value["coordinate_status"] != "release_observed":
        raise ValueError(
            f"constellation {label} coordinate requires release_observed status"
        )
    return deepcopy(value)


def _validate_optional_instance_binding(
    coordinate: dict[str, Any],
    document: dict[str, Any],
    label: str,
) -> None:
    observed = canonical_digest(document)
    for field in ("observation_digest", "reference_observation_digest"):
        expected = coordinate.get(field)
        if expected is not None:
            if not isinstance(expected, str) or _SHA256.fullmatch(expected) is None:
                raise ValueError(f"constellation {label} {field} requires SHA-256")
            if expected != observed:
                raise ValueError(
                    f"constellation {label} {field} differs from its observation"
                )
    projection_digest = coordinate.get("projection_digest")
    if projection_digest is not None:
        if (
            not isinstance(projection_digest, str)
            or _SHA256.fullmatch(projection_digest) is None
        ):
            raise ValueError(
                f"constellation {label} projection_digest requires SHA-256"
            )
        if projection_digest != canonical_digest(document["result"]["projection"]):
            raise ValueError(
                f"constellation {label} projection_digest differs from its projection"
            )


def _producer_context(
    document: dict[str, Any],
    coordinate: dict[str, Any],
) -> dict[str, Any]:
    producer_detail = document["result"]["producer_detail"]
    provenance = document["provenance"]
    return {
        "observation_id": document["observation_id"],
        "evidence_mode": document["evidence_mode"],
        "assurance_stage": document["assurance_stage"],
        "observation_digest": canonical_digest(document),
        "projection_digest": canonical_digest(document["result"]["projection"]),
        "producer_detail_digest": canonical_digest(producer_detail),
        "source": deepcopy(document["source"]),
        "source_digest": canonical_digest(document["source"]),
        "provenance": {
            "raw_artifact_digest": provenance["raw_artifact_digest"],
            "governed_locator": provenance["governed_locator"],
            "performed_by": provenance["performed_by"],
            "reviewed_by": provenance["reviewed_by"],
        },
        "provenance_digest": canonical_digest(provenance),
        "coordinate": deepcopy(coordinate),
    }


def _json_equal(left: Any, right: Any) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return math.isfinite(left) and math.isfinite(right) and left == right
    return type(left) is type(right) and left == right


def _raise_field_difference(
    value: dict[str, Any],
    expected: set[str],
    label: str,
) -> None:
    details = []
    missing = sorted(expected - value.keys())
    extra = sorted(value.keys() - expected)
    if missing:
        details.append("missing " + ", ".join(missing))
    if extra:
        details.append("unreleased " + ", ".join(extra))
    raise ValueError(f"{label} fields require " + "; ".join(details))


__all__ = [
    "AGREEMENT",
    "EXPLAINABLE_VARIATION",
    "MATERIAL_DIVERGENCE",
    "PROJECTION_PATHS",
    "compare_golden_specimen",
]
