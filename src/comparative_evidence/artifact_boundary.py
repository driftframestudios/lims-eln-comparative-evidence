"""Deterministic boundary checks for generated comparison reports."""

from __future__ import annotations

from hashlib import sha256
import os
from pathlib import Path
import stat

from .contract_v1 import strict_json_loads
from .model import digest
from .report import render_html


REPORT_ARTIFACTS = frozenset({"comparison.json", "comparison.html"})


class ReportArtifactError(ValueError):
    """Report artifacts return to the released output contract."""


def report_artifact_inventory(root: Path) -> dict[str, str]:
    """Return byte identities for one complete regular-file report bundle."""

    if root.is_symlink() or not root.is_dir():
        raise ReportArtifactError(
            "report root requires one concrete output directory"
        )
    inventory: dict[str, str] = {}
    report_document: dict | None = None
    html_document: str | None = None
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            raise ReportArtifactError(
                f"report artifact {relative} requires a regular file"
            )
        if path.is_dir():
            continue
        content = _read_regular_file(path, relative)
        if relative == "comparison.json":
            try:
                document = strict_json_loads(content)
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
    try:
        expected_html = render_html(report_document)
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


def _read_regular_file(path: Path, relative: str) -> bytes:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise ReportArtifactError(
            f"report artifact {relative} requires a readable regular file"
        ) from error
    with os.fdopen(descriptor, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ReportArtifactError(
                f"report artifact {relative} requires a regular file"
            )
        return stream.read()
