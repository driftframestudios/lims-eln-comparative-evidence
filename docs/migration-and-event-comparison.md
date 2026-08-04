# Migration and event evidence boundary

The comparison scenario records database and event-delivery outcomes that materially
affect a LIMS or ELN evaluation. Established frameworks retain the underlying
mechanics.

## Database migrations

Flyway Community owns migration discovery, ordering, schema history, checksum
validation, locking, execution, and repair. The scenario compares the configured
tool, UTC timestamp versioning, `outOfOrder` behavior, clean installation, populated
upgrade, and converged catalog result. Evaluation environments provide those values
from Flyway output and database inspection.

## Cross-service event delivery

The application writes a domain event to an outbox row in the same transaction as
the business change. Debezium Outbox Event Router publishes committed events, and
consumers apply idempotency at their own boundary. The scenario compares framework
identity, atomic outbox behavior, consumer idempotency, and measured publication
lag.

The repository compares supplied facts. Connector deployment, broker operation,
dead-letter handling, alerting, and replay use the selected platform's established
operational tooling.
