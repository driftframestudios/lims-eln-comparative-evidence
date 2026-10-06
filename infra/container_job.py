#!/usr/bin/env python3
"""Prepare a finite job from declared files and an offline dependency closure.

Canonical owner: Program's infra/container_job.py. Receiving copies retain the
same bytes; repository profiles own their distinct source and behavior inputs.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
from container_patch import admit_patch_files, dockerfile_patch
import re
import shutil
import signal
import stat
import unicodedata

MAX_FILES = 512
MAX_FILE_BYTES = 32 * 1024 * 1024
MAX_TOTAL_BYTES = 256 * 1024 * 1024
BASE_IMAGE = "python:3.12.15-slim-bookworm@sha256:54c85f3c47607a77f32adec749d3c81d1348bf25833671f512b26a9b6d778cb3"


class ContextError(ValueError):
    """A declared input requires a bounded, owned representation."""


@dataclass(frozen=True)
class Profile:
    name: str
    files: tuple[str, ...]
    dependencies: str


def relative_path(value: object) -> str:
    if not isinstance(value, str) or not value or len(value) > 256:
        raise ContextError("input-path")
    if "\\" in value or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ContextError("input-path")
    parts = value.split("/")
    if any(p in ("", ".", "..", ".git") for p in parts) or PurePosixPath(value).is_absolute():
        raise ContextError("input-path")
    return value


def admitted_profile(value: object) -> Profile:
    if not isinstance(value, dict) or set(value) != {"version", "name", "files", "dependencies"}:
        raise ContextError("profile-fields")
    if value["version"] != "1.0.0" or not isinstance(value["name"], str) or re.fullmatch(r"[a-z][a-z0-9-]{0,63}", value["name"]) is None:
        raise ContextError("profile-identity")
    paths = value["files"]
    if not isinstance(paths, list) or not 1 <= len(paths) <= MAX_FILES:
        raise ContextError("profile-file-count")
    files = tuple(relative_path(p) for p in paths)
    if len({unicodedata.normalize("NFC", p).casefold() for p in files}) != len(files):
        raise ContextError("profile-path-alias")
    if not {"infra/container_entry.py", "infra/container_runtime.py", "LICENSE", "AUTHORS"}.issubset(files):
        raise ContextError("profile-required-inputs")
    if value["dependencies"] not in ("stdlib", "wheels"):
        raise ContextError("profile-dependencies")
    return Profile(value["name"], files, value["dependencies"])


def regular_bytes(root: Path, relative: str) -> bytes:
    """Bounded descriptor read; each source belongs to an operator-owned tree."""
    parts = relative_path(relative).split("/")
    parent = root
    for part in parts[:-1]:
        parent = parent / part
        if not stat.S_ISDIR(parent.lstat().st_mode):
            raise ContextError("input-directory")
    descriptor = os.open(parent / parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > MAX_FILE_BYTES:
            raise ContextError("input-regular-file")
        content = stream.read(MAX_FILE_BYTES + 1)
        after = os.fstat(stream.fileno())
        if len(content) != before.st_size or len(content) > MAX_FILE_BYTES or (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise ContextError("input-changed-during-read")
        return content


def strict_document(content: bytes) -> object:
    def fields(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ContextError("duplicate-field")
            result[key] = value
        return result
    if len(content) > 256 * 1024:
        raise ContextError("manifest-size")
    try:
        return json.loads(content, object_pairs_hook=fields)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as error:
        raise ContextError("manifest-json") from error


def requirements_admitted(content: bytes) -> bool:
    """O(bytes) admission keeps each pinned package and its hashes together."""
    try:
        text = content.decode("ascii")
    except UnicodeDecodeError:
        return False
    fragments = []
    count = 0
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            if fragments:
                return False
            continue
        continued = line.endswith("\\")
        fragment = line[:-1].rstrip() if continued else line
        if not fragment:
            return False
        fragments.append(fragment)
        if continued:
            continue
        tokens = " ".join(fragments).split()
        fragments.clear()
        if (
            len(tokens) < 2
            or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*==[A-Za-z0-9_.+!-]+", tokens[0]) is None
            or any(re.fullmatch(r"--hash=sha256:[0-9a-f]{64}", token) is None for token in tokens[1:])
        ):
            return False
        count += 1
    if fragments or count == 0:
        return False

    return True


def admitted_dependencies(root: Path) -> tuple[bytes, tuple[tuple[str, str], ...]]:
    document = strict_document(regular_bytes(root, "wheel-manifest.json"))
    if not isinstance(document, dict) or set(document) != {"version", "requirementsSha256", "wheels"} or document["version"] != "1.0.0":
        raise ContextError("wheel-manifest")
    requirements = regular_bytes(root, "requirements.lock")
    if sha256(requirements).hexdigest() != document["requirementsSha256"] or not requirements_admitted(requirements):
        raise ContextError("locked-requirements")
    wheels = document["wheels"]
    if not isinstance(wheels, list) or not 1 <= len(wheels) <= 64:
        raise ContextError("wheel-count")
    records = []
    names = set()
    for item in wheels:
        if not isinstance(item, dict) or set(item) != {"file", "sha256"}:
            raise ContextError("wheel-record")
        name, digest = item["file"], item["sha256"]
        if not isinstance(name, str) or re.fullmatch(r"[A-Za-z0-9_.+-]+[.]whl", name) is None or name.casefold() in names:
            raise ContextError("wheel-name")
        if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise ContextError("wheel-digest")
        names.add(name.casefold())
        records.append((name, digest))
    return requirements, tuple(records)


def dockerfile(architecture: str) -> bytes:
    patch_layer = dockerfile_patch(architecture)
    return (f"FROM --platform=linux/{architecture} {BASE_IMAGE}\n"
            "ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1\n"
            "WORKDIR /opt/job/source\n" + patch_layer +
            "COPY requirements.lock /opt/job/requirements.lock\n"
            "COPY wheels/ /opt/job/wheels/\n"
            "RUN --network=none python -m pip install --no-cache-dir --no-index --find-links=/opt/job/wheels --require-hashes --only-binary=:all: -r /opt/job/requirements.lock && rm -r /opt/job/wheels\n"
            "COPY source/ /opt/job/source/\n"
            "COPY context-receipt.json /opt/job/context-receipt.json\n"
            "USER 10001:10001\n"
            'ENTRYPOINT ["python", "-B", "infra/container_entry.py"]\n').encode("ascii")


def prepare(source: Path, destination: Path, dependencies: Path | None = None,
            *, patches: Path, architecture: str) -> dict:
    """O(B + P log P) work; O(P + largest-file + patch-bytes) space.

    The operator owns quiescent source/dependency/patch trees. A complete receipt is
    written last. Failure removes only this invocation's new destination.
    """
    if source.is_symlink() or not source.is_dir():
        raise ContextError("source-directory")
    source = source.resolve()
    destination = destination.parent.resolve(strict=True) / destination.name
    if destination.is_relative_to(source):
        raise ContextError("external-context")
    profile_bytes = regular_bytes(source, "infra/container-profile.json")
    profile = admitted_profile(strict_document(profile_bytes))
    if (dependencies is None) != (profile.dependencies == "stdlib"):
        raise ContextError("dependency-profile")
    requirements, wheels = b"", ()
    if dependencies is not None:
        if dependencies.is_symlink() or not dependencies.is_dir():
            raise ContextError("dependency-directory")
        dependencies = dependencies.resolve()
        if destination.is_relative_to(dependencies):
            raise ContextError("external-context")
        requirements, wheels = admitted_dependencies(dependencies)
    if patches.is_symlink() or not patches.is_dir():
        raise ContextError("patch-directory")
    patches = patches.resolve()
    if destination.is_relative_to(patches):
        raise ContextError("external-context")
    try:
        patch_members = admit_patch_files(architecture, lambda name: regular_bytes(patches, name))
    except ValueError as error:
        raise ContextError(str(error)) from error
    acquired = False
    records = []
    total = 0
    def write(relative: str, content: bytes) -> None:
        nonlocal total
        total += len(content)
        if total > MAX_TOTAL_BYTES:
            raise ContextError("context-byte-budget")
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        directory = target.parent
        while directory != destination:
            directory.chmod(0o755)
            directory = directory.parent
        with target.open("xb") as stream:
            stream.write(content)
        target.chmod(0o644)
        records.append({"path": relative, "bytes": len(content), "sha256": sha256(content).hexdigest()})
    try:
        previous_mask = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGTERM})
        try:
            destination.mkdir(mode=0o700)
            acquired = True
        finally:
            signal.pthread_sigmask(signal.SIG_SETMASK, previous_mask)
        for path in profile.files:
            write("source/" + path, regular_bytes(source, path))
        for path, content in patch_members.items():
            write(path, content)
        (destination / "wheels").mkdir(mode=0o755)
        (destination / "wheels").chmod(0o755)
        for name, expected in wheels:
            content = regular_bytes(dependencies, name)
            if sha256(content).hexdigest() != expected:
                raise ContextError("wheel-byte-mismatch")
            write("wheels/" + name, content)
        write("requirements.lock", requirements)
        write("Dockerfile", dockerfile(architecture))
        receipt = {"version":"1.0.0", "profile":profile.name, "profileSha256":sha256(profile_bytes).hexdigest(), "sourceStanding":"declared-file-content", "baseImage":BASE_IMAGE, "members":sorted(records, key=lambda item:item["path"])}
        with (destination / "context-receipt.json").open("x") as stream:
            json.dump(receipt, stream, sort_keys=True, indent=2)
            stream.write("\n")
        (destination / "context-receipt.json").chmod(0o644)
        return {"profile":profile.name, "files":len(records), "bytes":total, "receiptSha256":sha256((destination / "context-receipt.json").read_bytes()).hexdigest()}
    except BaseException:
        if acquired:
            shutil.rmtree(destination)
        raise


def _main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--dependencies", type=Path)
    parser.add_argument("--patches", type=Path, required=True)
    parser.add_argument("--architecture", choices=("arm64", "amd64"), required=True)
    args = parser.parse_args()
    try:
        result = prepare(args.source, args.destination, args.dependencies,
                         patches=args.patches, architecture=args.architecture)
    except (ContextError, OSError) as error:
        print(json.dumps({"status":"held", "code":str(error) if isinstance(error, ContextError) else "filesystem-boundary"}))
        return 1
    print(json.dumps({"status":"prepared", **result}, sort_keys=True))
    return 0


def main() -> int:
    def interrupted(number: int, _frame) -> None:
        raise SystemExit(128 + number)
    previous = signal.signal(signal.SIGTERM, interrupted)
    try:
        return _main()
    finally:
        signal.signal(signal.SIGTERM, previous)


if __name__ == "__main__":
    raise SystemExit(main())
