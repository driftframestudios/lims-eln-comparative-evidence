"""Build and verify the deterministic Comparative Evidence Pages projection."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha1, sha256
from html import escape
from html.parser import HTMLParser
import json
import os
from pathlib import Path, PurePosixPath
import posixpath
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from typing import Any, Iterator
from urllib.parse import quote, urlsplit, urlunsplit


ROOT = Path(__file__).resolve().parents[1]


DEFAULT_CANONICAL_ORIGIN = (
    "https://driftframestudios.github.io/lims-eln-comparative-evidence/"
)
DEFAULT_REPOSITORY_URL = (
    "https://github.com/driftframestudios/lims-eln-comparative-evidence"
)
REVISION_PATTERN = re.compile(r"[0-9a-f]{40}")
HOST_PATTERN = re.compile(
    r"(?=.{1,253}\Z)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
)
MANIFEST_PATH = "projection-manifest.json"
MANIFEST_VERSION = "1.0.0"
PROJECTION_OWNER = "comparative-evidence-pages-builder"
MANIFEST_FILE_SCOPE = (
    "Every projection file except projection-manifest.json; the manifest "
    "is the bounded identity carrier and cannot contain its own digest."
)
RELEASED_SOURCE_STANDINGS = frozenset(
    {"clean_exact_revision", "validation_fixture"}
)
REFERENCE_REPORT_PATHS = (
    "reports/reference/comparison.html",
    "reports/reference/comparison.json",
)
GOLDEN_REPORT_PATHS = (
    "reports/golden-specimen/comparison.html",
    "reports/golden-specimen/comparison.json",
)
REPORT_PATHS = REFERENCE_REPORT_PATHS + GOLDEN_REPORT_PATHS
SOURCE_LINK_PATHS = (
    "specification/comparison-profile.json",
    "fixtures/pairs/simulation-observation.json",
    "fixtures/contracts/planned-observation.json",
    "specification/golden-specimen-verification-profile.json",
    "fixtures/pairs/enterprise-postgresql-observation.json",
    "fixtures/pairs/simulation-golden-specimen-observation.json",
    "constellation.lock.json",
    "src/comparative_evidence/compare.py",
    "src/comparative_evidence/golden_verification.py",
    "src/comparative_evidence/report.py",
    "release/repository-role.json",
)
REPORT_INPUT_PATHS = (
    "fixtures/pairs/simulation-observation.json",
    "fixtures/contracts/planned-observation.json",
    "specification/comparison-profile.json",
    "fixtures/pairs/enterprise-postgresql-observation.json",
    "fixtures/pairs/simulation-golden-specimen-observation.json",
    "specification/golden-specimen-verification-profile.json",
    "constellation.lock.json",
)
CONTRACT_RESOURCE_PATHS = (
    "src/comparative_evidence/contract_resources/contract-binding.v1.json",
    "src/comparative_evidence/contract_resources/golden-specimen.v1.json",
    "src/comparative_evidence/contract_resources/golden-specimen-result-projection.v1.schema.json",
    "src/comparative_evidence/contract_resources/observation-envelope.v1.schema.json",
)
RUNTIME_SOURCE_PATHS = (
    "tools/build_pages.py",
    "src/comparative_evidence/__init__.py",
    "src/comparative_evidence/artifact_boundary.py",
    "src/comparative_evidence/compare.py",
    "src/comparative_evidence/contract_v1.py",
    "src/comparative_evidence/database_release.py",
    "src/comparative_evidence/gate.py",
    "src/comparative_evidence/golden_verification.py",
    "src/comparative_evidence/model.py",
    "src/comparative_evidence/normalize.py",
    "src/comparative_evidence/publication.py",
    "src/comparative_evidence/report.py",
    "src/comparative_evidence/safety.py",
    "src/comparative_evidence/simulated_closure.py",
)
REQUIRED_COMMITTED_PATHS = frozenset(
    REPORT_INPUT_PATHS
    + CONTRACT_RESOURCE_PATHS
    + RUNTIME_SOURCE_PATHS
    + SOURCE_LINK_PATHS
)
REGULAR_GIT_MODES = frozenset({"100644", "100755"})


class PagesBuildError(ValueError):
    """The projection returns to its source-owned publication contract."""


@dataclass(frozen=True, slots=True)
class _RuntimeBindings:
    """Project runtime loaded only after its source boundary is selected."""

    report_artifact_inventory: Any
    contract_v1_module: Any
    compare_golden_specimen: Any
    compare_synthetic_contract: Any
    ObservationEnvelope: Any
    strict_json_loads: Any
    BIG_BENCH_CANARY: str
    MAPS_CANARY: str
    PUBLIC_ATTRIBUTION: str
    render_public_boundary: Any
    write_reports: Any


@dataclass(frozen=True, slots=True, init=False)
class _VerifiedCleanSourceProof:
    """An exact HEAD tree coordinate created only by the Git observation path."""

    revision: str
    tree: str
    repository_url: str
    repository_identity: _RepositoryIdentity
    tracked_blobs: tuple[_TrackedBlob, ...]


@dataclass(frozen=True, slots=True)
class _RepositoryIdentity:
    """Resolved identity of one Git worktree and its private Git directory."""

    worktree_root: Path
    git_directory: Path
    common_directory: Path


@dataclass(frozen=True, slots=True, order=True)
class _TrackedBlob:
    """One regular file and executable-mode identity from an exact Git tree."""

    path: str
    mode: str
    object_id: str


@dataclass(frozen=True, slots=True)
class ValidationFixtureSourceProof:
    """An explicit non-publication source coordinate for deterministic tests."""

    revision: str
    repository_url: str = DEFAULT_REPOSITORY_URL

    def __post_init__(self) -> None:
        if REVISION_PATTERN.fullmatch(self.revision) is None:
            raise PagesBuildError(
                "validation fixture source requires one full 40-character Git SHA"
            )
        object.__setattr__(self, "repository_url", _repository_url(self.repository_url))


SourceProof = _VerifiedCleanSourceProof | ValidationFixtureSourceProof


class _LinkCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[str] = []
        self.canonicals: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        lookup = dict(attrs)
        if tag in {"a", "link"} and lookup.get("href"):
            self.links.append(str(lookup["href"]))
        if (
            tag == "link"
            and lookup.get("href")
            and "canonical" in str(lookup.get("rel", "")).split()
        ):
            self.canonicals.append(str(lookup["href"]))
        if tag in {"img", "script", "source"} and lookup.get("src"):
            self.links.append(str(lookup["src"]))


def _safe_relative_path(relative: str) -> PurePosixPath:
    candidate = PurePosixPath(relative)
    if (
        not relative
        or candidate.is_absolute()
        or candidate.as_posix() != relative
        or any(part in {"", ".", ".."} for part in candidate.parts)
    ):
        raise PagesBuildError("source and projection paths require contained names")
    return candidate


def _read_regular_bytes(root: Path, relative: str, *, label: str) -> tuple[bytes, int]:
    if not hasattr(os, "O_NOFOLLOW"):
        raise PagesBuildError(
            "source and projection reads require operating-system no-follow support"
        )
    candidate = _safe_relative_path(relative)
    current = root
    for part in candidate.parts[:-1]:
        current = current / part
        try:
            parent_status = os.lstat(current)
        except OSError as exc:
            raise PagesBuildError(f"{label} requires a readable regular path") from exc
        if not stat.S_ISDIR(parent_status.st_mode):
            raise PagesBuildError(f"{label} requires regular files inside directories")

    path = root.joinpath(*candidate.parts)
    flags = os.O_RDONLY | os.O_NOFOLLOW
    if hasattr(os, "O_NONBLOCK"):
        flags |= os.O_NONBLOCK
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise PagesBuildError(f"{label} requires a readable regular file") from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise PagesBuildError(f"{label} requires regular file bytes")
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
        raise PagesBuildError(f"{label} changed while its bytes were read")
    return b"".join(chunks), before.st_mode


def _load_object(
    repository_root: Path,
    relative: str,
    *,
    runtime: _RuntimeBindings,
) -> dict[str, Any]:
    raw, _ = _read_regular_bytes(
        repository_root,
        relative,
        label=f"source input {relative}",
    )
    value = runtime.strict_json_loads(raw)
    if not isinstance(value, dict):
        raise PagesBuildError(f"{relative} requires one JSON object")
    return value


def _load_runtime(
    source_root: Path,
    *,
    require_fresh: bool = False,
) -> _RuntimeBindings:
    """Load project modules from one selected regular source tree."""

    if require_fresh and any(
        name == "comparative_evidence" or name.startswith("comparative_evidence.")
        for name in sys.modules
    ):
        raise PagesBuildError(
            "isolated materialized runtime requires a fresh Python module graph"
        )
    source_directory = source_root / "src"
    try:
        source_status = os.lstat(source_directory)
    except OSError as exc:
        raise PagesBuildError(
            "project runtime requires its committed source directory"
        ) from exc
    if stat.S_ISLNK(source_status.st_mode) or not stat.S_ISDIR(source_status.st_mode):
        raise PagesBuildError("project runtime requires one regular source directory")

    source_entry = str(source_directory)
    sys.path.insert(0, source_entry)
    try:
        from comparative_evidence import contract_v1 as contract_v1_module
        from comparative_evidence.artifact_boundary import report_artifact_inventory
        from comparative_evidence.compare import compare_synthetic_contract
        from comparative_evidence.golden_verification import compare_golden_specimen
        from comparative_evidence.model import ObservationEnvelope, strict_json_loads
        from comparative_evidence.publication import (
            BIG_BENCH_CANARY,
            MAPS_CANARY,
            PUBLIC_ATTRIBUTION,
            render_public_boundary,
        )
        from comparative_evidence.report import write_reports
    finally:
        if sys.path and sys.path[0] == source_entry:
            del sys.path[0]

    if require_fresh:
        resolved_source = source_directory.resolve(strict=True)
        for name, module in tuple(sys.modules.items()):
            if name != "comparative_evidence" and not name.startswith(
                "comparative_evidence."
            ):
                continue
            location = getattr(module, "__file__", None)
            if not isinstance(location, str):
                continue
            try:
                resolved_location = Path(location).resolve(strict=True)
            except OSError as exc:
                raise PagesBuildError(
                    "project runtime module requires a readable materialized source"
                ) from exc
            if not resolved_location.is_relative_to(resolved_source):
                raise PagesBuildError(
                    "project runtime modules require the materialized source tree"
                )

    return _RuntimeBindings(
        report_artifact_inventory=report_artifact_inventory,
        contract_v1_module=contract_v1_module,
        compare_golden_specimen=compare_golden_specimen,
        compare_synthetic_contract=compare_synthetic_contract,
        ObservationEnvelope=ObservationEnvelope,
        strict_json_loads=strict_json_loads,
        BIG_BENCH_CANARY=BIG_BENCH_CANARY,
        MAPS_CANARY=MAPS_CANARY,
        PUBLIC_ATTRIBUTION=PUBLIC_ATTRIBUTION,
        render_public_boundary=render_public_boundary,
        write_reports=write_reports,
    )


def _git_environment() -> dict[str, str]:
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("GIT_")
    }
    environment.update(
        {
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_NO_REPLACE_OBJECTS": "1",
            "LANG": "C",
            "LC_ALL": "C",
        }
    )
    return environment


def _run_git_bytes(
    repository_root: Path,
    *arguments: str,
    identity: _RepositoryIdentity | None = None,
    input_data: bytes | None = None,
) -> bytes:
    command = [
        "git",
        "--no-pager",
        "--no-replace-objects",
    ]
    if identity is not None:
        command.extend(
            (
                f"--git-dir={identity.git_directory}",
                f"--work-tree={identity.worktree_root}",
            )
        )
    command.extend(
        (
            "-c",
            "core.fsmonitor=false",
            "-c",
            "core.untrackedCache=false",
            *arguments,
        )
    )
    result = subprocess.run(
        command,
        cwd=repository_root,
        check=False,
        capture_output=True,
        env=_git_environment(),
        input=input_data,
    )
    if result.returncode != 0:
        raise PagesBuildError(
            f"git {' '.join(arguments)} requires a readable repository coordinate"
        )
    return result.stdout


def _run_git(
    repository_root: Path,
    *arguments: str,
    identity: _RepositoryIdentity | None = None,
) -> str:
    try:
        return _run_git_bytes(
            repository_root,
            *arguments,
            identity=identity,
        ).decode("utf-8", errors="strict").strip()
    except UnicodeDecodeError as exc:
        raise PagesBuildError("Git repository coordinates require UTF-8 text") from exc


def _git_directory_from_marker(worktree_root: Path) -> Path:
    marker = worktree_root / ".git"
    try:
        marker_status = os.lstat(marker)
    except OSError as exc:
        raise PagesBuildError("publication source requires its own Git worktree") from exc
    if stat.S_ISLNK(marker_status.st_mode):
        raise PagesBuildError("publication source requires a regular Git worktree marker")
    if stat.S_ISDIR(marker_status.st_mode):
        return marker.resolve(strict=True)
    if not stat.S_ISREG(marker_status.st_mode):
        raise PagesBuildError("publication source requires a regular Git worktree marker")
    try:
        marker_text = marker.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise PagesBuildError("publication source requires a readable Git worktree marker") from exc
    lines = marker_text.splitlines()
    if len(lines) != 1 or not lines[0].startswith("gitdir: "):
        raise PagesBuildError("linked worktree marker requires one Git directory")
    value = Path(lines[0].removeprefix("gitdir: "))
    git_directory_path = (
        value if value.is_absolute() else worktree_root / value
    )
    try:
        git_directory_status = os.lstat(git_directory_path)
    except OSError as exc:
        raise PagesBuildError("linked worktree requires one Git directory") from exc
    if stat.S_ISLNK(git_directory_status.st_mode) or not stat.S_ISDIR(
        git_directory_status.st_mode
    ):
        raise PagesBuildError("linked worktree requires one regular Git directory")
    git_directory = git_directory_path.resolve(strict=True)
    backpointer = git_directory / "gitdir"
    try:
        backpointer_status = os.lstat(backpointer)
        backpointer_value = backpointer.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError) as exc:
        raise PagesBuildError("linked worktree requires its Git backpointer") from exc
    if not stat.S_ISREG(backpointer_status.st_mode) or Path(
        backpointer_value
    ).resolve(strict=True) != marker.resolve(strict=True):
        raise PagesBuildError("linked worktree backpointer requires this source root")
    return git_directory


def _repository_identity(repository_root: Path) -> _RepositoryIdentity:
    try:
        root_status = os.lstat(repository_root)
    except OSError as exc:
        raise PagesBuildError("publication source requires one readable directory") from exc
    if stat.S_ISLNK(root_status.st_mode) or not stat.S_ISDIR(root_status.st_mode):
        raise PagesBuildError("publication source requires one regular directory")
    resolved_root = repository_root.resolve(strict=True)
    worktree_root = Path(
        _run_git(resolved_root, "rev-parse", "--show-toplevel")
    ).resolve(strict=True)
    if resolved_root != worktree_root:
        raise PagesBuildError(
            "publication source requires the resolved Git worktree root"
        )
    git_directory = _git_directory_from_marker(resolved_root)
    provisional = _RepositoryIdentity(
        worktree_root=worktree_root,
        git_directory=git_directory,
        common_directory=git_directory,
    )
    observed_git_directory = Path(
        _run_git(
            resolved_root,
            "rev-parse",
            "--absolute-git-dir",
            identity=provisional,
        )
    ).resolve(strict=True)
    if observed_git_directory != git_directory:
        raise PagesBuildError("publication source Git directory requires its worktree marker")
    common_value = Path(
        _run_git(
            resolved_root,
            "rev-parse",
            "--git-common-dir",
            identity=provisional,
        )
    )
    common_directory_path = (
        common_value
        if common_value.is_absolute()
        else git_directory / common_value
    )
    try:
        common_status = os.lstat(common_directory_path)
    except OSError as exc:
        raise PagesBuildError(
            "publication source requires one common Git directory"
        ) from exc
    if stat.S_ISLNK(common_status.st_mode) or not stat.S_ISDIR(common_status.st_mode):
        raise PagesBuildError("publication source requires one regular common Git directory")
    common_directory = common_directory_path.resolve(strict=True)
    return _RepositoryIdentity(
        worktree_root=worktree_root,
        git_directory=git_directory,
        common_directory=common_directory,
    )


def _origin_repository_url(identity: _RepositoryIdentity) -> str:
    raw = _run_git_bytes(
        identity.worktree_root,
        "config",
        "--no-includes",
        "--local",
        "--get-all",
        "remote.origin.url",
        identity=identity,
    )
    try:
        values = [line for line in raw.decode("utf-8").splitlines() if line]
    except UnicodeDecodeError as exc:
        raise PagesBuildError("origin repository URL requires UTF-8 text") from exc
    if len(values) != 1:
        raise PagesBuildError("publication source requires one origin repository URL")
    return _repository_url(values[0])


def _tree_blobs(identity: _RepositoryIdentity, revision: str) -> tuple[str, tuple[_TrackedBlob, ...]]:
    tree = _run_git(
        identity.worktree_root,
        "rev-parse",
        f"{revision}^{{tree}}",
        identity=identity,
    )
    if REVISION_PATTERN.fullmatch(tree) is None:
        raise PagesBuildError("source revision requires one full Git tree identity")
    raw = _run_git_bytes(
        identity.worktree_root,
        "ls-tree",
        "-r",
        "-z",
        "--full-tree",
        revision,
        identity=identity,
    )
    entries: list[_TrackedBlob] = []
    observed_paths: set[str] = set()
    for record in raw.split(b"\0"):
        if not record:
            continue
        try:
            metadata, encoded_path = record.split(b"\t", 1)
            mode_bytes, object_type, object_id_bytes = metadata.split(b" ", 2)
            mode = mode_bytes.decode("ascii")
            object_id = object_id_bytes.decode("ascii")
            path = encoded_path.decode("utf-8", errors="strict")
        except (ValueError, UnicodeDecodeError) as exc:
            raise PagesBuildError("source tree requires readable UTF-8 blob entries") from exc
        _safe_relative_path(path)
        if (
            object_type != b"blob"
            or mode not in REGULAR_GIT_MODES
            or REVISION_PATTERN.fullmatch(object_id) is None
        ):
            raise PagesBuildError(
                "publication source requires regular HEAD blobs and executable modes"
            )
        if path in observed_paths:
            raise PagesBuildError("source tree requires unique tracked paths")
        observed_paths.add(path)
        entries.append(_TrackedBlob(path=path, mode=mode, object_id=object_id))
    if not entries:
        raise PagesBuildError("publication source requires a non-empty Git tree")
    return tree, tuple(sorted(entries))


def _index_blobs(identity: _RepositoryIdentity) -> tuple[_TrackedBlob, ...]:
    flags = _run_git_bytes(
        identity.worktree_root,
        "ls-files",
        "-v",
        "-z",
        identity=identity,
    )
    for record in flags.split(b"\0"):
        if record and not record.startswith(b"H "):
            raise PagesBuildError(
                "publication source requires visible tracked index state; clear masked index flags"
            )

    raw = _run_git_bytes(
        identity.worktree_root,
        "ls-files",
        "--stage",
        "-z",
        identity=identity,
    )
    entries: list[_TrackedBlob] = []
    for record in raw.split(b"\0"):
        if not record:
            continue
        try:
            metadata, encoded_path = record.split(b"\t", 1)
            mode_bytes, object_id_bytes, stage = metadata.split(b" ", 2)
            mode = mode_bytes.decode("ascii")
            object_id = object_id_bytes.decode("ascii")
            path = encoded_path.decode("utf-8", errors="strict")
        except (ValueError, UnicodeDecodeError) as exc:
            raise PagesBuildError("source index requires readable UTF-8 entries") from exc
        _safe_relative_path(path)
        if stage != b"0" or mode not in REGULAR_GIT_MODES:
            raise PagesBuildError("publication source index requires regular stage-zero blobs")
        entries.append(_TrackedBlob(path=path, mode=mode, object_id=object_id))
    return tuple(sorted(entries))


def _git_blob_contents(
    identity: _RepositoryIdentity,
    entries: tuple[_TrackedBlob, ...],
) -> dict[str, bytes]:
    object_ids = tuple(sorted({entry.object_id for entry in entries}))
    raw = _run_git_bytes(
        identity.worktree_root,
        "cat-file",
        "--batch",
        identity=identity,
        input_data=b"".join(
            object_id.encode("ascii") + b"\n"
            for object_id in object_ids
        ),
    )
    contents: dict[str, bytes] = {}
    offset = 0
    for requested_object_id in object_ids:
        line_end = raw.find(b"\n", offset)
        if line_end < 0:
            raise PagesBuildError("source blobs require complete Git batch headers")
        try:
            returned_id, object_type, encoded_size = raw[offset:line_end].split(b" ", 2)
            object_id = returned_id.decode("ascii")
            size = int(encoded_size.decode("ascii"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise PagesBuildError("source blobs require readable Git batch headers") from exc
        content_start = line_end + 1
        content_end = content_start + size
        if (
            object_id != requested_object_id
            or object_type != b"blob"
            or content_end >= len(raw)
            or raw[content_end : content_end + 1] != b"\n"
        ):
            raise PagesBuildError("source blobs require exact Git batch identities")
        content = raw[content_start:content_end]
        observed_object_id = sha1(
            f"blob {len(content)}\0".encode("ascii") + content
        ).hexdigest()
        if observed_object_id != object_id:
            raise PagesBuildError("source blob differs from its Git identity")
        contents[object_id] = content
        offset = content_end + 1
    if offset != len(raw):
        raise PagesBuildError("source blobs require one complete Git batch response")
    return contents


def _verify_worktree_blobs(
    identity: _RepositoryIdentity,
    tracked_blobs: tuple[_TrackedBlob, ...],
) -> None:
    committed = _git_blob_contents(identity, tracked_blobs)
    for entry in tracked_blobs:
        worktree_content, worktree_mode = _read_regular_bytes(
            identity.worktree_root,
            entry.path,
            label=f"tracked source {entry.path}",
        )
        expected_content = committed[entry.object_id]
        expected_executable = entry.mode == "100755"
        observed_executable = bool(worktree_mode & stat.S_IXUSR)
        if worktree_content != expected_content or (
            observed_executable != expected_executable
        ):
            raise PagesBuildError(
                f"tracked source {entry.path} differs from exact HEAD bytes or executable mode"
            )


def _verify_required_sources(proof: _VerifiedCleanSourceProof) -> None:
    entries = {entry.path: entry for entry in proof.tracked_blobs}
    missing = REQUIRED_COMMITTED_PATHS - set(entries)
    if missing:
        raise PagesBuildError(
            "publication source commit requires every report input and runtime source: "
            + ", ".join(sorted(missing))
        )
    bytecode_paths = sorted(
        path
        for path in entries
        if path.endswith(".pyc") or "__pycache__" in PurePosixPath(path).parts
    )
    if bytecode_paths:
        raise PagesBuildError(
            "publication runtime uses committed Python source without bytecode carriers: "
            + ", ".join(bytecode_paths)
        )


def _observe_clean_source(
    repository_root: Path,
    *,
    expected_revision: str | None = None,
    expected_identity: _RepositoryIdentity | None = None,
    expected_repository_url: str = DEFAULT_REPOSITORY_URL,
    expected_tree: str | None = None,
    expected_blobs: tuple[_TrackedBlob, ...] | None = None,
) -> tuple[_RepositoryIdentity, str, str, str, tuple[_TrackedBlob, ...]]:
    identity = _repository_identity(repository_root)
    if expected_identity is not None and identity != expected_identity:
        raise PagesBuildError(
            "verified-clean source proof belongs to a different Git worktree"
        )
    repository_url = _origin_repository_url(identity)
    normalized_expected_url = _repository_url(expected_repository_url)
    if repository_url != normalized_expected_url:
        raise PagesBuildError(
            "publication source origin differs from the claimed GitHub repository"
        )
    revision = _run_git(
        identity.worktree_root,
        "rev-parse",
        "HEAD",
        identity=identity,
    )
    if REVISION_PATTERN.fullmatch(revision) is None:
        raise PagesBuildError("source revision requires one full 40-character Git SHA")
    if expected_revision is not None and revision != expected_revision:
        raise PagesBuildError(
            "source HEAD differs from the verified publication revision"
        )
    tree, tracked_blobs = _tree_blobs(identity, revision)
    if expected_tree is not None and tree != expected_tree:
        raise PagesBuildError("source tree differs from the verified publication tree")
    if expected_blobs is not None and tracked_blobs != expected_blobs:
        raise PagesBuildError("source blob inventory differs from the verified publication tree")
    index_blobs = _index_blobs(identity)
    if index_blobs != tracked_blobs:
        raise PagesBuildError("publication source index differs from exact HEAD")
    _verify_worktree_blobs(identity, tracked_blobs)
    status = _run_git(
        identity.worktree_root,
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
        identity=identity,
    )
    if status:
        raise PagesBuildError(
            "publication source requires a clean worktree at the exact revision"
        )
    return identity, revision, repository_url, tree, tracked_blobs


def clean_source_revision(
    repository_root: Path,
    *,
    expected_revision: str | None = None,
    expected_repository_url: str = DEFAULT_REPOSITORY_URL,
) -> _VerifiedCleanSourceProof:
    """Prove one exact regular-file worktree at its requested HEAD and origin."""

    identity, revision, repository_url, tree, tracked_blobs = _observe_clean_source(
        repository_root,
        expected_revision=expected_revision,
        expected_repository_url=expected_repository_url,
    )
    proof = object.__new__(_VerifiedCleanSourceProof)
    object.__setattr__(proof, "revision", revision)
    object.__setattr__(proof, "tree", tree)
    object.__setattr__(proof, "repository_url", repository_url)
    object.__setattr__(proof, "repository_identity", identity)
    object.__setattr__(proof, "tracked_blobs", tracked_blobs)
    return proof


def _source_coordinate(
    repository_root: Path,
    source_proof: SourceProof,
) -> tuple[str, str]:
    if isinstance(source_proof, _VerifiedCleanSourceProof):
        _, revision, _, _, _ = _observe_clean_source(
            repository_root,
            expected_revision=source_proof.revision,
            expected_identity=source_proof.repository_identity,
            expected_repository_url=source_proof.repository_url,
            expected_tree=source_proof.tree,
            expected_blobs=source_proof.tracked_blobs,
        )
        return revision, "clean_exact_revision"
    if isinstance(source_proof, ValidationFixtureSourceProof):
        return source_proof.revision, "validation_fixture"
    raise PagesBuildError(
        "Pages build requires a structured verified-clean or validation-fixture source proof"
    )


def _write_regular_file(path: Path, content: bytes, mode: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    try:
        view = memoryview(content)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise PagesBuildError("materialized source requires complete blob writes")
            view = view[written:]
        os.fchmod(descriptor, 0o755 if mode == "100755" else 0o644)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _materialize_verified_source(
    proof: _VerifiedCleanSourceProof,
    *,
    parent: Path,
) -> Path:
    root = Path(tempfile.mkdtemp(prefix=".comparative-source-", dir=parent))
    try:
        committed = _git_blob_contents(
            proof.repository_identity,
            proof.tracked_blobs,
        )
        for entry in proof.tracked_blobs:
            content = committed[entry.object_id]
            path = root.joinpath(*_safe_relative_path(entry.path).parts)
            _write_regular_file(path, content, entry.mode)
            observed, observed_mode = _read_regular_bytes(
                root,
                entry.path,
                label=f"materialized source {entry.path}",
            )
            if observed != content or bool(observed_mode & stat.S_IXUSR) != (
                entry.mode == "100755"
            ):
                raise PagesBuildError(
                    f"materialized source {entry.path} differs from its HEAD blob"
                )
        return root
    except Exception:
        shutil.rmtree(root, ignore_errors=True)
        raise


@contextmanager
def _contract_resources_from(
    source_root: Path,
    *,
    runtime: _RuntimeBindings,
) -> Iterator[None]:
    resource_paths = {
        PurePosixPath(relative).name: relative
        for relative in CONTRACT_RESOURCE_PATHS
    }
    original_reader = runtime.contract_v1_module._resource_bytes

    def read_resource(name: str) -> bytes:
        relative = resource_paths.get(name)
        if relative is None:
            raise PagesBuildError("comparison contract requires a committed resource")
        content, _ = _read_regular_bytes(
            source_root,
            relative,
            label=f"comparison contract resource {relative}",
        )
        return content

    runtime.contract_v1_module._resource_bytes = read_resource
    try:
        yield
    finally:
        runtime.contract_v1_module._resource_bytes = original_reader


def _paths_overlap(first: Path, second: Path) -> bool:
    return (
        first == second
        or first.is_relative_to(second)
        or second.is_relative_to(first)
    )


def _canonical_origin(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise PagesBuildError(
            "canonical origin requires one credential-free HTTPS location"
        )
    path = "/" + parsed.path.strip("/") if parsed.path.strip("/") else ""
    return urlunsplit(("https", parsed.netloc, path + "/", "", ""))


def _repository_url(value: str) -> str:
    parsed = urlsplit(value.removesuffix(".git"))
    parts = [part for part in parsed.path.split("/") if part]
    if (
        parsed.scheme != "https"
        or parsed.netloc != "github.com"
        or len(parts) != 2
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise PagesBuildError(
            "repository URL requires one credential-free GitHub repository location"
        )
    return f"https://github.com/{parts[0]}/{parts[1]}"


def _cname(value: str | None, canonical_origin: str) -> str | None:
    if value is None:
        return None
    candidate = value.strip().rstrip(".")
    if HOST_PATTERN.fullmatch(candidate) is None:
        raise PagesBuildError("CNAME requires one DNS hostname without a URL path")
    origin = urlsplit(canonical_origin)
    if origin.hostname != candidate or origin.path != "/":
        raise PagesBuildError(
            "CNAME and canonical origin require the same root-level hostname"
        )
    return candidate


def _canonical_url(canonical_origin: str, relative: str = "") -> str:
    base = canonical_origin.rstrip("/")
    return base + ("/" + relative.lstrip("/") if relative else "/")


def _source_url(repository_url: str, revision: str, relative: str) -> str:
    encoded = "/".join(quote(part, safe="") for part in relative.split("/"))
    return f"{repository_url}/blob/{revision}/{encoded}"


def _site_css() -> str:
    return """:root {
  color-scheme: light;
  --ink: #14243a;
  --paper: #f5f1e8;
  --surface: #fffdf7;
  --accent: #2357d9;
  --line: #aebbc8;
  --muted: #526276;
}
* { box-sizing: border-box; }
html { background: var(--paper); color: var(--ink); font: 16px/1.55 ui-sans-serif, system-ui, sans-serif; }
body { margin: 0; }
a { color: var(--accent); text-underline-offset: .18em; }
a:focus-visible { outline: .2rem solid var(--accent); outline-offset: .2rem; }
.skip-link { position: absolute; inset: .75rem auto auto .75rem; transform: translateY(-180%); padding: .55rem .8rem; background: var(--surface); z-index: 2; }
.skip-link:focus { transform: none; }
.page-shell { width: min(72rem, calc(100% - 2rem)); margin: 0 auto; }
header { padding: clamp(3rem, 8vw, 7rem) 0 2rem; }
.kicker { color: var(--accent); font-weight: 750; letter-spacing: .09em; text-transform: uppercase; }
h1 { max-width: 13ch; margin: .35rem 0 1rem; font-size: clamp(2.6rem, 8vw, 6rem); line-height: .92; letter-spacing: -.045em; }
h2 { margin-top: 0; }
.lede { max-width: 45rem; font-size: clamp(1.1rem, 2.5vw, 1.35rem); }
.actions { display: flex; flex-wrap: wrap; gap: .65rem; margin: 1.5rem 0 0; }
.button { display: inline-block; border: 1px solid currentColor; border-radius: 99rem; padding: .6rem .9rem; font-weight: 700; text-decoration: none; }
main { display: grid; gap: 1rem; padding-bottom: 2rem; }
.panel { border: 1px solid var(--line); border-radius: 1rem; padding: clamp(1rem, 3vw, 1.5rem); background: var(--surface); }
.metrics { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: .75rem; }
.metric { min-width: 0; border-left: .2rem solid var(--accent); padding-left: .75rem; }
.metric strong { display: block; font-size: clamp(1.6rem, 4vw, 2.4rem); line-height: 1.1; }
.source-list { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .6rem 1.2rem; padding-left: 1.2rem; }
code { overflow-wrap: anywhere; }
.public-boundary { margin-top: 1rem; padding-top: 1rem; border-top: 1px solid var(--line); }
.public-boundary pre { margin: .55rem 0; white-space: pre-wrap; overflow-wrap: anywhere; font: .78rem/1.45 ui-monospace, SFMono-Regular, Consolas, monospace; }
.attribution { color: var(--muted); font-size: .9rem; }
footer { padding: 0 0 2rem; }
@media (max-width: 52rem) {
  .metrics, .source-list { grid-template-columns: 1fr; }
  .page-shell { width: min(100% - 1.25rem, 72rem); }
}
.evidence-figure { margin: 1.5rem 0; }
.figure-scroll, .table-scroll { overflow-x: auto; border: 1px solid var(--line); padding: .5rem; }
.figure-scroll:focus-visible, .table-scroll:focus-visible { outline: .2rem solid var(--accent); outline-offset: .2rem; }
.evidence-figure svg { display: block; width: 100%; min-width: 36rem; height: auto; color: #17345f; }
.evidence-figure figcaption { max-width: 66ch; margin-top: .75rem; color: var(--muted); }
table { width: 100%; min-width: 42rem; border-collapse: collapse; }
caption { text-align: left; padding: .75rem; font-weight: 700; }
th, td { text-align: left; padding: .75rem; border-bottom: 1px solid var(--line); vertical-align: top; }
thead th { background: #e7efff; color: #17345f; }
tbody th { width: 30%; }
@media print {
  .skip-link { display: none; }
  .figure-scroll, .table-scroll { overflow: visible; border: 0; padding: 0; }
  .evidence-figure svg, table { min-width: 0; }
  tr { break-inside: avoid; }
}

@media (forced-colors: active) {
  .panel, .button { border-color: CanvasText; }
}
"""


def _page_head(*, title: str, canonical_url: str) -> str:
    return f"""<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="author" content="Driftframe Studios, Limited Liability Company">
<meta name="description" content="Deterministic LIMS/ELN comparative evidence and its source-bound report.">
<link rel="canonical" href="{escape(canonical_url, quote=True)}">
<link rel="stylesheet" href="assets/site.css">
<title>{escape(title)}</title>"""


def _index_html(
    *,
    canonical_origin: str,
    repository_url: str,
    source_revision: str,
    reference_report: dict[str, Any],
    golden_report: dict[str, Any],
    runtime: _RuntimeBindings,
) -> str:
    counts = golden_report["summary"]["classification_counts"]
    total = golden_report["summary"]["leaf_paths_compared"]
    categories = (
        ("agreement", "Agreement", "Matching compared values."),
        ("explainable_variation", "Explainable variation", "Differences admitted by the comparison profile."),
        ("material_divergence", "Material divergence", "Differences requiring further disposition."),
    )
    scale_max = max(1, *(counts[key] for key, _, _ in categories))
    bars = []
    rows = []
    for position, (key, label, meaning) in enumerate(categories):
        count = counts[key]
        y = 45 + position * 65
        width = 330 * count / scale_max
        bars.append(
            f'<text x="20" y="{y + 21}">{escape(label)}</text>'
            f'<rect x="280" y="{y}" width="{width:.2f}" height="30" fill="#2855f3"/>'
            f'<text x="630" y="{y + 21}">{count}</text>'
        )
        rows.append(
            f'<tr data-label="{escape(label, quote=True)}">'
            f'<th scope="row">{escape(label)}</th>'
            f'<td data-label="Compared paths">{count}</td>'
            f'<td data-label="Reading">{escape(meaning)}</td></tr>'
        )
    source_items = "\n".join(
        "<li><a href=\""
        + escape(_source_url(repository_url, source_revision, path), quote=True)
        + "\"><code>"
        + escape(path)
        + "</code></a></li>"
        for path in SOURCE_LINK_PATHS
    )
    return f"""<!doctype html>
<html lang="en">
<head>
{_page_head(title="LIMS/ELN Comparative Evidence", canonical_url=_canonical_url(canonical_origin))}
</head>
<body>
<a class="skip-link" href="#content">Skip to evidence</a>
<header class="page-shell">
  <p class="kicker">LIMS/ELN Comparative Evidence</p>
  <h1>See what changed in a synthetic laboratory workflow.</h1>
  <p class="lede">Compare two producers of the same laboratory record, inspect agreement and meaningful differences, and carry the evidence into review. This public example uses simulated inputs for a laboratory information management system (LIMS) and electronic laboratory notebook (ELN).</p>
  <div class="actions">
    <a class="button" href="reports/golden-specimen/comparison.html">View the worked comparison</a>
    <a class="button" href="reports/golden-specimen/comparison.json">Inspect report JSON</a>
  </div>
</header>
<main id="content" class="page-shell">
  <section class="panel" aria-labelledby="first-reading">
    <h2 id="first-reading">Start with one difference</h2>
    <ol>
      <li>View the Golden Specimen report and choose a field classified as material divergence.</li>
      <li>Compare its two values and the profile rule that gives the difference meaning.</li>
      <li>Use the report JSON to inspect the same result and its source identities.</li>
    </ol>
    <p>The report compares a durable-workbench snapshot with a selected-future scenario through the shared projection contract. Both producers in this example are simulated. The reading task works with the published artifacts; source-based reproduction is available to authorized repository collaborators.</p>
  </section>
  <section class="panel" aria-labelledby="report-summary">
    <h2 id="report-summary">What this run establishes</h2>
    <p>The same two fixtures, committed profile, constellation lock and comparator produce one stable report digest across {total} shared projection leaves. Each leaf is one compared field path.</p>
    <figure class="evidence-figure">
      <div class="figure-scroll" role="region" tabindex="0" aria-label="Comparison count chart">
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 700 275" role="img" aria-labelledby="counts-title counts-desc">
          <title id="counts-title">Classification counts for {total} compared paths</title>
          <desc id="counts-desc">All bars start at zero and use one count scale. The following table provides every count and its reading. Counts describe this report's fields, rather than a population outcome.</desc>
          <g fill="currentColor" font-family="sans-serif" font-size="18">
            {''.join(bars)}
            <text x="280" y="250">0</text>
            <text x="610" y="250" text-anchor="end">{scale_max} paths</text>
          </g>
          <path d="M280 35V220H610" fill="none" stroke="currentColor" stroke-width="1"/>
        </svg>
      </div>
      <figcaption>Counts share a zero baseline and one scale. Color identifies the common measure; category labels carry the distinction. The chart describes field classifications in this example, with scientific interpretation retained by the report and its reviewer.</figcaption>
    </figure>
    <div class="table-scroll" role="region" tabindex="0" aria-labelledby="classification-caption">
      <table data-label="Golden Specimen classification counts">
        <caption id="classification-caption">Every classification in the {total}-path comparison</caption>
        <thead><tr><th scope="col">Classification</th><th scope="col">Compared paths</th><th scope="col">Reading</th></tr></thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
    </div>
  </section>
  <section class="panel" aria-labelledby="reading-boundary">
    <h2 id="reading-boundary">Choose the next useful question</h2>
    <p>Use the <a href="reports/reference/comparison.html">contract-shape reference</a> and its <a href="reports/reference/comparison.json">machine-readable report</a> to inspect classifier and visibility behavior separately. Its report digest is <code>{escape(reference_report['report_digest'])}</code>.</p>
    <p>The <a href="https://cometspectrum.org/">Program guide</a> explains the five repository roles. The <a href="https://fieldformlab.org/">Governance guide</a> explains evidence records and review boundaries.</p>
    <p>Environment-observed results enter through their own provenance and acceptance route. Administrative study tools, configured database evidence and interactive workbench delivery retain their separately reviewed source and release scopes.</p>
    <p><a href="data-use.html">Read the data-use and crawler-intent note</a></p>
  </section>
  <section class="panel" aria-labelledby="source-coordinate">
    <h2 id="source-coordinate">Reproduce from the selected source</h2>
    <p>Authorized repository collaborators can use the source guide and fixtures below. Every source link resolves to revision <code>{escape(source_revision)}</code>. The public <a href="projection-manifest.json">projection manifest</a> records byte counts and SHA-256 identities for this complete candidate.</p>
    <ul class="source-list">{source_items}</ul>
    <p><a href="{escape(repository_url, quote=True)}">Repository overview (collaborator access)</a></p>
  </section>
</main>
<footer class="page-shell">
{runtime.render_public_boundary()}
</footer>
</body>
</html>
"""


def _data_use_html(
    *,
    canonical_origin: str,
    runtime: _RuntimeBindings,
) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
{_page_head(title="Data use · LIMS/ELN Comparative Evidence", canonical_url=_canonical_url(canonical_origin, 'data-use.html'))}
</head>
<body>
<a class="skip-link" href="#content">Skip to data-use note</a>
<header class="page-shell">
  <p class="kicker">Data use and crawler intent</p>
  <h1>Readable source, explicit benchmark markers.</h1>
  <p class="lede">The repository and its published comparison material support human-directed reading, research, search, citation, and agent-assisted inspection.</p>
</header>
<main id="content" class="page-shell">
  <section class="panel">
    <h2>How the signals fit together</h2>
    <p>The Apache License 2.0 governs use of the software. The exact MAPS Evaluations and BIG-bench markers ask dataset curators and automated collection systems to keep this material outside training and fine-tuning corpora. The markers express benchmark-integrity intent for the published material.</p>
    <p>This publication carries a synthetic comparison report, source coordinates, and integrity metadata. Each reader can inspect the material directly and cite the stable source revision.</p>
    <p><a href="./">Return to the report index</a></p>
  </section>
</main>
<footer class="page-shell">
{runtime.render_public_boundary()}
</footer>
</body>
</html>
"""


def _sha256(content: bytes) -> str:
    return sha256(content).hexdigest()


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def _all_projection_files(root: Path) -> list[Path]:
    try:
        root_status = os.lstat(root)
    except OSError as exc:
        raise PagesBuildError("projection requires one readable directory") from exc
    if stat.S_ISLNK(root_status.st_mode) or not stat.S_ISDIR(root_status.st_mode):
        raise PagesBuildError("projection requires one regular directory")
    files: list[Path] = []
    pending = [root]
    while pending:
        directory = pending.pop()
        try:
            with os.scandir(directory) as iterator:
                entries = sorted(iterator, key=lambda item: item.name)
        except OSError as exc:
            raise PagesBuildError("projection requires readable contained entries") from exc
        for entry in entries:
            try:
                entry_status = entry.stat(follow_symlinks=False)
            except OSError as exc:
                raise PagesBuildError("projection requires stable contained entries") from exc
            if entry.is_symlink():
                raise PagesBuildError("projection requires regular files and directories")
            path = Path(entry.path)
            if stat.S_ISDIR(entry_status.st_mode):
                pending.append(path)
            elif stat.S_ISREG(entry_status.st_mode):
                files.append(path)
            else:
                raise PagesBuildError("projection requires regular files and directories")
    return sorted(files, key=lambda path: path.relative_to(root).as_posix())


def _projection_files(root: Path) -> list[Path]:
    return [
        path
        for path in _all_projection_files(root)
        if path.relative_to(root).as_posix() != MANIFEST_PATH
    ]


def _manifest(
    root: Path,
    *,
    canonical_origin: str,
    repository_url: str,
    source_revision: str,
    source_standing: str,
    cname: str | None,
    report_digest: str,
    golden_specimen_report_digest: str,
) -> dict[str, Any]:
    report_sources = set(REPORT_PATHS)
    files = []
    for path in _projection_files(root):
        relative = path.relative_to(root).as_posix()
        content, _ = _read_regular_bytes(
            root,
            relative,
            label=f"projection file {relative}",
        )
        files.append(
            {
                "path": relative,
                "bytes": len(content),
                "sha256": _sha256(content),
                "sourceRevision": source_revision,
                "byteRelation": (
                    "exact_comparator_runtime_output"
                    if relative in report_sources
                    else "deterministic_pages_builder_output"
                ),
            }
        )
    return {
        "manifestVersion": MANIFEST_VERSION,
        "projectionOwner": PROJECTION_OWNER,
        "sourceStanding": source_standing,
        "sourceRevision": source_revision,
        "repositoryUrl": repository_url,
        "canonicalOrigin": canonical_origin,
        "cname": cname,
        "reportDigest": report_digest,
        "goldenSpecimenReportDigest": golden_specimen_report_digest,
        "fileScope": MANIFEST_FILE_SCOPE,
        "files": files,
    }


def _resolve_relative_link(current: str, link: str) -> str | None:
    parsed = urlsplit(link)
    if parsed.scheme or parsed.netloc or link.startswith("#"):
        return None
    if parsed.path.startswith("/"):
        raise PagesBuildError(
            f"{current} uses a root-relative link that loses project-path portability"
        )
    if not parsed.path:
        return None
    current_parent = posixpath.dirname(current)
    resolved = posixpath.normpath(posixpath.join(current_parent, parsed.path))
    if resolved == ".":
        resolved = "index.html"
    elif parsed.path.endswith("/") or resolved.endswith("/"):
        resolved = posixpath.join(resolved, "index.html")
    if resolved.startswith("../") or resolved == "..":
        raise PagesBuildError(f"{current} links outside the projection: {link}")
    return PurePosixPath(resolved).as_posix()


def validate_projection(
    root: Path,
    *,
    runtime: _RuntimeBindings | None = None,
) -> dict[str, Any]:
    """Validate manifest identity, portable links, and readable HTML structure."""

    if runtime is None:
        runtime = _load_runtime(ROOT)

    all_files = _all_projection_files(root)
    all_paths = {
        path.relative_to(root).as_posix(): path
        for path in all_files
    }
    if MANIFEST_PATH not in all_paths:
        raise PagesBuildError("projection requires one regular manifest document")
    manifest_bytes, _ = _read_regular_bytes(
        root,
        MANIFEST_PATH,
        label="projection manifest",
    )
    manifest = runtime.strict_json_loads(manifest_bytes)
    if not isinstance(manifest, dict):
        raise PagesBuildError("projection manifest requires one JSON object")
    if manifest.get("manifestVersion") != MANIFEST_VERSION:
        raise PagesBuildError(
            f"projection manifest requires version {MANIFEST_VERSION}"
        )
    if manifest.get("projectionOwner") != PROJECTION_OWNER:
        raise PagesBuildError(
            "projection manifest requires the released builder owner"
        )
    if manifest.get("fileScope") != MANIFEST_FILE_SCOPE:
        raise PagesBuildError(
            "projection manifest requires the released file-scope statement"
        )
    revision = manifest.get("sourceRevision")
    if not isinstance(revision, str) or REVISION_PATTERN.fullmatch(revision) is None:
        raise PagesBuildError("projection manifest requires one full source revision")
    if manifest.get("sourceStanding") not in RELEASED_SOURCE_STANDINGS:
        raise PagesBuildError("projection manifest requires a declared source standing")
    canonical_value = manifest.get("canonicalOrigin")
    if not isinstance(canonical_value, str):
        raise PagesBuildError("projection manifest requires one canonical origin")
    canonical_origin = _canonical_origin(canonical_value)
    if canonical_origin != canonical_value:
        raise PagesBuildError(
            "projection manifest canonical origin requires its normalized form"
        )
    repository_value = manifest.get("repositoryUrl")
    if not isinstance(repository_value, str) or (
        _repository_url(repository_value) != repository_value
    ):
        raise PagesBuildError(
            "projection manifest requires the normalized repository URL"
        )
    declared_entries = manifest.get("files")
    if not isinstance(declared_entries, list):
        raise PagesBuildError("projection manifest requires a file inventory")
    declared: dict[str, dict[str, Any]] = {}
    for entry in declared_entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise PagesBuildError("projection manifest file entries require paths")
        relative = entry["path"]
        if (
            relative == MANIFEST_PATH
            or relative in declared
            or PurePosixPath(relative).is_absolute()
            or ".." in PurePosixPath(relative).parts
        ):
            raise PagesBuildError(
                "projection manifest paths require unique contained files"
            )
        declared[relative] = entry
    observed_paths = set(all_paths) - {MANIFEST_PATH}
    if set(declared) != observed_paths:
        raise PagesBuildError(
            "projection manifest inventory differs from the generated files"
        )
    for relative, entry in declared.items():
        content, _ = _read_regular_bytes(
            root,
            relative,
            label=f"projection file {relative}",
        )
        if entry.get("bytes") != len(content) or entry.get("sha256") != _sha256(
            content
        ):
            raise PagesBuildError(
                f"projection file {relative} differs from its declared identity"
            )
        if entry.get("sourceRevision") != revision:
            raise PagesBuildError(
                f"projection file {relative} requires the manifest source revision"
            )

    nojekyll, _ = _read_regular_bytes(root, ".nojekyll", label=".nojekyll")
    if nojekyll != b"":
        raise PagesBuildError(".nojekyll requires an empty marker file")
    cname_value = manifest.get("cname")
    if cname_value is not None and not isinstance(cname_value, str):
        raise PagesBuildError("projection manifest CNAME requires one hostname")
    cname = _cname(cname_value, canonical_origin)
    if cname is None:
        if "CNAME" in observed_paths:
            raise PagesBuildError("CNAME bytes require a declared hostname")
    else:
        cname_bytes, _ = _read_regular_bytes(root, "CNAME", label="CNAME")
        if cname_bytes != f"{cname}\n".encode("utf-8"):
            raise PagesBuildError("CNAME bytes require the declared hostname")

    for relative in sorted(path for path in observed_paths if path.endswith(".html")):
        document_bytes, _ = _read_regular_bytes(
            root,
            relative,
            label=f"projection HTML {relative}",
        )
        document = document_bytes.decode("utf-8")
        if not document.startswith("<!doctype html>"):
            raise PagesBuildError(f"{relative} requires one HTML document")
        if '<html lang="en">' not in document or 'name="viewport"' not in document:
            raise PagesBuildError(
                f"{relative} requires language and viewport orientation"
            )
        maps_position = document.find(runtime.MAPS_CANARY)
        big_bench_position = document.find(runtime.BIG_BENCH_CANARY)
        if maps_position < 0 or big_bench_position <= maps_position:
            raise PagesBuildError(
                f"{relative} requires the approved MAPS then BIG-bench marker order"
            )
        if runtime.PUBLIC_ATTRIBUTION not in document:
            raise PagesBuildError(
                f"{relative} requires source-local public attribution"
            )
        collector = _LinkCollector()
        collector.feed(document)
        expected_canonical = _canonical_url(
            canonical_origin,
            "" if relative == "index.html" else relative,
        )
        if collector.canonicals != [expected_canonical]:
            raise PagesBuildError(
                f"{relative} requires the manifest-owned canonical URL"
            )
        for link in collector.links:
            target = _resolve_relative_link(relative, link)
            if target is not None and target not in observed_paths | {MANIFEST_PATH}:
                raise PagesBuildError(
                    f"{relative} has an unresolved projection link: {link}"
                )

    css_bytes, _ = _read_regular_bytes(
        root,
        "assets/site.css",
        label="projection stylesheet",
    )
    css = css_bytes.decode("utf-8")
    if (
        "@media (max-width: 52rem)" not in css
        or ".metrics, .source-list { grid-template-columns: 1fr; }" not in css
        or ".page-shell { width: min(" not in css
    ):
        raise PagesBuildError(
            "projection stylesheet requires narrow and bounded desktop structure"
        )
    index_bytes, _ = _read_regular_bytes(
        root,
        "index.html",
        label="projection index",
    )
    index = index_bytes.decode("utf-8")
    if 'class="skip-link"' not in index or '<main id="content"' not in index:
        raise PagesBuildError("projection index requires keyboard and landmark access")
    source_prefix = f"{manifest['repositoryUrl']}/blob/{revision}/"
    for source_path in SOURCE_LINK_PATHS:
        if _source_url(manifest["repositoryUrl"], revision, source_path) not in index:
            raise PagesBuildError(
                f"projection index requires the exact source link for {source_path}"
            )
    if index.count(source_prefix) < len(SOURCE_LINK_PATHS):
        raise PagesBuildError("projection source links require the full revision")

    report_bundles = (
        (
            "reports/reference",
            REFERENCE_REPORT_PATHS,
            "reportDigest",
            "reference comparison",
        ),
        (
            "reports/golden-specimen",
            GOLDEN_REPORT_PATHS,
            "goldenSpecimenReportDigest",
            "Golden Specimen comparison",
        ),
    )
    for report_directory, report_paths, manifest_field, label in report_bundles:
        report_inventory = runtime.report_artifact_inventory(
            root / report_directory
        )
        report_json_path = f"{report_directory}/comparison.json"
        report_bytes, _ = _read_regular_bytes(
            root,
            report_json_path,
            label=f"{label} report JSON",
        )
        report_document = runtime.strict_json_loads(
            report_bytes,
            budget=runtime.contract_v1_module.REPORT_BUDGET,
        )
        if not isinstance(report_document, dict) or (
            manifest.get(manifest_field) != report_document.get("report_digest")
        ):
            raise PagesBuildError(
                f"projection manifest {label} digest requires the validated runtime report"
            )
        for report_path in report_paths:
            entry = declared[report_path]
            name = PurePosixPath(report_path).name
            if entry.get("byteRelation") != "exact_comparator_runtime_output" or (
                "sha256:" + entry["sha256"] != report_inventory[name]
            ):
                raise PagesBuildError(
                    f"{report_path} requires exact comparator runtime bytes"
                )
    return manifest


def projection_byte_inventory(root: Path) -> dict[str, str]:
    inventory: dict[str, str] = {}
    for path in _all_projection_files(root):
        relative = path.relative_to(root).as_posix()
        content, _ = _read_regular_bytes(
            root,
            relative,
            label=f"projection inventory file {relative}",
        )
        inventory[relative] = _sha256(content)
    return inventory


def verify_reproducible_projections(first: Path, replay: Path) -> dict[str, str]:
    first_manifest = validate_projection(first)
    replay_manifest = validate_projection(replay)
    if first_manifest != replay_manifest:
        raise PagesBuildError("isolated Pages builds require one manifest")
    first_inventory = projection_byte_inventory(first)
    replay_inventory = projection_byte_inventory(replay)
    if first_inventory != replay_inventory:
        changed = sorted(set(first_inventory) | set(replay_inventory))
        raise PagesBuildError(
            "isolated Pages builds require byte-identical files: "
            + ", ".join(changed)
        )
    return first_inventory


def _render_projection(
    source_root: Path,
    output_root: Path,
    *,
    source_revision: str,
    source_standing: str,
    canonical_origin: str,
    repository_url: str,
    cname: str | None,
    runtime: _RuntimeBindings,
) -> dict[str, Any]:
    """Render and validate one projection with an already selected runtime."""

    with _contract_resources_from(source_root, runtime=runtime):
        reference_report = runtime.compare_synthetic_contract(
            runtime.ObservationEnvelope.from_dict(
                _load_object(
                    source_root,
                    "fixtures/pairs/simulation-observation.json",
                    runtime=runtime,
                )
            ),
            runtime.ObservationEnvelope.from_dict(
                _load_object(
                    source_root,
                    "fixtures/contracts/planned-observation.json",
                    runtime=runtime,
                )
            ),
            _load_object(
                source_root,
                "specification/comparison-profile.json",
                runtime=runtime,
            ),
        )
        golden_report = runtime.compare_golden_specimen(
            _load_object(
                source_root,
                "fixtures/pairs/enterprise-postgresql-observation.json",
                runtime=runtime,
            ),
            _load_object(
                source_root,
                "fixtures/pairs/simulation-golden-specimen-observation.json",
                runtime=runtime,
            ),
            _load_object(
                source_root,
                "specification/golden-specimen-verification-profile.json",
                runtime=runtime,
            ),
            _load_object(
                source_root,
                "constellation.lock.json",
                runtime=runtime,
            ),
        )
    report_root = output_root / "reports/reference"
    runtime.write_reports(
        reference_report,
        report_root,
        canonical_url=_canonical_url(
            canonical_origin,
            "reports/reference/comparison.html",
        ),
    )
    runtime.report_artifact_inventory(report_root)
    golden_report_root = output_root / "reports/golden-specimen"
    runtime.write_reports(
        golden_report,
        golden_report_root,
        canonical_url=_canonical_url(
            canonical_origin,
            "reports/golden-specimen/comparison.html",
        ),
    )
    runtime.report_artifact_inventory(golden_report_root)
    _write_text(output_root / "assets/site.css", _site_css())
    _write_text(
        output_root / "index.html",
        _index_html(
            canonical_origin=canonical_origin,
            repository_url=repository_url,
            source_revision=source_revision,
            reference_report=reference_report,
            golden_report=golden_report,
            runtime=runtime,
        ),
    )
    _write_text(
        output_root / "data-use.html",
        _data_use_html(
            canonical_origin=canonical_origin,
            runtime=runtime,
        ),
    )
    (output_root / ".nojekyll").write_bytes(b"")
    if cname is not None:
        _write_text(output_root / "CNAME", f"{cname}\n")
    manifest = _manifest(
        output_root,
        canonical_origin=canonical_origin,
        repository_url=repository_url,
        source_revision=source_revision,
        source_standing=source_standing,
        cname=cname,
        report_digest=reference_report["report_digest"],
        golden_specimen_report_digest=golden_report["report_digest"],
    )
    _write_text(
        output_root / MANIFEST_PATH,
        json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n",
    )
    validate_projection(output_root, runtime=runtime)
    return manifest


def _worker_environment() -> dict[str, str]:
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("GIT_") and not key.startswith("PYTHON")
    }
    environment.update(
        {
            "LANG": "C",
            "LC_ALL": "C",
            "PYTHONHASHSEED": "0",
        }
    )
    return environment


def _run_materialized_worker(
    source_root: Path,
    output_root: Path,
    *,
    source_revision: str,
    canonical_origin: str,
    repository_url: str,
    cname: str | None,
) -> dict[str, Any]:
    command = [
        sys.executable,
        "-I",
        "-S",
        "-B",
        str(source_root / "tools/build_pages.py"),
        "--_materialized-worker",
        "--output",
        str(output_root),
        "--source-revision",
        source_revision,
        "--canonical-origin",
        canonical_origin,
        "--repository-url",
        repository_url,
    ]
    if cname is not None:
        command.extend(("--cname", cname))
    result = subprocess.run(
        command,
        cwd=source_root,
        check=False,
        capture_output=True,
        text=True,
        env=_worker_environment(),
    )
    if result.returncode != 0:
        raise PagesBuildError(
            "materialized Pages runtime requires a successful isolated render"
        )
    try:
        receipt = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise PagesBuildError(
            "materialized Pages runtime requires one structured completion receipt"
        ) from exc
    if receipt != {
        "source_revision": source_revision,
        "status": "passed",
    }:
        raise PagesBuildError(
            "materialized Pages runtime returned a different source coordinate"
        )
    manifest_bytes, _ = _read_regular_bytes(
        output_root,
        MANIFEST_PATH,
        label="materialized projection manifest",
    )
    try:
        manifest = json.loads(manifest_bytes)
    except json.JSONDecodeError as exc:
        raise PagesBuildError(
            "materialized projection requires one readable manifest"
        ) from exc
    if not isinstance(manifest, dict) or (
        manifest.get("sourceRevision") != source_revision
        or manifest.get("sourceStanding") != "clean_exact_revision"
        or manifest.get("repositoryUrl") != repository_url
    ):
        raise PagesBuildError(
            "materialized projection manifest requires the verified source coordinate"
        )
    return manifest


def build_projection(
    repository_root: Path,
    output: Path,
    *,
    source_proof: SourceProof,
    canonical_origin: str = DEFAULT_CANONICAL_ORIGIN,
    repository_url: str = DEFAULT_REPOSITORY_URL,
    cname: str | None = None,
) -> dict[str, Any]:
    """Build one deterministic projection from an already selected source revision."""

    try:
        repository_status = os.lstat(repository_root)
        if stat.S_ISLNK(repository_status.st_mode) or not stat.S_ISDIR(
            repository_status.st_mode
        ):
            raise PagesBuildError("Pages source requires one regular directory")
        repository_root = repository_root.resolve(strict=True)
    except OSError as exc:
        raise PagesBuildError("Pages source requires one readable directory") from exc
    requested_output = output.absolute()
    if os.path.lexists(requested_output):
        raise PagesBuildError(
            "Pages output requires a fresh destination so retained files stay visible"
        )
    if os.path.lexists(requested_output.parent) and stat.S_ISLNK(
        os.lstat(requested_output.parent).st_mode
    ):
        raise PagesBuildError(
            "Pages output requires a direct directory path without symlink routing"
        )
    output = requested_output.resolve(strict=False)
    canonical_origin = _canonical_origin(canonical_origin)
    repository_url = _repository_url(repository_url)
    cname = _cname(cname, canonical_origin)
    if not isinstance(
        source_proof,
        (_VerifiedCleanSourceProof, ValidationFixtureSourceProof),
    ):
        raise PagesBuildError(
            "Pages build requires a structured verified-clean or validation-fixture source proof"
        )
    if source_proof.repository_url != repository_url:
        raise PagesBuildError(
            "Pages source and GitHub links require the same repository identity"
        )
    protected_roots = [repository_root]
    if isinstance(source_proof, _VerifiedCleanSourceProof):
        protected_roots.extend(
            (
                source_proof.repository_identity.git_directory,
                source_proof.repository_identity.common_directory,
            )
        )
    if any(_paths_overlap(protected, output) for protected in protected_roots):
        raise PagesBuildError(
            "Pages source, Git administration, and output require separate directory trees"
        )
    if os.path.lexists(output):
        raise PagesBuildError(
            "Pages output requires a fresh destination so retained files stay visible"
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{output.name}-build-", dir=output.parent)
    )
    materialized_source: Path | None = None
    materialized_inventory: dict[str, str] | None = None
    try:
        source_revision, source_standing = _source_coordinate(
            repository_root,
            source_proof,
        )
        if isinstance(source_proof, _VerifiedCleanSourceProof):
            _verify_required_sources(source_proof)
            materialized_source = _materialize_verified_source(
                source_proof,
                parent=output.parent,
            )
            manifest = _run_materialized_worker(
                materialized_source,
                temporary,
                source_revision=source_revision,
                canonical_origin=canonical_origin,
                repository_url=repository_url,
                cname=cname,
            )
            materialized_inventory = projection_byte_inventory(temporary)
        else:
            runtime = _load_runtime(repository_root)
            manifest = _render_projection(
                repository_root,
                temporary,
                source_revision=source_revision,
                source_standing=source_standing,
                canonical_origin=canonical_origin,
                repository_url=repository_url,
                cname=cname,
                runtime=runtime,
            )
        if isinstance(source_proof, _VerifiedCleanSourceProof):
            _source_coordinate(repository_root, source_proof)
            if projection_byte_inventory(temporary) != materialized_inventory:
                raise PagesBuildError(
                    "materialized projection changed before final acceptance"
                )
        os.replace(temporary, output)
        return manifest
    finally:
        if temporary.exists():
            shutil.rmtree(temporary, ignore_errors=True)
        if materialized_source is not None:
            shutil.rmtree(materialized_source, ignore_errors=True)


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(
        description=(
            "Build a deterministic, source-bound Comparative Evidence Pages candidate"
        )
    )
    command.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Fresh destination outside the source worktree",
    )
    command.add_argument("--source-revision")
    command.add_argument(
        "--canonical-origin",
        default=DEFAULT_CANONICAL_ORIGIN,
    )
    command.add_argument(
        "--repository-url",
        default=DEFAULT_REPOSITORY_URL,
    )
    command.add_argument("--cname")
    command.add_argument(
        "--_materialized-worker",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    return command


def _materialized_worker_main(args: argparse.Namespace) -> int:
    if not isinstance(args.source_revision, str) or (
        REVISION_PATTERN.fullmatch(args.source_revision) is None
    ):
        raise PagesBuildError(
            "materialized runtime requires one full source revision"
        )
    output = (
        args.output if args.output.is_absolute() else Path.cwd() / args.output
    ).resolve(strict=True)
    try:
        output_status = os.lstat(output)
    except OSError as exc:
        raise PagesBuildError(
            "materialized runtime requires its prepared output directory"
        ) from exc
    if stat.S_ISLNK(output_status.st_mode) or not stat.S_ISDIR(output_status.st_mode):
        raise PagesBuildError(
            "materialized runtime requires one regular output directory"
        )
    if any(output.iterdir()):
        raise PagesBuildError(
            "materialized runtime requires one empty output directory"
        )
    if _paths_overlap(ROOT, output):
        raise PagesBuildError(
            "materialized source and output require separate directory trees"
        )
    canonical_origin = _canonical_origin(args.canonical_origin)
    repository_url = _repository_url(args.repository_url)
    cname = _cname(args.cname, canonical_origin)
    runtime = _load_runtime(ROOT, require_fresh=True)
    _render_projection(
        ROOT,
        output,
        source_revision=args.source_revision,
        source_standing="clean_exact_revision",
        canonical_origin=canonical_origin,
        repository_url=repository_url,
        cname=cname,
        runtime=runtime,
    )
    print(
        json.dumps(
            {
                "source_revision": args.source_revision,
                "status": "passed",
            },
            sort_keys=True,
        )
    )
    return 0


def main(arguments: list[str] | None = None) -> int:
    if not (
        sys.flags.isolated
        and sys.flags.no_site
        and sys.flags.dont_write_bytecode
    ):
        raise PagesBuildError(
            "Pages command requires Python isolated mode: python -I -S -B"
        )
    args = parser().parse_args(arguments)
    if args._materialized_worker:
        return _materialized_worker_main(args)
    source_proof = clean_source_revision(
        ROOT,
        expected_revision=args.source_revision,
        expected_repository_url=args.repository_url,
    )
    output = (
        args.output
        if args.output.is_absolute()
        else Path.cwd() / args.output
    ).resolve(strict=False)
    manifest = build_projection(
        ROOT,
        output,
        source_proof=source_proof,
        canonical_origin=args.canonical_origin,
        repository_url=args.repository_url,
        cname=args.cname,
    )
    manifest_bytes = (output / MANIFEST_PATH).read_bytes()
    print(
        json.dumps(
            {
                "status": "passed",
                "source_revision": source_proof.revision,
                "files": len(manifest["files"]),
                "manifest_sha256": _sha256(manifest_bytes),
                "output": str(output),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
