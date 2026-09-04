"""Validate the content-addressed Comparative Evidence 0.3.2 candidate."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .contract_v1 import canonical_digest, strict_json_loads


SCHEMA_REFERENCE = "../schemas/promotion-candidate.schema.json"
SCHEMA_VERSION = "1.0.0"
RECEIPT_ID = "RCP-COMPARATIVE-PROMOTION-004"
REPOSITORY = "driftframestudios/lims-eln-comparative-evidence"
TARGET_RELEASE = "comparison-v0.3.2"
CANDIDATE_COORDINATE = {
    "release": "candidate-comparison-v0.3.2",
    "repository_release": "0.3.2",
    "constellation_lock": "constellation.lock.json",
    "constellation_lock_canonical_json_digest": (
        "sha256:a0f5a59dc032b7771e1c90b42942e7ac0a5a894fbc989fd14cadc42a8d81608e"
    ),
    "synthetic_contract_report_digest": (
        "sha256:5f66ed1a3023b00bc7779f8810c0440f594dd5fe10e90a475b073eaa438f741b"
    ),
    "golden_specimen_report_digest": (
        "sha256:a2f92ae4acb9fb7d835d0a9b126bb1932ae69b06b094303180dd9fea7217b77c"
    ),
    "golden_source_constellation_digest": (
        "sha256:6547340f075d5ab60a767ba32f1584054c30edf839239e196748a68118c641e2"
    ),
}
PRIOR_RELEASE_COORDINATE = {
    "promotion_receipt": "receipts/promotion-receipt.json",
    "promotion_receipt_file_sha256": (
        "sha256:733261cf52339f7f6b3e650302ab4b8b51c37eef57c752b0f5e2d2c4e27485ff"
    ),
    "tag": "comparison-v0.3.1",
    "tag_object_oid": "4c29f6ca410eb4400c55ad77fc34ada2960d1972",
    "commit_oid": "b5c13689a32739d29437e209816bf0cd6a878976",
    "tree_oid": "10a784b8a677ee6eb524d2860ff5ee7151d6050b",
    "archive_digest": (
        "sha256:92c2d57bd9e75c650365db4b481a22a6580b201926ba1c666fcf8cb8c9311a2e"
    ),
}
COMPARISON_AUTHORITY = {
    "evidence_mode": "simulated",
    "assurance_stage": "verified",
    "comparison_mode": "simulated_verification",
    "environment_observed_closure": "separate_unasserted_state",
    "production_authorization_effect": "none",
}

_ROOT_FIELDS = {
    "$schema",
    "schema_version",
    "promotion_receipt_id",
    "repository",
    "target_release",
    "promotion_state",
    "release_event_evidence",
    "comparison_authority",
    "candidate_coordinate",
    "prior_release_coordinate",
    "required_evidence",
    "remaining_promotion_evidence",
    "limitations",
    "accountable_role",
}


class PromotionCandidateError(ValueError):
    """Return a candidate difference to its source or promotion route."""


def canonical_json_digest_from_path(path: Path) -> str:
    """Return the canonical digest of one JSON candidate carrier."""
    value = strict_json_loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise PromotionCandidateError("promotion candidate requires one JSON object")
    return canonical_digest(value)


def validate_promotion_candidate(candidate: Any) -> None:
    """Require the exact 0.3.2 identities and recoverable prior release."""
    _expect_object(candidate, _ROOT_FIELDS, "promotion candidate")
    expected = {
        "$schema": SCHEMA_REFERENCE,
        "schema_version": SCHEMA_VERSION,
        "promotion_receipt_id": RECEIPT_ID,
        "repository": REPOSITORY,
        "target_release": TARGET_RELEASE,
        "promotion_state": "candidate_ready",
        "release_event_evidence": {
            "evidence_mode": "planned",
            "assurance_stage": "specified",
        },
        "comparison_authority": COMPARISON_AUTHORITY,
        "candidate_coordinate": CANDIDATE_COORDINATE,
        "prior_release_coordinate": PRIOR_RELEASE_COORDINATE,
    }
    for field, expected_value in expected.items():
        if candidate[field] != expected_value:
            raise PromotionCandidateError(
                f"promotion candidate {field} requires {expected_value!r}"
            )
    for field in (
        "required_evidence",
        "remaining_promotion_evidence",
        "limitations",
    ):
        _expect_statements(candidate[field], field)
    _expect_text(candidate["accountable_role"], "accountable_role", 3, 120)


def _expect_object(value: Any, fields: set[str], label: str) -> None:
    if not isinstance(value, dict) or set(value) != fields:
        raise PromotionCandidateError(f"{label} carries exactly {sorted(fields)!r}")


def _expect_statements(value: Any, label: str) -> None:
    if not isinstance(value, list) or not value:
        raise PromotionCandidateError(f"{label} carries unique material statements")
    if any(
        not isinstance(item, str)
        or len(item.strip()) < 20
        or len(item) > 500
        for item in value
    ):
        raise PromotionCandidateError(f"{label} carries unique material statements")
    if len(set(value)) != len(value):
        raise PromotionCandidateError(f"{label} carries unique material statements")


def _expect_text(value: Any, label: str, minimum: int, maximum: int) -> None:
    if (
        not isinstance(value, str)
        or len(value.strip()) < minimum
        or len(value) > maximum
    ):
        raise PromotionCandidateError(f"{label} carries meaningful text")


__all__ = [
    "CANDIDATE_COORDINATE",
    "PRIOR_RELEASE_COORDINATE",
    "PromotionCandidateError",
    "canonical_json_digest_from_path",
    "validate_promotion_candidate",
]
