"""Finalize one independently verified administrative study/report bundle.

The three-file profile composes the released regular-file reader and the
invocation-owned staging pattern from infra/container_runtime.py. Its package
API owns caller-selected destinations, bounded recomputation and exclusive
publication. The released two-file report contract retains its own verifier.
Preparation and file traversal scale with artifact bytes. Study admission and
independent scoring retain their own bounded graph, sorting and model costs.
The staging owner adds constant resource state and one attempt per release.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
import errno
from hashlib import sha256
import os
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

from lims_eln_contracts.administrative_study import admit_administrative_study
from lims_eln_contracts.canonical import canonical_json_bytes, strict_json_loads
from lims_eln_sim.administrative_pack import MAX_BYTES, admit_pack

from .artifact_boundary import BYTE_ORDER_MARKS, _read_regular_file
from .filesystem_publication import (
    _attach_cleanup, _cleanup_owned, _directory, _directory_flags,
    _exclusive_rename, _record_transition, _same_directory, _write_artifact,
)

if TYPE_CHECKING:
    from lims_eln_contracts.administrative_study import AdministrativeStudy
    from lims_eln_sim.administrative_pack import ScenarioPack
    from .administrative_evaluation import EvaluationReport


ADMINISTRATIVE_ARTIFACT_LIMITS = {
    "study.json": MAX_BYTES,
    "comparison.json": 4 * 1024 * 1024,
    "comparison.html": 16 * 1024 * 1024,
}
ADMINISTRATIVE_ARTIFACTS = frozenset(ADMINISTRATIVE_ARTIFACT_LIMITS)


class AdministrativeArtifactError(ValueError):
    """A fixed code identifies the bundle boundary needing another observation."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code + ": verify the complete bundle against its source pack")


class AdministrativePublicationError(ValueError):
    """Keep publication state and cleanup diagnostics available to the caller."""

    def __init__(self, stage: str, *, published: bool, cleanup_error: BaseException | None = None, pending_name: str | None = None):
        self.code = "bundle_" + stage
        self.stage = stage
        self.published = published
        self.cleanup_error = cleanup_error
        self.pending_name = pending_name
        recovery = (
            "the complete bundle is visible; verify it before another comparison"
            if published else "the destination is preserved; retry with a fresh or still-absent target"
        )
        if cleanup_error is not None:
            recovery += "; invocation-owned staging needs local cleanup review"
        super().__init__(self.code + ": " + recovery)


def _interruption(error: BaseException | None) -> BaseException | None:
    """Find the first control signal in the bounded owned-cleanup observations."""
    if isinstance(error, (KeyboardInterrupt, SystemExit)):
        return error
    if isinstance(error, BaseExceptionGroup):
        for child in error.exceptions:
            found = _interruption(child)
            if found is not None:
                return found
    return None


def _other_cleanup(error: BaseException | None, interruption: BaseException) -> BaseException | None:
    if error is interruption:
        return None
    if isinstance(error, BaseExceptionGroup):
        # subgroup preserves traceback, cause, context and notes on retained groups.
        return error.subgroup(
            lambda item: not isinstance(item, BaseExceptionGroup) and item is not interruption,
        )
    return error


def _failure_details(
    error: BaseException, *, cleanup_only: bool = False,
) -> tuple[BaseException | None, BaseException | None]:
    """Preserve control meaning at each owned translation and record cause once."""
    cleanup = getattr(error, "cleanup_error", None)
    if cleanup_only:
        cleanup = error if cleanup is None else BaseExceptionGroup(
            "Resource cleanup observations", [error, cleanup],
        )
    interruption = _interruption(error) or _interruption(cleanup)
    if interruption is not None:
        if hasattr(error, "retained_stream"):
            interruption.retained_stream = error.retained_stream
            interruption.retained_descriptor = error.retained_descriptor
        if interruption is not error:
            remaining = _other_cleanup(cleanup, interruption)
            if remaining is not None:
                _attach_cleanup(interruption, remaining)
            if not cleanup_only and getattr(interruption, "primary_error", None) is None:
                interruption.primary_error = error
        if not hasattr(interruption, "primary_error"):
            interruption.primary_error = None
        if not hasattr(interruption, "cleanup_error"):
            interruption.cleanup_error = None
    return interruption, cleanup


@contextmanager
def _artifact_io():
    """Normalize only the shared file helpers' owned stream outcomes.

    Their direct exception groups contain teardown observations after a
    successful body. Body failures instead retain attached cleanup_error.
    """
    try:
        yield
    except BaseException as error:
        interruption, _ = _failure_details(error, cleanup_only=isinstance(error, BaseExceptionGroup))
        if interruption is not None:
            raise interruption from interruption.primary_error
        raise


def _inventory_at(directory_fd: int, pack: ScenarioPack) -> dict[str, str]:
    from .administrative_evaluation import demonstration_study, evaluate, render_html
    from .administrative_report import admit_evaluation_report

    names = set()
    with os.scandir(directory_fd) as entries:
        for entry in entries:
            names.add(entry.name)
            if len(names) > len(ADMINISTRATIVE_ARTIFACTS):
                raise AdministrativeArtifactError("bundle_membership")
    if names != ADMINISTRATIVE_ARTIFACTS:
        raise AdministrativeArtifactError("bundle_membership")
    try:
        with _artifact_io():
            content = {
                name: _read_regular_file(
                    Path(name), name, max_bytes=limit,
                    directory_fd=directory_fd, single_link=True,
                )
                for name, limit in ADMINISTRATIVE_ARTIFACT_LIMITS.items()
            }
        for name in ("study.json", "comparison.json"):
            if any(content[name].startswith(marker) for marker in BYTE_ORDER_MARKS):
                raise AdministrativeArtifactError("bundle_encoding")
            strict_json_loads(content[name].decode("utf-8"))
        study = admit_administrative_study(content["study.json"])
        report = admit_evaluation_report(content["comparison.json"])
        if report.evidence_mode == "fixture_demonstration" and canonical_json_bytes(study) != canonical_json_bytes(demonstration_study(pack)):
            raise AdministrativeArtifactError("bundle_fixture_identity")
        reproduced = evaluate(pack, study, evidence_mode=report.evidence_mode)
        if content["study.json"] != canonical_json_bytes(study) + b"\n":
            raise AdministrativeArtifactError("bundle_study_projection")
        if content["comparison.json"] != canonical_json_bytes(reproduced) + b"\n":
            raise AdministrativeArtifactError("bundle_report_binding")
        if content["comparison.html"] != render_html(reproduced).encode("utf-8"):
            raise AdministrativeArtifactError("bundle_html_projection")
    except (ValueError, TypeError, RecursionError, OSError) as error:
        interruption, cleanup = _failure_details(error)
        if interruption is not None:
            raise interruption from interruption.primary_error
        if isinstance(error, AdministrativeArtifactError):
            raise
        translated = AdministrativeArtifactError("bundle_content")
        if cleanup is not None:
            _attach_cleanup(translated, cleanup)
        raise translated from error
    return {name: "sha256:" + sha256(payload).hexdigest() for name, payload in content.items()}


def administrative_artifact_inventory(root: Path, pack: ScenarioPack) -> dict[str, str]:
    """Verify a quiescent bundle by recomputing from its admitted study and pack.

    This receiver requires the independently received pack. Standalone semantic
    report admission remains a separate contract; these checks prove this
    bundle's exact source binding, complete membership and HTML projection.
    """
    try:
        admitted_pack = admit_pack(canonical_json_bytes(pack))
        with _directory(root) as descriptor:
            return _inventory_at(descriptor, admitted_pack)
    except (ValueError, TypeError, OSError) as error:
        interruption, cleanup = _failure_details(error)
        if interruption is not None:
            raise interruption from interruption.primary_error
        if isinstance(error, AdministrativeArtifactError):
            raise
        translated = AdministrativeArtifactError("bundle_source_or_directory")
        if cleanup is not None:
            _attach_cleanup(translated, cleanup)
        raise translated from error


class _Phase(Enum):
    PREPARE = "prepare"
    ACQUIRE = "acquire"
    WRITE = "write"
    VERIFY = "verify"
    SYNC_STAGING = "sync_staging"
    PUBLISH = "publish"
    SYNC_PARENT = "sync_parent"
    CLEANUP = "cleanup"
    DESTINATION_EXISTS = "destination_exists"

    @property
    def public_stage(self) -> str:
        # Existing callers receive one sync stage; ownership distinguishes its sides.
        return "sync" if self in (_Phase.SYNC_STAGING, _Phase.SYNC_PARENT) else self.value


@dataclass
class _PublicationState:
    phase: _Phase = _Phase.PREPARE
    published: bool = False
    pending_name: str | None = None
    operation_error: BaseException | None = None


class _AdministrativeStaging:
    """Own the acquired descriptor and private sibling until rename or release."""

    def __init__(self, parent_fd: int, state: _PublicationState):
        self.parent_fd = parent_fd
        self.state = state
        self.descriptor: int | None = None
        self.identity: tuple[int, int] | None = None

    def acquire(self, target_name: str) -> None:
        # The early check saves staging work; exclusive rename enforces the race boundary.
        try:
            os.stat(target_name, dir_fd=self.parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            self.state.phase = _Phase.DESTINATION_EXISTS
            raise FileExistsError(errno.EEXIST, "destination exists")
        with _record_transition():
            name = ".administrative-pending-" + uuid4().hex
            os.mkdir(name, mode=0o700, dir_fd=self.parent_fd)
            self.state.pending_name = name
            info = os.stat(name, dir_fd=self.parent_fd, follow_symlinks=False)
            self.identity = (info.st_dev, info.st_ino)
            self.descriptor = os.open(name, _directory_flags(), dir_fd=self.parent_fd)
        opened = os.fstat(self.descriptor)
        if (opened.st_dev, opened.st_ino) != self.identity:
            raise AdministrativeArtifactError("bundle_staging_identity")

    def publish(self, rename, target_name: str) -> None:
        if not _same_directory(self.parent_fd, self.state.pending_name, self.identity):
            raise AdministrativeArtifactError("bundle_staging_identity")
        with _record_transition():
            rename(self.parent_fd, self.state.pending_name, target_name)
            self.state.published = True
            self.state.pending_name = None

    def release(self) -> BaseException | None:
        """Attempt both owned releases, retaining their observation order."""
        observations = []
        if self.descriptor is not None:
            descriptor, self.descriptor = self.descriptor, None
            try:
                os.close(descriptor)
            except BaseException as error:
                observations.append(error)
        if self.state.pending_name is not None:
            try:
                _cleanup_owned(self.parent_fd, self.state.pending_name, self.identity)
                self.state.pending_name = None
            except BaseException as error:
                observations.append(error)
        if len(observations) == 1:
            return observations[0]
        if observations:
            return BaseExceptionGroup("Staging cleanup observations", observations)
        return None


@contextmanager
def _administrative_staging(target: Path, state: _PublicationState):
    """Finish staging and parent release before the public error policy runs."""
    state.phase = _Phase.ACQUIRE
    with _directory(target.parent, create=True) as parent_fd:
        staging = _AdministrativeStaging(parent_fd, state)
        try:
            staging.acquire(target.name)
            yield staging
        except BaseException as error:
            state.operation_error = error
            raise
        finally:
            cleanup = staging.release()
            if state.operation_error is not None:
                if cleanup is not None:
                    _attach_cleanup(state.operation_error, cleanup)
            else:
                state.phase = _Phase.CLEANUP
                if cleanup is not None:
                    raise cleanup


def _prepare_bundle(pack: ScenarioPack, study: AdministrativeStudy, report: EvaluationReport):
    from .administrative_evaluation import render_html

    admitted_pack = admit_pack(canonical_json_bytes(pack))
    payloads = {
        "study.json": canonical_json_bytes(study) + b"\n",
        "comparison.json": canonical_json_bytes(report) + b"\n",
        "comparison.html": render_html(report).encode("utf-8"),
    }
    if any(len(payload) > ADMINISTRATIVE_ARTIFACT_LIMITS[name] for name, payload in payloads.items()):
        raise AdministrativeArtifactError("bundle_bytes")
    return admitted_pack, payloads


def _raise_publication_failure(error: BaseException, state: _PublicationState) -> None:
    """Apply administrative interruption and diagnostic policy after all teardown."""
    stage = state.phase.public_stage
    interruption, cleanup = _failure_details(error, cleanup_only=state.phase is _Phase.CLEANUP)
    if interruption is not None:
        interruption.stage = stage
        interruption.published = state.published
        interruption.pending_name = state.pending_name
        if interruption.primary_error is not None:
            raise interruption from interruption.primary_error
        raise interruption
    if not isinstance(error, Exception) or (
        state.operation_error is None and state.phase is not _Phase.CLEANUP
        and not isinstance(error, (ValueError, OSError))
    ):
        raise error
    if state.phase is _Phase.PUBLISH and isinstance(error, FileExistsError):
        stage = _Phase.DESTINATION_EXISTS.value
    raise AdministrativePublicationError(
        stage, published=state.published, cleanup_error=cleanup, pending_name=state.pending_name,
    ) from error


def publish_administrative_bundle(
    pack: ScenarioPack, study: AdministrativeStudy, report: EvaluationReport, destination: Path,
) -> dict[str, str]:
    """Publish complete bytes once; a competing destination retains its contents.

    Files and staging metadata are synced before the exclusive rename; the
    parent is synced afterwards. A later sync error retains the complete final
    bundle and reports published=True. Hardware durability has its own scope.
    The caller controls the parent namespace; independent publishers own
    distinct staging names. Hostile same-user namespace mutation is outside
    this local filesystem protocol.
    """
    state = _PublicationState()
    try:
        rename = _exclusive_rename()
        admitted_pack, payloads = _prepare_bundle(pack, study, report)
        target = destination.absolute()
        with _administrative_staging(target, state) as staging:
            state.phase = _Phase.WRITE
            with _artifact_io():
                for name, payload in payloads.items():
                    _write_artifact(staging.descriptor, name, payload)
            state.phase = _Phase.VERIFY
            inventory = _inventory_at(staging.descriptor, admitted_pack)
            state.phase = _Phase.SYNC_STAGING
            os.fsync(staging.descriptor)
            state.phase = _Phase.PUBLISH
            staging.publish(rename, target.name)
            state.phase = _Phase.SYNC_PARENT
            os.fsync(staging.parent_fd)
        return inventory
    except BaseException as error:
        _raise_publication_failure(error, state)
