# Comparative evidence contribution guide

Start from `develop` with `feature/<bounded-change>`, `fix/<bounded-change>`,
or `chore/<bounded-change>` as accepted by `tools/check_branch_flow.py`. A pull
request identifies the comparison profile, scenario IDs, evidence classes, and
expected effect on prior reports.

Changes to expected results, normalizers, critical paths, tolerances, receipt schemas,
or the admission gate receive a reviewer independent from the implementation change.
This separation protects the comparator from learning the answer it is intended to
assess.

Release branches freeze profile, fixtures, and schemas. A released comparison defect
uses `hotfix/<defect>`, targets `main`, and returns to `develop`. Reports retain the
comparator version and profile digest.

Local comparator and admission tests remain the standing proof path. The
repository allocates 100–300 hosted runner minutes per month. One read-only,
cancellable Python 3.12 proof accompanies pull requests into `develop` and
`main`. The confirmed `verify-comparative-evidence` dispatch preserves the
three-version matrix, generated report, artifact check, and optional one-day
retention when a named receiver sets `ENABLE_GITHUB_ACTIONS=true` and selects
`confirm_run`.

`.github/dependabot.yml` supplies monthly GitHub Actions version updates into
`develop`, with at most two open pull requests. Minor and patch updates share
one bounded pull request; major updates retain separate review and recovery
coordinates. Default-branch security updates retain their `main` route.
Dependabot uses the complete
`dependabot/github_actions/<dependency-update>` grammar with
`dependabot[bot]`; Renovate uses `renovate/<dependency-update>` with
`renovate[bot]`. Each branch identity and target agree with the repository
checker. Each update receives the comparator and admission tests plus human
review. A security update accepted on `main` is reconciled into `develop`.

Code and documentation state affirmative target behavior. Security and privacy
boundaries identify the governed continuation path: protected values become
classification labels and digests; raw evidence moves to approved storage; an
unqualified record returns to environment execution and accountable review.
