# LIMS/ELN Comparative Evidence

This repository independently compares a released specification, a frozen simulated
forecast, and an observed implementation result. It produces machine-readable JSON
and a portable HTML report while preserving the original inputs and their authority.

The comparator treats the simulation as a hypothesis. An actual implementation can
confirm it, reveal an actual gap, expose a simulation fault, improve upon the
forecast, or show that context changed.

## Authority boundary

Evidence enters `accepted/` only through the admission gate. The gate requires:

- `evidence_mode: observed`;
- a named environment and immutable implementation identity;
- a raw-artifact digest and governed locator;
- performer and independent reviewer identities;
- an accountable approval for acceptance-stage records;
- a classification and redaction statement.

Planned and simulated records stay in their source namespaces and remain useful for
comparison. The gate returns them to the comparison workflow with an explicit
replacement path: execute the scenario in the named environment, capture an observed
envelope, and obtain the required review.

Raw vendor exports, sensitive traces, credentials, and regulated records live in
governed evidence storage. Git contains redacted manifests, content digests, and
protected locators.

## Run it

```bash
python -m unittest discover -s tests -v
PYTHONPATH=src python -m comparative_evidence.cli compare \
  --profile specification/comparison-profile.json \
  --simulation fixtures/pairs/simulation-observation.json \
  --actual fixtures/pairs/actual-observation.json \
  --output build/comparison
```

The output contains `comparison.json` and `comparison.html`. Difference values appear
only for paths declared in the released profile's `reportable_paths`. Every other
value becomes a classification and content digest.

Admission uses a separate command:

```bash
PYTHONPATH=src python -m comparative_evidence.cli admit \
  --envelope fixtures/pairs/actual-observation.json \
  --accepted accepted/
```

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
