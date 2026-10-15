# Accepted observed-evidence namespace

## Reader job

Use this namespace when a qualified workflow needs to admit one observed,
provenance-complete evidence envelope for later comparison.

## Current state

The checked-in namespace contains guidance only. Admission tests write accepted
envelopes to temporary directories, and a generated manifest enters source
control after its evidence owner approves a reviewed, redacted form.

## Owner and schema

The observed-evidence steward owns admission. The
[`admit` command](../src/comparative_evidence/cli.py) applies the gate in
[`gate.py`](../src/comparative_evidence/gate.py) to an envelope governed by
[`observation-envelope.schema.json`](../schemas/observation-envelope.schema.json).
The source envelope retains its implementation, environment, provenance,
review, classification, and raw-artifact identities.

## Use

Supply a governed observed envelope and an explicit destination:

```bash
PYTHONPATH=src python3 -m comparative_evidence.cli admit \
  --envelope "${OBSERVED_ENVELOPE}" \
  --accepted accepted/
```

Each admitted manifest carries the raw-artifact digest, protected locator,
independent reviewer, classification, and redaction disposition. Raw artifact
bytes remain with their governed evidence owner.

Acceptance-stage envelopes carry one accepting decision for each Scientific,
Quality, and Regulatory domain. Their normalized approver identities are
distinct from one another, the performer, and the reviewer. Other domains and
non-accepting decisions retain their recorded context. The gate checks these
associations in one pass over the bounded approval collection before publication.

Generated manifests become visible after their complete bytes are verified.
An identical generated-byte replay returns the accepted path; changed bytes
require the namespace's new-identity route. Follow the
[artifact publication guide](../docs/artifact-publication.md) when an interrupted
run or an occupied entry needs recovery.

## Quickest fitting command

From the repository root, exercise the admission boundary:

```bash
python3 -m unittest \
  tests.test_comparative_evidence.ComparativeEvidenceTests.test_observed_qualified_evidence_enters_accepted_namespace \
  -v
```

The focused test establishes that the gate admits the required evidence mode
and rejects a mismatched posture inside its temporary test boundary.

## Evidence ceiling

A file in this namespace records a qualified admission at its named source and
review coordinates. Its presence extends the comparison surface while the
accountable acceptance record and governed raw evidence retain their own
authority. The current empty namespace establishes no environment claim.

## Next route

- Review source-control-safe receipt projection in
  [`../receipts/redacted/README.md`](../receipts/redacted/README.md).
- Compare a qualified observed envelope through the root
  [observed comparison route](../README.md#run-it).
- Inspect release and evidence posture in
  [`../release/repository-role.json`](../release/repository-role.json).

## Return to repository root

[Return to Comparative Evidence orientation](../README.md).
