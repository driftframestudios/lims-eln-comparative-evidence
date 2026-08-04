# LIMS/ELN Comparative Evidence

This repository turns caller-supplied LIMS and ELN evaluation records into a
repeatable factual comparison. It validates each record with JSON Schema, applies a
versioned comparison profile, and emits machine-readable JSON plus a portable HTML
report.

The active implementation has three responsibilities:

1. normalize the shape and provenance of reference and candidate evidence;
2. compare declared paths with exact or numeric-tolerance rules; and
3. preserve limitations, source references, evidence level, environment, and record
   digests in the result.

Vendor selection, regulated acceptance, release authorization, and organizational
accountability remain with the evaluation program and its established systems. This
repository supplies comparison evidence for those processes.

## Evidence model

Every input declares:

- the vendor, product version, scenario, and evaluation environment;
- one evidence level: `documented`, `configured`, `exercised`, or `observed`;
- a data class: `synthetic`, `deidentified`, or `redacted`;
- source references and the observation time;
- a structured result plus explicit limitations.

The checked-in candidate fixture is synthetic and demonstrates the contract. Named
vendor-release conclusions require separately sourced evaluation records. Raw vendor
exports, regulated records, secrets, and sensitive traces stay in their designated
systems; records may use protected or redacted locators.

## Run it

```bash
python -m pip install --editable .
python -m unittest discover -s tests -v
lims-eln-compare compare \
  --profile specification/comparison-profile.json \
  --reference fixtures/reference/golden-specimen.json \
  --candidate fixtures/candidates/labkey-configured-example.json \
  --output build/comparison
```

The output directory contains `comparison.json` and `comparison.html`. Values appear
in clear text only for paths listed in `reportable_paths`; other differing values are
represented by content digests. This supports useful evaluation reports while
keeping the disclosure boundary explicit.

Forecast calibration remains available for planning probabilities whose outcomes
have subsequently been observed:

```bash
lims-eln-compare calibrate \
  --ledger fixtures/calibration/observed-outcomes.json
```

## Comparison semantics

The released profile owns the paths and rules. It provides:

- required measurements;
- exact critical contracts;
- explicit nondeterministic paths;
- numeric tolerances;
- reportable values; and
- direction-aware interpretations such as lower recovery time or higher normalized
  readback.

Reports use four bounded classifications:

- `candidate_advantage`
- `candidate_gap`
- `context_difference`
- `missing_measurement`

Exact data-contract paths keep JSON types distinct, including booleans and numbers.
Evidence records detach from caller-owned mutable objects, strict JSON parsing
rejects duplicate keys and non-finite numbers, and report rendering escapes
caller-supplied text.

## Enterprise framework boundaries

The reference scenario records Flyway Community with UTC timestamp migrations and
`outOfOrder=true`. Cross-service delivery records a transactional outbox implemented
with Debezium Outbox Event Router and idempotent consumers. The comparator evaluates
the resulting evidence; Flyway and Debezium retain their established operational
responsibilities. See
[`docs/migration-and-event-comparison.md`](docs/migration-and-event-comparison.md).

## Repository map

- `src/comparative_evidence/` — schema validation, immutable evidence model,
  comparator, calibration, and reports
- `src/comparative_evidence/schemas/` — packaged Draft 2020-12 contracts
- `specification/comparison-profile.json` — released comparison rules
- `fixtures/` — synthetic reference, candidate, and calibration examples
- `tests/` — data-contract and comparison behavior
- `machine-node.json` — documentary hydration for hybrid collaborators
- `quarantine/legacy-control-plane/` — preserved inactive experiments

Branches follow a GitFlow-like convention (`develop`, `feature/*`, `release/*`, and
`hotfix/*`) through standard repository protections and review. Automation uses the
branch names supplied by Dependabot or Renovate.
