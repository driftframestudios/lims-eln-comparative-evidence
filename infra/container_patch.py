"""Exact installer input and offline guards for the pinned Trixie runtime.

The official base owns Debian runtime packages. The pip wheel hash comes from
the release's PyPI metadata and supplies the separate installer stage. Revisions
receive review, an image scan, and configured-job evidence together. Admission
is O(B) time and space for the single wheel, bounded by its literal byte count.
Filesystem safety belongs to the caller's existing regular-file reader.
"""

from dataclasses import asdict, dataclass
import hashlib
import json
import shlex
from typing import Callable


@dataclass(frozen=True)
class PatchArtifact:
    filename: str
    size: int
    sha256: str
    url: str


_PIP_VERSION = "26.2.1"
_PIP = PatchArtifact(
    "pip-26.2.1-py3-none-any.whl", 1816632,
    "71138adf1f4ca900cdb7d289c21b7494329f2332b6d85f0e1c42108c0384ed3e",
    "https://files.pythonhosted.org/packages/f3/6e/1736e5b4ae2b778ef2f81c47d797de9f891d4d8acb047a24ca37a60294dd/pip-26.2.1-py3-none-any.whl",
)


def patch_artifacts(architecture: str) -> tuple[PatchArtifact, ...]:
    """Return the verified installer wheel for one reviewed platform selection."""
    if type(architecture) is not str or architecture not in ("arm64", "amd64"):
        raise ValueError("patch architecture must be arm64 or amd64")
    return (_PIP,)


def admit_patch_files(architecture: str, read_file: Callable[[str], bytes]) -> dict[str, bytes]:
    """Admit selected artifacts using the caller's bounded, regular-file reader."""
    admitted: dict[str, bytes] = {}
    for artifact in patch_artifacts(architecture):
        data = read_file(artifact.filename)
        if type(data) is not bytes or len(data) != artifact.size:
            raise ValueError(f"patch input size differs: {artifact.filename}")
        if hashlib.sha256(data).hexdigest() != artifact.sha256:
            raise ValueError(f"patch input digest differs: {artifact.filename}")
        admitted[f"security-patches/{artifact.filename}"] = data
    admitted["security-patches/pip.lock"] = (
        f"pip=={_PIP_VERSION} --hash=sha256:{_PIP.sha256}\n"
    ).encode("ascii")
    return admitted


def _offline_patch_run(commands: tuple[str, ...]) -> str:
    """Mount reviewed inputs for one network-disabled build operation."""
    return (
        "RUN --network=none --mount=type=bind,source=security-patches,target="
        "/opt/security-patches,ro \\\n    " + " && \\\n    ".join(commands) + "\n"
    )


def _checksum_command(artifacts: tuple[PatchArtifact, ...]) -> str:
    checksums = "".join(
        f"{item.sha256}  /opt/security-patches/{item.filename}\\n" for item in artifacts
    )
    return f"printf %b {shlex.quote(checksums)} | sha256sum --check --strict -"


def dockerfile_base_guard(architecture: str) -> str:
    """Confirm the pinned base's Debian release and selected architecture."""
    patch_artifacts(architecture)
    commands = (
        f'test "$(dpkg --print-architecture)" = {architecture}',
        ". /etc/os-release",
        'test "$ID" = debian',
        'test "$VERSION_ID" = 13',
    )
    return "RUN --network=none " + " && \\n    ".replace("\\n", "\\\n").join(commands) + "\n"


def dockerfile_installer() -> str:
    """Bootstrap the verified pip wheel within the separate installer stage."""
    mount = "/opt/security-patches"
    bootstrap = (
        "import runpy,sys; "
        f"sys.path.insert(0,{(mount + '/' + _PIP.filename)!r}); "
        "sys.argv=['pip','--isolated','--disable-pip-version-check','install',"
        "'--no-index','--no-deps','--no-cache-dir','--no-compile',"
        "'--only-binary=:all:','--require-hashes','--root-user-action=ignore',"
        f"'--find-links',{mount!r},'-r',{(mount + '/pip.lock')!r}]; "
        "runpy.run_module('pip',run_name='__main__')"
    )
    verify = (
        "import importlib.metadata; "
        f"assert importlib.metadata.version('pip') == {_PIP_VERSION!r}"
    )
    return _offline_patch_run((
        _checksum_command((_PIP,)),
        f"python -I -B -c {shlex.quote(bootstrap)}",
        f"python -I -B -c {shlex.quote(verify)}",
    ))


def runtime_tooling_guard() -> str:
    """Inspect import, distribution, and executable routes in the final image."""
    return (
        "import importlib.util,importlib.metadata; from pathlib import Path; "
        "assert all(importlib.util.find_spec(name) is None for name in ('pip','ensurepip')), 'runtime installer modules'; "
        "assert all(dist.metadata.get('Name','').casefold() != 'pip' for dist in importlib.metadata.distributions()), 'runtime pip metadata'; "
        "assert all(not Path('/usr/local/bin', name).exists() for name in ('pip','pip3','pip3.12')), 'runtime pip executables'"
    )


def dockerfile_runtime_cleanup() -> str:
    """Remove the pinned base's installer routes from its runtime filesystem.

    These paths belong to the named CPython 3.12 base, rather than caller input.
    The upstream base layers retain their historical bytes; later installer-stage
    layers stay outside the final image's ancestry.
    """
    verify_base = "import importlib.metadata; assert importlib.metadata.version('pip') == '25.0.1', 'base pip version'"
    return (
        f"RUN --network=none python -I -B -c {shlex.quote(verify_base)}"
        " && rm -r /usr/local/lib/python3.12/site-packages/pip"
        " /usr/local/lib/python3.12/site-packages/pip-25.0.1.dist-info"
        " /usr/local/lib/python3.12/ensurepip"
        " && rm /usr/local/bin/pip /usr/local/bin/pip3 /usr/local/bin/pip3.12"
        f" && python -I -B -c {shlex.quote(runtime_tooling_guard())}\n"
    )


def dockerfile_runtime_guard() -> str:
    return f"RUN --network=none python -I -B -c {shlex.quote(runtime_tooling_guard())}\n"


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="List the exact public installer input for acquisition.")
    parser.add_argument("architecture", choices=("arm64", "amd64"))
    args = parser.parse_args()
    print(json.dumps([asdict(item) for item in patch_artifacts(args.architecture)], indent=2))
