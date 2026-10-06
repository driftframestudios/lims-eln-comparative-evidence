# Confined finite container job

This repository uses the prepared-input and confined-runtime pattern from Enterprise's reviewed container work. The profile in [container-profile.json](container-profile.json) owns the exact admitted source files and this repository's finite job. The shared preparation helper is owned by Program; [container-support.json](container-support.json) binds the receiving copy.

## Prepare and run

Choose a reviewed source checkout or a verified source-carrier component. Keep it quiescent during preparation. This route records content digests; the accepted source receipt supplies Git lineage separately. Select new external context and output directories through shell variables. The output directory belongs to the invoking non-root user.

```sh
mkdir -m 700 "$LIMS_JOB_OUTPUT" &&
uv run --isolated --no-project --python 3.12 --managed-python -- \
  python infra/container_job.py "$LIMS_JOB_CONTEXT" &&
export LIMS_RUNTIME_UID="$(id -u)" LIMS_RUNTIME_GID="$(id -g)" &&
docker compose -f infra/container-compose.yml build &&
docker compose -f infra/container-compose.yml run --rm job
```

This core profile uses standard-library behavior and the admitted source resources. Optional Program conformance and complete repository/release suites retain their existing dependency and proof routes.

## Ownership and recovery

The image has a non-root default. Compose selects the non-root owner of the host output directory, a read-only root, one writable output mount, bounded temporary storage, dropped capabilities, privilege-escalation protection, process/memory/CPU bounds, and a network-disabled finite job. The job checks its ordinary identity and output ownership before writing. Runtime credentials and daemon sockets are outside this profile.

Each invocation produces a new run directory containing its complete native artifacts under `payload/` and a sibling `job-receipt.json`. Simulation and Comparison apply their native artifact validators before publication. Earlier runs retain their names and bytes. Ordinary failure or termination cleans the owned pending directory. A forced kill or host failure can leave a pending directory; retain it for private inspection, then remove only that invocation's incomplete directory. The completed marker establishes a complete generated set at return, rather than power-loss durability. Context preparation requires a fresh external destination and writes its complete receipt last; a failed preparation can be repeated with a fresh destination.

## Evidence and release

Run the new focused tests with the existing unittest discovery pattern:

```sh
uv run --isolated --no-project --python 3.12 --managed-python -- \
  python -m unittest discover -s tests -p 'test_container_*.py' -v
```

The fixture tests cover exact context membership, declared byte digests, path/file boundaries, clean failure, retained output, and configuration. A configured run must additionally establish the selected platform and actual confinement, repeatable output, image/dependency findings, and a fresh secret canary. Base-image identity and vulnerability status are separate observations. Tagging remains held by the five-repository hardening gate until those results and independent review are accepted. Existing hosted triggers, private-history proofs, main review protection, and publication settings retain their owners.

[Docker build secrets](https://docs.docker.com/build/building/secrets/) and [Compose service controls](https://docs.docker.com/reference/compose-file/services/) supply the upstream contract.

## Review and extension boundary

The source tree and dependency directory are operator-owned and quiescent during preparation. Each copied file is bounded and digest-bound; staged directories receive mode 0755 and copied files mode 0644 inside the private mode-0700 context. Program owns both shared modules and their receiving-copy digests. Each repository owns its finite entry, native parser, native artifact validator, and exact source profile.

The runtime inspects every emitted member and propagates directory traversal failures. Native artifact families retain their own exact inventories under `payload/`; container metadata stays beside that family. A successful rename publishes one complete invocation. Retry creates a new invocation while prior completed runs retain their bytes.

[Research and design decisions](https://github.com/driftframestudios/lims-eln-program-specification/blob/codex/container-hardening/infra/container-design-evidence.md) connect the shared implementation to primary sources and focused counterexamples. Current image findings and actual Compose behavior remain separate release evidence.
