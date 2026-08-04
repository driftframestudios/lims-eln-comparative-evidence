from __future__ import annotations

from dataclasses import asdict, dataclass
from collections.abc import Mapping
import re
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
}


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

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


TRUSTED_SIMULATED_DATABASE_RELEASE = DatabaseReleaseCoordinate(
    oracle_id="ORACLE-DATABASE-FINAL-STATE-001",
    oracle_version="1.0.0",
    database_release="database-final-state-v1",
    data_contract_id="CONTRACT-LABORATORY-CORE-001",
    data_contract_version="1.0.0",
    data_contract_digest=(
        "sha256:2fdaf4b5732426f68a9125ef568f0349f817b627dc4b91306e3bd6f8b22b33f0"
    ),
    migration_manifest_id="MANIFEST-DATABASE-MIGRATION-001",
    migration_manifest_version="1.0.0",
    migration_manifest_digest=(
        "sha256:0fe882e1b11fdc0ee07c5a59313dd778cc18124ffc49ec8b145216bcb97bebb8"
    ),
    migration_mechanism_id="ALEMBIC",
    migration_mechanism_version="1.16.5",
    migration_mechanism_digest=(
        "sha256:2222222222222222222222222222222222222222222222222222222222222222"
    ),
    migration_history_relation="program_control.alembic_version",
    migration_lock_strategy="postgresql_advisory_lock",
    migration_transaction_strategy="phase_declared_transaction_boundaries",
    migration_receipt_id="RECEIPT-DATABASE-MIGRATION-SIM-001",
    migration_receipt_digest=(
        "sha256:2e830735b7798a9fc9e6aeb3b8021dacadd0d34a320d35e22042db1d5489a879"
    ),
    release_receipt_id="RECEIPT-DATABASE-RELEASE-SIM-001",
    release_receipt_digest=(
        "sha256:b3ed89e363468e91e6105274ffedf4f4dac3820a4b39d6846fc0e3f8cabc7b0c"
    ),
    schema_digest=(
        "sha256:5555555555555555555555555555555555555555555555555555555555555555"
    ),
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
    return DatabaseReleaseCoordinate(**{field: value[field] for field in COORDINATE_FIELDS})


def database_release_alignment(
    simulation: DatabaseReleaseCoordinate,
    actual: DatabaseReleaseCoordinate,
) -> dict[str, Any]:
    """Return a receipt-aware view of target-database alignment."""

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
        "simulated_receipts": {
            "migration_receipt_id": simulation.migration_receipt_id,
            "migration_receipt_digest": simulation.migration_receipt_digest,
            "release_receipt_id": simulation.release_receipt_id,
            "release_receipt_digest": simulation.release_receipt_digest,
        },
        "observed_receipts": {
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
    alignment["target_state_aligned"] = all(
        alignment[field]
        for field in (
            "oracle_aligned",
            "data_contract_aligned",
            "schema_aligned",
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
