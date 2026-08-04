from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
import sys

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from comparative_evidence.calibration import score_calibration
from comparative_evidence.compare import compare
from comparative_evidence.database_release import (
    TRUSTED_SIMULATED_DATABASE_RELEASE,
)
from comparative_evidence.model import ObservationEnvelope, digest, strict_json_loads
from comparative_evidence.simulated_closure import validate_simulated_closure_bundle
from check_artifacts import PATTERNS


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
    profile = _load("specification/comparison-profile.json")
    profile_schema = _load("schemas/comparison-profile.schema.json")
    validate_json_contract(
        schema=profile_schema,
        instance=profile,
        version_property="profile_version",
        expected_version=manifest["contract_bindings"][
            "comparison_profile_schema"
        ],
        contract_name="comparison profile",
    )
    report = compare(
        ObservationEnvelope.from_dict(
            _load("fixtures/pairs/simulation-observation.json")
        ),
        ObservationEnvelope.from_dict(
            _load("fixtures/pairs/actual-observation.json")
        ),
        profile,
    )
    calibration = score_calibration(
        _load("fixtures/calibration/observed-outcomes.json")
    )
    expected = {
        "reference_report_digest": report["report_digest"],
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
    }
    drift = {
        field: {"manifest": manifest.get(field), "derived": value}
        for field, value in expected.items()
        if manifest.get(field) != value
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
                "comparison_report_digest": report["report_digest"],
                "closure_comparison_digest": bundle_summary[
                    "comparison_digest"
                ],
                "calibration_status": calibration["status"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
