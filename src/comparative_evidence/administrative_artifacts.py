"""Finalize one independently verified administrative study/report bundle.

The three-file profile composes the released regular-file reader and the
invocation-owned staging pattern from infra/container_runtime.py. Its package
API owns caller-selected destinations, bounded recomputation and exclusive
publication. The released two-file report contract retains its own verifier.
Work is O(study + report + HTML bytes), including bounded scoring and hashing.
"""

from __future__ import annotations

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


def _inventory_at(directory_fd: int, pack: ScenarioPack) -> dict[str, str]:
    from .administrative_evaluation import EvaluationReport, demonstration_study, evaluate, render_html

    names = set()
    with os.scandir(directory_fd) as entries:
        for entry in entries:
            names.add(entry.name)
            if len(names) > len(ADMINISTRATIVE_ARTIFACTS):
                raise AdministrativeArtifactError("bundle_membership")
    if names != ADMINISTRATIVE_ARTIFACTS:
        raise AdministrativeArtifactError("bundle_membership")
    try:
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
        report = EvaluationReport.model_validate_json(content["comparison.json"], strict=True)
        if report.evidence_mode == "fixture_demonstration" and canonical_json_bytes(study) != canonical_json_bytes(demonstration_study(pack)):
            raise AdministrativeArtifactError("bundle_fixture_identity")
        reproduced = evaluate(pack, study, evidence_mode=report.evidence_mode)
        if content["study.json"] != canonical_json_bytes(study) + b"\n":
            raise AdministrativeArtifactError("bundle_study_projection")
        if content["comparison.json"] != canonical_json_bytes(reproduced) + b"\n":
            raise AdministrativeArtifactError("bundle_report_binding")
        if content["comparison.html"] != render_html(reproduced).encode("utf-8"):
            raise AdministrativeArtifactError("bundle_html_projection")
    except AdministrativeArtifactError:
        raise
    except (ValueError, TypeError, RecursionError, OSError) as error:
        raise AdministrativeArtifactError("bundle_content") from error
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
    except AdministrativeArtifactError:
        raise
    except (ValueError, TypeError, OSError) as error:
        raise AdministrativeArtifactError("bundle_source_or_directory") from error


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
    from .administrative_evaluation import render_html

    stage = "prepare"
    published = False
    try:
        rename = _exclusive_rename()
        admitted_pack = admit_pack(canonical_json_bytes(pack))
        payloads = {
            "study.json": canonical_json_bytes(study) + b"\n",
            "comparison.json": canonical_json_bytes(report) + b"\n",
            "comparison.html": render_html(report).encode("utf-8"),
        }
        if any(len(payload) > ADMINISTRATIVE_ARTIFACT_LIMITS[name] for name, payload in payloads.items()):
            raise AdministrativeArtifactError("bundle_bytes")
        target = destination.absolute()
        stage = "acquire"
        with _directory(target.parent, create=True) as parent_fd:
            pending = None
            descriptor = None
            identity = None
            failure = cleanup_error = None
            inventory = None
            try:
                # An early collision saves preparation work; rename enforces the race boundary.
                try:
                    os.stat(target.name, dir_fd=parent_fd, follow_symlinks=False)
                except FileNotFoundError:
                    pass
                else:
                    stage = "destination_exists"
                    raise FileExistsError(errno.EEXIST, "destination exists")
                with _record_transition():
                    name = ".administrative-pending-" + uuid4().hex
                    os.mkdir(name, mode=0o700, dir_fd=parent_fd)
                    pending = name
                    info = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
                    identity = (info.st_dev, info.st_ino)
                descriptor = os.open(pending, _directory_flags(), dir_fd=parent_fd)
                opened = os.fstat(descriptor)
                if (opened.st_dev, opened.st_ino) != identity:
                    raise AdministrativeArtifactError("bundle_staging_identity")
                stage = "write"
                for name, payload in payloads.items():
                    _write_artifact(descriptor, name, payload)
                stage = "verify"
                inventory = _inventory_at(descriptor, admitted_pack)
                stage = "sync"
                os.fsync(descriptor)
                stage = "publish"
                if not _same_directory(parent_fd, pending, identity):
                    raise AdministrativeArtifactError("bundle_staging_identity")
                with _record_transition():
                    rename(parent_fd, pending, target.name)
                    published = True
                    pending = None
                stage = "sync"
                os.fsync(parent_fd)
            except BaseException as error:
                failure = error
            finally:
                if descriptor is not None:
                    try:
                        os.close(descriptor)
                    except OSError as error:
                        cleanup_error = error
                if pending is not None:
                    try:
                        _cleanup_owned(parent_fd, pending, identity)
                    except (OSError, ValueError) as error:
                        cleanup_error = error if cleanup_error is None else ExceptionGroup(
                            "Staging cleanup observations", [cleanup_error, error],
                        )
            if isinstance(failure, (KeyboardInterrupt, SystemExit)):
                if cleanup_error is not None:
                    _attach_cleanup(failure, cleanup_error)
                raise failure
            if failure is not None or cleanup_error is not None:
                nested_cleanup = getattr(failure, "cleanup_error", None)
                if nested_cleanup is not None:
                    cleanup_error = nested_cleanup if cleanup_error is None else BaseExceptionGroup(
                        "Resource cleanup observations", [nested_cleanup, cleanup_error],
                    )
                if stage == "publish" and isinstance(failure, FileExistsError):
                    stage = "destination_exists"
                raise AdministrativePublicationError(
                    stage if failure is not None else "cleanup",
                    published=published, cleanup_error=cleanup_error, pending_name=pending,
                ) from failure or cleanup_error
            return inventory
    except AdministrativePublicationError:
        raise
    except (ValueError, OSError) as error:
        raise AdministrativePublicationError(
            stage, published=published,
            cleanup_error=getattr(error, "cleanup_error", None),
        ) from error
