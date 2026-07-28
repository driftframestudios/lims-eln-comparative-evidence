# Comparative evidence contribution guide

Start from `develop` with `feature/<bounded-change>`. A pull request identifies the
comparison profile, scenario IDs, evidence classes, and expected effect on prior
reports.

Changes to expected results, normalizers, critical paths, tolerances, receipt schemas,
or the admission gate receive a reviewer independent from the implementation change.
This separation protects the comparator from learning the answer it is intended to
assess.

Release branches freeze profile, fixtures, and schemas. A released comparison defect
uses `hotfix/<defect>`, targets `main`, and returns to `develop`. Reports retain the
comparator version and profile digest.

Dependabot maintains immutable GitHub Action references on a monthly cadence.
Minor and patch updates may share one bounded pull request; major updates retain
separate review and rollback coordinates. Dependabot uses the complete
`dependabot/github_actions/<dependency-update>` grammar with
`dependabot[bot]`; Renovate uses `renovate/<dependency-update>` with
`renovate[bot]`. Either flow targets `main` or `develop`, and all three
coordinates must agree. Each update runs comparator and admission tests and
receives human review. A security update accepted on `main` is reconciled into
`develop`.

The branch-policy workflow receives pull-request metadata through a read-only
event, checks out the exact protected base SHA into `.base-policy`, and executes
only that base-controlled checker. Contributor code remains evidence input for
the ordinary verification workflow.

Code and documentation state affirmative target behavior. Security and privacy
boundaries identify the governed continuation path: protected values become
classification labels and digests; raw evidence moves to approved storage; an
unqualified record returns to environment execution and accountable review.
