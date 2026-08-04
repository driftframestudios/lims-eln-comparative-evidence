# Comparative evidence contribution guide

Start from `develop` with `feature/<bounded-change>`. Describe the affected scenario,
evidence fields, comparison paths, and expected report behavior in the pull request.

Changes to schemas, critical paths, tolerances, reportable values, or example results
receive focused review because each can change the meaning of a vendor comparison.
Tests cover the intended evidence contract and comparison behavior. Fixtures use
synthetic, deidentified, or redacted content and state their limitations.

Release branches freeze package, schemas, profiles, and fixtures together. Released
defects use `hotfix/<defect>` and return to `develop`. Standard repository protection
and review support the GitFlow-like branch convention; automation branches use their
native Dependabot or Renovate names.

Documentation and code comments state target behavior in affirmative terms. Security
and privacy boundaries direct sensitive material to its designated system while the
repository retains redacted locators, evidence metadata, and comparison results.
