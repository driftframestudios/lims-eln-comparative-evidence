"""Exact Bookworm patch inputs and an offline layer preceding application installs.

Debian package hashes were admitted from signed Bookworm security metadata.
The pip wheel hash comes from the release's PyPI metadata. Revisions receive
review, an image scan, and configured-job evidence together. Input admission is
O(B) time and space for the three selected artifacts, with B bounded by their
literal byte counts. Filesystem safety belongs to the caller's existing reader.
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


_PCRE_VERSION = "10.42-1+deb12u2"
_PERL_VERSION = "5.36.0-7+deb12u4"
_PIP_VERSION = "26.2.1"
_DEBIAN = "https://security.debian.org/debian-security/pool/updates/main"
_PIP = PatchArtifact(
    "pip-26.2.1-py3-none-any.whl", 1816632,
    "71138adf1f4ca900cdb7d289c21b7494329f2332b6d85f0e1c42108c0384ed3e",
    "https://files.pythonhosted.org/packages/f3/6e/1736e5b4ae2b778ef2f81c47d797de9f891d4d8acb047a24ca37a60294dd/pip-26.2.1-py3-none-any.whl",
)
_DEBIAN_INPUTS = (
    ("arm64", 230704, "8498d2c0bd6747dfc2fc6eec62774a86967079555f7043d5a7b78ee4efbbc0fb",
     1477684, "03d979b849a1a0a8955eee28b988dbc25a407fd3a0581df5c94e6ae7bcc01ddf"),
    ("amd64", 261628, "d2f7edfcc7689b9e0761c2742cc824ac86a20768bc5e8057818dc6875291fe76",
     1609596, "d7d1943aec9597629bf73075efcc5ef6dc9bda96d78e80d843156ecd448478b8"),
)


def patch_artifacts(architecture: str) -> tuple[PatchArtifact, ...]:
    """Return the three reviewed inputs for one explicitly selected platform."""
    if type(architecture) is not str or architecture not in ("arm64", "amd64"):
        raise ValueError("patch architecture must be arm64 or amd64")
    for arch, pcre_size, pcre_hash, perl_size, perl_hash in _DEBIAN_INPUTS:
        if arch == architecture:
            pcre = f"libpcre2-8-0_{_PCRE_VERSION}_{arch}.deb"
            perl = f"perl-base_{_PERL_VERSION}_{arch}.deb"
            return (
                PatchArtifact(pcre, pcre_size, pcre_hash, f"{_DEBIAN}/p/pcre2/{pcre}"),
                PatchArtifact(perl, perl_size, perl_hash, f"{_DEBIAN}/p/perl/{perl}"),
                _PIP,
            )
    raise ValueError("patch architecture has no reviewed inputs")


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


def dockerfile_patch(architecture: str) -> str:
    """Build with temporary read-only inputs and the patched wheel's own pip."""
    artifacts = patch_artifacts(architecture)
    mount = "/opt/security-patches"
    checksums = "".join(f"{item.sha256}  {mount}/{item.filename}\n" for item in artifacts)
    bootstrap = (
        "import runpy,sys; "
        f"sys.path.insert(0,{(mount + '/' + _PIP.filename)!r}); "
        "sys.argv=['pip','--isolated','--disable-pip-version-check','install',"
        "'--no-index','--no-deps','--no-cache-dir','--no-compile',"
        "'--only-binary=:all:','--require-hashes','--root-user-action=ignore',"
        f"'--find-links',{mount!r},'-r',{(mount + '/pip.lock')!r}]; "
        "runpy.run_module('pip',run_name='__main__')"
    )
    verify_pip = (
        "import importlib.metadata; "
        f"assert importlib.metadata.version('pip') == {_PIP_VERSION!r}"
    )
    # Literal shell input is quoted here; the caller supplies only an enum value.
    commands = (
        f'test "$(dpkg --print-architecture)" = {architecture}',
        f"printf %s {shlex.quote(checksums)} | sha256sum --check --strict -",
        "dpkg --install " + " ".join(shlex.quote(f"{mount}/{item.filename}") for item in artifacts[:2]),
        f"python -I -B -c {shlex.quote(bootstrap)}",
        'test "$(dpkg-query -W -f=\'${Version}\' libpcre2-8-0)" = ' + shlex.quote(_PCRE_VERSION),
        'test "$(dpkg-query -W -f=\'${Version}\' perl-base)" = ' + shlex.quote(_PERL_VERSION),
        f"python -I -B -c {shlex.quote(verify_pip)}",
    )
    # Escape physical newlines in the checksum input for a single Dockerfile RUN.
    checksum_command = commands[1].replace("\n", "\\n").replace("printf %s ", "printf %b ", 1)
    commands = (commands[0], checksum_command, *commands[2:])
    return (
        "RUN --network=none --mount=type=bind,source=security-patches,target="
        + mount + ",ro \\\n    " + " && \\\n    ".join(commands) + "\n"
    )


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="List the exact public patch inputs for acquisition.")
    parser.add_argument("architecture", choices=("arm64", "amd64"))
    args = parser.parse_args()
    print(json.dumps([asdict(item) for item in patch_artifacts(args.architecture)], indent=2))
