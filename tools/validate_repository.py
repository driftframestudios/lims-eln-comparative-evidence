from __future__ import annotations

from datetime import datetime
from hashlib import sha1, sha256
import json
from pathlib import Path
import re
import sys
import tempfile
from urllib.parse import unquote, urldefrag, urlsplit

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

PUBLIC_POSSIBLE_SKILL_METADATA = {
    ".agents/skills/contextual-jargon-scan/SKILL.md": {
        "name": "contextual-jargon-scan",
        "source_band": "public_possible",
        "skill_version": "0.1.0",
        "upstream_repository": "driftframestudios/human-ai-systems-exemplars",
        "upstream_path": ".agents/skills/contextual-jargon-scan/SKILL.md",
        "upstream_revision": "0c023343e46cd9b1333a63c2d509787352fbad14",
        "upstream_blob_sha1": "3c3a94db99152385253e0281c8afa8fea8208ac5",
        "upstream_sha256": (
            "da383f99eaff364d7e17c3bff93d8da618ec95894a45ff78a9620d8d7fc81523"
        ),
        "adaptation_relation": "repository_local_derivative",
    },
    ".agents/skills/deterministic-comparison-report-projection/SKILL.md": {
        "name": "deterministic-comparison-report-projection",
        "source_band": "public_possible",
        "skill_version": "0.1.0",
        "origin": "repository_native",
    },
    ".agents/skills/repository-reentry/SKILL.md": {
        "name": "repository-reentry",
        "source_band": "public_possible",
        "skill_version": "0.1.0",
        "upstream_repository": "driftframestudios/human-ai-systems-exemplars",
        "upstream_path": ".agents/skills/repository-reentry/SKILL.md",
        "upstream_revision": "0c023343e46cd9b1333a63c2d509787352fbad14",
        "upstream_blob_sha1": "ac2c3732826c515b236598af10e0a204dbe14ace",
        "upstream_sha256": (
            "c60bb1bac3a993c78d94b1d05aaa7a97761b99275fc9acdc8285acba6f688f02"
        ),
        "adaptation_relation": "repository_local_derivative",
    },
    ".agents/skills/source-authority-mapping/SKILL.md": {
        "name": "source-authority-mapping",
        "source_band": "public_possible",
        "skill_version": "0.1.0",
        "upstream_repository": "driftframestudios/human-ai-systems-exemplars",
        "upstream_path": ".agents/skills/source-authority-mapping/SKILL.md",
        "upstream_revision": "0c023343e46cd9b1333a63c2d509787352fbad14",
        "upstream_blob_sha1": "112830e9b70540b0bc9a8535ab77c7a04c1a5926",
        "upstream_sha256": (
            "1420eaee7f6d58805c29eaff23644d4982fdf1f12d2f6ce3cc39c65791939aff"
        ),
        "adaptation_relation": "repository_local_derivative",
    },
}

_SKILL_REQUIRED_SECTIONS = (
    "## Contract",
    "## Rules",
    "## Operating sequence",
    "## Completion",
)
_GIT_OID = re.compile(r"[0-9a-f]{40}")
_SHA256 = re.compile(r"[0-9a-f]{64}")
ACCEPTED_PUBLICATION_OBSERVATION_TIME = "2026-09-04T05:24:33Z"
CURRENT_LIVING_ORIENTATION_TIME = "2026-09-30T15:07:07Z"
ORIENTATION_README_CONTRACTS = {
    "README.md": (
        "## First receipt",
        "## Current state",
        "## Choose your route",
        "## Quickest proof",
        "## Evidence posture",
        "## Evidence namespaces",
        "## Run it",
        "## Coordination Horizon",
        "## Branch topology",
    ),
    "accepted/README.md": (
        "## Reader job",
        "## Current state",
        "## Owner and schema",
        "## Use",
        "## Quickest fitting command",
        "## Evidence ceiling",
        "## Next route",
        "## Return to repository root",
    ),
    "receipts/redacted/README.md": (
        "## Reader job",
        "## Current state",
        "## Owner and schema",
        "## Use",
        "## Quickest fitting command",
        "## Evidence ceiling",
        "## Next route",
        "## Return to repository root",
    ),
    "simulated-closures/README.md": (
        "## Reader job",
        "## Current state",
        "## Owner and schema",
        "## Use",
        "## Quickest fitting command",
        "## Evidence ceiling",
        "## Next route",
        "## Return to repository root",
    ),
}
README_DISCOVERY_EXCLUDED_PARTS = {
    ".git",
    ".mypy_cache",
    ".nox",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
}
MARKDOWN_LINK_TARGET = re.compile(
    r"(?<!!)\[[^\]]+\]\(([^)\s]+)(?:\s+[\"'][^\"']*[\"'])?\)"
)
ACCEPTED_MAIN_SOURCE_REVISION = "2cca88982444ebc8280f9eb2891d97bf25dbeb95"
ACCEPTED_DOCS_REVISION = "6ccc087875b439eb70304771f534434acae3f01c"
ACCEPTED_PROJECTION_MANIFEST_BLOB_OID = (
    "2c701af256c74c5ec73dd266c0e62aeb554b11a6"
)
ACCEPTED_PROJECTION_MANIFEST_SHA256 = (
    "sha256:38d01a78be6804d04bc4f24c412777b8cb08fe2c65372e278480c106b4bcbeea"
)
ACCEPTED_CANONICAL_ORIGIN = "https://cometspectrum.io/"
ACCEPTED_PAGES_RUN_ID = "33839764767"
ACCEPTED_PAGES_DEPLOY_JOB_ID = "100919655445"
PRIOR_PUBLICATION_COORDINATES = {
    "status": "published",
    "source_coordinate_kind": "accepted_main_publication_carrier",
    "accepted_branch_ref": "refs/remotes/origin/main",
    "release_subject_commit_oid": "b5c13689a32739d29437e209816bf0cd6a878976",
    "receipt_path": "receipts/promotion-receipt.json",
    "receipt_state": "release_observed",
    "receipt_blob_oid": "4b2f41fe86fb4050d2d3f7da984baa78463c0c12",
    "receipt_file_sha256": (
        "sha256:733261cf52339f7f6b3e650302ab4b8b51c37eef57c752b0f5e2d2c4e27485ff"
    ),
    "initial_source_revision": "9012a03d1e5175c7794c4c8d5c5e620b5943a430",
    "initial_docs_revision": "17636bb3587ad768d5422439af57240141d5cb9c",
    "initial_projection_manifest_sha256": (
        "sha256:0e5e73f183b993aa740f2979a463518ec65f9dcce8405f17ffa5b910e22ed221"
    ),
    "source_revision": "fadbb1aba21a828eb56ee35c0abb4bb32b7f498c",
    "source_revision_relation": (
        "presentation_follow_up_preserving_golden_report_digest"
    ),
    "publication_revision_role": "pages_source_revision",
    "projection_manifest_field": "sourceRevision",
    "docs_revision": "ff9a82f78b15b07ab90774032d2ec7a7bfd2bcd1",
    "projection_manifest_blob_oid": "c7ba848af3920b4d6b4d8d67d71778595b643d53",
    "projection_manifest_sha256": (
        "sha256:9a577fc95c31f4cffa40ebce51dd6b9f1738a3f70c595c3de59e9d80de4a69bf"
    ),
    "canonical_origin": "https://cometspectrum.io/",
    "observed_at": "2026-09-02T17:18:30Z",
    "receiver_issue": 17,
    "target_branch": "docs",
}

from comparative_evidence.artifact_boundary import verify_reproducible_reports
from comparative_evidence.calibration import score_calibration
from comparative_evidence.compare import compare_synthetic_contract
from comparative_evidence.contract_v1 import (
    load_golden_specimen_result_projection_schema,
    validate_golden_specimen_observation,
)
from comparative_evidence.database_release import (
    TRUSTED_SIMULATED_DATABASE_RELEASE,
)
from comparative_evidence.model import ObservationEnvelope, digest, strict_json_loads
from comparative_evidence.golden_verification import compare_golden_specimen
from comparative_evidence.promotion_receipt import (
    canonical_digest as promotion_receipt_digest,
    file_digest as promotion_file_digest,
    validate_promotion_receipt,
)
from comparative_evidence.promotion_candidate import (
    CANDIDATE_COORDINATE,
    PRIOR_RELEASE_COORDINATE,
    canonical_json_digest_from_path as promotion_candidate_digest,
    validate_promotion_candidate,
)
from comparative_evidence.promotion_observation import (
    CANDIDATE_COORDINATE as OBSERVED_CANDIDATE_COORDINATE,
    RELEASE_COORDINATE as CURRENT_RELEASE_COORDINATE,
    validate_promotion_observation,
)
from comparative_evidence.report import write_reports
from comparative_evidence.simulated_closure import validate_simulated_closure_bundle
from check_automation_contract import validate_automation_contract
from check_artifacts import PATTERNS
from build_pages import (
    ValidationFixtureSourceProof,
    build_projection,
    verify_reproducible_projections,
)


def parse_skill_source(path: Path) -> tuple[dict[str, str], str]:
    """Return the simple scalar front matter and complete skill source."""
    content = path.read_text(encoding="utf-8")
    lines = content.splitlines()
    if not lines or lines[0] != "---":
        raise ValueError(f"{path} requires YAML front matter")
    try:
        closing = lines.index("---", 1)
    except ValueError as error:
        raise ValueError(f"{path} has unclosed YAML front matter") from error
    metadata: dict[str, str] = {}
    for line in lines[1:closing]:
        if not line.strip():
            continue
        if ":" not in line:
            raise ValueError(f"{path} has unsupported front-matter line {line!r}")
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip().strip('"')
    return metadata, content


def _unfenced_markdown(content: str) -> str:
    """Return Markdown source with fenced code content removed."""
    visible: list[str] = []
    fence: str | None = None
    for line in content.splitlines():
        marker = line.lstrip()
        opening = re.match(r"(`{3,}|~{3,})", marker)
        if fence is None and opening:
            fence = opening.group(1)[0]
            continue
        if fence is not None:
            if re.match(rf"{re.escape(fence)}{{3,}}\s*$", marker):
                fence = None
            continue
        visible.append(line)
    return "\n".join(visible)


def _markdown_headings(content: str) -> list[str]:
    """Return ATX headings outside fenced code blocks."""
    return [
        match.group(0).rstrip(" #")
        for line in _unfenced_markdown(content).splitlines()
        if (match := re.match(r"^#{1,6}\s+.+?\s*$", line))
    ]


def _markdown_heading_ids(content: str) -> set[str]:
    """Return the GitHub-style IDs needed by repository-local links."""
    identifiers: set[str] = set()
    duplicates: dict[str, int] = {}
    for heading in _markdown_headings(content):
        label = re.sub(r"^#{1,6}\s+", "", heading)
        slug = label.casefold().strip()
        slug = re.sub(r"[^\w\- ]", "", slug, flags=re.UNICODE)
        slug = re.sub(r"\s+", "-", slug)
        duplicate = duplicates.get(slug, 0)
        identifiers.add(slug if duplicate == 0 else f"{slug}-{duplicate}")
        duplicates[slug] = duplicate + 1
    return identifiers


def _markdown_link_findings(path: Path, root: Path) -> list[str]:
    """Return repository-bound target and fragment findings for one README."""
    findings: list[str] = []
    relative_path = str(path.relative_to(root))
    content = path.read_text(encoding="utf-8")
    for raw_target in MARKDOWN_LINK_TARGET.findall(_unfenced_markdown(content)):
        target = raw_target.strip("<>")
        parsed = urlsplit(target)
        if parsed.scheme or parsed.netloc:
            continue
        location, fragment = urldefrag(target)
        destination = (
            path.resolve()
            if not location
            else (path.parent / unquote(location)).resolve()
        )
        try:
            destination.relative_to(root.resolve())
        except ValueError:
            findings.append(
                f"{relative_path} link leaves the repository: {target}"
            )
            continue
        if not destination.exists():
            findings.append(
                f"{relative_path} link target is absent: {target}"
            )
            continue
        if fragment and destination.is_file() and destination.suffix == ".md":
            destination_ids = _markdown_heading_ids(
                destination.read_text(encoding="utf-8")
            )
            if unquote(fragment) not in destination_ids:
                findings.append(
                    f"{relative_path} link fragment is absent: {target}"
                )
    return findings


def validate_orientation_readmes(root: Path = ROOT) -> list[str]:
    """Validate the complete README graph and its result-first root facts."""
    findings: list[str] = []
    expected_paths = set(ORIENTATION_README_CONTRACTS)
    observed_paths = {
        str(path.relative_to(root))
        for path in root.rglob("README.md")
        if not README_DISCOVERY_EXCLUDED_PARTS.intersection(
            path.relative_to(root).parts
        )
    }
    if observed_paths != expected_paths:
        findings.append(
            "orientation README inventory differs: expected "
            f"{sorted(expected_paths)!r}; received {sorted(observed_paths)!r}"
        )

    for relative_path, required_headings in ORIENTATION_README_CONTRACTS.items():
        path = root / relative_path
        if not path.is_file():
            continue
        content = path.read_text(encoding="utf-8")
        headings = set(_markdown_headings(content))
        for heading in required_headings:
            if heading not in headings:
                findings.append(f"{relative_path} requires heading {heading!r}")
        findings.extend(_markdown_link_findings(path, root))

    root_readme = root / "README.md"
    role_path = root / "release/repository-role.json"
    if root_readme.is_file() and role_path.is_file():
        root_content = root_readme.read_text(encoding="utf-8")
        role = json.loads(role_path.read_text(encoding="utf-8"))
        counts = role.get("golden_specimen_verification", {}).get(
            "classification_counts", {}
        )
        required_result_routes = (
            "https://cometspectrum.io/reports/golden-specimen/comparison.html",
            "https://cometspectrum.io/reports/golden-specimen/comparison.json",
            "(release/repository-role.json)",
        )
        for route in required_result_routes:
            if route not in root_content:
                findings.append(f"README.md requires result route {route!r}")
        labels = {
            "agreement": "Agreement",
            "explainable_variation": "Explainable variation",
            "material_divergence": "Material divergence",
        }
        for key, label in labels.items():
            count = counts.get(key)
            if f"| {label} | {count} |" not in root_content:
                findings.append(
                    f"README.md must present {label!r} count {count!r}"
                )
    return findings


def validate_collaboration_workbench(root: Path = ROOT) -> list[str]:
    """Validate the exact copy-local skill workbench and orientation routes."""
    findings: list[str] = []
    skills_root = root / ".agents" / "skills"
    actual_paths = {
        str(path.relative_to(root)) for path in skills_root.glob("*/SKILL.md")
    }
    expected_paths = set(PUBLIC_POSSIBLE_SKILL_METADATA)
    if actual_paths != expected_paths:
        findings.append(
            "public-possible skill inventory differs: expected "
            f"{sorted(expected_paths)!r}; received {sorted(actual_paths)!r}"
        )
    for relative_path, expected in PUBLIC_POSSIBLE_SKILL_METADATA.items():
        path = root / relative_path
        if not path.is_file():
            continue
        try:
            metadata, content = parse_skill_source(path)
        except ValueError as error:
            findings.append(str(error))
            continue
        observed = {key: metadata.get(key) for key in expected}
        if observed != expected:
            findings.append(
                f"{relative_path} metadata differs: expected {expected!r}; "
                f"received {observed!r}"
            )
        if path.parent.name != metadata.get("name"):
            findings.append(f"{relative_path} directory and skill name must match")
        if metadata.get("adaptation_relation") == "repository_local_derivative":
            if not _GIT_OID.fullmatch(metadata.get("upstream_revision", "")):
                findings.append(f"{relative_path} requires a full upstream revision")
            if not _GIT_OID.fullmatch(metadata.get("upstream_blob_sha1", "")):
                findings.append(f"{relative_path} requires an upstream blob identity")
            if not _SHA256.fullmatch(metadata.get("upstream_sha256", "")):
                findings.append(f"{relative_path} requires an upstream SHA-256 identity")
        for heading in _SKILL_REQUIRED_SECTIONS:
            if heading not in content:
                findings.append(f"{relative_path} requires {heading}")
        if "notion.so" in content or "app.notion.com" in content:
            findings.append(
                f"{relative_path} must remain usable through repository-local "
                "guidance; private workspace locator found"
            )
    for orientation_name in ("README.md", "AGENTS.md"):
        orientation_path = root / orientation_name
        if not orientation_path.is_file():
            findings.append(f"{orientation_name} is required for workbench routing")
            continue
        orientation = orientation_path.read_text(encoding="utf-8")
        for relative_path in expected_paths:
            if relative_path not in orientation:
                findings.append(
                    f"{orientation_name} must link the exact skill path {relative_path}"
                )
    return findings


def validate_living_publication_state(root: Path = ROOT) -> list[str]:
    """Check that living carriers describe the accepted public baseline."""
    findings: list[str] = []
    horizon = json.loads(
        (root / "COORDINATION-HORIZON.json").read_text(encoding="utf-8")
    )
    first_receipt = json.loads(
        (root / "first-receipt.json").read_text(encoding="utf-8")
    )
    machine_node = json.loads(
        (root / "machine-node.json").read_text(encoding="utf-8")
    )
    repository_role = json.loads(
        (root / "release/repository-role.json").read_text(encoding="utf-8")
    )
    timestamps = {
        horizon.get("as_of"),
        horizon.get("metadata", {}).get("updated_at"),
        first_receipt.get("as_of"),
        first_receipt.get("metadata", {}).get("updated_at"),
        machine_node.get("metadata", {}).get("updated_at"),
    }
    if timestamps != {CURRENT_LIVING_ORIENTATION_TIME}:
        findings.append("living carriers require one current orientation time")
    work_items = {
        item.get("item_id"): item
        for item in horizon.get("work_items", [])
        if isinstance(item, dict)
    }
    publication_item = work_items.get("WORK-COMPARATIVE-PUBLICATION-017", {})
    candidate_item = work_items.get("WORK-COMPARATIVE-PROMOTION-004", {})
    successor_publication_item = work_items.get(
        "WORK-COMPARATIVE-PUBLICATION-031", {}
    )
    living_orientation_item = work_items.get(
        "WORK-GOVERNANCE-LIVING-ORIENTATION-038", {}
    )
    program_handoff_item = work_items.get(
        "WORK-PROGRAM-CONSTELLATION-HANDOFF-001", {}
    )
    if (
        horizon.get("current_item_ids")
        != ["WORK-PROGRAM-CONSTELLATION-HANDOFF-001"]
        or publication_item.get("state") != "complete"
        or candidate_item.get("state") != "complete"
        or successor_publication_item.get("state") != "complete"
        or living_orientation_item.get("state") != "complete"
        or program_handoff_item.get("state") != "ready"
        or program_handoff_item.get("dependency_ids")
        != ["WORK-GOVERNANCE-LIVING-ORIENTATION-038"]
    ):
        findings.append(
            "completed publication and living orientation must route to the ready Program handoff"
        )
    publication_sources = [
        item
        for item in first_receipt.get("source_permissions", [])
        if isinstance(item, dict)
        and item.get("source") == "accepted-main-observation-carrier"
    ]
    if (
        len(publication_sources) != 1
        or publication_sources[0].get("permission") != "read"
        or ACCEPTED_MAIN_SOURCE_REVISION
        not in publication_sources[0].get("verification", "")
    ):
        findings.append("First Receipt must retain the accepted main source carrier")
    handoff = first_receipt.get("handoff", {})
    if (
        handoff.get("recipient_role")
        != "Program specification constellation receiver"
        or handoff.get("next_safe_action")
        != horizon.get("reentry_capsule", {}).get("next_safe_action")
    ):
        findings.append("living carriers must share one future receiving action")
    publication = repository_role.get("publication_coordinates", {})
    expected_fields = {
        "status": "published",
        "source_coordinate_kind": "accepted_main_publication_carrier",
        "accepted_branch_ref": "refs/remotes/origin/main",
        "release_subject_commit_oid": (
            "0289ff835c790693a769347e69da0abdcfaa47de"
        ),
        "receipt_path": "receipts/promotion-observation-v0.3.2.json",
        "receipt_state": "release_observed",
        "receipt_blob_oid": "c6318597b4d038cd59c897d4041c7e0178e60e15",
        "receipt_file_sha256": (
            "sha256:acccb507f0675cdc079aa56bc12299bd4ce533344cb150e42dba1c991c024fd4"
        ),
        "source_revision": ACCEPTED_MAIN_SOURCE_REVISION,
        "source_revision_relation": (
            "accepted_observation_carrier_descending_from_signed_release"
        ),
        "publication_revision_role": "pages_source_revision",
        "projection_manifest_field": "sourceRevision",
        "docs_revision": ACCEPTED_DOCS_REVISION,
        "projection_manifest_blob_oid": ACCEPTED_PROJECTION_MANIFEST_BLOB_OID,
        "projection_manifest_sha256": ACCEPTED_PROJECTION_MANIFEST_SHA256,
        "canonical_origin": ACCEPTED_CANONICAL_ORIGIN,
        "observed_at": ACCEPTED_PUBLICATION_OBSERVATION_TIME,
        "receiver_issue": 31,
        "target_branch": "docs",
        "hosted_observation": {
            "pages_run_id": ACCEPTED_PAGES_RUN_ID,
            "deploy_job_id": ACCEPTED_PAGES_DEPLOY_JOB_ID,
            "pages_run_head_revision": ACCEPTED_DOCS_REVISION,
            "pages_run_conclusion": "success",
            "pages_run_completed_at": "2026-09-04T05:15:41Z",
            "verified_at": ACCEPTED_PUBLICATION_OBSERVATION_TIME,
            "byte_parity": "verified_against_docs_projection",
            "responsive_report_surface": "narrow_and_desktop_verified",
        },
    }
    observed_fields = {key: publication.get(key) for key in expected_fields}
    if observed_fields != expected_fields:
        findings.append("release role differs from the accepted public coordinates")
    prior_publications = [
        item.get("publication_coordinates")
        for item in repository_role.get("historical_external_releases", [])
        if isinstance(item, dict)
        and item.get("external_release") == "comparison-v0.3.1"
    ]
    if prior_publications != [PRIOR_PUBLICATION_COORDINATES]:
        findings.append("release role must retain the complete 0.3.1 publication")
    return findings


def _load(relative: str) -> dict:
    value = strict_json_loads((ROOT / relative).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{relative} requires a JSON object")
    return value


def _repository_json_documents() -> int:
    count = 0
    for path in sorted(ROOT.rglob("*.json")):
        if any(part in {".git", "build", "__pycache__"} for part in path.parts):
            continue
        strict_json_loads(path.read_text(encoding="utf-8"))
        count += 1
    return count


def _repository_secret_shape_findings() -> list[str]:
    findings: list[str] = []
    for path in sorted(ROOT.rglob("*")):
        if (
            not path.is_file()
            or any(part in {".git", "build", "__pycache__"} for part in path.parts)
            or path.suffix in {".pyc", ".png", ".jpg", ".jpeg", ".gif", ".pdf"}
        ):
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if any(pattern.search(content) for pattern in PATTERNS):
            findings.append(str(path.relative_to(ROOT)))
    return findings


def _persisted_environment_claims() -> list[str]:
    findings: list[str] = []
    for relative_root in ("fixtures", "receipts/redacted"):
        for path in sorted((ROOT / relative_root).rglob("*.json")):
            document = strict_json_loads(path.read_text(encoding="utf-8"))
            if isinstance(document, dict) and (
                document.get("evidence_mode") == "observed"
                or document.get("assurance_stage") == "accepted"
            ):
                findings.append(str(path.relative_to(ROOT)))
    return findings


def validate_json_contract(
    *,
    schema: dict,
    instance: dict,
    version_property: str,
    expected_version: str,
    contract_name: str,
) -> None:
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise ValueError(
            f"{contract_name} schema requires a valid Draft 2020-12 contract: "
            f"{exc.message}"
        ) from exc

    declared_version = (
        schema.get("properties", {})
        .get(version_property, {})
        .get("const")
    )
    if declared_version != expected_version:
        raise ValueError(
            f"{contract_name} schema release binding requires "
            f"{expected_version!r}; schema declares {declared_version!r}"
        )

    errors = sorted(
        Draft202012Validator(schema).iter_errors(instance),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    if errors:
        details = []
        for error in errors:
            location = "$" + "".join(
                f"[{part}]" if isinstance(part, int) else f".{part}"
                for part in error.absolute_path
            )
            details.append(f"{location}: {error.message}")
        raise ValueError(
            f"{contract_name} instance requires schema conformance: "
            + "; ".join(details)
        )


def main() -> int:
    orientation_findings = validate_orientation_readmes()
    if orientation_findings:
        raise ValueError(
            "orientation README graph differs from its local contract: "
            + "; ".join(orientation_findings)
        )
    workbench_findings = validate_collaboration_workbench()
    if workbench_findings:
        raise ValueError(
            "collaboration workbench differs from its local contract: "
            + "; ".join(workbench_findings)
        )
    publication_findings = validate_living_publication_state()
    if publication_findings:
        raise ValueError(
            "living publication state differs from its accepted baseline: "
            + "; ".join(publication_findings)
        )
    json_count = _repository_json_documents()
    bundle_path = (
        ROOT
        / "fixtures/simulated-closures/future-reality-2028-06-30-v1.json"
    )
    bundle = _load(
        "fixtures/simulated-closures/future-reality-2028-06-30-v1.json"
    )
    bundle_summary = validate_simulated_closure_bundle(bundle)
    manifest = _load("release/repository-role.json")
    promotion_schema_path = ROOT / "schemas/promotion-receipt.schema.json"
    promotion_receipt_path = ROOT / "receipts/promotion-receipt.json"
    promotion_candidate_schema_path = (
        ROOT / "schemas/promotion-candidate.schema.json"
    )
    promotion_candidate_path = ROOT / "receipts/promotion-candidate.json"
    promotion_observation_schema_path = (
        ROOT / "schemas/promotion-observation-v0.3.2.schema.json"
    )
    promotion_observation_path = (
        ROOT / "receipts/promotion-observation-v0.3.2.json"
    )
    promotion_schema = _load("schemas/promotion-receipt.schema.json")
    promotion_receipt = _load("receipts/promotion-receipt.json")
    promotion_candidate_schema = _load(
        "schemas/promotion-candidate.schema.json"
    )
    promotion_candidate = _load("receipts/promotion-candidate.json")
    promotion_observation_schema = _load(
        "schemas/promotion-observation-v0.3.2.schema.json"
    )
    promotion_observation = _load(
        "receipts/promotion-observation-v0.3.2.json"
    )
    validate_json_contract(
        schema=promotion_schema,
        instance=promotion_receipt,
        version_property="schema_version",
        expected_version="1.0.0",
        contract_name="promotion receipt",
    )
    validate_promotion_receipt(promotion_receipt)
    validate_json_contract(
        schema=promotion_candidate_schema,
        instance=promotion_candidate,
        version_property="schema_version",
        expected_version="1.0.0",
        contract_name="promotion candidate",
    )
    validate_promotion_candidate(promotion_candidate)
    validate_json_contract(
        schema=promotion_observation_schema,
        instance=promotion_observation,
        version_property="schema_version",
        expected_version="1.0.0",
        contract_name="promotion observation",
    )
    validate_promotion_observation(promotion_observation)
    expected_promotion_binding = {
        "schema_path": "schemas/promotion-receipt.schema.json",
        "schema_version": "1.0.0",
        "schema_file_sha256": promotion_file_digest(promotion_schema_path),
        "receipt_path": "receipts/promotion-receipt.json",
        "receipt_canonical_json_digest": promotion_receipt_digest(
            promotion_receipt
        ),
    }
    expected_candidate_binding = {
        "schema_path": "schemas/promotion-candidate.schema.json",
        "schema_version": "1.0.0",
        "schema_file_sha256": (
            "sha256:"
            + sha256(promotion_candidate_schema_path.read_bytes()).hexdigest()
        ),
        "receipt_path": "receipts/promotion-candidate.json",
        "receipt_file_sha256": (
            "sha256:" + sha256(promotion_candidate_path.read_bytes()).hexdigest()
        ),
        "receipt_canonical_json_digest": promotion_candidate_digest(
            promotion_candidate_path
        ),
    }
    expected_observation_binding = {
        "schema_path": "schemas/promotion-observation-v0.3.2.schema.json",
        "schema_version": "1.0.0",
        "schema_file_sha256": (
            "sha256:"
            + sha256(promotion_observation_schema_path.read_bytes()).hexdigest()
        ),
        "receipt_path": "receipts/promotion-observation-v0.3.2.json",
        "receipt_file_sha256": (
            "sha256:"
            + sha256(promotion_observation_path.read_bytes()).hexdigest()
        ),
        "receipt_canonical_json_digest": digest(promotion_observation),
    }
    release_subject = promotion_receipt["release_subject"]
    if not isinstance(release_subject, dict):
        raise ValueError("observed promotion requires one immutable release subject")
    expected_release_subject = {
        "git_object_format": "sha1",
        "tag": "comparison-v0.3.1",
        "tag_object_oid": "4c29f6ca410eb4400c55ad77fc34ada2960d1972",
        "commit_oid": "b5c13689a32739d29437e209816bf0cd6a878976",
        "tree_oid": "10a784b8a677ee6eb524d2860ff5ee7151d6050b",
        "archive_format": "git-tar",
        "archive_digest": (
            "sha256:92c2d57bd9e75c650365db4b481a22a6580b201926ba1c666fcf8cb8c9311a2e"
        ),
        "promoted_at": "2026-09-02T06:27:41Z",
        "tag_signature_verification": "valid",
        "hosted_check_contexts": [
            {
                "name": "Repository validation",
                "run_id": "33597969223",
                "conclusion": "success",
            },
            {
                "name": "branch-shape",
                "run_id": "33597969333",
                "conclusion": "success",
            },
        ],
        "local_verification_signals": [
            "git rev-parse verified reviewed candidate 59d58c46d27a77150d399870ecebef2635c38dc5 and accepted commit b5c13689a32739d29437e209816bf0cd6a878976 share tree 10a784b8a677ee6eb524d2860ff5ee7151d6050b",
            "git archive --format=tar comparison-v0.3.1 reproduced sha256:92c2d57bd9e75c650365db4b481a22a6580b201926ba1c666fcf8cb8c9311a2e",
        ],
    }
    if release_subject != expected_release_subject:
        raise ValueError(
            "promotion receipt requires the reviewed comparison-v0.3.1 release evidence"
        )
    carrier_observation_time = CURRENT_LIVING_ORIENTATION_TIME
    publication_source_name = "accepted-main-observation-carrier"
    release_commit = release_subject["commit_oid"]
    golden_report_digest = (
        "sha256:a2f92ae4acb9fb7d835d0a9b126bb1932ae69b06b094303180dd9fea7217b77c"
    )
    candidate_receipt_bytes = promotion_candidate_path.read_bytes()
    promotion_observation_bytes = promotion_observation_path.read_bytes()
    expected_promotion_coordinates = {
        "status": "release_observed",
        "settled_receipt_id": promotion_observation["promotion_receipt_id"],
        "observation_receipt": "receipts/promotion-observation-v0.3.2.json",
        "observation_receipt_file_sha256": (
            "sha256:" + sha256(promotion_observation_bytes).hexdigest()
        ),
        "observation_receipt_canonical_json_digest": digest(
            promotion_observation
        ),
        "candidate_receipt": "receipts/promotion-candidate.json",
        "candidate_receipt_file_sha256": (
            "sha256:" + sha256(candidate_receipt_bytes).hexdigest()
        ),
        "candidate_receipt_canonical_json_digest": promotion_candidate_digest(
            promotion_candidate_path
        ),
        "target_release": promotion_observation["target_release"],
        "candidate_coordinate": OBSERVED_CANDIDATE_COORDINATE,
        "release_subject": CURRENT_RELEASE_COORDINATE,
        "prior_release": promotion_candidate["prior_release_coordinate"],
        "required_roles": [
            "site_reading_governance",
            "program_specification",
            "enterprise_implementation",
            "simulated_final_state",
            "comparative_evidence",
        ],
    }
    observation_blob_header = (
        f"blob {len(promotion_observation_bytes)}\0".encode("ascii")
    )
    expected_publication_coordinates = {
        "status": "published",
        "source_coordinate_kind": "accepted_main_publication_carrier",
        "accepted_branch_ref": "refs/remotes/origin/main",
        "release_subject_commit_oid": CURRENT_RELEASE_COORDINATE["commit_oid"],
        "receipt_path": "receipts/promotion-observation-v0.3.2.json",
        "receipt_state": "release_observed",
        "receipt_blob_oid": sha1(
            observation_blob_header + promotion_observation_bytes,
            usedforsecurity=False,
        ).hexdigest(),
        "receipt_file_sha256": (
            "sha256:" + sha256(promotion_observation_bytes).hexdigest()
        ),
        "source_revision": ACCEPTED_MAIN_SOURCE_REVISION,
        "source_revision_relation": (
            "accepted_observation_carrier_descending_from_signed_release"
        ),
        "publication_revision_role": "pages_source_revision",
        "projection_manifest_field": "sourceRevision",
        "docs_revision": ACCEPTED_DOCS_REVISION,
        "projection_manifest_blob_oid": ACCEPTED_PROJECTION_MANIFEST_BLOB_OID,
        "projection_manifest_sha256": ACCEPTED_PROJECTION_MANIFEST_SHA256,
        "canonical_origin": ACCEPTED_CANONICAL_ORIGIN,
        "observed_at": ACCEPTED_PUBLICATION_OBSERVATION_TIME,
        "receiver_issue": 31,
        "target_branch": "docs",
        "hosted_observation": {
            "pages_run_id": ACCEPTED_PAGES_RUN_ID,
            "deploy_job_id": ACCEPTED_PAGES_DEPLOY_JOB_ID,
            "pages_run_head_revision": ACCEPTED_DOCS_REVISION,
            "pages_run_conclusion": "success",
            "pages_run_completed_at": "2026-09-04T05:15:41Z",
            "verified_at": ACCEPTED_PUBLICATION_OBSERVATION_TIME,
            "byte_parity": "verified_against_docs_projection",
            "responsive_report_surface": "narrow_and_desktop_verified",
        },
    }
    if manifest.get("automation_controls") != {
        "pull_request_workflow": ".github/workflows/pull-request.yml",
        "pull_request_targets": ["develop", "main"],
        "pull_request_runner": "ubuntu-24.04",
        "pull_request_python": "3.12",
        "pull_request_timeout_minutes": 10,
        "pull_request_permissions": {"contents": "read"},
        "pull_request_concurrency_cancellation": True,
        "manual_full_proof_workflow": ".github/workflows/verify.yml",
        "dependabot_configuration": ".github/dependabot.yml",
        "dependabot_target": "develop",
        "dependabot_interval": "monthly",
        "dependabot_open_pull_requests_per_ecosystem": 2,
        "dependabot_grouped_update_types": ["minor", "patch"],
        "monthly_budget_minutes": {"minimum": 100, "maximum": 300},
        "settings_state": (
            "repository_validation_observed_ruleset_review_configured_bypass"
        ),
    }:
        raise ValueError(
            "release automation controls require the bounded hosted source contract"
        )
    validate_automation_contract(
        ROOT,
        declared_controls=manifest["automation_controls"],
    )
    profile = _load("specification/comparison-profile.json")
    profile_schema = _load("schemas/comparison-profile.schema.json")
    observation_schema = _load("schemas/observation-envelope.schema.json")
    validate_json_contract(
        schema=profile_schema,
        instance=profile,
        version_property="profile_version",
        expected_version=manifest["contract_bindings"][
            "comparison_profile_schema"
        ],
        contract_name="comparison profile",
    )
    simulation_observation = _load("fixtures/pairs/simulation-observation.json")
    planned_observation = _load("fixtures/contracts/planned-observation.json")
    planned_acceptance = _load(
        "fixtures/contracts/planned-acceptance-envelope.json"
    )
    for contract_name, observation in (
        ("simulated observation envelope", simulation_observation),
        ("planned synthetic contract envelope", planned_observation),
        ("planned acceptance contract envelope", planned_acceptance),
    ):
        validate_json_contract(
            schema=observation_schema,
            instance=observation,
            version_property="envelope_version",
            expected_version=manifest["contract_bindings"][
                "observation_envelope_schema"
            ],
            contract_name=contract_name,
        )
    golden_profile = _load(
        "specification/golden-specimen-verification-profile.json"
    )
    constellation = _load("constellation.lock.json")
    machine_node = _load("machine-node.json")
    first_receipt = _load("first-receipt.json")
    coordination_horizon = _load("COORDINATION-HORIZON.json")
    expected_comparison_coordinate = {
        "release": release_subject["tag"],
        "tag_object_oid": release_subject["tag_object_oid"],
        "commit": release_subject["commit_oid"],
        "digest": f"git-tree-sha1:{release_subject['tree_oid']}",
        "archive_digest": release_subject["archive_digest"],
        "coordinate_status": "release_observed",
        "canonical_closure_digest": manifest[
            "canonical_governance_closure_digest"
        ],
        "receipt_schema": manifest["contract_bindings"]["governance_schema"],
    }
    if constellation.get("comparison") != expected_comparison_coordinate:
        raise ValueError(
            "constellation comparison coordinate requires the observed release subject"
        )
    campaign_states = {
        item["campaign_id"]: item["status"]
        for item in machine_node.get("campaigns", [])
    }
    if (
        machine_node.get("lifecycle_state") != "settling"
        or machine_node.get("current_provenance")
        != {
            "release": "comparison-v0.3.2",
            "commit": CURRENT_RELEASE_COORDINATE["commit_oid"],
            "digest": CURRENT_RELEASE_COORDINATE["archive_digest"],
        }
        or machine_node.get("open_receipts") != []
        or first_receipt.get("open_receipts") != []
        or campaign_states.get("LIMS-ELN-OPEN-RECEIPTS") != "active"
    ):
        raise ValueError(
            "observed release requires exact provenance and a closed promotion receipt"
        )
    if datetime.fromisoformat(carrier_observation_time) <= datetime.fromisoformat(
        CURRENT_RELEASE_COORDINATE["promoted_at"].replace("Z", "+00:00")
    ):
        raise ValueError(
            "the promotion observation timestamp follows the current signed release"
        )
    if (
        machine_node.get("metadata", {}).get("updated_at")
        != carrier_observation_time
        or first_receipt.get("as_of") != carrier_observation_time
        or first_receipt.get("metadata", {}).get("updated_at")
        != carrier_observation_time
        or coordination_horizon.get("as_of") != carrier_observation_time
        or coordination_horizon.get("metadata", {}).get("updated_at")
        != carrier_observation_time
    ):
        raise ValueError(
            "control-plane carriers require one later observation timestamp"
        )
    horizon_items = {
        item["item_id"]: item
        for item in coordination_horizon.get("work_items", [])
    }
    publication_sources = [
        item
        for item in first_receipt.get("source_permissions", [])
        if isinstance(item, dict)
        and item.get("source") == publication_source_name
    ]
    publication_item = horizon_items.get("WORK-COMPARATIVE-PUBLICATION-017", {})
    candidate_item = horizon_items.get("WORK-COMPARATIVE-PROMOTION-004", {})
    successor_publication_item = horizon_items.get(
        "WORK-COMPARATIVE-PUBLICATION-031", {}
    )
    living_orientation_item = horizon_items.get(
        "WORK-GOVERNANCE-LIVING-ORIENTATION-038", {}
    )
    program_handoff_item = horizon_items.get(
        "WORK-PROGRAM-CONSTELLATION-HANDOFF-001", {}
    )
    reentry = coordination_horizon.get("reentry_capsule", {})
    handoff = first_receipt.get("handoff", {})
    publication_source = (
        publication_sources[0] if len(publication_sources) == 1 else {}
    )
    source_verification = (
        publication_source.get("verification", "")
    )
    next_action = reentry.get("next_safe_action", "")
    success_evidence = handoff.get("success_evidence", "")
    completion_evidence = (
        successor_publication_item.get("completion_evidence", [])
        if isinstance(successor_publication_item, dict)
        else []
    )
    handoff_completion_evidence = (
        program_handoff_item.get("completion_evidence", [])
        if isinstance(program_handoff_item, dict)
        else []
    )

    def meaningful_text(value: object) -> bool:
        return isinstance(value, str) and len(value.strip()) >= 40

    if (
        coordination_horizon.get("current_item_ids")
        != ["WORK-PROGRAM-CONSTELLATION-HANDOFF-001"]
        or not meaningful_text(coordination_horizon.get("objective"))
        or horizon_items.get("WORK-COMPARATIVE-PROMOTION-003", {}).get(
            "state"
        )
        != "complete"
        or not isinstance(publication_item, dict)
        or publication_item.get("sequence") != 4
        or publication_item.get("state") != "complete"
        or publication_item.get("owner_role")
        != "Comparative evidence publication receiver"
        or publication_item.get("dependency_ids")
        != ["WORK-COMPARATIVE-PROMOTION-003"]
        or not isinstance(candidate_item, dict)
        or candidate_item.get("sequence") != 5
        or candidate_item.get("state") != "complete"
        or candidate_item.get("owner_role")
        != "Comparative evidence release steward"
        or candidate_item.get("dependency_ids")
        != ["WORK-COMPARATIVE-PUBLICATION-017"]
        or not isinstance(successor_publication_item, dict)
        or successor_publication_item.get("sequence") != 6
        or successor_publication_item.get("state") != "complete"
        or successor_publication_item.get("owner_role")
        != "Comparative evidence publication receiver"
        or successor_publication_item.get("dependency_ids")
        != ["WORK-COMPARATIVE-PROMOTION-004"]
        or not isinstance(living_orientation_item, dict)
        or living_orientation_item.get("sequence") != 7
        or living_orientation_item.get("state") != "complete"
        or living_orientation_item.get("owner_role")
        != "Governance conformance reviewer"
        or living_orientation_item.get("dependency_ids")
        != ["WORK-COMPARATIVE-PUBLICATION-031"]
        or not isinstance(program_handoff_item, dict)
        or program_handoff_item.get("sequence") != 8
        or program_handoff_item.get("state") != "ready"
        or program_handoff_item.get("owner_role")
        != "Program specification constellation receiver"
        or program_handoff_item.get("dependency_ids")
        != ["WORK-GOVERNANCE-LIVING-ORIENTATION-038"]
        or len(publication_sources) != 1
        or publication_source.get("permission") != "read"
        or not meaningful_text(source_verification)
        or handoff.get("recipient_role")
        != "Program specification constellation receiver"
        or handoff.get("next_safe_action") != next_action
        or not meaningful_text(next_action)
        or not meaningful_text(reentry.get("current_state"))
        or not meaningful_text(reentry.get("verification"))
        or not meaningful_text(first_receipt.get("current_horizon_summary"))
        or not meaningful_text(success_evidence)
        or not isinstance(completion_evidence, list)
        or len(completion_evidence) < 3
        or any(not meaningful_text(value) for value in completion_evidence)
        or not isinstance(handoff_completion_evidence, list)
        or len(handoff_completion_evidence) < 3
        or any(
            not meaningful_text(value) for value in handoff_completion_evidence
        )
    ):
        raise ValueError(
            "Coordination Horizon routes the published 0.3.2 baseline to Program"
        )
    implementation_golden_path = (
        ROOT / "fixtures/pairs/enterprise-postgresql-observation.json"
    )
    simulation_golden_path = (
        ROOT / "fixtures/pairs/simulation-golden-specimen-observation.json"
    )
    implementation_golden = validate_golden_specimen_observation(
        _load("fixtures/pairs/enterprise-postgresql-observation.json")
    )
    simulation_golden = validate_golden_specimen_observation(
        _load("fixtures/pairs/simulation-golden-specimen-observation.json")
    )
    golden_projection_schema = load_golden_specimen_result_projection_schema()
    for contract_name, observation in (
        ("durable Golden Specimen projection", implementation_golden),
        ("selected-future Golden Specimen projection", simulation_golden),
    ):
        validate_json_contract(
            schema=golden_projection_schema,
            instance=observation["result"]["projection"],
            version_property="projection_version",
            expected_version="1.0.0",
            contract_name=contract_name,
        )
    golden_report = compare_golden_specimen(
        implementation_golden,
        simulation_golden,
        golden_profile,
        constellation,
    )
    if golden_report.get("report_digest") != golden_report_digest:
        raise ValueError(
            "Golden report digest requires the reviewed source-constellation identity"
        )
    golden_replay_report = compare_golden_specimen(
        validate_golden_specimen_observation(
            _load("fixtures/pairs/enterprise-postgresql-observation.json")
        ),
        validate_golden_specimen_observation(
            _load("fixtures/pairs/simulation-golden-specimen-observation.json")
        ),
        _load("specification/golden-specimen-verification-profile.json"),
        _load("constellation.lock.json"),
    )
    report = compare_synthetic_contract(
        ObservationEnvelope.from_dict(simulation_observation),
        ObservationEnvelope.from_dict(planned_observation),
        profile,
    )
    replay_report = compare_synthetic_contract(
        ObservationEnvelope.from_dict(
            _load("fixtures/pairs/simulation-observation.json")
        ),
        ObservationEnvelope.from_dict(
            _load("fixtures/contracts/planned-observation.json")
        ),
        _load("specification/comparison-profile.json"),
    )
    with (
        tempfile.TemporaryDirectory(prefix="comparison-first-") as first_directory,
        tempfile.TemporaryDirectory(prefix="comparison-replay-") as replay_directory,
    ):
        first_path = Path(first_directory)
        replay_path = Path(replay_directory)
        write_reports(report, first_path)
        write_reports(replay_report, replay_path)
        report_artifact_inventory = verify_reproducible_reports(
            first_path,
            replay_path,
        )
    with (
        tempfile.TemporaryDirectory(prefix="golden-first-") as first_directory,
        tempfile.TemporaryDirectory(prefix="golden-replay-") as replay_directory,
    ):
        first_path = Path(first_directory)
        replay_path = Path(replay_directory)
        write_reports(golden_report, first_path)
        write_reports(golden_replay_report, replay_path)
        golden_report_artifact_inventory = verify_reproducible_reports(
            first_path,
            replay_path,
        )
    with (
        tempfile.TemporaryDirectory(prefix="pages-first-") as first_directory,
        tempfile.TemporaryDirectory(prefix="pages-replay-") as replay_directory,
    ):
        first_pages = Path(first_directory) / "site"
        replay_pages = Path(replay_directory) / "site"
        pages_revision = "0" * 40
        pages_source = ValidationFixtureSourceProof(pages_revision)
        build_projection(
            ROOT,
            first_pages,
            source_proof=pages_source,
        )
        build_projection(
            ROOT,
            replay_pages,
            source_proof=pages_source,
        )
        pages_inventory = verify_reproducible_projections(
            first_pages,
            replay_pages,
        )
        if any(
            ".agents" in path.parts or path.name == "AGENTS.md"
            for path in first_pages.rglob("*")
        ):
            raise ValueError(
                "public-possible collaboration skills remain outside Pages"
            )
    if report.get("comparison_mode") != "synthetic_contract" or report.get(
        "authority_posture"
    ) != {
        "evidence_claim": "synthetic_contract_shape_only",
        "environment_observed_closure": "separate_unasserted_state",
        "production_authorization_effect": "none",
    }:
        raise ValueError(
            "reference report requires the released non-authorizing synthetic "
            "contract posture"
        )
    calibration = score_calibration(
        _load("fixtures/calibration/observed-outcomes.json")
    )
    expected = {
        "repository_release": "0.3.2",
        "release_state": "release_observed",
        "external_release": "comparison-v0.3.2",
        "synthetic_contract_report_digest": report["report_digest"],
        "canonical_governance_closure_digest": bundle_summary[
            "governance_closure_digest"
        ],
        "simulated_closure_comparison_digest": bundle_summary[
            "comparison_digest"
        ],
        "aggregate_closure_artifact_digest": bundle_summary[
            "aggregate_artifact_digest"
        ],
        "source_result_digest": bundle_summary["source_result_digest"],
        "comparison_profile_digest": digest(profile),
        "calibration_ledger_digest": calibration["ledger_digest"],
        "canonical_closure_bundle_digest": digest(bundle),
        "canonical_closure_bundle_file_sha256": (
            f"sha256:{sha256(bundle_path.read_bytes()).hexdigest()}"
        ),
        "golden_specimen_verification": {
            "profile_digest": digest(golden_profile),
            "report_digest": golden_report["report_digest"],
            "constellation_lock_digest": digest(constellation),
            "source_constellation_digest": golden_report[
                "source_constellation_digest"
            ],
            "classification_counts": golden_report["summary"][
                "classification_counts"
            ],
            "implementation": {
                "fixture_path": (
                    "fixtures/pairs/enterprise-postgresql-observation.json"
                ),
                "fixture_authority": (
                    "comparative_owned_snapshot_from_accepted_enterprise_source"
                ),
                "file_sha256": (
                    "sha256:"
                    + sha256(implementation_golden_path.read_bytes()).hexdigest()
                ),
                "observation_digest": digest(implementation_golden),
                "projection_digest": digest(
                    implementation_golden["result"]["projection"]
                ),
            },
            "simulation": {
                "fixture_path": (
                    "fixtures/pairs/simulation-golden-specimen-observation.json"
                ),
                "fixture_authority": "accepted_simulation_release_observation",
                "file_sha256": (
                    "sha256:"
                    + sha256(simulation_golden_path.read_bytes()).hexdigest()
                ),
                "observation_digest": digest(simulation_golden),
                "projection_digest": digest(
                    simulation_golden["result"]["projection"]
                ),
            },
        },
    }
    drift = {
        field: {"manifest": manifest.get(field), "derived": value}
        for field, value in expected.items()
        if manifest.get(field) != value
    }
    promotion_binding = manifest.get("promotion_receipt_contract")
    if promotion_binding != expected_promotion_binding:
        drift["promotion_receipt_contract"] = {
            "manifest": promotion_binding,
            "derived": expected_promotion_binding,
        }
    candidate_binding = manifest.get("promotion_candidate_contract")
    if candidate_binding != expected_candidate_binding:
        drift["promotion_candidate_contract"] = {
            "manifest": candidate_binding,
            "derived": expected_candidate_binding,
        }
    observation_binding = manifest.get("promotion_observation_contract")
    if observation_binding != expected_observation_binding:
        drift["promotion_observation_contract"] = {
            "manifest": observation_binding,
            "derived": expected_observation_binding,
        }
    if manifest.get("promotion_coordinates") != expected_promotion_coordinates:
        drift["promotion_coordinates"] = {
            "manifest": manifest.get("promotion_coordinates"),
            "derived": expected_promotion_coordinates,
        }
    if manifest.get("publication_coordinates") != expected_publication_coordinates:
        drift["publication_coordinates"] = {
            "manifest": manifest.get("publication_coordinates"),
            "derived": expected_publication_coordinates,
        }
    prior_publications = [
        item.get("publication_coordinates")
        for item in manifest.get("historical_external_releases", [])
        if isinstance(item, dict)
        and item.get("external_release") == "comparison-v0.3.1"
    ]
    if prior_publications != [PRIOR_PUBLICATION_COORDINATES]:
        drift["historical_0.3.1_publication"] = {
            "manifest": prior_publications,
            "derived": [PRIOR_PUBLICATION_COORDINATES],
        }
    for label, observation_field in (
        ("implementation", "observation_digest"),
        ("simulation", "reference_observation_digest"),
    ):
        expected_fixture = expected["golden_specimen_verification"][label]
        expected_lock = {
            "fixture_path": expected_fixture["fixture_path"],
            "fixture_authority": expected_fixture["fixture_authority"],
            "fixture_file_sha256": expected_fixture["file_sha256"],
            observation_field: expected_fixture["observation_digest"],
            "projection_digest": expected_fixture["projection_digest"],
        }
        observed_lock = {
            field: constellation[label].get(field) for field in expected_lock
        }
        if observed_lock != expected_lock:
            drift[f"constellation.{label}.fixture_binding"] = {
                "lock": observed_lock,
                "derived": expected_lock,
            }
    if (
        manifest.get("trusted_simulated_database_release")
        != TRUSTED_SIMULATED_DATABASE_RELEASE.as_dict()
    ):
        drift["trusted_simulated_database_release"] = {
            "manifest": manifest.get("trusted_simulated_database_release"),
            "derived": TRUSTED_SIMULATED_DATABASE_RELEASE.as_dict(),
        }
    if drift:
        raise ValueError(
            "release manifest differs from derived evidence: "
            + json.dumps(drift, sort_keys=True)
        )
    environment_claims = _persisted_environment_claims()
    if environment_claims:
        raise ValueError(
            "repository fixtures require planned or simulated authority: "
            + ", ".join(environment_claims)
        )
    findings = _repository_secret_shape_findings()
    if findings:
        raise ValueError(
            "repository files require governed credential storage: "
            + ", ".join(findings)
        )
    print(
        json.dumps(
            {
                "status": "passed",
                "json_documents": json_count,
                "comparison_profile_schema": manifest["contract_bindings"][
                    "comparison_profile_schema"
                ],
                "observation_envelope_schema": manifest["contract_bindings"][
                    "observation_envelope_schema"
                ],
                "synthetic_contract_report_digest": report["report_digest"],
                "golden_specimen_verification_report_digest": golden_report[
                    "report_digest"
                ],
                "closure_comparison_digest": bundle_summary[
                    "comparison_digest"
                ],
                "calibration_status": calibration["status"],
                "report_artifact_inventory_digest": digest(
                    report_artifact_inventory
                ),
                "golden_report_artifact_inventory_digest": digest(
                    golden_report_artifact_inventory
                ),
                "pages_projection_inventory_digest": digest(pages_inventory),
                "orientation_readmes": len(ORIENTATION_README_CONTRACTS),
                "collaboration_skills": len(PUBLIC_POSSIBLE_SKILL_METADATA),
                "promotion_receipt_digest": promotion_receipt_digest(
                    promotion_receipt
                ),
                "promotion_candidate_digest": promotion_candidate_digest(
                    promotion_candidate_path
                ),
                "promotion_observation_digest": digest(
                    promotion_observation
                ),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
