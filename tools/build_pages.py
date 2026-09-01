"""Build and verify the deterministic Comparative Evidence Pages projection."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from hashlib import sha256
from html import escape
from html.parser import HTMLParser
import json
import os
from pathlib import Path, PurePosixPath
import posixpath
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from comparative_evidence.artifact_boundary import report_artifact_inventory
from comparative_evidence.compare import compare_synthetic_contract
from comparative_evidence.model import ObservationEnvelope, strict_json_loads
from comparative_evidence.publication import (
    BIG_BENCH_CANARY,
    MAPS_CANARY,
    PUBLIC_ATTRIBUTION,
    render_public_boundary,
)
from comparative_evidence.report import write_reports


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
REPORT_PATHS = (
    "reports/reference/comparison.html",
    "reports/reference/comparison.json",
)
SOURCE_LINK_PATHS = (
    "specification/comparison-profile.json",
    "fixtures/pairs/simulation-observation.json",
    "fixtures/contracts/planned-observation.json",
    "src/comparative_evidence/compare.py",
    "src/comparative_evidence/report.py",
    "release/repository-role.json",
)


class PagesBuildError(ValueError):
    """The projection returns to its source-owned publication contract."""


@dataclass(frozen=True, slots=True, init=False)
class _VerifiedCleanSourceProof:
    """A clean HEAD coordinate created only by the Git observation path."""

    revision: str
    repository_identity: _RepositoryIdentity


@dataclass(frozen=True, slots=True)
class _RepositoryIdentity:
    """Resolved identity of one Git worktree and its private Git directory."""

    worktree_root: Path
    git_directory: Path


@dataclass(frozen=True, slots=True)
class ValidationFixtureSourceProof:
    """An explicit non-publication source coordinate for deterministic tests."""

    revision: str

    def __post_init__(self) -> None:
        if REVISION_PATTERN.fullmatch(self.revision) is None:
            raise PagesBuildError(
                "validation fixture source requires one full 40-character Git SHA"
            )


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


def _load_object(repository_root: Path, relative: str) -> dict[str, Any]:
    value = strict_json_loads(
        (repository_root / relative).read_text(encoding="utf-8")
    )
    if not isinstance(value, dict):
        raise PagesBuildError(f"{relative} requires one JSON object")
    return value


def _run_git(repository_root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=repository_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise PagesBuildError(
            f"git {' '.join(arguments)} requires a readable repository coordinate"
        )
    return result.stdout.strip()


def _repository_identity(repository_root: Path) -> _RepositoryIdentity:
    resolved_root = repository_root.resolve()
    worktree_root = Path(
        _run_git(resolved_root, "rev-parse", "--show-toplevel")
    ).resolve()
    if resolved_root != worktree_root:
        raise PagesBuildError(
            "publication source requires the resolved Git worktree root"
        )
    git_directory_value = Path(
        _run_git(resolved_root, "rev-parse", "--git-dir")
    )
    git_directory = (
        git_directory_value
        if git_directory_value.is_absolute()
        else resolved_root / git_directory_value
    ).resolve()
    return _RepositoryIdentity(
        worktree_root=worktree_root,
        git_directory=git_directory,
    )


def _observe_clean_source(
    repository_root: Path,
    *,
    expected_revision: str | None = None,
    expected_identity: _RepositoryIdentity | None = None,
) -> tuple[_RepositoryIdentity, str]:
    identity = _repository_identity(repository_root)
    if expected_identity is not None and identity != expected_identity:
        raise PagesBuildError(
            "verified-clean source proof belongs to a different Git worktree"
        )
    revision = _run_git(identity.worktree_root, "rev-parse", "HEAD")
    if REVISION_PATTERN.fullmatch(revision) is None:
        raise PagesBuildError("source revision requires one full 40-character Git SHA")
    if expected_revision is not None and revision != expected_revision:
        raise PagesBuildError(
            "source HEAD differs from the verified publication revision"
        )
    status = _run_git(
        identity.worktree_root,
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
    )
    if status:
        raise PagesBuildError(
            "publication source requires a clean worktree at the exact revision"
        )
    return identity, revision


def clean_source_revision(
    repository_root: Path,
    *,
    expected_revision: str | None = None,
) -> _VerifiedCleanSourceProof:
    """Prove one clean worktree at its requested exact HEAD."""

    identity, revision = _observe_clean_source(
        repository_root,
        expected_revision=expected_revision,
    )
    proof = object.__new__(_VerifiedCleanSourceProof)
    object.__setattr__(proof, "revision", revision)
    object.__setattr__(proof, "repository_identity", identity)
    return proof


def _source_coordinate(
    repository_root: Path,
    source_proof: SourceProof,
) -> tuple[str, str]:
    if isinstance(source_proof, _VerifiedCleanSourceProof):
        _, revision = _observe_clean_source(
            repository_root,
            expected_revision=source_proof.revision,
            expected_identity=source_proof.repository_identity,
        )
        return revision, "clean_exact_revision"
    if isinstance(source_proof, ValidationFixtureSourceProof):
        return source_proof.revision, "validation_fixture"
    raise PagesBuildError(
        "Pages build requires a structured verified-clean or validation-fixture source proof"
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
    report: dict[str, Any],
) -> str:
    summary = report["summary"]
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
  <p class="kicker">Deterministic comparison</p>
  <h1>Inspect the result and its source.</h1>
  <p class="lede">This reference report compares one released selected-future simulation with a planned synthetic contract shape. It exercises the comparison contract while environment-observed evidence retains its own admission path.</p>
  <div class="actions">
    <a class="button" href="reports/reference/comparison.html">Open the readable report</a>
    <a class="button" href="reports/reference/comparison.json">Inspect report JSON</a>
  </div>
</header>
<main id="content" class="page-shell">
  <section class="panel" aria-labelledby="report-summary">
    <h2 id="report-summary">What this run establishes</h2>
    <p>The same fixtures, released profile, and comparator produce one stable report digest. The report records that its evidence comes from a synthetic contract exercise; an environment conclusion begins with separately admitted observed evidence.</p>
    <div class="metrics" aria-label="Reference report summary">
      <div class="metric"><strong>{summary['leaf_paths_compared']}</strong>paths compared</div>
      <div class="metric"><strong>{summary['converged_paths']}</strong>converged paths</div>
      <div class="metric"><strong>{summary['material_differences']}</strong>contract differences</div>
      <div class="metric"><strong>{summary['critical_differences']}</strong>critical differences</div>
    </div>
  </section>
  <section class="panel" aria-labelledby="source-coordinate">
    <h2 id="source-coordinate">Source coordinate</h2>
    <p>Every source link below resolves to revision <code>{escape(source_revision)}</code>. The <a href="projection-manifest.json">projection manifest</a> records byte counts and SHA-256 identities for this complete candidate.</p>
    <ul class="source-list">{source_items}</ul>
    <p><a href="{escape(repository_url, quote=True)}">Open the repository overview</a></p>
  </section>
  <section class="panel" aria-labelledby="reading-boundary">
    <h2 id="reading-boundary">Reading boundary</h2>
    <p>The report is a synthetic contract exercise. Its two differences show how the released classifier and visibility rules behave; they remain distinct from measured outcomes in a configured environment.</p>
    <p><a href="data-use.html">Read the data-use and crawler-intent note</a></p>
  </section>
</main>
<footer class="page-shell">
{render_public_boundary()}
</footer>
</body>
</html>
"""


def _data_use_html(*, canonical_origin: str) -> str:
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
{render_public_boundary()}
</footer>
</body>
</html>
"""


def _sha256(content: bytes) -> str:
    return sha256(content).hexdigest()


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def _projection_files(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.relative_to(root).as_posix() != MANIFEST_PATH
    )


def _manifest(
    root: Path,
    *,
    canonical_origin: str,
    repository_url: str,
    source_revision: str,
    source_standing: str,
    cname: str | None,
    report_digest: str,
) -> dict[str, Any]:
    report_sources = set(REPORT_PATHS)
    files = []
    for path in _projection_files(root):
        relative = path.relative_to(root).as_posix()
        content = path.read_bytes()
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


def validate_projection(root: Path) -> dict[str, Any]:
    """Validate manifest identity, portable links, and readable HTML structure."""

    manifest_path = root / MANIFEST_PATH
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise PagesBuildError("projection requires one regular manifest document")
    manifest = strict_json_loads(manifest_path.read_text(encoding="utf-8"))
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
    observed_paths = {
        path.relative_to(root).as_posix() for path in _projection_files(root)
    }
    if set(declared) != observed_paths:
        raise PagesBuildError(
            "projection manifest inventory differs from the generated files"
        )
    for relative, entry in declared.items():
        path = root / relative
        if path.is_symlink():
            raise PagesBuildError(f"projection file {relative} requires regular bytes")
        content = path.read_bytes()
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

    if (root / ".nojekyll").read_bytes() != b"":
        raise PagesBuildError(".nojekyll requires an empty marker file")
    cname_value = manifest.get("cname")
    if cname_value is not None and not isinstance(cname_value, str):
        raise PagesBuildError("projection manifest CNAME requires one hostname")
    cname = _cname(cname_value, canonical_origin)
    if cname is None:
        if "CNAME" in observed_paths:
            raise PagesBuildError("CNAME bytes require a declared hostname")
    elif (root / "CNAME").read_text(encoding="utf-8") != f"{cname}\n":
        raise PagesBuildError("CNAME bytes require the declared hostname")

    for relative in sorted(path for path in observed_paths if path.endswith(".html")):
        document = (root / relative).read_text(encoding="utf-8")
        if not document.startswith("<!doctype html>"):
            raise PagesBuildError(f"{relative} requires one HTML document")
        if '<html lang="en">' not in document or 'name="viewport"' not in document:
            raise PagesBuildError(
                f"{relative} requires language and viewport orientation"
            )
        maps_position = document.find(MAPS_CANARY)
        big_bench_position = document.find(BIG_BENCH_CANARY)
        if maps_position < 0 or big_bench_position <= maps_position:
            raise PagesBuildError(
                f"{relative} requires the approved MAPS then BIG-bench marker order"
            )
        if PUBLIC_ATTRIBUTION not in document:
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

    css = (root / "assets/site.css").read_text(encoding="utf-8")
    if (
        "@media (max-width: 52rem)" not in css
        or ".metrics, .source-list { grid-template-columns: 1fr; }" not in css
        or ".page-shell { width: min(" not in css
    ):
        raise PagesBuildError(
            "projection stylesheet requires narrow and bounded desktop structure"
        )
    index = (root / "index.html").read_text(encoding="utf-8")
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

    report_root = root / "reports/reference"
    report_inventory = report_artifact_inventory(report_root)
    report_document = strict_json_loads(
        (report_root / "comparison.json").read_text(encoding="utf-8")
    )
    if not isinstance(report_document, dict) or (
        manifest.get("reportDigest") != report_document.get("report_digest")
    ):
        raise PagesBuildError(
            "projection manifest report digest requires the validated runtime report"
        )
    for report_path in REPORT_PATHS:
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
    return {
        path.relative_to(root).as_posix(): _sha256(path.read_bytes())
        for path in sorted(item for item in root.rglob("*") if item.is_file())
    }


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

    repository_root = repository_root.resolve()
    output = output.resolve()
    canonical_origin = _canonical_origin(canonical_origin)
    repository_url = _repository_url(repository_url)
    cname = _cname(cname, canonical_origin)
    if output.exists():
        raise PagesBuildError(
            "Pages output requires a fresh destination so retained files stay visible"
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{output.name}-build-", dir=output.parent)
    )
    try:
        # This is the last practical local observation before source fixtures
        # are read. An isolated, read-only checkout closes the residual interval
        # in which another process could mutate a shared worktree.
        source_revision, source_standing = _source_coordinate(
            repository_root,
            source_proof,
        )
        report = compare_synthetic_contract(
            ObservationEnvelope.from_dict(
                _load_object(
                    repository_root,
                    "fixtures/pairs/simulation-observation.json",
                )
            ),
            ObservationEnvelope.from_dict(
                _load_object(
                    repository_root,
                    "fixtures/contracts/planned-observation.json",
                )
            ),
            _load_object(repository_root, "specification/comparison-profile.json"),
        )
        report_root = temporary / "reports/reference"
        write_reports(
            report,
            report_root,
            canonical_url=_canonical_url(
                canonical_origin,
                "reports/reference/comparison.html",
            ),
        )
        report_artifact_inventory(report_root)
        _write_text(temporary / "assets/site.css", _site_css())
        _write_text(
            temporary / "index.html",
            _index_html(
                canonical_origin=canonical_origin,
                repository_url=repository_url,
                source_revision=source_revision,
                report=report,
            ),
        )
        _write_text(
            temporary / "data-use.html",
            _data_use_html(canonical_origin=canonical_origin),
        )
        (temporary / ".nojekyll").write_bytes(b"")
        if cname is not None:
            _write_text(temporary / "CNAME", f"{cname}\n")
        manifest = _manifest(
            temporary,
            canonical_origin=canonical_origin,
            repository_url=repository_url,
            source_revision=source_revision,
            source_standing=source_standing,
            cname=cname,
            report_digest=report["report_digest"],
        )
        _write_text(
            temporary / MANIFEST_PATH,
            json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n",
        )
        validate_projection(temporary)
        os.replace(temporary, output)
        return manifest
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(
        description=(
            "Build a deterministic, source-bound Comparative Evidence Pages candidate"
        )
    )
    command.add_argument(
        "--output",
        type=Path,
        default=Path(".artifacts/pages"),
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
    return command


def main(arguments: list[str] | None = None) -> int:
    args = parser().parse_args(arguments)
    source_proof = clean_source_revision(
        ROOT,
        expected_revision=args.source_revision,
    )
    output = args.output if args.output.is_absolute() else ROOT / args.output
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
