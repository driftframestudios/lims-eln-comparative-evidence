# Redacted receipt manifests

## Reader job

Use this namespace to inspect or prepare a reviewed receipt manifest whose
classification and redaction posture is suitable for source control.

## Current state

The accepted 0.3.2 release contains guidance only and makes no persisted
environment-evidence claim here. Tests construct a synthetic observed receipt
inside their temporary boundary to exercise the schema and canonical receipt
family vocabulary.

## Owner and schema

The evidence owner and independent redaction reviewer own each manifest's
source-control disposition. The contract is
[`redacted-receipt.schema.json`](../../schemas/redacted-receipt.schema.json),
and [`safety.py`](../../src/comparative_evidence/safety.py) enforces the
classification and reviewed-redaction vocabulary used during admission.

## Use

A reviewed manifest identifies the claim, exact environment and implementation,
scenario, observed result, raw-artifact digest, governed locator, limitations,
performer, reviewer, accountable approver where applicable, and retest triggers.
Sensitive values travel as classification labels and content digests; authorized
reviewers use the governed locator to reach raw evidence.

## Quickest fitting command

From the repository root, validate the redacted-receipt contract and vocabulary:

```bash
python3 -m unittest \
  tests.test_comparative_evidence.ComparativeEvidenceTests.test_redacted_receipt_uses_canonical_family_vocabulary \
  -v
```

The focused test establishes schema agreement for one synthetic reviewed
manifest. Material redaction quality and access authorization remain with the
evidence owner and reviewer.

## Evidence ceiling

A committed redacted manifest can establish the reviewed metadata and digests
it carries. It remains a source-control-safe projection of evidence; the raw
artifact, environment observation, and accountable decision retain their named
owners.

## Next route

- Begin observed admission at [`../../accepted/README.md`](../../accepted/README.md).
- Inspect the admission and comparison posture in
  [`../../release/repository-role.json`](../../release/repository-role.json).
- Use [`../../schemas/redacted-receipt.schema.json`](../../schemas/redacted-receipt.schema.json)
  when the manifest shape changes.

## Return to repository root

[Return to Comparative Evidence orientation](../../README.md).
