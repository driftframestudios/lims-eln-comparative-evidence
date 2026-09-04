"""Validate the observed Comparative Evidence 0.3.2 release."""

from __future__ import annotations

from typing import Any

from .promotion_candidate import COMPARISON_AUTHORITY


SCHEMA_REFERENCE = "../schemas/promotion-observation-v0.3.2.schema.json"
SCHEMA_VERSION = "1.0.0"
RECEIPT_ID = "RCP-COMPARATIVE-PROMOTION-004"
REPOSITORY = "driftframestudios/lims-eln-comparative-evidence"
TARGET_RELEASE = "comparison-v0.3.2"
CANDIDATE_COORDINATE = {
    "release": "candidate-comparison-v0.3.2",
    "commit_oid": "abcb3d295938f047d58ffc754eeabdeeefa52873",
    "tree_oid": "60c85e4206e2d487dac83d521401816dec0f34ae",
    "candidate_receipt": "receipts/promotion-candidate.json",
    "candidate_receipt_file_sha256": (
        "sha256:a99f38fcebccff85d6c8e63a63c69bafc39749317fe79750c5897700de5a6784"
    ),
    "candidate_receipt_canonical_json_digest": (
        "sha256:74a19b585dcc69001b8097a3f9be883436d08964a271e7e35c935e7ae5abd227"
    ),
}
RELEASE_COORDINATE = {
    "git_object_format": "sha1",
    "tag": "comparison-v0.3.2",
    "tag_object_oid": "ccc4b206d9071933516863ee0eb3f5b091fc76b0",
    "commit_oid": "0289ff835c790693a769347e69da0abdcfaa47de",
    "tree_oid": "60c85e4206e2d487dac83d521401816dec0f34ae",
    "archive_format": "git-tar",
    "archive_digest": (
        "sha256:5c1697f98655ce1979fcc6f4a85b719e0c44afde8a3004037d19dd1416d0720e"
    ),
    "promoted_at": "2026-09-04T04:30:15Z",
    "pull_request": 33,
    "hosted_checks": [
        {
            "name": "Repository validation",
            "run_id": "33836962288",
            "job_id": "100911347748",
            "conclusion": "success",
        }
    ],
    "review_observation": {
        "merge_admission": "configured_ruleset_bypass",
        "independent_review": "constructive_architecture_review_completed",
        "github_review_record": "no_formal_review_submitted",
    },
    "merge_signature_verification": "valid",
    "tag_signature_verification": "valid",
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
    "release_coordinate",
    "required_evidence",
    "limitations",
    "accountable_role",
}


class PromotionObservationError(ValueError):
    """Return an observation difference to its candidate or release source."""


def validate_promotion_observation(observation: Any) -> None:
    """Require the exact candidate, release, and comparison-authority bindings."""
    _expect_object(observation, _ROOT_FIELDS, "promotion observation")
    expected = {
        "$schema": SCHEMA_REFERENCE,
        "schema_version": SCHEMA_VERSION,
        "promotion_receipt_id": RECEIPT_ID,
        "repository": REPOSITORY,
        "target_release": TARGET_RELEASE,
        "promotion_state": "release_observed",
        "release_event_evidence": {
            "evidence_mode": "observed",
            "assurance_stage": "verified",
        },
        "comparison_authority": COMPARISON_AUTHORITY,
        "candidate_coordinate": CANDIDATE_COORDINATE,
        "release_coordinate": RELEASE_COORDINATE,
        "accountable_role": "Comparative evidence release stewardship",
    }
    for field, expected_value in expected.items():
        if observation[field] != expected_value:
            raise PromotionObservationError(
                f"promotion observation {field} requires {expected_value!r}"
            )
    for field in ("required_evidence", "limitations"):
        _expect_statements(observation[field], field)


def _expect_object(value: Any, fields: set[str], label: str) -> None:
    if not isinstance(value, dict) or set(value) != fields:
        raise PromotionObservationError(
            f"{label} carries exactly {sorted(fields)!r}"
        )


def _expect_statements(value: Any, label: str) -> None:
    if not isinstance(value, list) or not value:
        raise PromotionObservationError(
            f"{label} carries unique material statements"
        )
    if any(
        not isinstance(item, str)
        or len(item.strip()) < 20
        or len(item) > 500
        for item in value
    ):
        raise PromotionObservationError(
            f"{label} carries unique material statements"
        )
    if len(set(value)) != len(value):
        raise PromotionObservationError(
            f"{label} carries unique material statements"
        )


__all__ = [
    "CANDIDATE_COORDINATE",
    "PromotionObservationError",
    "RELEASE_COORDINATE",
    "validate_promotion_observation",
]
