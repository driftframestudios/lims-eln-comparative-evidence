"""Local filesystem ownership shared by complete artifact publishers.

Callers control the parent namespace. Independent publishers use distinct
private staging names; each final name identifies complete bytes. Receivers
inspect quiescent artifacts. Abrupt process death can retain private staging.
"""
from __future__ import annotations

from contextlib import contextmanager
import ctypes
import errno
import os
from pathlib import Path
import shutil
import signal
import stat
import sys
from uuid import uuid4

from .artifact_boundary import _owned_binary_stream, _read_regular_file


def _directory_flags() -> int:
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise OSError(errno.ENOTSUP, "complete publication requires supported filesystem primitives")
    return os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW


@contextmanager
def _directory(path: Path, *, create: bool = False):
    """Anchor each concrete path component before opening the next one."""
    absolute = path.absolute()
    descriptor = os.open(absolute.anchor, _directory_flags())
    failure = None
    try:
        for component in absolute.parts[1:]:
            if create:
                try:
                    os.mkdir(component, dir_fd=descriptor)
                except FileExistsError:
                    pass
            child = os.open(component, _directory_flags(), dir_fd=descriptor)
            previous = descriptor
            descriptor = child
            os.close(previous)
        yield descriptor
    except BaseException as error:
        failure = error
        raise
    finally:
        try:
            os.close(descriptor)
        except BaseException as error:
            if failure is None:
                raise
            _attach_cleanup(failure, error)


def _attach_cleanup(primary: BaseException, cleanup: BaseException) -> None:
    previous = getattr(primary, "cleanup_error", None)
    primary.cleanup_error = cleanup if previous is None else BaseExceptionGroup(
        "Resource cleanup observations", [previous, cleanup],
    )
    primary.add_note("Resource cleanup needs local review; the primary failure remains available.")


def _exclusive_rename():
    """Bind the platform's five-argument, errno-reporting exclusive rename ABI."""
    symbol, flag = {
        "linux": ("renameat2", 1),       # RENAME_NOREPLACE
        "darwin": ("renameatx_np", 4),  # RENAME_EXCL
    }.get(sys.platform, (None, None))
    if symbol is None or not shutil.rmtree.avoids_symlink_attacks:
        raise OSError(errno.ENOTSUP, "complete publication requires supported filesystem primitives")
    library = ctypes.CDLL(None, use_errno=True)
    try:
        rename = getattr(library, symbol)
    except AttributeError as error:
        raise OSError(errno.ENOTSUP, "complete publication requires supported filesystem primitives") from error
    rename.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint)
    rename.restype = ctypes.c_int

    def publish(parent_fd: int, source: str, destination: str) -> None:
        if rename(parent_fd, os.fsencode(source), parent_fd, os.fsencode(destination), flag) != 0:
            number = ctypes.get_errno()
            raise OSError(number, os.strerror(number))

    return publish


@contextmanager
def _record_transition():
    """Record resource ownership before delivering a pending termination signal."""
    previous = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGINT, signal.SIGTERM})
    try:
        yield
    finally:
        signal.pthread_sigmask(signal.SIG_SETMASK, previous)


def _write_artifact(directory_fd: int, name: str, payload: bytes) -> None:
    descriptor = None
    try:
        with _record_transition():
            descriptor = os.open(
                name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600, dir_fd=directory_fd,
            )
    except BaseException as error:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except BaseException as cleanup:
                _attach_cleanup(error, cleanup)
        raise
    with _owned_binary_stream(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def _same_directory(parent_fd: int, name: str, identity: tuple[int, int]) -> bool:
    info = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    return stat.S_ISDIR(info.st_mode) and (info.st_dev, info.st_ino) == identity


def _cleanup_owned(parent_fd: int, name: str, identity: tuple[int, int]) -> None:
    if not _same_directory(parent_fd, name, identity):
        raise ValueError("staging identity requires the invocation-owned directory")
    shutil.rmtree(name, dir_fd=parent_fd)


class PublicationError(ValueError):
    """Expose final-name state and any invocation-owned recovery work."""

    def __init__(self, stage, *, published=False, pending_name=None, cleanup_error=None):
        self.stage = stage
        self.published = published
        self.pending_name = pending_name
        self.cleanup_error = cleanup_error
        if published:
            action = "complete artifacts are visible; verify them before retrying"
        elif stage == "destination_exists":
            action = "prior artifacts are preserved; choose a fresh report directory or a new evidence identity"
        else:
            action = "destination is preserved; resolve the reported failure and retry the same target"
        if cleanup_error is not None:
            action += "; review invocation-owned staging cleanup"
        super().__init__(f"artifact {stage}: {action}")


class _Publication:
    def __init__(self):
        self.stage = "acquire"
        self.published = False
        self.pending_name = None


@contextmanager
def _staged(destination: Path):
    """Acquire one private sibling directory and release only its owned state."""
    state = _Publication()
    try:
        with _directory(destination.absolute().parent, create=True) as parent_fd:
            descriptor = identity = None
            failure = None
            try:
                with _record_transition():
                    name = ".artifact-pending-" + uuid4().hex
                    os.mkdir(name, mode=0o700, dir_fd=parent_fd)
                    state.pending_name = name
                    info = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
                    identity = (info.st_dev, info.st_ino)
                    descriptor = os.open(name, _directory_flags(), dir_fd=parent_fd)
                opened = os.fstat(descriptor)
                if (opened.st_dev, opened.st_ino) != identity:
                    raise ValueError("staging identity requires the acquired directory")
                yield state, parent_fd, descriptor
            except BaseException as error:
                failure = error
                raise
            finally:
                cleanups = []
                if descriptor is not None:
                    try:
                        os.close(descriptor)
                    except BaseException as error:
                        cleanups.append(error)
                if state.pending_name is not None:
                    try:
                        _cleanup_owned(parent_fd, state.pending_name, identity)
                        state.pending_name = None
                    except BaseException as error:
                        cleanups.append(error)
                if cleanups:
                    cleanup = cleanups[0] if len(cleanups) == 1 else BaseExceptionGroup(
                        "Staging cleanup observations", cleanups,
                    )
                    if failure is not None:
                        _attach_cleanup(failure, cleanup)
                    else:
                        state.stage = "cleanup"
                        raise cleanup
    except BaseException as error:
        if isinstance(error, (KeyboardInterrupt, SystemExit)):
            error.published = state.published
            error.pending_name = state.pending_name
            raise
        raise PublicationError(
            state.stage, published=state.published, pending_name=state.pending_name,
            cleanup_error=getattr(error, "cleanup_error", error if state.stage == "cleanup" else None),
        ) from error


def _same_bytes(directory_fd: int, name: str, payload: bytes) -> bool:
    return _read_regular_file(
        Path(name), name, max_bytes=len(payload), directory_fd=directory_fd,
    ) == payload


def publish_manifest(payload: bytes, destination: Path) -> None:
    """Publish immutable generated JSON; equal bytes resolve an accepted retry."""
    destination = destination.absolute()
    destination = destination.parent.resolve() / destination.name
    with _staged(destination) as (state, parent_fd, descriptor):
        state.stage = "write"
        _write_artifact(descriptor, "manifest.json", payload)
        state.stage = "verify"
        if not _same_bytes(descriptor, "manifest.json", payload):
            raise ValueError("manifest candidate requires its complete prepared bytes")
        os.fsync(descriptor)
        state.stage = "publish"
        try:
            with _record_transition():
                os.link(
                    "manifest.json", destination.name,
                    src_dir_fd=descriptor, dst_dir_fd=parent_fd, follow_symlinks=False,
                )
                state.published = True
        except FileExistsError:
            state.stage = "destination_exists"
            if not _same_bytes(parent_fd, destination.name, payload):
                raise ValueError("accepted evidence is immutable; choose a new evidence identity")
            state.published = True
        state.stage = "sync"
        os.fsync(parent_fd)


def publish_report(payloads: dict[str, bytes], destination: Path, verify) -> None:
    """Atomically fill an absent/empty directory or accept byte-identical replay."""
    exclusive = _exclusive_rename()
    destination = destination.absolute()
    destination = destination.parent.resolve() / destination.name
    with _staged(destination) as (state, parent_fd, descriptor):
        state.stage = "write"
        for name, payload in payloads.items():
            _write_artifact(descriptor, name, payload)
        state.stage = "verify"
        verify(descriptor)
        os.fsync(descriptor)
        state.stage = "publish"
        # A concrete existing empty directory is a supported legacy destination.
        # Rename replaces it atomically; a competing populated directory survives.
        try:
            info = os.stat(destination.name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            existing = False
        else:
            existing = True
            if not stat.S_ISDIR(info.st_mode):
                state.stage = "destination_exists"
                raise ValueError("report destination requires a concrete empty or fresh directory")
        try:
            with _record_transition():
                if existing:
                    os.rename(state.pending_name, destination.name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
                else:
                    exclusive(parent_fd, state.pending_name, destination.name)
                state.published = True
                state.pending_name = None
        except OSError as error:
            if error.errno not in (errno.EEXIST, errno.ENOTEMPTY):
                raise
            state.stage = "destination_exists"
            with _directory(destination) as existing_fd:
                with os.scandir(existing_fd) as entries:
                    names = set()
                    for entry in entries:
                        names.add(entry.name)
                        if len(names) > len(payloads):
                            break
                if names != payloads.keys() or any(
                    not _same_bytes(existing_fd, name, payload) for name, payload in payloads.items()
                ):
                    raise ValueError("completed report is immutable; choose a fresh output directory") from error
            state.published = True
        state.stage = "sync"
        os.fsync(parent_fd)
