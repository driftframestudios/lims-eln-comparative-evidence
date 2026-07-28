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

Code and documentation state affirmative target behavior. Security and privacy
boundaries identify the governed continuation path: protected values become
classification labels and digests; raw evidence moves to approved storage; an
unqualified record returns to environment execution and accountable review.

