# Simulated closure namespace

This namespace receives immutable, validated closure bundles for selected future
realities. Each bundle carries the exact governance 2.0.0 closure projection and the
four detailed receipts that reproduce its family and aggregate digests. Closure uses
`evidence_mode: simulated`, `closure_status: closed_in_simulation`,
`environment_observed_closure: separate_unasserted_state`, and
`production_authorization_effect: none`.

The admission command creates files here during a release workflow. Generated
admission output remains outside Git until review selects a release artifact.

An observed encounter can later be compared with a simulated closure. That comparison
adds evidence while preserving the selected future, canonical governance digest, and
non-authorizing boundary.
