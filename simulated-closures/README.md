# Simulated closure namespace

## Reader job

Use this namespace when a release workflow needs to admit one immutable,
validated closure bundle for a selected future reality.

## Current state

The checked-in namespace contains guidance only. The canonical source fixture
is
[`future-reality-2028-06-30-v1.json`](../fixtures/simulated-closures/future-reality-2028-06-30-v1.json);
reviewed admission output becomes a distinct release artifact in this namespace.

## Owner and schema

The selected-future release steward owns admission. The bundle contract is
[`simulated-closure-bundle.schema.json`](../schemas/simulated-closure-bundle.schema.json),
and [`simulated_closure.py`](../src/comparative_evidence/simulated_closure.py)
verifies the canonical Governance projection, four detailed receipt families,
family and aggregate digests, and immutable destination behavior.

## Use

From the repository root, admit a reviewed closure bundle through the bounded
command:

```bash
PYTHONPATH=src python3 -m comparative_evidence.cli admit-simulated \
  --closure-bundle fixtures/simulated-closures/future-reality-2028-06-30-v1.json \
  --accepted simulated-closures/
```

The admitted bundle records `evidence_mode: simulated`,
`closure_status: closed_in_simulation`, and
`environment_observed_closure: separate_unasserted_state`.

Generated manifests become visible after their complete bytes are verified.
An identical generated-byte replay returns the accepted path; changed bytes
require the namespace's new-identity route. Follow the
[artifact publication guide](../docs/artifact-publication.md) when an interrupted
run or an occupied entry needs recovery.

## Quickest fitting command

Exercise the canonical closure and immutable admission path:

```bash
python3 -m unittest \
  tests.test_comparative_evidence.ComparativeEvidenceTests.test_selected_future_closure_admission_is_immutable \
  -v
```

The focused test establishes source validation and destination immutability for
the canonical bundle within a temporary directory.

## Evidence ceiling

The bundle closes the modeled receipt families inside its declared selected
future. It supports comparison and grants `production_authorization_effect:
none`. A later observed encounter adds independent evidence while preserving
the selected future and its canonical Governance digest.

## Next route

- Inspect the canonical fixture under
  [`../fixtures/simulated-closures/`](../fixtures/simulated-closures/).
- Read the comparison result and evidence posture in the
  [root orientation](../README.md#first-receipt).
- Trace release and closure identities through
  [`../release/repository-role.json`](../release/repository-role.json).

## Return to repository root

[Return to Comparative Evidence orientation](../README.md).
