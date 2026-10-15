"""Deterministic boundary checks for generated comparison reports."""

from __future__ import annotations

from contextlib import contextmanager
import io
from hashlib import sha256
from html import unescape
import os
from pathlib import Path
import re
import stat

from .contract_v1 import strict_json_loads
from .model import digest
from .report import render_html


REPORT_ARTIFACTS = frozenset({"comparison.json", "comparison.html"})
O_NOFOLLOW = getattr(os, "O_NOFOLLOW", None)
BYTE_ORDER_MARKS = (
    b"\x00\x00\xfe\xff",
    b"\xff\xfe\x00\x00",
    b"\xfe\xff",
    b"\xff\xfe",
    b"\xef\xbb\xbf",
)
CANONICAL_LINK_PATTERN = re.compile(
    r'<link rel="canonical" href="([^"]+)">'
)


class ReportArtifactError(ValueError):
    """Report artifacts return to the released output contract."""


def report_artifact_inventory(root: Path) -> dict[str, str]:
    """Return byte identities for one complete regular-file report bundle."""

    if root.is_symlink() or not root.is_dir():
        raise ReportArtifactError(
            "report root requires one concrete output directory"
        )
    def contents():
        for path in sorted(root.rglob("*")):
            relative = path.relative_to(root).as_posix()
            if path.is_symlink():
                raise ReportArtifactError(
                    f"report artifact {relative} requires a regular file"
                )
            if path.is_dir():
                continue
            yield relative, _read_regular_file(path, relative)
    return _report_content_inventory(contents())


def _report_inventory_at(directory_fd: int, limits: dict[str, int]) -> dict[str, str]:
    """Verify an owned candidate with reads bounded by its prepared byte counts."""
    names = set()
    with os.scandir(directory_fd) as entries:
        for entry in entries:
            names.add(entry.name)
            if len(names) > len(REPORT_ARTIFACTS):
                break
    if names != REPORT_ARTIFACTS:
        raise ReportArtifactError("report bundle requires exactly its JSON and HTML artifacts")
    return _report_content_inventory(
        (name, _read_regular_file(Path(name), name, max_bytes=limits[name], directory_fd=directory_fd))
        for name in REPORT_ARTIFACTS
    )


def _report_content_inventory(contents) -> dict[str, str]:
    inventory: dict[str, str] = {}
    report_document: dict | None = None
    html_document: str | None = None
    for relative, content in contents:
        if relative == "comparison.json":
            if any(content.startswith(marker) for marker in BYTE_ORDER_MARKS):
                raise ReportArtifactError(
                    "comparison.json requires UTF-8 text without a byte-order mark"
                )
            try:
                json_text = content.decode("utf-8", errors="strict")
            except UnicodeDecodeError as error:
                raise ReportArtifactError(
                    "comparison.json requires UTF-8 text"
                ) from error
            try:
                document = strict_json_loads(json_text)
            except ValueError as error:
                raise ReportArtifactError(
                    f"comparison.json requires strict JSON: {error}"
                ) from error
            if not isinstance(document, dict):
                raise ReportArtifactError(
                    "comparison.json requires one report object"
                )
            report_document = document
        elif relative == "comparison.html":
            try:
                html = content.decode("utf-8")
            except UnicodeDecodeError as error:
                raise ReportArtifactError(
                    "comparison.html requires UTF-8 text"
                ) from error
            if not html.startswith("<!doctype html>"):
                raise ReportArtifactError(
                    "comparison.html requires the portable report document"
                )
            html_document = html
        inventory[relative] = "sha256:" + sha256(content).hexdigest()

    observed = set(inventory)
    missing = sorted(REPORT_ARTIFACTS - observed)
    unexpected = sorted(observed - REPORT_ARTIFACTS)
    if missing or unexpected:
        details = []
        if missing:
            details.append("missing: " + ", ".join(missing))
        if unexpected:
            details.append("unexpected: " + ", ".join(unexpected))
        raise ReportArtifactError(
            "report bundle requires the released JSON and HTML artifacts; "
            + "; ".join(details)
        )
    if report_document is None or html_document is None:
        raise ReportArtifactError(
            "report bundle requires parsed JSON and HTML projections"
        )
    unsigned_report = dict(report_document)
    claimed_digest = unsigned_report.pop("report_digest", None)
    if claimed_digest != digest(unsigned_report):
        raise ReportArtifactError(
            "comparison.json requires the digest of its report content"
        )
    canonical_matches = CANONICAL_LINK_PATTERN.findall(html_document)
    if len(canonical_matches) > 1:
        raise ReportArtifactError(
            "comparison.html requires at most one canonical URL"
        )
    try:
        expected_html = render_html(
            report_document,
            canonical_url=(
                unescape(canonical_matches[0]) if canonical_matches else None
            ),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ReportArtifactError(
            "comparison.json requires the portable report fields"
        ) from error
    if html_document != expected_html:
        raise ReportArtifactError(
            "comparison.html requires the exact human-readable projection of "
            "comparison.json"
        )
    return inventory


def verify_reproducible_reports(first: Path, replay: Path) -> dict[str, str]:
    """Prove two isolated report runs carry the same exact bytes."""

    first_inventory = report_artifact_inventory(first)
    replay_inventory = report_artifact_inventory(replay)
    changed = sorted(
        name
        for name in REPORT_ARTIFACTS
        if first_inventory[name] != replay_inventory[name]
    )
    if changed:
        raise ReportArtifactError(
            "isolated comparison replay requires byte-identical reports; drift: "
            + ", ".join(changed)
        )
    return first_inventory


@contextmanager
def _owned_binary_stream(descriptor: int, mode: str):
    """Invalidate both stream layers before releasing their owned descriptor."""
    raw = None
    stream = None
    failure = None
    try:
        raw = io.FileIO(descriptor, mode, closefd=False)
        if mode == "rb":
            stream = io.BufferedReader(raw)
        elif mode == "wb":
            stream = io.BufferedWriter(raw)
        else:
            raise ValueError("artifact streams require binary read or write mode")
        yield stream
    except BaseException as error:
        failure = error
        raise
    finally:
        cleanups = []
        if stream is not None:
            try:
                stream.close()
            except BaseException as cleanup:
                cleanups.append(cleanup)
        if raw is not None and not raw.closed:
            try:
                raw.close()
            except BaseException as cleanup:
                cleanups.append(cleanup)
        retained = raw is not None and not raw.closed
        if not retained:
            try:
                os.close(descriptor)
            except BaseException as cleanup:
                cleanups.append(cleanup)
        if cleanups:
            cleanup = cleanups[0] if len(cleanups) == 1 else BaseExceptionGroup(
                "Stream and descriptor cleanup observations", cleanups,
            )
            if retained:
                owner = failure if failure is not None else cleanup
                owner.retained_stream = raw
                owner.retained_descriptor = descriptor
            if failure is None:
                raise cleanup
            previous = getattr(failure, "cleanup_error", None)
            failure.cleanup_error = cleanup if previous is None else BaseExceptionGroup(
                "Resource cleanup observations", [previous, cleanup],
            )
            failure.add_note("Resource cleanup needs local review; the primary failure remains available.")


def _read_regular_file(
    path: Path,
    relative: str,
    *,
    max_bytes: int | None = None,
    directory_fd: int | None = None,
    single_link: bool = False,
) -> bytes:
    if O_NOFOLLOW is None:
        raise ReportArtifactError(
            "report artifact verification requires operating-system O_NOFOLLOW support"
        )
    flags = os.O_RDONLY | O_NOFOLLOW | os.O_NONBLOCK
    try:
        descriptor = os.open(path, flags, dir_fd=directory_fd)
    except OSError as error:
        raise ReportArtifactError(
            f"report artifact {relative} requires a readable regular file"
        ) from error
    with _owned_binary_stream(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or (single_link and info.st_nlink != 1):
            raise ReportArtifactError(
                f"report artifact {relative} requires a regular file"
            )
        if max_bytes is not None and info.st_size > max_bytes:
            raise ReportArtifactError("report artifact exceeds its byte budget")
        content = stream.read() if max_bytes is None else stream.read(max_bytes + 1)
        if max_bytes is not None and len(content) > max_bytes:
            raise ReportArtifactError("report artifact exceeds its byte budget")
        return content
