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
        "sha256:8c50463132809dbcf4bcfee1a1fda94d3c74de532387c13fc68f09603f5f1684"
    ),
    migration_manifest_id="MANIFEST-DATABASE-MIGRATION-001",
    migration_manifest_version="1.0.0",
    migration_manifest_digest=(
        "sha256:e77fc009d4c7c5da2adc670ba54b699b21f2a2edce5e8c5841c2ff33ea914098"
    ),
    migration_mechanism_id="FLYWAY",
    migration_mechanism_version="13.0.0",
    migration_mechanism_digest=(
        "sha256:f3c8433401abf859ef9022584c8e6111684363ec490f737e749e9a4705ea32d0"
    ),
    migration_history_relation="public.flyway_schema_history",
    migration_lock_strategy="flyway_postgresql_history_lock",
    migration_transaction_strategy="one_transaction_per_migration",
    migration_receipt_id="RECEIPT-DATABASE-MIGRATION-SIM-001",
    migration_receipt_digest=(
        "sha256:bb48765cc0cabf23fa9d78e365f751cc005c441471370c862c2cc4442a840c24"
    ),
    release_receipt_id="RECEIPT-DATABASE-RELEASE-SIM-001",
    release_receipt_digest=(
        "sha256:2a5ae9db07b7f36bf82878e36d38e795ec81773cf551e22408c947b038d13346"
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
