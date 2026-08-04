# LIMS/ELN Comparative Evidence

This repository independently compares a released specification, a frozen selected
future, and—when useful—an observed implementation result. It produces
machine-readable JSON and a portable HTML report while preserving the original
inputs and their authority.

The selected future is definitive within its declared simulation reality. An
environment encounter is a separate evidence mode that can confirm it, reveal an
actual gap, expose a simulation fault, improve upon the forecast, or show that
context changed.

## Evidence namespaces

`simulated-closures/` receives a bundle after the comparator confirms:

- the exact governance 2.0.1 closure document matches its release-bound digest;
- the closure bundle's source-result digest independently reproduces the
  aggregate artifact digest;
- all four governance receipt projections and detailed executable receipts are
  present exactly once in the same future reality;
- every projected artifact digest resolves to its detailed receipt;
- the aggregate artifact binds the evidence basis and ordered family digests;
- configured vendor, migration and restore, security and observability, and
  Scientific/Quality/Regulatory criteria passed;
- distinct simulated accountable roles share one acceptance basis.

This path records `closed_in_simulation`, keeps environment-observed closure in
`separate_unasserted_state`, and grants `production_authorization_effect: none`.
It closes the receipts inside the selected future using simulated accountable roles
and declared reference-environment coordinates; external environment encounters and
personal identities remain in `separate_unasserted_state`.

Evidence enters `accepted/` only through the admission gate. The gate requires:

- `evidence_mode: observed`;
- a named environment and immutable implementation identity;
- a typed database-release coordinate binding the target data contract, migration
  manifest, mechanism identity and execution semantics, observed migration and
  release receipts, and resulting schema digest;
- a raw-artifact digest and governed locator;
- performer and independent reviewer identities;
- an accountable approval for acceptance-stage records;
- a classification and redaction statement.

Observed records retain their independent admission path. Their presence extends the
comparative surface and does not determine whether a selected future is complete.

Raw vendor exports, sensitive traces, credentials, and regulated records live in
governed evidence storage. Git contains redacted manifests, content digests, and
protected locators.

Receipt-family vocabulary is owned by program specification contract
`RECEIPT-VOCABULARY-MAP-001` in
`driftframestudios/lims-eln-program-specification` at repository path
`specifications/receipt-vocabulary-map.v1.json`. Comparator schemas and redacted
manifests use its four canonical governance-family values directly. The release
manifest records this external repository coordinate, digest, and promotion state.

## Run it

```bash
python -m pip install --editable ".[validation]"
python -m unittest discover -s tests -v
PYTHONPATH=src python -m comparative_evidence.cli compare \
  --profile specification/comparison-profile.json \
  --simulation fixtures/pairs/simulation-observation.json \
  --actual fixtures/pairs/actual-observation.json \
  --output build/comparison
```

The validation extra executes the released Draft 2020-12 comparison-profile and
observation-envelope contracts during both the test matrix and the aggregate
repository gate.

The output contains `comparison.json` and `comparison.html`. Difference values appear
only for paths declared in the released profile's `reportable_paths`. Every other
value becomes a classification and content digest.

Observation envelopes detach and recursively freeze all nested input content. JSON
serialization returns a fresh mutable projection, preserving the envelope digest
across caller activity. Comparison applies JSON primitive semantics: booleans remain
distinct from numbers, and numeric tolerances apply exclusively to finite numeric
values. Each report also records both database-release coordinates and states whether
their oracle, data contract, migration manifest, migration mechanism, history
relation, lock strategy, transaction strategy, and target schema align. Target-state
alignment and release-path alignment remain separate machine-readable judgments, so
equivalent schemas reached through distinct migration systems retain visible
provenance. Simulated and observed receipt identities remain separate evidence
coordinates. [`docs/migration-mechanism-comparison.md`](docs/migration-mechanism-comparison.md)
defines this comparison boundary and its residual architecture decision.

The released profile also declares every required comparison path and the preferred
direction for recovery time and manual effort. A missing governed path becomes a
shared-specification violation; a faster or lower-effort observed result can be
recognized as a favorable divergence.

Admission uses a separate command:

```bash
PYTHONPATH=src python -m comparative_evidence.cli admit \
  --envelope fixtures/pairs/actual-observation.json \
  --accepted accepted/
```

Selected-future closure uses:

```bash
PYTHONPATH=src python -m comparative_evidence.cli admit-simulated \
  --closure-bundle fixtures/simulated-closures/future-reality-2028-06-30-v1.json \
  --accepted simulated-closures/
```

Forecast calibration starts with an honest empty ledger and activates only when an
independently observed outcome carries immutable resolution evidence:

```bash
PYTHONPATH=src python -m comparative_evidence.cli calibrate \
  --ledger fixtures/calibration/observed-outcomes.json
```

The resulting Brier score ranges from zero to one, with lower values indicating
closer probabilistic fit. Simulated results remain available for comparison and stay
outside the observed calibration ledger.

The stable `comparative-validation` workflow gate recomputes the canonical closure,
reference report, profile, calibration posture, JSON integrity, and repository-wide
credential-shape scan after the complete Python test matrix succeeds.

## Coordination Horizon

[`COORDINATION-HORIZON.json`](COORDINATION-HORIZON.json) describes current focus,
completion evidence, retained effects, and the re-entry path in a
planning-vocabulary-neutral form. [`machine-node.json`](machine-node.json) and
[`first-receipt.json`](first-receipt.json) provide governance-2.0.1-conformant,
orientation-only entry surfaces; neither artifact authorizes runtime effects.

## Comparative literacy

Every difference receives one of these classifications:

- `converged`
- `desired_divergence`
- `actual_gap`
- `actual_defect`
- `simulation_fault`
- `shared_specification_violation`
- `context_changed`
- `receipt_pending`
- `comparison_inconclusive`

Critical scientific, tenant-security, audit, signature, migration, and restore
invariants use exact comparison. Approved performance fields use declared tolerances.
The report retains every judgment rule so a reviewer can challenge the adjudication.

## GitFlow-like branches

- `main`: released comparator and accepted redacted receipt manifests;
- `develop`: integration for the next comparator release;
- `feature/*`: bounded comparison rules, normalizers, or report changes;
- `release/*`: frozen fixtures, schemas, and release hardening;
- `hotfix/*`: correction of a released comparator defect, followed by reconciliation
  into `develop`.

Fixture, oracle, critical-path, tolerance, and admission changes receive independent
review. Release tags use `comparison-vMAJOR.MINOR.PATCH`.
