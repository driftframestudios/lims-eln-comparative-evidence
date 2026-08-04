from __future__ import annotations

from dataclasses import dataclass, fields
from collections.abc import Mapping
import re
from types import MappingProxyType
from typing import Any

from .model import digest
from .safety import EvidenceSafetyError, validate_digest


IDENTIFIER_PATTERN = re.compile(r"^[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*$")
SEMVER_PATTERN = re.compile(
    r"^(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)$"
)
RELEASE_PATTERN = re.compile(r"^[a-z0-9]+(?:[.-][a-z0-9]+)*$")
QUALIFIED_RELATION_PATTERN = re.compile(
    r"^[a-z][a-z0-9_]{0,62}\.[a-z][a-z0-9_]{0,62}$"
)
MECHANISM_STRATEGY_PATTERN = re.compile(
    r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$"
)
COORDINATE_FIELDS = {
    "oracle_id",
    "oracle_version",
    "database_release",
    "data_contract_id",
    "data_contract_version",
    "data_contract_digest",
    "migration_manifest_id",
    "migration_manifest_version",
    "migration_manifest_digest",
    "migration_mechanism_id",
    "migration_mechanism_version",
    "migration_mechanism_digest",
    "migration_history_relation",
    "migration_lock_strategy",
    "migration_transaction_strategy",
    "migration_receipt_id",
    "migration_receipt_digest",
    "release_receipt_id",
    "release_receipt_digest",
    "schema_digest",
    "semantic_policy_profile_id",
    "semantic_policy_profile_version",
    "semantic_policy_profile_digest",
    "semantic_policy_coverage",
}

SEMANTIC_POLICY_REQUIREMENTS = {
    "tenant": {
        "policy_id": "DATA-TENANT-001",
        "representation_digest": (
            "sha256:69c64005a1b7c2830c71e66abb88697093139c683f17d249b5d42ff17bab3299"
        ),
        "required_semantics": (
            "tenant_leading_composite_keys",
            "forced_row_level_security",
        ),
    },
    "temporal": {
        "policy_id": "DATA-TIME-001",
        "representation_digest": (
            "sha256:75e9ee7535e924601426f2adb7106afea294fac5904cfe09f76d3aeb17bf4eef"
        ),
        "required_semantics": (
            "occurrence_recording_distinct",
            "timezone_aware_instants",
            "finite_instants",
        ),
    },
    "identity": {
        "policy_id": "DATA-ID-001",
        "representation_digest": (
            "sha256:7985cd19c439751508761383d8211901137fe4feb31bd9e794b4fde7d4b5b680"
        ),
        "required_semantics": (
            "internal_uuid",
            "external_constrained_source_scoped",
        ),
    },
    "digest": {
        "policy_id": "DATA-DIGEST-001",
        "representation_digest": (
            "sha256:74986404c294bf80a96f98390137ef1ab43b6c3fdb6a35d714baed9c5906f653"
        ),
        "required_semantics": (
            "sha256_32_byte",
            "canonicalization_profile",
            "content_scope",
        ),
    },
    "measurement": {
        "policy_id": "DATA-MEASURE-001",
        "representation_digest": (
            "sha256:141e3240521a68ad6c597683eb9fd7f31e0192f7750740c5fac5c30fafeb82df"
        ),
        "required_semantics": (
            "raw_numeric_lexeme",
            "raw_value",
            "canonical_value",
            "assay_method_numeric_profile",
            "qualifier_reference_and_detection_limits",
        ),
    },
    "unit": {
        "policy_id": "DATA-UNIT-001",
        "representation_digest": (
            "sha256:eb4746bcb3f62453ff9eef406e5805860850c0c770df975953beb458e73fdc7b"
        ),
        "required_semantics": (
            "source_unit",
            "canonical_ucum",
            "vocabulary_version",
            "mapping_revision",
            "conversion_and_rounding_provenance",
        ),
    },
}


def _released_semantic_policy_coverage() -> dict[str, dict[str, Any]]:
    return {
        dimension: {
            "policy_id": binding["policy_id"],
            "representation_digest": binding["representation_digest"],
            "required_semantics": list(binding["required_semantics"]),
        }
        for dimension, binding in SEMANTIC_POLICY_REQUIREMENTS.items()
    }


TRUSTED_SEMANTIC_POLICY_PROFILE_ID = "PROFILE-DATABASE-SEMANTICS-002"
TRUSTED_SEMANTIC_POLICY_PROFILE_VERSION = "2.0.0"
TRUSTED_SEMANTIC_POLICY_PROFILE_DIGEST = digest(
    {
        "semantic_policy_profile_id": TRUSTED_SEMANTIC_POLICY_PROFILE_ID,
        "semantic_policy_profile_version": TRUSTED_SEMANTIC_POLICY_PROFILE_VERSION,
        "semantic_policy_coverage": _released_semantic_policy_coverage(),
    }
)


class DatabaseReleaseError(ValueError):
    """A database release coordinate receives a precise completion path."""


@dataclass(frozen=True)
class DatabaseReleaseCoordinate:
    oracle_id: str
    oracle_version: str
    database_release: str
    data_contract_id: str
    data_contract_version: str
    data_contract_digest: str
    migration_manifest_id: str
    migration_manifest_version: str
    migration_manifest_digest: str
    migration_mechanism_id: str
    migration_mechanism_version: str
    migration_mechanism_digest: str
    migration_history_relation: str
    migration_lock_strategy: str
    migration_transaction_strategy: str
    migration_receipt_id: str
    migration_receipt_digest: str
    release_receipt_id: str
    release_receipt_digest: str
    schema_digest: str
    semantic_policy_profile_id: str
    semantic_policy_profile_version: str
    semantic_policy_profile_digest: str
    semantic_policy_coverage: Mapping[str, Mapping[str, Any]]

    def __post_init__(self) -> None:
        frozen_coverage = MappingProxyType(
            {
                dimension: MappingProxyType(
                    {
                        "policy_id": binding["policy_id"],
                        "representation_digest": binding[
                            "representation_digest"
                        ],
                        "required_semantics": tuple(
                            binding["required_semantics"]
                        ),
                    }
                )
                for dimension, binding in self.semantic_policy_coverage.items()
            }
        )
        object.__setattr__(self, "semantic_policy_coverage", frozen_coverage)

    def as_dict(self) -> dict[str, Any]:
        value = {
            field.name: getattr(self, field.name)
            for field in fields(self)
            if field.name != "semantic_policy_coverage"
        }
        value["semantic_policy_coverage"] = {
            dimension: {
                "policy_id": binding["policy_id"],
                "representation_digest": binding["representation_digest"],
                "required_semantics": list(binding["required_semantics"]),
            }
            for dimension, binding in self.semantic_policy_coverage.items()
        }
        return value


TRUSTED_SIMULATED_DATABASE_RELEASE = DatabaseReleaseCoordinate(
    oracle_id="ORACLE-DATABASE-FINAL-STATE-002",
    oracle_version="2.0.0",
    database_release="database-final-state-v2",
    data_contract_id="CONTRACT-LABORATORY-CORE-002",
    data_contract_version="2.0.0",
    data_contract_digest=(
        "sha256:9b88582b00ba65f96f8feddc42ab2da6a569d22e85ca8220b50494689c13f691"
    ),
    migration_manifest_id="MANIFEST-DATABASE-MIGRATION-002",
    migration_manifest_version="2.0.0",
    migration_manifest_digest=(
        "sha256:804195a301d3509965555c057d4dc3b5fca6c5b043ab31455e7102330b0322f2"
    ),
    migration_mechanism_id="FLYWAY",
    migration_mechanism_version="13.0.0",
    migration_mechanism_digest=(
        "sha256:031722729a3c47c61bc7a22db507975dfaa9c31138815977f82adb408b60563e"
    ),
    migration_history_relation="public.flyway_schema_history",
    migration_lock_strategy="flyway_postgresql_history_lock",
    migration_transaction_strategy="one_transaction_per_migration",
    migration_receipt_id="RECEIPT-DATABASE-MIGRATION-SIM-002",
    migration_receipt_digest=(
        "sha256:c22c64d9aa03f1a31dcc88c764b46df7850597d09b35c445c7ce63532c854564"
    ),
    release_receipt_id="RECEIPT-DATABASE-RELEASE-SIM-002",
    release_receipt_digest=(
        "sha256:d8b4db48094584f926c391e04365c27db4ecbad96b95bbd43418a0304eb23d12"
    ),
    schema_digest=(
        "sha256:1f9f23687a349876079f21063b9904b275933519eb442936056e780fa07101bd"
    ),
    semantic_policy_profile_id=TRUSTED_SEMANTIC_POLICY_PROFILE_ID,
    semantic_policy_profile_version=TRUSTED_SEMANTIC_POLICY_PROFILE_VERSION,
    semantic_policy_profile_digest=TRUSTED_SEMANTIC_POLICY_PROFILE_DIGEST,
    semantic_policy_coverage=_released_semantic_policy_coverage(),
)


def validate_database_release_coordinate(
    value: Any,
    *,
    label: str = "database_release",
) -> DatabaseReleaseCoordinate:
    if not isinstance(value, Mapping) or set(value) != COORDINATE_FIELDS:
        raise DatabaseReleaseError(
            f"{label} requires the released database coordinate fields"
        )
    for field in (
        "oracle_id",
        "data_contract_id",
        "migration_manifest_id",
        "migration_mechanism_id",
        "migration_receipt_id",
        "release_receipt_id",
        "semantic_policy_profile_id",
    ):
        item = value[field]
        if not isinstance(item, str) or IDENTIFIER_PATTERN.fullmatch(item) is None:
            raise DatabaseReleaseError(
                f"{label}.{field} requires an uppercase governed identity"
            )
    for field in (
        "oracle_version",
        "data_contract_version",
        "migration_manifest_version",
        "migration_mechanism_version",
        "semantic_policy_profile_version",
    ):
        item = value[field]
        if not isinstance(item, str) or SEMVER_PATTERN.fullmatch(item) is None:
            raise DatabaseReleaseError(
                f"{label}.{field} requires semantic versioning"
            )
    database_release = value["database_release"]
    if (
        not isinstance(database_release, str)
        or RELEASE_PATTERN.fullmatch(database_release) is None
    ):
        raise DatabaseReleaseError(
            f"{label}.database_release requires a bounded release identity"
        )
    for field in (
        "data_contract_digest",
        "migration_manifest_digest",
        "migration_mechanism_digest",
        "migration_receipt_digest",
        "release_receipt_digest",
        "schema_digest",
        "semantic_policy_profile_digest",
    ):
        try:
            validate_digest(value[field], f"{label}.{field}")
        except EvidenceSafetyError as error:
            raise DatabaseReleaseError(str(error)) from error
    history_relation = value["migration_history_relation"]
    if (
        not isinstance(history_relation, str)
        or QUALIFIED_RELATION_PATTERN.fullmatch(history_relation) is None
    ):
        raise DatabaseReleaseError(
            f"{label}.migration_history_relation requires one qualified PostgreSQL relation"
        )
    for field in ("migration_lock_strategy", "migration_transaction_strategy"):
        strategy = value[field]
        if (
            not isinstance(strategy, str)
            or len(strategy) > 96
            or MECHANISM_STRATEGY_PATTERN.fullmatch(strategy) is None
        ):
            raise DatabaseReleaseError(
                f"{label}.{field} requires one bounded machine-readable strategy"
            )
    coverage = value["semantic_policy_coverage"]
    if not isinstance(coverage, Mapping) or set(coverage) != set(
        SEMANTIC_POLICY_REQUIREMENTS
    ):
        raise DatabaseReleaseError(
            f"{label}.semantic_policy_coverage requires tenant, temporal, identity, "
            "digest, measurement, and unit policy dimensions"
        )
    normalized_coverage: dict[str, dict[str, Any]] = {}
    for dimension, requirement in SEMANTIC_POLICY_REQUIREMENTS.items():
        binding = coverage[dimension]
        if not isinstance(binding, Mapping) or set(binding) != {
            "policy_id",
            "representation_digest",
            "required_semantics",
        }:
            raise DatabaseReleaseError(
                f"{label}.semantic_policy_coverage.{dimension} requires the released binding fields"
            )
        if binding["policy_id"] != requirement["policy_id"]:
            raise DatabaseReleaseError(
                f"{label}.semantic_policy_coverage.{dimension}.policy_id requires "
                f"{requirement['policy_id']}"
            )
        try:
            validate_digest(
                binding["representation_digest"],
                f"{label}.semantic_policy_coverage.{dimension}.representation_digest",
            )
        except EvidenceSafetyError as error:
            raise DatabaseReleaseError(str(error)) from error
        required_semantics = binding["required_semantics"]
        if (
            not isinstance(required_semantics, (list, tuple))
            or list(required_semantics) != list(requirement["required_semantics"])
        ):
            raise DatabaseReleaseError(
                f"{label}.semantic_policy_coverage.{dimension}.required_semantics "
                "requires the released semantic capabilities"
            )
        normalized_coverage[dimension] = {
            "policy_id": binding["policy_id"],
            "representation_digest": binding["representation_digest"],
            "required_semantics": list(required_semantics),
        }
    expected_profile_digest = digest(
        {
            "semantic_policy_profile_id": value["semantic_policy_profile_id"],
            "semantic_policy_profile_version": value[
                "semantic_policy_profile_version"
            ],
            "semantic_policy_coverage": normalized_coverage,
        }
    )
    if value["semantic_policy_profile_digest"] != expected_profile_digest:
        raise DatabaseReleaseError(
            f"{label}.semantic_policy_profile_digest requires the canonical semantic policy profile digest"
        )
    normalized = {field: value[field] for field in COORDINATE_FIELDS}
    normalized["semantic_policy_coverage"] = normalized_coverage
    return DatabaseReleaseCoordinate(**normalized)


def database_release_alignment(
    simulation: DatabaseReleaseCoordinate,
    actual: DatabaseReleaseCoordinate,
    *,
    counterpart_receipts_key: str = "observed_receipts",
) -> dict[str, Any]:
    """Return a receipt-aware view of target-database alignment."""

    if counterpart_receipts_key not in {
        "observed_receipts",
        "planned_receipt_shapes",
    }:
        raise DatabaseReleaseError(
            "counterpart receipt label requires a released comparison mode"
        )

    alignment = {
        "oracle_aligned": (
            simulation.oracle_id,
            simulation.oracle_version,
            simulation.database_release,
        )
        == (
            actual.oracle_id,
            actual.oracle_version,
            actual.database_release,
        ),
        "data_contract_aligned": (
            simulation.data_contract_id,
            simulation.data_contract_version,
            simulation.data_contract_digest,
        )
        == (
            actual.data_contract_id,
            actual.data_contract_version,
            actual.data_contract_digest,
        ),
        "migration_manifest_aligned": (
            simulation.migration_manifest_id,
            simulation.migration_manifest_version,
            simulation.migration_manifest_digest,
        )
        == (
            actual.migration_manifest_id,
            actual.migration_manifest_version,
            actual.migration_manifest_digest,
        ),
        "migration_implementation_aligned": (
            simulation.migration_mechanism_id,
            simulation.migration_mechanism_version,
            simulation.migration_mechanism_digest,
        )
        == (
            actual.migration_mechanism_id,
            actual.migration_mechanism_version,
            actual.migration_mechanism_digest,
        ),
        "migration_history_aligned": (
            simulation.migration_history_relation
            == actual.migration_history_relation
        ),
        "migration_execution_aligned": (
            simulation.migration_lock_strategy,
            simulation.migration_transaction_strategy,
        )
        == (
            actual.migration_lock_strategy,
            actual.migration_transaction_strategy,
        ),
        "schema_aligned": simulation.schema_digest == actual.schema_digest,
        "semantic_policy_profile_aligned": (
            simulation.semantic_policy_profile_id,
            simulation.semantic_policy_profile_version,
            simulation.semantic_policy_profile_digest,
        )
        == (
            actual.semantic_policy_profile_id,
            actual.semantic_policy_profile_version,
            actual.semantic_policy_profile_digest,
        ),
        "semantic_policy_alignment": {
            dimension: simulation.semantic_policy_coverage[dimension]
            == actual.semantic_policy_coverage[dimension]
            for dimension in SEMANTIC_POLICY_REQUIREMENTS
        },
        "simulated_receipts": {
            "migration_receipt_id": simulation.migration_receipt_id,
            "migration_receipt_digest": simulation.migration_receipt_digest,
            "release_receipt_id": simulation.release_receipt_id,
            "release_receipt_digest": simulation.release_receipt_digest,
        },
        counterpart_receipts_key: {
            "migration_receipt_id": actual.migration_receipt_id,
            "migration_receipt_digest": actual.migration_receipt_digest,
            "release_receipt_id": actual.release_receipt_id,
            "release_receipt_digest": actual.release_receipt_digest,
        },
    }
    alignment["migration_mechanism_aligned"] = all(
        alignment[field]
        for field in (
            "migration_implementation_aligned",
            "migration_history_aligned",
            "migration_execution_aligned",
        )
    )
    alignment["semantic_policy_aligned"] = (
        alignment["semantic_policy_profile_aligned"]
        and all(alignment["semantic_policy_alignment"].values())
    )
    alignment["target_state_aligned"] = all(
        alignment[field]
        for field in (
            "oracle_aligned",
            "data_contract_aligned",
            "schema_aligned",
            "semantic_policy_aligned",
        )
    )
    alignment["release_path_aligned"] = all(
        alignment[field]
        for field in (
            "migration_manifest_aligned",
            "migration_mechanism_aligned",
        )
    )
    if alignment["target_state_aligned"] and alignment["release_path_aligned"]:
        alignment["target_status"] = "aligned_target"
    elif alignment["target_state_aligned"]:
        alignment["target_status"] = "aligned_target_distinct_release_path"
    else:
        alignment["target_status"] = "target_divergence"
    alignment["alignment_digest"] = digest(alignment)
    return alignment
