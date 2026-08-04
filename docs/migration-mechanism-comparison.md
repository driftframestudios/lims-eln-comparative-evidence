# Migration mechanism comparison boundary

## Decision

Database release coordinates carry two independently reviewable axes:

1. **Target state** binds the selected oracle, semantic data contract, and schema
   digest.
2. **Release path** binds the migration manifest plus the mechanism identity,
   version, implementation digest, history relation, lock strategy, and transaction
   strategy.

This structure allows a reviewer to recognize a shared destination while preserving
the operationally material route used to reach it. The report status
`aligned_target_distinct_release_path` means the target-state coordinate agrees and
the release path receives an explicit architecture disposition.

## Current candidate comparison

| Coordinate | Selected-future projection | Enterprise implementation |
| --- | --- | --- |
| Mechanism | Flyway Community 13.0.0 | Flyway Community 13.0.0 |
| Implementation binding | Selected-future tool artifact digest | Promoted Flyway artifact digest |
| History relation | `public.flyway_schema_history` | `public.flyway_schema_history` |
| Lock strategy | Flyway PostgreSQL history lock | Flyway PostgreSQL history lock |
| Transaction strategy | One transaction per migration | One transaction per migration |
| Manifest identity | `MANIFEST-DATABASE-MIGRATION-001` | `IMPLEMENTATION-DATABASE-MIGRATIONS-001` |

The selected-future values come from its database oracle and program migration
contract. The observed exemplar values come from the enterprise implementation's
Flyway output, reviewed migration set, schema history, and release receipt. A shared
mechanism can lead to distinct release paths because each path retains its own
manifest, environment, and accountable evidence.

## Admission and comparison rules

- Every observation supplies the complete database-release coordinate.
- Governed identities and semantic versions use bounded machine-readable forms.
- Mechanism and manifest digests preserve immutable implementation provenance.
- The history relation names one schema-qualified PostgreSQL relation.
- Lock and transaction strategies use bounded vocabulary values that support exact
  comparison.
- Receipt identities remain evidence coordinates and stay outside target-state
  equality.
- `aligned_target` requires agreement across target state and release path.
- `aligned_target_distinct_release_path` requires target-state agreement and records
  a distinct manifest or mechanism.
- `target_divergence` records a difference in oracle, data contract, or schema.

## Settled ownership boundary

The program contract remains mechanism-neutral while its current implementation
profile selects Flyway Community 13.0.0 for repository-owned PostgreSQL schema
evolution. Flyway owns ordered application, schema history, checksums, deployment
serialization, and transactional execution. Repository SQL and tests own domain
types, constraints, tenant boundaries, scientific lineage, and upgrade preconditions.

Vendor-owned LIMS and ELN databases continue through vendor-supported upgrades and
APIs. Cross-platform data movement uses qualified exports, APIs, native database
transport where appropriate, and checkpointed semantic reconciliation. Those paths
produce their own receipts and remain separate from Flyway schema history.

Promotion evidence binds the exact Flyway version and artifact digest, reviewed
migration files, `info` and `validate` output, schema fingerprint, and environment
receipt. Distinct manifests therefore remain visible even when the tool mechanism
aligns.
