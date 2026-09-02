#!/usr/bin/env python3
"""Verify the Comparator promotion receipt against its signed Git release."""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import os
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from comparative_evidence.promotion_receipt import (  # noqa: E402
    validate_promotion_receipt,
)


DEFAULT_ACCEPTED_REF = "refs/remotes/origin/main"
DEFAULT_RECEIPT = Path("receipts/promotion-receipt.json")
DEFAULT_TRUSTED_SIGNERS = Path("release/trusted-release-signers")
EXPECTED_SIGNING_FINGERPRINT = "SHA256:86lsl/VvHgab8NoMoFDtIeJMZIhzOQ/yyqe2C8mkNhU"
EXPECTED_RELEASE = {
    "tag": "comparison-v0.3.1",
    "tag_object_oid": "4c29f6ca410eb4400c55ad77fc34ada2960d1972",
    "commit_oid": "b5c13689a32739d29437e209816bf0cd6a878976",
    "tree_oid": "10a784b8a677ee6eb524d2860ff5ee7151d6050b",
    "archive_digest": (
        "sha256:92c2d57bd9e75c650365db4b481a22a6580b201926ba1c666fcf8cb8c9311a2e"
    ),
}
_DERIVED_SUBJECT_FIELDS = (
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


class ReleaseCoordinateError(ValueError):
    """Return an unverifiable coordinate to its observable release path."""


@dataclass(frozen=True)
class _RepositoryIdentity:
    """One resolved worktree, Git administration directory, and Git program."""

    worktree_root: Path
    git_directory: Path
    common_directory: Path
    git_program: Path


@dataclass(frozen=True)
class _ReleaseSnapshot:
    """Mutable release inputs captured before coordinate derivation."""

    tag_ref: str
    tag_object_oid: str
    accepted_ref: str
    accepted_commit: str
    trusted_signers_path: Path
    trusted_signers_bytes: bytes


@dataclass(frozen=True)
class ReleaseCoordinate:
    """The locally reproducible fields of one signed release subject."""

    git_object_format: str
    tag: str
    tag_object_oid: str
    commit_oid: str
    tree_oid: str
    archive_format: str
    archive_digest: str
    promoted_at: str
    tag_signature_verification: str

    def as_dict(self) -> dict[str, str]:
        return {field: getattr(self, field) for field in _DERIVED_SUBJECT_FIELDS}


def observe_release_coordinate(
    repository: Path,
    *,
    tag: str,
    accepted_ref: str = DEFAULT_ACCEPTED_REF,
    trusted_signers: Path = DEFAULT_TRUSTED_SIGNERS,
    expected_signing_fingerprint: str = EXPECTED_SIGNING_FINGERPRINT,
) -> ReleaseCoordinate:
    """Derive one signed annotated-tag coordinate from local Git objects."""
    identity = _repository_identity(repository)
    carrier_commit = _git_text(identity, "rev-parse", "--verify", "HEAD^{commit}")
    coordinate, snapshot = _observe_release_coordinate(
        identity,
        tag=tag,
        accepted_ref=accepted_ref,
        trusted_signers=trusted_signers,
        expected_signing_fingerprint=expected_signing_fingerprint,
        carrier_commit=carrier_commit,
    )
    _require_final_snapshot(
        identity,
        carrier_commit=carrier_commit,
        release_snapshot=snapshot,
    )
    return coordinate


def _observe_release_coordinate(
    identity: _RepositoryIdentity,
    *,
    tag: str,
    accepted_ref: str,
    trusted_signers: Path,
    expected_signing_fingerprint: str,
    carrier_commit: str,
) -> tuple[ReleaseCoordinate, _ReleaseSnapshot]:
    tag_ref = _tag_ref(identity, tag)

    object_format = _git_text(identity, "rev-parse", "--show-object-format")
    if object_format != "sha1":
        raise ReleaseCoordinateError(
            f"release repository object format is sha1; observed {object_format!r}"
        )
    if _git_text(identity, "cat-file", "-t", tag_ref) != "tag":
        raise ReleaseCoordinateError(
            f"release ref {tag_ref!r} identifies a direct annotated tag object"
        )

    tag_object_oid = _git_text(identity, "rev-parse", "--verify", tag_ref)
    headers = _tag_headers(
        _git_text(identity, "cat-file", "-p", tag_object_oid),
        tag_ref,
    )
    if headers.get("type") != "commit":
        raise ReleaseCoordinateError(
            f"release tag {tag_ref!r} directly identifies a commit object"
        )
    if headers.get("tag") != tag:
        raise ReleaseCoordinateError(
            f"release tag payload names {tag!r}; observed {headers.get('tag')!r}"
        )

    commit_oid = _git_text(
        identity,
        "rev-parse",
        "--verify",
        f"{tag_object_oid}^{{commit}}",
    )
    if headers.get("object") != commit_oid:
        raise ReleaseCoordinateError(
            "release tag payload and peeled commit identify one Git object"
        )
    tree_oid = _git_text(identity, "rev-parse", "--verify", f"{commit_oid}^{{tree}}")

    accepted_commit = _git_text(
        identity,
        "rev-parse",
        "--verify",
        f"{accepted_ref}^{{commit}}",
    )
    ancestry = _run_git(
        identity,
        "merge-base",
        "--is-ancestor",
        commit_oid,
        accepted_commit,
    )
    if ancestry.returncode == 1:
        raise ReleaseCoordinateError(
            f"release commit {commit_oid} is outside accepted history {accepted_ref}"
        )
    if ancestry.returncode != 0:
        raise ReleaseCoordinateError(
            _command_failure("git merge-base --is-ancestor", ancestry)
        )

    _require_ancestry(
        identity,
        accepted_commit,
        carrier_commit,
        failure=(
            f"observation carrier HEAD {carrier_commit} descends from accepted "
            f"history {accepted_ref}"
        ),
    )
    _require_ancestry(
        identity,
        commit_oid,
        carrier_commit,
        failure=(
            f"observation carrier HEAD {carrier_commit} descends from signed "
            f"release commit {commit_oid}"
        ),
    )

    signer_path, signer_bytes = _trusted_signer_bytes(
        identity,
        trusted_signers,
        expected_signing_fingerprint,
        carrier_commit=carrier_commit,
        release_commit=commit_oid,
    )
    _verify_tag_signature(identity, tag_object_oid, signer_bytes)
    promoted_at = (
        datetime.fromtimestamp(_tagger_epoch(headers["tagger"], tag_ref), UTC)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )
    coordinate = ReleaseCoordinate(
        git_object_format=object_format,
        tag=tag,
        tag_object_oid=tag_object_oid,
        commit_oid=commit_oid,
        tree_oid=tree_oid,
        archive_format="git-tar",
        archive_digest=_archive_digest(identity, commit_oid),
        promoted_at=promoted_at,
        tag_signature_verification="valid",
    )
    snapshot = _ReleaseSnapshot(
        tag_ref=tag_ref,
        tag_object_oid=tag_object_oid,
        accepted_ref=accepted_ref,
        accepted_commit=accepted_commit,
        trusted_signers_path=signer_path,
        trusted_signers_bytes=signer_bytes,
    )
    return coordinate, snapshot


def verify_release_coordinate(
    repository: Path,
    *,
    receipt_path: Path = DEFAULT_RECEIPT,
    accepted_ref: str = DEFAULT_ACCEPTED_REF,
    expected_release: Mapping[str, str] = EXPECTED_RELEASE,
    expected_signing_fingerprint: str = EXPECTED_SIGNING_FINGERPRINT,
    require_observed: bool = False,
) -> dict[str, str]:
    """Validate the receipt, then verify its observed release when present."""
    identity = _repository_identity(repository)
    receipt_file = _repository_file(
        identity.worktree_root,
        receipt_path,
        "promotion receipt",
    )
    receipt_bytes = _read_regular_bytes(receipt_file, "promotion receipt")
    try:
        receipt: Any = json.loads(receipt_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ReleaseCoordinateError(
            "promotion receipt carries valid UTF-8 JSON"
        ) from error
    validate_promotion_receipt(receipt)
    carrier_commit = _git_text(identity, "rev-parse", "--verify", "HEAD^{commit}")
    _verify_receipt_carrier(
        identity,
        receipt_file,
        receipt_bytes,
        carrier_commit=carrier_commit,
    )

    if receipt["promotion_state"] == "candidate_ready":
        if require_observed:
            raise ReleaseCoordinateError(
                "an observed signed release coordinate is required; "
                "the promotion receipt remains candidate_ready"
            )
        _require_final_snapshot(
            identity,
            carrier_commit=carrier_commit,
            receipt_path=receipt_file,
            receipt_bytes=receipt_bytes,
        )
        return {
            "status": "resting",
            "promotion_state": "candidate_ready",
            "target_release": receipt["target_release"],
        }

    coordinate, snapshot = _observe_release_coordinate(
        identity,
        tag=receipt["target_release"],
        accepted_ref=accepted_ref,
        trusted_signers=DEFAULT_TRUSTED_SIGNERS,
        expected_signing_fingerprint=expected_signing_fingerprint,
        carrier_commit=carrier_commit,
    )
    observed = coordinate.as_dict()
    expected_differences = {
        field: {"expected": expected_release.get(field), "derived": observed[field]}
        for field in (
            "tag",
            "tag_object_oid",
            "commit_oid",
            "tree_oid",
            "archive_digest",
        )
        if expected_release.get(field) != observed[field]
    }
    if expected_differences:
        raise ReleaseCoordinateError(
            "signed Git release differs from the accepted release coordinate: "
            + _difference_summary(expected_differences, "expected")
        )

    subject = receipt["release_subject"]
    receipt_differences: dict[str, dict[str, str]] = {}
    for field, derived in observed.items():
        recorded = subject[field]
        matches = (
            _instant(recorded) == _instant(derived)
            if field == "promoted_at"
            else recorded == derived
        )
        if not matches:
            receipt_differences[field] = {
                "receipt": recorded,
                "derived": derived,
            }
    if receipt_differences:
        raise ReleaseCoordinateError(
            "promotion receipt differs from the signed Git release coordinate: "
            + _difference_summary(receipt_differences, "receipt")
        )

    _require_final_snapshot(
        identity,
        carrier_commit=carrier_commit,
        receipt_path=receipt_file,
        receipt_bytes=receipt_bytes,
        release_snapshot=snapshot,
    )
    return {
        "status": "passed",
        "promotion_state": "release_observed",
        "tag": coordinate.tag,
        "commit_oid": coordinate.commit_oid,
    }


def _resolve_program(name: str) -> Path:
    candidate = shutil.which(name)
    if candidate is None:
        raise ReleaseCoordinateError(f"release verification requires the {name} program")
    try:
        resolved = Path(candidate).resolve(strict=True)
        status = os.stat(resolved)
    except OSError as error:
        raise ReleaseCoordinateError(
            f"release verification requires a readable {name} program"
        ) from error
    if not stat.S_ISREG(status.st_mode) or not os.access(resolved, os.X_OK):
        raise ReleaseCoordinateError(
            f"release verification requires an executable {name} program"
        )
    return resolved


def _git_directory_from_marker(worktree_root: Path) -> Path:
    marker = worktree_root / ".git"
    try:
        marker_status = os.lstat(marker)
    except OSError as error:
        raise ReleaseCoordinateError(
            "release repository requires its own Git worktree marker"
        ) from error
    if stat.S_ISLNK(marker_status.st_mode):
        raise ReleaseCoordinateError(
            "release repository requires a regular Git worktree marker"
        )
    if stat.S_ISDIR(marker_status.st_mode):
        return marker.resolve(strict=True)
    if not stat.S_ISREG(marker_status.st_mode):
        raise ReleaseCoordinateError(
            "release repository requires a regular Git worktree marker"
        )
    try:
        lines = marker.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as error:
        raise ReleaseCoordinateError(
            "release repository requires a readable Git worktree marker"
        ) from error
    if len(lines) != 1 or not lines[0].startswith("gitdir: "):
        raise ReleaseCoordinateError(
            "linked release worktree marker requires one Git directory"
        )
    value = Path(lines[0].removeprefix("gitdir: "))
    candidate = value if value.is_absolute() else worktree_root / value
    try:
        candidate_status = os.lstat(candidate)
        resolved = candidate.resolve(strict=True)
    except OSError as error:
        raise ReleaseCoordinateError(
            "linked release worktree requires one Git directory"
        ) from error
    if stat.S_ISLNK(candidate_status.st_mode) or not stat.S_ISDIR(
        candidate_status.st_mode
    ):
        raise ReleaseCoordinateError(
            "linked release worktree requires one regular Git directory"
        )
    backpointer = resolved / "gitdir"
    try:
        backpointer_status = os.lstat(backpointer)
        backpointer_value = backpointer.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError) as error:
        raise ReleaseCoordinateError(
            "linked release worktree requires its Git backpointer"
        ) from error
    if not stat.S_ISREG(backpointer_status.st_mode) or Path(
        backpointer_value
    ).resolve(strict=True) != marker.resolve(strict=True):
        raise ReleaseCoordinateError(
            "linked release worktree backpointer requires this source root"
        )
    return resolved


def _common_git_directory(git_directory: Path) -> Path:
    marker = git_directory / "commondir"
    if not os.path.lexists(marker):
        return git_directory
    try:
        marker_status = os.lstat(marker)
        lines = marker.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as error:
        raise ReleaseCoordinateError(
            "release repository requires a readable common Git directory marker"
        ) from error
    if stat.S_ISLNK(marker_status.st_mode) or not stat.S_ISREG(
        marker_status.st_mode
    ):
        raise ReleaseCoordinateError(
            "release repository requires a regular common Git directory marker"
        )
    if len(lines) != 1 or not lines[0]:
        raise ReleaseCoordinateError(
            "release repository common Git marker names one directory"
        )
    value = Path(lines[0])
    candidate = value if value.is_absolute() else git_directory / value
    try:
        candidate_status = os.lstat(candidate)
        resolved = candidate.resolve(strict=True)
    except OSError as error:
        raise ReleaseCoordinateError(
            "release repository requires one common Git directory"
        ) from error
    if stat.S_ISLNK(candidate_status.st_mode) or not stat.S_ISDIR(
        candidate_status.st_mode
    ):
        raise ReleaseCoordinateError(
            "release repository requires one regular common Git directory"
        )
    return resolved


def _repository_identity(repository: Path) -> _RepositoryIdentity:
    try:
        root_status = os.lstat(repository)
        root = repository.resolve(strict=True)
    except OSError as error:
        raise ReleaseCoordinateError(
            "release repository path is a readable directory"
        ) from error
    if stat.S_ISLNK(root_status.st_mode) or not stat.S_ISDIR(root_status.st_mode):
        raise ReleaseCoordinateError("release repository path is a regular directory")

    git_directory = _git_directory_from_marker(root)
    identity = _RepositoryIdentity(
        worktree_root=root,
        git_directory=git_directory,
        common_directory=_common_git_directory(git_directory),
        git_program=_resolve_program("git"),
    )
    _reject_git_local_overrides(identity)
    observed_root = Path(
        _git_text(identity, "rev-parse", "--show-toplevel")
    ).resolve(strict=True)
    if observed_root != root:
        raise ReleaseCoordinateError(
            "repository path identifies its Git top level: "
            f"expected {root}, observed {observed_root}"
        )
    observed_git_directory = Path(
        _git_text(identity, "rev-parse", "--absolute-git-dir")
    ).resolve(strict=True)
    if observed_git_directory != git_directory:
        raise ReleaseCoordinateError(
            "release repository Git directory requires its worktree marker"
        )
    common_value = Path(_git_text(identity, "rev-parse", "--git-common-dir"))
    common_candidate = (
        common_value
        if common_value.is_absolute()
        else identity.git_directory / common_value
    )
    if common_candidate.resolve(strict=True) != identity.common_directory:
        raise ReleaseCoordinateError(
            "release repository common Git directory requires its worktree marker"
        )
    return identity


def _reject_git_local_overrides(identity: _RepositoryIdentity) -> None:
    for directory in {identity.git_directory, identity.common_directory}:
        grafts = directory / "info" / "grafts"
        if os.path.lexists(grafts):
            raise ReleaseCoordinateError(
                "release verification requires Git history without local grafts"
            )
        attributes = directory / "info" / "attributes"
        if os.path.lexists(attributes):
            raise ReleaseCoordinateError(
                "release verification requires archive attributes without local "
                "info/attributes"
            )


def _repository_file(repository: Path, path: Path, label: str) -> Path:
    candidate = path if path.is_absolute() else repository / path
    if candidate.is_symlink():
        raise ReleaseCoordinateError(f"{label} uses a repository-owned regular file")
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(repository)
    except (FileNotFoundError, ValueError) as error:
        raise ReleaseCoordinateError(
            f"{label} uses a repository-owned regular file"
        ) from error
    if not resolved.is_file():
        raise ReleaseCoordinateError(f"{label} uses a repository-owned regular file")
    return resolved


def _read_regular_bytes(path: Path, label: str) -> bytes:
    if not hasattr(os, "O_NOFOLLOW"):
        raise ReleaseCoordinateError(f"{label} requires no-follow file reads")
    flags = os.O_RDONLY | os.O_NOFOLLOW
    if hasattr(os, "O_NONBLOCK"):
        flags |= os.O_NONBLOCK
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise ReleaseCoordinateError(f"{label} uses a readable regular file") from error
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ReleaseCoordinateError(f"{label} uses a regular file")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    identity_before = (
        before.st_dev,
        before.st_ino,
        before.st_mode,
        before.st_size,
        before.st_mtime_ns,
    )
    identity_after = (
        after.st_dev,
        after.st_ino,
        after.st_mode,
        after.st_size,
        after.st_mtime_ns,
    )
    if identity_before != identity_after:
        raise ReleaseCoordinateError(f"{label} remains stable while it is read")
    return b"".join(chunks)


def _repository_blob_bytes(
    identity: _RepositoryIdentity,
    commit_oid: str,
    relative: str,
    label: str,
) -> bytes:
    listing = _run_git_bytes(
        identity,
        "ls-tree",
        "-z",
        "--full-tree",
        commit_oid,
        "--",
        relative,
    )
    records = [record for record in listing.split(b"\0") if record]
    if len(records) != 1:
        raise ReleaseCoordinateError(f"{label} contains one repository file")
    metadata, separator, observed_path = records[0].partition(b"\t")
    fields = metadata.split()
    if (
        not separator
        or observed_path != relative.encode("utf-8")
        or len(fields) != 3
        or fields[0] not in {b"100644", b"100755"}
        or fields[1] != b"blob"
    ):
        raise ReleaseCoordinateError(f"{label} contains one regular Git blob")
    try:
        object_id = fields[2].decode("ascii")
    except UnicodeDecodeError as error:
        raise ReleaseCoordinateError(f"{label} contains one Git blob identity") from error
    return _run_git_bytes(identity, "cat-file", "blob", object_id)


def _verify_receipt_carrier(
    identity: _RepositoryIdentity,
    receipt_path: Path,
    working_bytes: bytes,
    *,
    carrier_commit: str,
) -> None:
    relative = receipt_path.relative_to(identity.worktree_root).as_posix()
    carrier_bytes = _repository_blob_bytes(
        identity,
        carrier_commit,
        relative,
        "observation carrier HEAD",
    )
    if carrier_bytes != working_bytes:
        raise ReleaseCoordinateError(
            "observation carrier HEAD and the working tree contain exact promotion-receipt bytes"
        )


def _trusted_signer_bytes(
    identity: _RepositoryIdentity,
    path: Path,
    expected_fingerprint: str,
    *,
    carrier_commit: str,
    release_commit: str,
) -> tuple[Path, bytes]:
    signer_path = _repository_file(
        identity.worktree_root,
        path,
        "trusted release signers",
    )
    working_bytes = _read_regular_bytes(signer_path, "trusted release signers")
    relative = signer_path.relative_to(identity.worktree_root).as_posix()
    carrier_bytes = _repository_blob_bytes(
        identity,
        carrier_commit,
        relative,
        "observation carrier HEAD trusted release signers",
    )
    if working_bytes != carrier_bytes:
        raise ReleaseCoordinateError(
            "observation carrier HEAD and the working tree contain exact "
            "trusted-release-signers bytes"
        )
    release_bytes = _repository_blob_bytes(
        identity,
        release_commit,
        relative,
        "signed release tree trusted release signers",
    )
    if carrier_bytes != release_bytes:
        raise ReleaseCoordinateError(
            "observation carrier HEAD and the signed release tree contain exact "
            "trusted-release-signers bytes"
        )
    try:
        active_lines = [
            line.strip()
            for line in carrier_bytes.decode("utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
    except UnicodeDecodeError as error:
        raise ReleaseCoordinateError(
            "trusted release signers use UTF-8 allowed-signers syntax"
        ) from error
    if not active_lines:
        raise ReleaseCoordinateError(
            "trusted release signers name one Git-scoped public key"
        )
    fingerprints = {_ssh_fingerprint(line) for line in active_lines}
    if fingerprints != {expected_fingerprint}:
        raise ReleaseCoordinateError(
            "trusted release signers carry exactly the accepted signing-key fingerprint: "
            + expected_fingerprint
        )
    return signer_path, carrier_bytes


def _ssh_fingerprint(allowed_signer: str) -> str:
    try:
        fields = shlex.split(allowed_signer)
    except ValueError as error:
        raise ReleaseCoordinateError(
            "trusted release signers use valid OpenSSH allowed-signers syntax"
        ) from error
    if (
        len(fields) != 4
        or not fields[0]
        or not fields[2].startswith(("ssh-", "ecdsa-", "sk-"))
    ):
        raise ReleaseCoordinateError(
            "trusted release signers place allowed-signers options before the public key"
        )
    options = _allowed_signer_options(fields[1])
    if options.get("namespaces") != "git":
        raise ReleaseCoordinateError(
            "trusted release signers scope each public key to exactly the Git namespace"
        )
    try:
        key_blob = base64.b64decode(fields[3], validate=True)
    except (ValueError, binascii.Error) as error:
        raise ReleaseCoordinateError(
            "trusted release signers carry a valid OpenSSH public key"
        ) from error
    encoded = base64.b64encode(sha256(key_blob).digest()).decode("ascii")
    return "SHA256:" + encoded.rstrip("=")


def _allowed_signer_options(raw: str) -> dict[str, str | None]:
    options: dict[str, str | None] = {}
    for entry in raw.split(","):
        name, separator, value = entry.partition("=")
        normalized = name.casefold()
        if (
            not normalized
            or normalized in options
            or normalized
            not in {"cert-authority", "namespaces", "valid-after", "valid-before"}
        ):
            raise ReleaseCoordinateError(
                "trusted release signers use valid OpenSSH allowed-signers options"
            )
        if normalized == "cert-authority":
            if separator:
                raise ReleaseCoordinateError(
                    "trusted release signers use valid OpenSSH allowed-signers options"
                )
            options[normalized] = None
        else:
            if not separator or not value:
                raise ReleaseCoordinateError(
                    "trusted release signers use valid OpenSSH allowed-signers options"
                )
            options[normalized] = value
    return options


def _tag_ref(identity: _RepositoryIdentity, tag: str) -> str:
    tag_ref = f"refs/tags/{tag}"
    if not tag or _run_git(identity, "check-ref-format", tag_ref).returncode != 0:
        raise ReleaseCoordinateError("release tag is a complete Git ref segment")
    return tag_ref


def _require_ancestry(
    identity: _RepositoryIdentity,
    ancestor: str,
    descendant: str,
    *,
    failure: str,
) -> None:
    result = _run_git(
        identity,
        "merge-base",
        "--is-ancestor",
        ancestor,
        descendant,
    )
    if result.returncode == 1:
        raise ReleaseCoordinateError(failure)
    if result.returncode != 0:
        raise ReleaseCoordinateError(
            _command_failure("git merge-base --is-ancestor", result)
        )


def _require_final_snapshot(
    identity: _RepositoryIdentity,
    *,
    carrier_commit: str,
    receipt_path: Path | None = None,
    receipt_bytes: bytes | None = None,
    release_snapshot: _ReleaseSnapshot | None = None,
) -> None:
    """Recheck every mutable carrier immediately before returning a result."""
    _reject_git_local_overrides(identity)
    if release_snapshot is not None:
        _require_ref_snapshot(
            identity,
            release_snapshot.tag_ref,
            release_snapshot.tag_object_oid,
            label="release tag ref",
        )
        _require_ref_snapshot(
            identity,
            f"{release_snapshot.accepted_ref}^{{commit}}",
            release_snapshot.accepted_commit,
            label="accepted history ref",
        )
    if receipt_path is not None and receipt_bytes is not None:
        observed_receipt = _read_regular_bytes(
            receipt_path,
            "promotion receipt final snapshot",
        )
        if observed_receipt != receipt_bytes:
            raise ReleaseCoordinateError(
                "working promotion receipt remains at the exact captured bytes "
                "during verification"
            )
    if release_snapshot is not None:
        observed_signers = _read_regular_bytes(
            release_snapshot.trusted_signers_path,
            "trusted release signers final snapshot",
        )
        if observed_signers != release_snapshot.trusted_signers_bytes:
            raise ReleaseCoordinateError(
                "working trusted-release-signers remains at the exact captured bytes "
                "during verification"
            )
    _require_stable_head(identity, carrier_commit)


def _require_ref_snapshot(
    identity: _RepositoryIdentity,
    reference: str,
    expected_oid: str,
    *,
    label: str,
) -> None:
    result = _run_git(identity, "rev-parse", "--verify", reference)
    observed_oid = result.stdout.strip() if result.returncode == 0 else None
    if observed_oid != expected_oid:
        raise ReleaseCoordinateError(
            f"{label} {reference!r} remains at one exact captured object "
            "during verification"
        )


def _require_stable_head(
    identity: _RepositoryIdentity,
    carrier_commit: str,
) -> None:
    observed = _git_text(identity, "rev-parse", "--verify", "HEAD^{commit}")
    if observed != carrier_commit:
        raise ReleaseCoordinateError(
            "observation carrier HEAD remains at one exact commit during verification"
        )


def _tag_headers(payload: str, tag_ref: str) -> dict[str, str]:
    header_block, separator, _message = payload.partition("\n\n")
    if not separator:
        raise ReleaseCoordinateError(
            f"release tag {tag_ref!r} carries an annotated tag payload"
        )
    headers: dict[str, str] = {}
    for line in header_block.splitlines():
        field, separator, value = line.partition(" ")
        if not separator or field in headers:
            raise ReleaseCoordinateError(
                f"release tag {tag_ref!r} carries unambiguous object headers"
            )
        headers[field] = value
    if not {"object", "type", "tag", "tagger"}.issubset(headers):
        raise ReleaseCoordinateError(
            f"release tag {tag_ref!r} carries object, type, tag, and tagger headers"
        )
    return headers


def _tagger_epoch(tagger_header: str, tag_ref: str) -> int:
    parts = tagger_header.rsplit(" ", 2)
    raw = parts[-2] if len(parts) == 3 else ""
    offset = parts[-1] if len(parts) == 3 else ""
    try:
        epoch = int(raw)
    except ValueError as error:
        raise ReleaseCoordinateError(
            f"release tag {tag_ref!r} carries an exact tagger instant"
        ) from error
    if (
        epoch <= 0
        or len(offset) != 5
        or offset[0] not in {"+", "-"}
        or not offset[1:].isdigit()
    ):
        raise ReleaseCoordinateError(
            f"release tag {tag_ref!r} carries an exact tagger instant"
        )
    return epoch


def _verify_tag_signature(
    identity: _RepositoryIdentity,
    tag_object_oid: str,
    trusted_signers: bytes,
) -> None:
    ssh_keygen = _resolve_program("ssh-keygen")
    with tempfile.TemporaryDirectory(prefix="release-signers-") as temporary:
        signer_path = Path(temporary) / "allowed-signers"
        signer_path.write_bytes(trusted_signers)
        signer_path.chmod(0o600)
        result = _run_git(
            identity,
            "-c",
            "gpg.format=ssh",
            "-c",
            "gpg.minTrustLevel=fully",
            "-c",
            f"gpg.ssh.program={ssh_keygen}",
            "-c",
            f"gpg.ssh.allowedSignersFile={signer_path}",
            "-c",
            f"gpg.ssh.revocationFile={os.devnull}",
            "verify-tag",
            "--raw",
            tag_object_oid,
        )
    if result.returncode != 0:
        raise ReleaseCoordinateError(
            "release tag has a valid signature from a repository-trusted signer: "
            + _diagnostic(result)
        )


def _archive_digest(identity: _RepositoryIdentity, commit_oid: str) -> str:
    digest = sha256()
    _reject_git_local_overrides(identity)
    with tempfile.TemporaryFile(prefix="release-archive-") as archive:
        result = subprocess.run(
            _git_command(
                identity,
                "-c",
                "tar.umask=0002",
                "archive",
                "--format=tar",
                commit_oid,
            ),
            cwd=identity.worktree_root,
            check=False,
            stdout=archive,
            stderr=subprocess.PIPE,
            env=_git_environment(),
        )
        _reject_git_local_overrides(identity)
        diagnostic = result.stderr.decode("utf-8", errors="replace").strip()
        archive.seek(0)
        for block in iter(lambda: archive.read(1024 * 1024), b""):
            digest.update(block)
    if result.returncode != 0:
        raise ReleaseCoordinateError(
            f"git archive exited with {result.returncode}: {diagnostic or 'no diagnostic'}"
        )
    return f"sha256:{digest.hexdigest()}"


def _instant(value: str) -> datetime:
    try:
        instant = datetime.fromisoformat(value)
    except (AttributeError, ValueError) as error:
        raise ReleaseCoordinateError(
            f"release promotion instant is valid ISO 8601: {value!r}"
        ) from error
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ReleaseCoordinateError(
            f"release promotion instant has an explicit UTC offset: {value!r}"
        )
    return instant.astimezone(UTC)


def _difference_summary(
    differences: Mapping[str, Mapping[str, str | None]],
    expected_label: str,
) -> str:
    return "; ".join(
        f"{field}: {expected_label}={values[expected_label]!r}, "
        f"derived={values['derived']!r}"
        for field, values in sorted(differences.items())
    )


def _git_environment() -> dict[str, str]:
    environment = {
        key: value for key, value in os.environ.items() if not key.startswith("GIT_")
    }
    environment.update(
        {
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_ATTR_NOSYSTEM": "1",
            "GIT_NO_REPLACE_OBJECTS": "1",
            "LANG": "C",
            "LC_ALL": "C",
        }
    )
    return environment


def _git_command(
    identity: _RepositoryIdentity,
    *arguments: str,
) -> list[str]:
    _reject_git_local_overrides(identity)
    return [
        str(identity.git_program),
        "--no-pager",
        "--no-replace-objects",
        "--literal-pathspecs",
        f"--git-dir={identity.git_directory}",
        f"--work-tree={identity.worktree_root}",
        "-c",
        "core.fsmonitor=false",
        "-c",
        "core.untrackedCache=false",
        "-c",
        f"core.attributesFile={os.devnull}",
        *arguments,
    ]


def _run_git_bytes(identity: _RepositoryIdentity, *arguments: str) -> bytes:
    result = subprocess.run(
        _git_command(identity, *arguments),
        cwd=identity.worktree_root,
        check=False,
        capture_output=True,
        env=_git_environment(),
    )
    if result.returncode != 0:
        diagnostic = result.stderr.decode("utf-8", errors="replace").strip()
        raise ReleaseCoordinateError(
            f"git {' '.join(arguments)} exited with {result.returncode}: "
            f"{diagnostic or 'no diagnostic'}"
        )
    return result.stdout


def _git_text(identity: _RepositoryIdentity, *arguments: str) -> str:
    result = _run_git(identity, *arguments)
    if result.returncode != 0:
        raise ReleaseCoordinateError(
            _command_failure("git " + " ".join(arguments), result)
        )
    return result.stdout.strip()


def _run_git(
    identity: _RepositoryIdentity,
    *arguments: str,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        _git_command(identity, *arguments),
        cwd=identity.worktree_root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=_git_environment(),
    )


def _diagnostic(result: subprocess.CompletedProcess[str]) -> str:
    return result.stderr.strip() or result.stdout.strip() or "no diagnostic"


def _command_failure(
    command: str,
    result: subprocess.CompletedProcess[str],
) -> str:
    return f"{command} exited with {result.returncode}: {_diagnostic(result)}"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, default=ROOT)
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    parser.add_argument("--accepted-ref", default=DEFAULT_ACCEPTED_REF)
    parser.add_argument(
        "--require-observed",
        action="store_true",
        help="return nonzero while the promotion receipt remains candidate_ready",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        result = verify_release_coordinate(
            args.repository,
            receipt_path=args.receipt,
            accepted_ref=args.accepted_ref,
            require_observed=args.require_observed,
        )
    except (OSError, ValueError, ReleaseCoordinateError) as error:
        print(
            f"Release-coordinate verification requires attention: {error}",
            file=sys.stderr,
        )
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
