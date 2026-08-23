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

Local comparator and admission tests are the standing proof path. GitHub Actions
rests disabled in repository settings at a **$0** budget. The manual
`verify-comparative-evidence` workflow becomes available only when a named human
enables Actions, sets `ENABLE_GITHUB_ACTIONS=true`, selects `confirm_run`, and
dispatches it. After the proof is read, set `ENABLE_GITHUB_ACTIONS=false` and
disable Actions in repository settings to restore the resting state.

Dependency scheduling rests in `.github/dependabot.manual.yml`. A reviewed
rename to `.github/dependabot.yml` activates its monthly cadence. When active,
minor and patch updates may share one bounded pull request; major updates retain
separate review and rollback coordinates. Dependabot uses the complete
`dependabot/github_actions/<dependency-update>` grammar with
`dependabot[bot]`; Renovate uses `renovate/<dependency-update>` with
`renovate[bot]`. Either flow targets `main` or `develop`, and all three
coordinates must agree. Each update receives the local comparator and admission
tests plus human review. A security update accepted on `main` is reconciled into
`develop`. The repository-local branch checker remains available to reviewers;
the resting state has no automatic branch-policy workflow.

Code and documentation state affirmative target behavior. Security and privacy
boundaries identify the governed continuation path: protected values become
classification labels and digests; raw evidence moves to approved storage; an
unqualified record returns to environment execution and accountable review.
