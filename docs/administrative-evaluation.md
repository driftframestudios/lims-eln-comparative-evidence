# Compare administrative observations

Inspect normalization quality, policy agreement, scientific-content findings,
and workflow differences in one bounded offline comparison. Each score retains
its denominator, source pack, recorded execution, and independent expectation.

## Quick start

Use Python 3.12 or newer from this checkout. The optional profile resolves exact
Program and Simulation commits through the collaborator's existing Git access.
The ordinary Golden Specimen and observed-evidence routes remain independently
available through the [root README](../README.md#start-with-a-comparison).

```bash
python3 -m venv .venv-admin
.venv-admin/bin/python -m pip install --editable ".[administrative-study]"
.venv-admin/bin/python -m lims_eln_sim.administrative_pack \
  --output build/administrative-pack.json
.venv-admin/bin/python -m comparative_evidence.administrative_evaluation \
  --pack build/administrative-pack.json --fixture-demo \
  --output build/administrative-comparison
```

Open `build/administrative-comparison/comparison.html`. The directory also holds
the exact `comparison.json` and Program-admitted `study.json`. The default pack
plans 144 runs. Its demonstration includes abstention, failure, exclusion,
pending observations, and an intentionally changed scientific fact. Those
findings exercise the observer; they are useful evidence about this harness.

Choose a fresh destination for a separate comparison. To score a receiving team's
synthetic observations, replace `--fixture-demo` with `--study STUDY_JSON`.
The study must bind the same plans, specification, and expected-pair identities.
Actual outputs can agree, differ, remain partial, or carry a failed attempt.

## Read the scores

| Question | Result | Denominator and meaning |
| --- | --- | --- |
| Did normalization return the expected set? | Exact set agreement and Jaccard | Scored runs; two empty sets have Jaccard one |
| Which labels need attention? | Per-label counts, micro precision/recall/F1, macro F1 | Micro pools label decisions; macro weights the union of expected and observed labels in scored runs equally, including prediction-only labels |
| Was uncertainty or policy interpreted as expected? | Classification and policy agreement | Scored runs, beside planned-run coverage |
| Was raw source retained? | Exact raw-label preservation | Scored runs; original text stays in the local study |
| Was required information carried forward? | Required-fact recall | Required facts in scored runs |
| Was unsupported information introduced? | Unsupported-fact rate | Supplied facts in scored runs |
| What happened to workflow effort? | Paired difference in minutes | Within-subject repeat mean, then equal weight per complete paired subject |

Undefined ratios are `null`. Empty and small groups retain counts while their
workflow score stays withheld. The group threshold counts independent subjects,
rather than runs. The full local diagnostic report retains run-level findings;
its small-cell display rule is an interpretive safeguard, rather than a privacy
release mechanism. Any public population extract receives its own disclosure review.

Program's byte-identity comparison and eligibility companion remain separate
report sections. Parsed field scoring can distinguish harmless text formatting
from changed content. Probability calibration needs probability outputs, and
inferential intervals need a reviewed sampling design. This deliberately authored
distribution supports fixture and observer correctness; broader population,
causal, fairness, and deployment conclusions retain their own evidence routes.

## Ownership, recovery, and extension

Simulation owns the input pack and expected results. Comparative's fixture
producer uses its own literal rules and creates a separate observation artifact.
The evaluator admits caller observations through Program and computes scores
from those observations. Altering an expectation changes the evaluation while
the demonstration's emitted observations stay stable.

Every planned run remains visible, including unattempted and incomplete work.
Retain `study.json` as the finite observation checkpoint. A renewed comparison
can read that artifact without executing a model. Changed plans or specification
receive a successor study; existing observations keep their original bindings.

### Complete local bundles and recovery

The command prepares the three files in a private, invocation-owned sibling
directory, verifies their exact membership and meaning, then makes the complete
directory visible at the requested fresh destination. Existing destinations,
including empty directories and symbolic links, retain their contents. A second
concurrent invocation receives `bundle_destination_exists`; the successful
invocation retains its complete result.

The administrative receiver is
`comparative_evidence.administrative_artifacts.administrative_artifact_inventory(directory, admitted_pack)`.
It requires a separately admitted source pack, re-admits `study.json`, recomputes
the report, and checks the exact HTML projection. A `fixture_demonstration`
label binds the exact demonstration study for that pack; receiving observations
use `caller_supplied_synthetic`. Its three-file profile is
separate from the released two-file report verifier. Each member is a regular
file with one link; study, report JSON and HTML budgets are 2, 4 and 16 MiB,
respectively. The returned SHA-256 inventory identifies the verified bytes.
Saved-report admission is described below; bundle verification retains its exact
source recomputation and filesystem recovery contract.

Publication requires concrete parent directories and an exclusive directory
rename on a supporting local filesystem: Linux uses `renameat2` with
`RENAME_NOREPLACE`; macOS uses `renameatx_np` with `RENAME_EXCL`.
Directory descriptors anchor traversal and publication. A symlink in the parent
route receives an acquisition failure; select the concrete directory path.
The caller controls that parent namespace, and bundle verification reads a
quiescent directory. Independent publishers receive distinct staging names;
protection against a hostile same-user actor changing the namespace has its
own filesystem isolation requirements.
Other platforms or filesystems receive a held publication result. The primitive
contracts are documented in the
[Linux manual](https://man7.org/linux/man-pages/man2/rename.2.html) and
[Apple's system-call source](https://github.com/apple-oss-distributions/xnu/blob/main/bsd/man/man2/rename.2).

The publisher flushes and syncs each file, syncs the completed staging directory,
performs the exclusive rename, and syncs the destination parent. This establishes
complete visibility and successful operating-system sync calls. Storage-device
power-loss guarantees remain a separate environment property. A final parent-sync
failure returns `bundle_sync` with `published=True`: the complete bundle remains
available for verification. Preserve it and choose a new destination for another
comparison.

Before publication, acquisition, write, verification and rename failures retain
the existing destination and release invocation-owned staging. Correct the named
failure and retry the same still-absent destination. A cleanup failure retains
the primary error plus a separate cleanup diagnostic and the pending directory
name for local review. Abrupt process termination can leave a private
`.administrative-pending-*` sibling; a later invocation uses its own fresh staging
directory. Inspect and remove an abandoned sibling only after confirming its
owning process has ended. Previously published bundles retain their names and
bytes throughout recovery.

The administrative publisher carries one invocation state through preparation,
acquisition, writing, verification, staging sync, exclusive publication, parent
sync, and cleanup. A dedicated staging owner records the descriptor and directory
identity as they are acquired, then attempts each release once. Descriptor zero
is an owned descriptor. The publication operation transfers the private name to
the final name while termination signals wait for the ownership record.

| Boundary | Receiving behavior |
| --- | --- |
| Before exclusive rename | The final name retains its prior state; the owner releases its staging directory |
| After exclusive rename | The final name contains the complete bundle; the owner releases its descriptor |
| Operation plus teardown failure | The operation remains the cause and ordered cleanup observations remain locally inspectable |
| Cleanup interruption | The first `KeyboardInterrupt` or `SystemExit` retains control meaning after the remaining releases; prior operation and secondary cleanup observations remain attached |

The existing filesystem helpers own regular-file streams, anchored parent
traversal, identity checks and exclusive rename. This administrative owner composes
those mechanics with its own collision and interruption policies. The released
two-file report and manifest publishers keep their own replay policies. This
boundary avoids routing distinct public contracts through one general workflow.
Preparation and file traversal scale with artifact bytes; admission, sorting and
independent scoring retain their separately bounded costs. The lifecycle adds
constant resource state, with diagnostic storage proportional to observed
cleanup failures. Exact source recomputation remains the bundle's verification
step.

[Enterprise #36](https://github.com/driftframestudios/lims-eln-enterprise-implementation/issues/36)
owns the broader adapter handoff. [#40](https://github.com/driftframestudios/lims-eln-comparative-evidence/issues/40)
owns additional source admission and exercised recovery procedures.
[#44](https://github.com/driftframestudios/lims-eln-comparative-evidence/issues/44)
retains the independent Golden Specimen measurement question. Publication,
release tags, and external model execution remain separately authorized.

Return to [first receipt](../README.md#first-receipt).

## Admit a saved report

Use `comparative_evidence.administrative_report.admit_evaluation_report(payload)`
with immutable UTF-8 bytes. It returns an `EvaluationReport` using the existing
`urn:driftframe:comparison:administrative-evaluation:1.0.0` identity. The
executable contract lives in
[`administrative_report.py`](../src/comparative_evidence/administrative_report.py);
`EvaluationReport.model_json_schema()` supplies its structural validation
projection with local definitions. Runtime validators own cross-field meaning.
Program's exact `StudyComparisonReport` and `StudyInterpretation` types own
the nested identity and eligibility records. Python callers now access those
records through attributes, such as `report.eligibility.pairs`; their JSON
field names and values stay stable.

Admission checks strict JSON, finite numbers, unique keys, a 4 MiB input and
canonical-output ceiling, 32 container levels, and 100,000 decoded values.
Program's lexical depth check runs before decoding; its decoded-value and
bounded-output helpers retain their original ownership. The model permits
2 through 512 run records, 1 through 256 Program pairs, up to 4,096 attempts,
1 through 8 cohorts, and up to 16,384 distinct label rows. Nested Program
collections retain their own declared bounds. These limits bound accepted
representations; process memory and elapsed time require separate observations.

Counts use strict integers and exact equality. Ratios carry a numerator,
denominator, and value in [0, 1]; a zero denominator requires a zero numerator
and `null` value. Division and derived floating-point means use
`math.isclose(rel_tol=1e-12, abs_tol=1e-12)`. That tolerance applies to floats
only. Finite workflow measurements are integer minutes from 0 through 1,440;
paired differences occupy [-1,440, 1,440]. Scientific fact counts retain the
16-term output bound.

Run identities, two-arm pairs, cohort and subject membership, status
partitions, labels, scientific counts, aggregate scores, complete pairs and
equal-subject workflow means reconcile to the records present. Program
eligibility governs paired estimates. Macro F1 divides by the distinct labels
appearing in either expected or observed sets of scored runs; prediction-only
labels contribute zero F1. An empty label union produces `null` macro F1.
Two matching empty sets still have exact agreement and Jaccard one.

A saved report preserves declared counts and coherent relationships. The
1.0.0 format omits per-run retry histories, raw expected/observed label sets,
and the configured small-cell threshold. Admission checks attempted-count
bounds, agreement between aggregate populations, and a possible shared
threshold in the supported 2 through 32 range. Exact historical attempts,
label provenance and the selected threshold require the source-complete route:

```python
from comparative_evidence.administrative_report import (
    admit_evaluation_report,
    verify_evaluation_report,
)

report = admit_evaluation_report(payload)
reproduced = verify_evaluation_report(payload, pack=admitted_pack, study=admitted_study)
```

`verify_evaluation_report` re-admits both supplied sources, checks their
digests, recomputes the full report, and compares exact structure and counts
with the declared float policy. A known digest mismatch is returned even when
the other source is missing; matching partial sources receive
`report_sources_required`. The scoring digest binds Comparative's unchanged
profile, and the interpretation uses Program's default declared-input profile.
A `fixture_demonstration` claim additionally requires the exact demonstration
study. The pack's Program version and source coordinate, study specification
bindings, and accepted dependency pins retain their existing owners.

Both APIs raise `ReportAdmissionError` with a fixed `code` and safe text.
Categories distinguish JSON/resource failures, shape and nested-record
validation, ratio/run/group/count coherence, source bindings, missing sources,
fixture identity, and `report_recomputation`. Rejected values and detailed
source diagnostics stay with the caller. The renderer re-admits the report
before projecting the same values into HTML. The bundle receiver continues to
require canonical byte equality, which is stronger than float-tolerant semantic
recomputation, and preserves its existing staging and recovery behavior.

These signals support distinct decisions:

- Admission establishes self-consistency of the saved representation.
- A digest identifies the exact canonical content against a trusted coordinate.
- Recomputation establishes agreement with the admitted study and authored pack.
- Provenance review establishes whether those source identities and assertions
  are suitable for the receiving purpose.
- Accountable acceptance authorizes the next governed use.

A coherent altered score can pass admission and still fail recomputation.
The independent fixtures in
[`test_administrative_report.py`](../tests/test_administrative_report.py) exercise
that distinction, literal expected counts, empty and sparse observations,
failed and mismatched execution, withholding, parser budgets, and semantic
agreement between JSON and HTML. The existing evaluator and bundle recovery
checks remain the regression route.

This source is prepared for
[#56](https://github.com/driftframestudios/lims-eln-comparative-evidence/issues/56)
pending the Governance handoff and independent parent review. Merge, release,
publication, cloud execution and external-model execution retain their separate
authorization boundaries.

## Execution identity and paired evidence

The local demonstration records its own versioned producer identity and actual
repeat settings. A different requested identity appears as an execution mismatch
through the existing Program interpretation. Matching an authored fixture shows
that the evaluator can recognize the expected result; external model behavior
has its own authorized receiving study.

Paired workflow estimates require Program eligibility and two usable scored
outputs. Every planned run remains in coverage, including runs belonging to an
ineligible pair. The complete report retains Program's reasons alongside the
field-level scores, so a receiving reviewer can distinguish coverage, substantive
agreement, and comparison eligibility.
