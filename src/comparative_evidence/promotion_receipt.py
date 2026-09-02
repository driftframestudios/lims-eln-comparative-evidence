"""Validate the repository-owned comparative-evidence promotion receipt."""

from __future__ import annotations

from datetime import datetime
from hashlib import sha256
from pathlib import Path
import re
from typing import Any

from .contract_v1 import canonical_digest


SCHEMA_REFERENCE = "../schemas/promotion-receipt.schema.json"
SCHEMA_VERSION = "1.0.0"
RECEIPT_ID = "RCP-COMPARATIVE-PROMOTION-003"
REPOSITORY = "driftframestudios/lims-eln-comparative-evidence"
TARGET_RELEASE = "comparison-v0.3.1"
CANDIDATE_SOURCE = {
    "coordinate_kind": "accepted_develop_merge_source",
    "commit_oid": "daae956379cf00f5008672d19765aee6bec7eb4a",
    "tree_oid": "ba1c8b3dcc7a0c3233b0d5b8c9f74765152dade3",
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
    "candidate_source",
    "release_subject",
    "required_evidence",
    "accountable_role",
}
_COMPARISON_AUTHORITY = {
    "evidence_mode": "simulated",
    "assurance_stage": "verified",
    "comparison_mode": "simulated_verification",
    "environment_observed_closure": "separate_unasserted_state",
    "production_authorization_effect": "none",
}
_SUBJECT_FIELDS = {
    "git_object_format",
    "tag",
    "tag_object_oid",
    "commit_oid",
    "tree_oid",
    "archive_format",
    "archive_digest",
    "promoted_at",
    "tag_signature_verification",
    "hosted_check_contexts",
    "local_verification_signals",
}
_HOSTED_CHECK_FIELDS = {"name", "run_id", "conclusion"}
_NONZERO_SHA1 = re.compile(r"^(?!0{40}$)[a-f0-9]{40}$")
_NONZERO_SHA256 = re.compile(r"^sha256:(?!0{64}$)[a-f0-9]{64}$")
_RUN_ID = re.compile(r"^[1-9][0-9]*$")
_INSTANT = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]{1,6})?(?:Z|[+-][0-9]{2}:[0-9]{2})$"
)


class PromotionReceiptError(ValueError):
    """A promotion record returns to its candidate or observed completion path."""


def file_digest(path: Path) -> str:
    """Return a SHA-256 digest for exact carrier bytes."""
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def validate_promotion_receipt(receipt: Any) -> None:
    """Validate candidate and observed promotion states without external packages."""
    _expect_object(receipt, _ROOT_FIELDS, "promotion receipt")
    _expect_equal(receipt, "$schema", SCHEMA_REFERENCE)
    _expect_equal(receipt, "schema_version", SCHEMA_VERSION)
    _expect_equal(receipt, "promotion_receipt_id", RECEIPT_ID)
    _expect_equal(receipt, "repository", REPOSITORY)
    _expect_equal(receipt, "target_release", TARGET_RELEASE)

    state = receipt["promotion_state"]
    if state not in {"candidate_ready", "release_observed"}:
        raise PromotionReceiptError(
            "promotion_state must be candidate_ready or release_observed"
        )

    event = receipt["release_event_evidence"]
    _expect_object(
        event,
        {"evidence_mode", "assurance_stage"},
        "release_event_evidence",
    )
    expected_event = (
        {"evidence_mode": "planned", "assurance_stage": "specified"}
        if state == "candidate_ready"
        else {"evidence_mode": "observed", "assurance_stage": "verified"}
    )
    if event != expected_event:
        raise PromotionReceiptError(
            f"{state} release-event evidence is {expected_event!r}"
        )

    authority = receipt["comparison_authority"]
    _expect_object(
        authority,
        set(_COMPARISON_AUTHORITY),
        "comparison_authority",
    )
    if authority != _COMPARISON_AUTHORITY:
        raise PromotionReceiptError(
            "comparison_authority uses simulated-verification authority; "
            "environment-observed closure and production authorization remain "
            "separate"
        )

    source = receipt["candidate_source"]
    _expect_object(source, set(CANDIDATE_SOURCE), "candidate_source")
    if source != CANDIDATE_SOURCE:
        raise PromotionReceiptError(
            "candidate_source binds the accepted develop merge source without "
            "claiming the later release subject"
        )

    _expect_unique_strings(
        receipt["required_evidence"],
        "required_evidence",
        minimum=1,
        minimum_length=10,
        maximum_length=500,
    )
    _expect_string(
        receipt["accountable_role"],
        "accountable_role",
        minimum=3,
        maximum=120,
    )

    subject = receipt["release_subject"]
    if state == "candidate_ready":
        if subject is not None:
            raise PromotionReceiptError(
                "candidate_ready keeps release_subject null until promotion is observed"
            )
        return
    _validate_observed_subject(subject)


def _validate_observed_subject(subject: Any) -> None:
    _expect_object(subject, _SUBJECT_FIELDS, "release_subject")
    _expect_equal(subject, "git_object_format", "sha1")
    _expect_equal(subject, "tag", TARGET_RELEASE)
    for field in ("tag_object_oid", "commit_oid", "tree_oid"):
        value = subject[field]
        if not isinstance(value, str) or _NONZERO_SHA1.fullmatch(value) is None:
            raise PromotionReceiptError(
                f"release_subject.{field} is an exact nonzero SHA-1 object ID"
            )
    _expect_equal(subject, "archive_format", "git-tar")
    archive_digest = subject["archive_digest"]
    if (
        not isinstance(archive_digest, str)
        or _NONZERO_SHA256.fullmatch(archive_digest) is None
    ):
        raise PromotionReceiptError(
            "release_subject.archive_digest is an exact nonzero SHA-256 digest"
        )
    _validate_timestamp(subject["promoted_at"])
    _expect_equal(subject, "tag_signature_verification", "valid")
    _validate_hosted_checks(subject["hosted_check_contexts"])
    _expect_unique_strings(
        subject["local_verification_signals"],
        "release_subject.local_verification_signals",
        minimum=2,
        minimum_length=3,
        maximum_length=300,
    )


def _validate_hosted_checks(value: Any) -> None:
    if not isinstance(value, list) or not value:
        raise PromotionReceiptError(
            "release_subject.hosted_check_contexts carries at least one successful check"
        )
    names: set[str] = set()
    run_ids: set[str] = set()
    for index, check in enumerate(value):
        label = f"release_subject.hosted_check_contexts[{index}]"
        _expect_object(check, _HOSTED_CHECK_FIELDS, label)
        name = check["name"]
        run_id = check["run_id"]
        _expect_string(name, f"{label}.name", minimum=1, maximum=200)
        if not isinstance(run_id, str) or _RUN_ID.fullmatch(run_id) is None:
            raise PromotionReceiptError(f"{label}.run_id is a positive run ID")
        _expect_equal(check, "conclusion", "success", prefix=label)
        if name in names or run_id in run_ids:
            raise PromotionReceiptError(
                "release_subject.hosted_check_contexts keeps check names and run IDs unique"
            )
        names.add(name)
        run_ids.add(run_id)


def _validate_timestamp(value: Any) -> None:
    if not isinstance(value, str) or _INSTANT.fullmatch(value) is None:
        raise PromotionReceiptError(
            "release_subject.promoted_at is a valid ISO 8601 instant with an "
            "explicit UTC offset"
        )
    try:
        instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise PromotionReceiptError(
            "release_subject.promoted_at is a valid ISO 8601 instant"
        ) from error
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise PromotionReceiptError(
            "release_subject.promoted_at includes an explicit UTC offset"
        )


def _expect_object(value: Any, fields: set[str], label: str) -> None:
    if not isinstance(value, dict) or set(value) != fields:
        raise PromotionReceiptError(f"{label} carries exactly {sorted(fields)!r}")


def _expect_equal(
    value: dict[str, Any],
    field: str,
    expected: Any,
    *,
    prefix: str = "promotion receipt",
) -> None:
    if value[field] != expected:
        raise PromotionReceiptError(f"{prefix}.{field} is {expected!r}")


def _expect_string(
    value: Any,
    label: str,
    *,
    minimum: int,
    maximum: int,
) -> None:
    if (
        not isinstance(value, str)
        or len(value.strip()) < minimum
        or len(value) > maximum
    ):
        raise PromotionReceiptError(f"{label} is a meaningful string")


def _expect_unique_strings(
    value: Any,
    label: str,
    *,
    minimum: int,
    minimum_length: int,
    maximum_length: int,
) -> None:
    if not isinstance(value, list) or len(value) < minimum:
        raise PromotionReceiptError(f"{label} carries at least {minimum} entries")
    if any(
        not isinstance(item, str)
        or len(item.strip()) < minimum_length
        or len(item) > maximum_length
        for item in value
    ):
        raise PromotionReceiptError(f"{label} carries meaningful strings")
    if len(set(value)) != len(value):
        raise PromotionReceiptError(f"{label} keeps entries unique")
