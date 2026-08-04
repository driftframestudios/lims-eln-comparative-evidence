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
| Mechanism | Alembic 1.16.5 | Manifest-authenticated psql 1.0.0 |
| Implementation binding | Selected-future tool implementation digest | Released runner SHA-256 digest |
| History relation | `program_control.alembic_version` | `laboratory_migration.applied_migration` |
| Lock strategy | PostgreSQL advisory lock | PostgreSQL transaction-level advisory lock |
| Transaction strategy | Phase-declared transaction boundaries | One transaction per migration |
| Manifest identity | `MANIFEST-DATABASE-MIGRATION-001` | `IMPLEMENTATION-DATABASE-MIGRATIONS-001` |

The selected-future values come from its database oracle and program migration
contract. The observed exemplar values come from the enterprise implementation's
released manifest, runner binding, applied-history definition, and transaction
contract.

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

## Residual architecture decision

The program can settle one of three coherent release postures:

1. project the Alembic revision graph into the enterprise implementation;
2. advance the program contract to a mechanism-neutral interface that binds the
   same history, checksum, lock, transaction, recovery, and rehearsal semantics; or
3. qualify both mechanisms as distinct release paths to one data contract and require
   path-specific receipts.

The comparison contract records current evidence while that choice remains open.
Promotion evidence should name the selected posture and bind its exact mechanism
coordinate.
