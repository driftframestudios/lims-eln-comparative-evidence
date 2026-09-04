# Comparative Evidence collaboration ground

This repository owns independent comparison, observed-evidence admission, and
deterministic report generation for the LIMS/ELN program. Make changes here
when comparison meaning, evidence posture, report behavior, or its living
publication route needs to change.

## Begin with current source

- Run `git status --short --branch` and read the latest local and remote
  history.
- Read [`README.md`](README.md),
  [`release/repository-role.json`](release/repository-role.json),
  [`machine-node.json`](machine-node.json), [`first-receipt.json`](first-receipt.json),
  [`COORDINATION-HORIZON.json`](COORDINATION-HORIZON.json), and
  [`constellation.lock.json`](constellation.lock.json) before changing
  comparison behavior or a receiving route.
- Treat runnable source and tests as current behavior. Treat the signed tag,
  promotion receipt, and released report identities as accepted-release
  evidence. Living orientation can advance while those release records remain
  immutable.
- Preserve unrelated work already present in the worktree.

Use
[`repository-reentry`](.agents/skills/repository-reentry/SKILL.md)
when resumed work needs current branch, release, public-baseline, and receiving
state reconstructed.

Use
[`source-authority-mapping`](.agents/skills/source-authority-mapping/SKILL.md)
when producer evidence, Comparator-owned snapshots, profiles, runtime reports,
release records, or public projections could be treated as the same authority.

Use
[`deterministic-comparison-report-projection`](.agents/skills/deterministic-comparison-report-projection/SKILL.md)
when report generation, rendering, source-bound Pages construction, projection
identity, or hosted report bytes change.

Use
[`contextual-jargon-scan`](.agents/skills/contextual-jargon-scan/SKILL.md)
in stride when public or cross-repository prose may assume local context.
Retain exact comparison, evidence, release, Git, scientific, and regulatory
language; define useful compact terms and revise shorthand whose object or
consequence remains unclear.

These four skills remain public-possible while repository use and review
establish whether each is ready for a separate public projection. A future
public projection includes only skills that complete a public-ready review.

## Keep authority and evidence roles distinct

- Profiles and schemas define comparison and admission contracts.
- Producer-owned evidence retains its source authority. Comparator-owned
  snapshots record accepted source coordinates without becoming producer
  releases.
- Runtime JSON is the machine-readable report; its HTML semantic twin is the
  human-readable rendering of the same comparison.
- Two isolated runs and complete byte inventories establish deterministic
  behavior for the named source and inputs.
- A signed release establishes an immutable comparison baseline. A later main
  carrier or docs revision can publish that baseline without changing its
  report meaning.
- Simulated and planned evidence retain their declared scope. Environment
  observations enter through the independent admission route. Comparison and
  publication grant no production authorization.

## Use the accepted branch route

- `main` contains released comparison baselines; `develop` integrates the next
  comparator state.
- Begin bounded work from `develop` on `feature/`, `fix/`, or `chore/`, then
  return it to `develop` through review.
- Form `release/<semver>` when one candidate freezes profiles, fixtures, and
  schemas. Form a `hotfix/` from `main` for an accepted release repair, then
  merge the accepted correction forward into `develop`.
- Keep signed tags and accepted report identities immutable so later
  comparisons can recover what the team accepted at that time.

## Write toward the verifiable state

- Lead with the behavior a collaborator can create or verify.
- Pair a safety, privacy, scope, or authority boundary with the affirmative
  behavior that keeps the comparator useful.
- Use ordinary language around exact technical and regulated terms. Define
  repository shorthand where it first changes a reader's decision.
- State what each observation establishes before its coverage boundary.
- Keep personal attribution in the repository's approved carriers. Commit,
  Issue, pull-request, and review prose stays focused on the change.

## Validate the material behavior

Use a configured Python 3.12 interpreter for the complete source-owned proof.
The examples below assume `python3` resolves to that interpreter:

```sh
python3 -m unittest discover -s tests -v
python3 tools/validate_repository.py
python3 tools/verify_release_coordinate.py --require-observed
git diff --check
```

The aggregate validator checks strict JSON and schema contracts, regenerates
both report families and the Pages candidate twice, compares complete byte
inventories, verifies release and living-publication bindings, and scans
repository text for credential-shaped values.

## Close with one clear receiver

Return the changed source, the smallest observation that establishes its
behavior, its evidence limit, and the repository or accountable role that can
make the next decision. Name the exact event that reopens a waiting route.
