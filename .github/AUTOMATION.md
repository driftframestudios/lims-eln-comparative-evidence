# Bounded hosted automation

## Pull-request proof

The repository allocates **100–300 GitHub-hosted runner minutes per month**.
`pull-request-proof` gives pull requests into `develop` and `main` one
review-visible check on Python 3.12. It uses one standard runner, read-only
repository permission, a ten-minute ceiling, and cancellation for a superseded
run. The repository test suite and aggregate validator exercise strict evidence
admission, deterministic comparison behavior, schema bindings, and repository
safety together. A dependency-free automation check parses the admitted YAML
subset, derives its effective controls, and requires them to agree with the
release manifest.

The final step verifies the complete retained release history. The original 0.3.1
receipt continues through its unchanged verifier, and the additive 0.3.2 observation
reuses that verifier's signed-tag and repository-safety engine.

Repository settings remain the authority for enabling Actions and selecting a
required check after its exact hosted name has been observed.

## Confirmed full proof

`verify-comparative-evidence` retains the Python 3.11–3.13 matrix, portable
report generation, artifact-boundary check, optional one-day report retention,
and stable matrix-result check. A named receiver can run it by setting
`ENABLE_GITHUB_ACTIONS=true`, selecting `confirm_run`, and dispatching the
workflow when that broader evidence is useful.

## Monthly dependency upkeep

`.github/dependabot.yml` checks pinned GitHub Actions monthly. Version-update
pull requests target `develop`, at most two remain open, and minor and patch
updates share one reviewable group. Major updates retain an individual review
coordinate. GitHub reads this configuration from the default branch, so the
reviewed schedule begins after release promotion to `main` and sends its
version-update pull requests back to `develop`.

## Recovery

Local comparison tests and `python3 tools/validate_repository.py` remain the
standing source-owned evidence. Setting `ENABLE_GITHUB_ACTIONS=false` rests the
confirmed full proof. Repository settings can pause all hosted execution. A
reviewed source change can return the dependency schedule to its manual
filename while preserving the ecosystem and branch contract.
