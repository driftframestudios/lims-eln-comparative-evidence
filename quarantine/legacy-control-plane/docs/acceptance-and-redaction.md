# Acceptance and redaction policy

## Namespace admission

`accepted/` represents observed evidence only. The admission gate verifies source
identity, raw-artifact provenance, independent review, classification, and redaction.
Acceptance-stage records additionally carry separate scientific, Quality, and
Regulatory decisions.

A planned or simulated record remains on the comparison surface. Its continuation
path is an execution in the named environment followed by governed capture and
review.

## Evidence placement

| Evidence class | Location |
|---|---|
| Synthetic comparison fixture | Git |
| Redacted receipt manifest | Git after owner review |
| Raw configured-vendor export | governed evidence storage |
| Security finding details | restricted security evidence store |
| Regulated or identifiable record | approved regulated system |
| Credential or signing material | approved secrets service |

The repository retains stable digests and protected locators so reviewers can verify
lineage with appropriate authorization.

