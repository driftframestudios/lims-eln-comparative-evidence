#!/usr/bin/env python3
"""Verify the 0.3.2 promotion observation against its signed Git release."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from comparative_evidence.contract_v1 import (  # noqa: E402
    canonical_digest,
    strict_json_loads,
)
from comparative_evidence.promotion_observation import (  # noqa: E402
    validate_promotion_observation,
)
from tools.verify_release_coordinate import (  # noqa: E402
    DEFAULT_ACCEPTED_REF,
    EXPECTED_SIGNING_FINGERPRINT,
    ReleaseCoordinateError,
    _git_text,
    _read_regular_bytes,
    _repository_file,
    _repository_identity,
    _require_final_snapshot,
    _run_git_bytes,
    _verify_receipt_carrier,
    observe_release_coordinate,
)


DEFAULT_OBSERVATION = Path("receipts/promotion-observation-v0.3.2.json")
_DERIVED_RELEASE_FIELDS = (
    "git_object_format",
    "tag",
    "tag_object_oid",
    "commit_oid",
    "tree_oid",
    "archive_format",
    "archive_digest",
    "promoted_at",
    "tag_signature_verification",
)


class PromotionObservationVerificationError(ValueError):
    """Return an observation difference to its source or signed release."""


def _same_instant(left: str, right: str) -> bool:
    def parse(value: str) -> datetime:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)

    try:
        return parse(left) == parse(right)
    except (AttributeError, ValueError) as error:
        raise PromotionObservationVerificationError(
            "promotion observation carries valid release instants"
        ) from error


def _release_differences(
    recorded: dict[str, Any],
    derived: dict[str, str],
) -> dict[str, dict[str, Any]]:
    differences: dict[str, dict[str, Any]] = {}
    for field in _DERIVED_RELEASE_FIELDS:
        matches = (
            _same_instant(recorded[field], derived[field])
            if field == "promoted_at"
            else recorded[field] == derived[field]
        )
        if not matches:
            differences[field] = {
                "observation": recorded[field],
                "derived": derived[field],
            }
    return differences


def verify_promotion_observation(
    repository: Path,
    *,
    observation_path: Path = DEFAULT_OBSERVATION,
    accepted_ref: str = DEFAULT_ACCEPTED_REF,
    expected_signing_fingerprint: str = EXPECTED_SIGNING_FINGERPRINT,
) -> dict[str, str]:
    """Verify the observation carrier, candidate source, and signed release."""
    identity = _repository_identity(repository)
    observation_file = _repository_file(
        identity.worktree_root,
        observation_path,
        "promotion observation",
    )
    observation_bytes = _read_regular_bytes(
        observation_file,
        "promotion observation",
    )
    try:
        observation: Any = strict_json_loads(
            observation_bytes.decode("utf-8")
        )
    except UnicodeDecodeError as error:
        raise PromotionObservationVerificationError(
            "promotion observation carries valid UTF-8 JSON"
        ) from error
    validate_promotion_observation(observation)

    carrier_commit = _git_text(identity, "rev-parse", "--verify", "HEAD^{commit}")
    _verify_receipt_carrier(
        identity,
        observation_file,
        observation_bytes,
        carrier_commit=carrier_commit,
    )

    release_coordinate = observe_release_coordinate(
        identity.worktree_root,
        tag=observation["target_release"],
        accepted_ref=accepted_ref,
        expected_signing_fingerprint=expected_signing_fingerprint,
    )
    differences = _release_differences(
        observation["release_coordinate"],
        release_coordinate.as_dict(),
    )
    if differences:
        raise PromotionObservationVerificationError(
            "promotion observation differs from the signed Git release: "
            + json.dumps(differences, sort_keys=True)
        )

    candidate = observation["candidate_coordinate"]
    candidate_tree = _git_text(
        identity,
        "rev-parse",
        "--verify",
        f"{candidate['commit_oid']}^{{tree}}",
    )
    if candidate_tree != candidate["tree_oid"]:
        raise PromotionObservationVerificationError(
            "promotion observation candidate commit and tree remain aligned"
        )
    if candidate_tree != release_coordinate.tree_oid:
        raise PromotionObservationVerificationError(
            "accepted candidate and signed release share one Git tree"
        )
    candidate_bytes = _run_git_bytes(
        identity,
        "cat-file",
        "blob",
        f"{candidate['commit_oid']}:{candidate['candidate_receipt']}",
    )
    if (
        "sha256:" + sha256(candidate_bytes).hexdigest()
        != candidate["candidate_receipt_file_sha256"]
    ):
        raise PromotionObservationVerificationError(
            "candidate receipt bytes match the reviewed candidate coordinate"
        )
    candidate_value = strict_json_loads(candidate_bytes.decode("utf-8"))
    if (
        canonical_digest(candidate_value)
        != candidate["candidate_receipt_canonical_json_digest"]
    ):
        raise PromotionObservationVerificationError(
            "candidate receipt canonical identity matches the reviewed coordinate"
        )

    _require_final_snapshot(
        identity,
        carrier_commit=carrier_commit,
        receipt_path=observation_file,
        receipt_bytes=observation_bytes,
    )
    return {
        "status": "passed",
        "promotion_state": observation["promotion_state"],
        "tag": release_coordinate.tag,
        "commit_oid": release_coordinate.commit_oid,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, default=ROOT)
    parser.add_argument("--observation", type=Path, default=DEFAULT_OBSERVATION)
    parser.add_argument("--accepted-ref", default=DEFAULT_ACCEPTED_REF)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        result = verify_promotion_observation(
            args.repository,
            observation_path=args.observation,
            accepted_ref=args.accepted_ref,
        )
    except (OSError, ValueError, ReleaseCoordinateError) as error:
        print(
            f"Promotion-observation verification requires attention: {error}",
            file=sys.stderr,
        )
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
