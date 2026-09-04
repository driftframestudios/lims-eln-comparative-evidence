#!/usr/bin/env python3
"""Verify every retained signed Comparative Evidence release coordinate."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.verify_promotion_observation import verify_promotion_observation  # noqa: E402
from tools.verify_release_coordinate import (  # noqa: E402
    DEFAULT_ACCEPTED_REF,
    DEFAULT_TRUSTED_SIGNERS,
    ReleaseCoordinateError,
    _RepositoryIdentity,
    _git_text,
    _read_regular_bytes,
    _reject_git_local_overrides,
    _repository_file,
    _repository_identity,
    _require_ref_snapshot,
    _require_stable_head,
    verify_release_coordinate,
)


_RETAINED_TAGS = ("comparison-v0.3.1", "comparison-v0.3.2")


@dataclass(frozen=True)
class _HistorySnapshot:
    """Mutable carriers shared by every retained release verification."""

    carrier_commit: str
    accepted_commit: str
    tag_objects: tuple[tuple[str, str], ...]
    trusted_signers_path: Path
    trusted_signers_bytes: bytes


def _capture_history_snapshot(
    repository: Path,
) -> tuple[_RepositoryIdentity, _HistorySnapshot]:
    identity = _repository_identity(repository)
    carrier_commit = _git_text(identity, "rev-parse", "--verify", "HEAD^{commit}")
    accepted_commit = _git_text(
        identity,
        "rev-parse",
        "--verify",
        f"{DEFAULT_ACCEPTED_REF}^{{commit}}",
    )
    tag_objects = tuple(
        (
            f"refs/tags/{tag}",
            _git_text(identity, "rev-parse", "--verify", f"refs/tags/{tag}"),
        )
        for tag in _RETAINED_TAGS
    )
    trusted_signers_path = _repository_file(
        identity.worktree_root,
        DEFAULT_TRUSTED_SIGNERS,
        "trusted release signers",
    )
    return identity, _HistorySnapshot(
        carrier_commit=carrier_commit,
        accepted_commit=accepted_commit,
        tag_objects=tag_objects,
        trusted_signers_path=trusted_signers_path,
        trusted_signers_bytes=_read_regular_bytes(
            trusted_signers_path,
            "trusted release signers",
        ),
    )


def _require_history_snapshot(
    identity: _RepositoryIdentity,
    snapshot: _HistorySnapshot,
) -> None:
    """Recheck the shared history carriers immediately before returning."""
    _reject_git_local_overrides(identity)
    for tag_ref, tag_object_oid in snapshot.tag_objects:
        _require_ref_snapshot(
            identity,
            tag_ref,
            tag_object_oid,
            label="retained release tag ref",
        )
    _require_ref_snapshot(
        identity,
        f"{DEFAULT_ACCEPTED_REF}^{{commit}}",
        snapshot.accepted_commit,
        label="accepted history ref",
    )
    if (
        _read_regular_bytes(
            snapshot.trusted_signers_path,
            "trusted release signers final history snapshot",
        )
        != snapshot.trusted_signers_bytes
    ):
        raise ReleaseCoordinateError(
            "working trusted-release-signers remains at the exact captured bytes "
            "during release-history verification"
        )
    _require_stable_head(identity, snapshot.carrier_commit)


def verify_release_history(repository: Path) -> dict[str, object]:
    """Verify the immutable 0.3.1 receipt and additive 0.3.2 observation."""
    identity, snapshot = _capture_history_snapshot(repository)
    prior = verify_release_coordinate(repository, require_observed=True)
    current = verify_promotion_observation(repository)
    _require_history_snapshot(identity, snapshot)
    return {
        "status": "passed",
        "releases": [prior, current],
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, default=ROOT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        result = verify_release_history(args.repository)
    except (OSError, ValueError) as error:
        print(
            f"Release-history verification requires attention: {error}",
            file=sys.stderr,
        )
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
